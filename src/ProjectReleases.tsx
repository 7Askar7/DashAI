import {useEffect, useRef, useState, type FormEvent} from 'react';
import {ArrowLeft, ExternalLink, Pencil, Plus, RefreshCw, Save, Search, Tag, X} from 'lucide-react';
import {api, ApiError, type Project, type ProjectRelease, type ReleaseStatus, type ReleaseSummary} from './api';
import './project-releases.css';

const statuses:Record<ReleaseStatus,string>={draft:'Черновик',released:'Выпущена',rolled_back:'Откачена'};
type Draft=Pick<ProjectRelease,'version_name'|'title'|'status'|'environment'|'released_at'|'changelog'|'link'|'source_revision'>;
type Page={releases:ReleaseSummary[];total:number;has_more:boolean};
type Props={project:Project;notify:(message:string)=>void;onDirtyChange:(dirty:boolean)=>void};
const initial:Draft={version_name:'',title:'',status:'draft',environment:'production',released_at:null,changelog:'',link:'',source_revision:''};
const dateLabel=(value:string|null)=>value?new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T00:00:00Z')):'Дата не указана';

export default function ProjectReleases({project,notify,onDirtyChange}:Props) {
  const root=`/projects/${project.id}/releases`;
  const [items,setItems]=useState<ReleaseSummary[]>([]),[total,setTotal]=useState(0),[more,setMore]=useState(false),[offset,setOffset]=useState(0);
  const [query,setQuery]=useState(''),[filter,setFilter]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [detail,setDetail]=useState<ProjectRelease|null>(null),[draft,setDraft]=useState<Draft|null>(null),[reason,setReason]=useState(''),[dirty,setDirty]=useState(false),[conflict,setConflict]=useState(false);
  const sequence=useRef(0),detailSequence=useRef(0),saveKey=useRef(crypto.randomUUID()),heading=useRef<HTMLHeadingElement>(null);
  async function load(start=offset) {
    const current=++sequence.current;setLoading(true);
    try {
      const params=new URLSearchParams({offset:String(start),limit:'30',q:query,...(filter?{status:filter}:{})});
      const data=await api<Page>(`${root}?${params}`);
      if(current!==sequence.current)return;
      setItems(data.releases);setTotal(data.total);setMore(data.has_more);setOffset(start);
    } catch(error){if(current===sequence.current)setError((error as Error).message);}
    finally{if(current===sequence.current)setLoading(false);}
  }
  useEffect(()=>{const timer=setTimeout(()=>void load(0),200);return()=>{clearTimeout(timer);++sequence.current;};},[project.id,query,filter]);
  useEffect(()=>{onDirtyChange(dirty);return()=>onDirtyChange(false);},[dirty,onDirtyChange]);
  useEffect(()=>{if(!dirty)return;const leave=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};window.addEventListener('beforeunload',leave);return()=>window.removeEventListener('beforeunload',leave);},[dirty]);
  function canLeave(){return !busy&&(!dirty||window.confirm('В записи о версии есть несохранённые изменения. Закрыть без сохранения?'));}
  function focusDetail(){setTimeout(()=>{heading.current?.focus();heading.current?.scrollIntoView({block:'nearest'});},0);}
  async function open(id:string) {
    if(!canLeave())return;
    const current=++detailSequence.current;setBusy(true);setError('');
    try {const value=await api<ProjectRelease>(`${root}/${id}`);if(current!==detailSequence.current)return;const {changelog,...summary}=value;setItems(previous=>previous.map(item=>item.id===value.id?{...summary,changelog_preview:changelog.slice(0,300)}:item));setDetail(value);setDraft(null);setDirty(false);setConflict(false);focusDetail();}
    catch(error){setError((error as Error).message);}finally{if(current===detailSequence.current)setBusy(false);}
  }
  function create(){if(!canLeave())return;setDetail(null);setDraft({...initial});setReason('Запись новой версии проекта');setDirty(true);setConflict(false);setError('');saveKey.current=crypto.randomUUID();focusDetail();}
  function edit(){if(!detail)return;setDraft({...detail});setReason('');setDirty(false);setConflict(false);saveKey.current=crypto.randomUUID();focusDetail();}
  function change<K extends keyof Draft>(key:K,value:Draft[K]){setDraft(current=>current?{...current,[key]:value}:current);setDirty(true);saveKey.current=crypto.randomUUID();}
  async function save(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();if(!draft||busy||conflict)return;setBusy(true);setError('');
    const fields={version_name:draft.version_name.trim(),title:draft.title.trim(),status:draft.status,environment:draft.environment.trim(),released_at:draft.released_at||null,changelog:draft.changelog,link:draft.link.trim(),source_revision:draft.source_revision.trim()};
    try {
      const saved=await api<ProjectRelease>(detail?`${root}/${detail.id}`:root,{method:detail?'PATCH':'POST',body:JSON.stringify({... (detail?{expected_version:detail.version,changes:fields}:fields),reason:reason.trim(),idempotency_key:saveKey.current})});
      setDetail(saved);setDraft(null);setDirty(false);setConflict(false);setQuery('');setFilter('');await load(0);notify('Запись о версии сохранена');focusDetail();
    }catch(error){setError((error as Error).message);if(error instanceof ApiError&&error.status===409)setConflict(true);}
    finally{setBusy(false);}
  }
  return <section className="project-releases" aria-label="Версии проекта">
    <div className="settings-heading"><div><h2>Версии проекта</h2><p>Что изменилось в каждом выпуске «{project.name}». Укажите, когда и в какое окружение выложили версию.</p></div><button className="button primary" onClick={create} disabled={busy}><Plus size={16}/>Добавить версию</button></div>
    {error&&<div className="settings-error" role="alert"><span>{error}</span>{conflict&&detail?<button className="button secondary" onClick={()=>void open(detail.id)} disabled={busy}>Перечитать запись</button>:<button className="button secondary" onClick={()=>{setError('');void load();}} disabled={busy}>Повторить загрузку</button>}</div>}
    <div className="release-toolbar"><label className="field release-search"><span className="sr-only">Найти версию</span><div><Search size={16} aria-hidden="true"/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Версия, изменение или окружение…" maxLength={200}/></div></label><label className="field"><span className="sr-only">Статус версии</span><select aria-label="Статус версии" value={filter} onChange={event=>setFilter(event.target.value)}><option value="">Все статусы</option>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><span className="muted" aria-live="polite">Записей: {total}</span><button className="icon-button" aria-label="Обновить версии" onClick={()=>void load()} disabled={loading}><RefreshCw size={16}/></button></div>
    <div className={`release-layout ${draft||detail?'has-detail':''}`}>
      <div className="release-history" aria-label="История версий" aria-busy={loading}>
        {loading?<p className="muted" role="status">Загрузка версий…</p>:items.length?items.map(item=><button key={item.id} className={`release-row ${detail?.id===item.id?'selected':''}`} onClick={()=>void open(item.id)} disabled={busy} aria-pressed={detail?.id===item.id}>
          <span className="release-row-top"><strong><Tag size={15} aria-hidden="true"/>{item.version_name}</strong><span className={`release-status ${item.status}`}>{statuses[item.status]}</span></span>
          {item.title&&<span className="release-title">{item.title}</span>}<span className="release-meta">{item.environment} · {dateLabel(item.released_at)}</span><span className="release-preview">{item.changelog_preview}</span>
        </button>):<div className="module-empty"><h3>{query||filter?'Подходящих версий нет':'Журнал релизов пока пуст'}</h3><p>{query||filter?'Измените запрос или сбросьте фильтры.':'Добавьте первую запись: номер выпуска, изменения и дату выхода в прод.'}</p>{query||filter?<button className="button secondary" onClick={()=>{setQuery('');setFilter('');}}>Сбросить фильтры</button>:<button className="button secondary" onClick={create} disabled={busy}>Добавить первую версию</button>}</div>}
        {(offset>0||more)&&<div className="release-pagination"><button className="button secondary" disabled={loading||offset===0} onClick={()=>void load(Math.max(0,offset-30))}>Назад</button><span className="muted">{offset+1}–{Math.min(offset+30,total)} из {total}</span><button className="button secondary" disabled={loading||!more} onClick={()=>void load(offset+30)}>Далее</button></div>}
      </div>
      {(draft||detail)&&<div className="release-detail">
        <div className="release-detail-heading"><h3 ref={heading} tabIndex={-1}>{draft?(detail?'Редактирование версии':'Новая версия'):detail?.version_name}</h3><button className="icon-button" aria-label="Закрыть запись о версии" onClick={()=>{if(canLeave()){setDraft(null);setDetail(null);setDirty(false);setError('');}}} disabled={busy}><X size={18}/></button></div>
        {draft?<form className="release-form" onSubmit={save}><fieldset disabled={busy}>
          <div className="form-row"><label className="field"><span>Номер версии</span><input autoFocus required maxLength={100} value={draft.version_name} onChange={event=>change('version_name',event.target.value)} placeholder="Например, 2.4.0"/></label><label className="field"><span>Окружение</span><input required maxLength={100} value={draft.environment} onChange={event=>change('environment',event.target.value)} list="release-environments"/><datalist id="release-environments"><option value="production"/><option value="staging"/><option value="development"/></datalist></label></div>
          <label className="field"><span>Название выпуска</span><input maxLength={200} value={draft.title} onChange={event=>change('title',event.target.value)} placeholder="Коротко о главном изменении"/></label>
          <div className="form-row"><label className="field"><span>Состояние</span><select value={draft.status} onChange={event=>change('status',event.target.value as ReleaseStatus)}>{Object.entries(statuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label className="field"><span>Дата выпуска{draft.status==='draft'?' · необязательно':''}</span><input type="date" required={draft.status!=='draft'} value={draft.released_at||''} onChange={event=>change('released_at',event.target.value||null)}/></label></div>
          <label className="field"><span>Что сделали</span><textarea required maxLength={50000} rows={9} value={draft.changelog} onChange={event=>change('changelog',event.target.value)} placeholder="Новые возможности, исправления, изменения для пользователей…"/></label>
          <div className="form-row"><label className="field"><span>Commit или tag · необязательно</span><input maxLength={200} value={draft.source_revision} onChange={event=>change('source_revision',event.target.value)}/></label><label className="field"><span>Ссылка на выпуск · необязательно</span><input type="url" maxLength={2000} value={draft.link} onChange={event=>change('link',event.target.value)} placeholder="https://…"/></label></div>
          <label className="field"><span>Комментарий к записи</span><input required maxLength={4000} value={reason} onChange={event=>{setReason(event.target.value);setDirty(true);saveKey.current=crypto.randomUUID();}} placeholder="Почему добавляем или исправляем эту запись"/></label>
          <div className="release-form-actions"><button className="button secondary" type="button" onClick={()=>{if(canLeave()){setDraft(null);setDirty(false);setConflict(false);setError('');}}}><ArrowLeft size={15}/>Отмена</button><button className="button primary" disabled={busy||conflict||!dirty||!reason.trim()}><Save size={15}/>{busy?'Сохранение…':'Сохранить версию'}</button></div>
        </fieldset></form>:detail&&<article className="release-document"><div className="release-document-meta"><span className={`release-status ${detail.status}`}>{statuses[detail.status]}</span><span>{detail.environment}</span><time dateTime={detail.released_at||undefined}>{dateLabel(detail.released_at)}</time></div>{detail.title&&<h4>{detail.title}</h4>}<p className="release-changelog">{detail.changelog}</p>{detail.source_revision&&<p className="release-source">Commit / tag: <code>{detail.source_revision}</code></p>}{detail.link&&<a href={detail.link} target="_blank" rel="noopener noreferrer">Открыть выпуск<ExternalLink size={14}/></a>}<div className="release-document-footer"><span className="muted">Редакция записи {detail.version}</span><button className="button secondary" onClick={edit} disabled={busy}><Pencil size={15}/>Изменить запись</button></div></article>}
      </div>}
    </div>
  </section>;
}
