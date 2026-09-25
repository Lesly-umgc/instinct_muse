import { useState } from "react";
import type { Screen } from "./types";
import ChatScreen from "./screens/ChatScreen";
import LibraryScreen from "./screens/LibraryScreen";
import PlaceholderScreen from "./screens/PlaceholderScreen";
import { ChatIcon, FeedIcon, GoalsIcon, IdeasIcon, LibraryIcon } from "./components/icons";

const NAV: { id: Screen; label: string; Icon: () => JSX.Element }[] = [
  { id: "chat", label: "Chat", Icon: ChatIcon },
  { id: "feed", label: "Feed", Icon: FeedIcon },
  { id: "ideas", label: "Ideas", Icon: IdeasIcon },
  { id: "goals", label: "Goals", Icon: GoalsIcon },
  { id: "library", label: "Library", Icon: LibraryIcon },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("chat");
  return (
    <div className="app">
      <nav className="rail" aria-label="Main navigation">
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
      </nav>
      {screen === "chat" && <ChatScreen />}
      {screen === "library" && <LibraryScreen />}
      {screen === "feed" && (
        <PlaceholderScreen
          title="Feed"
          body="Scheduled briefings with source links will live here. Coming in phase 2, once goals and scheduling land in the app service."
        />
      )}
      {screen === "ideas" && (
        <PlaceholderScreen
          title="Ideas"
          body="Personalized suggestions from your memory and goals. Coming in phase 2."
        />
      )}
      {screen === "goals" && (
        <PlaceholderScreen
          title="Goals"
          body="Durable goal tracking and the execution queue. Coming in phase 2 - the records live in the app service, not the engine, so they survive engine switches."
        />
      )}
    </div>
  );
}
