# Независимая проверка Windows установки и обновлений

Дата: 4 октября 2026 года. Проверяющий: отдельный агент `desktop_critic`; авторы runtime, коннектора и упаковки — другие агенты. Прочитаны архитектура, исследования, desktop runtime, updater, MCP companion, Inno script, build/release scripts и GitHub Actions workflow. Проверка не изменяла рабочую базу пользователя.

## Закрытые замечания

| Замечание | Исправление | Проверка |
|---|---|---|
| Frozen runtime читал отсутствующий `package.json` и мог завершиться до запуска | Файл версии включён в bundle | Реальный frozen smoke запускает GUI/API и companion |
| Companion мог ждать установщик, удерживая собственный executable и DLL | Handoff запускает отдельный Windows PowerShell; он ждёт завершения обоих frozen процессов | Реальная установка и native handoff проверяются отдельно от unit tests |
| `Split-Path -LiteralPath ... -Parent` не работает в Windows PowerShell 5.1; ошибка возникала до catch | Использован `System.IO.Path.GetDirectoryName` | Воспроизведено на настоящем `powershell.exe`; отказ повреждённому installer теперь сохраняет журнал |
| SQLite context manager не закрывал соединения backup и оставлял Windows file handles | Использован `contextlib.closing` | Backup живого WAL содержит committed запись; source и backup сразу удаляются без WinError 32 |
| Старый установщик мог перезаписать более новую установленную версию | Inno сравнивает сохранённый DisplayVersion в HKCU | Проверяется запуск настоящего старого installer после обновления |
| Uninstall мог оставить собственный Run entry, указывающий на удалённый exe | Удаляется только значение, совпадающее с установленным executable | Проверяется owned autostart entry; чужое значение не переписывается тестом |
| MCP SDK закрывал исходный stdout; PyInstaller при выходе повторно flush-ил оба aliases | После окончания протокола заменяются `sys.stdout` и `sys.__stdout__` | Ошибка воспроизведена в первом installer; финальный frozen smoke явно запрещает Traceback в stderr |
| CI запускал Python из PowerShell 7; Windows PowerShell 5.1 helper наследовал несовместимый PSModulePath и не находил Get-FileHash | Внутри native helper задан каталог встроенных Windows PowerShell modules; глобальные settings и parent environment не изменяются | Отдельно повторён real native test с намеренно несуществующим inherited PSModulePath: 1 passed; helper дошёл до проверки SHA-256 и отказал повреждённому installer |

## Сохранённые проверки

`tests/test_desktop.py`: **2 aggregate tests прошли**, в том числе в production build environment с Python 3.14. Они проверяют неверный publisher key, изменение подписанного payload, rollback/same version, HTTPS границу и запрет HTTP redirect, размер manifest/installer, checksum, timestamp, превышение размера потока, очистку частичной загрузки, повреждение после загрузки и правильное закрытие WAL backup. HTTPS тела в unit test подставляются; настоящим сетевым скачиванием этот тест не является.

После CI finding независимо повторён изменённый `test_live_wal_backup_closes_handles_and_native_handoff_rechecks_hash`: **1 passed**. Он передаёт helper неправильный `PSModulePath`, поэтому успешный refusal по SHA-256 подтверждает использование рабочих встроенных modules, а не случайный ранний отказ из-за отсутствующего cmdlet.

Дополнительный независимый прогон `artifacts/qa/desktop_adversarial.py`: **19 проверок прошли**, включая настоящий Windows PowerShell с повреждённым installer по пути с пробелами и квадратными скобками. Исполняемый файл не запускается при неправильной SHA-256.

`scripts/frozen_smoke.py`: финальный bundle прошёл version, UI/API, project configs и real stdio MCP hierarchy. Персональная база теста отдельная. Наличие `.mcp.json` само по себе не выдаётся за подключение: SDK действительно выполняет `initialize` и tools.

## Реальный жизненный цикл

