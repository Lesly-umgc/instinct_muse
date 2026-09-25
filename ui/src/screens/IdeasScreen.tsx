import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Idea } from "../types";
import AgentAvatar from "../components/AgentAvatar";
import { DotsIcon } from "../components/icons";

export default function IdeasScreen() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

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
        <h3>{idea.title}</h3>
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
        {error && <p className="dim">{error}</p>}
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
      </div>
    </div>
  );
}
