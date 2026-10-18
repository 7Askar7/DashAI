import { insideVSCode, hostRequest } from "./host";

const key = "dashai.workspace.v1";
const views = ["overview", "board", "project_history", "history", "connectors", "map", "architecture", "documentation", "modules", "integrations", "releases"] as const;
export type View = typeof views[number];
export const isProjectView = (view: View) => !["overview", "history", "connectors"].includes(view);
export const validId = (value: unknown): value is string => typeof value === "string" && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value);
export type ProjectWorkspace = {
  view: View; query: string; taskTypeFilter: string; subprojectFilter: string;
  agentFilter: string; statusFilter: string; priorityFilter: string;
  listView: boolean; filtersOpen: boolean;
};
export type Workspace = { version: 1; projectId: string | null; view: View; taskId: string | null; projects: Record<string, ProjectWorkspace> };
export const defaultProjectWorkspace: ProjectWorkspace = {
  view: "board", query: "", taskTypeFilter: "", subprojectFilter: "", agentFilter: "",
  statusFilter: "", priorityFilter: "", listView: false, filtersOpen: false,
};
const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const choice = (value: unknown, values: readonly string[], fallback = "") => typeof value === "string" && values.includes(value) ? value : fallback;
const filterId = (value: unknown) => value === "unassigned" || validId(value) ? value : "";

export function normalizeWorkspace(value: unknown): Workspace {
  const data = object(value), projects: Workspace["projects"] = {};
  if (data.version !== 1) return { version: 1, projectId: null, view: "board", taskId: null, projects };
  for (const [id, value] of Object.entries(object(data.projects)).slice(-100)) {
    if (!validId(id)) continue;
    const prefs = object(value), view = choice(prefs.view, views, "board") as View;
    projects[id] = {
      view: isProjectView(view) ? view : "board",
      query: typeof prefs.query === "string" ? prefs.query.slice(0, 500) : "",
      taskTypeFilter: choice(prefs.taskTypeFilter, ["research", "development", "testing", "bugfix", "documentation", "other"]),
      subprojectFilter: filterId(prefs.subprojectFilter), agentFilter: choice(prefs.agentFilter, ["human", "codex", "claude"]) || filterId(prefs.agentFilter),
      statusFilter: choice(prefs.statusFilter, ["backlog", "in_progress", "review", "done", "blocked"]),
      priorityFilter: choice(prefs.priorityFilter, ["urgent", "high", "medium", "low"]),
      listView: prefs.listView === true, filtersOpen: prefs.filtersOpen === true,
    };
  }
  return { version: 1, projectId: validId(data.projectId) ? data.projectId : null,
    taskId: validId(data.taskId) ? data.taskId : null, view: choice(data.view, views, "board") as View, projects };
}

export async function loadWorkspace(): Promise<{ workspace: Workspace; warning: string }> {
  let value: unknown = null, warning = "";
  try {
    const saved = localStorage.getItem(key);
    value = saved ? JSON.parse(saved) : { version: 1, projectId: localStorage.getItem("agentboard.project") };
  } catch { warning = "Не удалось прочитать сохранённый вид. Пространство открыто с исходными настройками."; }
  if (insideVSCode) {
    try { value = await hostRequest<unknown>("load_workspace", {}) ?? value; warning = ""; }
    catch { warning = "Хранилище VS Code недоступно. Восстановлены настройки этого браузера, если они сохранились."; }
  }
  return { workspace: normalizeWorkspace(value), warning };
}

let hostSave = Promise.resolve<unknown>(null);
export async function saveWorkspace(workspace: Workspace) {
  const state = JSON.stringify(normalizeWorkspace(workspace));
  let localSaved = false;
  try { localStorage.setItem(key, state); localSaved = true; } catch { /* The host can still persist this workspace. */ }
  if (insideVSCode) {
    hostSave = hostSave.catch(() => {}).then(() => hostRequest("save_workspace", { state }));
    try { await hostSave; return; }
    catch { throw new Error(localSaved ? "Настройки сохранены только в браузере: хранилище VS Code недоступно." : "Не удалось сохранить вид пространства. После перезапуска настройки могут сброситься."); }
  }
  if (!localSaved) throw new Error("Браузер не разрешает сохранить вид пространства. После перезапуска настройки могут сброситься.");
}

export function taskLink(id: string) {
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("task", id);
  return url.href;
}
export function taskFromUrl() {
  return new URL(window.location.href).searchParams.get("task");
}
