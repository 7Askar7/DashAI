import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowRightLeft, GripVertical, Link2 } from "lucide-react";
import {
  priorities,
  statuses,
  type Agent,
  type Section,
  type Status,
  type Task,
} from "./api";
import "./kanban.css";

type Props = {
  tasks: Task[];
  agents: Agent[];
  sections: Section[];
  onOpen: (id: string) => void;
  onMove: (task: Task, status: Status) => void;
};

export default function KanbanBoard({
  tasks,
  agents,
  sections,
  onOpen,
  onMove,
}: Props) {
  const [activeStatus, setActiveStatus] = useState<Status>("backlog");
  const [dragEnabled, setDragEnabled] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropStatus, setDropStatus] = useState<Status | null>(null);
  const draggedTask = useRef<string | null>(null);
  const agentsById = new Map(agents.map((agent) => [agent.id, agent]));
  const sectionsById = new Map(
    sections.map((section) => [section.id, section]),
  );

  function finishDrag() {
    draggedTask.current = null;
    setDragId(null);
    setDropStatus(null);
  }

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 761px) and (pointer: fine)");
    const update = () => {
      setDragEnabled(desktop.matches);
      if (!desktop.matches) finishDrag();
    };
    update();
    desktop.addEventListener("change", update);
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") finishDrag();
    };
    window.addEventListener("keydown", escape);
    window.addEventListener("blur", finishDrag);
    return () => {
      desktop.removeEventListener("change", update);
      window.removeEventListener("keydown", escape);
      window.removeEventListener("blur", finishDrag);
    };
  }, []);

  return (
    <div className="kanban-workspace">
      <nav className="kanban-status-nav" aria-label="Статус задач">
        {statuses.map((status) => (
          <button
            type="button"
            key={status.value}
            aria-pressed={activeStatus === status.value}
            onClick={() => setActiveStatus(status.value)}
          >
            <span>{status.label}</span>
            <span className="kanban-count">
              {tasks.filter((task) => task.status === status.value).length}
            </span>
          </button>
        ))}
      </nav>
      <div
        className="kanban-scroll"
        role="region"
        tabIndex={0}
        aria-label="Канбан-доска по статусам"
      >
        <div className="kanban-columns">
          {statuses.map((status) => {
            const columnTasks = tasks.filter(
              (task) => task.status === status.value,
            );
            return (
              <section
                key={status.value}
                data-status={status.value}
                aria-label={`${status.label}: ${columnTasks.length}`}
                style={{ "--kanban-status": status.color } as CSSProperties}
                className={`kanban-column ${status.value}${activeStatus === status.value ? " is-active" : ""}${dropStatus === status.value ? " is-drop-target" : ""}`}
                onDragOver={(event) => {
                  if (
                    !draggedTask.current ||
                    !tasks.some((task) => task.id === draggedTask.current)
                  )
                    return;
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                  setDropStatus(status.value);
                }}
                onDragLeave={(event) => {
                  if (
                    !event.currentTarget.contains(
                      event.relatedTarget as Node | null,
                    )
                  )
                    setDropStatus(null);
                }}
                onDrop={(event) => {
                  // Only this board's drag can request a move; ignore external payloads.
                  const task = tasks.find(
                    (task) => task.id === draggedTask.current,
                  );
                  if (task) event.preventDefault();
                  finishDrag();
                  if (task && task.status !== status.value)
                    onMove(task, status.value);
                }}
              >
                <header className="kanban-column-header">
                  <span className="kanban-status-dot" aria-hidden="true" />
                  <h3>{status.label}</h3>
                  <span className="kanban-count">{columnTasks.length}</span>
                </header>
                <div className="kanban-cards">
                  {columnTasks.map((task) => {
                    const agent = task.assignee_id
                      ? agentsById.get(task.assignee_id)
                      : undefined;
                    const section = sectionsById.get(task.section_id);
                    return (
                      <article
                        key={task.id}
                        data-task-id={task.id}
                        className={`kanban-card${dragId === task.id ? " is-dragging" : ""}`}
                        draggable={dragEnabled}
                        onDragStart={(event) => {
                          if (
                            !dragEnabled ||
                            (event.target as HTMLElement).closest("select")
                          ) {
                            event.preventDefault();
                            return;
                          }
                          draggedTask.current = task.id;
                          setDragId(task.id);
                          event.dataTransfer.effectAllowed = "move";
                          event.dataTransfer.setData(
                            "text/plain",
                            task.short_id,
                          );
                        }}
                        onDragEnd={finishDrag}
                      >
                        <button
                          type="button"
                          className="kanban-card-open"
                          aria-label={`Открыть задачу ${task.short_id}: ${task.title}`}
                          onClick={() => onOpen(task.id)}
                        >
                          <span className="kanban-card-top">
                            <span className="kanban-task-id">
                              {task.short_id}
                            </span>
                            <span
                              className={`kanban-priority ${task.priority}`}
                            >
                              {priorities[task.priority]}
                            </span>
                            <GripVertical
                              className="kanban-drag-handle"
                              size={15}
                              aria-hidden="true"
                            />
                          </span>
                          <span
                            className="kanban-card-title"
                            title={task.title}
                          >
                            {task.title}
                          </span>
                          {section && (
                            <span
                              className="kanban-section-tag"
                              title={section.title}
                            >
                              {section.title}
                            </span>
                          )}
                          <span className="kanban-card-meta">
                            <span
                              className={`kanban-agent-mark ${agent?.kind || "unassigned"}`}
                              aria-hidden="true"
                            >
                              {agent
                                ? agent.name.slice(0, 1).toUpperCase()
                                : "—"}
                            </span>
                            <span
                              className="kanban-assignee"
                              title={agent?.name}
                            >
                              {agent?.name || "Не назначена"}
                            </span>
                            {task.depends_on.length > 0 && (
                              <span
                                className="kanban-dependencies"
                                aria-label={`Зависимостей: ${task.depends_on.length}`}
                              >
                                <Link2 size={13} aria-hidden="true" />
                                {task.depends_on.length}
                              </span>
                            )}
                          </span>
                        </button>
                        <label className="kanban-move">
                          <ArrowRightLeft size={13} aria-hidden="true" />
                          <span>Переместить</span>
                          <select
                            aria-label={`Переместить ${task.short_id}: ${task.title}`}
                            value={task.status}
                            draggable={false}
                            onChange={(event) => {
                              const next = event.target.value as Status;
                              if (next !== task.status) onMove(task, next);
                            }}
                          >
                            {statuses.map((item) => (
                              <option key={item.value} value={item.value}>
                                {item.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      </article>
                    );
                  })}
                  {columnTasks.length === 0 && (
                    <div className="kanban-empty">
                      <span>Пока нет задач</span>
                      <small className="kanban-drop-hint">
                        Перетащите карточку в эту колонку
                      </small>
                    </div>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
