import { ArrowDown, ArrowUp, ChevronsUp, Minus } from 'lucide-react';
import { priorities, type Priority } from './api';

export default function PriorityMark({priority, label = false}: {priority:Priority;label?:boolean}) {
  const Icon = {urgent:ChevronsUp,high:ArrowUp,medium:Minus,low:ArrowDown}[priority];
  return <span className={`priority-mark ${priority}`} title={`Приоритет: ${priorities[priority]}`}>
    <Icon size={15} strokeWidth={2} aria-hidden="true"/>
    <span className={label ? undefined : 'sr-only'}>{priorities[priority]}</span>
  </span>;
}
