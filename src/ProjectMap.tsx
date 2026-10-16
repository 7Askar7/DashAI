import { useEffect, useId, useRef, useState } from 'react';
import { FileText, Folder, RefreshCw, Search, Download, Check, Sparkles } from 'lucide-react';
import { api, ApiError, date, type Project, type Task } from './api';
import { hostRequest, insideVSCode } from './host';
import './project-map.css';

type Description = { title: string; summary: string; purpose: string; workflow: string[]; related_paths: string[] };
type MapFile = { path: string; kind: 'file'|'directory'; sha256: string|null; description: Description|null; status: string|null; author_name?: string; updated_at?: string; reviewed_by?: string|null };
type Diagram = { id: string; title: string; notation: string; scope: string; explanation: string; legend: string; source: string; related_paths: string[]; status: string; author_name: string; updated_at: string; reviewed_by?: string|null };
type DocumentConfig = { title: string; context: string; sections: string[]; diagram_ids: string[] };
type MapData = { project_id: string; version: number; source_revision: string; files: MapFile[]; diagrams: Diagram[]; document: DocumentConfig; updated_at: string|null; author_name: string|null };
const notationNames: Record<string,string> = { c4_context:'C4 · L1 · Контекст', c4_containers:'C4 · L2 · Контейнеры', c4_components:'C4 · L3 · Компоненты', sequence:'UML · Sequence', state:'UML · State', erd:'ERD · Данные', flowchart:'Flowchart · Алгоритм' };
const sectionNames: Record<string,string> = {intro:'Цель и границы',diagrams:'Архитектура и сценарии',files:'Описания файлов',decisions:'Решения',verification:'Проверки и ограничения'};
const statusNames: Record<string,string> = {draft:'Черновик',stale:'Требует обновления',reviewed:'Проверено человеком'};
const escapeHtml = (value: string) => value.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const svgCache = new Map<string,string>();
const diagramFrame = (svg: string) => `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><style>body{margin:0;background:#11171f;color:#e9edf2}svg{min-width:700px;width:100%;height:auto;display:block}</style></head><body>${svg}</body></html>`;

