import { useState, useRef, useEffect, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import type { SessionItem } from "@/components/Sidebar";
import ChatMessageComponent from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";
import ThinkingIndicator from "@/components/ThinkingIndicator";
import { ApiError, fetchHistory, sendChat } from "@/lib/api";
import type { ChatResponse } from "@/lib/api";
import { forgetSession, loadSessions, rememberSession } from "@/lib/sessions";
import type { ChatMessage } from "@/lib/types";

function roleFor(type: ChatResponse["type"]): ChatMessage["role"] {
  if (type === "blocked") return "warning";
  if (type === "error") return "error";
  return "assistant";
}

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    return err.requestId ? `${err.message} (request id ${err.requestId})` : err.message;
  }
  return "Something went wrong. Please try again.";
}

const Index = () => {
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessions, setSessions] = useState<SessionItem[]>(loadSessions);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleNewChat = useCallback(() => {
    setSessionId(crypto.randomUUID());
    setMessages([]);
    setIsLoading(false);
  }, []);

  const handleSelectSession = useCallback(async (selectedId: string) => {
    setSessionId(selectedId);
    setIsLoading(false);
    setMessages([]);

    try {
      // History holds the text of each turn; charts and SQL are only shown live.
      const history = await fetchHistory(selectedId);
      setMessages(
        history.map((m) => ({
          id: crypto.randomUUID(),
          role: m.role === "user" ? "user" : "assistant",
          content: m.content,
        })),
      );
    } catch (err) {
      setMessages([{ id: crypto.randomUUID(), role: "error", content: errorText(err) }]);
    }
  }, []);

  const handleDeleteSession = useCallback(
    (targetId: string) => {
      setSessions(forgetSession(targetId));
      if (targetId === sessionId) handleNewChat();
    },
    [sessionId, handleNewChat],
  );

  const handleSend = useCallback(
    async (prompt: string) => {
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: prompt }]);
      setIsLoading(true);

      try {
        const res = await sendChat(prompt, sessionId);
        setSessions(rememberSession(res.session_id, prompt));
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: roleFor(res.type),
            content: res.message,
            responseType: res.type,
            query: res.query,
            chart: res.chart,
            trace: res.trace,
          },
        ]);
      } catch (err) {
        console.error("Chat request failed:", err);
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "error", content: errorText(err) }]);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId],
  );

  const handleEditMessage = useCallback(
    (messageId: string, newContent: string) => {
      // Drop the edited message and everything after it from the view, then resend.
      const idx = messages.findIndex((m) => m.id === messageId);
      if (idx === -1) return;
      setMessages(messages.slice(0, idx));
      handleSend(newContent);
    },
    [messages, handleSend],
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        sessions={sessions}
        activeSessionId={sessionId}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />

      <main className="flex flex-1 flex-col">
        <div className="flex-1 overflow-y-auto py-6">
          {messages.length === 0 && !isLoading && (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
              <p className="text-2xl font-semibold text-foreground">Ask your database</p>
              <p className="text-sm">
                Ask a question about the telecom warehouse in plain language. Try "Plot monthly revenue for 2025".
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <ChatMessageComponent
              key={msg.id}
              message={msg}
              onEdit={msg.role === "user" && !isLoading ? handleEditMessage : undefined}
            />
          ))}

          {isLoading && <ThinkingIndicator />}

          <div ref={bottomRef} />
        </div>

        <ChatInput onSend={handleSend} disabled={isLoading} />
      </main>
    </div>
  );
};

export default Index;
