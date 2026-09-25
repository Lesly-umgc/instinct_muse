import type { Approval, Artifact, Conversation, EngineStatus, FeedEdition, Goal, Idea, ModelInfo, SearchResult } from "./types";

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

  config: () => req<{ initial_screen: string }>("/api/config"),
  goals: () => req<{ goals: Goal[] }>("/api/goals"),
  createGoal: (title: string, category: string) =>
    req<Goal>("/api/goals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, category }),
    }),
  updateGoal: (id: string, patch: Partial<Pick<Goal, "done" | "status_line" | "title">>) =>
    req<Goal>(`/api/goals/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteGoal: (id: string) => req<void>(`/api/goals/${id}`, { method: "DELETE" }),
  feed: () => req<{ editions: FeedEdition[] }>("/api/feed"),
  refreshFeed: () => req<{ ok: boolean }>("/api/feed/refresh", { method: "POST" }),
  loveFeedItem: (id: string, loved: boolean) =>
    req<{ ok: boolean }>(`/api/feed/items/${id}/love`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ loved }),
    }),
  ideas: () => req<{ ideas: Idea[] }>("/api/ideas"),
  refreshIdeas: () => req<{ ok: boolean }>("/api/ideas/refresh", { method: "POST" }),
  dismissIdea: (id: string) => req<void>(`/api/ideas/${id}/dismiss`, { method: "POST" }),
  search: (q: string) => req<{ results: SearchResult[] }>(`/api/search?q=${encodeURIComponent(q)}`),
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
