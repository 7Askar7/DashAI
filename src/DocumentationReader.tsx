import { useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronRight, FileText, Folder, Search, X } from 'lucide-react';
import type { Project, ProjectModule } from './api';
import type { Diagram, DocumentConfig, MapData } from './ProjectMap';
import { renderMarkdown } from './markdown';
import './documentation.css';

export const sectionNames: Record<string, string> = {
  intro: 'Цель и границы', diagrams: 'Архитектура и сценарии', files: 'Описания файлов',
  decisions: 'Решения и дополнительные документы', verification: 'Проверки и ограничения',
};
const statusNames: Record<string, string> = { draft: 'Черновик', stale: 'Требует обновления', reviewed: 'Проверено человеком' };
const PAGE_SIZE = 30;

export function Markdown({text}: {text: string}) {
  const html = useMemo(() => renderMarkdown(text), [text]);
  return <div className="doc-markdown" dangerouslySetInnerHTML={{__html: html}}/>;
}

export default function DocumentationReader({project, data, doc, modules, modulesReady, modulesError, historical, historicalNotice, onConfigure, renderDiagram}: {
  project: Project; data: MapData; doc: DocumentConfig; modules: ProjectModule[];
  modulesReady: boolean; modulesError: string; historical: boolean; historicalNotice: string;
  onConfigure: () => void; renderDiagram: (diagram: Diagram) => ReactNode;
}) {
  const [selected, setSelected] = useState(''), [query, setQuery] = useState(''), [page, setPage] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null), search = useRef<HTMLInputElement>(null);
  const sections = Object.keys(sectionNames).filter(id => doc.sections.includes(id));
  const active = sections.includes(selected) ? selected : sections[0];
  const diagrams = data.diagrams.filter(d => doc.diagram_ids.includes(d.id));
  const searchIndex = useMemo(() => data.files.map(file => ({file, text: [file.path, file.description?.title, file.description?.summary, file.description?.purpose, ...(file.description?.workflow || [])].join(' ').toLocaleLowerCase()})), [data.files]);
  const matches = useMemo(() => {
    const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    return searchIndex.filter(item => words.every(word => item.text.includes(word))).map(item => item.file);
  }, [query, searchIndex]);
  const currentPage = Math.min(page, Math.max(0, Math.ceil(matches.length / PAGE_SIZE) - 1));
  const first = currentPage * PAGE_SIZE;
  const counts: Record<string, number | undefined> = {files: data.files.length, diagrams: diagrams.length, decisions: historical || !modulesReady ? undefined : modules.length};
  function goTo(id: string, focus = true) {
    setSelected(id);
    requestAnimationFrame(() => { if(focus)heading.current?.focus({preventScroll: true}); heading.current?.scrollIntoView({block: 'start'}); });
  }
  function changePage(next: number) {
    setPage(next);
    heading.current?.focus({preventScroll: true});
    heading.current?.scrollIntoView({block: 'start'});
  }
  return <div className="map-document-layout">
    <aside className="doc-sidebar">
      <label className="doc-mobile-select">Содержание<select aria-label="Раздел документа" value={active || ''} onChange={e => goTo(e.target.value, false)}>{sections.length ? sections.map(id => <option key={id} value={id}>{sectionNames[id]}{counts[id] === undefined ? '' : ` · ${counts[id]}`}</option>) : <option value="">Разделы не выбраны</option>}</select></label>
      <nav className="doc-navigation" aria-label="Оглавление документа">
        <h3>Содержание</h3>
        {sections.map(id => <button key={id} type="button" aria-label={sectionNames[id]} aria-current={active === id ? 'page' : undefined} onClick={() => goTo(id)}><span>{sectionNames[id]}</span>{counts[id] !== undefined && <small aria-hidden="true">{counts[id]}</small>}</button>)}
        {!sections.length && <p className="muted">Выберите разделы в настройках состава.</p>}
      </nav>
      <p className="doc-export-note">Экспорт и печать включают все выбранные разделы и файлы.</p>
    </aside>
    <article className="map-document-preview">
      <header className="doc-cover"><h1>{doc.title || 'Документация проекта'}</h1>{doc.context && <Markdown text={doc.context}/>}<p className="map-meta">{project.name} · Версия карты {data.version}{historical ? ' · Исторический снимок' : ''}</p></header>
      <section className="doc-section" key={active} aria-labelledby="doc-section-title">
        <h2 id="doc-section-title" tabIndex={-1} ref={heading}>{sectionNames[active] || 'Состав документа пока пуст'}</h2>
        {!active && <button className="button secondary" onClick={onConfigure}>Выбрать разделы</button>}
        {active === 'intro' && <Markdown text={project.description || 'Описание проекта пока не заполнено.'}/>}
        {active === 'diagrams' && (diagrams.length ? diagrams.map(d => <section className="doc-diagram-section" key={d.id}>
          <h3>{d.title}</h3><p className="map-meta">{statusNames[d.status]}</p><p><strong>Область:</strong> {d.scope}</p>{renderDiagram(d)}
          <h4>Как читать схему</h4><Markdown text={d.legend}/><Markdown text={d.explanation}/>
          {!!d.related_paths.length && <p className="map-path">Файлы: {d.related_paths.join(', ')}</p>}
        </section>) : <div className="doc-empty"><p>{data.diagrams.length ? `В карте есть схемы (${data.diagrams.length}), но в состав документа они пока не включены.` : 'В этом снимке пока нет опубликованных схем.'}</p>{!!data.diagrams.length && !historical && <button className="button secondary" onClick={onConfigure}>Выбрать схемы</button>}</div>)}
        {active === 'files' && <>
          <p className="doc-section-help">Найдите файл по пути или смыслу описания. Раскройте строку, чтобы узнать, зачем он нужен и как работает.</p>
          <label className="map-search doc-file-search"><Search size={17}/><input ref={search} aria-label="Поиск по файлам документа" placeholder="Путь, название или слова из описания" value={query} onChange={e => {setQuery(e.target.value); setPage(0);}} onKeyDown={e => {if(e.key === 'Escape'){setQuery(''); setPage(0);}}}/>{query && <button type="button" aria-label="Очистить поиск по документации" onClick={() => {setQuery(''); setPage(0); search.current?.focus();}}><X size={16}/></button>}</label>
          <p className="doc-result-count" role="status">{matches.length ? `${first + 1}–${Math.min(first + PAGE_SIZE, matches.length)} из ${matches.length}${query.trim() ? ' найденных' : ' файлов и папок'}` : 'Ничего не найдено'}</p>
          <div className="doc-file-list">
            {matches.slice(first, first + PAGE_SIZE).map(file => <details className="doc-file" key={file.path}>
              <summary><ChevronRight className="doc-disclosure" size={16}/>{file.kind === 'directory' ? <Folder size={17}/> : <FileText size={17}/>}<span className="doc-file-label"><strong>{file.path}</strong><span>{file.description?.summary || 'Описание ещё не опубликовано'}</span></span><span className={`doc-status ${file.status || ''}`}>{statusNames[file.status || ''] || 'Нет описания'}</span></summary>
              <div className="doc-file-body">
                {file.status === 'stale' && <p className="map-warning">Файл изменился. Описание относится к предыдущему снимку.</p>}
                {file.description ? <><Markdown text={file.description.summary}/>{file.description.purpose && <><h3>Зачем нужен</h3><Markdown text={file.description.purpose}/></>}{!!file.description.workflow.length && <><h3>Как работает</h3><ol>{file.description.workflow.map((step, i) => <li key={i}>{step}</li>)}</ol></>}{!!file.description.related_paths.length && <><h3>Связанные файлы</h3><ul className="doc-related-paths">{file.description.related_paths.map(path => <li key={path}><code>{path}</code></li>)}</ul></>}</> : <p>В снимке есть путь к файлу, но агент ещё не добавил его описание.</p>}
              </div>
            </details>)}
          </div>
          {!matches.length && <div className="doc-empty"><p>{data.files.length ? 'Попробуйте часть пути или другое слово из описания.' : 'Файлы появятся после публикации карты проекта.'}</p>{query && <button className="button secondary" onClick={() => {setQuery(''); setPage(0); search.current?.focus();}}>Сбросить поиск</button>}</div>}
          {matches.length > PAGE_SIZE && <nav className="doc-pagination" aria-label="Страницы файлов"><button className="button secondary" disabled={!currentPage} onClick={() => changePage(currentPage - 1)} aria-label="Предыдущие файлы">Назад</button><span>Страница {currentPage + 1} из {Math.ceil(matches.length / PAGE_SIZE)}</span><button className="button secondary" disabled={first + PAGE_SIZE >= matches.length} onClick={() => changePage(currentPage + 1)} aria-label="Следующие файлы">Далее</button></nav>}
        </>}
        {active === 'decisions' && (historical ? <p>{historicalNotice}</p> : !modulesReady ? <p role="status">{modulesError ? 'Материалы недоступны до повторной загрузки.' : 'Загрузка дополнительных документов…'}</p> : modules.length ? <><p className="doc-section-help">У этих документов собственные версии: они загружены отдельно от снимка карты.</p>{modules.map(item => <section className="doc-module" key={item.id}><h3>{item.name}</h3><p className="map-meta">Модуль документа · v{item.version}</p><Markdown text={item.content || 'Документ пока не заполнен.'}/></section>)}</> : <div className="doc-empty"><p>Дополнительные документы пока не добавлены.</p><p>Их можно создать во вкладке «Модули». Решения и причины изменений доступны в истории проекта.</p></div>)}
        {active === 'verification' && <><p>Статусы отражают проверку автора. Изменения репозитория после снимка не проверены; наличие evidence само по себе не доказывает независимую проверку.</p><dl className="doc-status-guide"><dt>Черновик</dt><dd>Описание опубликовано, но ещё не подтверждено человеком.</dd><dt>Требует обновления</dt><dd>Файл изменился после публикации описания.</dd><dt>Проверено человеком</dt><dd>Описание сверено с указанным снимком. Это не проверка последующих изменений.</dd></dl><h3>Источник документа</h3><p>{data.source_revision || 'Снимок не опубликован'}</p></>}
      </section>
    </article>
  </div>;
}
