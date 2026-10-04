# DashAI: сохраненный MCP путь после будущего обновления VS Code

04.10.2026. Агент `vscode_actual_test`, независимый review `dashai_critic`. **PASS**, exit code **0**: `artifacts/qa/vscode-handoff-087a3d3f82/results.json`.

```powershell
.venv/Scripts/python.exe scripts/vscode_handoff_smoke.py
```

Проверка использует две копии настоящего текущего frozen build **1.4.0** в изолированной личной папке. У второй копии изменено **только** поле версии bundled `package.json` на **1.5.0**. Это metadata fixture для проверки маршрутизации, а не заявление о существовании будущего выпуска. USERNAME, LOCALAPPDATA, SQLite и credentials отдельные; рабочие проекты пользователя не затронуты.

GUI fixture запущен в `--vscode` режиме. После SDK-вызова сохраненного MCP executable из папки 1.4.0 native `Win32_Process` подтвердил родитель **PID 47400** и непосредственный child **PID 142876** из папки fixture 1.5.0. Выполнены настоящие stdio initialize и tools: создан подпроект, создана задача в нем, те же ID прочитаны через работающий HTTP API. В audit history сохранены actor `codex` и исходный session ID. В обеих runtime папках отсутствуют копии SQLite. После закрытия клиентского stdio child завершился, MCP handle освобожден, сервер остановлен штатно.

Первая настоящая проверка до исправления поймала blocker: parent запускал новый child, но stdio initialize не получал ответа. Прямое подключение к тому же newer executable работало. Независимый native Windows эксперимент критика воспроизвел причину: `CREATE_NO_WINDOW` с omitted stdio не сохранял нужные client pipe handles. Минимальное исправление — явные `stdin=sys.stdin`, `stdout=sys.stdout`, `stderr=sys.stderr` в стандартном `subprocess.call`; не добавлены PIPE, прокси или новый transport. После исправления frozen сценарий выше завершился успешно.

Подписанный updater проверяется отдельно; fixture не подменяет проверку подписи, publisher key, размера или SHA-256 реального релиза.
