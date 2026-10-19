import { MessageSquarePlus, BarChart3, LogOut, Trash2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

export interface SessionItem {
  id: string;
  started_at: string;
  preview: string;
}

interface SidebarProps {
  sessions: SessionItem[];
  activeSessionId: string;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

const Sidebar = ({ sessions, activeSessionId, onNewChat, onSelectSession, onDeleteSession }: SidebarProps) => {
  const { signOut, user, authEnabled } = useAuth();

  return (
    <aside className="flex h-full w-64 flex-col border-r border-sidebar-border bg-sidebar">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-5 py-5">
        <BarChart3 className="h-6 w-6 text-primary" />
        <h1 className="text-lg font-semibold tracking-tight text-foreground">
          Ask your database
        </h1>
      </div>

      {/* New Chat */}
      <div className="px-3">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-lg border border-border px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-sidebar-hover"
        >
          <MessageSquarePlus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      {/* Session History */}
      <div className="mt-6 flex-1 overflow-y-auto px-3">
        <p className="mb-2 px-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          History
        </p>
        {sessions.length === 0 && (
          <p className="px-2 text-xs text-muted-foreground">No sessions yet</p>
        )}
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group flex items-center rounded-md transition-colors ${
              session.id === activeSessionId
                ? "bg-primary/15"
                : "hover:bg-sidebar-hover"
            }`}
          >
            <button
              onClick={() => onSelectSession(session.id)}
              className={`flex-1 truncate px-2 py-1.5 text-left text-sm ${
                session.id === activeSessionId
                  ? "text-primary"
                  : "text-sidebar-foreground"
              }`}
            >
              {session.preview}
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDeleteSession(session.id);
              }}
              className="mr-1 rounded p-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
              title="Delete session"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      {/* Sign Out */}
      {authEnabled && (
      <div className="border-t border-sidebar-border px-3 py-3">
        <div className="mb-2 truncate px-2 text-xs text-muted-foreground">
          {user?.email}
        </div>
        <button
          onClick={signOut}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-sidebar-hover hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          Sign Out
        </button>
      </div>
      )}
    </aside>
  );
};

export default Sidebar;
