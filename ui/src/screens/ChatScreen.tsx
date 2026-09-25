import { useCallback, useEffect, useRef, useState } from "react";
import { api, conversationSocket, serviceOrigin, waitForService } from "../api";
import type { Approval, Conversation, EngineStatus, Message, ModelInfo } from "../types";
import AgentAvatar from "../components/AgentAvatar";
import {
  SearchIcon, DotsIcon, PlusIcon, MicIcon, SendIcon, GiftIcon,
} from "../components/icons";

interface LocalMessage {
  role: string;
  content: string;
  ts?: number;
  streaming?: boolean;
}

const MAIN_CHAT_KEY = "muse.mainChatId";

export default function ChatScreen({ initialChatId }: { initialChatId?: string }) {
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
  const [filter, setFilter] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
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
        const savedEngine = localStorage.getItem("muse.engine");
        const first = (savedEngine && r.engines.find((e) => e.id === savedEngine && e.available))
          ?? r.engines.find((e) => e.id === r.default && e.available)
          ?? r.engines.find((e) => e.available && !e.id.startsWith("cli:"));
        if (first) setEngine(first.id);
        api.conversations().then((r) => {
          if (cancelled) return;
          setConversations(r.conversations);
        }).catch((e) => setError(String(e)));
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
      const savedModel = localStorage.getItem("muse.model");
      const def = (savedModel && r.models.find((m) => `${m.provider_id}/${m.model_id}` === savedModel))
        ?? r.models.find((m) => m.is_default) ?? r.models[0];
      setModel(def ? `${def.provider_id}/${def.model_id}` : "");
    }).catch((e) => { setModels([]); setError(String(e)); });
  }, [engine]);

  // Remember the engine/model choice so the app always starts on it
  // (his default: OpenCode Zen / Muse Spark 1.3 Free).
  useEffect(() => { if (engine) localStorage.setItem("muse.engine", engine); }, [engine]);
  useEffect(() => { if (model) localStorage.setItem("muse.model", model); }, [model]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const refreshConversations = useCallback(() =>
    api.conversations().then((r) => setConversations(r.conversations)).catch(() => {}), []);

  const openConversationRef = useRef((conv: Conversation) => { void conv; });
  const initialChatDone = useRef(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [showInvite, setShowInvite] = useState(false);
  const [copied, setCopied] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const onAttach = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setAttaching(true);
    try {
      const buf = await file.arrayBuffer();
      let bin = "";
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < bytes.length; i += 8192) {
        bin += String.fromCharCode(...bytes.subarray(i, i + 8192));
      }
      const r = await api.uploadAttachment(file.name, btoa(bin));
      setDraft((d) => (d ? d + "\n" : "") + `[Attached file: ${r.path}]`);
    } catch (err) {
      setError(String(err));
    } finally {
      setAttaching(false);
    }
  };
  const openConversation = useCallback((conv: Conversation) => {
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
  openConversationRef.current = openConversation;

  useEffect(() => {
    if (!initialChatId || initialChatDone.current) return;
    const target = conversations.find((c) => c.id === initialChatId);
    if (target) {
      initialChatDone.current = true;
      openConversation(target);
    }
  }, [initialChatId, conversations, openConversation]);

  useEffect(() => () => wsRef.current?.close(), []);

  const newChat = async (title = "New chat") => {
    if (!engine) return null;
    const conv = await api.createConversation(title, engine, model || undefined);
    refreshConversations();
    setMessages([]);
    openConversation(conv);
    return conv;
  };

  const mainChatId = localStorage.getItem(MAIN_CHAT_KEY);
  const mainChat = conversations.find((c) => c.id === mainChatId)
    ?? conversations.find((c) => c.title === "Main chat");
  const sideChats = conversations
    .filter((c) => c.id !== mainChat?.id)
    .filter((c) => !filter || c.title.toLowerCase().includes(filter.toLowerCase()));

  const openMainChat = async () => {
    if (mainChat) {
      openConversation(mainChat);
      return;
    }
    const conv = await newChat("Main chat");
    if (conv) localStorage.setItem(MAIN_CHAT_KEY, conv.id);
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

  const deliver = (cid: string, payload: string, attempt: number) => {
    const current = activeRef.current;
    if (!current || current.id !== cid) return;
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

  const fmtTs = (ts: number) => {
    const d = new Date(ts * 1000);
    const today = new Date();
    const sameDay = d.toDateString() === today.toDateString();
    const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return sameDay ? time : `${d.toLocaleDateString([], { day: "numeric", month: "short" })} at ${time}`;
  };

  const ChatRow = ({ c, label }: { c?: Conversation; label?: string }) => (
    <div
      className={`side-item ${active?.id === c?.id ? "active" : ""}`}
      onClick={() => (c ? openConversation(c) : openMainChat())}
    >
      <span className="side-title">{c ? c.title : label}</span>
      {c && (confirmDeleteId === c.id ? (
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
        >x</button>
      ))}
    </div>
  );

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-search">
          <div className="search-field">
            <SearchIcon />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search"
              aria-label="Search chats"
            />
          </div>
          <div className="menu-wrap">
            <button className="icon-btn" aria-label="Chat options" onClick={() => setMenuOpen(!menuOpen)}>
              <DotsIcon />
            </button>
            {menuOpen && (
              <div className="menu-pop">
                <label>
                  Engine
                  <select value={engine} onChange={(e) => setEngine(e.target.value)} aria-label="Engine">
                    {availableEngines.map((e) => (
                      <option key={e.id} value={e.id} disabled={!e.available}>
                        {e.name}{e.available ? "" : ` - ${e.reason}`}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Model
                  <select value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model" disabled={models.length === 0}>
                    {models.length === 0 && <option value="">No models</option>}
                    {models.map((m) => (
                      <option key={`${m.provider_id}/${m.model_id}`} value={`${m.provider_id}/${m.model_id}`}>
                        {m.label}{m.is_default ? " (default)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="ghost-btn" onClick={() => { setDiagnosticsOpen(!diagnosticsOpen); setMenuOpen(false); }}>
                  Diagnostics
                </button>
              </div>
            )}
          </div>
        </div>
        <div className="sidebar-list">
          <ChatRow c={mainChat} label="Main chat" />
          <div className="side-section">
            <span>Side chats</span>
            <button className="icon-btn small" onClick={() => void newChat()} disabled={!engine || serviceState !== "ready"}
              title="New side chat" aria-label="New side chat">
              <PlusIcon />
            </button>
          </div>
          {sideChats.map((c) => <ChatRow key={c.id} c={c} />)}
          {sideChats.length === 0 && <div className="side-empty dim">No side chats yet.</div>}
        </div>
      </div>
      <div className="main">
        {diagnosticsOpen && <section className="diagnostics" aria-label="Diagnostics">
          <strong>App service: {serviceState}</strong> - {serviceOrigin}
          <div>Logs: ~/.instinct_muse/desktop.log and ~/.instinct_muse/service.log</div>
          {engines.map((e) => <div key={e.id}>{e.name}: {e.available ? `ready (${e.detail})` : e.reason || "unavailable"}</div>)}
          {error && <div className="error-banner" role="alert">{error}</div>}
        </section>}
        <div className="messages">
          <div className="msg-column">
            <div className="chat-agent-header">
              <AgentAvatar size={56} />
              <span className="agent-name">Muse</span>
            </div>
            <button className="invite-btn" aria-label="Invite friends" onClick={() => setShowInvite(true)}>
              <GiftIcon /> <span>Invite</span>
            </button>
            {!active && (
              <div className="empty-state">
                <h3>Instinct Muse</h3>
                <p>Open the main chat or start a side chat. Detected agents on this machine light up automatically - no API key needed when the agent CLI is already logged in.</p>
              </div>
            )}
            {messages.map((m, i) => {
              const prev = messages[i - 1];
              const showTs = m.ts && (!prev?.ts || m.ts - prev.ts > 300);
              return (
                <div key={i} className="msg-block">
                  {showTs && <div className="msg-ts">{fmtTs(m.ts!)}</div>}
                  <div className={`card ${m.role} ${m.streaming ? "streaming" : ""}`}>
                    {m.content}
                    {m.streaming && <span className="stream-cursor" aria-hidden="true" />}
                  </div>
                </div>
              );
            })}
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
            {thinking && (
              <div className="card assistant thinking">
                <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
                Muse is thinking - free models can take a minute or two
              </div>
            )}
            {error && <div className="card assistant">Error: {error}</div>}
            <div ref={bottomRef} />
          </div>
        </div>
        <div className="composer">
          <div className="composer-inner">
            <button className="composer-plus" aria-label="Attach" disabled={!active || attaching}
              onClick={() => fileInputRef.current?.click()}>
              <PlusIcon />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: "none" }}
              onChange={onAttach}
            />
            <textarea
              rows={1}
              placeholder={active ? "Message" : "Open a chat first"}
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
            <button className="composer-mic" aria-label="Dictate" disabled={!active}>
              <MicIcon />
            </button>
            <button className="composer-send" onClick={send} disabled={!active || !draft.trim()} aria-label="Send">
              <SendIcon />
            </button>
          </div>
        </div>
      </div>
      {showInvite && (
          <div className="modal-backdrop" onClick={() => setShowInvite(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>Invite friends</h3>
              <p className="dim">Share Instinct Muse with a friend. They get the app, you get the satisfaction.</p>
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Your invite code</h3>
                  <p>MUSE-DEMO-2026</p>
                </div>
                <button className="pill-btn" onClick={() => {
                  navigator.clipboard?.writeText("MUSE-DEMO-2026").then(() => {
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }).catch(() => {});
                }}>{copied ? "Copied" : "Copy"}</button>
              </div>
              <div className="modal-actions">
                <button className="pill-btn" onClick={() => setShowInvite(false)}>Close</button>
              </div>
            </div>
          </div>
        )}
    </>
  );
}
