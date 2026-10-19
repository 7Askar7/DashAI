import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Check,ExternalLink,Link2,Pause,Plug,RefreshCw,Unplug} from 'lucide-react';
import {api,ApiError,date,type Project} from './api';
import './project-settings.css';

type Provider='confluence'|'jira';
type Connection={id:string;provider:Provider;url:string;deployment:'cloud'|'data_center';root_title:string;root_id:string;project_key?:string;enabled:boolean;auto_sync:boolean;version:number;verified_at:string;credential_present:boolean;counts:Record<string,number>;errors:{local_id:string;status:string;error:string;paused?:boolean}[];issue_type_id?:string;issue_types?:{id:string;name:string}[]};
type Props={project:Project;notify:(message:string)=>void;onDirtyChange:(dirty:boolean)=>void};
const names={confluence:'Confluence',jira:'Jira'};
const statuses:Record<string,string>={pending:'В очереди',processing:'Отправляется',failed:'Не отправлено',uncertain:'Нужна проверка',synced:'Синхронизировано',removed:'Снято с синхронизации'};

export default function ProjectIntegrations({project,notify,onDirtyChange}:Props) {
  const [connections,setConnections]=useState<Connection[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true),[dirty,setDirty]=useState<Record<string,boolean>>({});
  const sequence=useRef(0),root=`/projects/${project.id}/integrations`;
  const hasDirty=Object.values(dirty).some(Boolean);
  async function load(){const current=++sequence.current;try{const data=await api<{integrations:Connection[]}>(root);if(current===sequence.current){setConnections(data.integrations);setError('');}}catch(error){if(current===sequence.current)setError((error as Error).message);}finally{if(current===sequence.current)setLoading(false);}}
  useEffect(()=>{void load();const timer=setInterval(()=>{if(!document.hidden)void load();},5000);return()=>{++sequence.current;clearInterval(timer);};},[project.id]);
  useEffect(()=>{onDirtyChange(hasDirty);return()=>onDirtyChange(false);},[hasDirty,onDirtyChange]);
  useEffect(()=>{if(!hasDirty)return;const leave=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};window.addEventListener('beforeunload',leave);return()=>window.removeEventListener('beforeunload',leave);},[hasDirty]);
  return <section className="project-integrations" aria-label="Интеграции проекта">
    <div className="settings-heading"><div><h2>Публикация знаний проекта</h2><p>Личные подключения для «{project.name}». После подключения изменения описаний, схем и включённых документов отправляются в выбранное место.</p></div><button className="button secondary" onClick={()=>void load()} disabled={loading}><RefreshCw size={16}/>Обновить статус</button></div>
    <div className="integration-scope"><Link2 size={20} aria-hidden="true"/><p><strong>Граница записи закрепляется при подключении.</strong> Confluence получает дочерние страницы выбранного корня. Jira получает задачи выбранного проекта. Внешние проекты, пространства и родительские страницы не создаются.</p></div>
    {error&&<div className="settings-error" role="alert">{error}</div>}
    {loading?<p className="muted" role="status">Загрузка подключений…</p>:<div className="integration-list">{(['confluence','jira'] as const).map(provider=><ConnectionForm key={provider} provider={provider} connection={connections.find(item=>item.provider===provider)} root={root} onRefresh={load} notify={notify} onDirty={value=>setDirty(previous=>({...previous,[provider]:value}))}/>)}</div>}
    <p className="scope-note">Синхронизация односторонняя: DashAI → внешний сервис. Отключение сохраняет созданные страницы и задачи. Изменённые вручную удалённые документы требуют вашего решения перед перезаписью. Mermaid передаётся как исходник схемы; отображение зависит от возможностей внешнего сервиса.</p>
  </section>;
}

