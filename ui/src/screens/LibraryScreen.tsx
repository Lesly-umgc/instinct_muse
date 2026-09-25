import { useEffect, useState } from "react";
import { api } from "../api";
import type { Artifact } from "../types";
import AgentAvatar from "../components/AgentAvatar";
import {
  SearchIcon, LibraryIcon, DocIcon, GlobeIcon, ImageIcon, VideoIcon,
  PodcastIcon, FolderIcon, SlidersIcon, PlusIcon,
} from "../components/icons";

const KIND_LABEL: Record<string, string> = {
  document: "Document", web: "Artefact", image: "Image", video: "Video",
  podcast: "Podcast", file: "File",
};

export default function LibraryScreen({ initialArtifactId }: { initialArtifactId?: string }) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [category, setCategory] = useState<string>("all");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Artifact | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.artifacts().then((r) => {
      setArtifacts(r.artifacts);
      if (initialArtifactId) {
        const a = r.artifacts.find((x) => x.id === initialArtifactId) ?? r.artifacts[0];
        if (a) api.artifact(a.id).then(setSelected).catch(() => {});
      }
    }).catch((e) => setError(String(e)));
  }, [initialArtifactId]);

  const inCategory = (a: Artifact) => {
    if (category === "all") return true;
    if (category === "documents") return a.kind === "document";
    if (category === "web") return a.kind === "web";
    if (category === "images") return a.kind === "image";
    if (category === "videos") return a.kind === "video";
    if (category === "podcasts") return a.kind === "podcast";
    return true;
  };
  const shown = artifacts.filter(inCategory)
    .filter((a) => !filter || a.title.toLowerCase().includes(filter.toLowerCase()));
  const recent = shown[0];

  const NavItem = ({ id, label, Icon }: { id: string; label: string; Icon: () => JSX.Element }) => (
    <div className={`side-item ${category === id ? "active" : ""}`} onClick={() => setCategory(id)}>
      <span className="side-title nav-label"><Icon /> {label}</span>
    </div>
  );

  const Card = ({ a, large }: { a: Artifact; large?: boolean }) => (
    <div className={`artifact-card ${large ? "large" : ""}`} onClick={() => setSelected(a)}>
      <div className="artifact-thumb"><DocIcon /></div>
      <div className="artifact-meta">
        <h3>{a.title}</h3>
        <p>{KIND_LABEL[a.kind] ?? "File"} - {new Date(a.created_at * 1000).toLocaleDateString([], { day: "numeric", month: "short" })}</p>
      </div>
    </div>
  );

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-search">
          <div className="search-field">
            <SearchIcon />
            <input value={filter} onChange={(e) => setFilter(e.target.value)}
              placeholder="Search" aria-label="Search artefacts" />
          </div>
        </div>
        <div className="sidebar-list">
          <div className="side-section"><span>Artefacts</span></div>
          <NavItem id="all" label="All artefacts" Icon={LibraryIcon} />
          <NavItem id="documents" label="Documents" Icon={DocIcon} />
          <NavItem id="web" label="Web artefacts" Icon={GlobeIcon} />
          <div className="side-section"><span>Media</span></div>
          <NavItem id="images" label="Images" Icon={ImageIcon} />
          <NavItem id="videos" label="Videos" Icon={VideoIcon} />
          <NavItem id="podcasts" label="Podcasts" Icon={PodcastIcon} />
          <div className="spacer" />
          <NavItem id="system" label="System files" Icon={FolderIcon} />
        </div>
      </div>
      <div className="page">
        <header className="page-header">
          <h1>{category === "all" ? "All artefacts" : category === "system" ? "System files" : category[0].toUpperCase() + category.slice(1)}</h1>
          <div className="agent-mark">
            <AgentAvatar size={44} />
            <span>Muse</span>
          </div>
          <div className="header-actions">
            <button className="pill-btn">Select</button>
            <button className="icon-btn" aria-label="Sort"><SlidersIcon /></button>
            <button className="primary-btn"><PlusIcon /> Create an artefact</button>
          </div>
        </header>
        <div className="page-body library">
          {error && <div className="error-banner" role="alert">{error}</div>}
          {recent && (
            <section>
              <h2 className="category-heading">Recent</h2>
              <Card a={recent} large />
            </section>
          )}
          <section>
            <h2 className="category-heading">{category === "all" ? "All artefacts" : "Items"}</h2>
            {shown.length === 0 && <p className="dim">Nothing here yet. Artefacts Muse makes in chat land here.</p>}
            <div className="artifact-grid">
              {shown.map((a) => <Card key={a.id} a={a} />)}
            </div>
          </section>
        </div>
        {selected && (
          <div className="modal-backdrop" onClick={() => setSelected(null)}>
            <div className="modal artifact-preview" onClick={(e) => e.stopPropagation()}>
              <button className="close-btn" onClick={() => setSelected(null)} aria-label="Close">x</button>
              <div className="preview-head">
                <span className="kind-badge">{KIND_LABEL[selected.kind] ?? "File"}</span>
                <span className="dim">{new Date(selected.created_at * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
              </div>
              <h3>{selected.title}</h3>
              <p className="dim preview-path">{selected.path}</p>
              <pre>{selected.content ?? "(no preview available)"}</pre>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
