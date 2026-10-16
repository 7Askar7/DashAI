// Prepared examples for the design prototype; no model calls or project-store writes.
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const svgText = (x,y,text,size=18,anchor='middle') => `<text x="${x}" y="${y}" text-anchor="${anchor}" fill="#c7d5e3" font-size="${size}" font-family="Segoe UI,Arial,sans-serif">${escapeHtml(text)}</text>`;
function svgBox(x,y,width,height,title,lines,type='') {
  return `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="9" fill="#192632" stroke="#748a9f"/>${type?svgText(x+16,y+27,type,16,'start'):''}${svgText(x+16,y+(type?57:34),title,20,'start')}${lines.map((line,i)=>svgText(x+16,y+(type?84:62)+i*25,line,18,'start')).join('')}`;
}
const svgTerminator = (x,y,width,height,title,lines) => svgBox(x,y,width,height,title,lines).replace('rx="9"','rx="48"');
function svgEdge(path,label,x,y,dashed=false) {
  return `<path d="${path}" fill="none" stroke="#a2b9ce" stroke-width="1.7" ${dashed?'stroke-dasharray="6 5"':''} marker-end="url(#n-arrow)"/>${label?`<g stroke="#0f161e" stroke-width="6" paint-order="stroke">${svgText(x,y,label)}</g>`:''}`;
}
function boundary(x,y,width,height,title) {
  return `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="8" fill="none" stroke="#8ebf88" stroke-dasharray="7 5"/>${svgText(x+18,y+29,title,18,'start')}`;
}

