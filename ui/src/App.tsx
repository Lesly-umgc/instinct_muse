import { useEffect, useState } from "react";
import type { Screen } from "./types";
import { api } from "./api";
import ChatScreen from "./screens/ChatScreen";
import FeedScreen from "./screens/FeedScreen";
import IdeasScreen from "./screens/IdeasScreen";
import GoalsScreen from "./screens/GoalsScreen";
import LibraryScreen from "./screens/LibraryScreen";
import SearchScreen from "./screens/SearchScreen";
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
  useEffect(() => {
    api.config().then((c) => {
      const valid: Screen[] = ["chat", "search", "feed", "ideas", "goals", "library"];
      if (valid.includes(c.initial_screen as Screen)) setScreen(c.initial_screen as Screen);
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
        <button title="Menu" aria-label="Menu">
          <MenuIcon />
        </button>
      </nav>
      {screen === "chat" && <ChatScreen />}
      {screen === "search" && <SearchScreen />}
      {screen === "feed" && <FeedScreen />}
      {screen === "ideas" && <IdeasScreen />}
      {screen === "goals" && <GoalsScreen />}
      {screen === "library" && <LibraryScreen />}
    </div>
  );
}
