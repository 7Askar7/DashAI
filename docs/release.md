# Установка на компьютер и выпуск обновлений

Agentboard 1.1.0 упакован как приложение Windows 10/11 x64. Пользователю достаточно запустить `Agentboard-Setup-1.1.0.exe`: Python, Node.js и checkout ему не нужны. Установка не запрашивает права администратора. Ярлык «Agentboard» открывает приложение и локальную доску в браузере.

Программа устанавливается в `%LOCALAPPDATA%\Programs\Agentboard`. Каждый пользователь Windows хранит свое пространство в `%LOCALAPPDATA%\Agentboard`: база, история, credentials, резервные копии и логи. Установщик не содержит ни проектов разработчика, ни его токенов. Обновление заменяет программу, сохраняя личные данные. Удаление приложения также сохраняет эту папку; стереть личные данные можно отдельно после резервной копии.

Ярлык на рабочем столе и запуск при входе в Windows — отдельные необязательные пункты установщика. MCP работает через консольный `AgentboardMCP.exe`; он использует API того же установленного приложения и той же личной базы. Конфигурацию Codex/Claude Code нужно создать для выбранного репозитория через приложение. Наличие программы не заменяет установленный клиент агента или его обычное разрешение MCP.

## Как приходят обновления

В установщик встраиваются адрес стабильного канала и публичный ключ издателя. Приложение проверяет подписанный `latest.json`, принимает только более новую версию, скачивает установщик по HTTPS и сверяет его размер и SHA-256 с подписанным манифестом. Перед установкой создается SQLite backup с проверкой `integrity_check`.

Обновление откладывается, пока MCP-клиенты используют приложение. Живые сессии агентов не завершаются принудительно. После закрытия приложения внешний Windows helper запускает установщик, затем приложение открывается снова. Downgrade запрещен также самим установщиком; повторная установка той же версии допустима. Отсутствие сети или ошибка подписи не стирают данные и не мешают работе текущей версии.

Helper использует штатный Windows PowerShell 5.1 и его системные модули. Унаследованный от PowerShell 7 путь модулей сбрасывается внутри helper-процесса; настройки PowerShell пользователя не изменяются. Это проверяется отдельным regression test и при сборке в GitHub Actions.