const notations = {
  overview:{title:'Свободный обзор',family:'Обзор',scope:'Основной путь данных в DashAI',purpose:'Быстро объяснить, как интерфейс и внешние агенты используют общий сервер.',legend:'Прямоугольник — часть системы; стрелка — обращение. Это свободная схема, без формальной нотации.',files:['src/App.tsx','server/app.py','connectors/mcp_server.py'],explanation:['Интерфейс обращается к HTTP API.','Внешний агент вызывает MCP-коннектор, который обращается к тому же API.','Только сервер открывает SQLite; изменение данных и событие сохраняются вместе.'],source:`flowchart LR
  UI["Веб-интерфейс"] -->|HTTP| API["Сервер и правила"]
  API -->|SQL| DB[("SQLite: данные и история")]
  Agent["Codex / Claude Code"] -->|MCP| MCP["MCP-коннектор"]
  MCP -->|HTTP API| API`,draw:()=>svgBox(30,100,250,135,'Веб-интерфейс',['Проекты и задачи','React / TypeScript'])+svgBox(375,100,250,135,'HTTP API',['Общие правила','Python / FastAPI'])+svgBox(720,100,250,135,'SQLite',['Данные + история','Одна транзакция'])+svgBox(30,360,250,135,'Внешний агент',['Codex / Claude Code'])+svgBox(375,360,250,135,'MCP-коннектор',['Python / stdio'])+svgEdge('M280 168H375','HTTP',327,151)+svgEdge('M625 168H720','SQL',672,151)+svgEdge('M280 428H375','MCP',327,411)+svgEdge('M500 360V235','HTTP API',563,305)},
  context:{title:'Контекст системы DashAI',family:'C4 · L1',scope:'DashAI как единая программная система',purpose:'Для владельца проекта: кто пользуется системой и с каким результатом.',legend:'Person — человек; Software system — программная система. Внешний клиент находится за пределами DashAI. Стрелка показывает направление использования.',files:['README.md','docs/architecture.md'],explanation:['Человек использует DashAI для управления проектами и чтения истории.','Codex и Claude Code — внешние программные клиенты, которые читают и изменяют задачи через MCP.','На уровне контекста внутренние приложения и база данных не раскрываются.'],source:`flowchart LR
  Person["Человек · Person<br/>Управляет проектами"]
  DashAI["DashAI · Software system<br/>Общая память проектов и задач"]
  Agent["Codex / Claude Code · External system<br/>Выполняет работу в своей среде"]
  Person -->|Управляет проектами| DashAI
  Agent -->|Читает и изменяет задачи через MCP| DashAI`,draw:()=>svgBox(30,135,250,150,'Человек',['Управляет проектами'],'Person')+svgBox(375,135,250,150,'DashAI',['Проекты, задачи','и история действий'],'Software system')+svgBox(720,135,250,150,'Внешний агент',['Codex / Claude Code','Работает в своей среде'],'External system')+svgEdge('M280 210H375','Управляет проектами',324,104)+svgEdge('M720 210H625','Работает с задачами / MCP',690,104),height:340},
  containers:{title:'Контейнеры системы DashAI',family:'C4 · L2',scope:'Приложения и хранилище внутри DashAI',purpose:'Для разработчика: какие части исполняются отдельно, за что отвечают и по каким протоколам связаны.',legend:'Пунктир — граница системы DashAI; Container — приложение или хранилище, а не обязательно Docker. Person и External system находятся снаружи. Подписи стрелок указывают способ обращения.',files:['src/App.tsx','server/app.py','connectors/mcp_server.py'],explanation:['Человек открывает веб-интерфейс React. Интерфейс отправляет HTTP/JSON-запросы серверу FastAPI.','Внешний клиент вызывает Python-коннектор по MCP/stdio. Коннектор отправляет HTTP/JSON-запросы серверу.','Сервер обращается к SQLite через sqlite3. Ни веб-интерфейс, ни коннектор не открывают базу напрямую.','Это граница программной системы; desktop-упаковка и процесс обновлений здесь опущены.'],source:`flowchart LR
  Human["Человек · Person"]
  Agent["Codex / Claude Code · External system"]
  subgraph DashAI["DashAI · Software system"]
    UI["Веб-интерфейс · Container<br/>React / TypeScript · управление проектами"]
    API["HTTP API · Container<br/>Python / FastAPI · общие правила"]
    MCP["MCP-коннектор · Container<br/>Python · передаёт действия в API"]
    DB[("SQLite · Data store<br/>Данные и история")]
    UI -->|HTTP / JSON| API
    MCP -->|HTTP / JSON| API
    API -->|SQL / sqlite3| DB
  end
  Human -->|Открывает в браузере| UI
  Agent -->|MCP / stdio| MCP`,draw:()=>boundary(320,55,660,530,'DashAI [Software system]')+svgBox(20,145,200,145,'Человек',['Управляет','проектами'],'Person')+svgBox(20,385,200,145,'Внешний агент',['Codex / Claude','Code'],'External system')+svgBox(350,145,260,145,'Веб-интерфейс',['Проекты и задачи','React / TypeScript'],'Container')+svgBox(730,145,230,145,'HTTP API',['Общие правила','Python / FastAPI'],'Container')+svgBox(350,385,260,145,'MCP-коннектор',['Действия в API','Python / stdio'],'Container')+svgBox(730,385,230,145,'SQLite',['Данные и история','SQLite / sqlite3'],'Data store')+svgEdge('M220 218H350','Браузер',285,200)+svgEdge('M610 218H730','HTTP / JSON',670,200)+svgEdge('M220 458H350','MCP / stdio',285,440)+svgEdge('M610 458H675V258H730','HTTP / JSON',674,348)+svgEdge('M845 290V385','SQL',879,344)},
  components:{title:'Компоненты HTTP API',family:'C4 · L3',scope:'Логические части server/app.py внутри контейнера API',purpose:'Для изменения сервера: где принимается действие, где проверяется и где сохраняется.',legend:'Пунктир — граница контейнера API. Component — логическая ответственность, а не отдельный файл или процесс. Стрелки показывают обращения между частями.',files:['server/app.py','tests/test_api.py'],explanation:['HTTP-обработчики FastAPI получают автора через зависимость actor.','Для изменения вызываются check_version, check_claim и validate_task.','Store.transaction обеспечивает SQLite-транзакцию; изменение и событие проходят в ней вместе.','Все показанные части сейчас находятся в server/app.py. Диаграмма не предлагает разделять их на микросервисы.'],source:`flowchart TB
  subgraph API["HTTP API · Container: Python / FastAPI"]
    Routes["HTTP-обработчики · Component<br/>FastAPI · действия с проектами и задачами"]
    Actor["actor · Component<br/>Python / FastAPI · определение автора"]
    Rules["Правила изменений · Component<br/>Python · версии, владение и зависимости"]
    Store["Store · Component<br/>Python / sqlite3 · транзакции и audit"]
    Routes -->|Определяет автора| Actor
    Routes -->|Проверяет действие| Rules
    Routes -->|Сохраняет в транзакции| Store
  end`,draw:()=>boundary(30,55,940,520,'HTTP API [Container: Python / FastAPI]')+svgBox(65,130,335,150,'HTTP-обработчики',['Действия с проектами','FastAPI / Python'],'Component')+svgBox(600,130,335,150,'actor',['Определяет автора','FastAPI / Python'],'Component')+svgBox(65,390,335,150,'Правила изменений',['Версии и зависимости','Python'],'Component')+svgBox(600,390,335,150,'Store',['Транзакции и audit','Python / sqlite3'],'Component')+svgEdge('M400 205H600','Определяет автора',500,183)+svgEdge('M232 280V390','Проверяет действие',340,340)+svgEdge('M400 250H500V465H600','Сохраняет',556,448)},
  sequence:{title:'Агент берёт задачу в работу',family:'UML · Sequence',scope:'Успешный вызов claim_task; ошибки показаны в Flowchart',purpose:'Для разбора сценария: кто, кому и в каком порядке передаёт сообщения.',legend:'Вертикальный пунктир — линия жизни участника; сплошная стрелка — запрос; пунктирная стрелка — ответ. Время идёт сверху вниз. Показан только успешный сценарий.',files:['connectors/mcp_server.py','server/app.py','tests/test_mcp.py'],explanation:['Агент вызывает claim_task с идентификатором задачи и expected_version.','Коннектор отправляет авторизованный HTTP-запрос POST /api/tasks/{id}/claim.','API открывает BEGIN IMMEDIATE, проверяет версию и владение, изменяет задачу и добавляет audit event.','SQLite фиксирует транзакцию; обновлённая задача возвращается агенту через API и MCP.'],source:`sequenceDiagram
  participant Agent as Агент
  participant MCP as MCP-коннектор
  participant API as HTTP API
  participant DB as SQLite
  Agent->>MCP: claim_task(id, expected_version)
  MCP->>API: POST /api/tasks/{id}/claim
  API->>DB: BEGIN IMMEDIATE
  Note over API,DB: Проверка версии и владения
  API->>DB: UPDATE task + INSERT event
  API->>DB: COMMIT
  DB-->>API: Транзакция зафиксирована
  API-->>MCP: Задача с новой версией
  MCP-->>Agent: Результат claim`,draw:()=>{
    const participants=[['Агент',110],['MCP',370],['HTTP API',630],['SQLite',890]];
    return participants.map(([name,x])=>svgBox(x-90,35,180,66,name,[])+`<path d="M${x} 101V555" stroke="#7f96aa" stroke-dasharray="6 6"/>`).join('')+
      svgEdge('M110 145H370','claim_task(id, version)',240,133)+svgEdge('M370 205H630','POST /claim',500,193)+svgEdge('M630 265H890','BEGIN IMMEDIATE',760,253)+svgText(760,309,'Проверка версии и владения',17)+svgEdge('M630 355H890','UPDATE + audit; COMMIT',760,343)+svgEdge('M890 415H630','Зафиксировано',760,403,true)+svgEdge('M630 475H370','Задача / новая версия',500,463,true)+svgEdge('M370 535H110','Результат claim',240,523,true);
  }},
  states:{title:'Состояния задачи',family:'UML · State',scope:'Типичный маршрут одной задачи, не полный автомат API',purpose:'Для понимания работы: как задача движется от планирования к проверенному результату.',legend:'Скруглённый блок — состояние; стрелка — переход; текст в квадратных скобках — условие. Чёрная точка — начало. Готово не обозначено конечным состоянием: задачу можно вернуть в работу по правилам API.',files:['server/app.py','src/KanbanBoard.tsx','tests/test_api.py'],explanation:['Задача создаётся в backlog, затем берётся в in_progress.','Из in_progress результат отправляется в review; замечания возвращают его в работу.','review → done требует критерии приёмки и хотя бы одну evidence note; это не независимая сертификация качества.','Блокировка отмечается blocked; после устранения причины задача возвращается в работу. Показаны типичные, а не все допустимые переходы.'],source:`stateDiagram-v2
  state "Запланировано" as backlog
  state "В работе" as active
  state "Проверка" as review
  state "Готово" as done
  state "Блокировка" as blocked
  [*] --> backlog
  backlog --> active: claim
  active --> review: результат готов
  review --> active: замечания
  review --> done: [критерии и evidence]
  active --> blocked: указана причина
  blocked --> active: причина устранена
  note right of done: Типичный маршрут, не полный автомат API`,draw:()=>`<circle cx="30" cy="180" r="8" fill="#b4f4a5"/>`+svgBox(65,130,195,105,'Запланировано',['backlog'])+svgBox(350,130,255,105,'В работе',['in_progress'])+svgBox(735,130,225,105,'Проверка',['review'])+svgBox(350,390,255,105,'Блокировка',['blocked'])+svgBox(735,390,225,105,'Готово',['done'])+svgEdge('M38 180H65','',0,0)+svgEdge('M260 180H350','claim',305,163)+svgEdge('M605 180H735','Результат',670,163)+svgEdge('M848 130V85H478V130','Замечания',662,68)+svgEdge('M478 235V390','Есть блокер',405,320)+svgEdge('M605 442H662V265H557V235','Причина устранена',685,359)+svgEdge('M848 235V390','[критерии и evidence]',838,320)},
  data:{title:'Модель данных проекта',family:'ERD',scope:'Упрощённая логическая модель, не физическая схема SQLite',purpose:'Для чтения данных: какие сущности связаны и сколько записей участвует в связи.',legend:'Блок — сущность и часть её полей; PK — идентификатор, FK — ссылка. 1 означает ровно одну запись, 0..1 — необязательную, 0..* — любое количество. Связи не обозначают HTTP-вызовы. Подпроекты, зависимости и часть полей опущены.',files:['server/app.py','docs/architecture.md'],explanation:['Один Project имеет любое количество Task; каждая Task относится к одному Project.','У Task может быть несколько Note; каждая Note принадлежит одной Task.','Event может относиться к одной Task или не иметь task_id, например событие изменения проекта.','Каждый Event имеет автора Agent; у одного Agent может быть много событий. Это логическая модель: часть полей хранится в JSON payload.'],source:`erDiagram
  PROJECT ||--o{ TASK : contains
  TASK ||--o{ NOTE : has
  TASK |o--o{ EVENT : references
  AGENT ||--o{ EVENT : authors
  PROJECT {
    string id PK
    string name
  }
  TASK {
    string id PK
    string project_id FK
    string status
    int version
  }
  NOTE {
    string id PK
    string task_id FK
    string kind
  }
  EVENT {
    int id PK
    string task_id FK "nullable"
    string actor_id FK
  }
  AGENT {
    string id PK
    string name
    string kind
  }`,draw:()=>svgBox(25,85,255,145,'Project',['id · PK','name'])+svgBox(375,85,255,170,'Task',['id · PK / project_id · FK','status / version'])+svgBox(725,85,250,145,'Note',['id · PK / task_id · FK','kind'])+svgBox(375,375,255,160,'Event',['task_id · FK / nullable','actor_id · FK'])+svgBox(725,375,250,160,'Agent',['id · PK','name / kind'])+`<path d="M280 157H375 M630 157H725 M502 255V375 M725 455H630" fill="none" stroke="#a2b9ce" stroke-width="1.7"/>`+svgText(295,143,'1')+svgText(345,143,'0..*')+svgText(647,143,'1')+svgText(695,143,'0..*')+svgText(537,283,'0..1')+svgText(537,358,'0..*')+svgText(701,439,'1')+svgText(658,439,'0..*')},
  flow:{title:'Изменение задачи без потери чужой правки',family:'Flowchart',scope:'Проверка версии при PATCH; остальные проверки сгруппированы',purpose:'Для объяснения алгоритма: где появляется развилка и что делать при конфликте.',legend:'Скруглённая капсула — начало или результат; прямоугольник — действие; ромб — вопрос; Да/Нет — условие ветви. Это блок-схема, не BPMN.',files:['server/app.py','tests/test_api.py'],explanation:['Клиент передаёт expected_version. После определения автора сервер начинает транзакцию и читает актуальную запись.','Если версия не совпала, сервер возвращает 409; клиент перечитывает данные и снова подтверждает намерение.','Если версия совпала, сервер проверяет владение, зависимости и условия статуса. Ошибка любой проверки откатывает транзакцию.','При успехе изменение и audit event записываются атомарно, после чего клиент получает новую версию.'],source:`flowchart TD
  A(["PATCH с expected_version"]) --> B["Определить автора; BEGIN; прочитать запись"]
  B --> C{"Версия совпала?"}
  C -->|Нет| D(["409; перечитать и подтвердить заново"])
  C -->|Да| E["Проверить владение, зависимости и статус"]
  E --> F["UPDATE + audit event; COMMIT"]
  F --> G(["Успех; новая версия"])
  E -.->|Ошибка проверки| H(["Откат; ответ с ошибкой"])`,draw:()=>svgTerminator(30,70,440,100,'PATCH + expected_version',[])+svgBox(30,215,440,110,'Автор; BEGIN; чтение',[])+`<path d="M250 365 410 430 250 495 90 430Z" fill="#263426" stroke="#9abf8e"/>`+svgText(250,437,'Версия совпала?')+svgTerminator(585,385,375,105,'409 · конфликт',['Перечитать и подтвердить'])+svgBox(30,570,440,105,'Проверить действие',['Владение, зависимости, статус'])+svgTerminator(585,570,375,105,'Изменение + audit',['COMMIT; новая версия'])+svgTerminator(30,765,440,100,'Откат транзакции',['Вернуть ошибку проверки'])+svgEdge('M250 170V215','',0,0)+svgEdge('M250 325V365','',0,0)+svgEdge('M410 430H585','Нет',493,411)+svgEdge('M250 495V570','Да',273,540)+svgEdge('M470 622H585','Успех',527,604)+svgEdge('M250 675V765','Ошибка проверки',351,727,true),height:910}
};

