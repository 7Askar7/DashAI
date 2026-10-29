import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { FileText, Folder, ChevronRight, ChevronsDownUp, LocateFixed, X, RefreshCw, Search, Download, Check, Sparkles } from 'lucide-react';
import { api, ApiError, date, type Project, type ProjectModule, type Task } from './api';
import { hostRequest, insideVSCode } from './host';
import DocumentationReader, { sectionNames } from './DocumentationReader';
import { renderMarkdown } from './markdown';
import proseStyles from './documentation-prose.css?inline';
import './project-map.css';

type Description = { title: string; summary: string; purpose: string; workflow: string[]; related_paths: string[] };
type MapFile = { path: string; kind: 'file'|'directory'; sha256: string|null; description: Description|null; status: string|null; author_name?: string; updated_at?: string; reviewed_by?: string|null };
export type Diagram = { id: string; title: string; notation: string; scope: string; explanation: string; legend: string; source: string; related_paths: string[]; status: string; author_name: string; updated_at: string; reviewed_by?: string|null };
export type DocumentConfig = { title: string; context: string; sections: string[]; diagram_ids: string[] };
export type MapData = { project_id: string; version: number; source_revision: string; files: MapFile[]; diagrams: Diagram[]; document: DocumentConfig; updated_at: string|null; author_name: string|null };
const notationNames: Record<string,string> = { c4_context:'C4 · L1 · Контекст', c4_containers:'C4 · L2 · Контейнеры', c4_components:'C4 · L3 · Компоненты', sequence:'UML · Sequence', state:'UML · State', erd:'ERD · Данные', flowchart:'Flowchart · Алгоритм' };
const statusNames: Record<string,string> = {draft:'Черновик',stale:'Требует обновления',reviewed:'Проверено человеком'};
const escapeHtml = (value: string) => value.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const svgCache = new Map<string,string>();
const diagramFrame = (svg: string) => `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>:root{color-scheme:dark}body{margin:0;background:transparent;color:#eef1ff}svg{min-width:700px;width:100%;height:auto;display:block}</style></head><body>${svg}</body></html>`;

async function renderDiagramSvg(diagram: Diagram, id: string) {
  const cacheKey=diagram.id+'\n'+diagram.source;
  const cached=svgCache.get(cacheKey);
  if(cached)return cached;
  const mermaid=(await import('mermaid')).default;
  mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'dark',fontFamily:'Segoe UI, sans-serif',maxTextSize:30000,maxEdges:300,suppressErrorRendering:true,flowchart:{htmlLabels:false},secure:['secure','securityLevel','startOnLoad','maxTextSize','maxEdges','suppressErrorRendering','themeCSS','flowchart','fontFamily']});
  const {svg}=await mermaid.render('map'+id,diagram.source);
  if(svgCache.size>=100)svgCache.clear();
  svgCache.set(cacheKey,svg);
  return svg;
}

function DiagramView({diagram}:{diagram:Diagram}) {
  const [svg,setSvg]=useState(''),[error,setError]=useState('');
  const id=useId().replace(/[^a-zA-Z0-9]/g,'');
  useEffect(()=>{
    let cancelled=false;
    setSvg('');setError('');
    (async()=>{
      try {
        const result=await renderDiagramSvg(diagram,id);
        if(cancelled)return;
        setSvg(result);
      } catch { if(!cancelled)setError('Не удалось отрисовать Mermaid. Текст и исходник сохранены; попросите автора исправить синтаксис.'); }
    })();
    return()=>{cancelled=true;};
  },[diagram.id,diagram.source,id]);
  return <div className="map-diagram">
    {error?<p role="alert" className="error-box">{error}</p>:svg?<iframe sandbox="" title={`Схема: ${diagram.title}`} srcDoc={diagramFrame(svg)}/>:<p role="status" className="muted">Отрисовка схемы…</p>}
    <p className="muted">Схему можно прокрутить. Текстовое объяснение доступно ниже.</p>
  </div>;
}

