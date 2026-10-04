import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Blocks,
  Check,
  CheckCheck,
  ChevronRight,
  Circle,
  Clipboard,
  Code2,
  FileCode2,
  FolderKanban,
  GitBranch,
  History,
  LayoutDashboard,
  List,
  Menu,
  PanelTop,
  Pencil,
  Plug,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
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
  type Agent,
  type Board,
  type Bootstrap,
  type Connectors,
  type Detail,
  type Event,
  type Project,
  type Task,
  type Status,
} from "./api";
import KanbanBoard from "./KanbanBoard";

type View = "overview" | "board" | "project_history" | "history" | "connectors";
type Modal =
  | { kind: "project"; project?: Project }
  | { kind: "task" };
const emptyBootstrap: Bootstrap = { projects: [], agents: [], activity: [] };
const text = (data: FormData, key: string) =>
  String(data.get(key) || "").trim();
const agentName = (agents: Agent[], id: string | null) =>
  agents.find((a) => a.id === id)?.name || "Не назначен";
const kindLabel = (kind: string) =>
  kind === "human" ? "Человек" : kind === "claude" ? "Claude Code" : "Codex";
const fieldLabels:Record<string,string> = {title:'Название',description:'Описание',rationale:'Зачем',acceptance_criteria:'Критерии готовности',status:'Статус',priority:'Приоритет',task_type:'Тип задачи',assignee_id:'Исполнитель',section_id:'Раздел',depends_on:'Зависимости',claim_owner_id:'Владелец'};

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
function Dialog({
  title,
  children,
  onClose,
  drawer = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  drawer?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    label = useId(),
    closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      ref.current?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={drawer ? "drawer" : "modal"}
      aria-labelledby={label}
      onCancel={(event) => {
        event.preventDefault();
        closeRef.current();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) closeRef.current();
      }}
    >
      <div className="dialog-inner">
        <div className="dialog-head">
          <h2 id={label}>{title}</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Закрыть"
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
  return <Dialog title="Переместить задачу" onClose={() => { if (!busy) onClose(); }}>
    <form className="entity-form" onSubmit={submit}>
      <p className="move-task-title"><span>{current.short_id}</span>{current.title}</p>
      <div className="move-summary"><StatusPill status={current.status} /><ArrowRight size={17} aria-hidden="true" /><StatusPill status={status} /></div>
      <Field label="Почему перемещаем задачу" name="reason" area required hint="Причина и смена статуса сохранятся в истории. Карточка переместится после подтверждения." />
      {error && <ErrorBox message={error} onRefresh={stale && !busy ? refreshConflict : undefined} />}
      <div className="form-footer move-footer">
        <button type="button" className="text-button" disabled={busy} onClick={onOpen}>Открыть задачу</button>
        <button type="button" className="button secondary" disabled={busy} onClick={onClose}>Отмена</button>
        <button type="submit" className="button primary" disabled={busy || stale || current.status === status}>{busy ? "Сохраняем…" : "Переместить"}</button>
      </div>
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
  const isProject = modal.kind === "project";
  const item = isProject ? modal.project : undefined;
  const title = isProject
    ? item
      ? "Изменить проект"
      : "Новый проект"
    : "Новая задача";
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
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
      } else {
        const task = await api<Task>("/tasks", {
          method: "POST",
          body: JSON.stringify({
            project_id: board!.project.id,
            task_type: text(d, "task_type"),
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
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={title} onClose={onClose}>
      <form onSubmit={submit} className="entity-form">
        <p className="form-intro">
          {isProject
            ? "Отдельная доска, контекст и история для одного проекта."
            : "Выберите тип работы, опишите результат и зачем он нужен. Агент получит этот контекст вместе с задачей."}
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
        ) : (
          <>
            <Field label="Название задачи" name="title" required />
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
              <Select label="Исполнитель" name="assignee_id">
                <option value="">Не назначен</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
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
                : "Добавление задачи в план проекта"
          }
        />
        {error && <ErrorBox message={error} />}
        <div className="form-footer">
          <button type="button" className="button secondary" onClick={onClose}>
            Отмена
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Сохраняем…" : item ? "Сохранить изменения" : "Создать"}
            <ArrowRight size={16} />
          </button>
        </div>
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
                                assignee_id: "Исполнитель",
                                section_id: "Раздел",
                                body: "Запись",
                                metadata: "Файлы и проверки",
                                depends_on: "Зависимости",
                                name: "Название",
                                claim_owner_id: "Владелец",
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
    return statuses.find((s) => s.value === value)?.label || String(value);
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
}: {
  detail: Detail;
  board: Board;
  agents: Agent[];
  onClose: () => void;
  onRefresh: () => Promise<Detail | null>;
  onChanged: () => Promise<void>;
}) {
  const [edit, setEdit] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [noteKind, setNoteKind] = useState("progress");
  const task = detail.task,
    key = useRef(crypto.randomUUID()),
    noteKey = useRef(crypto.randomUUID()),
    editBaseline = useRef(task),
    editButton = useRef<HTMLButtonElement>(null);
  const [saveVersion, setSaveVersion] = useState(task.version);
  function beginEdit() {
    editBaseline.current = task;
    setSaveVersion(task.version);
    setError("");
    setEdit(true);
    editButton.current?.focus();
  }
  function finishEdit() {
    editButton.current?.focus();
    setEdit(false);
    setError("");
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
      await onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const assignee = agents.find((a) => a.id === task.assignee_id);
  return (
    <Dialog title={task.short_id} onClose={onClose} drawer>
      <div className="drawer-body">
        <div className="drawer-breadcrumb">
          <FolderKanban size={13} />
          <span>{board.project.name}</span>
          <ChevronRight size={12} />
          <span>{taskTypes[task.task_type || "other"]}</span>
        </div>
        <div className="task-detail-heading">
          <h3>{task.title}</h3>
          <button
            ref={editButton}
            className="icon-button"
            onClick={() => {
              if (edit) finishEdit();
              else beginEdit();
            }}
            aria-label={
              edit ? "Отменить редактирование" : "Редактировать задачу"
            }
          >
            <Pencil size={17} />
          </button>
        </div>
        <div className="task-properties">
          <StatusPill status={task.status} />
          <span className="task-type-tag">{taskTypes[task.task_type || "other"]}</span>
          <span className={`priority ${task.priority}`}>
            <span className="priority-bars">▂▄▆</span>
            {priorities[task.priority]}
          </span>
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
          <form onSubmit={update} className="edit-form">
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
              <Select
                label="Исполнитель"
                name="assignee_id"
                defaultValue={task.assignee_id || ""}
              >
                <option value="">Не назначен</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
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
                onClick={finishEdit}
              >
                Отмена
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? "Сохраняем…" : "Сохранить"}
              </button>
            </div>
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
            <div className="detail-section">
              <h4>
                <CheckCheck size={15} />
                Критерии готовности
              </h4>
              <p>
                {task.acceptance_criteria ||
                  "Критерии не заданы. Добавьте их перед завершением."}
              </p>
            </div>
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
            <button className="button secondary wide" onClick={beginEdit}>
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
            <article className={`note ${n.kind}`} key={n.id}>
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
          <form className="note-form" onSubmit={note}>
            <div className="field">
              <label htmlFor={`note-kind-${task.id}`}>Добавить запись</label>
              <select id={`note-kind-${task.id}`} value={noteKind} onChange={event => setNoteKind(event.target.value)}>
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
  useEffect(() => {
    api<Connectors>("/connectors")
      .then(setInfo)
      .catch((e) => setError(e.message));
  }, []);
  async function copy(value: string, id: string) {
    try {
      await navigator.clipboard.writeText(value);
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
      setCredential(
        await api("/agents", {
          method: "POST",
          body: JSON.stringify({
            name: text(d, "name"),
            kind: text(d, "kind"),
            reason: text(d, "reason"),
          }),
        }),
      );
      setNewAgent(false);
      notify("Агент создан. Сохраните его токен.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const entries =
    info &&
    (["codex", "claude"] as const).map((kind) => {
      const args = [
        info.mcp_script,
        "--agent",
        kind,
        "--credentials",
        info.credentials_file,
        info.desktop ? "--data-dir" : "--url",
        info.desktop ? info.data_dir : info.base_url,
      ];
      const config =
        kind === "codex"
          ? `[mcp_servers.agentboard]\ncommand = ${JSON.stringify(info.python_command)}\nargs = ${JSON.stringify(args)}\nstartup_timeout_sec = 20\ntool_timeout_sec = 60`
          : JSON.stringify(
              {
                mcpServers: {
                  agentboard: {
                    type: "stdio",
                    command: info.python_command,
                    args,
                  },
                },
              },
              null,
              2,
            );
      return { kind, config };
    });
  return (
    <div className="connectors-page">
      <div className="page-kicker">
        <Plug size={15} />
        ОБЩИЙ КОНТЕКСТ
      </div>
      <div className="page-heading">
        <div>
          <h1>
            Подключите ваших агентов<span className="heading-dot">.</span>
          </h1>
          <p>
            Codex и Claude Code работают на одной доске. Каждое действие
            оставляет след.
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
            Коннектор общается с локальным API. Ключи OpenAI и Anthropic для
            dashboard не нужны.
          </p>
        </div>
        <span className="local-badge">LOCAL / MCP</span>
      </div>
      <div className="connector-grid">
        {entries?.map(({ kind, config }) => {
          const agent = agents.find((a) => a.id === kind);
          return (
            <article className={`connector-card ${kind}`} key={kind}>
              <div className="connector-title">
                <Avatar agent={agent} />
                <div>
                  <h2>{kindLabel(kind)}</h2>
                  <span>Стандартный MCP · stdio</span>
                </div>
                <span className="client-tag">
                  {kind === "codex" ? "01" : "02"}
                </span>
              </div>
              <div className="connection-status">
                <span
                  className={`status-dot ${agent?.last_seen ? "seen" : ""}`}
                />
                {agent?.last_seen
                  ? `Последний запрос ${date(agent.last_seen)}`
                  : "Запросов пока нет"}
              </div>
              <p>
                Добавьте конфигурацию в{" "}
                <code>
                  {kind === "codex" ? ".codex/config.toml" : ".mcp.json"}
                </code>{" "}
                нужного проекта.
              </p>
              <div className="code-block">
                <div className="code-label">
                  {kind === "codex" ? "TOML" : "JSON"}
                  <button
                    onClick={() => copy(config, kind)}
                    aria-label={`Скопировать конфигурацию ${kindLabel(kind)}`}
                  >
                    {copied === kind ? (
                      <Check size={15} />
                    ) : (
                      <Clipboard size={15} />
                    )}{" "}
                    {copied === kind ? "Скопировано" : "Копировать"}
                  </button>
                </div>
                <pre>{config}</pre>
              </div>
              <p className="connector-hint">
                {kind === "codex"
                  ? "Откройте доверенный проект в новой сессии Codex и проверьте /mcp."
                  : "Откройте проект в Claude Code, разрешите project MCP и проверьте /mcp."}
              </p>
            </article>
          );
        })}
      </div>
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
            <Field label="Имя агента" name="name" required />
            <Select label="Клиент" name="kind" defaultValue="codex">
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
              вместо --credentials, сохранив --agent codex или --agent claude. Идентичность определяется токеном
              на сервере.
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

export default function App() {
  const [bootstrap, setBootstrap] = useState(emptyBootstrap),
    [board, setBoard] = useState<Board | null>(null),
    [projectId, setProjectId] = useState<string | null>(() =>
      localStorage.getItem("agentboard.project"),
    ),
    [view, setView] = useState<View>("board"),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [syncAt, setSyncAt] = useState<string | null>(null),
    [modal, setModal] = useState<Modal | null>(null),
    [move, setMove] = useState<{ task: Task; status: Status } | null>(null),
    [detail, setDetail] = useState<Detail | null>(null),
    [drawerBoard, setDrawerBoard] = useState<Board | null>(null),
    [toast, setToast] = useState(""),
    [mobileMenu, setMobileMenu] = useState(false);
  const [query, setQuery] = useState(""),
    [taskTypeFilter, setTaskTypeFilter] = useState(""),
    [agentFilter, setAgentFilter] = useState(""),
    [statusFilter, setStatusFilter] = useState(""),
    [priorityFilter, setPriorityFilter] = useState(""),
    [listView, setListView] = useState(false),
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
    detailId = useRef<string|null>(null),
    sidebarRef = useRef<HTMLElement>(null),
    menuOpener = useRef<HTMLButtonElement>(null),
    toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const historySequence = useRef(0),
    historyScope = useRef(""),
    historyBusy = useRef(false);
  historyScope.current = `${view}:${projectId}`;
  projectRef.current = projectId;
  useEffect(()=>{
    if(!mobileMenu)return;
    const sidebar=sidebarRef.current;
    const controls=()=>Array.from(sidebar?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, select, [tabindex="0"]')||[]);
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
      if (id !== projectRef.current) setProjectId(id);
      if (id) {
        const result = await api<Board>(`/projects/${id}`);
        if (sequence !== loadSequence.current) return;
        setBoard(result);
      } else setBoard(null);
      setError("");
      setSyncAt(new Date().toISOString());
    } catch (e) {
      if (sequence === loadSequence.current) setError((e as Error).message);
    } finally {
      if (sequence === loadSequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    if (projectId) localStorage.setItem("agentboard.project", projectId);
    refresh(projectId);
    const interval = setInterval(() => {
      if (!document.hidden) refresh(projectRef.current, true);
    }, 5000);
    return () => clearInterval(interval);
  }, [projectId]);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
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
    target?.focus();
  }, [move]);
  async function loadHistory(reset = false) {
    if (historyBusy.current && !reset) return;
    const scope = historyScope.current,
      sequence = ++historySequence.current;
    historyBusy.current = true;
    setHistoryLoading(true);
    try {
      const result = await api<{ events: Event[]; next_cursor: number }>(
        `/history?after=${reset ? 0 : cursor}&limit=100${view === "project_history" && projectId ? `&project_id=${projectId}` : ""}`,
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
    setProjectId(id);
    setView("board");
    setQuery("");
    setTaskTypeFilter("");
    setAgentFilter("");
    setStatusFilter("");
    setPriorityFilter("");
    setMobileMenu(false);
    setMove(null);
    closeDetail();
  }
  function closeDetail() {
    detailSequence.current++;
    detailId.current=null;
    setDetail(null);
    setDrawerBoard(null);
  }
  async function openTask(id: string) {
    const sequence=++detailSequence.current;
    detailId.current=id;
    try {
      const result = await api<Detail>(`/tasks/${id}`);
      const context = await api<Board>(`/projects/${result.task.project_id}`);
      if(sequence!==detailSequence.current||detailId.current!==id)return;
      setDrawerBoard(context);
      setDetail(result);
    } catch (e) {
      if(sequence===detailSequence.current)notify((e as Error).message);
    }
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
      setProjectId(id);
      setView("board");
    }
    await refresh(id || projectRef.current, true);
    if (taskId) await openTask(taskId);
    notify("Сохранено в пространстве");
  }
  async function exportProject() {
    if (!board) return;
    try {
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
      a.download = `agentboard-${board.project.id}.json`;
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
    setAgentFilter("");
    setStatusFilter("");
    setPriorityFilter("");
  }
  const filters = !!(
    query ||
    taskTypeFilter ||
    agentFilter ||
    (listView && statusFilter) ||
    priorityFilter
  );
  const tasks =
    board?.tasks.filter(
      (t) =>
        (!taskTypeFilter || (t.task_type || "other") === taskTypeFilter) &&
        (!agentFilter ||
          (agentFilter === "unassigned"
            ? !t.assignee_id
            : t.assignee_id === agentFilter)) &&
        (!listView || !statusFilter || t.status === statusFilter) &&
        (!priorityFilter || t.priority === priorityFilter) &&
        (!query ||
          `${t.short_id} ${t.title} ${t.description} ${t.rationale} ${taskTypes[t.task_type || "other"]}`
            .toLocaleLowerCase("ru")
            .includes(query.toLocaleLowerCase("ru"))),
    ) || [];
  const isProjectView = view === "board" || view === "project_history";
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
          <span className="brand-mark">
            <Blocks size={22} />
          </span>
          <span>
            agentboard<span className="brand-period">.</span>
          </span>
        </button>
        <div className="workspace-switch">
          <span className="workspace-icon">A</span>
          <div>
            <strong>Мое пространство</strong>
            <span>Человек + агенты</span>
          </div>
          <span className="local-indicator" title="Локальное пространство" />
        </div>
        <div className="nav-caption">ПРОСТРАНСТВО</div>
        <nav aria-label="Рабочее пространство">
          <button
            className={`nav-item ${view === "overview" ? "active" : ""}`}
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
            onClick={() => setModal({ kind: "project" })}
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
            onClick={() => setModal({ kind: "project" })}
          >
            <Plus size={14} />
            Новый проект
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="local-server">
            <span className={`status-dot ${error ? "offline" : "seen"}`} />
            <span>{error ? "Сервер недоступен" : "Локальный сервер"}</span>
            <span className="server-port">API</span>
          </div>
          <div className="profile">
            <Avatar agent={bootstrap.agents.find((a) => a.kind === "human")} />
            <div>
              <strong>Вы и ваши агенты</strong>
              <span>Общая память работы</span>
            </div>
            <span className="profile-badge">01</span>
          </div>
        </div>
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
            <span className={`sync-status ${error ? "error" : ""}`}>
              <span className="status-dot" />
              {error
                ? "Нет связи"
                : syncAt
                  ? `Обновлено ${new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", hour: "2-digit", minute: "2-digit" }).format(new Date(syncAt))}`
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
          className={`main-content ${isProjectView ? "project-content" : ""}`}
        >
          {error && <ErrorBox message={error} onRefresh={() => refresh()} />}
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
                  onClick={() => setModal({ kind: "project" })}
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
                    Codex + Claude Code
                  </span>
                </div>
              </div>
            )}
          {view === "connectors" && (
            <ConnectorView agents={bootstrap.agents} notify={notify} />
          )}
          {view === "overview" && bootstrap.projects.length > 0 && (
            <>
              <div className="page-kicker">
                <LayoutDashboard size={14} />
                РАБОЧЕЕ ПРОСТРАНСТВО
              </div>
              <div className="page-heading">
                <div>
                  <h1>
                    Вся работа на виду<span className="heading-dot">.</span>
                  </h1>
                  <p>Проекты, агенты и решения — в одном пространстве.</p>
                </div>
                <button
                  className="button primary"
                  onClick={() => setModal({ kind: "project" })}
                >
                  <Plus size={16} />
                  Новый проект
                </button>
              </div>
              <div className="overview-grid">
                {bootstrap.projects.map((p) => (
                  <button
                    className="project-overview"
                    key={p.id}
                    onClick={() => selectProject(p.id)}
                  >
                    <span
                      className="project-overview-icon"
                      style={{ color: p.color }}
                    >
                      <FolderKanban size={23} />
                    </span>
                    <ArrowUpRight className="overview-arrow" size={18} />
                    <h2>{p.name}</h2>
                    <p>
                      {p.description || "Контекст проекта еще не добавлен."}
                    </p>
                    <footer>
                      <span>Открыть доску</span>
                      <span>v{p.version}</span>
                    </footer>
                  </button>
                ))}
              </div>
              <div className="overview-activity">
                <div className="subheading">
                  <h2>Последние действия</h2>
                  <button
                    className="text-button"
                    onClick={() => setView("history")}
                  >
                    Вся история
                    <ArrowRight size={14} />
                  </button>
                </div>
                <Events
                  events={bootstrap.activity.slice(0, 10)}
                  agents={bootstrap.agents}
                  onTask={openTask}
                />
              </div>
            </>
          )}
          {isProjectView && board && (
            <>
              <div className="project-heading">
                <div>
                  <div className="project-kicker">
                    <span
                      className="project-color"
                      style={{ background: project?.color || "#b4f4a5" }}
                    />
                    ПРОЕКТ
                    <span className="project-version">v{project?.version}</span>
                  </div>
                  <h1>
                    {project?.name}
                    <button
                      className="icon-button"
                      aria-label="Редактировать проект"
                      onClick={() => setModal({ kind: "project", project })}
                    >
                      <Pencil size={16} />
                    </button>
                  </h1>
                  <p>
                    {project?.description ||
                      "Добавьте цель проекта, чтобы агенты понимали контекст работы."}
                  </p>
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
                    onClick={() => setModal({ kind: "task" })}
                  >
                    <Plus size={17} />
                    Новая задача
                  </button>
                </div>
              </div>
              <div className="project-stats">
                <span>
                  <Circle size={13} />
                  <strong>{board.tasks.length}</strong> задач
                </span>
                <span className="stat-active">
                  <Activity size={13} />
                  <strong>
                    {
                      board.tasks.filter((t) => t.status === "in_progress")
                        .length
                    }
                  </strong>{" "}
                  в работе
                </span>
                <span className="stat-review">
                  <ShieldCheck size={13} />
                  <strong>
                    {board.tasks.filter((t) => t.status === "review").length}
                  </strong>{" "}
                  на проверке
                </span>
                <span className="stat-blocked">
                  <GitBranch size={13} />
                  <strong>
                    {board.tasks.filter((t) => t.status === "blocked").length}
                  </strong>{" "}
                  блокировок
                </span>
              </div>
              <div className="project-tabs">
                <div className="tabs-nav">
                  <button
                    className={view === "board" ? "selected" : ""}
                    onClick={() => setView("board")}
                  >
                    <FolderKanban size={15} />
                    Доска<span className="count">{board.tasks.length}</span>
                  </button>
                  <button
                    className={view === "project_history" ? "selected" : ""}
                    onClick={() => setView("project_history")}
                  >
                    <History size={15} />
                    История
                  </button>
                </div>
                <div className="project-agents">
                  {bootstrap.agents
                    .filter((a) => a.kind !== "human")
                    .slice(0, 4)
                    .map((a) => (
                      <span title={a.name} key={a.id}>
                        <Avatar agent={a} small />
                      </span>
                    ))}
                  <button
                    className="text-button"
                    onClick={() => setView("connectors")}
                  >
                    Агенты
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
              {view === "board" && (
                <>
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
                    <div className="filter-controls">
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
                      {listView && <select
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
                      </select>}
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
                      <span>Найдено задач: {tasks.length}</span>
                      <button className="text-button" onClick={resetFilters}>
                        <X size={12} />
                        Сбросить фильтры
                      </button>
                    </div>
                  )}
                  {filters && !tasks.length ? (
                    <div className="empty-board">
                      <Search size={26} />
                      <h2>Задачи не найдены</h2>
                      <p>Попробуйте другой запрос или уберите фильтры.</p>
                      <button className="button secondary" onClick={resetFilters}>
                        Сбросить фильтры
                      </button>
                    </div>
                  ) : !listView ? (
                    <KanbanBoard key={board.project.id} tasks={tasks} agents={bootstrap.agents}
                      onOpen={openTask} onMove={(task, status) => setMove({ task, status })} />
                  ) : (
                    <div className="board is-list">
                      <div className="task-list"><div className="list-items">
                        {tasks.map((task) => {
                          const agent = bootstrap.agents.find((item) => item.id === task.assignee_id);
                          return (
                            <button className={`task-card ${task.status}`} key={task.id} onClick={() => openTask(task.id)}>
                              <div className="task-card-top">
                                <span className="task-id">{task.short_id}</span>
                                <span className={`priority-symbol ${task.priority}`} title={`Приоритет: ${priorities[task.priority]}`}>
                                  <span aria-hidden="true">▂▄▆</span>
                                  <span className="sr-only">{priorities[task.priority]}</span>
                                </span>
                              </div>
                              <div className="task-list-heading">
                                <h3>{task.title}</h3>
                                <span className="task-type-tag">{taskTypes[task.task_type || "other"]}</span>
                              </div>
                              <StatusPill status={task.status} />
                              <div className="task-card-footer">
                                <span className="card-assignee">
                                  <Avatar agent={agent} small />
                                  <span>{agentName(bootstrap.agents, task.assignee_id)}</span>
                                </span>
                                <span className="card-meta" title={`Обновлено ${date(task.updated_at, true)}`}>
                                  <span>v{task.version}</span>
                                  {task.depends_on.length > 0 && <GitBranch size={12} />}
                                </span>
                              </div>
                            </button>
                          );
                        })}
                      </div></div>
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
                    {history.length} событий загружено
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
                    onClick={() => loadHistory()}
                  >
                    Загрузить следующие события
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
        onOpen={() => { setMove(null); openTask(move.task.id); }} />}
      {detail && drawerBoard && (
        <TaskDrawer
          key={detail.task.id}
          detail={detail}
          board={drawerBoard}
          agents={bootstrap.agents}
          onClose={closeDetail}
          onRefresh={updateDetail}
          onChanged={changed}
        />
      )}
    </div>
  );
}