function diagramSvg(id,prefix='notation') {
  const n=notations[id], marker=`${prefix}-${id}-arrow`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 ${n.height||620}" role="img" aria-label="${escapeHtml(n.title)}" data-notation="${id}"><rect width="100%" height="100%" fill="#0f161e"/><defs><marker id="${marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="m1 1 8 4-8 4" fill="none" stroke="#a2b9ce" stroke-width="1.3"/></marker></defs>${n.draw().replaceAll('#n-arrow','#'+marker)}</svg>`;
}

const documentSections = {intro:'Цель и границы',diagrams:'Архитектура и сценарии',files:'Описания файлов',decisions:'Принятые решения',verification:'Проверки и ограничения'};
const includedDiagrams = new Set(['context','containers','sequence','data']);
const includedSections = new Set(Object.keys(documentSections));
function renderNotation() {
  const id=$('notation-select').value,n=notations[id];
  $('architecture-overview').hidden=id!=='overview';$('overview-legend').hidden=id!=='overview';$('notation-view').hidden=id==='overview';
  if(id!=='overview')$('notation-view').innerHTML=`<div class="notation-title"><div class="notation-meta"><span class="label">${n.family}</span><span class="label amber">Подготовленный пример</span></div><h2>${n.title}</h2><p>${n.purpose}</p><small class="muted">Область: ${n.scope}</small><p class="mobile-diagram-hint">Схема прокручивается по горизонтали. Текстовое объяснение доступно ниже.</p></div><div class="notation-viewport" tabindex="0" aria-label="Схема ${n.family}; доступна горизонтальная прокрутка">${diagramSvg(id)}</div><p class="notation-legend"><strong>Легенда.</strong> ${n.legend}</p><details class="diagram-accessible" open><summary>Текстовое объяснение</summary><ol>${n.explanation.map(text=>`<li>${text}</li>`).join('')}</ol></details><div class="notation-related">${n.files.map(fileButton).join('')}</div>`;
  $('mermaid-source').textContent=n.source;
  $('include-diagram').disabled=includedDiagrams.has(id)&&includedSections.has('diagrams');
  $('include-diagram').textContent=$('include-diagram').disabled?'Уже в документе':'Включить в документ';
}