async function saveFile(filename:string,content:string) {
  if(insideVSCode) {await hostRequest('save_document',{filename,content});return;}
  const url=URL.createObjectURL(new Blob([content],{type:filename.endsWith('.html')?'text/html;charset=utf-8':'text/plain;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

type TreeNode = {path:string;name:string;parent:string;children:string[];file?:MapFile;count:number};
const TREE_ROW_HEIGHT=48;
function Tree({files,query,onSelect,selected,onClear,revealRequest}:{files:MapFile[];query:string;onSelect:(path:string)=>void;selected:string;onClear:()=>void;revealRequest:number}) {
  const viewport=useRef<HTMLDivElement>(null),pendingReveal=useRef(''),id=useId();
  const [expanded,setExpanded]=useState<Set<string>>(new Set()),[active,setActive]=useState(''),[scroll,setScroll]=useState(0),[height,setHeight]=useState(480);
  const index=useMemo(()=>{
    const nodes=new Map<string,TreeNode>([['',{path:'',name:'',parent:'',children:[],count:0}]]);
    for(const file of files){
      let parent='';
      for(const name of file.path.split('/')){
        const path=parent?parent+'/'+name:name;
        if(!nodes.has(path)){nodes.set(path,{path,name,parent,children:[],count:0});nodes.get(parent)!.children.push(path);}
        const node=nodes.get(path)!;if(file.kind==='file')node.count++;parent=path;
      }
      nodes.get(file.path)!.file=file;
    }
    for(const node of nodes.values())node.children.sort((a,b)=>Number(!!nodes.get(b)!.children.length||nodes.get(b)!.file?.kind==='directory')-Number(!!nodes.get(a)!.children.length||nodes.get(a)!.file?.kind==='directory')||nodes.get(a)!.name.localeCompare(nodes.get(b)!.name,'ru'));
    return nodes;
  },[files]);
  const searchable=useMemo(()=>files.map(file=>({file,text:[file.path,file.description?.title,file.description?.summary,file.description?.purpose,...(file.description?.workflow||[])].join(' ').toLocaleLowerCase('ru')})),[files]);
  const searching=!!query.trim();
  const matches=useMemo(()=>{const terms=query.trim().toLocaleLowerCase('ru').split(/\s+/);return searchable.filter(({text})=>terms.every(term=>text.includes(term))).map(({file})=>file.path);},[searchable,query]);
  const rows=useMemo(()=>{
    if(searching)return matches.map((path,i)=>({node:index.get(path)!,level:1,position:i+1,siblings:matches.length}));
    const result:{node:TreeNode;level:number;position:number;siblings:number}[]=[];
    const children=index.get('')!.children,stack=children.map((path,i)=>({path,level:1,position:i+1,siblings:children.length})).reverse();
    while(stack.length){const {path,level,position,siblings}=stack.pop()!,node=index.get(path)!;result.push({node,level,position,siblings});if(expanded.has(path))for(let i=node.children.length-1;i>=0;i--)stack.push({path:node.children[i],level:level+1,position:i+1,siblings:node.children.length});}
    return result;
  },[index,expanded,matches,searching]);
  function reveal(path:string){
    pendingReveal.current=path;setActive(path);setExpanded(previous=>{const next=new Set(previous);let parent=index.get(path)?.parent;while(parent){next.add(parent);parent=index.get(parent)?.parent;}return next;});
  }
  useEffect(()=>{reveal(selected);},[selected,index,revealRequest]);
  useEffect(()=>{
    const observer=new ResizeObserver(entries=>setHeight(entries[0].contentRect.height));if(viewport.current)observer.observe(viewport.current);return()=>observer.disconnect();
  },[!!rows.length]);
  useEffect(()=>{
    if(viewport.current){viewport.current.scrollTop=0;setScroll(0);}if(!query.trim()){reveal(selected);return;}const path=matches.includes(selected)?selected:rows[0]?.node.path||'';setActive(path);pendingReveal.current=path;
  },[query]);
  useEffect(()=>{
    const position=rows.findIndex(row=>row.node.path===pendingReveal.current);
    if(position<0)return;
    const element=viewport.current;if(element){const top=position*TREE_ROW_HEIGHT;if(top<element.scrollTop||top+TREE_ROW_HEIGHT>element.scrollTop+element.clientHeight){element.scrollTop=Math.max(0,top-element.clientHeight/2);setScroll(element.scrollTop);}}
    pendingReveal.current='';
  },[rows]);
  const current=Math.max(0,rows.findIndex(row=>row.node.path===active)),start=Math.max(0,Math.floor(scroll/TREE_ROW_HEIGHT)-5),end=Math.min(rows.length,start+Math.ceil(height/TREE_ROW_HEIGHT)+10);
  // Keep the active descendant mounted for assistive technology when the user scrolls it out of view.
  const mounted=[...new Set([...Array.from({length:Math.max(0,end-start)},(_,i)=>start+i),...(rows.length?[current]:[])])].sort((a,b)=>a-b);
  function move(position:number){const row=rows[Math.max(0,Math.min(rows.length-1,position))];if(!row)return;setActive(row.node.path);const element=viewport.current,top=position*TREE_ROW_HEIGHT;if(element){if(top<element.scrollTop)element.scrollTop=top;else if(top+TREE_ROW_HEIGHT>element.scrollTop+element.clientHeight)element.scrollTop=top+TREE_ROW_HEIGHT-element.clientHeight;setScroll(element.scrollTop);}}
  function toggle(path:string){setExpanded(previous=>{const next=new Set(previous);if(next.has(path))next.delete(path);else next.add(path);return next;});}
  function open(node:TreeNode){setActive(node.path);if(node.children.length&&!searching)toggle(node.path);if(node.file)onSelect(node.path);viewport.current?.focus({preventScroll:true});}
  return <div className="map-explorer">
    <div className="map-tree-toolbar"><span role="status">{searching?`Найдено: ${matches.length} из ${files.length}`:`Пути: ${files.length}`}</span><div><button type="button" title="Показать выбранный путь" aria-label="Показать выбранный путь" disabled={!selected} onClick={()=>{onClear();reveal(selected);viewport.current?.focus({preventScroll:true});}}><LocateFixed size={16}/></button><button type="button" title="Свернуть все папки" aria-label="Свернуть все папки" disabled={searching||!expanded.size} onClick={()=>{setExpanded(new Set());setActive(index.get('')!.children[0]||'');if(viewport.current)viewport.current.scrollTop=0;setScroll(0);}}><ChevronsDownUp size={16}/></button></div></div>
    <p className="map-tree-help" id={id+'-help'}>{searching?'Результаты по пути и описанию. Enter — открыть.':'Стрелки — навигация · Enter — описание'}</p>
    {rows.length?<div role="tree" aria-label={searching?'Результаты поиска по карте':'Дерево проекта'} aria-describedby={id+'-help'} aria-activedescendant={id+'-'+current} tabIndex={0} ref={viewport} className="map-tree" style={{height:`min(${rows.length*TREE_ROW_HEIGHT}px, var(--map-tree-max-height))`}} onScroll={event=>setScroll(event.currentTarget.scrollTop)} onKeyDown={event=>{
      const node=rows[current]?.node;if(!node)return;
      if(['ArrowDown','ArrowUp','ArrowRight','ArrowLeft','Home','End','Enter',' '].includes(event.key))event.preventDefault();
      if(event.key==='ArrowDown')move(current+1);else if(event.key==='ArrowUp')move(current-1);else if(event.key==='Home')move(0);else if(event.key==='End')move(rows.length-1);
      else if(event.key==='ArrowRight'&&!searching&&node.children.length){if(!expanded.has(node.path))toggle(node.path);else move(current+1);}
      else if(event.key==='ArrowLeft'&&!searching){if(expanded.has(node.path))toggle(node.path);else {const parent=rows.findIndex(row=>row.node.path===node.parent);if(parent>=0)move(parent);}}
      else if(event.key==='Enter'||event.key===' '){if(node.file)onSelect(node.path);else toggle(node.path);}
    }}><div className="map-tree-spacer" role="none" style={{height:rows.length*TREE_ROW_HEIGHT}}>{mounted.map(i=>{const {node,level,position,siblings}=rows[i],folder=!!node.children.length||node.file?.kind==='directory';return <button type="button" role="treeitem" tabIndex={-1} id={id+'-'+i} key={node.path} data-path={node.path} aria-level={level} aria-posinset={position} aria-setsize={siblings} aria-selected={node.path===selected} aria-expanded={!searching&&node.children.length?expanded.has(node.path):undefined} className={`map-tree-row${i===current?' is-active':''}`} title={node.path} style={{top:i*TREE_ROW_HEIGHT,paddingLeft:searching?10:10+Math.min(level-1,8)*14}} onClick={()=>open(node)}>
      {!searching&&<ChevronRight size={13} className={node.children.length?expanded.has(node.path)?'map-tree-chevron is-open':'map-tree-chevron':'map-tree-chevron is-hidden'}/>}{folder?<Folder size={16}/>:<FileText size={15}/>}<span className="map-tree-label"><span>{node.name}</span>{searching&&<small>{node.path}</small>}</span>{!searching&&folder&&<small className="map-tree-count">{node.count}</small>}
    </button>;})}</div></div>:<div className="map-tree-empty"><strong>{searching?'Пути не найдены':'Карта пока пуста'}</strong><p>{searching?'Попробуйте часть пути, название или слова из объяснения.':'Создайте задачу на анализ: агент опубликует файлы и их описания.'}</p>{searching&&<button type="button" className="button secondary" onClick={onClear}>Сбросить поиск</button>}</div>}
  </div>;
}

function FileContent({file,onSelect}:{file:MapFile;onSelect:(path:string)=>void}) {
  return <><h2>{file.description?.title||file.path.split('/').pop()}</h2><p className="map-path">{file.path}</p>
    <div className="map-meta"><span>{file.status?statusNames[file.status]:'Нет описания'}</span>{file.author_name&&<span>{file.author_name}</span>}{file.updated_at&&<span>{date(file.updated_at,true)}</span>}{file.reviewed_by&&<span>Проверил: {file.reviewed_by}</span>}</div>
    {file.status==='stale'&&<p className="map-warning">Содержимое изменилось в новом снимке. Описание относится к предыдущей версии.</p>}
    {file.description?<><p className="map-lead">{file.description.summary}</p><h3>Зачем нужен</h3><p>{file.description.purpose}</p><h3>Как работает</h3><ol>{file.description.workflow.map((text,i)=><li key={i}>{text}</li>)}</ol><h3>Связанные файлы</h3><div className="map-related">{file.description.related_paths.map(path=><button className="button secondary" key={path} onClick={()=>onSelect(path)}>{path}</button>)}</div></>:<p className="muted">Агент опубликовал путь и hash, но ещё не добавил объяснение.</p>}
  </>;
}

function DiagramLibrary({diagrams,selected,readerId,onSelect}:{diagrams:Diagram[];selected:string;readerId:string;onSelect:(id:string)=>void}) {
  const [query,setQuery]=useState(''),[notation,setNotation]=useState(''),[status,setStatus]=useState('');
  const library=useRef<HTMLDetailsElement>(null),search=useRef<HTMLInputElement>(null);
  const terms=query.trim().toLocaleLowerCase('ru').split(/\s+/);
  const matches=diagrams.filter(diagram=>{const text=[diagram.title,diagram.scope,diagram.explanation,diagram.legend,...diagram.related_paths].join(' ').toLocaleLowerCase('ru');return (!notation||diagram.notation===notation)&&(!status||diagram.status===status)&&terms.every(term=>text.includes(term));});
  const filtered=!!(query.trim()||notation||status),selectedHidden=!!selected&&!matches.some(diagram=>diagram.id===selected);
  function clear(reveal=false) {
    setQuery('');setNotation('');setStatus('');
    requestAnimationFrame(()=>reveal?library.current?.querySelector<HTMLButtonElement>('[aria-current=true]')?.focus():search.current?.focus());
  }
  function choose(id:string) {
    onSelect(id);
    if(window.matchMedia('(max-width:800px)').matches){if(library.current)library.current.open=false;requestAnimationFrame(()=>{const heading=document.getElementById(readerId);heading?.focus({preventScroll:true});heading?.scrollIntoView({block:'start'});});}
  }
  return <details className="architecture-library" ref={library} open>
    <summary>Библиотека схем <span>{diagrams.length}</span></summary>
    <div className="architecture-library-body">
      <label className="architecture-search"><span>Найти схему</span><span><Search size={16} aria-hidden="true"/><input ref={search} type="search" value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==='Escape'){setQuery('');event.preventDefault();}}} placeholder="Название, смысл или путь"/></span></label>
      <div className="architecture-filters">
        <label>Нотация<select value={notation} onChange={event=>setNotation(event.target.value)}><option value="">Все · {diagrams.length}</option>{Object.entries(notationNames).map(([value,name])=><option key={value} value={value}>{name} · {diagrams.filter(diagram=>diagram.notation===value).length}</option>)}</select></label>
        <label>Проверка схемы<select value={status} onChange={event=>setStatus(event.target.value)}><option value="">Все · {diagrams.length}</option>{Object.entries(statusNames).map(([value,name])=><option key={value} value={value}>{name} · {diagrams.filter(diagram=>diagram.status===value).length}</option>)}</select></label>
      </div>
      <div className="architecture-results"><span role="status">Найдено: {matches.length} из {diagrams.length}</span>{filtered&&<button type="button" onClick={()=>clear()}>Сбросить фильтры</button>}</div>
      {selectedHidden&&<div className="architecture-selection-note"><p>Открытая схема вне фильтра. Она остаётся доступна для чтения.</p><button type="button" onClick={()=>clear(true)}>Показать открытую схему</button></div>}
      <a className="architecture-reader-link" href={'#'+readerId}>К открытой схеме</a>
      {matches.length?<ul className="architecture-diagram-list" aria-label="Схемы проекта">{matches.map(diagram=><li key={diagram.id}><button type="button" aria-label={`${diagram.title} · ${notationNames[diagram.notation]} · ${statusNames[diagram.status]}`} aria-current={diagram.id===selected?'true':undefined} onClick={()=>choose(diagram.id)}><span className="architecture-diagram-title">{diagram.title}{diagram.id===selected&&<Check size={16} aria-hidden="true"/>}</span><span>{notationNames[diagram.notation]}</span><span>{statusNames[diagram.status]}</span><span className="architecture-diagram-scope">{diagram.scope}</span></button></li>)}</ul>:<div className="architecture-no-results"><strong>Схемы не найдены</strong><p>Измените запрос или сбросьте фильтры. Поиск учитывает название, область, объяснение и связанные пути.</p></div>}
    </div>
  </details>;
}

export default function ProjectMap({project,mode,onNotify,onDirtyChange,onShowMap}:{project:Project;mode:'map'|'architecture'|'documentation';onNotify:(message:string)=>void;onDirtyChange:(dirty:boolean)=>void;onShowMap:()=>void}) {
  const [data,setData]=useState<MapData|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[selected,setSelected]=useState(''),[query,setQuery]=useState(''),[diagramId,setDiagramId]=useState(''),[doc,setDoc]=useState<DocumentConfig|null>(null),[reason,setReason]=useState(''),[dirty,setDirty]=useState(false),[historic,setHistoric]=useState(''),[importText,setImportText]=useState(''),[taskId,setTaskId]=useState(''),[conflict,setConflict]=useState(false);
  const sequence=useRef(0),root=useRef<HTMLElement>(null),search=useRef<HTMLInputElement>(null),pendingTask=useRef(crypto.randomUUID()),mutationKey=useRef({payload:'',key:''});
  const [revealRequest,setRevealRequest]=useState(0);
  const [settingsOpen,setSettingsOpen]=useState(false),[exporting,setExporting]=useState(false),[printHtml,setPrintHtml]=useState('');
  const settingsPanel=useId(),diagramReaderId=useId();
  const [modules,setModules]=useState<{projectId:string;mapVersion:number;items:ProjectModule[]}|null>(null),[modulesError,setModulesError]=useState(''),[moduleRetry,setModuleRetry]=useState(0);
  const historical=!!historic;
  const modulesReady=modules?.projectId===project.id&&modules.mapVersion===data?.version;
  const documentModules=modulesReady?modules.items.filter(item=>item.enabled&&item.kind==='document'):[];
  const modulesUnavailable=!!doc?.sections.includes('decisions')&&!historical&&(!modulesReady||!!modulesError);
  const historicalModulesNotice='Модули документов не входят в историческую ревизию карты. Текущие ADR и другие документы здесь не включены.';
  useEffect(()=>{const done=()=>setPrintHtml('');window.addEventListener('afterprint',done);return()=>window.removeEventListener('afterprint',done);},[]);
  async function load(version='') {
    const current=++sequence.current;setBusy(true);setError('');setConflict(false);
    try {
      const value=await api<MapData>(`/projects/${project.id}/map${version?'?version='+encodeURIComponent(version):''}`);
      if(current!==sequence.current)return;
      setData(value);setDoc(value.document);setDirty(false);setSelected(path=>value.files.some(f=>f.path===path)?path:value.files[0]?.path||'');setDiagramId(id=>value.diagrams.some(d=>d.id===id)?id:value.diagrams[0]?.id||'');setHistoric(version);setModuleRetry(value=>value+1);
    } catch(e){if(current===sequence.current)setError((e as Error).message);}finally{if(current===sequence.current)setBusy(false);}
  }
  useEffect(()=>{load();return()=>{sequence.current++;};},[project.id]);
  useEffect(()=>{
    setModules(null);setModulesError('');
    if(mode!=='documentation'||historical||!data||data.project_id!==project.id)return;
    let cancelled=false;
    api<{modules:ProjectModule[]}>(`/projects/${project.id}/modules`).then(value=>{if(!cancelled)setModules({projectId:project.id,mapVersion:data.version,items:value.modules});}).catch(error=>{if(!cancelled)setModulesError((error as Error).message);});
    return()=>{cancelled=true;};
  },[project.id,mode,historic,data?.version,moduleRetry]);
  useEffect(()=>{
    onDirtyChange(dirty);
    const guard=(event:BeforeUnloadEvent)=>{if(dirty||busy||exporting)event.preventDefault();};
    const check=(event:Event)=>{if(busy||exporting)(event as CustomEvent<{busy:boolean}>).detail.busy=true;};
    window.addEventListener('beforeunload',guard);window.addEventListener('dashai:check-navigation',check);
    return()=>{window.removeEventListener('beforeunload',guard);window.removeEventListener('dashai:check-navigation',check);};
  },[dirty,busy,exporting,onDirtyChange]);
  function selectFile(path:string,navigate=false,fromTree=false) {
    if(!data?.files.some(f=>f.path===path)){onNotify('Файл отсутствует в этом снимке; проверьте историю карты.');return;}
    setSelected(path);setRevealRequest(value=>value+1);root.current?.querySelector('.map-workspace>.map-file-article')?.scrollTo({top:0});if(!fromTree)setQuery('');if(navigate)onShowMap();
    const mobile=window.matchMedia('(max-width:800px)').matches;
    if(mobile)root.current?.querySelector('.map-mobile-tree')?.removeAttribute('open');
    if(!fromTree||mobile)window.setTimeout(()=>root.current?.querySelector<HTMLElement>('.map-file-article h2')?.focus(),0);
  }
  async function mutate(path:string,body:Record<string,unknown>,method='POST') {
    if(!data)return;
    setBusy(true);setError('');
    const payload=JSON.stringify({...body,expected_version:data.version,reason});
    if(mutationKey.current.payload!==path+payload)mutationKey.current={payload:path+payload,key:crypto.randomUUID()};
    try {await api(`/projects/${project.id}/map${path}`,{method,body:JSON.stringify({...body,expected_version:data.version,reason,idempotency_key:mutationKey.current.key})});await load();onNotify('Карта и история сохранены');setReason('');}
    catch(e){setError((e as Error).message);setConflict(e instanceof ApiError&&e.status===409);}finally{setBusy(false);}
  }
  async function requestAnalysis() {
    setBusy(true);setError('');
    try {
      const task=await api<Task>('/tasks',{method:'POST',body:JSON.stringify({project_id:project.id,task_type:'documentation',title:'Создать или обновить карту проекта',rationale:'Объяснить назначение файлов и архитектуру проекта человеку',description:'Прочитайте исходники в разрешённом репозитории. Вызовите get_project_map, затем publish_project_map с полным манифестом относительных путей, SHA-256, описаниями что/как/зачем и Mermaid-схемами C4/UML/ERD/Flowchart. Исключите секреты, локальные данные, зависимости и сборку. Укажите source_revision; не выдавайте публикацию за независимую проверку.',acceptance_criteria:'Описания и схемы опубликованы через общий API, доступны после перезапуска; даны реальные исходные пути и hashes, соблюдены ограничения данных.',reason:'Пользователь запросил документацию проекта',idempotency_key:pendingTask.current})});
      setTaskId(task.short_id);onNotify(`Создана ${task.short_id}. Ожидает внешнего агента; генерация не запущена автоматически.`);
    }catch(e){setError((e as Error).message);setConflict(e instanceof ApiError&&e.status===409);}finally{setBusy(false);}
  }
  function editDoc(next:DocumentConfig){setDoc(next);setDirty(JSON.stringify(next)!==JSON.stringify(data?.document));}
  function documentParts(diagramSvgs=new Map<string,string>()) {
    if(!data||!doc)return {html:'',markdown:''};
    if(modulesUnavailable)throw new Error(modulesError?`Дополнительные документы не загружены: ${modulesError}. Повторите загрузку перед экспортом.`:'Дождитесь загрузки дополнительных документов перед экспортом.');
    const warning=`Снимок: ${data.source_revision||'не опубликован'}. Версия карты: ${data.version}. Изменения репозитория после анализа не проверены. Статусы отражают проверку автора, а не независимую сертификацию.`;
    let html=`<h1>${escapeHtml(doc.title)}</h1><p>${escapeHtml(warning)}</p>${renderMarkdown(doc.context)}`,markdown=`# ${escapeHtml(doc.title)}\n\n${escapeHtml(warning)}\n\n${doc.context}\n\n`;
    function section(id:string,body:string,text:string){if(doc!.sections.includes(id)){html+=`<section><h2>${sectionNames[id]}</h2>${body}</section>`;markdown+=`## ${sectionNames[id]}\n\n${text}\n\n`;}}
    section('intro',renderMarkdown(project.description),project.description);
    const diagrams=doc.diagram_ids.map(id=>data.diagrams.find(d=>d.id===id)).filter((d):d is Diagram=>!!d);
    section('diagrams',diagrams.map(d=>`<section><h3>${escapeHtml(d.title)} · ${notationNames[d.notation]}</h3><p>${statusNames[d.status]}</p><p>Область: ${escapeHtml(d.scope)}</p>${diagramSvgs.get(d.id)||`<pre>${escapeHtml(d.source)}</pre>`}<h4>Как читать схему</h4>${renderMarkdown(d.legend)}${renderMarkdown(d.explanation)}<p>Файлы: ${d.related_paths.map(escapeHtml).join(', ')}</p></section>`).join(''),diagrams.map(d=>`### ${escapeHtml(d.title)} · ${notationNames[d.notation]}\n\n${statusNames[d.status]}\n\nОбласть: ${escapeHtml(d.scope)}\n\n\`\`\`mermaid\n${d.source}\n\`\`\`\n\nЛегенда: ${escapeHtml(d.legend)}\n\n${escapeHtml(d.explanation)}\n\nФайлы: ${d.related_paths.join(', ')}`).join('\n\n'));
    section('files',data.files.map(f=>`<section><h3>${escapeHtml(f.path)}</h3><p>${f.status?statusNames[f.status]:'Нет описания'}</p>${f.description?`${renderMarkdown(f.description.summary)}<h4>Зачем нужен</h4>${renderMarkdown(f.description.purpose)}<h4>Как работает</h4><ol>${f.description.workflow.map(t=>`<li>${escapeHtml(t)}</li>`).join('')}</ol>`:''}</section>`).join(''),data.files.map(f=>`### ${escapeHtml(f.path)}\n\n${f.status?statusNames[f.status]:'Нет описания'}\n\n${escapeHtml(f.description?.summary||'')}\n\nЗачем: ${escapeHtml(f.description?.purpose||'')}\n\n${f.description?.workflow.map(t=>'- '+escapeHtml(t)).join('\n')||''}`).join('\n\n'));
    const moduleNotice=historical?historicalModulesNotice:documentModules.length?'Дополнительные документы загружены отдельно от снимка карты; ниже указаны их собственные версии.':'Дополнительные документы не добавлены в проект. Решения и причины изменений доступны в журнале проекта.';
    section('decisions',`<p>${escapeHtml(moduleNotice)}</p>`+(!historical?documentModules.map(item=>`<section><h3>${escapeHtml(item.name)}</h3><p>Модуль документа · v${item.version}</p>${renderMarkdown(item.content)}</section>`).join(''):''),moduleNotice+(!historical?'\n\n'+documentModules.map(item=>`### ${escapeHtml(item.name)}\n\nМодуль документа · v${item.version}\n\n${item.content}`).join('\n\n'):''));
    section('verification',`<p>${escapeHtml(warning)}</p>`,escapeHtml(warning));
    return {html,markdown};
  }
  async function exportDoc(format:'md'|'html'|'print') {
    setExporting(true);setError('');
    try {
      if(modulesUnavailable)throw new Error('Дождитесь загрузки дополнительных документов перед экспортом.');
      const diagramSvgs=new Map<string,string>();
      if(format!=='md'&&doc?.sections.includes('diagrams'))for(const id of doc.diagram_ids){
        const d=data?.diagrams.find(item=>item.id===id);
        if(!d)throw new Error('Выбранная схема отсутствует в снимке. Обновите состав документа.');
        try{diagramSvgs.set(d.id,await renderDiagramSvg(d,crypto.randomUUID().replace(/-/g,'')));}
        catch{throw new Error(`Не удалось подготовить схему «${d.title}». Исправьте её или исключите из состава документа. Markdown сохраняет исходник схемы.`);}
      }
      const parts=documentParts(diagramSvgs);
      if(format==='print'){flushSync(()=>setPrintHtml(parts.html));window.print();return;}
      const html=`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${escapeHtml(doc?.title||project.name)}</title><style>${proseStyles}body{font:16px/1.8 Segoe UI,sans-serif;max-width:78ch;margin:40px auto;padding:0 24px;color:#17202a}h2{margin-top:36px}svg{width:100%;max-width:100%;height:auto;background:#11171f}section{break-inside:auto}section>section{margin:32px 0}@media print{body{margin:0}svg{print-color-adjust:exact}}</style><body class="doc-markdown">${parts.html}</body></html>`;
      await saveFile(`dashai-documentation.${format}`,format==='md'?parts.markdown:html);
    }catch(e){setError((e as Error).message);}finally{setExporting(false);}
  }
  if(!data)return <section className="project-map"><p>{busy?'Загрузка карты…':'Карта недоступна'}</p>{error&&<p className="error-box" role="alert">{error}</p>}<button className="button secondary" onClick={()=>load()} disabled={busy}>Повторить</button></section>;
  const versionForm=data.version>0&&<form className="map-version" onSubmit={e=>{e.preventDefault();if(busy||dirty)return;const value=new FormData(e.currentTarget).get('version');load(String(value||''));}}><label>Версия из истории <input type="number" name="version" min="1" max={data.version} defaultValue={data.version} aria-label="Номер версии карты"/></label><button className="button secondary" disabled={busy||dirty}>Открыть</button>{historical&&<><span className="map-warning">Исторический снимок · только чтение</span><button type="button" className="button secondary" onClick={()=>load()} disabled={dirty}>К текущей карте</button></>}</form>;
  const file=data.files.find(f=>f.path===selected), diagram=data.diagrams.find(d=>d.id===diagramId);
  return <section className={`project-map${mode==='documentation'?' documentation-view':''}`} ref={root} aria-label={mode==='documentation'?'Документация проекта':mode==='architecture'?'Архитектура проекта':'Карта проекта'}>
    <header className="map-toolbar"><div><h2>{mode==='map'?'Карта проекта':mode==='architecture'?'Архитектура':'Документация'}</h2><p className="muted">{mode==='documentation'&&data.version?`${data.author_name} · ${date(data.updated_at!,true)}`:data.version?`Снимок ${data.source_revision} · v${data.version} · ${data.author_name} · ${date(data.updated_at!,true)}`:'Агент ещё не опубликовал карту этого проекта'}</p></div><div className="map-actions"><button className="button secondary" onClick={()=>load()} disabled={busy||dirty}><RefreshCw size={15}/>Обновить</button><button className="button primary" onClick={requestAnalysis} disabled={busy||!!taskId}><Sparkles size={15}/>{taskId?`${taskId} · ожидает агента`:'Задача на анализ'}</button></div></header>

    {error&&<div role="alert" className="error-box">{error}{conflict&&<><span> Сохраните свой текст перед загрузкой актуальной карты.</span><button className="button secondary" disabled={busy} onClick={()=>{if(!dirty||confirm('Сбросить несохранённый состав документа и загрузить актуальную карту?'))load();}}>Перечитать карту</button></>}</div>}
    {dirty&&<p role="status" className="map-warning">Есть несохранённый состав документа. Экспорт использует ваши текущие настройки; сохраните их перед закрытием вкладки.</p>}
    {mode!=='map'?<details className="doc-source"><summary>Снимок v{data.version} · Актуальность после анализа не проверена</summary><p>{data.source_revision||'Снимок ещё не опубликован'}</p><p className="map-truth">DashAI хранит результат внешнего агента. Изменения файлов после снимка не проверены. Задача на анализ появится на доске; модель автоматически не запускается.</p>{versionForm}</details>:<><p className="map-truth">DashAI хранит результат внешнего агента. Изменения файлов после снимка не проверены. Задача на анализ появится на доске; модель автоматически не запускается.</p>{versionForm}</>}
    {mode==='map'&&<div className="map-workspace"><aside><label className="map-search"><Search size={16}/><input ref={search} value={query} onChange={e=>{setQuery(e.target.value);const tree=root.current?.querySelector<HTMLDetailsElement>('.map-mobile-tree');if(tree)tree.open=true;}} onKeyDown={event=>{if(event.key==='Escape'){setQuery('');event.preventDefault();}if(event.key==='ArrowDown'){root.current?.querySelector<HTMLElement>('[role=tree]')?.focus();event.preventDefault();}}} placeholder="Путь, название, объяснение" aria-label="Найти файл или объяснение"/>{query&&<button type="button" aria-label="Сбросить поиск" onClick={()=>{setQuery('');search.current?.focus();}}><X size={15}/></button>}</label><details className="map-mobile-tree" open><summary>Файлы и папки · {data.files.length}</summary><Tree files={data.files} query={query} selected={selected} revealRequest={revealRequest} onSelect={path=>selectFile(path,false,true)} onClear={()=>setQuery('')}/></details></aside><article className="map-file-article">{file?<><div tabIndex={-1} ref={node=>node?.querySelector('h2')?.setAttribute('tabindex','-1')}><FileContent file={file} onSelect={selectFile}/></div>{file.description&&file.status!=='stale'&&file.status!=='reviewed'&&!historical&&<div className="map-review"><label>Основание проверки<input value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></label><button className="button secondary" disabled={busy||dirty||!reason.trim()} onClick={()=>mutate('/review',{path:file.path})}><Check size={15}/>Подтвердить после сверки</button></div>}</>:<p className="empty-state">Карта пока пуста. Создайте задачу на анализ или опубликуйте снимок через MCP / импорт JSON.</p>}</article></div>}
    {mode==='architecture'&&(diagram?<div className="architecture-workspace">
      <DiagramLibrary diagrams={data.diagrams} selected={diagramId} readerId={diagramReaderId} onSelect={id=>{setDiagramId(id);root.current?.querySelector('.architecture-reader')?.scrollTo({top:0});}}/>
      <article className="map-file-article architecture-reader" aria-labelledby={diagramReaderId}>
        <header className="architecture-reader-header"><div><h2 id={diagramReaderId} tabIndex={-1}>{diagram.title}</h2><p className="map-meta"><span>{notationNames[diagram.notation]}</span><span>{statusNames[diagram.status]}</span></p></div><button className="button secondary" onClick={()=>saveFile('dashai-diagram.mmd',diagram.source).catch(e=>setError(e.message))}><Download size={15} aria-hidden="true"/>Скачать .mmd</button></header>
        <div className="map-meta"><span>Автор: {diagram.author_name}</span><span>{date(diagram.updated_at,true)}</span>{diagram.reviewed_by&&<span>Проверил: {diagram.reviewed_by}</span>}</div>
        {diagram.status==='stale'&&<p className="map-warning">После обновления снимка схема требует сверки с исходниками.</p>}
        <p><strong>Область:</strong> {diagram.scope}</p>
        <DiagramView diagram={diagram}/>
        <h3>Объяснение</h3><p>{diagram.explanation}</p><h3>Легенда</h3><p>{diagram.legend}</p>
        {!!diagram.related_paths.length&&<><h3>Связанные файлы</h3><div className="map-related">{diagram.related_paths.map(path=><button className="button secondary" key={path} onClick={()=>selectFile(path,true)}>{path}</button>)}</div></>}
        <details className="architecture-source"><summary>Исходник Mermaid</summary><pre>{diagram.source}</pre></details>
        {diagram.status==='draft'&&!historical&&<div className="map-review"><label>Основание проверки<input value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></label><button className="button secondary" disabled={busy||dirty||!reason.trim()} onClick={()=>mutate('/review',{diagram_id:diagram.id})}>Подтвердить после сверки</button></div>}
      </article>
    </div>:<p className="empty-state">Схем пока нет. Создайте задачу на анализ: агент может опубликовать C4 (контекст, контейнеры, компоненты), UML Sequence/State, ERD и Flowchart. Здесь будут только схемы выбранного проекта.</p>)}
    {mode==='documentation'&&doc&&<>
      <div className="doc-toolbar">
        <button type="button" className="button secondary" aria-expanded={settingsOpen} aria-controls={settingsPanel} onClick={()=>setSettingsOpen(value=>!value)}>Настроить состав{dirty?' · Не сохранён':''}</button>
        <div className="map-actions" aria-label="Экспорт полного документа">
          <button className="button secondary" disabled={modulesUnavailable||exporting||busy} onClick={()=>exportDoc('md')}><Download size={15}/>Markdown</button>
          <button className="button secondary" disabled={modulesUnavailable||exporting||busy} onClick={()=>exportDoc('html')}><Download size={15}/>HTML</button>
          <button className="button secondary" disabled={modulesUnavailable||exporting||busy} onClick={()=>exportDoc('print')}>Печать / PDF</button>
        </div>
      </div>
      {exporting&&<p role="status" className="muted">Подготовка полного документа и схем…</p>}
      {doc.sections.includes('decisions')&&!historical&&modulesError&&<div className="error-box" role="alert">Не удалось загрузить дополнительные документы: {modulesError}. Экспорт с этим разделом ожидает полной загрузки.<button className="button secondary" onClick={()=>setModuleRetry(value=>value+1)}>Повторить загрузку модулей</button></div>}
      <div className="doc-settings-panel" id={settingsPanel} hidden={!settingsOpen}>
        <h3>Состав документа</h3><p className="muted">Выберите разделы для чтения, экспорта и печати. Изменения применятся к предпросмотру сразу; сохраните состав, чтобы использовать его при следующем открытии.</p>
        <fieldset className="map-settings" aria-label="Состав документа" disabled={busy||historical||exporting}><label>Название<input value={doc.title} maxLength={255} onChange={e=>editDoc({...doc,title:e.target.value})}/></label><label>Контекст<textarea value={doc.context} maxLength={20000} rows={4} onChange={e=>editDoc({...doc,context:e.target.value})}/></label><h3>Разделы</h3>{Object.entries(sectionNames).map(([id,label])=><label className="map-checkbox" key={id}><input type="checkbox" checked={doc.sections.includes(id)} onChange={e=>editDoc({...doc,sections:e.target.checked?[...doc.sections,id]:doc.sections.filter(v=>v!==id)})}/>{label}</label>)}<h3>Схемы</h3>{data.diagrams.map(d=><label className="map-checkbox" key={d.id}><input type="checkbox" checked={doc.diagram_ids.includes(d.id)} onChange={e=>editDoc({...doc,diagram_ids:e.target.checked?[...doc.diagram_ids,d.id]:doc.diagram_ids.filter(v=>v!==d.id)})}/>{notationNames[d.notation]} · {d.title}</label>)}<label>Причина сохранения<input value={reason} maxLength={4000} onChange={e=>setReason(e.target.value)}/></label><button className="button primary" disabled={busy||historical||!dirty||!reason.trim()||!doc.title.trim()} onClick={()=>mutate('/document',{document:doc},'PATCH')}>Сохранить состав</button></fieldset>
      </div>
      <DocumentationReader key={project.id} project={project} data={data} doc={doc} modules={documentModules} modulesReady={modulesReady} modulesError={modulesError} historical={historical} historicalNotice={historicalModulesNotice} onConfigure={()=>{setSettingsOpen(true);requestAnimationFrame(()=>document.getElementById(settingsPanel)?.scrollIntoView({block:'nearest'}));}} renderDiagram={diagram=><DiagramView diagram={diagram}/>}/>
      {printHtml&&<article className="doc-print-content doc-markdown" dangerouslySetInnerHTML={{__html:printHtml}}/>}
    </>}
    {!historical&&<details className="map-import"><summary>Публикация снимка · MCP или JSON</summary><p>Агент читает исходники в своей среде и вызывает <code>get_project_map</code> / <code>publish_project_map</code>. Для ручного импорта вставьте JSON с source_revision, files и необязательными diagrams. Файлы требуют SHA-256; описание: title, summary, purpose, workflow, related_paths. Нотации: c4_context, c4_containers, c4_components, sequence, state, erd, flowchart. Причина и текущая версия передаются отдельно.</p><label>Снимок JSON<textarea aria-label="Снимок JSON" value={importText} onChange={e=>setImportText(e.target.value)} maxLength={2000000} rows={8}/></label><label>Причина публикации<input value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></label><button className="button secondary" disabled={busy||dirty||!reason.trim()||!importText.trim()} onClick={()=>{try{const parsed=JSON.parse(importText);if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('Нужен JSON-объект снимка');mutate('',{source_revision:parsed.source_revision,files:parsed.files,...(Object.hasOwn(parsed,'diagrams')?{diagrams:parsed.diagrams}:{})},'PUT');}catch(e){setError((e as Error).message);}}}>Опубликовать снимок</button></details>}
  </section>;
}
