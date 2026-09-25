import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Goal } from "../types";
import AgentAvatar from "../components/AgentAvatar";
import {
  DotsIcon, ChevronRightIcon, HeartIcon, CommentIcon, CheckIcon,
} from "../components/icons";

const CATEGORIES = ["Health", "Relationships", "Finance", "Career", "Learning", "Other"];

export default function GoalsScreen() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [creating, setCreating] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.goals().then((r) => setGoals(r.goals)).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  const tracking = goals.filter((g) => g.group_name === "Tracking");
  const plain = goals.filter((g) => g.group_name !== "Tracking");

  const toggle = (g: Goal) => api.updateGoal(g.id, { done: !g.done }).then(load);

  const create = () => {
    if (!newTitle.trim() || !creating) return;
    api.createGoal(newTitle.trim(), creating).then(() => {
      setNewTitle("");
      setCreating(null);
      load();
    }).catch((e) => setError(String(e)));
  };

  const GoalRow = ({ goal }: { goal: Goal }) => (
    <div className={`goal-row ${goal.done ? "done" : ""}`}>
      <button
        className="checkbox"
        role="checkbox"
        aria-checked={goal.done}
        aria-label={`Mark ${goal.title} done`}
        onClick={() => toggle(goal)}
      >
        {goal.done && <CheckIcon />}
      </button>
      <div className="goal-text">
        <h3>{goal.title}</h3>
        {goal.status_line && <p>{goal.status_line}</p>}
      </div>
      <button className="icon-btn small" aria-label="Goal menu"><DotsIcon /></button>
    </div>
  );

  return (
    <div className="page">
      <header className="page-header">
        <h1>Goals</h1>
        <div className="agent-mark">
          <AgentAvatar size={44} />
          <span>Muse</span>
        </div>
        <button className="icon-btn" aria-label="More"><DotsIcon /></button>
      </header>
      <div className="page-body goals">
        {error && <p className="dim">{error}</p>}
        {tracking.length > 0 && (
          <section className="goal-group">
            <h2 className="group-label tracking">Tracking</h2>
            {tracking.map((g) => <GoalRow key={g.id} goal={g} />)}
          </section>
        )}
        <section className="goal-group">
          <h2 className="group-label goals-label">Goals</h2>
          {plain.map((g) => <GoalRow key={g.id} goal={g} />)}
          {plain.length === 0 && <p className="dim">No goals yet. Create one below.</p>}
        </section>

        <section className="create-goal">
          <h2>Create a goal</h2>
          {CATEGORIES.map((cat) => (
            <button key={cat} className="category-row" onClick={() => setCreating(cat)}>
              <span className="category-icon">
                {cat === "Health" ? <HeartIcon /> : cat === "Relationships" ? <CommentIcon /> : <ChevronRightIcon />}
              </span>
              <span>{cat}</span>
              <ChevronRightIcon />
            </button>
          ))}
        </section>
      </div>

      {creating && (
        <div className="modal-backdrop" onClick={() => setCreating(null)}>
          <div className="modal create-goal-modal" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setCreating(null)} aria-label="Close">x</button>
            <h3>New {creating} goal</h3>
            <p className="dim">Name it now; refine the plan together in chat afterwards.</p>
            <input
              autoFocus
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && create()}
              placeholder={`e.g. ${creating === "Health" ? "Train for a 10k" : creating === "Finance" ? "Save for a trip" : "Learn Spanish"}`}
            />
            <button className="primary-btn" onClick={create} disabled={!newTitle.trim()}>
              Create goal
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
