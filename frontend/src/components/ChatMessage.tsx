import { useState } from "react";
import type { ChatMessage as ChatMessageType } from "@/lib/types";
import ChartRenderer from "./ChartRenderer";
import Markdown from "./Markdown";
import SqlPanel from "./SqlPanel";
import AgentTrace from "./AgentTrace";
import { AlertTriangle, XCircle, Pencil, Check, X } from "lucide-react";

interface ChatMessageProps {
  message: ChatMessageType;
  onEdit?: (messageId: string, newContent: string) => void;
}

const ChatMessageComponent = ({ message, onEdit }: ChatMessageProps) => {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(message.content);

  if (message.role === "user") {
    return (
      <div className="flex justify-end px-6 py-2 group">
        {editing ? (
          <div className="flex max-w-[70%] flex-col gap-2">
            <textarea
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              className="w-full rounded-2xl bg-user-bubble px-4 py-3 text-sm leading-relaxed text-user-bubble-foreground outline-none resize-none border border-primary/30"
              rows={Math.max(2, editValue.split("\n").length)}
              autoFocus
            />
            <div className="flex justify-end gap-1.5">
              <button
                onClick={() => { setEditing(false); setEditValue(message.content); }}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-secondary transition-colors"
                title="Cancel"
              >
                <X className="h-4 w-4" />
              </button>
              <button
                onClick={() => {
                  const trimmed = editValue.trim();
                  if (trimmed && trimmed !== message.content && onEdit) {
                    onEdit(message.id, trimmed);
                  }
                  setEditing(false);
                }}
                className="rounded-lg bg-primary p-1.5 text-primary-foreground hover:opacity-90 transition-opacity"
                title="Save & resend"
              >
                <Check className="h-4 w-4" />
              </button>
            </div>
          </div>
        ) : (
          <div className="relative max-w-[70%]">
            <div className="rounded-2xl rounded-tr-sm bg-user-bubble px-4 py-3 text-sm leading-relaxed text-user-bubble-foreground">
              {message.content}
            </div>
            {onEdit && (
              <button
                onClick={() => { setEditValue(message.content); setEditing(true); }}
                className="absolute -left-8 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:bg-secondary"
                title="Edit & resend"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  if (message.role === "error") {
    return (
      <div className="flex items-start gap-2 px-6 py-2">
        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="max-w-[70%] rounded-2xl rounded-tl-sm bg-destructive/10 px-4 py-3 text-sm leading-relaxed text-destructive">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "warning") {
    return (
      <div className="flex items-start gap-2 px-6 py-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--warning))]" />
        <div className="max-w-[70%] rounded-2xl rounded-tl-sm bg-[hsl(var(--warning)/0.1)] px-4 py-3 text-sm leading-relaxed text-[hsl(var(--warning))]">
          <Markdown>{message.content}</Markdown>
        </div>
      </div>
    );
  }

  // Assistant
  return (
    <div className="px-6 py-2">
      <div className="max-w-[80%]">
        <div className="rounded-2xl rounded-tl-sm bg-assistant-bubble px-4 py-3 text-sm leading-relaxed text-assistant-bubble-foreground">
          <Markdown>{message.content}</Markdown>
        </div>
        {message.chart && (
          <div className="mt-2 rounded-xl border border-border bg-card p-4">
            <ChartRenderer spec={message.chart.spec} data={message.chart.data} />
          </div>
        )}
        {message.query && <SqlPanel query={message.query} />}
        {message.trace && message.trace.length > 0 && <AgentTrace trace={message.trace} />}
      </div>
    </div>
  );
};

export default ChatMessageComponent;
