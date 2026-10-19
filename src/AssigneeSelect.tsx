import {useId,useRef,useState} from 'react';
import {Plus} from 'lucide-react';
import {api,type Agent} from './api';
import './assignee-select.css';

type Props={agents:Agent[];name?:string;label?:string;defaultValue?:string;className?:string;disabled?:boolean;onCreated?:(agent:Agent)=>void};

export default function AssigneeSelect({agents,name='assignee_id',label='Исполнитель',defaultValue='',className='',disabled=false,onCreated}:Props) {
  const id=useId(),key=useRef(crypto.randomUUID());
  const [selected,setSelected]=useState(defaultValue),[created,setCreated]=useState<Agent[]>([]);
  const [adding,setAdding]=useState(false),[newName,setNewName]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const items=[...new Map([...agents,...created].map(agent=>[agent.id,agent])).values()];
  async function save() {
    if(busy||disabled||!newName.trim())return;
    const existing=items.find(agent=>agent.name.trim().toLocaleLowerCase()===newName.trim().toLocaleLowerCase());
    if(existing){setSelected(existing.id);setAdding(false);setNewName('');setError('');return;}
    setBusy(true);setError('');
    try {
      const {agent}=await api<{agent:Agent;token:null}>('/agents',{method:'POST',body:JSON.stringify({name:newName.trim(),kind:'custom',issue_token:false,reason:'Добавление исполнителя для назначения задач',idempotency_key:key.current})});
      setCreated(previous=>[...previous,agent]);setSelected(agent.id);setAdding(false);setNewName('');onCreated?.(agent);
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  return <div className={`field assignee-select ${className}`}>
    <label htmlFor={id}>{label}</label>
    <select id={id} name={name} value={selected} onChange={event=>setSelected(event.target.value)} disabled={disabled||busy} aria-describedby={`${id}-hint`}>
      <option value="">Не назначен</option>
      {items.map(agent=><option key={agent.id} value={agent.id}>{agent.name}</option>)}
    </select>
    <small id={`${id}-hint`}>Свой исполнитель сохраняется для всех проектов. Подключение к модели не создаётся.</small>
    {!adding?<button type="button" className="text-button assignee-add" disabled={disabled} onClick={()=>{setAdding(true);setError('');key.current=crypto.randomUUID();}}><Plus size={14} aria-hidden="true"/>Свой исполнитель</button>:<div className="assignee-create" aria-busy={busy}>
      <label className="sr-only" htmlFor={`${id}-new`}>Имя нового исполнителя</label>
      <input id={`${id}-new`} autoFocus value={newName} maxLength={255} disabled={disabled} aria-disabled={busy} aria-describedby={`${id}-hint ${id}-pending`} placeholder="Человек, команда или модель" ref={element=>{element?.setCustomValidity('Сначала сохраните нового исполнителя или нажмите «Отмена».');}} onChange={event=>{if(!busy){setNewName(event.target.value);setError('');key.current=crypto.randomUUID();}}} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();void save();}}}/>
      <div className="assignee-actions"><button type="button" className="button secondary" disabled={disabled||busy||!newName.trim()} onClick={()=>void save()}>{busy?'Сохранение…':'Сохранить исполнителя'}</button><button type="button" className="text-button" disabled={disabled||busy} onClick={()=>{setAdding(false);setNewName('');setError('');}}>Отмена</button></div>
      <small id={`${id}-pending`} role="status">{busy?'Сохраняем исполнителя. Дождитесь завершения.':'Сначала сохраните имя, затем сохраняйте задачу.'}</small>
    </div>}
    {error&&<div className="error-box" role="alert">{error}</div>}
  </div>;
}