function DiagramView({diagram}:{diagram:Diagram}) {
  const [svg,setSvg]=useState(''),[error,setError]=useState('');
  const id=useId().replace(/[^a-zA-Z0-9]/g,'');
  useEffect(()=>{
    let cancelled=false;
    setSvg('');setError('');
    (async()=>{
      try {
        const mermaid=(await import('mermaid')).default;
        mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'dark',fontFamily:'Segoe UI, sans-serif',maxTextSize:30000,maxEdges:300,suppressErrorRendering:true,flowchart:{htmlLabels:false},secure:['secure','securityLevel','startOnLoad','maxTextSize','maxEdges','suppressErrorRendering','themeCSS','flowchart','fontFamily']});
        const cacheKey=diagram.id+'\n'+diagram.source;
        const cached=svgCache.get(cacheKey);
        const result=cached || (await mermaid.render('map'+id,diagram.source)).svg;
        if(cancelled)return;
        if(svgCache.size>100)svgCache.clear();
        svgCache.set(cacheKey,result);setSvg(result);
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

function Tree({paths,onSelect,selected}:{paths:string[];onSelect:(path:string)=>void;selected:string}) {
  function branch(prefix:string): React.ReactNode {
    const names=[...new Set(paths.filter(p=>p.startsWith(prefix)).map(p=>p.slice(prefix.length).split('/')[0]))].sort((a,b)=>a.localeCompare(b,'ru'));
    return names.map(name=>{
      const path=prefix+name,children=paths.some(p=>p.startsWith(path+'/'));
      return children?<details open key={path}><summary><Folder size={15}/>{name}</summary>{paths.includes(path)&&<button onClick={()=>onSelect(path)} aria-current={path===selected?'true':undefined}>Описание папки</button>}<div className="map-tree-level">{branch(path+'/')}</div></details>:<button key={path} onClick={()=>onSelect(path)} aria-current={path===selected?'true':undefined}><FileText size={14}/>{name}</button>;
    });
  }
  return <nav aria-label="Дерево проекта" className="map-tree">{branch('')}</nav>;
}

function FileContent({file,onSelect}:{file:MapFile;onSelect:(path:string)=>void}) {
  return <><h2>{file.description?.title||file.path.split('/').pop()}</h2><p className="map-path">{file.path}</p>
    <div className="map-meta"><span>{file.status?statusNames[file.status]:'Нет описания'}</span>{file.author_name&&<span>{file.author_name}</span>}{file.updated_at&&<span>{date(file.updated_at,true)}</span>}{file.reviewed_by&&<span>Проверил: {file.reviewed_by}</span>}</div>
    {file.status==='stale'&&<p className="map-warning">Содержимое изменилось в новом снимке. Описание относится к предыдущей версии.</p>}
    {file.description?<><p className="map-lead">{file.description.summary}</p><h3>Зачем нужен</h3><p>{file.description.purpose}</p><h3>Как работает</h3><ol>{file.description.workflow.map((text,i)=><li key={i}>{text}</li>)}</ol><h3>Связанные файлы</h3><div className="map-related">{file.description.related_paths.map(path=><button className="button secondary" key={path} onClick={()=>onSelect(path)}>{path}</button>)}</div></>:<p className="muted">Агент опубликовал путь и hash, но ещё не добавил объяснение.</p>}
  </>;
}

export default function ProjectMap({project,mode,onNotify,onDirtyChange,onShowMap}:{project:Project;mode:'map'|'architecture'|'documentation';onNotify:(message:string)=>void;onDirtyChange:(dirty:boolean)=>void;onShowMap:()=>void}) {
  const [data,setData]=useState<MapData|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[selected,setSelected]=useState(''),[query,setQuery]=useState(''),[diagramId,setDiagramId]=useState(''),[doc,setDoc]=useState<DocumentConfig|null>(null),[reason,setReason]=useState(''),[dirty,setDirty]=useState(false),[historic,setHistoric]=useState(''),[importText,setImportText]=useState(''),[taskId,setTaskId]=useState(''),[conflict,setConflict]=useState(false);
  const sequence=useRef(0),root=useRef<HTMLElement>(null),pendingTask=useRef(crypto.randomUUID()),mutationKey=useRef({payload:'',key:''});
  const historical=!!historic;
  async function load(version='') {
    const current=++sequence.current;setBusy(true);setError('');setConflict(false);
    try {
      const value=await api<MapData>(`/projects/${project.id}/map${version?'?version='+encodeURIComponent(version):''}`);
      if(current!==sequence.current)return;
      setData(value);setDoc(value.document);setDirty(false);setSelected(path=>value.files.some(f=>f.path===path)?path:value.files[0]?.path||'');setDiagramId(id=>value.diagrams.some(d=>d.id===id)?id:value.diagrams[0]?.id||'');setHistoric(version);
    } catch(e){if(current===sequence.current)setError((e as Error).message);}finally{if(current===sequence.current)setBusy(false);}
  }
  useEffect(()=>{load();return()=>{sequence.current++;};},[project.id]);
  useEffect(()=>{onDirtyChange(dirty);const guard=(event:BeforeUnloadEvent)=>{if(dirty)event.preventDefault();};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);},[dirty,onDirtyChange]);
  function selectFile(path:string,navigate=false) {
    if(!data?.files.some(f=>f.path===path)){onNotify('Файл отсутствует в этом снимке; проверьте историю карты.');return;}
    setSelected(path);if(navigate)onShowMap();
    window.setTimeout(()=>root.current?.querySelector<HTMLElement>('.map-file-article h2')?.focus(),0);
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
  function editDoc(next:DocumentConfig){setDoc(next);setDirty(true);}
  function documentParts() {
    if(!data||!doc)return {html:'',markdown:''};
    const warning=`Снимок: ${data.source_revision||'не опубликован'}. Версия карты: ${data.version}. Изменения репозитория после анализа не проверены. Статусы отражают проверку автора, а не независимую сертификацию.`;
    let html=`<h1>${escapeHtml(doc.title)}</h1><p>${escapeHtml(warning)}</p><p>${escapeHtml(doc.context)}</p>`,markdown=`# ${escapeHtml(doc.title)}\n\n${escapeHtml(warning)}\n\n${escapeHtml(doc.context)}\n\n`;
    function section(id:string,body:string,text:string){if(doc!.sections.includes(id)){html+=`<section><h2>${sectionNames[id]}</h2>${body}</section>`;markdown+=`## ${sectionNames[id]}\n\n${text}\n\n`;}}
    section('intro',`<p>${escapeHtml(project.description)}</p>`,escapeHtml(project.description));
    const diagrams=doc.diagram_ids.map(id=>data.diagrams.find(d=>d.id===id)).filter((d):d is Diagram=>!!d);
    section('diagrams',diagrams.map(d=>`<section><h3>${escapeHtml(d.title)} · ${notationNames[d.notation]}</h3><p>${statusNames[d.status]}</p><p>Область: ${escapeHtml(d.scope)}</p>${svgCache.get(d.id+'\n'+d.source)||`<pre>${escapeHtml(d.source)}</pre>`}<p>Легенда: ${escapeHtml(d.legend)}</p><p>${escapeHtml(d.explanation)}</p><p>Файлы: ${d.related_paths.map(escapeHtml).join(', ')}</p></section>`).join(''),diagrams.map(d=>`### ${escapeHtml(d.title)} · ${notationNames[d.notation]}\n\n${statusNames[d.status]}\n\nОбласть: ${escapeHtml(d.scope)}\n\n\`\`\`mermaid\n${d.source}\n\`\`\`\n\nЛегенда: ${escapeHtml(d.legend)}\n\n${escapeHtml(d.explanation)}\n\nФайлы: ${d.related_paths.join(', ')}`).join('\n\n'));
    section('files',data.files.map(f=>`<section><h3>${escapeHtml(f.path)}</h3><p>${f.status?statusNames[f.status]:'Нет описания'}</p>${f.description?`<p>${escapeHtml(f.description.summary)}</p><h4>Зачем нужен</h4><p>${escapeHtml(f.description.purpose)}</p><h4>Как работает</h4><ol>${f.description.workflow.map(t=>`<li>${escapeHtml(t)}</li>`).join('')}</ol>`:''}</section>`).join(''),data.files.map(f=>`### ${escapeHtml(f.path)}\n\n${f.status?statusNames[f.status]:'Нет описания'}\n\n${escapeHtml(f.description?.summary||'')}\n\nЗачем: ${escapeHtml(f.description?.purpose||'')}\n\n${f.description?.workflow.map(t=>'- '+escapeHtml(t)).join('\n')||''}`).join('\n\n'));
    section('decisions','<p>Решения и причины изменений находятся в журнале проекта. В этой карте они не опубликованы отдельными ADR.</p>','Решения и причины изменений находятся в журнале проекта. Отдельные ADR не опубликованы.');
    section('verification',`<p>${escapeHtml(warning)}</p>`,escapeHtml(warning));
    return {html,markdown};
  }
  async function exportDoc(format:'md'|'html') {
    try {
      const parts=documentParts();
      if(format==='html'&&doc?.sections.includes('diagrams')&&doc.diagram_ids.some(id=>{const d=data?.diagrams.find(d=>d.id===id);return !d||!svgCache.has(d.id+'\n'+d.source);}))throw new Error('Дождитесь отрисовки всех выбранных схем либо исключите схему с ошибкой. Markdown сохраняет исходники независимо от отрисовки.');
      const html=`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${escapeHtml(doc?.title||project.name)}</title><style>body{font:16px/1.7 Segoe UI,sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#17202a}h2{margin-top:36px}p,li,h1,h3{overflow-wrap:anywhere;white-space:pre-wrap}svg{max-width:100%;height:auto;background:#11171f}pre{white-space:pre-wrap}section{break-inside:auto}@media print{body{margin:0}svg{print-color-adjust:exact}}</style><body>${parts.html}</body></html>`;
      await saveFile(`dashai-documentation.${format}`,format==='md'?parts.markdown:html);
    }catch(e){setError((e as Error).message);}
  }
  if(!data)return <section className="project-map"><p>{busy?'Загрузка карты…':'Карта недоступна'}</p>{error&&<p className="error-box" role="alert">{error}</p>}<button className="button secondary" onClick={()=>load()} disabled={busy}>Повторить</button></section>;
  const file=data.files.find(f=>f.path===selected), diagram=data.diagrams.find(d=>d.id===diagramId);
  const filtered=data.files.filter(f=>[f.path,f.description?.title,f.description?.summary,f.description?.purpose,...(f.description?.workflow||[])].join(' ').toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru')));
  return <section className="project-map" ref={root} aria-label="Карта проекта">
    <header className="map-toolbar"><div><h2>{mode==='map'?'Карта проекта':mode==='architecture'?'Архитектура':'Документация'}</h2><p className="muted">{data.version?`Снимок ${data.source_revision} · v${data.version} · ${data.author_name} · ${date(data.updated_at!,true)}`:'Агент ещё не опубликовал карту этого проекта'}</p></div><div className="map-actions"><button className="button secondary" onClick={()=>load()} disabled={busy||dirty}><RefreshCw size={15}/>Обновить</button><button className="button primary" onClick={requestAnalysis} disabled={busy||!!taskId}><Sparkles size={15}/>{taskId?`${taskId} · ожидает агента`:'Задача на анализ'}</button></div></header>
    <p className="map-truth">DashAI хранит результат внешнего агента. Изменения файлов после снимка не проверены. Задача на анализ появится на доске; модель автоматически не запускается.</p>
    {error&&<div role="alert" className="error-box">{error}{conflict&&<><span> Сохраните свой текст перед загрузкой актуальной карты.</span><button className="button secondary" disabled={busy} onClick={()=>{if(!dirty||confirm('Сбросить несохранённый состав документа и загрузить актуальную карту?'))load();}}>Перечитать карту</button></>}</div>}
    {dirty&&<p role="status" className="map-warning">Есть несохранённый состав документа. Экспорт использует ваши текущие настройки; сохраните их перед закрытием вкладки.</p>}
    {data.version>0&&<form className="map-version" onSubmit={e=>{e.preventDefault();if(busy||dirty)return;const value=new FormData(e.currentTarget).get('version');load(String(value||''));}}><label>Версия из истории <input type="number" name="version" min="1" max={data.version} defaultValue={data.version} aria-label="Номер версии карты"/></label><button className="button secondary" disabled={busy||dirty}>Открыть</button>{historical&&<><span className="map-warning">Исторический снимок · только чтение</span><button type="button" className="button secondary" onClick={()=>load()} disabled={dirty}>К текущей карте</button></>}</form>}
    {mode==='map'&&<div className="map-workspace"><aside><label className="map-search"><Search size={16}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Найти файл или объяснение" aria-label="Найти файл или объяснение"/></label><details className="map-mobile-tree" open><summary>Файлы · {filtered.length}</summary><Tree paths={filtered.map(f=>f.path)} selected={selected} onSelect={selectFile}/></details></aside><article className="map-file-article">{file?<><div tabIndex={-1} ref={node=>node?.querySelector('h2')?.setAttribute('tabindex','-1')}><FileContent file={file} onSelect={selectFile}/></div>{file.description&&file.status!=='stale'&&file.status!=='reviewed'&&!historical&&<div className="map-review"><label>Основание проверки<input value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></label><button className="button secondary" disabled={busy||dirty||!reason.trim()} onClick={()=>mutate('/review',{path:file.path})}><Check size={15}/>Подтвердить после сверки</button></div>}</>:<p className="empty-state">Карта пока пуста. Создайте задачу на анализ или опубликуйте снимок через MCP / импорт JSON.</p>}{query&&!filtered.length&&<p role="status">Ничего не найдено. Измените поиск.</p>}</article></div>}
    {mode==='architecture'&&<><label className="map-notation">Схема / нотация<select value={diagramId} onChange={e=>setDiagramId(e.target.value)}><option value="">Выберите опубликованную схему</option>{data.diagrams.map(d=><option key={d.id} value={d.id}>{notationNames[d.notation]} · {d.title}</option>)}</select></label>{diagram?<article className="map-file-article"><h2>{diagram.title}</h2><p className="map-meta">{statusNames[diagram.status]} · {diagram.author_name} · {date(diagram.updated_at,true)}</p><p><strong>Область:</strong> {diagram.scope}</p><DiagramView diagram={diagram}/><h3>Легенда</h3><p>{diagram.legend}</p><h3>Объяснение</h3><p>{diagram.explanation}</p><div className="map-related">{diagram.related_paths.map(path=><button className="button secondary" key={path} onClick={()=>selectFile(path,true)}>{path}</button>)}</div><details><summary>Исходник Mermaid</summary><pre>{diagram.source}</pre><button className="button secondary" onClick={()=>saveFile('dashai-diagram.mmd',diagram.source).catch(e=>setError(e.message))}>Скачать .mmd</button></details>{diagram.status==='draft'&&!historical&&<div className="map-review"><label>Основание проверки<input value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></label><button className="button secondary" disabled={busy||dirty||!reason.trim()} onClick={()=>mutate('/review',{diagram_id:diagram.id})}>Подтвердить после сверки</button></div>}</article>:<p className="empty-state">Схем пока нет. Агент может опубликовать C4 (контекст, контейнеры, компоненты), UML Sequence/State, ERD и Flowchart. Здесь будут только схемы выбранного проекта.</p>}</>}
    {mode==='documentation'&&doc&&<><div className="map-actions"><button className="button secondary" onClick={()=>exportDoc('md')}><Download size={15}/>Markdown</button><button className="button secondary" onClick={()=>exportDoc('html')}><Download size={15}/>HTML</button><button className="button secondary" onClick={()=>window.print()}>Печать / PDF</button></div><div className="map-document-layout"><fieldset className="map-settings" aria-label="Состав документа" disabled={busy||historical}><label>Название<input value={doc.title} maxLength={255} onChange={e=>editDoc({...doc,title:e.target.value})}/></label><label>Контекст<textarea value={doc.context} maxLength={20000} rows={4} onChange={e=>editDoc({...doc,context:e.target.value})}/></label><h3>Разделы</h3>{Object.entries(sectionNames).map(([id,label])=><label className="map-checkbox" key={id}><input type="checkbox" checked={doc.sections.includes(id)} onChange={e=>editDoc({...doc,sections:e.target.checked?[...doc.sections,id]:doc.sections.filter(v=>v!==id)})}/>{label}</label>)}<h3>Схемы</h3>{data.diagrams.map(d=><label className="map-checkbox" key={d.id}><input type="checkbox" checked={doc.diagram_ids.includes(d.id)} onChange={e=>editDoc({...doc,diagram_ids:e.target.checked?[...doc.diagram_ids,d.id]:doc.diagram_ids.filter(v=>v!==d.id)})}/>{notationNames[d.notation]} · {d.title}</label>)}<label>Причина сохранения<input value={reason} maxLength={4000} onChange={e=>setReason(e.target.value)}/></label><button className="button primary" disabled={busy||historical||!dirty||!reason.trim()||!doc.title.trim()} onClick={()=>mutate('/document',{document:doc},'PATCH')}>Сохранить состав</button></fieldset><article className="map-document-preview"><h1>{doc.title}</h1><p>{doc.context}</p><p className="map-warning">Снимок {data.source_revision||'не опубликован'} · v{data.version}. Актуальность после анализа не проверена.</p>{doc.sections.includes('intro')&&<section><h2>Цель и границы</h2><p>{project.description}</p></section>}{doc.sections.includes('diagrams')&&<section><h2>Архитектура и сценарии</h2>{doc.diagram_ids.map(id=>data.diagrams.find(d=>d.id===id)).filter((d):d is Diagram=>!!d).map(d=><section key={d.id}><h3>{d.title} · {notationNames[d.notation]}</h3><p>{statusNames[d.status]}</p><p>Область: {d.scope}</p><DiagramView diagram={d}/><p>Легенда: {d.legend}</p><p>{d.explanation}</p><p>Файлы: {d.related_paths.join(', ')}</p></section>)}</section>}{doc.sections.includes('files')&&<section><h2>Описания файлов</h2>{data.files.map(f=><section key={f.path}><h3>{f.path}</h3><p>{f.status?statusNames[f.status]:'Нет описания'}</p><p>{f.description?.summary}</p><h4>Зачем нужен</h4><p>{f.description?.purpose}</p><h4>Как работает</h4><ol>{f.description?.workflow.map((step,i)=><li key={i}>{step}</li>)}</ol></section>)}</section>}{doc.sections.includes('decisions')&&<section><h2>Решения</h2><p>Решения и причины изменений находятся в журнале проекта. В этой карте они не опубликованы отдельными ADR.</p></section>}{doc.sections.includes('verification')&&<section><h2>Проверки и ограничения</h2><p>Статусы отражают проверку автора. Изменения репозитория после снимка не проверены; наличие evidence само по себе не доказывает независимую проверку.</p></section>}</article></div></>}
    {!historical&&<details className="map-import"><summary>Публикация снимка · MCP или JSON</summary><p>Агент читает исходники в своей среде и вызывает <code>get_project_map</code> / <code>publish_project_map</code>. Для ручного импорта вставьте JSON с source_revision, files и необязательными diagrams. Файлы требуют SHA-256; описание: title, summary, purpose, workflow, related_paths. Нотации: c4_context, c4_containers, c4_components, sequence, state, erd, flowchart. Причина и текущая версия передаются отдельно.</p><label>Снимок JSON<textarea aria-label="Снимок JSON" value={importText} onChange={e=>setImportText(e.target.value)} maxLength={2000000} rows={8}/></label><label>Причина публикации<input value={reason} onChange={e=>setReason(e.target.value)} maxLength={4000}/></label><button className="button secondary" disabled={busy||dirty||!reason.trim()||!importText.trim()} onClick={()=>{try{const parsed=JSON.parse(importText);if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('Нужен JSON-объект снимка');mutate('',{source_revision:parsed.source_revision,files:parsed.files,...(Object.hasOwn(parsed,'diagrams')?{diagrams:parsed.diagrams}:{})},'PUT');}catch(e){setError((e as Error).message);}}}>Опубликовать снимок</button></details>}
  </section>;
}
