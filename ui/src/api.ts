import type { Approval, Artifact, Conversation, EngineStatus, ModelInfo } from "./types";

const desktop = "__TAURI_INTERNALS__" in window;
const base = desktop ? "http://127.0.0.1:8000" : "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, init);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
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
  const host = desktop ? "127.0.0.1:8000" : location.host;
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
