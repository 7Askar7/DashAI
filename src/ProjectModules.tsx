import {useEffect,useState,type FormEvent} from 'react';
import {ArrowRight,Blocks,Check,FileText,Plus,Save,X} from 'lucide-react';
import {api,ApiError,type Project,type ProjectModule} from './api';
import './project-settings.css';

type Props={project:Project;notify:(message:string)=>void;onChanged:()=>void;onDirtyChange:(dirty:boolean)=>void;onOpen:(view:string)=>void};

export default function ProjectModules({project,notify,onChanged,onDirtyChange,onOpen}:Props) {
  const [items,setItems]=useState<ProjectModule[]>([]),[selected,setSelected]=useState(''),[content,setContent]=useState(''),[reason,setReason]=useState('Обновление документа проекта');
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[catalog,setCatalog]=useState(false),[query,setQuery]=useState(''),[creating,setCreating]=useState(false);
  const [templateDirty,setTemplateDirty]=useState(false);
  const hasDirty=dirty||templateDirty;
  const active=items.find(item=>item.id===selected);
  const root=`/projects/${project.id}/modules`;
  async function load(preserveError=false) {
    if(!preserveError)setError('');
    try {const data=await api<{modules:ProjectModule[]}>(root);setItems(data.modules);}
    catch(error){setError((error as Error).message);}finally{setLoading(false);}
  }
  useEffect(()=>{void load();},[project.id]);
  useEffect(()=>{onDirtyChange(hasDirty);return()=>onDirtyChange(false);},[hasDirty,onDirtyChange]);
  useEffect(()=>{if(!hasDirty)return;const leave=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};window.addEventListener('beforeunload',leave);return()=>window.removeEventListener('beforeunload',leave);},[hasDirty]);
  function choose(item:ProjectModule) {
    if(dirty&&!window.confirm('В модуле есть несохранённый текст. Перейти без сохранения?'))return;
    setSelected(item.id);setContent(item.content);setDirty(false);setError('');
  }
  async function update(item:ProjectModule,enabled:boolean,nextContent?:string) {
    setBusy(true);setError('');
    try {
      const saved=await api<ProjectModule>(`${root}/${item.id}`,{method:'PUT',body:JSON.stringify({expected_version:item.version,enabled,...(nextContent===undefined?{}:{content:nextContent}),reason:nextContent===undefined?(enabled?'Добавление модуля в проект':'Отключение модуля с сохранением данных'):reason,idempotency_key:crypto.randomUUID()})});
      setItems(previous=>previous.map(value=>value.id===item.id?saved:value));
      if(nextContent!==undefined){setContent(saved.content);setDirty(false);}
      if(!enabled&&selected===item.id){setSelected('');setDirty(false);}
      onChanged();notify(nextContent!==undefined?'Текст модуля сохранён':enabled?'Модуль добавлен в проект':'Модуль отключён. Данные сохранены.');
    }catch(error){setError((error as Error).message);if(error instanceof ApiError&&error.status===409)await load(true);}
    finally{setBusy(false);}
  }
  async function create(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();if(busy||dirty)return;const form=new FormData(event.currentTarget);setBusy(true);setError('');
    try {
      const item=await api<ProjectModule>('/modules',{method:'POST',body:JSON.stringify({name:String(form.get('name')).trim(),description:String(form.get('description')).trim(),template:String(form.get('template')),reason:'Создание повторно используемого документного модуля',idempotency_key:crypto.randomUUID()})});
      setCreating(false);setTemplateDirty(false);setCatalog(true);setQuery('');await load();setSelected(item.id);setContent(item.template||'');setDirty(false);notify('Шаблон создан. Добавьте его в нужные проекты.');
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  const visible=items.filter(item=>(catalog||item.enabled)&&`${item.name} ${item.description}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return <section className="project-modules" aria-label="Модули проекта">
    <div className="settings-heading"><div><h2>Модули проекта</h2><p>Выберите нужные возможности для «{project.name}». Отключённые модули сохраняют свои данные.</p></div><button className="button secondary" onClick={()=>{if(templateDirty&&!window.confirm('Закрыть шаблон без сохранения?'))return;setCreating(!creating);setTemplateDirty(false);}} disabled={busy||dirty}>{creating?<X size={16}/>:<Plus size={16}/>}Свой модуль</button></div>
    {error&&<div className="settings-error" role="alert">{error}<button className="button secondary" onClick={()=>void load()} disabled={busy}>Перечитать модули</button></div>}
    {creating&&<form className="module-create" onSubmit={create} onChange={()=>setTemplateDirty(true)}>
      <h3>Повторно используемый шаблон</h3><p>Например, требования к API или чек-лист выпуска. Каждый проект получит собственный текст.</p>
      <label>Название<input name="name" disabled={busy} required maxLength={100} placeholder="Например, Чек-лист выпуска"/></label>
      <label>Назначение<input name="description" disabled={busy} maxLength={3000}/></label>
      <label>Начальный текст<textarea name="template" disabled={busy} rows={6} maxLength={100000} placeholder="Разделы и вопросы, которые нужно заполнить"/></label>
      <button className="button primary" disabled={busy||dirty}>Создать шаблон</button>
    </form>}
    <div className="module-toolbar"><div className="segmented" role="group" aria-label="Показать модули"><button aria-pressed={!catalog} onClick={()=>setCatalog(false)}>В проекте · {items.filter(item=>item.enabled).length}</button><button aria-pressed={catalog} onClick={()=>setCatalog(true)}>Каталог · {items.length}</button></div><label className="module-search"><span className="sr-only">Найти модуль</span><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Найти модуль…"/></label></div>
    {loading?<p className="muted" role="status">Загрузка модулей…</p>:<div className={`module-layout ${active?.kind==='document'?'with-editor':''}`}>
      <div className="module-list">{visible.map(item=><article key={item.id} className={`module-row ${selected===item.id?'selected':''}`}>
        {item.kind==='document'?<FileText size={19} aria-hidden="true"/>:<Blocks size={19} aria-hidden="true"/>}
        <div className="module-info"><h3><button onClick={()=>item.kind==='document'?choose(item):item.enabled&&onOpen(item.id)} disabled={busy||(item.kind==='feature'&&!item.enabled)}>{item.name}{item.enabled&&<Check size={14} aria-hidden="true"/>}</button></h3><p>{item.description}</p></div>
        <div className="module-actions">{item.enabled&&item.kind==='feature'&&<button className="icon-button" aria-label={`Открыть ${item.name}`} onClick={()=>onOpen(item.id)}><ArrowRight size={16}/></button>}<button className="button secondary" disabled={busy} onClick={()=>{if(dirty&&selected===item.id&&!window.confirm('Отключить модуль и потерять несохранённый текст?'))return;void update(item,!item.enabled);}}>{item.enabled?'Убрать':'Добавить'}</button></div>
      </article>)}{!visible.length&&<div className="module-empty"><h3>{query?'Модуль не найден':'Проекту пока не добавлены модули'}</h3><p>{query?'Измените запрос или создайте собственный шаблон.':'Откройте каталог и выберите нужные возможности.'}</p>{!catalog&&<button className="button secondary" onClick={()=>setCatalog(true)}>Открыть каталог</button>}</div>}</div>
      {active?.kind==='document'&&<form className="module-editor" onSubmit={event=>{event.preventDefault();void update(active,true,content);}}>
        <div className="module-editor-title"><h3>{active.name}</h3><span className="muted">{dirty?'Есть несохранённые изменения':active.enabled?'Сохранено в проекте':'Шаблон · ещё не добавлен'}</span></div>
        <label>Текст документа<textarea disabled={busy} value={content} onChange={event=>{setContent(event.target.value);setDirty(true);}} maxLength={200000} rows={20} spellCheck placeholder="Опишите контекст, решения и проверки…"/></label>
        <label>Комментарий к правке<input disabled={busy} value={reason} onChange={event=>setReason(event.target.value)} required maxLength={4000}/></label>
        <div className="module-editor-footer"><span className="muted">Обычный текст и Markdown. Версия {active.version}.</span><button className="button primary" disabled={busy||!reason.trim()||(!dirty&&active.enabled)}><Save size={16}/>{busy?'Сохранение…':active.enabled?'Сохранить':'Добавить и сохранить'}</button></div>
      </form>}
    </div>}
  </section>;
}
