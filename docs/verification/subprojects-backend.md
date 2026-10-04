# Подпроекты DashAI: backend и MCP

Проверено 4 октября 2026 года на Windows, production-интерпретатор `.venv-build` Python 3.14.3. Эта запись подтверждает domain/API/MCP и совместимость данных; проверка интерфейса и выпуска VSIX фиксируется отдельно.

```powershell
.venv-build/Scripts/python.exe -m pytest tests -q
```

Фактический результат: **25 passed, 931 warnings, 37.80 s**. Предупреждения исходят из установленных FastAPI/Starlette/Pydantic: устаревающие asyncio/AnyIO API и незавершенная forward annotation `lifespan`; ошибок тестов нет. До общей проверки целевой запуск API/MCP дал **18 passed, 832 warnings, 26.28 s**.

Подпроект остается метаданными принадлежности на одной общей доске проекта. Проверены создание трехуровневого дерева, изменение названия/родителя, перенос в корень, выбор/изменение/очищение подпроекта задачи, сохранение типа и группы при смене статуса, board/export и восстановление после перезапуска. Legacy-разделы остаются отдельной совместимой коллекцией; их нельзя выдавать за подпроекты или передавать новый подпроект через `section_id`.

Domain проверки отклоняют самоссылку, циклы, ссылки между проектами, несуществующие или неподходящие контейнеры, неизвестные поля, пустые изменения и stale version. Два конкурентных переподчинения A→B/B→A выполняются под SQLite `BEGIN IMMEDIATE`: проходит только одно, второе возвращает 422, дерево остается ацикличным. Неудачные операции не меняют entities, tasks, audit или idempotency. Изменение и событие сохраняются атомарно; причины, before/after, actor и session проверены.

Idempotency повторяет исходный успешный ответ без второго события. Для nullable `subproject_id` и `parent_id` пропущенное поле и явный `null` являются разными намерениями: повтор с измененным содержимым возвращает 409. Старые cached create/patch до новых полей продолжают работать с read-time default. Тест старой базы сравнивает все исходные строки проектов, разделов, задач, notes, событий, agents и cached responses до/после чтения, перезапуска и legacy-повторов: переписывания не происходит; credentials неизменны. FK-check пустой.

`tests/test_mcp.py` запускает отдельный HTTP сервер с временной SQLite и два настоящих stdio `ClientSession` официального MCP SDK. Codex и Claude создают вложенные подпроекты, читают общую доску, независимо занимают две задачи в разных направлениях и видят shared state. Проверены фильтр с потомками/без потомков, исключение живых claims из ready queue, безопасный `null`, optimistic conflict, subproject audit и session correlation. На 500 подпроектах проверены bounded summaries, context и независимая пагинация; коннектор не открывает SQLite.

В рабочей локальной доске через MCP создана и занята **AD-012**; записаны decision, `log_change` и evidence с фактическими результатами. Название существующего проекта изменено на **DashAI** авторизованным HTTP PATCH после чтения актуальной version. Рабочая база не наполнялась тестовыми деревьями: сценарии запускаются в временных каталогах.

Независимый критик повторил API/MCP проверки: **18 passed, 24.36 s**. Два обнаруженных замечания исправлены и покрыты проверками: неоднозначный legacy `section_id` и пропущенное поле против явного `null` в повторном PATCH. Итог correctness/security и отдельного Ponytail review: [subprojects-review.md](../reviews/subprojects-review.md). Новых runtime-зависимостей и второго store не добавлено.

## Продолжение: MCP после обновления VSIX

Добавлен переход старого постоянного VS Code companion к новой активной версии при следующей MCP-сессии. Он действует только для frozen executable в известной папке личного runtime с explicit `--data-dir`, без URL override. Новая версия должна быть строго выше текущей, ее descriptor указывать тот же каталог данных и точный MCP executable; package marker и живой bounded `/api/health` должны подтвердить version, mode, instance UUID и integer PID. Source/desktop режим, равная/старая версия и явный URL не перенаправляются. Некорректный кандидат или неподтвержденный API не запускают внешнюю программу. Переход сохраняет stdio, рабочую папку, остальные аргументы и session ID, не читает token и не создает второй store. Signed updater проверяет VSIX до размещения runtime; персональные файлы остаются внутри доверенной границы пользователя ОС.

После добавления перехода полная production suite: **27 passed, 931 warnings, 24.45 s**. Последующее замечание root о сохранении рабочей папки исправлено удалением `cwd` override; два целевых forwarding-теста повторно прошли: **2 passed, 5 deselected, 1.23 s**. Проверены path/version/source/URL/marker guards, UUID/PID/mode/health совпадение, bounded response, отсутствие auth/proxy/redirect, stop-forward на новой версии, аргументы и сохранение relative token-file, native stdio без capture, environment reset, session ID и exit code. В этих тестах native launch подменен проверяющим stub; реальный переход между двумя frozen runtime должен отдельно пройти финальную проверку сборки.

Новый процесс получает `PYINSTALLER_RESET_ENVIRONMENT=1` и сброс DLL directory существующим helper: это поддержанный public механизм самостоятельного child bootloader, описанный в [PyInstaller 6.22.3 Advanced Topics](https://pyinstaller.org/en/stable/advanced-topics.html#environment-variables-used-by-frozen-applications). Private `_PYI_` переменные вручную не изменяются.

Первый реальный native handoff выявил проблему, которую stub не покрывал: старый frozen companion запускал новый процесс, но `initialize` зависал при полностью пропущенных stdio arguments и `CREATE_NO_WINDOW`. Прямой запуск того же нового companion с тем же API работал. Независимый критик воспроизвел разницу на настоящем WinPython: пропущенные streams не передают нужные pipe handles, а явные родительские streams передают. Исправление задает `stdin=sys.stdin`, `stdout=sys.stdout`, `stderr=sys.stderr` в native subprocess call, сохраняя прямой stdio без PIPE, relay, shell или capture. Тест проверяет тождество трех streams; после исправления **2 targeted tests passed, 1.24 s**. Перед публикацией требуется повторный реальный frozen handoff с пересобранным companion; первоначальное зависание не выдается за успешный результат.