function renderDocumentSettings() {
  $('document-sections').innerHTML=Object.entries(documentSections).map(([id,title])=>`<label class="check-row"><input type="checkbox" data-section="${id}" ${includedSections.has(id)?'checked':''}>${title}</label>`).join('');
  $('document-diagrams').innerHTML=Object.entries(notations).map(([id,n])=>`<label class="check-row"><input type="checkbox" data-diagram="${id}" ${includedDiagrams.has(id)?'checked':''}>${n.family==='Обзор'?n.title:n.family+' · '+n.title}</label>`).join('');
}

function buildDocumentation() {
  const title=$('document-name').value.trim()||'Документация проекта', context=$('document-context').value.trim();
  let html=`<h1>${escapeHtml(title)}</h1><p class="doc-state">Подготовленный пример · 16.10.2026 · ревизия исходников не сверена</p>${context?`<p>${escapeHtml(context)}</p>`:''}`;
  let markdown=`# ${escapeHtml(title.replace(/[\r\n]/g,' '))}\n\n> Подготовленный пример · 16.10.2026 · ревизия исходников не сверена.\n\n${context?escapeHtml(context)+'\n\n':''}`;
  html+=`<nav class="doc-toc" aria-label="Содержание документа">${Object.entries(documentSections).filter(([id])=>includedSections.has(id)).map(([id,label])=>`<a href="#doc-${id}">${label}</a>`).join('')}</nav>`;
  const section=(id,body,text)=>{if(includedSections.has(id)){html+=`<section id="doc-${id}"><h2>${documentSections[id]}</h2>${body}</section>`;markdown+=`## ${documentSections[id]}\n\n${text}\n\n`;}};
  const intro='DashAI — локальное пространство общей работы человека, Codex и Claude Code. Проекты и задачи доступны через интерфейс и единый HTTP API; MCP-коннектор передаёт действия внешних агентов в тот же API. Приложение не запускает модели. Этот документ охватывает основную работу с задачами; desktop-упаковка и обновления не раскрыты.';
  section('intro',`<p>${intro}</p>`,intro);
  let diagramHtml='',diagramMarkdown='';
  for(const id of includedDiagrams){
    const n=notations[id];
    diagramHtml+=`<figure><figcaption><h3>${n.family} · ${n.title}</h3><p>${n.purpose}</p><p><strong>Область:</strong> ${n.scope}</p></figcaption><div class="notation-viewport" tabindex="0" aria-label="Схема ${n.family}">${diagramSvg(id,'document')}</div><p><strong>Легенда:</strong> ${n.legend}</p><ol>${n.explanation.map(text=>`<li>${text}</li>`).join('')}</ol><p><strong>Исходные файлы:</strong> ${n.files.map(path=>`<code>${path}</code>`).join(', ')}</p></figure>`;
    diagramMarkdown+=`### ${n.family} · ${n.title}\n\n${n.purpose}\n\nОбласть: ${n.scope}.\n\n\`\`\`mermaid\n${n.source}\n\`\`\`\n\nЛегенда: ${n.legend}\n\n${n.explanation.map(text=>'- '+text).join('\n')}\n\nИсходные файлы: ${n.files.map(path=>'\`'+path+'\`').join(', ')}.\n\n`;
  }
  section('diagrams',diagramHtml||'<p>Схемы не выбраны. Отметьте нужные слева.</p>',diagramMarkdown||'Схемы не выбраны.');
  section('files',files.map(f=>`<details><summary><code>${f.path}</code> · ${f.title}</summary><div><p>${f.summary}</p><h4>Зачем нужен</h4><p>${f.why}</p><h4>Как работает</h4><ol>${f.steps.map(([heading,text])=>`<li><strong>${heading}.</strong> ${text}</li>`).join('')}</ol></div></details>`).join(''),files.map(f=>`### ${f.path}\n\n${f.summary}\n\n**Зачем нужен.** ${f.why}\n\n${f.steps.map(([heading,text],i)=>`${i+1}. **${heading}.** ${text}`).join('\n')}`).join('\n\n'));
  const decisions=[['Один сервер и одна база','Человек и внешние агенты используют общий HTTP API; MCP не создаёт собственный project store.'],['Атомарная история','Изменение данных и audit event проходят в одной SQLite-транзакции.'],['Конфликт сохраняет чужую правку','expected_version предотвращает stale overwrite; после 409 клиент перечитывает данные.']];
  section('decisions',`<p>Краткие решения из архитектурного контракта. Это не полный журнал ADR.</p>${decisions.map(([heading,text])=>`<h3>${heading}</h3><p>${text}</p>`).join('')}`,'Краткие решения из архитектурного контракта; не полный журнал ADR.\n\n'+decisions.map(([heading,text])=>`- **${heading}.** ${text}`).join('\n'));
  const verification='Описание кода, схемы и связи подготовлены для обсуждения, не сгенерированы подключённым анализатором и не сверены с текущей ревизией. Схемы упрощены; State показывает типичный маршрут, ERD — часть логической модели. Наличие evidence в задаче само по себе не доказывает независимую проверку. Перед использованием документа для реализации необходимо сверить исходники, версии и фактические результаты проверок.';
  section('verification',`<p>${verification}</p><p>Основание: <code>docs/architecture.md</code>, <code>server/app.py</code>, <code>connectors/mcp_server.py</code>. Нотации: C4, UML Sequence / State, ERD и Flowchart. Ссылки на первичные руководства перечислены в спецификации прототипа.</p>`,verification+'\n\nОснование: docs/architecture.md, server/app.py, connectors/mcp_server.py.');
  if(!includedSections.size)html+='<p class="document-empty">Выберите хотя бы один раздел документа.</p>';
  return {title,html,markdown};
}
function renderDocumentation(){ $('document-preview').innerHTML=`<article class="assembled-document">${buildDocumentation().html}</article>`; }
function downloadDocument(name,type,content) {
  const url=URL.createObjectURL(new Blob([content],{type})),link=document.createElement('a');
  link.href=url;link.download=name;document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);announce(`Подготовлен файл ${name}. Проверьте загрузки браузера.`);
}