Канал этого проекта: [7Askar7/DashAI Releases](https://github.com/7Askar7/DashAI/releases), манифест `https://github.com/7Askar7/DashAI/releases/latest/download/latest.json`. Установщик содержит этот адрес и публичный ключ издателя. До публикации подписанного релиза отсутствие feed не мешает работе локальной доски. Закрытый GitHub-репозиторий потребует доступного пользователям HTTPS-хостинга файлов; токен GitHub не встраивается в приложение.

## Один раз настроить издателя

1. Разместить этот проект в [7Askar7/DashAI](https://github.com/7Askar7/DashAI) с публично доступными Releases.
2. Для этого проекта Ed25519 ключ издателя уже создан: private key хранится отдельно в gitignored `data/publisher/ed25519-private.key`, а public key — в `packaging/update-public-key.txt`. Сохранить отдельную надежную резервную копию private key. **Не генерировать новый ключ для следующего релиза:** существующие установки доверяют текущему ключу. Для нового независимого проекта команда сохраняет private key в указанном новом файле и печатает только public key:

   ```powershell
   .venv/Scripts/python scripts/release.py keygen --private-key-file "C:/secure/agentboard-update-private.txt"
   ```

3. В GitHub Settings → Secrets and variables → Actions добавить **secret** `AGENTBOARD_UPDATE_PRIVATE_KEY`: содержимое private-файла. Public key workflow читает из `packaging/update-public-key.txt`; необязательная **variable** `AGENTBOARD_UPDATE_PUBLIC_KEY` может переопределить его. Private-файл не добавлять в Git, installer или историю задач.
4. Workflow использует `https://github.com/OWNER/REPO/releases/latest/download/latest.json` из имени текущего репозитория. Для собственного HTTPS-хостинга указать variable `AGENTBOARD_UPDATE_MANIFEST_URL` и публиковать туда тот же подписанный `latest.json` и установщики. Адрес нельзя менять у уже установленных клиентов без доступного старого канала или новой ручной установки.

Публичный ключ не является секретом. Подпись манифеста защищает канал от подмены установщика. Это отдельный механизм от Windows Authenticode: текущий EXE не подписан платным сертификатом издателя, поэтому Windows может показать предупреждение SmartScreen при первой установке.

## Выпустить новую версию

Изменить версию в `package.json` и `package-lock.json`, проверить изменения, сохранить их в commit и создать совпадающий tag:

```powershell
git add .
git commit -m "Release 1.1.1"
git push origin main
git tag v1.1.1
git push origin v1.1.1
```

Workflow `.github/workflows/release.yml` на Windows собирает production UI, два самостоятельных EXE и Inno Setup installer, запускает тесты, подписывает манифест и публикует Release с `Agentboard-Setup-1.1.1.exe` и `latest.json`. Private key доступен только шагу подписи. В installed bundle попадают публичный ключ, адрес канала и лицензии зависимостей.

Выпуск можно запустить также без терминала: GitHub → Actions → **Windows release** → **Run workflow** для выбранной ветки. Workflow берет версию из `package.json`, создает соответствующий tag и Release для того же commit, который был собран. Уже существующий Release с этой версией не перезаписывается: для следующего выпуска увеличьте версию.

Tag должен совпадать с `package.json`; prerelease suffix в этом стабильном канале не используется. GitHub Release считается готовым только после успешного workflow. Не удаляйте установщики предыдущих версий: у пользователей мог уже скачаться подписанный манифест с прежним URL. Изменение схемы базы должно сохранять данные и проходить проверку обновления с предыдущей реальной версией, а не только запуск на пустой базе.

## Собрать локально

На компьютере издателя нужны Python 3.14, Node.js 22 и официальный [Inno Setup](https://jrsoftware.org/isdl.php). Конечным пользователям эти инструменты не нужны. Сборка использует отдельную `.venv-build` и зафиксированные `requirements-build-lock.txt`, не изменяя development `.venv`.

```powershell
# Без update-канала — полностью автономная локальная установка.
./scripts/build-desktop.ps1

# С настроенным каналом для распространения.
./scripts/build-desktop.ps1 -ManifestUrl 'https://github.com/7Askar7/DashAI/releases/latest/download/latest.json'
```

Результат: `artifacts/releases/Agentboard-Setup-1.1.0.exe`; распакованное приложение: `artifacts/desktop/Agentboard/`. Build читает только явно перечисленные ресурсы, а не копирует весь checkout. `data/`, `.mcp.json`, `.codex/config.toml`, Git и development environment не упаковываются. Если compiler установлен нестандартно, передать `-InnoCompiler 'C:/path/to/ISCC.exe'`.

Если `python` в PATH указывает на старую среду, при первой сборке передать `-PythonExecutable 'C:/Python314/python.exe'`. Версия Python runtime включается в EXE; старые Anaconda environments не используются для распространяемой сборки.

Для собственного хостинга подписать уже собранный установщик:

```powershell
.venv-build/Scripts/python scripts/release.py manifest --installer artifacts/releases/Agentboard-Setup-1.1.0.exe --version 1.1.0 --installer-url 'https://example.org/releases/Agentboard-Setup-1.1.0.exe' --private-key-file 'C:/secure/agentboard-update-private.txt' --public-key 'BASE64_PUBLIC_KEY' --output artifacts/releases/latest.json
```

## Проверить перед распространением

```powershell
.venv-build/Scripts/python -m pytest tests -q
.venv-build/Scripts/python scripts/frozen_smoke.py
```

Frozen smoke запускает собранный EXE с отдельной временной папкой и проверяет реальный stdio MCP companion через официальный SDK. Дополнительно установите EXE на чистой Windows-учетной записи: создать проект, обновить приложение, проверить сохранение истории и credentials, удалить приложение и подтвердить сохранение личной папки. Локальные автоматические проверки не заменяют эту проверку следующей миграции схемы.

Первичные документы для выбранной сборки: [PyInstaller spec/data files](https://pyinstaller.org/en/stable/spec-files.html), [PyInstaller console/windowed](https://pyinstaller.org/en/stable/usage.html), [Inno per-user install](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm), [Inno AppMutex](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm), [Inno version comparison](https://jrsoftware.org/ishelp/topic_isxfunc_comparepackedversion.htm), [Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/), [GitHub workflow permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
