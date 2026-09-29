import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Idea } from "../types";
import AgentAvatar from "../components/AgentAvatar";
import { DotsIcon } from "../components/icons";

export default function IdeasScreen({ initialIdeaId }: { initialIdeaId?: string }) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Idea | null>(null);
  useEffect(() => { if (initialIdeaId) api.ideas().then((r) => { const item = r.ideas.find((i) => i.id === initialIdeaId); if (item) setSelected(item); else setError("That idea is no longer available."); }).catch((e) => setError(String(e))); }, [initialIdeaId]);

  const load = useCallback(() => {
    api.ideas().then((r) => setIdeas(r.ideas)).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  const refresh = () => {
    setRefreshing(true);
    api.refreshIdeas()
      .then(() => setTimeout(() => { load(); setRefreshing(false); }, 45000))
      .catch((e) => { setError(String(e)); setRefreshing(false); });
  };

  const top = ideas.filter((i) => !i.category);
  const categories = [...new Set(ideas.filter((i) => i.category).map((i) => i.category))];

  const IdeaCard = ({ idea }: { idea: Idea }) => (
    <article className="idea-card">
      <div className="feed-title-row">
        <button className="idea-open" onClick={() => setSelected(idea)} aria-label={`Open idea: ${idea.title}`}>{idea.title}</button>
        <button className="icon-btn small" aria-label="Dismiss"
          onClick={() => api.dismissIdea(idea.id).then(load)}>
          <DotsIcon />
        </button>
      </div>
      <p>{idea.body}</p>
    </article>
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Ideas</h1>
          <p className="subtitle">
            I'm always thinking about new and different ways to help you. I'll surface my favourite ideas here.
          </p>
        </div>
        <div className="agent-mark">
          <AgentAvatar size={44} />
          <span>Muse</span>
        </div>
      </header>
      <div className="page-body ideas">
        {error && <div className="error-banner" role="alert">{error}</div>}
        {ideas.length === 0 && !error && (
          <div className="empty-state">
            <h3>No ideas yet</h3>
            <p>Once Muse knows a little about what you're working on, ideas show up here.</p>
            <button className="primary-btn" onClick={refresh} disabled={refreshing}>
              {refreshing ? "Thinking..." : "Suggest ideas"}
            </button>
          </div>
        )}
        {top.map((i) => <IdeaCard key={i.id} idea={i} />)}
        {categories.map((cat) => (
          <section key={cat}>
            <h2 className="category-heading">{cat}</h2>
            {ideas.filter((i) => i.category === cat).map((i) => <IdeaCard key={i.id} idea={i} />)}
          </section>
        ))}
        {ideas.length > 0 && (
          <button className="ghost-btn refresh" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Thinking..." : "More ideas"}
          </button>
        )}
        {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><div className="modal" role="dialog" aria-label={selected.title} onClick={(e) => e.stopPropagation()}><button onClick={() => setSelected(null)} aria-label="Close idea">Close</button><h2>{selected.title}</h2><p>{selected.body}</p></div></div>}
      </div>
    </div>
  );
}
