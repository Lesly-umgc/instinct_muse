import { useCallback, useEffect, useRef, useState } from "react";
import { api, conversationSocket } from "../api";
import type { Approval, Conversation, EngineStatus, Message, ModelInfo } from "../types";

interface LocalMessage {
  role: string;
  content: string;
  ts?: number;
}

export default function ChatScreen() {
  const [engines, setEngines] = useState<EngineStatus[]>([]);
  const [engine, setEngine] = useState<string>("");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [model, setModel] = useState<string>("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api.engines().then((r) => {
      setEngines(r.engines);
      const first = r.engines.find((e) => e.id === r.default && e.available)
        ?? r.engines.find((e) => e.available && !e.id.startsWith("cli:"));
      if (first) setEngine(first.id);
    }).catch((e) => setError(String(e)));
    refreshConversations();
    api.pendingApprovals().then((r) => setApprovals(r.approvals)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!engine || engine.startsWith("cli:")) return;
    api.models(engine).then((r) => {
      setModels(r.models);
      const def = r.models.find((m) => m.is_default) ?? r.models[0];
      setModel(def ? `${def.provider_id}/${def.model_id}` : "");
    }).catch(() => setModels([]));
  }, [engine]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const refreshConversations = () =>
    api.conversations().then((r) => setConversations(r.conversations)).catch(() => {});

  const openConversation = useCallback((conv: Conversation) => {
    wsRef.current?.close();
    setActive(conv);
    setError("");
    api.conversation(conv.id).then((full) => {
      setMessages((full.messages ?? []).map((m: Message) => ({
        role: m.role, content: m.content, ts: m.created_at,
      })));
    });
    const ws = conversationSocket(conv.id, (ev) => {
      if (ev.type === "text_delta") {
        setStreaming(true);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === "assistant" && streaming) {
            return [...prev.slice(0, -1), { ...last, content: last.content + String(ev.text ?? "") }];
          }
          return [...prev, { role: "assistant", content: String(ev.text ?? "") }];
        });
      } else if (ev.type === "message_done") {
        setStreaming(false);
      } else if (ev.type === "approval") {
        setApprovals((prev) => [...prev, ev.approval as Approval]);
      } else if (ev.type === "error") {
        setStreaming(false);
        setError(String(ev.text ?? "unknown error"));
      }
    });
    wsRef.current = ws;
  }, [streaming]);

  useEffect(() => () => wsRef.current?.close(), []);

  const newChat = async () => {
    if (!engine) return;
    const conv = await api.createConversation("New chat", engine, model || undefined);
    refreshConversations();
    setMessages([]);
    openConversation(conv);
  };

  const send = () => {
    const text = draft.trim();
    if (!text || !active || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    setMessages((prev) => [...prev, { role: "user", content: text, ts: Date.now() / 1000 }]);
    wsRef.current.send(JSON.stringify({ type: "message", text }));
    setDraft("");
    refreshConversations();
  };

  const decide = async (approval: Approval, decision: "allow" | "always" | "deny") => {
    const updated = await api.decideApproval(approval.id, decision);
    setApprovals((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
  };

  const availableEngines = engines.filter((e) => !e.id.startsWith("cli:"));
  const cliNotes = engines.filter((e) => e.id.startsWith("cli:") && !e.available);

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-header">
          <h2>Chats</h2>
          <button className="new-chat-btn" onClick={newChat} disabled={!engine}>+ New</button>
        </div>
        <div className="sidebar-list">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`side-item ${active?.id === c.id ? "active" : ""}`}
              onClick={() => openConversation(c)}
            >
              {c.title}
            </div>
          ))}
          {conversations.length === 0 && (
            <div className="side-item">No chats yet. Start one.</div>
          )}
        </div>
      </div>
      <div className="main">
        <div className="topbar">
          <select value={engine} onChange={(e) => setEngine(e.target.value)} aria-label="Engine">
            {availableEngines.map((e) => (
              <option key={e.id} value={e.id} disabled={!e.available}>
                {e.name}{e.available ? "" : ` - ${e.reason}`}
              </option>
            ))}
          </select>
          <select value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model" disabled={models.length === 0}>
            {models.length === 0 && <option value="">No models (engine unavailable)</option>}
            {models.map((m) => (
              <option key={`${m.provider_id}/${m.model_id}`} value={`${m.provider_id}/${m.model_id}`}>
                {m.label}{m.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
          {cliNotes.map((n) => (
            <span key={n.id} className="engine-note" title={n.reason}>{n.name}: not detected</span>
          ))}
        </div>
        <div className="messages">
          <div className="msg-column">
            {!active && (
              <div className="empty-state">
                <h3>Instinct Muse</h3>
                <p>Pick an engine and start a chat. Detected agents on this machine light up automatically - no API key needed when the agent CLI is already logged in.</p>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.role}`}>
                {m.content}
                {m.ts && <span className="ts">{new Date(m.ts * 1000).toLocaleTimeString()}</span>}
              </div>
            ))}
            {approvals.filter((a) => !active || a.conversation_id === active.id).map((a) => (
              <div key={a.id} className={`approval-card ${a.status !== "pending" ? "resolved" : ""}`}>
                <div className="action">Approval needed: {a.action}</div>
                <div className="detail">{a.detail}</div>
                {a.status === "pending" ? (
                  <div className="buttons">
                    <button className="allow" onClick={() => decide(a, "allow")}>Allow</button>
                    <button onClick={() => decide(a, "always")}>Always</button>
                    <button className="deny" onClick={() => decide(a, "deny")}>Deny</button>
                  </div>
                ) : (
                  <div className="detail">{a.status}</div>
                )}
              </div>
            ))}
            {error && <div className="bubble assistant">Error: {error}</div>}
            <div ref={bottomRef} />
          </div>
        </div>
        <div className="composer">
          <div className="composer-inner">
            <textarea
              rows={1}
              placeholder={active ? "Message..." : "Start a new chat first"}
              value={draft}
              disabled={!active}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button onClick={send} disabled={!active || !draft.trim()} aria-label="Send">↑</button>
          </div>
        </div>
      </div>
    </>
  );
}
