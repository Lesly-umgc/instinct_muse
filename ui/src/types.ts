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

export type Screen = "chat" | "feed" | "ideas" | "goals" | "library";
