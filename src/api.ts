export type Status = "backlog" | "in_progress" | "review" | "done" | "blocked";
export type Priority = "urgent" | "high" | "medium" | "low";
export type Agent = {
  id: string;
  name: string;
  kind: "human" | "codex" | "claude";
  last_seen: string | null;
  created_at: string;
};
export type Project = {
  id: string;
  name: string;
  description: string;
  repository: string;
  color: string;
  version: number;
  created_at: string;
  updated_at: string;
};
export type Section = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  position: number;
  version: number;
  created_at: string;
};
export type Task = {
  id: string;
  short_id: string;
  project_id: string;
  section_id: string;
  title: string;
  description: string;
  rationale: string;
  acceptance_criteria: string;
  status: Status;
  priority: Priority;
  assignee_id: string | null;
  depends_on: string[];
  version: number;
  claim_owner_id: string | null;
  claim_expires_at: string | null;
  created_at: string;
  updated_at: string;
};
export type Event = {
  id: number;
  project_id: string | null;
  task_id: string | null;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_id: string;
  actor_name: string;
  actor_kind: string;
  reason: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
  session_id: string | null;
};
export type Note = {
  id: string;
  task_id: string;
  kind: string;
  body: string;
  actor_id: string;
  created_at: string;
  metadata?: Record<string, unknown>;
};
export type Board = {
  project: Project;
  sections: Section[];
  tasks: Task[];
  activity: Event[];
};
export type Detail = { task: Task; events: Event[]; notes: Note[] };
export type Bootstrap = {
  projects: Project[];
  agents: Agent[];
  activity: Event[];
};
export type Connectors = {
  base_url: string;
  python_command: string;
  mcp_script: string;
  credentials_file: string;
  data_dir: string;
  desktop: boolean;
  agents: Agent[];
};

export const statuses: { value: Status; label: string; color: string }[] = [
  { value: "backlog", label: "Очередь", color: "#9da8b7" },
  { value: "in_progress", label: "В работе", color: "#80bfff" },
  { value: "review", label: "Проверка", color: "#c5a9ff" },
  { value: "done", label: "Готово", color: "#b4f4a5" },
  { value: "blocked", label: "Блокировка", color: "#fba7a7" },
];
export const priorities: Record<Priority, string> = {
  urgent: "Срочный",
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};
export const noteLabels: Record<string, string> = {
  progress: "Ход работы",
  decision: "Решение",
  evidence: "Проверка",
  comment: "Комментарий",
  change: "Правка кода",
};
export const actionLabels: Record<string, string> = {
  "project.created": "создал проект",
  "project.updated": "изменил проект",
  "section.created": "создал раздел",
  "section.updated": "изменил раздел",
  "task.created": "создал задачу",
  "task.updated": "изменил задачу",
  "task.claimed": "взял задачу",
  "task.released": "освободил задачу",
  "note.created": "добавил запись",
  "change.logged": "записал правку",
  "agent.created": "добавил агента",
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Dashboard-Client": "browser",
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      0,
      "Нет связи с сервером. Проверьте, что Agentboard запущен, и повторите сохранение.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : "Проверьте заполненные поля и повторите действие.";
    throw new ApiError(
      response.status,
      response.status === 409 && detail.startsWith("Объект уже изменен.")
        ? `Конфликт изменений. ${detail} Обновите данные перед повторным сохранением.`
        : detail,
    );
  }
  return response.json();
}
export function date(value: string, full = false) {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "short",
    ...(full ? { year: "numeric" as const } : {}),
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
