import {
  useEffect,
  useCallback,
  useId,
  useRef,
  useState,
  lazy,
  Suspense,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Blocks,
  Check,
  CheckCheck,
  CircleCheck,
  ChevronRight,
  Circle,
  Clock3,
  Clipboard,
  Code2,
  FileCode2,
  FolderKanban,
  GitBranch,
  History,
  LayoutDashboard,
  Link2,
  List,
  Menu,
  PanelTop,
  Pencil,
  Plug,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  ShieldCheck,
  Settings2,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  date,
  statuses,
  priorities,
  taskTypes,
  noteLabels,
  actionLabels,
  subprojectPath,
  inSubproject,
  type Agent,
  type Board,
  type Bootstrap,
  type OverviewData,
  type Connectors,
  type Detail,
  type Event,
  type Project,
  type Subproject,
  type Task,
  type Status,
} from "./api";
import KanbanBoard from "./KanbanBoard";
import PriorityMark from './PriorityMark';
import ProjectModules from './ProjectModules';
import ProjectIntegrations from './ProjectIntegrations';
import ProjectReleases from './ProjectReleases';
import AssigneeSelect from './AssigneeSelect';
import ThemePicker from './ThemePicker';
import './task-review.css';
import './task-workspace.css';
import './overview.css';
import { insideVSCode, hostRequest, writeClipboard } from "./host";
import { defaultProjectWorkspace, isProjectView as projectView, saveWorkspace, taskFromUrl, taskLink, validId, type ProjectWorkspace, type Workspace, type View } from "./workspace";
const ProjectMap = lazy(() => import('./ProjectMap'));

type Modal =
  | { kind: "project"; project?: Project }
  | { kind: "subproject"; subproject?: Subproject; parent_id?: string }
  | { kind: "task"; subproject_id?: string };
const emptyBootstrap: Bootstrap = { projects: [], agents: [], activity: [] };
const text = (data: FormData, key: string) =>
  String(data.get(key) || "").trim();
const agentName = (agents: Agent[], id: string | null) =>
  agents.find((a) => a.id === id)?.name || "Не назначен";
const kindLabel = (kind: string) =>
  kind === "human" ? "Человек" : kind === "claude" ? "Claude Code" : kind === "codex" ? "Codex" : "Другой агент";
const fieldLabels:Record<string,string> = {title:'Название',description:'Описание',rationale:'Зачем',acceptance_criteria:'Критерии готовности',status:'Статус',priority:'Приоритет',task_type:'Тип задачи',subproject_id:'Подпроект',parent_id:'Родительский подпроект',assignee_id:'Исполнитель',section_id:'Раздел',depends_on:'Зависимости',claim_owner_id:'Владелец'};

function Avatar({ agent, small = false }: { agent?: Agent; small?: boolean }) {
  return (
    <span
      className={`avatar ${small ? "small" : ""} ${agent?.kind || "unassigned"}`}
      aria-hidden="true"
    >
      {agent?.kind === "codex" ? (
        <Code2 size={small ? 12 : 15} />
      ) : agent?.kind === "claude" ? (
        <Sparkles size={small ? 12 : 15} />
      ) : agent?.kind === "human" ? (
        "В"
      ) : agent?.kind === 'custom' ? (
        agent.name.slice(0,1).toLocaleUpperCase()
      ) : (
        "—"
      )}
    </span>
  );
}
function StatusPill({ status }: { status: string }) {
  const item = statuses.find((s) => s.value === status);
  return (
    <span className={`status-pill ${status}`}>
      <span className="status-dot" />
      {item?.label || status}
    </span>
  );
}
function useFormDraft(busy: boolean) {
  const form = useRef<HTMLFormElement | null>(null), baseline = useRef("");
  const snapshot = () => form.current ? JSON.stringify(Array.from(form.current.elements)
    .filter((field): field is HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement =>
      field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement)
    .filter(field => field.value && (field.name || field instanceof HTMLInputElement) &&
      (!(field instanceof HTMLInputElement) || !["checkbox", "radio"].includes(field.type) || field.checked))
    .map(field => [field.name || field.id, field.value])) : "";
  const ref = useCallback((node: HTMLFormElement | null) => {
    form.current = node;
    baseline.current = snapshot();
  }, []);
  const isDirty = () => !!form.current && snapshot() !== baseline.current;
  useEffect(() => {
    const leave = (event: BeforeUnloadEvent) => {
      if (busy || isDirty()) { event.preventDefault(); event.returnValue = ""; }
    };
    const check: EventListener = (event) => {
      const state = (event as CustomEvent<{ busy: boolean; dirty: boolean }>).detail;
      state.busy ||= busy;
      state.dirty ||= isDirty();
    };
    window.addEventListener("beforeunload", leave);
    window.addEventListener("dashai:check-navigation", check);
    return () => {
      window.removeEventListener("beforeunload", leave);
      window.removeEventListener("dashai:check-navigation", check);
    };
  }, [busy]);
  return { ref, isDirty, reset: () => { baseline.current = snapshot(); }, form };
}
function Dialog({
  title,
  children,
  onClose,
  drawer = false,
  docked = false,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  drawer?: boolean;
  docked?: boolean;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    label = useId(),
    closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    const media = window.matchMedia("(min-width: 1280px)");
    const present = () => {
      const focused = dialog.contains(document.activeElement) ? document.activeElement as HTMLElement : null;
      if (dialog.open) dialog.close();
      const inline = docked && media.matches;
      dialog.classList.toggle("is-docked", inline);
      dialog.setAttribute("aria-modal", String(!inline));
      if (inline) dialog.show(); else dialog.showModal();
      focused?.focus({ preventScroll: true });
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented && dialog.classList.contains("is-docked") && !document.querySelector("dialog:modal")) {
        event.preventDefault();
        closeRef.current();
      }
    };
    present();
    if (docked) media.addEventListener("change", present);
    window.addEventListener("keydown", escape);
    return () => {
      const restore = dialog.contains(document.activeElement) || document.activeElement === document.body;
      media.removeEventListener("change", present);
      window.removeEventListener("keydown", escape);
      dialog.close();
      if (restore && previous?.isConnected) {
        const collapsed = previous.closest("details:not([open])");
        (collapsed?.querySelector("summary") || previous).focus({ preventScroll: true });
      }
    };
  }, [docked]);
  return (
    <dialog
      ref={ref}
      className={drawer ? "drawer" : "modal"}
      aria-labelledby={label}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) closeRef.current();
      }}
      onClick={(e) => {
        if (!busy && e.target === e.currentTarget && e.currentTarget.matches(":modal")) closeRef.current();
      }}
    >
      <div className="dialog-inner">
        <div className="dialog-head">
          <h2 id={label}>{title}</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Закрыть"
            disabled={busy}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
function Field({
  label,
  name,
  defaultValue = "",
  required = false,
  area = false,
  hint,
}: {
  label: string;
  name: string;
  defaultValue?: string;
  required?: boolean;
  area?: boolean;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required && <span className="required"> *</span>}
      </label>
      {area ? (
        <textarea
          id={id}
          name={name}
          defaultValue={defaultValue}
          required={required}
          rows={3}
          maxLength={20000}
        />
      ) : (
        <input
          id={id}
          name={name}
          defaultValue={defaultValue}
          required={required}
          maxLength={name === "title" || name === "name" ? 240 : 2000}
        />
      )}{" "}
      {hint && <small>{hint}</small>}
    </div>
  );
}
function Select({
  label,
  name,
  children,
  defaultValue = "",
}: {
  label: string;
  name: string;
  children: ReactNode;
  defaultValue?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} name={name} defaultValue={defaultValue}>
        {children}
      </select>
    </div>
  );
}
function ErrorBox({
  message,
  onRefresh,
}: {
  message: string;
  onRefresh?: () => void;
}) {
  return (
    <div className="error-box" role="alert">
      {message}
      {onRefresh && (
        <button type="button" className="text-button" onClick={onRefresh}>
          <RefreshCw size={14} />
          Обновить данные
        </button>
      )}
    </div>
  );
}

