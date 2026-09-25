import type { Approval, Artifact, Conversation, EngineStatus, ModelInfo } from "./types";

const desktop = "__TAURI_INTERNALS__" in window;
const base = desktop ? "http://127.0.0.1:18764" : "";

export const serviceOrigin = base || location.origin;

export async function waitForService(attempts = 25): Promise<void> {
  for (let i = 0; i < attempts; i++) {
    try {
      const response = await fetch(`${base}/health`, { cache: "no-store" });
      if (response.ok && ((await response.json()).system === "instinct_muse")) return;
    } catch { /* The bundled service may still be starting. */ }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Instinct Muse service is not ready at ${serviceOrigin} (another app may be using its port). Check ~/.instinct_muse/desktop.log and ~/.instinct_muse/service.log.`);
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, init);
  } catch (cause) {
    throw new Error(`Cannot reach app service at ${serviceOrigin}. Check ~/.instinct_muse/desktop.log and ~/.instinct_muse/service.log. (${String(cause)})`);
  }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  engines: () => req<{ engines: EngineStatus[]; default: string }>("/api/engines"),
  models: (engine: string) => req<{ models: ModelInfo[] }>(`/api/models?engine=${engine}`),
  conversations: () => req<{ conversations: Conversation[] }>("/api/conversations"),
  conversation: (id: string) => req<Conversation>(`/api/conversations/${id}`),
  createConversation: (title: string, engine?: string, model?: string) =>
    req<Conversation>("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, engine, model }),
    }),
  deleteConversation: (id: string) =>
    req<void>(`/api/conversations/${id}`, { method: "DELETE" }),
  artifacts: () => req<{ artifacts: Artifact[] }>("/api/artifacts"),
  artifact: (id: string) => req<Artifact>(`/api/artifacts/${id}`),
  pendingApprovals: () => req<{ approvals: Approval[] }>("/api/approvals?status=pending"),
  decideApproval: (id: string, decision: "allow" | "always" | "deny") =>
    req<Approval>(`/api/approvals/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    }),
};

export function conversationSocket(
  cid: string,
  onEvent: (ev: Record<string, unknown>) => void,
): WebSocket {
  const proto = !desktop && location.protocol === "https:" ? "wss" : "ws";
  const host = desktop ? "127.0.0.1:18764" : location.host;
  const ws = new WebSocket(`${proto}://${host}/ws/conversations/${cid}`);
  ws.onmessage = (m) => {
    try {
      onEvent(JSON.parse(m.data));
    } catch {
      /* ignore malformed frames */
    }
  };
  return ws;
}
