import { useCallback, useEffect, useRef, useState } from "react";
import { api, conversationSocket, serviceOrigin, waitForService } from "../api";
import type { Approval, Conversation, EngineStatus, Message, ModelInfo } from "../types";

interface LocalMessage {
  role: string;
  content: string;
  ts?: number;
  streaming?: boolean;
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
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [thinking, setThinking] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const activeRef = useRef<Conversation | null>(null);
  activeRef.current = active;

  const [serviceState, setServiceState] = useState<"starting" | "ready" | "unavailable">("starting");
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setServiceState("starting");
      try {
        await waitForService();
        if (cancelled) return;
        setServiceState("ready");
        setError("");
        const r = await api.engines();
        if (cancelled) return;
        setEngines(r.engines);
        const first = r.engines.find((e) => e.id === r.default && e.available)
          ?? r.engines.find((e) => e.available && !e.id.startsWith("cli:"));
        if (first) setEngine(first.id);
        api.conversations().then((r) => { if (!cancelled) setConversations(r.conversations); }).catch((e) => setError(String(e)));
        api.pendingApprovals().then((r) => { if (!cancelled) setApprovals(r.approvals); }).catch(() => {});
      } catch (e) {
        if (!cancelled) { setServiceState("unavailable"); setError(String(e)); }
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!engine || engine.startsWith("cli:")) return;
    api.models(engine).then((r) => {
      setModels(r.models);
      const def = r.models.find((m) => m.is_default) ?? r.models[0];
      setModel(def ? `${def.provider_id}/${def.model_id}` : "");
    }).catch((e) => { setModels([]); setError(String(e)); });
  }, [engine]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const refreshConversations = useCallback(() =>
    api.conversations().then((r) => setConversations(r.conversations)).catch(() => {}), []);

  const openConversation = useCallback((conv: Conversation) => {
    // Already viewing this chat on a live socket: reopening would drop and
    // re-create the connection for no reason (the churn that lost replies).
    const cur = wsRef.current;
    setActive((prev) => {
      if (prev?.id === conv.id && cur && (cur.readyState === WebSocket.OPEN || cur.readyState === WebSocket.CONNECTING)) {
        return prev;
      }
      cur?.close();
      setError("");
      api.conversation(conv.id).then((full) => {
        setMessages((full.messages ?? []).map((m: Message) => ({
          role: m.role, content: m.content, ts: m.created_at,
        })));
      });
      const ws = conversationSocket(conv.id, (ev) => {
        if (ev.type === "status" && ev.state === "working") {
          setThinking(true);
        } else if (ev.type === "text_delta") {
          setThinking(false);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant" && last.streaming) {
              return [...prev.slice(0, -1), { ...last, content: last.content + String(ev.text ?? "") }];
            }
            return [...prev, { role: "assistant", content: String(ev.text ?? ""), streaming: true }];
          });
        } else if (ev.type === "message_done") {
          setThinking(false);
          setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: undefined } : m)));
          refreshConversations();
        } else if (ev.type === "approval") {
          setApprovals((prev) => [...prev, ev.approval as Approval]);
        } else if (ev.type === "error") {
          setThinking(false);
          setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: undefined } : m)));
          setError(String(ev.text ?? "unknown error"));
        } else if (ev.type === "conversation_renamed") {
          refreshConversations();
          setActive((a) => (a && a.id === ev.conversation_id ? { ...a, title: String(ev.title ?? a.title) } : a));
        } else if (ev.type === "conversation_deleted") {
          if (ev.conversation_id === conv.id) {
            setActive(null);
            setMessages([]);
          }
          refreshConversations();
        }
      });
      ws.onclose = () => {
        // Unexpected drop (service restart, network blip): reconnect once after
        // a short pause, but only if this socket is still the current one.
        setTimeout(() => {
          setActive((a) => {
            if (a && a.id === conv.id && wsRef.current === ws && ws.readyState === WebSocket.CLOSED) {
              openConversation(conv);
            }
            return a;
          });
        }, 1500);
      };
      wsRef.current = ws;
      return conv;
    });
  }, [refreshConversations]);

  useEffect(() => () => wsRef.current?.close(), []);

  const newChat = async () => {
    if (!engine) return;
    const conv = await api.createConversation("New chat", engine, model || undefined);
    refreshConversations();
    setMessages([]);
    openConversation(conv);
  };

  const deleteChat = async (conv: Conversation) => {
    try {
      await api.deleteConversation(conv.id);
    } catch (e) {
      setError(String(e));
      return;
    }
    setConfirmDeleteId(null);
    if (activeRef.current?.id === conv.id) {
      setActive(null);
      setMessages([]);
    }
    refreshConversations();
  };

  // Retry delivery against a live socket for ~10s, reconnecting as needed,
  // so a message is never silently dropped by connection churn. If it still
  // cannot go out, say so visibly instead of pretending it was sent.
  const deliver = (cid: string, payload: string, attempt: number) => {
    const current = activeRef.current;
    if (!current || current.id !== cid) return; // user moved on before it went out
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(payload);
      return;
    }
    if (attempt >= 20) {
      setError("Message not sent - the connection dropped. Copy it and send it again.");
      return;
    }
    if (!ws || ws.readyState === WebSocket.CLOSED) openConversation(current);
    setTimeout(() => deliver(cid, payload, attempt + 1), 500);
  };

  const send = () => {
    const text = draft.trim();
    if (!text || !active) return;
    setMessages((prev) => [...prev, { role: "user", content: text, ts: Date.now() / 1000 }]);
    setDraft("");
    deliver(active.id, JSON.stringify({ type: "message", text }), 0);
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
          <button className="new-chat-btn" onClick={newChat} disabled={!engine || serviceState !== "ready"}>+ New</button>
        </div>
        <div className="sidebar-list">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`side-item ${active?.id === c.id ? "active" : ""}`}
              onClick={() => openConversation(c)}
            >
              <span className="side-title">{c.title}</span>
              {confirmDeleteId === c.id ? (
                <span className="del-confirm" onClick={(e) => e.stopPropagation()}>
                  <button className="del-yes" onClick={() => void deleteChat(c)}>Delete</button>
                  <button className="del-no" onClick={() => setConfirmDeleteId(null)}>Keep</button>
                </span>
              ) : (
                <button
                  className="del-chat"
                  title="Delete chat"
                  aria-label={`Delete chat ${c.title}`}
                  onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(c.id); }}
                >×</button>
              )}
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
          <button className="diagnostics-toggle" onClick={() => setDiagnosticsOpen(!diagnosticsOpen)}>Diagnostics</button>
          {cliNotes.map((n) => (
            <span key={n.id} className="engine-note" title={n.reason}>{n.name}: not detected</span>
          ))}
        </div>
        {diagnosticsOpen && <section className="diagnostics" aria-label="Diagnostics">
          <strong>App service: {serviceState}</strong> · {serviceOrigin}
          <div>Logs: ~/.instinct_muse/desktop.log and ~/.instinct_muse/service.log</div>
          {engines.map((e) => <div key={e.id}>{e.name}: {e.available ? `ready (${e.detail})` : e.reason || "unavailable"}</div>)}
          {error && <div>{error}</div>}
        </section>}
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
                {m.streaming && <span className="ts">...</span>}
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
            {thinking && <div className="bubble assistant thinking">Thinking... (slow models can take a minute or two)</div>}
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
