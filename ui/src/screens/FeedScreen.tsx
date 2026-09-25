import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { FeedEdition } from "../types";
import AgentAvatar from "../components/AgentAvatar";
import { HeartIcon, CommentIcon, DotsIcon, SlidersIcon } from "../components/icons";

export default function FeedScreen() {
  const [editions, setEditions] = useState<FeedEdition[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.feed().then((r) => setEditions(r.editions)).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  const refresh = () => {
    setRefreshing(true);
    api.refreshFeed()
      .then(() => setTimeout(() => { load(); setRefreshing(false); }, 45000))
      .catch((e) => { setError(String(e)); setRefreshing(false); });
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>Feed</h1>
        <div className="agent-mark">
          <AgentAvatar size={44} />
          <span>Muse</span>
        </div>
        <button className="icon-btn" title="Feed instructions" aria-label="Feed instructions">
          <SlidersIcon />
        </button>
      </header>
      <div className="page-body feed">
        {error && <div className="error-banner" role="alert">{error}</div>}
        {editions.length === 0 && !error && (
          <div className="empty-state">
            <h3>No editions yet</h3>
            <p>Muse writes a personal briefing on a schedule. Generate the first one now.</p>
            <button className="primary-btn" onClick={refresh} disabled={refreshing}>
              {refreshing ? "Writing your briefing..." : "Generate a briefing"}
            </button>
          </div>
        )}
        {editions.map((ed) => (
          <section key={ed.id} className="edition">
            <h2>{ed.label}</h2>
            {(ed.items ?? []).map((item) => (
              <article key={item.id} className="feed-card">
                <div className="feed-thumb" aria-hidden="true" />
                <div className="feed-content">
                  <div className="feed-title-row">
                    <h3>{item.title}</h3>
                    <button className="icon-btn small" aria-label="More"><DotsIcon /></button>
                  </div>
                  <p>{item.body}</p>
                  <div className="feed-actions">
                    <button
                      className={`ghost-btn ${item.loved ? "loved" : ""}`}
                      onClick={() => api.loveFeedItem(item.id, !item.loved).then(load)}
                      aria-label="Love"
                    >
                      <HeartIcon />
                    </button>
                    <button className="ghost-btn labeled" aria-label="Discuss">
                      <CommentIcon /> <span>Discuss</span>
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </section>
        ))}
        {editions.length > 0 && (
          <button className="ghost-btn refresh" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Writing a new edition..." : "New edition"}
          </button>
        )}
      </div>
    </div>
  );
}
