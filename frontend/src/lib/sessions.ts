import type { SessionItem } from "@/components/Sidebar";

// The API keeps each conversation's messages but has no "list my conversations" endpoint
// (there are no per-user accounts on the backend yet), so the sidebar list lives in the browser.
const STORAGE_KEY = "ask-your-database:sessions";
const MAX_SESSIONS = 50;

export function loadSessions(): SessionItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as SessionItem[]) : [];
  } catch {
    return [];
  }
}

function save(sessions: SessionItem[]): SessionItem[] {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // Storage full or blocked: the list just won't survive a reload.
  }
  return sessions;
}

export function rememberSession(id: string, firstMessage: string): SessionItem[] {
  const sessions = loadSessions();
  if (sessions.some((s) => s.id === id)) return sessions;
  const item: SessionItem = { id, started_at: new Date().toISOString(), preview: firstMessage.slice(0, 80) };
  return save([item, ...sessions].slice(0, MAX_SESSIONS));
}

export function forgetSession(id: string): SessionItem[] {
  return save(loadSessions().filter((s) => s.id !== id));
}
