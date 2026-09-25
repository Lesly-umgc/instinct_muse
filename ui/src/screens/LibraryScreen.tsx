import { useEffect, useState } from "react";
import { api } from "../api";
import type { Artifact } from "../types";

const KINDS = ["all", "document", "web", "image", "video", "podcast", "file"];

export default function LibraryScreen() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [kind, setKind] = useState("all");
  const [open, setOpen] = useState<Artifact | null>(null);

  useEffect(() => {
    api.artifacts().then((r) => setArtifacts(r.artifacts)).catch(() => {});
  }, []);

  const shown = kind === "all" ? artifacts : artifacts.filter((a) => a.kind === kind);

  return (
    <div className="main">
      <div className="library">
        <div className="library-inner">
          <h2>Library</h2>
          <div className="kind-filters">
            {KINDS.map((k) => (
              <button key={k} className={kind === k ? "active" : ""} onClick={() => setKind(k)}>
                {k === "all" ? "All" : k[0].toUpperCase() + k.slice(1) + "s"}
              </button>
            ))}
          </div>
          {shown.length === 0 && (
            <p style={{ color: "var(--text-dim)" }}>
              Nothing here yet. Files the agent creates in chat show up here automatically.
            </p>
          )}
          <div className="artifact-grid">
            {shown.map((a) => (
              <div key={a.id} className="artifact-card" onClick={() => setOpen(a)}>
                <div className="kind">{a.kind}</div>
                <div className="title">{a.title}</div>
                <div className="date">{new Date(a.created_at * 1000).toLocaleString()}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setOpen(null)} aria-label="Close">×</button>
            <h3>{open.title}</h3>
            <p style={{ color: "var(--text-dim)", fontSize: 13 }}>{open.path}</p>
            {open.content != null ? <pre>{open.content}</pre> : <p>No preview available.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