$('notation-select').addEventListener('change',()=>{renderNotation();announce(`Выбрано представление: ${notations[$('notation-select').value].title}`);});
$('diagram-source-toggle').addEventListener('click',()=>{const open=$('diagram-source').hidden;$('diagram-source').hidden=!open;$('diagram-source-toggle').setAttribute('aria-expanded',String(open));});
$('download-source').addEventListener('click',()=>downloadDocument(`dashai-${$('notation-select').value}.mmd`,'text/plain;charset=utf-8',notations[$('notation-select').value].source));
$('include-diagram').addEventListener('click',()=>{includedDiagrams.add($('notation-select').value);includedSections.add('diagrams');renderNotation();renderDocumentSettings();renderDocumentation();announce('Схема включена. Откройте вкладку «Документация» для просмотра.');});
document.querySelectorAll('#document-sections,#document-diagrams').forEach(container=>container.addEventListener('change',event=>{
  const input=event.target,set=input.dataset.section?includedSections:includedDiagrams,key=input.dataset.section||input.dataset.diagram;
  if(input.checked)set.add(key);else set.delete(key);renderDocumentation();renderNotation();announce('Состав документа обновлён.');
}));
for(const id of ['document-name','document-context'])$(id).addEventListener('input',renderDocumentation);
$('export-markdown').addEventListener('click',()=>downloadDocument('dashai-documentation.md','text/markdown;charset=utf-8',buildDocumentation().markdown));
$('export-html').addEventListener('click',()=>{
  const doc=buildDocumentation();
  const css='body{font:16px/1.65 Segoe UI,Arial,sans-serif;color:#17202a;margin:40px auto;padding:0 24px;max-width:1040px}h1,h2,h3{line-height:1.3}h2{margin-top:40px}p,li,summary{overflow-wrap:anywhere}code{font-size:14px}svg{display:block;width:100%;height:auto}figure{margin:30px 0}details{padding:12px 0;border-top:1px solid #c5ced7}summary{cursor:pointer}a{color:#214b72}.doc-toc{display:flex;gap:16px;flex-wrap:wrap}.doc-state{color:#765300}@media print{body{margin:0;padding:0}.doc-toc{display:none}figure{break-inside:avoid}details>div{display:block!important}svg{print-color-adjust:exact}}';
  downloadDocument('dashai-documentation.html','text/html;charset=utf-8',`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(doc.title)}</title><style>${css}</style><body><article>${doc.html.replaceAll('<details>','<details open>')}</article></body></html>`);
});
window.addEventListener('beforeprint',()=>document.querySelectorAll('#document-preview details:not([open])').forEach(details=>{details.dataset.closedForPrint='true';details.open=true;}));
window.addEventListener('afterprint',()=>document.querySelectorAll('[data-closed-for-print]').forEach(details=>{details.open=false;delete details.dataset.closedForPrint;}));
$('print-document').addEventListener('click',()=>window.print());
renderNotation();renderDocumentSettings();renderDocumentation();
