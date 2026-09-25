export interface EngineStatus {
  id: string;
  name: string;
  available: boolean;
  reason: string;
  detail: string;
}

export interface ModelInfo {
  engine: string;
  provider_id: string;
  model_id: string;
  label: string;
  is_default: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  engine: string;
  model: string | null;
  engine_session_id: string | null;
  created_at: number;
  updated_at: number;
  messages?: Message[];
}

export interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  created_at: number;
}

export interface Artifact {
  id: string;
  conversation_id: string | null;
  kind: string;
  path: string;
  title: string;
  content: string | null;
  created_at: number;
}

export interface Approval {
  id: string;
  conversation_id: string | null;
  engine_permission_id: string | null;
  action: string;
  detail: string;
  status: string;
  created_at: number;
  resolved_at: number | null;
}

export interface Goal {
  id: string;
  title: string;
  status_line: string;
  group_name: string;
  category: string;
  done: boolean;
  created_at: number;
  updated_at: number;
}

export interface FeedItem {
  id: string;
  edition_id: string;
  title: string;
  body: string;
  links: { label: string; url: string }[];
  loved: boolean;
  created_at: number;
}

export interface FeedEdition {
  id: string;
  label: string;
  created_at: number;
  items?: FeedItem[];
}

export interface Idea {
  id: string;
  title: string;
  body: string;
  category: string;
  dismissed: boolean;
  created_at: number;
}

export interface SearchResult {
  kind: string;
  id: string;
  title: string;
  snippet: string;
}

export type Screen = "chat" | "search" | "feed" | "ideas" | "goals" | "library" | "settings";