function MoveTaskDialog({ task, status, onClose, onOpen, onMoved }: {
  task: Task;
  status: Status;
  onClose: () => void;
  onOpen: () => void;
  onMoved: (updated: Task) => Promise<void>;
}) {
  const [current, setCurrent] = useState(task),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [stale, setStale] = useState(false);
  const key = useRef(crypto.randomUUID());
  const label = (value: Status) => statuses.find((item) => item.value === value)!.label;
  const draft = useFormDraft(busy);
  const canDiscard = () => !busy && (!draft.isDirty() || window.confirm("Причина перемещения не сохранена. Продолжить без сохранения?"));
  async function refreshConflict() {
    setBusy(true);
    try {
      const latest = await api<Detail>(`/tasks/${task.id}`);
      setCurrent(latest.task);
      key.current = crypto.randomUUID();
      setStale(false);
      setError(latest.task.status === status
        ? "Карточка уже находится в выбранной колонке. Закройте окно или откройте задачу."
        : `Данные обновлены до версии ${latest.task.version}. Сейчас: «${label(latest.task.status)}». Причина сохранена; подтвердите перемещение ещё раз.`);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<Task>(`/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ expected_version: current.version, changes: { status },
          reason: text(new FormData(event.currentTarget), "reason"), idempotency_key: key.current }),
      });
      await onMoved(updated);
    } catch (error) {
      setError((error as Error).message);
      setStale(error instanceof ApiError && error.status === 409 && error.message.startsWith("Конфликт изменений."));
    } finally {
      setBusy(false);
    }
  }
  return <Dialog title="Переместить задачу" busy={busy} onClose={() => { if (canDiscard()) onClose(); }}>
    <form ref={draft.ref} className="entity-form" onSubmit={submit} aria-busy={busy}>
      <fieldset className="draft-fields" disabled={busy}>
      <p className="move-task-title"><span>{current.short_id}</span>{current.title}</p>
      <div className="move-summary"><StatusPill status={current.status} /><ArrowRight size={17} aria-hidden="true" /><StatusPill status={status} /></div>
      <Field label="Почему перемещаем задачу" name="reason" area required hint="Причина и смена статуса сохранятся в истории. Карточка переместится после подтверждения." />
      {error && <ErrorBox message={error} onRefresh={stale && !busy ? refreshConflict : undefined} />}
      <div className="form-footer move-footer">
        <button type="button" className="text-button" disabled={busy} onClick={() => { if (canDiscard()) onOpen(); }}>Открыть задачу</button>
        <button type="button" className="button secondary" disabled={busy} onClick={() => { if (canDiscard()) onClose(); }}>Отмена</button>
        <button type="submit" className="button primary" disabled={busy || stale || current.status === status}>{busy ? "Сохраняем…" : "Переместить"}</button>
      </div>
      </fieldset>
    </form>
  </Dialog>;
}

function EntityForm({
  modal,
  board,
  agents,
  onClose,
  onSaved,
}: {
  modal: Modal;
  board: Board | null;
  agents: Agent[];
  onClose: () => void;
  onSaved: (projectId?: string, taskId?: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const key = useRef(crypto.randomUUID());
  const draft = useFormDraft(busy);
  function requestClose() {
    if (!busy && (!draft.isDirty() || window.confirm("В форме есть несохранённые изменения. Закрыть без сохранения?"))) onClose();
  }
  const isProject = modal.kind === "project";
  const isSubproject = modal.kind === "subproject";
  const item = modal.kind === "project" ? modal.project : modal.kind === "subproject" ? modal.subproject : undefined;
  const subprojects = board?.subprojects || [];
  const options = [...subprojects].sort((a, b) => subprojectPath(subprojects, a.id).localeCompare(subprojectPath(subprojects, b.id), "ru"));
  const title = isProject
    ? item
      ? "Изменить проект"
      : "Новый проект"
    : isSubproject ? item ? "Изменить подпроект" : "Новый подпроект" : "Новая задача";
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    const d = new FormData(e.currentTarget),
      reason = text(d, "reason");
    try {
      if (modal.kind === "project") {
        const changes = {
          name: text(d, "name"),
          description: text(d, "description"),
          repository: text(d, "repository"),
          color: text(d, "color"),
        };
        const result = await api<Project>(
          modal.project ? `/projects/${modal.project.id}` : "/projects",
          {
            method: modal.project ? "PATCH" : "POST",
            body: JSON.stringify(
              modal.project
                ? { expected_version: modal.project.version, changes, reason }
                : { ...changes, reason, idempotency_key: key.current },
            ),
          },
        );
        await onSaved(result.id);
      } else if (modal.kind === "subproject") {
        const changes = { title: text(d, "title"), description: text(d, "description"), parent_id: text(d, "parent_id") || null };
        await api<Subproject>(modal.subproject ? `/subprojects/${modal.subproject.id}` : `/projects/${board!.project.id}/subprojects`, {
          method: modal.subproject ? "PATCH" : "POST",
          body: JSON.stringify(modal.subproject
            ? { expected_version: modal.subproject.version, changes, reason, idempotency_key: key.current }
            : { ...changes, reason, idempotency_key: key.current }),
        });
        await onSaved();
      } else {
        const task = await api<Task>("/tasks", {
          method: "POST",
          body: JSON.stringify({
            project_id: board!.project.id,
            task_type: text(d, "task_type"),
            subproject_id: text(d, "subproject_id") || null,
            title: text(d, "title"),
            description: text(d, "description"),
            rationale: text(d, "rationale"),
            acceptance_criteria: text(d, "acceptance_criteria"),
            priority: text(d, "priority"),
            assignee_id: text(d, "assignee_id") || null,
            depends_on: d.getAll("depends_on"),
            reason,
            idempotency_key: key.current,
          }),
        });
        await onSaved(undefined, task.id);
      }
      onClose();
    } catch (e) {
      setError((e as Error).message + (e instanceof ApiError && e.status === 409 && item
        ? " Сохранение не выполнено. Скопируйте нужные правки, закройте форму, обновите доску и откройте объект повторно, чтобы получить актуальную версию."
        : ""));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={title} busy={busy} onClose={requestClose}>
      <form ref={draft.ref} onSubmit={submit} className="entity-form" aria-busy={busy}>
        <fieldset className="draft-fields" disabled={busy}>
        <p className="form-intro">
          {isProject
            ? "Отдельная доска, контекст и история для одного проекта."
            : isSubproject ? "Направление работы внутри проекта. Его задачи останутся на общей доске; можно выбрать родительский подпроект."
            : "Выберите подпроект и тип работы, опишите результат и зачем он нужен. Агент получит этот контекст вместе с задачей."}
        </p>
        {isProject ? (
          <>
            <Field
              label="Название проекта"
              name="name"
              required
              defaultValue={modal.project?.name}
            />
            <Field
              label="Цель проекта"
              name="description"
              area
              defaultValue={modal.project?.description}
            />
            <Field
              label="Репозиторий или путь"
              name="repository"
              defaultValue={modal.project?.repository}
            />
            <Select
              label="Цвет проекта"
              name="color"
              defaultValue={modal.project?.color || "#b4f4a5"}
            >
              {modal.project?.color &&
                !["#b4f4a5", "#80bfff", "#c5a9ff", "#f4c580"].includes(modal.project.color) &&
                <option value={modal.project.color}>{modal.project.color}</option>}
              <option value="#b4f4a5">Мятный</option>
              <option value="#80bfff">Голубой</option>
              <option value="#c5a9ff">Лиловый</option>
              <option value="#f4c580">Песочный</option>
            </Select>
          </>
        ) : modal.kind === "subproject" ? (
          <>
            <Field label="Название подпроекта" name="title" required defaultValue={modal.subproject?.title} />
            <Field label="Цель подпроекта" name="description" area defaultValue={modal.subproject?.description} />
            <Select label="Родительский подпроект" name="parent_id" defaultValue={modal.subproject?.parent_id || modal.parent_id || ""}>
              <option value="">В корне проекта</option>
              {options.filter((s) => !modal.subproject || !inSubproject(subprojects, s.id, modal.subproject.id)).map((s) => <option key={s.id} value={s.id}>{subprojectPath(subprojects, s.id)}</option>)}
            </Select>
          </>
        ) : (
          <>
            <Field label="Название задачи" name="title" required />
            <Select label="Подпроект" name="subproject_id" defaultValue={modal.kind === "task" ? modal.subproject_id || "" : ""}>
              <option value="">Весь проект · без подпроекта</option>
              {options.map((s) => <option key={s.id} value={s.id}>{subprojectPath(subprojects, s.id)}</option>)}
            </Select>
            <Select
              label="Тип задачи"
              name="task_type"
              defaultValue="development"
            >
              {Object.entries(taskTypes).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Field label="Что нужно сделать" name="description" area />
            <Field label="Зачем это нужно" name="rationale" area required />
            <Field
              label="Критерии готовности"
              name="acceptance_criteria"
              area
              hint="Наблюдаемый результат: что должно работать и как это проверить."
            />
            <div className="form-row">
              <Select label="Приоритет" name="priority" defaultValue="medium">
                {Object.entries(priorities).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
              <AssigneeSelect agents={agents} disabled={busy}/>
            </div>
            {board && board.tasks.length > 0 && (
              <details className="dependency-picker">
                <summary>Зависимости задачи</summary>
                <div className="checkbox-list">
                  {board.tasks.map((t) => (
                    <label key={t.id}>
                      <input type="checkbox" name="depends_on" value={t.id} />
                      <span>
                        {t.short_id} · {t.title}
                      </span>
                    </label>
                  ))}
                </div>
              </details>
            )}
          </>
        )}
        <Field
          label="Причина записи в истории"
          name="reason"
          required
          area
          defaultValue={
            item
              ? "Уточнение контекста проекта"
              : isProject
                ? "Создание нового проекта"
                : isSubproject ? "Создание направления работы в проекте" : "Добавление задачи в план проекта"
          }
        />
        {error && <ErrorBox message={error} />}
        <div className="form-footer">
          <button type="button" className="button secondary" onClick={requestClose}>
            Отмена
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Сохраняем…" : item ? "Сохранить изменения" : "Создать"}
            <ArrowRight size={16} />
          </button>
        </div>
        </fieldset>
      </form>
    </Dialog>
  );
}

function Events({
  events,
  agents,
  onTask,
}: {
  events: Event[];
  agents: Agent[];
  onTask?: (id: string) => void;
}) {
  if (!events.length)
    return (
      <div className="empty-small">
        <History size={22} />
        <p>История пока пуста</p>
        <span>Успешные изменения появятся здесь вместе с причиной.</span>
      </div>
    );
  return (
    <div className="timeline">
      {[...events]
        .sort((a, b) => b.id - a.id)
        .map((event) => {
          const changed = Object.keys(event.after || {}).filter(
            (k) =>
              ![
                "updated_at",
                "created_at",
                "version",
                "claim_expires_at",
              ].includes(k) &&
              JSON.stringify(event.before?.[k]) !==
                JSON.stringify(event.after?.[k]),
          );
          return (
            <article className="timeline-event" key={event.id}>
              <div className="timeline-avatar">
                <Avatar agent={agents.find((a) => a.id === event.actor_id)} />
              </div>
              <div className="event-content">
                <div className="event-title">
                  <strong>{event.actor_name}</strong>{" "}
                  <span>{event.action === "section.created" && event.after?.is_default
                    ? "подготовил доску проекта" : actionLabels[event.action] || event.action}</span>
                  {event.task_id && onTask && (
                    <button
                      className="event-link"
                      onClick={() => onTask(event.task_id!)}
                    >
                      {String(
                        event.after?.short_id ||
                          event.before?.short_id ||
                          "Задача",
                      )}
                      <ArrowUpRight size={12} />
                    </button>
                  )}
                </div>
                <p className="event-reason">{event.reason}</p>
                <div className="event-meta">
                  <time
                    dateTime={event.created_at}
                    title={date(event.created_at, true)}
                  >
                    {date(event.created_at, true)} · МСК
                  </time>
                  <span>#{event.id}</span>
                  {event.session_id && (
                    <span title={event.session_id}>
                      Сессия {event.session_id.slice(0, 12)}
                    </span>
                  )}
                </div>
                {changed.length > 0 && (
                  <details className="event-diff">
                    <summary>
                      Изменения <span>{changed.length}</span>
                    </summary>
                    <dl>
                      {changed.map((k) => (
                        <div key={k}>
                          <dt>
                            {(
                              {
                                title: "Название",
                                description: "Описание",
                                rationale: "Зачем",
                                acceptance_criteria: "Критерии",
                                status: "Статус",
                                priority: "Приоритет",
                                task_type: "Тип задачи",
                                subproject_id: "Подпроект",
                                parent_id: "Родительский подпроект",
                                assignee_id: "Исполнитель",
                                section_id: "Раздел",
                                body: "Запись",
                                metadata: "Файлы и проверки",
                                depends_on: "Зависимости",
                                name: "Название",
                                claim_owner_id: "Владелец",
                                version_name: "Номер версии",
                                environment: "Окружение",
                                released_at: "Дата выпуска",
                                changelog: "Изменения выпуска",
                                source_revision: "Commit / tag",
                                link: "Ссылка",
                              } as Record<string, string>
                            )[k] || k}
                          </dt>
                          <dd>
                            {event.before && (
                              <>
                                <span className="before">
                                  {formatValue(k, event.before[k], agents)}
                                </span>
                                <ArrowRight size={12} />
                              </>
                            )}
                            <span>
                              {formatValue(k, event.after?.[k], agents)}
                            </span>
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                )}
              </div>
            </article>
          );
        })}
    </div>
  );
}
function formatValue(key: string, value: unknown, agents: Agent[]) {
  if (value == null || value === "") return "—";
  if (key === "status")
    return statuses.find((s) => s.value === value)?.label || ({draft:'Черновик',released:'Выпущена',rolled_back:'Откачена'} as Record<string,string>)[String(value)] || String(value);
  if (key === "priority")
    return priorities[value as keyof typeof priorities] || String(value);
  if (key === "task_type")
    return taskTypes[value as keyof typeof taskTypes] || String(value);
  if (key === "assignee_id" || key === "claim_owner_id")
    return agentName(agents, String(value));
  return typeof value === "object"
    ? JSON.stringify(value, null, 2)
    : String(value);
}

function TaskDrawer({
  detail,
  board,
  agents,
  onClose,
  onRefresh,
  onChanged,
  onCopyLink,
  docked,
}: {
  detail: Detail;
  board: Board;
  agents: Agent[];
  onClose: () => void;
  onRefresh: () => Promise<Detail | null>;
  onChanged: () => Promise<void>;
  onCopyLink: () => void;
  docked: boolean;
}) {
  const [edit, setEdit] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [noteKind, setNoteKind] = useState("progress");
  const task = detail.task,
    key = useRef(crypto.randomUUID()),
    noteKey = useRef(crypto.randomUUID()),
    editBaseline = useRef(task),
    editButton = useRef<HTMLButtonElement>(null),
    focusAfterEdit = useRef(false);
  const [saveVersion, setSaveVersion] = useState(task.version);
  const editDraft = useFormDraft(busy), noteDraft = useFormDraft(busy);
  const latestEvidenceRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (focusAfterEdit.current && !edit && !busy) {
      focusAfterEdit.current = false;
      editButton.current?.focus();
    }
  }, [edit, busy]);
  function canDiscardDraft() {
    return !busy && (!(editDraft.isDirty() || noteDraft.isDirty()) || window.confirm("Есть несохранённые изменения. Продолжить без сохранения?"));
  }
  function beginEdit() {
    if (!canDiscardDraft()) return;
    editBaseline.current = task;
    setSaveVersion(task.version);
    setError("");
    setEdit(true);
    editButton.current?.focus();
  }
  function finishEdit() {
    focusAfterEdit.current = true;
    setEdit(false);
    setError("");
  }
  function cancelEdit() {
    if (canDiscardDraft()) finishEdit();
  }
  async function refreshConflict() {
    try {
      const latest = await onRefresh();
      if (latest) {
        setSaveVersion(latest.task.version);
        const changes = Object.keys(latest.task).filter(
          (k) =>
            !['version','created_at','updated_at','claim_expires_at'].includes(k) &&
            JSON.stringify(latest.task[k as keyof Task]) !==
            JSON.stringify(editBaseline.current[k as keyof Task]),
        ).map(key=>fieldLabels[key]||key);
        setError(
          `Данные обновлены до версии ${latest.task.version}. Черновик сохранен. Повторное сохранение применит только измененные вами поля. Другой автор изменил: ${changes.join(", ") || "нет изменений"}.`,
        );
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function update(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const d = new FormData(e.currentTarget);
    try {
      const draft = {
        title: text(d, "title"),
        description: text(d, "description"),
        rationale: text(d, "rationale"),
        acceptance_criteria: text(d, "acceptance_criteria"),
        status: text(d, "status"),
        priority: text(d, "priority"),
        assignee_id: text(d, "assignee_id") || null,
        task_type: text(d, "task_type"),
        subproject_id: text(d, "subproject_id") || null,
        depends_on: d.getAll("depends_on"),
      };
      const changes = Object.fromEntries(
        Object.entries(draft).filter(
          ([field, value]) =>
            JSON.stringify(value) !==
            JSON.stringify(editBaseline.current[field as keyof Task]),
        ),
      );
      if (!Object.keys(changes).length) {
        setError("Вы еще не изменили поля задачи.");
        return;
      }
      await api(`/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          expected_version: saveVersion,
          reason: text(d, "reason"),
          idempotency_key: key.current,
          changes,
        }),
      });
      key.current = crypto.randomUUID();
      await onChanged();
      finishEdit();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function note(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const form = e.currentTarget,
      d = new FormData(form);
    const payload =
      noteKind === "change"
        ? {
            summary: text(d, "body"),
            files: text(d, "files")
              .split("\n")
              .map((x) => x.trim())
              .filter(Boolean),
            diff: text(d, "diff"),
            commit: text(d, "commit"),
            verification: text(d, "verification"),
            reason: text(d, "note_reason"),
            idempotency_key: noteKey.current,
          }
        : {
            kind: noteKind,
            body: text(d, "body"),
            reason: text(d, "note_reason"),
            idempotency_key: noteKey.current,
          };
    try {
      await api(
        `/tasks/${task.id}/${noteKind === "change" ? "changes" : "notes"}`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      noteKey.current = crypto.randomUUID();
      form.reset();
      noteDraft.reset();
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const assignee = agents.find((a) => a.id === task.assignee_id);
  const evidence = detail.notes.filter(note => note.kind === "evidence")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const waiting = task.depends_on.filter(id => board.tasks.find(item => item.id === id)?.status !== "done");
  function chooseNoteKind(next: string) {
    if (busy) return false;
    const fields = noteDraft.form.current && new FormData(noteDraft.form.current);
    if (noteKind === "change" && next !== "change" && fields &&
      ["files", "diff", "commit", "verification"].some(name => text(fields, name)) &&
      !window.confirm("При смене типа записи несохранённые файлы, diff, commit и результат проверки будут удалены. Продолжить?")) return false;
    setNoteKind(next);
    return true;
  }
  function showNotes(addEvidence = false) {
    if (addEvidence && !chooseNoteKind("evidence")) return;
    requestAnimationFrame(() => {
      const target = addEvidence ? noteDraft.form.current?.querySelector<HTMLTextAreaElement>("textarea") : latestEvidenceRef.current;
      target?.scrollIntoView({ block: addEvidence ? "center" : "start" });
      target?.focus({ preventScroll: true });
    });
  }
  return (
    <Dialog title={task.short_id} onClose={() => { if (canDiscardDraft()) onClose(); }} busy={busy} drawer docked={docked}>
      <div className="drawer-body">
        <div className="drawer-breadcrumb">
          <FolderKanban size={13} />
          <span>{board.project.name}</span>
          <ChevronRight size={12} />
          <span>{subprojectPath(board.subprojects || [], task.subproject_id) || "Весь проект"}</span>
        </div>
        <div className="task-detail-heading">
          <h3>{task.title}</h3>
          <button className="icon-button task-copy-link" onClick={onCopyLink} aria-label="Скопировать ссылку на задачу" title="Скопировать ссылку на задачу в этом локальном пространстве">
            <Link2 size={17} />
          </button>
          <button
            ref={editButton}
            className="icon-button"
            onClick={() => {
              if (edit) cancelEdit();
              else beginEdit();
            }}
            aria-label={
              edit ? "Отменить редактирование" : "Редактировать задачу"
            }
            disabled={busy}
          >
            <Pencil size={17} />
          </button>
        </div>
        <div className="task-properties">
          <StatusPill status={task.status} />
          <span className="task-type-tag">{taskTypes[task.task_type || "other"]}</span>
          <PriorityMark priority={task.priority} label/>
          <span className="assigned">
            <Avatar agent={assignee} small />
            {agentName(agents, task.assignee_id)}
          </span>
        </div>
        <div className="version-line">
          Версия {task.version} · обновлено {date(task.updated_at)} · МСК
        </div>
        {task.claim_owner_id &&
          task.claim_expires_at &&
          new Date(task.claim_expires_at) > new Date() && (
            <div className="lease-banner">
              <ShieldCheck size={16} />
              <span>
                В работе у {agentName(agents, task.claim_owner_id)} до{" "}
                {date(task.claim_expires_at)}. Ручные изменения сохранят вашу
                причину.
              </span>
            </div>
          )}
        {edit ? (
          <form ref={editDraft.ref} onSubmit={update} className="edit-form" aria-busy={busy}>
            <fieldset className="draft-fields" disabled={busy}>
            <Field
              label="Название задачи"
              name="title"
              defaultValue={task.title}
              required
            />
            <div className="form-row">
              <Select label="Статус" name="status" defaultValue={task.status}>
                {statuses.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
              <Select
                label="Приоритет"
                name="priority"
                defaultValue={task.priority}
              >
                {Object.entries(priorities).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-row">
              <AssigneeSelect agents={agents} defaultValue={task.assignee_id || ""} disabled={busy}/>
              <Select
                label="Тип задачи"
                name="task_type"
                defaultValue={task.task_type || "other"}
              >
                {Object.entries(taskTypes).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
            <Select label="Подпроект" name="subproject_id" defaultValue={task.subproject_id || ""}>
              <option value="">Весь проект · без подпроекта</option>
              {[...(board.subprojects || [])].sort((a, b) => subprojectPath(board.subprojects || [], a.id).localeCompare(subprojectPath(board.subprojects || [], b.id), "ru")).map((s) => <option key={s.id} value={s.id}>{subprojectPath(board.subprojects || [], s.id)}</option>)}
            </Select>
            <Field
              label="Что нужно сделать"
              name="description"
              area
              defaultValue={task.description}
            />
            <Field
              label="Зачем это нужно"
              name="rationale"
              area
              required
              defaultValue={task.rationale}
            />
            <Field
              label="Критерии готовности"
              name="acceptance_criteria"
              area
              defaultValue={task.acceptance_criteria}
            />
            <details className="dependency-picker">
              <summary>Зависимости · {task.depends_on.length}</summary>
              <div className="checkbox-list">
                {board.tasks
                  .filter((t) => t.id !== task.id)
                  .map((t) => (
                    <label key={t.id}>
                      <input
                        type="checkbox"
                        name="depends_on"
                        value={t.id}
                        defaultChecked={task.depends_on.includes(t.id)}
                      />
                      <span>
                        {t.short_id} · {t.title}
                      </span>
                    </label>
                  ))}
              </div>
            </details>
            <Field label="Почему меняем задачу" name="reason" area required />
            {error && <ErrorBox message={error} onRefresh={error.startsWith('Конфликт изменений.')?refreshConflict:undefined} />}
            <div className="form-footer">
              <button
                className="button secondary"
                type="button"
                onClick={cancelEdit}
              >
                Отмена
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? "Сохраняем…" : "Сохранить"}
              </button>
            </div>
            </fieldset>
          </form>
        ) : (
          <>
            <div className="detail-section">
              <h4>Что делаем</h4>
              <p>{task.description || "Описание пока не добавлено."}</p>
            </div>
            <div className="detail-section rationale">
              <h4>
                <Sparkles size={14} />
                Зачем
              </h4>
              <p>{task.rationale}</p>
            </div>
            <div className="detail-section criteria-section">
              <h4>
                <CheckCheck size={15} />
                Критерии готовности
              </h4>
              <p>
                {task.acceptance_criteria ||
                  "Критерии не заданы. Добавьте их перед завершением."}
              </p>
            </div>
            <section className="task-review" aria-label="Готовность к завершению">
              <h4>Результат и проверка</h4>
              <ul className="task-readiness">
                <li>{task.acceptance_criteria.trim() ? <CheckCheck size={15} aria-hidden="true" /> : <Circle size={15} aria-hidden="true" />}<span>{task.acceptance_criteria.trim() ? "Критерии заданы" : "Добавьте критерии готовности"}</span></li>
                <li>{evidence ? <CheckCheck size={15} aria-hidden="true" /> : <Circle size={15} aria-hidden="true" />}<span>{evidence ? "Проверка приложена" : "Проверка пока не приложена"}</span></li>
                {waiting.length > 0 && <li className="task-readiness-waiting"><GitBranch size={15} aria-hidden="true" /><span>Незавершённых зависимостей: {waiting.length}</span></li>}
              </ul>
              {evidence ? <div className="latest-evidence">
                <p className="latest-evidence-body">{evidence.body}</p>
                <p className="latest-evidence-author">{agentName(agents, evidence.actor_id)} · <time dateTime={evidence.created_at}>{date(evidence.created_at)} · МСК</time></p>
                <span className="muted">Запись автора; DashAI не выполняет проверки.</span>
              </div> : <p className="task-review-hint">Перед завершением укажите, что проверили и какой результат получили.</p>}
              <div className="task-review-actions">
                <button type="button" className="text-button" disabled={busy} onClick={() => showNotes(!evidence)}>{evidence ? "К записям и проверкам" : "Добавить проверку"}<ArrowRight size={14} aria-hidden="true" /></button>
                {!task.acceptance_criteria.trim() && <button type="button" className="text-button" disabled={busy} onClick={beginEdit}>Добавить критерии</button>}
              </div>
            </section>
            {task.depends_on.length > 0 && (
              <div className="detail-section">
                <h4>
                  <GitBranch size={15} />
                  Зависимости
                </h4>
                {task.depends_on.map((id) => {
                  const t = board.tasks.find((t) => t.id === id);
                  return (
                    <div className="dependency-line" key={id}>
                      <StatusPill status={t?.status || "backlog"} />
                      <span>
                        {t?.short_id} · {t?.title || id}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            <button className="button secondary wide" onClick={beginEdit} disabled={busy}>
              <Pencil size={15} />
              Изменить статус или детали
            </button>
          </>
        )}
        <div className="detail-section notes-section">
          <div className="subheading">
            <h4>Записи и правки</h4>
            <span className="count">{detail.notes.length}</span>
          </div>
          {!detail.notes.length && (
            <p className="muted">
              Пока нет записей. Сохраните ход работы, решение или проверку.
            </p>
          )}
          {detail.notes.map((n) => (
            <article className={`note ${n.kind}`} key={n.id} ref={n.id === evidence?.id ? latestEvidenceRef : undefined} tabIndex={n.id === evidence?.id ? -1 : undefined}>
              <div className="note-head">
                <span>{noteLabels[n.kind] || n.kind}</span>
                <time>{date(n.created_at)}</time>
              </div>
              <p>{n.body}</p>
              {n.kind === "change" && n.metadata && (
                <div className="change-artifacts">
                  {Array.isArray(n.metadata.files) &&
                    n.metadata.files.map((f, i) => (
                      <div className="file-path" key={i}>
                        <FileCode2 size={13} />
                        <code>{String(f)}</code>
                      </div>
                    ))}
                  {Boolean(n.metadata.commit) && (
                    <div className="file-path">
                      <GitBranch size={13} />
                      <code>{String(n.metadata.commit)}</code>
                    </div>
                  )}
                  {Boolean(n.metadata.verification) && (
                    <p>
                      <strong>Проверка:</strong>{" "}
                      {String(n.metadata.verification)}
                    </p>
                  )}
                  {Boolean(n.metadata.diff) && (
                    <details>
                      <summary>Посмотреть diff</summary>
                      <pre>{String(n.metadata.diff)}</pre>
                    </details>
                  )}
                </div>
              )}
              <footer>{agentName(agents, n.actor_id)}</footer>
            </article>
          ))}
        </div>
        {!edit && (
          <form ref={noteDraft.ref} className="note-form" onSubmit={note} aria-busy={busy}>
            <fieldset className="draft-fields" disabled={busy}>
            <div className="field">
              <label htmlFor={`note-kind-${task.id}`}>Добавить запись</label>
              <select id={`note-kind-${task.id}`} value={noteKind} onChange={event => chooseNoteKind(event.target.value)}>
                {Object.entries(noteLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <Field
              label={
                noteKind === "change"
                  ? "Что изменено"
                  : noteKind === "evidence"
                    ? "Что проверили и какой результат"
                    : "Текст записи"
              }
              name="body"
              required
              area
            />
            {noteKind === "change" && (
              <>
                <Field
                  label="Измененные файлы"
                  name="files"
                  required
                  area
                  hint="Один путь на строку"
                />
                <Field label="Commit / ветка" name="commit" />
                <Field label="Diff" name="diff" area />
                <Field label="Результат проверки" name="verification" area />
              </>
            )}
            <Field
              label="Почему добавляем запись"
              name="note_reason"
              required
            />
            {error && <ErrorBox message={error} onRefresh={onRefresh} />}
            <button className="button secondary wide" disabled={busy}>
              <Plus size={15} />
              {busy ? "Сохраняем…" : "Добавить в историю"}
            </button>
            </fieldset>
          </form>
        )}
        <div className="detail-section">
          <div className="subheading">
            <h4>
              <History size={15} />
              Хронология задачи
            </h4>
            <span className="count">{detail.events.length}</span>
          </div>
          <Events events={detail.events} agents={agents} />
        </div>
      </div>
    </Dialog>
  );
}

function ConnectorView({
  agents,
  notify,
}: {
  agents: Agent[];
  notify: (s: string) => void;
}) {
  const [info, setInfo] = useState<Connectors | null>(null),
    [error, setError] = useState(""),
    [newAgent, setNewAgent] = useState(false),
    [credential, setCredential] = useState<{
      agent: Agent;
      token: string;
    } | null>(null),
    [busy, setBusy] = useState(false),
    [copied, setCopied] = useState("");
  const [client,setClient]=useState('codex'),[identity,setIdentity]=useState('codex'),[tokenFile,setTokenFile]=useState('');
  const [issuedAgents,setIssuedAgents]=useState<Agent[]>([]);
  const [generated,setGenerated]=useState<{filename:string;format:string;content:string}|null>(null),[configError,setConfigError]=useState(''),[configBusy,setConfigBusy]=useState(false);
  useEffect(() => {
    api<Connectors>("/connectors")
      .then(setInfo)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(()=>{
    if(!info)return;
    if(!['codex','claude'].includes(identity)&&!tokenFile.trim()){setGenerated(null);setConfigError('Укажите путь к локальному JSON-файлу с выданным токеном.');setConfigBusy(false);return;}
    let cancelled=false;setConfigBusy(true);setConfigError('');
    const timer=setTimeout(()=>{api<{filename:string;format:string;content:string}>('/connectors/config',{method:'POST',body:JSON.stringify({client,agent_id:identity,...(tokenFile.trim()?{token_file:tokenFile.trim()}:{})})}).then(value=>{if(!cancelled)setGenerated(value);}).catch(error=>{if(!cancelled){setConfigError(error.message);setGenerated(null);}}).finally(()=>{if(!cancelled)setConfigBusy(false);});},250);
    return()=>{cancelled=true;clearTimeout(timer);};
  },[info,client,identity,tokenFile]);
  async function copy(value: string, id: string) {
    try {
      await writeClipboard(value);
      setCopied(id);
      notify("Конфигурация скопирована");
    } catch {
      setError(
        "Не удалось скопировать. Выделите конфигурацию и скопируйте вручную.",
      );
    }
  }
  async function provision(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const d = new FormData(e.currentTarget);
    try {
      const created = await api<{agent:Agent;token:string}>("/agents", {
          method: "POST",
          body: JSON.stringify({
            name: text(d, "name"),
            kind: text(d, "kind"),
            reason: text(d, "reason"),
          }),
        });
      setCredential(created);setIssuedAgents(previous=>[...previous,created.agent]);setIdentity(created.agent.id);setTokenFile('');
      setNewAgent(false);
      notify("Агент создан. Сохраните его токен.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const knownAgents=agents.filter(agent=>agent.kind!=='human');
  knownAgents.push(...issuedAgents.filter(agent=>!knownAgents.some(existing=>existing.id===agent.id)));
  const currentAgent=knownAgents.find(agent=>agent.id===identity);
  return (
    <div className="connectors-page">
      <div className="page-heading">
        <div>
          <h1>
            Подключите ваших агентов<span className="heading-dot">.</span>
          </h1>
          <p>
            Любые агенты с поддержкой MCP работают на общей доске. Имя модели и
            формат конфигурации клиента выбираются отдельно.
          </p>
        </div>
        <button className="button secondary" onClick={() => setNewAgent(true)}>
          <Plus size={16} />
          Отдельный агент
        </button>
      </div>
      {error && <ErrorBox message={error} />}
      <div className="connector-banner">
        <ShieldCheck size={23} />
        <div>
          <strong>Ваш компьютер. Ваша история.</strong>
          <p>
            Коннектор общается с локальным API. Dashboard не запускает модели
            и не требует ключей их провайдеров.
          </p>
        </div>
        <span className="local-badge">LOCAL / MCP</span>
      </div>
      {info&&<section className="connector-configurator" aria-label="Генератор MCP-конфигурации"><h2>Готовая конфигурация для вашего клиента</h2>
        <div className="connector-config-controls"><label>Приложение / MCP-клиент<select value={client} onChange={event=>setClient(event.target.value)}>{info.client_profiles.map(profile=><option key={profile.id} value={profile.id}>{profile.label}</option>)}</select></label>
        <label>Имя агента в истории<select value={identity} onChange={event=>{setIdentity(event.target.value);setTokenFile('');}}>{knownAgents.map(agent=><option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>
        <label className="wide">Путь к JSON-файлу токена {['codex','claude'].includes(identity)&&'(необязательно для стандартной идентичности)'}<input value={tokenFile} onChange={event=>setTokenFile(event.target.value)} placeholder={insideVSCode?'Абсолютный путь на вашем компьютере':'Например, /Users/me/.config/dashai/qwen.json'} spellCheck={false}/></label></div>
        <p className="connector-hint">Модель можно назвать как угодно: Qwen, Gemini, локальный агент или имя команды. Создайте отдельную идентичность, чтобы её действия различались в истории.</p>
        {configError&&<ErrorBox message={configError}/>}
        {configBusy&&<p className="muted" role="status">Формируем конфигурацию…</p>}
        {generated&&!configBusy&&<><p>{client==='cline'?<>В Cline откройте MCP Servers → Configure MCP Servers и добавьте сервер в открытые настройки, сохранив остальные записи.</>:client==='generic'?<>Вставьте объект <code>command</code> и <code>args</code> в настройки локального stdio MCP своего клиента. Имя и расположение файла определяет клиент.</>:<>Добавьте настройки в <code>{generated.filename}</code> нужного проекта, сохранив остальные MCP-серверы.</>}</p><div className="code-block"><div className="code-label">{generated.format}<button onClick={()=>copy(generated.content,'generated')} aria-label="Скопировать MCP-конфигурацию">{copied==='generated'?<Check size={15}/>:<Clipboard size={15}/>} {copied==='generated'?'Скопировано':'Копировать'}</button></div><pre>{generated.content}</pre></div></>}
        <div className="connection-status"><span className={`status-dot ${currentAgent?.last_seen?'seen':''}`}/>{currentAgent?.last_seen?`Последний запрос ${date(currentAgent.last_seen)}`:'Запросов пока нет'}</div>
        <p className="connector-hint">Перезапустите MCP-сессию клиента и разрешите доступ к этому проекту. Конфигурация сама по себе не подтверждает подключение; первый реальный запрос появится в статусе агента.</p>
      </section>}
      {!info && !error && (
        <div className="loading">
          <RefreshCw size={18} />
          Загружаем конфигурации…
        </div>
      )}
      <div className="workflow-panel">
        <div>
          <span className="eyebrow">КАК АГЕНТ РАБОТАЕТ</span>
          <h2>От намерения — к проверенному результату</h2>
        </div>
        <div className="workflow-steps">
          {[
            ["01", "Читает контекст", "get_board / get_task"],
            ["02", "Берет задачу", "create_task / claim_task"],
            ["03", "Сохраняет правки", "log_change / add_note"],
            ["04", "Передает на проверку", "evidence → review → done"],
          ].map(([n, t, c]) => (
            <div key={n}>
              <span className="step-number">{n}</span>
              <strong>{t}</strong>
              <code>{c}</code>
            </div>
          ))}
        </div>
      </div>
      <div className="agents-panel">
        <div className="subheading">
          <h2>Идентичности в пространстве</h2>
          <span className="count">
            {agents.filter((a) => a.kind !== "human").length}
          </span>
        </div>
        {agents
          .filter((a) => a.kind !== "human")
          .map((a) => (
            <div className="agent-row" key={a.id}>
              <Avatar agent={a} />
              <div>
                <strong>{a.name}</strong>
                <span>
                  {kindLabel(a.kind)} · {a.id}
                </span>
              </div>
              <span className="agent-last-seen">
                {a.last_seen
                  ? `Последний запрос: ${date(a.last_seen)}`
                  : "Ожидает первого запроса"}
              </span>
            </div>
          ))}
      </div>
      <p className="scope-note">
        Запись «Правка кода» создается вызовом log_change. Dashboard не следит
        за файлами автоматически. Последний запрос подтверждает контакт с API, а
        не работу процесса в данный момент.
      </p>
      {newAgent && (
        <Dialog
          title="Отдельная идентичность агента"
          onClose={() => setNewAgent(false)}
        >
          <form className="entity-form" onSubmit={provision}>
            <p className="form-intro">
              Для нескольких экземпляров создавайте отдельные токены. Тогда
              история покажет, какой агент внес правку.
            </p>
            <Field label="Имя модели или агента" name="name" required hint="Например, Qwen · ревью проекта" />
            <Select label="Тип идентичности" name="kind" defaultValue="custom">
              <option value="custom">Другая модель / свой агент</option>
              <option value="codex">Codex</option>
              <option value="claude">Claude Code</option>
            </Select>
            <Field
              label="Причина"
              name="reason"
              required
              defaultValue="Подключение отдельного исполнителя"
            />
            {error && <ErrorBox message={error} />}
            <div className="form-footer">
              <button className="button primary" disabled={busy}>
                {busy ? "Создаем…" : "Создать идентичность"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
      {credential && (
        <Dialog
          title="Сохраните токен агента"
          onClose={() => setCredential(null)}
        >
          <div className="entity-form">
            <p className="form-intro">
              Токен для {credential.agent.name} показывается один раз. Сохраните
              его в локальный JSON-файл вне репозитория.
            </p>
            <div className="code-block">
              <pre>{JSON.stringify({ token: credential.token }, null, 2)}</pre>
              <button
                className="button secondary"
                onClick={() =>
                  copy(
                    JSON.stringify({ token: credential.token }, null, 2),
                    "token",
                  )
                }
              >
                <Clipboard size={14} />
                Копировать JSON токена
              </button>
            </div>
            <p className="scope-note">
              В args коннектора используйте --token-file &lt;абсолютный путь&gt;
              вместо --credentials и --agent {credential.agent.id}. Выберите эту идентичность в генераторе выше. Имя и права определяются токеном на сервере.
            </p>
            <button
              className="button primary"
              onClick={() => setCredential(null)}
            >
              Токен сохранен
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function Overview({ bootstrap, onProject, onTask, onCreate, onHistory }: {
  bootstrap: Bootstrap;
  onProject: (id: string) => void;
  onTask: (id: string) => void;
  onCreate: () => void;
  onHistory: () => void;
}) {
  const [status, setStatus] = useState<Status | 'attention' | 'active'>('attention');
  const [projectId, setProjectId] = useState(''), [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0), [retry, setRetry] = useState(0);
  const [expandedProjects, setExpandedProjects] = useState(false);
  const [result, setResult] = useState<{ key: string; scope: string; status: typeof status; data: OverviewData } | null>(null);
  const [error, setError] = useState('');
  const scope = new URLSearchParams({ ...(projectId ? { project_id: projectId } : {}), q: query.trim() }).toString();
  const requestKey = `${scope}&status=${status}&offset=${offset}&limit=12`;
  const data = result?.key === requestKey ? result.data : null;
  const page = result?.scope === scope && result.status === status ? result.data : null;
  const counts = result?.scope === scope ? result.data.counts : null;
  useEffect(() => {
    let current = true;
    setError('');
    api<OverviewData>(`/overview?${requestKey}`).then(next => {
      if (!current) return;
      if (offset > 0 && offset >= next.total) {
        setOffset(Math.max(0, Math.floor((next.total - 1) / next.limit) * next.limit));
        return;
      }
      setResult({ key: requestKey, scope, status, data: next });
    }).catch(error => { if (current) setError(error.message); });
    return () => { current = false; };
  }, [bootstrap, requestKey, scope, status, offset, retry]);
  const filters: { value: typeof status; label: string; count: number | undefined }[] = [
    { value: 'attention', label: 'Требует внимания', count: counts ? counts.blocked + counts.review : undefined },
    { value: 'review', label: 'Проверка', count: counts?.review },
    { value: 'blocked', label: 'Блокировка', count: counts?.blocked },
    { value: 'in_progress', label: 'В работе', count: counts?.in_progress },
    { value: 'active', label: 'Все открытые', count: counts ? counts.backlog + counts.in_progress + counts.review + counts.blocked : undefined },
    { value: 'backlog', label: 'Очередь', count: counts?.backlog },
    { value: 'done', label: 'Готово', count: counts?.done },
  ];
  const projectSummaries = new Map(result?.data.projects.map(project => [project.id, project]));
  const projects = [...bootstrap.projects].sort((a, b) => {
    const first = projectSummaries.get(a.id)?.counts, second = projectSummaries.get(b.id)?.counts;
    return (second ? second.blocked + second.review : 0) - (first ? first.blocked + first.review : 0);
  });
  const changeStatus = (next: typeof status) => { setStatus(next); setOffset(0); };
  return <div className="workspace-overview">
    <div className="page-heading">
      <div><h1>Обзор<span className="heading-dot">.</span></h1><p>Сначала — задачи на проверке и блокировки. Затем — текущая работа.</p></div>
      <button className="button primary" onClick={onCreate}><Plus size={16} aria-hidden="true"/>Новый проект</button>
    </div>
    <div className="overview-layout">
      <section className="overview-tasks overview-panel" aria-labelledby="overview-tasks-heading">
        <div className="overview-section-heading"><h2 id="overview-tasks-heading">Задачи</h2><span className="overview-scope">{projectId ? 'Выбранный проект' : 'Все проекты'}</span></div>
        <div className="overview-filters">
          <label className="overview-search"><span className="sr-only">Поиск задач в обзоре</span><Search size={16} aria-hidden="true"/><input type="search" value={query} maxLength={200} placeholder="Найти задачу или ID" onChange={event => { setQuery(event.target.value); setOffset(0); }}/></label>
          <label className="overview-project-filter"><span className="sr-only">Проект в обзоре</span><select value={projectId} onChange={event => { setProjectId(event.target.value); setOffset(0); }}><option value="">Все проекты</option>{bootstrap.projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        </div>
        <div className="overview-status-filters" role="group" aria-label="Статус задач в обзоре">
          {filters.map(filter => <button key={filter.value} aria-pressed={status === filter.value} onClick={() => changeStatus(filter.value)}>{filter.label}<span>{filter.count ?? '—'}</span></button>)}
        </div>
        <label className="overview-mobile-status"><span className="sr-only">Статус задач</span><select value={status} onChange={event => changeStatus(event.target.value as typeof status)}>{filters.map(filter => <option key={filter.value} value={filter.value}>{filter.label} · {filter.count ?? '—'}</option>)}</select></label>
        <p className="overview-sort">Сначала блокировки, затем проверка; внутри статуса — по приоритету и обновлению.</p>
        {error && <ErrorBox message={`Не удалось обновить обзор. ${error}`} onRefresh={() => setRetry(value => value + 1)}/>}
        <div className="overview-result-summary" role="status" aria-live="polite">
          {data ? data.total ? `Показаны ${data.offset + 1}–${Math.min(data.offset + data.limit, data.total)} из ${data.total}` : 'Задач не найдено' : error ? 'Данные недоступны' : 'Загружаем задачи…'}
        </div>
        {data && data.tasks.length > 0 && <ul className="overview-task-list">
          {data.tasks.map(task => <li key={task.id}>
            <button className="overview-task-row" data-task-id={task.id} onClick={() => onTask(task.id)} aria-labelledby={`overview-${task.id}-title`} aria-describedby={`overview-${task.id}-status overview-${task.id}-meta`}>
              <span className="overview-task-title" id={`overview-${task.id}-title`}><span className="sr-only">Открыть задачу </span><span className="overview-task-id">{task.short_id}</span><strong>{task.title}</strong></span>
              <span id={`overview-${task.id}-status`}><StatusPill status={task.status}/></span>
              <span className="overview-task-meta" id={`overview-${task.id}-meta`}>
                <span className="overview-task-project">{bootstrap.projects.find(project => project.id === task.project_id)?.name}</span>
                <PriorityMark priority={task.priority} label/>
                <span className="overview-task-assignee"><Avatar small agent={bootstrap.agents.find(agent => agent.id === task.assignee_id)}/>{agentName(bootstrap.agents, task.assignee_id)}</span>
                <time dateTime={task.updated_at} title={`Обновлена ${date(task.updated_at, true)}`}>{date(task.updated_at)}</time>
              </span>
            </button>
          </li>)}
        </ul>}
        {data && !data.tasks.length && <div className="overview-empty">
          <CircleCheck size={26} aria-hidden="true"/>
          <h3>{status === 'attention' && !query.trim() ? 'Нет задач, требующих внимания' : 'Нет задач по этим условиям'}</h3>
          <p>{status === 'attention' ? 'Здесь появляются задачи со статусом «Проверка» или «Блокировка».' : 'Выберите другой статус, проект или измените поиск.'}</p>
          <div>{status !== 'active' && <button className="button secondary" onClick={() => changeStatus('active')}>Показать все открытые</button>}{(projectId || query) && <button className="text-button" onClick={() => { setProjectId(''); setQuery(''); setOffset(0); }}>Сбросить поиск и проект</button>}</div>
        </div>}
        {page && page.total > page.limit && <nav className="overview-pagination" aria-label="Страницы задач в обзоре">
          <button className="button secondary" aria-disabled={!data || page.offset === 0} onClick={() => { if (data && data.offset > 0) setOffset(data.offset - data.limit); }}>Назад</button>
          <span>{Math.floor(page.offset / page.limit) + 1} / {Math.ceil(page.total / page.limit)}</span>
          <button className="button secondary" aria-disabled={!data || page.offset + page.limit >= page.total} onClick={() => { if (data && data.offset + data.limit < data.total) setOffset(data.offset + data.limit); }}>Далее</button>
        </nav>}
        {result && <p className="overview-updated">Данные обновлены <time dateTime={result.data.updated_at}>{date(result.data.updated_at)}</time>{error && ' · показана последняя доступная версия'}</p>}
      </section>
      <section className="overview-projects overview-panel" aria-labelledby="overview-projects-heading">
        <div className="overview-section-heading"><h2 id="overview-projects-heading">Проекты</h2><span className="overview-scope">{projects.length}</span></div>
        <p className="overview-projects-hint">Все проекты. Сначала те, где нужна проверка или есть блокировки.</p>
        <ul id="overview-project-list" className="overview-project-list">
          {(expandedProjects ? projects : projects.slice(0, 6)).map(project => {
            const summary = projectSummaries.get(project.id);
            return <li key={project.id}>
              <button className="overview-project-link" onClick={() => onProject(project.id)} aria-label={`Открыть проект ${project.name}`}><span className="project-dot" style={{ background: project.color }}/><strong>{project.name}</strong><ArrowUpRight size={16} aria-hidden="true"/></button>
              {summary ? <dl className="overview-project-counts">
                <div><dt>Открыто</dt><dd>{summary.total - summary.counts.done}</dd></div>
                <div className={summary.counts.review ? 'has-review' : ''}><dt>Проверка</dt><dd>{summary.counts.review}</dd></div>
                <div className={summary.counts.blocked ? 'has-blocked' : ''}><dt>Блокировки</dt><dd>{summary.counts.blocked}</dd></div>
                <div><dt>Готово</dt><dd>{summary.counts.done}</dd></div>
              </dl> : <p className="overview-project-pending">{error ? 'Статусы недоступны' : 'Загружаем статусы…'}</p>}
            </li>;
          })}
        </ul>
        {projects.length > 6 && <button className="overview-expand text-button" aria-expanded={expandedProjects} aria-controls="overview-project-list" onClick={() => setExpandedProjects(value => !value)}>{expandedProjects ? 'Свернуть проекты' : `Показать все проекты (${projects.length})`}</button>}
      </section>
    </div>
    <details className="overview-recent overview-panel">
      <summary>Последние действия <span>{bootstrap.activity.slice(0, 5).length}</span></summary>
      <div className="overview-recent-body"><button className="text-button" onClick={onHistory}>Вся история<ArrowRight size={14} aria-hidden="true"/></button><Events events={bootstrap.activity.slice(0, 5)} agents={bootstrap.agents} onTask={onTask}/></div>
    </details>
  </div>;
}

export default function App({ initialWorkspace, initialWorkspaceWarning = "" }: { initialWorkspace: Workspace; initialWorkspaceWarning?: string }) {
  const initialProject = initialWorkspace.projects[initialWorkspace.projectId || ""] || defaultProjectWorkspace;
  const [bootstrap, setBootstrap] = useState(emptyBootstrap),
    [board, setBoard] = useState<Board | null>(null),
    [projectId, setProjectId] = useState<string | null>(initialWorkspace.projectId),
    [view, setViewState] = useState<View>(initialWorkspace.view),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [syncError, setSyncError] = useState(false),
    [syncAt, setSyncAt] = useState<string | null>(null),
    [modal, setModal] = useState<Modal | null>(null),
    [move, setMove] = useState<{ task: Task; status: Status } | null>(null),
    [detail, setDetail] = useState<Detail | null>(null),
    [drawerBoard, setDrawerBoard] = useState<Board | null>(null),
    [toast, setToast] = useState(""),
    [mobileMenu, setMobileMenu] = useState(false);
  const [mapDirty,setMapDirty]=useState(false);
  const [workspaceWarning, setWorkspaceWarning] = useState(initialWorkspaceWarning);
  const [routeTaskId, setRouteTaskId] = useState<string | null>(() => taskFromUrl() ?? initialWorkspace.taskId);
  const [taskError, setTaskError] = useState("");
  const [taskAttempt, setTaskAttempt] = useState(0);
  const savedProjects = useRef({ ...initialWorkspace.projects });
  const routeIndex = useRef(Number.isInteger(window.history.state?.dashaiIndex) ? window.history.state.dashaiIndex as number : 0),
    acceptedUrl = useRef(window.location.href), restoringHistory = useRef(false);
  function canNavigate(includeMap = true) {
    const state = { busy: false, dirty: false };
    window.dispatchEvent(new CustomEvent("dashai:check-navigation", { detail: state }));
    if (state.busy) { notify("Дождитесь завершения сохранения"); return false; }
    return !(state.dirty || (includeMap && mapDirty)) || window.confirm("Есть несохранённые изменения. Перейти без сохранения?");
  }
  function setView(next:View) {
    const withinMap=['map','architecture','documentation'].includes(view)&&['map','architecture','documentation'].includes(next);
    if (next === view) return;
    if (!canNavigate(!withinMap)) return;
    if (!withinMap) setMapDirty(false);
    if (routeTaskId !== null) navigateTask(null, "push", true);
    setViewState(next);
  }
  const [query, setQuery] = useState(initialProject.query),
    [taskTypeFilter, setTaskTypeFilter] = useState(initialProject.taskTypeFilter),
    [subprojectFilter, setSubprojectFilter] = useState(initialProject.subprojectFilter),
    [agentFilter, setAgentFilter] = useState(initialProject.agentFilter),
    [statusFilter, setStatusFilter] = useState(initialProject.statusFilter),
    [priorityFilter, setPriorityFilter] = useState(initialProject.priorityFilter),
    [filtersOpen, setFiltersOpen] = useState(initialProject.filtersOpen),
    [listView, setListView] = useState(initialProject.listView),
    [history, setHistory] = useState<Event[]>([]),
    [cursor, setCursor] = useState(0),
    [hasMore, setHasMore] = useState(false),
    [historyQuery, setHistoryQuery] = useState(""),
    [historyAgent, setHistoryAgent] = useState(""),
    [historyLoading, setHistoryLoading] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null),
    moveFocus = useRef<string | null>(null),
    projectRef = useRef(projectId),
    loadSequence = useRef(0),
    detailSequence = useRef(0),
    detailId = useRef<string|null>(routeTaskId),
    sidebarRef = useRef<HTMLElement>(null),
    menuOpener = useRef<HTMLButtonElement>(null),
    toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const historySequence = useRef(0),
    historyScope = useRef(""),
    historyBusy = useRef(false);
  historyScope.current = `${view}:${projectId}`;
  projectRef.current = projectId;
  function applyProject(id: string | null, restoreView = true) {
    const prefs = savedProjects.current[id || ""] || defaultProjectWorkspace;
    loadSequence.current++;
    projectRef.current = id;
    setProjectId(id);
    if (restoreView) setViewState(prefs.view);
    setQuery(prefs.query); setTaskTypeFilter(prefs.taskTypeFilter); setSubprojectFilter(prefs.subprojectFilter);
    setAgentFilter(prefs.agentFilter); setStatusFilter(prefs.statusFilter); setPriorityFilter(prefs.priorityFilter);
    setListView(prefs.listView); setFiltersOpen(prefs.filtersOpen);
  }
  useEffect(() => {
    if (loading || (projectId && board?.project.id !== projectId)) return;
    if (projectId) {
      const previous = savedProjects.current[projectId] || defaultProjectWorkspace;
      const prefs: ProjectWorkspace = { view: projectView(view) ? view : previous.view, query, taskTypeFilter,
        subprojectFilter, agentFilter, statusFilter, priorityFilter, listView, filtersOpen };
      delete savedProjects.current[projectId];
      savedProjects.current[projectId] = prefs;
    }
    void saveWorkspace({ version: 1, projectId, view, taskId: routeTaskId, projects: savedProjects.current })
      .catch((error: Error) => setWorkspaceWarning(error.message));
  }, [projectId, view, query, taskTypeFilter, subprojectFilter, agentFilter, statusFilter, priorityFilter, listView, filtersOpen, routeTaskId, loading, board?.project.id]);
  useEffect(() => {
    if (loading || !syncAt || syncError || !board || board.project.id !== projectId) return;
    if (subprojectFilter && subprojectFilter !== "unassigned" && !board.subprojects.some(item => item.id === subprojectFilter)) setSubprojectFilter("");
    if (agentFilter && agentFilter !== "unassigned" && !bootstrap.agents.some(item => item.id === agentFilter)) setAgentFilter("");
  }, [board, bootstrap.agents, projectId, subprojectFilter, agentFilter, loading, syncAt, syncError]);
  function writeTaskUrl(id: string | null, replace = false) {
    const url = new URL(window.location.href);
    if (id === null) url.searchParams.delete("task"); else url.searchParams.set("task", id);
    if (!replace) routeIndex.current++;
    window.history[replace ? "replaceState" : "pushState"]({ ...window.history.state, dashaiIndex: routeIndex.current }, "", url);
    acceptedUrl.current = url.href;
  }
  function navigateTask(id: string | null, mode: "push" | "pop" = "push", checked = false) {
    if (id === routeTaskId) return true;
    if (!checked && !canNavigate()) return false;
    detailSequence.current++;
    detailId.current = id;
    setDetail(null); setDrawerBoard(null); setTaskError("");
    setModal(null); setMove(null); setRouteTaskId(id);
    if (mode === "push") writeTaskUrl(id);
    return true;
  }
  useEffect(() => { writeTaskUrl(routeTaskId, true); }, []);
  useEffect(() => {
    const pop = () => {
      if (restoringHistory.current) { restoringHistory.current = false; return; }
      const targetIndex = window.history.state?.dashaiIndex;
      if (navigateTask(taskFromUrl(), "pop")) {
        routeIndex.current = Number.isInteger(targetIndex) ? targetIndex : 0;
        acceptedUrl.current = window.location.href;
      } else if (Number.isInteger(targetIndex) && targetIndex !== routeIndex.current) {
        restoringHistory.current = true;
        window.history.go(routeIndex.current - targetIndex);
      } else {
        window.history.replaceState({ ...window.history.state, dashaiIndex: routeIndex.current }, "", acceptedUrl.current);
      }
    };
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  });
  useEffect(() => {
    const id = routeTaskId, sequence = ++detailSequence.current;
    detailId.current = id;
    if (id === null) return;
    if (!validId(id)) { setTaskError("В ссылке указан некорректный идентификатор задачи."); return; }
    void (async () => {
      try {
        const result = await api<Detail>(`/tasks/${id}`);
        const context = await api<Board>(`/projects/${result.task.project_id}`);
        if (sequence !== detailSequence.current) return;
        if (result.task.project_id !== projectRef.current) {
          applyProject(result.task.project_id, view !== 'overview');
          setMapDirty(false);
        }
        setBoard(context); setDrawerBoard(context); setDetail(result);
      } catch (error) {
        if (sequence === detailSequence.current) setTaskError(error instanceof ApiError && error.status === 404
          ? "Задача не найдена. Возможно, ссылка относится к другому локальному пространству." : (error as Error).message);
      }
    })();
    return () => { detailSequence.current++; };
  }, [routeTaskId, taskAttempt]);
  useEffect(()=>{
    if(!mobileMenu)return;
    const sidebar=sidebarRef.current;
    const controls=()=>Array.from(sidebar?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]')||[])
      .filter(element=>!(element instanceof HTMLInputElement)||element.type!=='radio'||element.checked);
    controls()[0]?.focus();
    const keyboard=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){event.preventDefault();setMobileMenu(false);}
      if(event.key==='Tab'){
        const items=controls(),first=items[0],last=items.at(-1);
        if(!sidebar?.contains(document.activeElement)){event.preventDefault();first?.focus();}
        else if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
      }
    };
    const media=window.matchMedia('(min-width:701px)');
    const resize=()=>{if(media.matches)setMobileMenu(false);};
    document.addEventListener('keydown',keyboard);
    media.addEventListener('change',resize);
    return()=>{document.removeEventListener('keydown',keyboard);media.removeEventListener('change',resize);menuOpener.current?.focus();};
  },[mobileMenu]);
  function notify(message: string) {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 4000);
  }
  async function refresh(target = projectRef.current, quiet = false) {
    const sequence = ++loadSequence.current;
    if (!quiet) setLoading(true);
    try {
      const data = await api<Bootstrap>("/bootstrap");
      if (sequence !== loadSequence.current) return;
      setBootstrap(data);
      const id = data.projects.some((p) => p.id === target)
        ? target
        : data.projects[0]?.id || null;
      if (id !== projectRef.current) { applyProject(id, projectView(view)); return; }
      if (id) {
        const result = await api<Board>(`/projects/${id}`);
        if (sequence !== loadSequence.current) return;
        setBoard(result);
      } else setBoard(null);
      setError("");
      setSyncError(false);
      setSyncAt(new Date().toISOString());
    } catch (e) {
      if (sequence === loadSequence.current) {
        setError((e as Error).message);
        setSyncError(true);
      }
    } finally {
      if (sequence === loadSequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    refresh(projectId);
    const interval = setInterval(() => {
      if (!document.hidden) refresh(projectRef.current, true);
    }, 5000);
    return () => clearInterval(interval);
  }, [projectId]);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k" && !document.querySelector('dialog[open]')) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => {
    if (view === "history" || view === "project_history") {
      setHistory([]);
      setCursor(0);
      loadHistory(true);
    }
  }, [view, projectId]);
  useEffect(() => {
    if (move || !moveFocus.current) return;
    const id = moveFocus.current;
    moveFocus.current = null;
    if (document.querySelector("dialog[open]")) return;
    const selector = document.querySelector<HTMLSelectElement>(`.kanban-card[data-task-id="${CSS.escape(id)}"] select`);
    const target = selector?.getClientRects().length ? selector
      : document.querySelector<HTMLButtonElement>('.kanban-status-nav button[aria-pressed="true"]');
    const fallback = document.querySelector<HTMLButtonElement>('.board-quick-views button[aria-pressed="true"]') || document.querySelector<HTMLButtonElement>('.filter-toggle');
    (target?.getClientRects().length ? target : fallback)?.focus();
  }, [move]);
  async function loadHistory(reset = false) {
    if (historyBusy.current && !reset) return;
    const scope = historyScope.current,
      sequence = ++historySequence.current;
    historyBusy.current = true;
    setHistoryLoading(true);
    try {
      const result = await api<{ events: Event[]; next_cursor: number }>(
        `/history?order=desc${!reset && cursor ? `&before=${cursor}` : ""}&limit=100${view === "project_history" && projectId ? `&project_id=${projectId}` : ""}`,
      );
      if (
        sequence !== historySequence.current ||
        scope !== historyScope.current
      )
        return;
      setHistory((prev) =>
        reset
          ? result.events
          : [
              ...prev,
              ...result.events.filter(
                (e) => !prev.some((old) => old.id === e.id),
              ),
            ],
      );
      setCursor(result.next_cursor);
      setHasMore(result.events.length === 100);
    } catch (e) {
      if (
        sequence === historySequence.current &&
        scope === historyScope.current
      )
        setError((e as Error).message);
    } finally {
      if (sequence === historySequence.current) {
        historyBusy.current = false;
        setHistoryLoading(false);
      }
    }
  }
  function selectProject(id: string) {
    if (id === projectId && projectView(view)) { setMobileMenu(false); return; }
    if (!canNavigate()) return;
    setMapDirty(false);
    applyProject(id);
    setMobileMenu(false);
    setMove(null);
    navigateTask(null, "push", true);
  }
  function closeDetail() {
    navigateTask(null, "push", true);
  }
  function openTask(id: string) {
    navigateTask(id);
  }
  function openEntity(next: Modal) {
    if (!canNavigate()) return;
    if (routeTaskId !== null) navigateTask(null, "push", true);
    setModal(next);
  }
  async function copyTaskLink() {
    if (!detail) return;
    try {
      await writeClipboard(taskLink(detail.task.id));
      notify("Ссылка на задачу скопирована. Она работает в этом локальном пространстве");
    } catch { notify("Не удалось скопировать ссылку. Попробуйте ещё раз"); }
  }
  async function updateDetail() {
    if (detail) {
      const sequence=detailSequence.current,id=detail.task.id;
      const [updated, context] = await Promise.all([
        api<Detail>(`/tasks/${detail.task.id}`),
        api<Board>(`/projects/${detail.task.project_id}`),
      ]);
      if(sequence!==detailSequence.current||detailId.current!==id)return null;
      setDetail(updated);
      setDrawerBoard(context);
      return updated;
    }
    return null;
  }
  async function changed() {
    await Promise.all([refresh(projectRef.current, true), updateDetail()]);
    notify("Изменения сохранены в истории");
  }
  async function moved(updated: Task) {
    moveFocus.current = updated.id;
    setMove(null);
    setBoard((previous) => previous && previous.project.id === updated.project_id
      ? { ...previous, tasks: previous.tasks.map((task) => task.id === updated.id ? updated : task) }
      : previous);
    notify("Карточка перемещена. Причина сохранена в истории");
    await refresh(projectRef.current, true);
  }
  async function saved(id?: string, taskId?: string) {
    if (id) {
      applyProject(id);
      setViewState("board");
    }
    await refresh(id || projectRef.current, true);
    if (taskId) {
      resetFilters();
      navigateTask(taskId, "push", true);
    }
    notify("Сохранено в пространстве");
  }
  async function exportProject() {
    if (!board) return;
    try {
      if (insideVSCode) {
        if (await hostRequest("export", { project_id: board.project.id })) notify("Проект и полная история экспортированы");
        return;
      }
      const snapshot = await api<Record<string, unknown>>(
        `/projects/${board.project.id}/export`,
      );
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(snapshot, null, 2)], {
          type: "application/json",
        }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `dashai-${board.project.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
      notify("Проект и полная история экспортированы");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function resetFilters() {
    setQuery("");
    setTaskTypeFilter("");
    setSubprojectFilter("");
    setAgentFilter("");
    setStatusFilter("");
    setPriorityFilter("");
  }
  const filters = !!(
    query.trim() ||
    taskTypeFilter ||
    subprojectFilter ||
    agentFilter ||
    statusFilter ||
    priorityFilter
  );
  const tasks =
    board?.tasks.filter(
      (t) =>
        (!taskTypeFilter || (t.task_type || "other") === taskTypeFilter) &&
        (!subprojectFilter || (subprojectFilter === "unassigned" ? !t.subproject_id : inSubproject(board?.subprojects || [], t.subproject_id, subprojectFilter))) &&
        (!agentFilter ||
          (agentFilter === "unassigned"
            ? !t.assignee_id
            : t.assignee_id === agentFilter)) &&
        (!statusFilter || t.status === statusFilter) &&
        (!priorityFilter || t.priority === priorityFilter) &&
        (!query.trim() ||
          `${t.short_id} ${t.title} ${t.description} ${t.rationale} ${t.acceptance_criteria} ${taskTypes[t.task_type || "other"]} ${subprojectPath(board?.subprojects || [], t.subproject_id)}`
            .toLocaleLowerCase("ru")
            .includes(query.trim().toLocaleLowerCase("ru"))),
    ) || [];
  const isProjectView = projectView(view);
  const featureEnabled = (id:string) => board?.modules?.find(item=>item.id===id)?.enabled ?? ['map','architecture','documentation'].includes(id);
  const project = board?.project;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        К основному содержимому
      </a>
      <aside ref={sidebarRef} className={`sidebar ${mobileMenu ? "mobile-open" : ""}`} role={mobileMenu?'dialog':undefined} aria-modal={mobileMenu?true:undefined} aria-label="Проекты и навигация">
        <button
          className="brand"
          onClick={() => {
            setView("overview");
            setMobileMenu(false);
          }}
        >
          <span className="brand-mark" aria-hidden="true" />
          <span>
            DashAI<span className="brand-period">.</span>
          </span>
        </button>
        <div className="nav-caption">ПРОСТРАНСТВО</div>
        <nav aria-label="Рабочее пространство">
          <button
            className={`nav-item ${view === "overview" ? "active" : ""}`}
            aria-current={view === "overview" ? "page" : undefined}
            onClick={() => {
              setView("overview");
              setMobileMenu(false);
            }}
          >
            <LayoutDashboard size={17} />
            Обзор
          </button>
          <button
            className={`nav-item ${isProjectView ? "active" : ""}`}
            aria-current={isProjectView ? "page" : undefined}
            onClick={() => {
              setView("board");
              setMobileMenu(false);
            }}
          >
            <FolderKanban size={17} />
            Проекты
            <span className="nav-count">{bootstrap.projects.length}</span>
          </button>
          <button
            className={`nav-item ${view === "history" ? "active" : ""}`}
            aria-current={view === "history" ? "page" : undefined}
            onClick={() => {
              setView("history");
              setMobileMenu(false);
            }}
          >
            <History size={17} />
            История
          </button>
          <button
            className={`nav-item ${view === "connectors" ? "active" : ""}`}
            aria-current={view === "connectors" ? "page" : undefined}
            onClick={() => {
              setView("connectors");
              setMobileMenu(false);
            }}
          >
            <Plug size={17} />
            Коннекторы<span className="nav-count">MCP</span>
          </button>
        </nav>
        <div className="nav-caption projects-caption">
          ПРОЕКТЫ
          <button
            className="icon-button"
            onClick={() => openEntity({ kind: "project" })}
            aria-label="Создать проект"
          >
            <Plus size={15} />
          </button>
        </div>
        <nav className="project-nav" aria-label="Проекты">
          {bootstrap.projects.map((p) => (
            <button
              key={p.id}
              className={`project-nav-item ${isProjectView && projectId === p.id ? "selected" : ""}`}
              aria-current={isProjectView && projectId === p.id ? "page" : undefined}
              onClick={() => selectProject(p.id)}
            >
              <span
                className="project-color"
                style={{ background: p.color || "#b4f4a5" }}
              />
              <span>{p.name}</span>
              {isProjectView && projectId === p.id && (
                <ChevronRight size={13} />
              )}
            </button>
          ))}
          {!bootstrap.projects.length && (
            <p className="nav-empty">Здесь будут ваши проекты</p>
          )}
          <button
            className="create-project"
            onClick={() => openEntity({ kind: "project" })}
          >
            <Plus size={14} />
            Новый проект
          </button>
        </nav>
        <ThemePicker />
      </aside>
      {mobileMenu && (
        <button
          className="mobile-backdrop"
          aria-label="Закрыть меню"
          onClick={() => setMobileMenu(false)}
        />
      )}
      <div className="main-shell" inert={mobileMenu}>
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu-button"
              aria-label="Открыть меню"
                ref={menuOpener}
              onClick={() => setMobileMenu(true)}
            >
              <Menu size={20} />
            </button>
            <span>Пространство</span>
            <ChevronRight size={13} />
            <strong>
              {isProjectView
                ? project?.name || "Проекты"
                : view === "connectors"
                  ? "Коннекторы"
                  : view === "history"
                    ? "История"
                    : "Обзор"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className={`sync-status ${syncError ? "error" : ""}`} title="Последнее обновление проектов и доски">
              <span className="status-dot" />
              {syncError
                ? "Ошибка обновления"
                : syncAt
                  ? `Доска · ${new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", hour: "2-digit", minute: "2-digit" }).format(new Date(syncAt))}`
                  : "Подключение…"}
            </span>
            <button
              className="icon-button"
              aria-label="Обновить пространство"
              onClick={() => refresh()}
            >
              <RefreshCw size={16} />
            </button>
            <span className="topbar-divider" />
            <Avatar agent={bootstrap.agents.find((a) => a.kind === "human")} />
          </div>
        </header>
        <main
          id="main"
          tabIndex={-1}
          className={`main-content ${isProjectView ? "project-content" : ""}`}
        >
          {error && <ErrorBox message={error} onRefresh={() => refresh()} />}
          {workspaceWarning && <div className="workspace-warning" role="status"><span>{workspaceWarning}</span><button className="icon-button" aria-label="Закрыть предупреждение о настройках" onClick={() => setWorkspaceWarning("")}><X size={16} /></button></div>}
          {loading && !board && (
            <div className="loading">
              <RefreshCw size={20} />
              Загружаем пространство…
            </div>
          )}
          {!loading &&
            !error &&
            !bootstrap.projects.length &&
            view !== "connectors" && (
              <div className="onboarding">
                <div className="onboarding-symbol">
                  <FolderKanban size={34} />
                </div>
                <span className="eyebrow">ОБЩЕЕ МЕСТО ДЛЯ ВАШЕЙ РАБОТЫ</span>
                <h1>
                  У каждого проекта — своя история
                  <span className="heading-dot">.</span>
                </h1>
                <p>
                  Создайте проект и добавьте задачи на общую доску.
                  <br />
                  Дайте агентам задачи и сохраните, что сделано и почему.
                </p>
                <button
                  className="button primary"
                  onClick={() => openEntity({ kind: "project" })}
                >
                  <Plus size={17} />
                  Создать первый проект
                </button>
                <button
                  className="text-button"
                  onClick={() => setView("connectors")}
                >
                  Сначала подключить агента
                  <ArrowRight size={15} />
                </button>
                <div className="onboarding-features">
                  <span>
                    <PanelTop size={16} />
                    Проектные доски
                  </span>
                  <span>
                    <History size={16} />
                    История решений
                  </span>
                  <span>
                    <Plug size={16} />
                    Любые MCP-агенты
                  </span>
                </div>
              </div>
            )}
          {view === "connectors" && (
            <ConnectorView agents={bootstrap.agents} notify={notify} />
          )}
          {view === "overview" && bootstrap.projects.length > 0 && (
            <Overview bootstrap={bootstrap} onProject={selectProject} onTask={openTask} onCreate={() => openEntity({ kind: 'project' })} onHistory={() => setView('history')}/>
          )}
          {isProjectView && board && (
            <>
              <div className="project-heading">
                <div>
                  <h1>
                    {project?.name}
                    <button
                      className="icon-button"
                      aria-label="Редактировать проект"
                      onClick={() => openEntity({ kind: "project", project })}
                    >
                      <Pencil size={16} />
                    </button>
                  </h1>
                  <details className="project-doc-description"><summary>Описание проекта</summary><p>{project?.description || 'Описание проекта пока не заполнено.'}</p></details>
                  {project?.repository && (
                    <div className="repository">
                      <GitBranch size={13} />
                      <span title={project.repository}>
                        {project.repository}
                      </span>
                    </div>
                  )}
                </div>
                <div className="project-actions">
                  <button className="button secondary" onClick={() => openEntity({ kind: "subproject" })}><GitBranch size={15} />Подпроект</button>
                  <button
                    className="button secondary"
                    onClick={exportProject}
                    aria-label="Экспортировать проект"
                  >
                    <ArrowDownToLine size={15} />
                    <span>Экспорт</span>
                  </button>
                  <button
                    className="button primary"
                    onClick={() => openEntity({ kind: "task", subproject_id: subprojectFilter === "unassigned" ? "" : subprojectFilter })}
                  >
                    <Plus size={17} />
                    Новая задача
                  </button>
                </div>
              </div>
              <div className="project-tabs">
                <div className="tabs-nav">
                  <button
                    className={view === "board" ? "selected" : ""}
                    aria-current={view === "board" ? "page" : undefined}
                    onClick={() => setView("board")}
                  >
                    <FolderKanban size={15} />
                    Доска<span className="count">{board.tasks.length}</span>
                  </button>
                  {(['map','architecture','documentation'] as const).filter(featureEnabled).map(mode=><button key={mode} className={view===mode?'selected':''} aria-current={view===mode?'page':undefined} onClick={()=>setView(mode)}>{mode==='map'?<FileCode2 size={15}/>:mode==='architecture'?<GitBranch size={15}/>:<List size={15}/>}{{map:'Карта проекта',architecture:'Архитектура',documentation:'Документация'}[mode]}</button>)}
                  {featureEnabled('integrations')&&<button className={view==='integrations'?'selected':''} aria-current={view==='integrations'?'page':undefined} onClick={()=>setView('integrations')}><Plug size={15}/>Интеграции</button>}
                  {featureEnabled('releases')&&<button className={view==='releases'?'selected':''} aria-current={view==='releases'?'page':undefined} onClick={()=>setView('releases')}><GitBranch size={15}/>Версии</button>}
                  <button className={view==='modules'?'selected':''} aria-current={view==='modules'?'page':undefined} onClick={()=>setView('modules')}><Blocks size={15}/>Модули</button>
                  <button
                    className={view === "project_history" ? "selected" : ""}
                    aria-current={view === "project_history" ? "page" : undefined}
                    onClick={() => setView("project_history")}
                  >
                    <History size={15} />
                    История
                  </button>
                </div>
              </div>
              {(view==='map'||view==='architecture'||view==='documentation')&&(featureEnabled(view)||mapDirty)&&<Suspense fallback={<p className="muted">Загрузка карты проекта…</p>}><ProjectMap key={board.project.id} project={board.project} mode={view} onNotify={notify} onDirtyChange={setMapDirty} onShowMap={()=>setView(featureEnabled('map')?'map':'modules')}/></Suspense>}
              {['map','architecture','documentation','integrations','releases'].includes(view)&&!featureEnabled(view)&&<div className="module-empty"><h2>Этот модуль отключён</h2><p>Данные сохранены. Добавьте модуль обратно, чтобы продолжить работу.</p><button className="button secondary" onClick={()=>setView('modules')}>Модули проекта</button></div>}
              {view==='modules'&&<ProjectModules key={board.project.id} project={board.project} notify={notify} onChanged={()=>void refresh(projectRef.current,true)} onDirtyChange={setMapDirty} onOpen={mode=>setView(mode as View)}/>}
              {view==='integrations'&&(featureEnabled('integrations')||mapDirty)&&<ProjectIntegrations key={board.project.id} project={board.project} notify={notify} onDirtyChange={setMapDirty}/>}
              {view==='releases'&&(featureEnabled('releases')||mapDirty)&&<ProjectReleases key={board.project.id} project={board.project} notify={notify} onDirtyChange={setMapDirty}/>}
              {view === "board" && (
                <>
                  <div className="board-quick-views" role="group" aria-label="Быстрые выборки задач">
                    <button aria-pressed={!filters} onClick={resetFilters}>Все задачи <span>{board.tasks.length}</span></button>
                    {statuses.filter(s => ['in_progress', 'review', 'blocked'].includes(s.value)).map(s => (
                      <button key={s.value} aria-pressed={statusFilter === s.value} onClick={() => setStatusFilter(statusFilter === s.value ? "" : s.value)}>
                        <span className={`status-pill ${s.value}`}><span className="status-dot" />{s.label}</span>
                        <span>{board.tasks.filter(t => t.status === s.value).length}</span>
                      </button>
                    ))}
                    <button aria-pressed={agentFilter === "unassigned"} onClick={() => setAgentFilter(agentFilter === "unassigned" ? "" : "unassigned")}>
                      Без исполнителя <span>{board.tasks.filter(t => !t.assignee_id).length}</span>
                    </button>
                  </div>
                  {!!board.subprojects?.length && <details className="subprojects-panel">
                    <summary>Подпроекты <span className="count">{board.subprojects.length}</span><span className="muted">Одна доска для всех направлений</span></summary>
                    <div className="subprojects-list">{[...board.subprojects].sort((a, b) => subprojectPath(board.subprojects, a.id).localeCompare(subprojectPath(board.subprojects, b.id), "ru")).map((s) => <div key={s.id}>
                      <button className="text-button" onClick={() => setSubprojectFilter(s.id)} title={s.description}>{subprojectPath(board.subprojects, s.id)}</button>
                      <span className="muted">{board.tasks.filter((t) => inSubproject(board.subprojects, t.subproject_id, s.id)).length} задач</span>
                      <button className="icon-button" aria-label={`Добавить вложенный подпроект в ${s.title}`} onClick={() => openEntity({ kind: "subproject", parent_id: s.id })}><Plus size={14} /></button>
                      <button className="icon-button" aria-label={`Изменить подпроект ${s.title}`} onClick={() => openEntity({ kind: "subproject", subproject: s })}><Pencil size={14} /></button>
                    </div>)}</div>
                  </details>}
                  <div className="board-toolbar">
                    <div className="search-field">
                      <Search size={16} />
                      <input
                        ref={searchRef}
                        aria-label="Поиск задач в проекте"
                        placeholder="Поиск задач в проекте…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                      {query ? (
                        <button
                          className="icon-button"
                          onClick={() => setQuery("")}
                          aria-label="Очистить поиск"
                        >
                          <X size={13} />
                        </button>
                      ) : (
                        <kbd>Ctrl K</kbd>
                      )}
                    </div>
                    <button className="button secondary filter-toggle" aria-expanded={filtersOpen} aria-controls="board-filters" onClick={() => setFiltersOpen(!filtersOpen)}>
                      <SlidersHorizontal size={15} />Фильтры
                      {[taskTypeFilter, subprojectFilter, agentFilter, statusFilter, priorityFilter].filter(Boolean).length > 0 && <span className="count">{[taskTypeFilter, subprojectFilter, agentFilter, statusFilter, priorityFilter].filter(Boolean).length}</span>}
                    </button>
                    <div className="filter-controls" id="board-filters" hidden={!filtersOpen}>
                      <select aria-label="Фильтр подпроекта" value={subprojectFilter} onChange={(e) => setSubprojectFilter(e.target.value)}>
                        <option value="">Все подпроекты</option><option value="unassigned">Без подпроекта</option>
                        {[...(board.subprojects || [])].sort((a, b) => subprojectPath(board.subprojects || [], a.id).localeCompare(subprojectPath(board.subprojects || [], b.id), "ru")).map((s) => <option key={s.id} value={s.id}>{subprojectPath(board.subprojects || [], s.id)} · с вложенными</option>)}
                      </select>
                      <select
                        aria-label="Фильтр типа задачи"
                        value={taskTypeFilter}
                        onChange={(e) => setTaskTypeFilter(e.target.value)}
                      >
                        <option value="">Все типы</option>
                        {Object.entries(taskTypes).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label="Фильтр исполнителя"
                        value={agentFilter}
                        onChange={(e) => setAgentFilter(e.target.value)}
                      >
                        <option value="">Все исполнители</option>
                        <option value="unassigned">Не назначен</option>
                        {bootstrap.agents.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label="Фильтр статуса"
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                      >
                        <option value="">Все статусы</option>
                        {statuses.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label="Фильтр приоритета"
                        value={priorityFilter}
                        onChange={(e) => setPriorityFilter(e.target.value)}
                      >
                        <option value="">Приоритет</option>
                        {Object.entries(priorities).map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="view-switch">
                      <button
                        className={!listView ? "selected" : ""}
                        onClick={() => setListView(false)}
                        aria-label="Показать доску"
                        aria-pressed={!listView}
                      >
                        <FolderKanban size={15} />
                      </button>
                      <button
                        className={listView ? "selected" : ""}
                        onClick={() => setListView(true)}
                        aria-label="Показать список"
                        aria-pressed={listView}
                      >
                        <List size={16} />
                      </button>
                    </div>
                  </div>
                  {filters && (
                    <div className="filter-summary">
                      <span role="status">Найдено задач: {tasks.length} из {board.tasks.length}</span>
                      {statusFilter && <span>{statuses.find(s => s.value === statusFilter)?.label}</span>}
                      {agentFilter && <span>{agentFilter === "unassigned" ? "Без исполнителя" : agentName(bootstrap.agents, agentFilter)}</span>}
                      {subprojectFilter && <span>{subprojectFilter === "unassigned" ? "Без подпроекта" : subprojectPath(board.subprojects || [], subprojectFilter)}</span>}
                      {taskTypeFilter && <span>{taskTypes[taskTypeFilter as keyof typeof taskTypes]}</span>}
                      {priorityFilter && <span>{priorities[priorityFilter as keyof typeof priorities]}</span>}
                      <button className="text-button" onClick={resetFilters}>
                        <X size={12} />
                        Сбросить фильтры
                      </button>
                    </div>
                  )}
                  {!board.tasks.length ? (
                    <div className="board-onboarding">
                      <FolderKanban size={28} aria-hidden="true" />
                      <h2>С чего начнём этот проект?</h2>
                      <p>Добавьте первую задачу: что нужно сделать, зачем и какой результат вы ожидаете.</p>
                      <button className="button primary" onClick={() => openEntity({ kind: "task", subproject_id: subprojectFilter === "unassigned" ? "" : subprojectFilter })}><Plus size={16} />Создать первую задачу</button>
                      <span>Назначение исполнителя сохраняет ответственность. Агент начинает работу в своём MCP-клиенте.</span>
                    </div>
                  ) : filters && !tasks.length ? (
                    <div className="empty-board">
                      <Search size={26} />
                      <h2>Задачи не найдены</h2>
                      <p>Попробуйте другой запрос или уберите фильтры.</p>
                      <button className="button secondary" onClick={resetFilters}>
                        Сбросить фильтры
                      </button>
                    </div>
                  ) : !listView ? (
                    <KanbanBoard key={board.project.id} tasks={tasks} agents={bootstrap.agents} subprojects={board.subprojects || []}
                      statusFilter={statusFilter as Status | ""} filterKey={[query.trim(), taskTypeFilter, subprojectFilter, agentFilter, statusFilter, priorityFilter].join("\n")}
                      onOpen={openTask} onMove={(task, status) => {
                        if (!canNavigate()) return;
                        if (routeTaskId !== null) navigateTask(null, "push", true);
                        setMove({ task, status });
                      }} />
                  ) : (
                    <div className="board is-list">
                      <div className="task-list">
                      {statuses.map(status => {
                        const group = tasks.filter(task => task.status === status.value);
                        if (!group.length) return null;
                        const GroupIcon = { backlog: Clock3, in_progress: Settings2, review: Search, done: CircleCheck, blocked: TriangleAlert }[status.value];
                        return <details className={`task-group ${status.value}`} key={status.value} open>
                          <summary><span className="task-group-status" aria-hidden="true"><GroupIcon size={21} /></span><h2>{status.label}</h2><span className="count">{group.length}</span><ChevronRight size={16} className="task-group-toggle" aria-hidden="true" /></summary>
                          <div className="list-items">
                        {group.map((task) => {
                          const agent = bootstrap.agents.find((item) => item.id === task.assignee_id);
                          return (
                            <button className={`task-card ${task.status}`} key={task.id} data-task-id={task.id} aria-current={routeTaskId === task.id ? "true" : undefined} onClick={() => openTask(task.id)}>
                              <div className="task-card-top">
                                <span className="task-id">{task.short_id}</span>
                                <PriorityMark priority={task.priority}/>
                              </div>
                              <div className="task-list-heading">
                                <h3>{task.title}</h3>
                                <span className="task-type-tag">{taskTypes[task.task_type || "other"]}</span>
                                {task.subproject_id && <span className="subproject-tag">{subprojectPath(board.subprojects || [], task.subproject_id)}</span>}
                              </div>
                              <div className="task-card-footer">
                                <span className="card-assignee">
                                  <Avatar agent={agent} small />
                                  <span>{agentName(bootstrap.agents, task.assignee_id)}</span>
                                </span>
                                <span className="card-meta" title={`Обновлено ${date(task.updated_at, true)}`}>
                                  <span>{date(task.updated_at)}</span>
                                  {task.depends_on.length > 0 && <GitBranch size={12} />}
                                </span>
                              </div>
                            </button>
                          );
                        })}
                          </div>
                        </details>;
                      })}
                      </div>
                      {!tasks.length && <div className="empty-board">
                        <h2>Пока нет задач</h2>
                        <p>Нажмите «Новая задача», чтобы добавить первую карточку.</p>
                      </div>}
                    </div>
                  )}
                  <div className="board-footnote">
                    <span>
                      <ShieldCheck size={13} />
                      Каждое изменение сохраняется с автором и причиной
                    </span>
                    <span>Время: Москва · UTC+3</span>
                  </div>
                </>
              )}
            </>
          )}
          {(view === "history" || view === "project_history") &&
            bootstrap.projects.length > 0 && (
              <div className="history-page">
                {view === "history" && (
                  <>
                    <div className="page-kicker">
                      <History size={14} />
                      ПАМЯТЬ ПРОСТРАНСТВА
                    </div>
                    <div className="page-heading">
                      <div>
                        <h1>
                          История работы<span className="heading-dot">.</span>
                        </h1>
                        <p>Что изменилось, кто это сделал и почему.</p>
                      </div>
                      <button
                        className="button secondary"
                        onClick={() => loadHistory(true)}
                      >
                        <RefreshCw size={15} />
                        Обновить историю
                      </button>
                    </div>
                  </>
                )}
                <div className="history-toolbar">
                  {view === "project_history" && <button className="button secondary" disabled={historyLoading} onClick={() => loadHistory(true)}><RefreshCw size={15} />Обновить историю</button>}
                  <div className="search-field">
                    <Search size={16} />
                    <input
                      aria-label="Поиск в истории"
                      placeholder="Поиск по автору, действию и причине…"
                      value={historyQuery}
                      onChange={(e) => setHistoryQuery(e.target.value)}
                    />
                  </div>
                  <select
                    aria-label="Автор события"
                    value={historyAgent}
                    onChange={(e) => setHistoryAgent(e.target.value)}
                  >
                    <option value="">Все авторы</option>
                    {bootstrap.agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                  <span className="muted">
                    {history.length} событий загружено · поиск по загруженным
                  </span>
                </div>
                <Events
                  events={history.filter(
                    (e) =>
                      (!historyAgent || e.actor_id === historyAgent) &&
                      (!historyQuery ||
                        `${e.actor_name} ${e.action} ${actionLabels[e.action]} ${e.reason}`
                          .toLocaleLowerCase("ru")
                          .includes(historyQuery.toLocaleLowerCase("ru"))),
                  )}
                  agents={bootstrap.agents}
                  onTask={openTask}
                />
                {hasMore && (
                  <button
                    className="button secondary wide"
                    disabled={historyLoading}
                    onClick={() => loadHistory()}
                  >
                    {historyLoading ? "Загружаем…" : "Загрузить более ранние события"}
                  </button>
                )}
                <p className="scope-note">
                  История показывает записанные действия и причины. Проверки —
                  сообщения их авторов; сам dashboard не исполняет команды из
                  записей.
                </p>
              </div>
            )}
        </main>
      </div>
      <div
        className={`toast ${toast ? "visible" : ""}`}
        role="status"
        aria-live="polite"
      >
        {toast && (
          <>
            <Check size={16} />
            {toast}
          </>
        )}
      </div>
      {modal && (
        <EntityForm
          modal={modal}
          board={board}
          agents={bootstrap.agents}
          onClose={() => setModal(null)}
          onSaved={saved}
        />
      )}
      {move && <MoveTaskDialog key={`${move.task.id}:${move.status}`} task={move.task} status={move.status}
        onClose={() => setMove(null)} onMoved={moved}
        onOpen={() => { navigateTask(move.task.id, "push", true); }} />}
      {detail && drawerBoard && (
        <TaskDrawer
          key={detail.task.id}
          detail={detail}
          board={drawerBoard}
          agents={bootstrap.agents}
          onClose={closeDetail}
          onRefresh={updateDetail}
          onChanged={changed}
          onCopyLink={copyTaskLink}
          docked={view === "board"}
        />
      )}
      {routeTaskId !== null && !detail && <Dialog title={taskError ? "Не удалось открыть задачу" : "Открываем задачу…"} onClose={closeDetail} drawer docked={view === "board"}>
        {taskError ? <><p role="alert">{taskError}</p><div className="form-actions"><button className="button secondary" onClick={() => { setTaskError(""); setTaskAttempt(value => value + 1); }}>Повторить</button><button className="button primary" onClick={closeDetail}>Закрыть сообщение</button></div></>
          : <p role="status">Загружаем карточку и её проект…</p>}
      </Dialog>}
    </div>
  );
}
