# Исследование: личная синхронизация Confluence и Jira

Дата проверки: 17 октября 2026. Источники — официальные REST-документы Atlassian; сетевые тесты реализации используют подменённый транспорт, а не аккаунт пользователя.

## Потребность и выбранная граница

Пользователь ведёт архитектуру и описания проекта в DashAI, но часть команды читает знания в Confluence/Jira. Он выбирает личный проект назначения по ссылке. Система должна переносить эти знания автоматически и не получать возможность создавать чужие проекты или выходить выше выбранного корня. Подключение необязательно, отдельно для каждого локального проекта. Пользователь уточнил необходимость Cloud и собственного сервера, а затем личный характер каждого подключения.

Решение: один локальный односторонний REST-коннектор на service/project, проверенный numeric remote root, стабильные local→remote mappings и транзакционная outbox. Повторное использование общего `httpx` и SQLite покрывает задачу без нового runtime моделей, SDK-пакета или универсального plugin framework. Запуск агентов и двусторонняя синхронизация задач не входят в этот запрос.

## Что проверено по первичным источникам

| Источник | Подтверждённый механизм | Следствие для реализации |
|---|---|---|
| [Confluence Cloud — Page REST v2](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/) | GET page возвращает `spaceId`, `parentId`, version; создание принимает `spaceId`, `parentId`, storage/ADF body; update требует version | Создание всегда с pinned parent; обновление только после scope GET, version+1; никакого root-level create |
| [Confluence Data Center — REST examples](https://developer.atlassian.com/server/confluence/confluence-rest-api-examples/) | `rest/api/content`, `space`, `ancestors`, storage body и optimistic version; PAT доступен с 7.9 | Отдельный concrete wire format для DC, тот же domain intent; собственный context path сохраняется |
| [Jira Cloud — Issues](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/) | Issue create задаёт `fields.project`, `issuetype`, summary/description; API v3 использует ADF для description | Запись только numeric pinned project, без project-create API; обычный issue type из GET project |
| [Jira Data Center — Issue REST](https://developer.atlassian.com/server/jira/platform/rest/v11001/api-group-issue/) | API v2 issue create/edit с project/type и текстовыми полями | DC adapter не посылает Cloud ADF; permission/custom-field ошибки не маскируются успешным состоянием |
| [Jira Cloud — Issue search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/) | Enhanced search `/search/jql` с JQL и ограниченным результатом | Восстановление mapping после неизвестного create ищет только numeric project и уникальный DashAI label |
| [Cloud basic authentication](https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/), [Confluence basic auth](https://developer.atlassian.com/cloud/confluence/basic-auth-for-rest-apis/) | Email + API token для личных REST calls; для распространяемых apps рекомендуются единый 3LO app и ограничения сбора токенов | Личный token-режим обозначен явно; зарегистрированный публичный OAuth нельзя обещать без регистрации/broker |
| [Data Center — Personal Access Tokens](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html) | PAT передаётся Bearer, Confluence 7.9+ / Jira 8.14+ | Bearer credential хранится локально, HTTPS/TLS обязательны; отсутствуют SSO/password scraping |

Примеры в источниках местами используют localhost/HTTP для developer server. Это не рекомендация перенести такую схему в личный коннектор: реализация принимает HTTPS и отсекает loopback/link-local, сохраняя доступ к private LAN для Data Center. Подключение к собственному серверу не означает разрешения отключить TLS-проверку.

## Сравнение подходов и решение

| Подход | Польза | Цена/ограничение | Решение |
|---|---|---|---|
| Только экспорт Markdown | Нет хранения credentials, человек проверяет назначения | Нет запрошенной автоматической передачи | Существующий экспорт сохраняется как дополнение |
| Полноценное Atlassian Connect/Forge приложение | Публичный lifecycle, permissions и UI Atlassian | Отдельный hosted продукт/регистрация, не просто desktop feature | Не создавать без отдельного publisher-проекта |
| Единый OAuth 3LO broker | Более подходящий путь для распространяемой Cloud-интеграции | Нужны регистрация, redirect URL, доступный доверенный broker; desktop не может безопасно содержать client secret | Документировать будущий concrete contract, не выдавать личный token за OAuth |
| Конкретные REST Cloud/DC адаптеры в локальном приложении | Выполняют личный per-project сценарий, работают без общего облачного store | Нужно честно показать личный режим, limits, pending/error и live verification | Реализовано с явным согласием на отправку |
| Универсальный integration framework с очередью-брокером | Разные поставщики и исполнение plugins | Ненужные зависимости, отдельное хранение/развёртывание | Не добавлять: одна SQLite outbox и конкретные 2 сервиса достаточны |

Выводы о подходящем UX являются проектными решениями по запросу, не результатом пользовательских интервью. Исследование не сравнивало производительность установленных Confluence/Jira и не подтверждает работу с любым custom workflow.

## Критичные свойства корректности

1. Корень подтверждается реальным чтением при connect и перед отправкой, а не наличием конфигурации. Confluence — строго непосредственные дети страницы; Jira — задачи одного numeric project. API создания spaces/projects и произвольного URL отсутствуют.
2. Локальное сохранение и enqueue атомарны вместе с audit. Remote mutation не может быть частью той же SQLite transaction; она получает собственный подтверждённый статус и mapping.
3. Пустой search после timeout не доказывает отсутствие созданной записи. Поэтому результат POST остаётся uncertain и создание не повторяется автоматически.
4. Unknown creation сохраняет исходный attempted payload. Найденный remote content сравнивается с ним до adoption: ручная правка не должна молча стать новым baseline. Удаление/выключение локального модуля не стирает этот факт.
5. Исчезновение локального материала останавливает будущую отправку, но не удаляет remote записи. Повторное включение возобновляет ту же идентичность, а не создаёт дубликат.
6. Confluence version исключает stale PUT. Jira не гарантирует общей CAS атомарности read/PUT; существующее внешнее изменение managed description блокируется, но узкая гонка после GET остаётся документированным пределом API.
7. Неактивные очереди фильтруются до LIMIT, чтобы 10 выключенных элементов не остановили другой активный проект. Сетевые ожидания не держат SQLite writer и не блокируют все подключения глобальным mutex.
8. Credentials не попадают в SQLite/audit/export/read API; удалённый текст ошибки не выводится. Redirects и env proxies выключены. Подключения на известные loopback/link-local адреса блокируются до отправки Authorization.

## Если понадобится публичный Cloud OAuth

Владелец продукта регистрирует одно OAuth 3LO-приложение, определяет его scopes и callback на своём HTTPS broker. Desktop открывает authorization URL с одноразовым state и PKCE/проверкой возврата, если это поддерживает зарегистрированная схема; broker выполняет разрешённый обмен без client secret в VSIX. После разрешения выбирается accessible resource, сохраняется cloudId и pinned remote root. Broker выдаёт ограниченный короткоживущий credential или выполняет строго привязанный REST proxy, сохраняет refresh token у себя и поддерживает revocation. Такой сервис не реализован и не требуется личному локальному режиму; наличие раздела в документации не означает подключённый OAuth.

## Проверка

Независимый review воспроизвёл и помог устранить три ошибки раннего варианта: starvation за выключенными очередями, потерю uncertain после выключения модуля и overwrite ручной правки при recovery POST. Все сценарии закреплены в `tests/test_integrations.py` вместе с Cloud/DC wire formats, неизменяемым scope, version conflicts, concurrent local edit, credential isolation и HTTPS boundary. Тесты проверяют реальные HTTP paths/payload через MockTransport. Live учётная запись, пользовательские URL, права и custom fields проверяются человеком при настройке; до этого UI не должен показывать реальное подключение.
