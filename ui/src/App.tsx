import { useEffect, useState } from "react";
import type { Screen } from "./types";
import { api } from "./api";
import ChatScreen from "./screens/ChatScreen";
import FeedScreen from "./screens/FeedScreen";
import IdeasScreen from "./screens/IdeasScreen";
import GoalsScreen from "./screens/GoalsScreen";
import LibraryScreen from "./screens/LibraryScreen";
import SearchScreen from "./screens/SearchScreen";
import SettingsScreen from "./screens/SettingsScreen";
import AgentAvatar from "./components/AgentAvatar";
import {
  ChatIcon, SearchIcon, FeedIcon, IdeasIcon, GoalsIcon, LibraryIcon,
  QuickChatIcon, MenuIcon,
} from "./components/icons";

const NAV: { id: Screen; label: string; Icon: () => JSX.Element }[] = [
  { id: "chat", label: "Chat", Icon: ChatIcon },
  { id: "search", label: "Search", Icon: SearchIcon },
  { id: "feed", label: "Feed", Icon: FeedIcon },
  { id: "ideas", label: "Ideas", Icon: IdeasIcon },
  { id: "goals", label: "Goals", Icon: GoalsIcon },
  { id: "library", label: "Library", Icon: LibraryIcon },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("chat");
  const [initialChat, setInitialChat] = useState("");
  const [settingsSection, setSettingsSection] = useState("");
  const [deep, setDeep] = useState<{ goal: string; artifact: string; search: string; forceError: string }>({ goal: "", artifact: "", search: "", forceError: "" });
  useEffect(() => {
    const order: Screen[] = ["chat", "search", "feed", "ideas", "goals", "library"];
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === ",") { e.preventDefault(); setScreen("settings"); return; }
      if (e.key.toLowerCase() === "k") { e.preventDefault(); setScreen("search"); return; }
      const n = Number(e.key);
      if (n >= 1 && n <= order.length) { e.preventDefault(); setScreen(order[n - 1]); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => {
    import("./api").then(({ waitForService }) =>
      waitForService(60).then(() => api.config())
    ).then((c) => {
      const valid: Screen[] = ["chat", "search", "feed", "ideas", "goals", "library", "settings"];
      if (valid.includes(c.initial_screen as Screen)) setScreen(c.initial_screen as Screen);
      if (c.initial_chat) setInitialChat(c.initial_chat);
      if (c.initial_settings_section) setSettingsSection(c.initial_settings_section);
      setDeep({
        goal: c.initial_goal ?? "", artifact: c.initial_artifact ?? "",
        search: c.initial_search ?? "", forceError: c.force_error ?? "",
      });
    }).catch(() => {});
  }, []);
  return (
    <div className="app">
      <nav className="rail" aria-label="Main navigation">
        <button className="quick-chat" title="Quick chat" aria-label="Quick chat"
          onClick={() => setScreen("chat")}>
          <QuickChatIcon />
        </button>
        {NAV.map(({ id, label, Icon }) => (
          <button
            key={id}
            className={screen === id ? "active" : ""}
            title={label}
            aria-label={label}
            onClick={() => setScreen(id)}
          >
            <Icon />
          </button>
        ))}
        <div className="spacer" />
        <button className="rail-avatar" title="You" aria-label="You">
          <AgentAvatar size={34} />
        </button>
        <button title="Settings" aria-label="Settings" onClick={() => setScreen("settings")}>
          <MenuIcon />
        </button>
      </nav>
      {screen === "chat" && <ChatScreen initialChatId={initialChat} forceError={deep.forceError} />}
      {screen === "search" && <SearchScreen initialQuery={deep.search} />}
      {screen === "feed" && <FeedScreen />}
      {screen === "ideas" && <IdeasScreen />}
      {screen === "goals" && <GoalsScreen initialGoalId={deep.goal} />}
      {screen === "library" && <LibraryScreen initialArtifactId={deep.artifact} />}
      {screen === "settings" && <SettingsScreen initialSection={settingsSection} />}
    </div>
  );
}
