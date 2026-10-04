# DashAI: review исследования повторного отказа Marketplace

05.10.2026. Независимый критик `dashai_critic`; Ponytail full. **Normal factual review — PASS.** Проверены дополнения в `docs/research/04-marketplace-packaging.md` и обновленный `docs/marketplace-support.txt`. Пользователь подтвердил ту же точную ошибку после 1.4.2; HTTP response самого портала в этом review не получен. Причина отказа и false positive не установлены.

## Проверка первичных свидетельств

Через официальный GitHub API прочитаны body/comments восьми свежих случаев и исторические ветки; сохранены очищенные от email и notification links source snapshots в `artifacts/qa/marketplace-repeat-research/`. Сверены точные comment links и даты для #2197, #2215, #2019, #1117, #1821 и #352. `Closed` отдельно от результата: #2197 содержит направление в support, не подтвержденное исправление account flag; #1117 содержит и ответ команды, и explicit подтверждение публикации автором. Одновременная замена name/publisher/Git URL у другого автора не выделяет одно ответственное поле.

Независимо прочитаны [Vera #1106](https://github.com/aallan/vera/issues/1106#issuecomment-5046899010) и [PR1165](https://github.com/aallan/vera/pull/1165), включая API snapshots `vera-1106-comments.json` и `vera-pr1165.json`. Автор привел письмо Microsoft от 20.07 о blocked keywords; отвергнутый 22.07 пакет и впоследствии скачанный автором Marketplace пакет имеют один заявленный SHA-256 `b04afb6a1c0a397697346553bd743dd26cd13b119edb967f8b9b29ff12612242`. Это документированный исход в первичных записях автора; наш review не скачивал Vera VSIX, не подтверждает неизвестное server action и не объявляет `llm/contracts` запрещенными словами.

Прочитан [Sextant PR15](https://github.com/KyleBastien/sextant-mcp/pull/15): автор прямо указывает сохранение отказа после LICENSE fix. Название предыдущего PR с `fix` не доказывает успешный upload. Общие советы Q&A отделены от последующего сообщения автора об их неэффективности; необоснованный запрет `scripts/devDependencies` не перенесен в продукт.

## Проверка наших metadata и draft

Повторная реальная Gallery проверка с positive controls сохранена в `gallery-*.json`: slug `agentboard` — ноль, `ruff` — существующий Ruff; `DashAI` — ноль, `Ruff` — существующие результаты. Text search обнаруживает чужой displayName Agentboard с другим slug. В документах правильно ограничен вывод публичным каталогом: reserved/unpublished namespaces, similarity rules и account flags не видны.

Заново прочитан сам VSIX 1.4.2: **35 881 575 байт**, SHA-256 `7cf58fef889944f794eef99bca921288b6556ea86f20d95080e4d08078fa982e`; полный CRC — PASS. JSON/XML согласованы: `7Askar7.agentboard`, 1.4.2, `win32-x64`; реальные generated Tags — `kanban,codex,claude,agents,local`. Description и keywords в support draft совпадают с artifact. Указанный source commit соответствует HEAD `4b07d5032085bc00472b351a5895488ab67fb08a` до этих doc-only изменений. Старый support draft 1.4.1 в `support-original-1.4.1.txt` побайтно совпал с прежним tracked файлом.

Draft запрашивает конкретное поле/файл/detection и account finding; не утверждает причину DashAI по примеру Vera. Сообщение о том, что cleanup не устранил повторный отказ, опирается на подтверждение пользователя. Публикация в Marketplace или отдельный GitHub Release 1.4.2 не заявляются. Письмо не отправлено. Диагностические инструкции про message/typeKey/correlation ID исключают полный HAR, cookies и Authorization. Фактических ошибок, требующих исправления этих двух файлов, не найдено; они критиком не изменены.

## Отдельный Ponytail-review

Прочитан `.agents/skills/ponytail-review/SKILL.md`. Текущий diff документирует запрошенное исследование и конкретное обращение; runtime, dependencies, version и binaries не меняются. Новые speculative fixes и scanner обходы не добавлены. Дополнительных обоснованных сокращений нет; этот вывод не означает одобрение Marketplace.

Lean already. Ship.