Прогон `artifacts/qa/desktop_lifecycle.py` выполняется с отдельной установочной папкой и временным `LOCALAPPDATA`. Перед установкой проверяется отсутствие существующей HKCU регистрации Agentboard; при сбое удаляется только собственная тестовая установка. Fixture 1.1.1 создаётся из копии bundle, меняет версию ресурса и использует настоящий Inno installer с запретом автоматического открытия браузера. Он подписан ключом издателя; приватный ключ не выводится в журнал и не попадает в bundle.

Финальный lifecycle: **7 из 7 проверок прошли**.

1. Настоящий installer установил приложение без административного режима в отдельную папку.
2. Работающий desktop mutex запретил повторную установку; процесс и база продолжили работу.
3. Frozen companion проверил подпись и checksum, запустил native PowerShell и завершился; PowerShell дождался обоих процессов и настоящий Inno заменил bundle.
4. Обновлённый companion и runtime показали 1.1.1. Совпали все сохранённые поля export: project, sections, tasks, notes, audit events и IDs; совпали исходные bytes credentials. Исключена только `exported_at`, которая описывает время нового запроса экспорта.
5. Настоящий старый installer 1.1.0 отказался понизить установленную 1.1.1.
6. Uninstaller удалил принадлежащий приложению autostart Run entry.
7. Uninstaller удалил executable и регистрацию, сохранил персональную базу и credentials; SQLite `integrity_check` вернул `ok`, задача осталась в базе.

Артефакты: `artifacts/qa/desktop-lifecycle-20261004-172146/result.json`, installer/uninstall logs и MCP stderr log. Тестовая HKCU регистрация после проверки отсутствует. Папка рабочей базы пользователя не использовалась. Это проверка замены приложения и сохранения текущей схемы, не испытание будущих миграций базы. Fixture 1.1.1 не является опубликованным релизом.

## Границы и первичные источники

`sys.executable` в frozen приложении — bootloader, поэтому MCP получает отдельный console executable; GUI не использует stdout как transport. [PyInstaller runtime information](https://pyinstaller.org/en/stable/runtime-information.html), [windowed mode and external programs](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html).

Установка использует `PrivilegesRequired=lowest`; `AppMutex` защищает запуск installer/uninstaller при работающем приложении. Автоматический updater ждёт освобождения handles и не применяет force close к агентам. [Inno per-user mode](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm), [AppMutex](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm), [CloseApplications](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm), [Microsoft mutex API](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw).

Ed25519 проверяется готовым API cryptography; SHA-256 и signed size связывают manifest с installer. Это небольшой pinned-key updater, без заявления о полной реализации TUF или автоматической ротации ключей. [cryptography Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/), [TUF update specification](https://theupdateframework.github.io/specification/latest/).

Для WAL используется SQLite backup API; обычное копирование файла активной базы не применяется. [Python sqlite3 backup](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup).

Microsoft отдельно описывает этот Windows PowerShell compatibility случай: прямой запуск из PowerShell 7 корректирует module path, но промежуточный Python процесс передаёт исходный PS7 path; Windows PowerShell может найти несовместимую версию общего module и сломать autoloading. Native helper теперь использует только встроенные modules своего Windows host. [Microsoft: PSModulePath and intermediate processes](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath?view=powershell-7.5).

Личная база находится отдельно от обновляемых executable и сохраняется при uninstall. Это локальное хранение и separate stores; приложение не предоставляет изоляцию localhost API от других недоверенных Windows аккаунтов на одном компьютере.

## Отдельный Ponytail review

Прочитан `.agents/skills/ponytail-review/SKILL.md`. Проверены desktop modules, console companion, PyInstaller spec, Inno installer, сборка, publisher CLI и workflow. Два executable нужны для разных console режимов; queue/thread нужны для неблокирующего updater; криптографическая зависимость защищает запуск обновлений. Повторяющихся framework layers, speculative interfaces и лишних runtime зависимостей не обнаружено.

**Lean already. Ship.**
