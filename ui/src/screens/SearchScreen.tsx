import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SearchResult } from "../types";
import AgentAvatar from "../components/AgentAvatar";
import { SearchIcon, ChatIcon, DocIcon, GoalsIcon, IdeasIcon } from "../components/icons";

const KIND_ICON: Record<string, () => JSX.Element> = {
  chat: ChatIcon,
  artifact: DocIcon,
  goal: GoalsIcon,
  idea: IdeasIcon,
};

export default function SearchScreen({ initialQuery, onOpen }: { initialQuery?: string; onOpen: (result: SearchResult) => void }) {
  const [q, setQ] = useState(initialQuery ?? "");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setQ(initialQuery ?? "");
  }, [initialQuery]);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const seq = ++request.current;
    setError("");
    if (!q.trim()) {
      setResults([]);
      setSearched(false);
      return;
    }
    timer.current = setTimeout(() => {
      api.search(q).then((r) => { if (seq === request.current) { setResults(r.results); setSearched(true); } }).catch((e) => { if (seq === request.current) { setResults([]); setSearched(false); setError(`Search failed: ${String(e)}`); } });
    }, 300);
  }, [q]);

  const grouped = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    (acc[r.kind] ??= []).push(r);
    return acc;
  }, {});

  return (
    <div className="page">
      <header className="page-header">
        <h1>Search</h1>
        <div className="agent-mark">
          <AgentAvatar size={44} />
          <span>Muse</span>
        </div>
      </header>
      <div className="page-body search">
        <div className="search-box">
          <SearchIcon />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search chats, goals, artefacts and ideas"
            aria-label="Search"
          />
        </div>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {searched && results.length === 0 && <p className="dim">Nothing found for "{q}".</p>}
        {Object.entries(grouped).map(([kind, items]) => {
          const Icon = KIND_ICON[kind] ?? DocIcon;
          return (
            <section key={kind} className="result-group">
              <h2 className="category-heading">{kind === "chat" ? "Chats" : kind === "artifact" ? "Artefacts" : kind === "goal" ? "Goals" : "Ideas"}</h2>
              {items.map((r) => (
                <button key={`${kind}-${r.id}`} type="button" className="result-row" onClick={() => onOpen(r)} aria-label={`Open ${kind}: ${r.title}`}>
                  <span className="result-icon"><Icon /></span>
                  <div>
                    <h3>{r.title}</h3>
                    <p>{r.snippet}</p>
                  </div>
                </button>
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}
