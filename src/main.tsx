import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import { loadWorkspace } from "./workspace";

const root = createRoot(document.getElementById("root")!);
root.render(<p role="status" className="empty-state">Восстанавливаем пространство…</p>);
void loadWorkspace().then(({ workspace, warning }) => {
  root.render(<App initialWorkspace={workspace} initialWorkspaceWarning={warning} />);
});