function ConnectionForm({provider,connection,root,onRefresh,notify,onDirty}:{provider:Provider;connection?:Connection;root:string;onRefresh:()=>Promise<void>;notify:(message:string)=>void;onDirty:(value:boolean)=>void}) {
  const [deployment,setDeployment]=useState<'cloud'|'data_center'>(connection?.deployment||'cloud'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[editing,setEditing]=useState(!connection),[personal,setPersonal]=useState(false),[dirty,setDirty]=useState(false);
  const formRef=useRef<HTMLFormElement>(null),name=names[provider];
  function markDirty(value:boolean){setDirty(value);onDirty(value);}
  function closeSettings(){
    if(busy||dirty&&!window.confirm('Закрыть настройки без сохранения?'))return;
    formRef.current?.reset();setPersonal(false);setEditing(false);markDirty(false);
  }
  async function mutate(action:string,body:Record<string,unknown>,method='POST'){
    setBusy(true);setError('');
    try {await api(`${root}/${provider}${action}`,{method,body:JSON.stringify({expected_version:connection?.version||0,...body})});await onRefresh();return true;}
    catch(error){setError((error as Error).message);if(error instanceof ApiError&&error.status===409)await onRefresh();return false;}
    finally{setBusy(false);}
  }
  async function connect(event:FormEvent<HTMLFormElement>){
    event.preventDefault();const values=new FormData(event.currentTarget);
    const ok=await mutate('',{url:String(values.get('url')).trim(),deployment,email:String(values.get('email')||'').trim(),token:String(values.get('token')||''),personal_cloud_token:deployment==='cloud'&&personal,enabled:true,auto_sync:values.has('auto_sync'),...(values.get('issue_type_id')?{issue_type_id:String(values.get('issue_type_id'))}:{}),reason:'Личное подключение и разрешение публикации знаний только в выбранный корень'},'PUT');
    if(ok){formRef.current?.reset();setPersonal(false);setEditing(false);markDirty(false);notify(`${name}: корень проверен, синхронизация поставлена в очередь`);}
  }
  async function disconnect(){if(busy||!connection||!window.confirm(`Отключить ${name}? Созданные страницы и задачи останутся во внешнем сервисе.${dirty?' Несохранённые настройки будут потеряны.':''}`))return;
    if(await mutate('/disconnect',{reason:'Отключение отправки знаний и удаление локального токена'})){formRef.current?.reset();setPersonal(false);setEditing(false);markDirty(false);notify(`${name} отключён`);}}
  const count=connection?.counts||{},pending=(count.pending||0)+(count.processing||0);
  return <article className="integration-row">
    <div className="integration-title"><Plug size={22} aria-hidden="true"/><div><h3>{name}</h3><p>{provider==='confluence'?'Страницы с описаниями и архитектурой':'Документационные задачи внутри проекта'}</p></div><span className={`integration-state ${connection?.enabled?'verified':''}`}>{connection?.enabled?<Check size={14}/>:<Pause size={14}/>} {connection?.enabled?'Корень проверен':connection?'Отключено':'Не подключено'}</span></div>
    {connection&&<div className="integration-target"><strong>{connection.root_title} {connection.project_key&&`· ${connection.project_key}`}</strong><a href={connection.url} target="_blank" rel="noreferrer">Открыть выбранный корень <ExternalLink size={13}/></a><small>Проверка доступа: {date(connection.verified_at,true)} · {connection.deployment==='cloud'?'Cloud':'Data Center'}</small></div>}
    {connection?.enabled&&<><div className="integration-counts" role="status"><span><strong>{count.synced||0}</strong> синхронизировано</span><span><strong>{pending}</strong> в очереди</span>{!!count.failed&&<span className="integration-attention">{count.failed} с ошибкой</span>}{!!count.uncertain&&<span className="integration-attention">{count.uncertain} требуют проверки</span>}<span className="muted">{connection.auto_sync?'Автоматическая публикация включена':'Автоматическая публикация выключена'}</span></div>
      <div className="integration-actions"><button className="button secondary" disabled={busy} onClick={async()=>{if(await mutate('/sync',{reason:'Ручная синхронизация текущих знаний проекта'}))notify(`${name}: проверка изменений поставлена в очередь`);}}><RefreshCw size={15}/>Синхронизировать</button><button className="button secondary" disabled={busy} onClick={()=>editing?closeSettings():setEditing(true)}>Настройки</button><button className="text-button" disabled={busy} onClick={()=>void disconnect()}><Unplug size={15}/>Отключить</button></div>
    </>}
    {connection&&!connection.enabled&&!editing&&<button className="button secondary" onClick={()=>setEditing(true)}>Подключить снова</button>}
    {connection&&connection.errors.length>0&&<details className="integration-errors"><summary>Проблемы отправки · {connection.errors.length}</summary>{connection.errors.map(item=><div key={item.local_id}><strong>{statuses[item.status]||item.status}</strong><code>{item.local_id}</code><p>{item.error}</p>{item.paused&&<p className="muted">Отправка документа приостановлена. Включите его модуль или верните источник в состав документа, чтобы продолжить синхронизацию.</p>}{item.status==='uncertain'&&!item.paused&&<button className="button secondary" disabled={busy} onClick={async()=>{if(!window.confirm('Вы проверили выбранный внешний проект и убедились, что эта запись не создана? Повторная отправка может создать дубликат, если она уже существует.'))return;if(await mutate('/resolve',{local_id:item.local_id,confirm_remote_absent:true,reason:'Пользователь проверил отсутствие записи во внешнем проекте и разрешил повторное создание'}))notify('Запись поставлена в очередь повторно');}}>Проверил: запись отсутствует</button>}</div>)}<button className="button secondary" disabled={busy} onClick={async()=>{if(!window.confirm('Разрешить обновить связанные документы текущим текстом DashAI, включая изменения, сделанные во внешнем сервисе? Запись останется внутри закреплённого корня.'))return;if(await mutate('/sync',{overwrite_remote:true,reason:'Явное разрешение перезаписать связанные удалённые документы текущей версией DashAI'}))notify('Обновление поставлено в очередь');}}>Разрешить обновление связанных документов</button></details>}
    {error&&<div className="settings-error" role="alert">{error}</div>}
    {editing&&<form ref={formRef} className="integration-form" onSubmit={connect} onChange={()=>markDirty(true)}>
      <div className="integration-fields"><label>Размещение<select value={deployment} disabled={busy||!!connection} onChange={event=>{setDeployment(event.target.value as typeof deployment);setPersonal(false);}}><option value="cloud">Atlassian Cloud</option><option value="data_center">Свой сервер / Data Center</option></select></label>
      <label>Ссылка на {provider==='confluence'?'корневую страницу':'проект Jira'}<input name="url" type="url" disabled={busy} required readOnly={!!connection} defaultValue={connection?.url||''} placeholder={provider==='confluence'?'https://team.atlassian.net/wiki/spaces/DEV/pages/123/Project':'https://team.atlassian.net/jira/software/projects/DEV/boards/1'}/></label>
      {deployment==='cloud'&&<label>Email Atlassian<input name="email" type="email" disabled={busy} required={!connection?.credential_present} autoComplete="username" placeholder={connection?.credential_present?'Сохранён вместе с токеном':'you@company.com'}/></label>}
      <label>{deployment==='cloud'?'Личный API-токен':'Personal Access Token'}<input name="token" type="password" disabled={busy} required={!connection?.credential_present} autoComplete="new-password" maxLength={4096} placeholder={connection?.credential_present?'Оставьте пустым, чтобы сохранить текущий':'Хранится только на этом компьютере'}/></label>
      {provider==='jira'&&!!connection?.issue_types?.length&&<label>Тип документационной задачи<select name="issue_type_id" disabled={busy} defaultValue={connection.issue_type_id}>{connection.issue_types.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      </div>
      {deployment==='cloud'&&<label className="integration-check"><input type="checkbox" disabled={busy} checked={personal} onChange={event=>setPersonal(event.target.checked)} required/><span>Личное подключение моего аккаунта на этом компьютере. Разрешаю использовать мой токен для выбранного проекта.</span></label>}
      {provider==='jira'&&<p className="scope-note">Для ограничения прав на стороне Jira используйте отдельный аккаунт с доступом только к выбранному проекту и выдайте токен этому аккаунту.</p>}
      <label className="integration-check"><input name="auto_sync" type="checkbox" disabled={busy} defaultChecked={connection?.auto_sync??true}/><span>Автоматически публиковать изменения описаний, схем и включённых документов проекта</span></label>
      <p className="muted">{connection?'Корень закреплён. Его нельзя заменить ссылкой на другой проект.':'Сначала проверим доступ и закрепим корень. Созданные документы будут только внутри него.'} Токен не попадает в историю проекта и экспорт.</p>
      <div className="integration-actions"><button className="button primary" disabled={busy||(deployment==='cloud'&&!personal)}>{busy?'Проверяем доступ…':'Проверить и подключить'}</button>{connection&&<button type="button" className="button secondary" disabled={busy} onClick={closeSettings}>Отмена</button>}</div>
    </form>}
  </article>;
}
