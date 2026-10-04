# DashAI: review отклонения первой публикации Marketplace

05.10.2026. Независимый критик `dashai_critic`; Ponytail full. Пользователь сообщил, что ручная загрузка кандидата **1.4.1** отклонена сообщением о suspicious content с предложением проверить metadata или обратиться в поддержку. **Marketplace не принял пакет.** Предыдущие local packaging и real editor проверки остаются действительными, но не подтверждают прохождение серверной проверки Microsoft.

## Проверенный artifact и metadata

Повторно проверен предложенный пользователю `artifacts/releases/Agentboard-VSCode-1.4.1-win32-x64.vsix`: **35 895 190 байт**, SHA-256 `45606ffcbd11de215ff09705e0c4fdbd9d57b5c08d5e0ee7647b3d387447fac2`. Байты совпадают с ранее протестированным локальным кандидатом. Пользователь сообщил текст отказа; фактически выбранный в портале файл, upload request/response и внутренний scanner verdict здесь независимо не подтверждены.

JSON и VSIX XML согласованы: name `agentboard`, displayName `DashAI`, publisher `7Askar7`, version `1.4.1`, target `win32-x64`, engine `^1.95.0`. Required fields заполнены, activationEvents содержат `onStartupFinished` и `onView:agentboard.launcher`, main существует, icon — настоящий PNG 128×128. Повторный вызов установленного официального `vsce.validateManifestForPackaging` — PASS. Это локальная валидация manifest, не проверка Marketplace.

Проверены [официальный manifest reference](https://code.visualstudio.com/api/references/extension-manifest) и [publishing guide Microsoft](https://code.visualstudio.com/api/working-with-extensions/publishing-extension). Явного нарушения документированных metadata требований в исследованном пакете не найдено. `contributes`, `scripts` и `devDependencies` — документированные поля; их удаление по стороннему совету не обосновано. License не является обязательным полем manifest; существующее `UNLICENSED` не меняется на другую лицензию ради недоказанного scanner trigger.

README содержит только HTTPS ссылки GitHub/raw GitHub; нет HTML/script/embed, HTTP images или SVG cover. В package/README/extension code отсутствуют неожиданные управляющие символы, bidi controls и U+FFFD. ZIP CRC — PASS; дубликатов путей без учета регистра нет. Все шесть metadata/README URL проверены реальными HTTP HEAD запросами и ответили **200**:

- repository `https://github.com/7Askar7/DashAI`;
- repository `.git` URL, перенаправленный на тот же публичный репозиторий;
- `docs/vscode.md` на main;
- issues;
- releases/latest, разрешившийся в GitHub v1.4.0;
- выбранная PNG cover на raw.githubusercontent.com.

## Содержимое и пределы вывода

В пакете нет project credentials, SQLite store, private keys, `.env`, project MCP configs, QA, tests или node_modules. Закрепленный update public key является публичным и нужен для проверки Ed25519; его удаление ослабило бы защиту. `certifi/cacert.pem` содержит публичные CA certificates, не приватный ключ.

Пакет содержит два frozen EXE, 51 DLL, 28 PYD и штатный desktop update helper PowerShell; это явное содержимое Windows runtime, а не утверждение о триггере отказа. Helper проверяет size/hash и завершение процессов, не является README metadata. [Документация platform-specific extensions](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#platform-specific-extensions) прямо предусматривает platform libraries и binaries; из наличия этих файлов не следует запрет публикации. Backend, native runtime, helper и security checks не удаляются для обхода неизвестного verdict.

[Microsoft описывает](https://code.visualstudio.com/docs/configure/extensions/extension-runtime-security#marketplace-protections) отдельные серверные malware, dynamic detection, secret scanning и name protection. Локальный vsce и успешное выполнение в редакторе не воспроизводят эти проверки. Сообщение не указывает файл, поле, detection name или правило. Поэтому причина отказа **не установлена**, и ложноположительное срабатывание **не доказано**.

В первичном [отчете другого издателя](https://github.com/microsoft/vsmarketplace/issues/1821#issuecomment-4380248604) изменение slug с названием сторонней платформы помогло ему опубликовать расширение. Это наблюдение конкретного автора, не документированное правило и не диагноз DashAI: наш slug `agentboard` такого названия не содержит. Массовое переименование, удаление упоминаний supported agents или перебор версий не предлагаются как подтвержденное исправление.

## Следующий шаг

Подготовить обращение с publisher/extension/version, точным текстом ошибки, SHA-256 и size VSIX, публичным repository, описанием локального runtime и просьбой назвать offending field/file/detection либо провести ручной review. При наличии добавить время попытки и безопасный request/correlation ID; не включать cookies, authorization, токены, локальные credentials или полный HAR.

Официальный publishing guide рекомендует [Manage Publishers & Extensions → Contact Microsoft](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#common-questions). Для той же ошибки [команда Marketplace](https://github.com/microsoft/vsmarketplace/issues/2010#issuecomment-4959860814) направляет на `VSMarketplace@microsoft.com`; такой же ответ дан для [binary-containing package](https://github.com/microsoft/vsmarketplace/issues/1530#issuecomment-3616043200). Обращение готовится как draft; отправка и повторная публикация этим review не выполнялись.

## Отдельный Ponytail-review

Прочитан `.agents/skills/ponytail-review/SKILL.md`. Изменения после отказа ограничены диагностикой и документацией; новых runtime функций, scanner обходов, auth framework или зависимостей не требуется.

Ponytail вывод относится к размеру изменений. Он не означает одобрение пакета Marketplace.

Lean already. Ship.
