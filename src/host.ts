const parentOrigin = window.location.ancestorOrigins?.[0] || "";
export const insideVSCode = new URLSearchParams(window.location.search).get("vscode") === "1"
  && window.parent !== window && /^vscode-webview:\/\/(?:[a-f0-9-]{36}|[0-9a-v]{52})$/i.test(parentOrigin);
const pending = new Map<string, { resolve: (value: boolean) => void; reject: (error: Error) => void }>();

if (insideVSCode) window.addEventListener("message", event => {
  if (event.source !== window.parent || event.origin !== parentOrigin || event.data?.kind !== "agentboard-host-result") return;
  const request = pending.get(event.data.id);
  if (!request) return;
  pending.delete(event.data.id);
  if (event.data.error) request.reject(new Error(String(event.data.error)));
  else request.resolve(event.data.result === true);
});

export function hostRequest(action: "clipboard" | "export", data: Record<string, string>): Promise<boolean> {
  return new Promise((resolve, reject) => {
    const id = crypto.randomUUID();
    const timer = window.setTimeout(() => {
      pending.delete(id);
      reject(new Error("VS Code не ответил. Повторите действие."));
    }, 5 * 60 * 1000);
    pending.set(id, {
      resolve: value => { clearTimeout(timer); resolve(value); },
      reject: error => { clearTimeout(timer); reject(error); },
    });
    window.parent.postMessage({ kind: "agentboard-host", id, action, ...data }, parentOrigin);
  });
}

export async function writeClipboard(value: string) {
  if (insideVSCode) await hostRequest("clipboard", { text: value });
  else await navigator.clipboard.writeText(value);
}
