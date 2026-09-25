import { useEffect, useState } from "react";
import { api, serviceOrigin } from "../api";
import type { Approval, EngineStatus } from "../types";
import AgentAvatar from "../components/AgentAvatar";

type Section =
  | "general" | "connectors" | "filesystem" | "dictation" | "wallet"
  | "securestore" | "permissions" | "messaging" | "devices" | "data"
  | "help" | "legal";

const SECTIONS: { id: Section; label: string }[] = [
  { id: "general", label: "General" },
  { id: "connectors", label: "Connectors" },
  { id: "filesystem", label: "File system" },
  { id: "dictation", label: "Dictation" },
  { id: "wallet", label: "Wallet" },
  { id: "securestore", label: "Secure Store" },
  { id: "permissions", label: "Permissions" },
  { id: "messaging", label: "Messaging" },
  { id: "devices", label: "Devices" },
  { id: "data", label: "Data controls" },
  { id: "help", label: "Help" },
  { id: "legal", label: "Legal" },
];

export default function SettingsScreen({ initialSection }: { initialSection?: string }) {
  const valid = SECTIONS.some((s) => s.id === initialSection);
  const [section, setSection] = useState<Section>(valid ? (initialSection as Section) : "general");
  const [config, setConfig] = useState<{ version?: string; data_dir?: string }>({});
  const [engines, setEngines] = useState<EngineStatus[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    api.config().then(setConfig).catch(() => {});
    api.engines().then((r) => setEngines(r.engines)).catch(() => {});
    api.allApprovals().then((r) => setApprovals(r.approvals)).catch(() => {});
  }, []);

  const doExport = async () => {
    const data = await api.exportData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `instinct-muse-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const doReset = async () => {
    setResetting(true);
    try {
      await api.resetData();
      location.reload();
    } finally {
      setResetting(false);
      setConfirmReset(false);
    }
  };

  return (
    <>
      <div className="sidebar">
        <div className="side-section"><span>Settings</span></div>
        <div className="sidebar-list">
          {SECTIONS.map((s) => (
            <div key={s.id} className={`side-item ${section === s.id ? "active" : ""}`}
              onClick={() => setSection(s.id)}>
              <span className="side-title">{s.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="page">
        <header className="page-header">
          <h1>{SECTIONS.find((s) => s.id === section)?.label}</h1>
        </header>
        <div className="page-body settings">
          {section === "general" && (
            <>
              <div className="settings-card">
                <div className="settings-row">
                  <div className="settings-row-text">
                    <h3>Appearance</h3>
                    <p>Dark, matching the Muse design</p>
                  </div>
                  <span className="dim">Dark</span>
                </div>
              </div>
              <div className="settings-card">
                <div className="settings-row">
                  <div className="settings-row-text">
                    <h3>Keyboard shortcuts</h3>
                    <p>Cmd+K search - Cmd+1..6 switch screens - Cmd+, settings</p>
                  </div>
                </div>
              </div>
              <div className="settings-card">
                <div className="settings-row">
                  <div className="settings-row-text">
                    <h3>Version</h3>
                    <p>{config.version ?? "..."} - service at {serviceOrigin}</p>
                  </div>
                </div>
                <div className="settings-row">
                  <div className="settings-row-text">
                    <h3>Data folder</h3>
                    <p>{config.data_dir ?? "..."}</p>
                  </div>
                </div>
              </div>
            </>
          )}
          {section === "connectors" && (
            <div className="settings-card">
              {engines.map((e) => (
                <div className="settings-row" key={e.id}>
                  <div className="settings-row-icon"><AgentAvatar size={32} /></div>
                  <div className="settings-row-text">
                    <h3>{e.name}</h3>
                    <p>{e.available ? (e.detail || "Connected") : (e.reason || "Not available")}</p>
                  </div>
                  <span className={`status-dot ${e.available ? "on" : "off"}`} />
                </div>
              ))}
              {engines.length === 0 && <p className="dim">No agents detected. Install OpenCode to give Muse a brain.</p>}
            </div>
          )}
          {section === "filesystem" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Agent workspace</h3>
                  <p>{config.data_dir ? `${config.data_dir}/workspace` : "..."}</p>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Least-privilege access</h3>
                  <p>Muse's agent reads and writes inside its own workspace folder only. It does not get Full Disk Access.</p>
                </div>
              </div>
            </div>
          )}
          {section === "dictation" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Dictation</h3>
                  <p>Uses macOS system dictation. Press the mic key (or Fn twice) while the composer is focused. Enable it in System Settings - Keyboard - Dictation.</p>
                </div>
              </div>
            </div>
          )}
          {section === "wallet" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Wallet</h3>
                  <p>Payments are coming soon. Muse will never spend money without your approval first.</p>
                </div>
                <span className="dim">Coming soon</span>
              </div>
            </div>
          )}
          {section === "securestore" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>No saved logins</h3>
                  <p>Website logins you save will live here, stored only on this Mac and kept separate from the agent runtime.</p>
                </div>
              </div>
            </div>
          )}
          {section === "permissions" && (
            <div className="settings-card">
              {approvals.length === 0 && <p className="dim">No approvals yet. When Muse asks to run an action, your choice is remembered here.</p>}
              {approvals.map((a) => (
                <div className="settings-row" key={a.id}>
                  <div className="settings-row-text">
                    <h3>{a.action}</h3>
                    <p>{a.status}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
          {section === "messaging" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>WhatsApp</h3>
                  <p>Not connected. Messaging channels are coming soon.</p>
                </div>
                <span className="dim">Coming soon</span>
              </div>
            </div>
          )}
          {section === "devices" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>This Mac</h3>
                  <p>Current device. Instinct Muse runs entirely on this machine.</p>
                </div>
                <span className="status-dot on" />
              </div>
            </div>
          )}
          {section === "data" && (
            <>
              <div className="settings-card">
                <div className="settings-row">
                  <div className="settings-row-text">
                    <h3>Export your data</h3>
                    <p>Chats, artefacts, goals and ideas as JSON</p>
                  </div>
                  <button className="pill-btn" onClick={doExport}>Export</button>
                </div>
              </div>
              <div className="settings-card danger">
                <div className="settings-row">
                  <div className="settings-row-text">
                    <h3>Reset Instinct Muse</h3>
                    <p>Deletes all chats, artefacts, goals, ideas and remembered approvals on this Mac. This cannot be undone.</p>
                  </div>
                  <button className="pill-btn danger-btn" onClick={() => setConfirmReset(true)}>Reset</button>
                </div>
              </div>
            </>
          )}
          {section === "help" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Report a problem</h3>
                  <p>Open an issue on the project tracker with what you did and what happened.</p>
                </div>
                <button className="pill-btn" onClick={() => window.open("https://github.com/Lesly-umgc/instinct_muse/issues", "_blank")}>Open issues</button>
              </div>
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Logs</h3>
                  <p>{config.data_dir ? `${config.data_dir}/service.log and desktop.log` : "..."}</p>
                </div>
              </div>
            </div>
          )}
          {section === "legal" && (
            <div className="settings-card">
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Responses come from an AI model</h3>
                  <p>They can be wrong. Check anything that matters.</p>
                </div>
              </div>
              <div className="settings-row">
                <div className="settings-row-text">
                  <h3>Instinct Muse</h3>
                  <p>An independent open-source project. Not affiliated with Meta or the Muse product. Your data stays on this Mac.</p>
                </div>
              </div>
            </div>
          )}
        </div>
        {confirmReset && (
          <div className="modal-backdrop" onClick={() => setConfirmReset(false)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>Reset everything?</h3>
              <p className="dim">All chats, artefacts, goals, ideas and remembered approvals are deleted from this Mac. There is no undo.</p>
              <div className="modal-actions">
                <button className="pill-btn" onClick={() => setConfirmReset(false)}>Cancel</button>
                <button className="pill-btn danger-btn" onClick={doReset} disabled={resetting}>
                  {resetting ? "Resetting..." : "Reset everything"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
