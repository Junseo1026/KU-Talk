import { useState, useRef, useEffect } from "react";
import { ChatMessage } from "./ChatMessage";
import { ChatInput } from "./ChatInput";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

export const ChatInterface = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // scroll behavior: if there's a recent user message, scroll it to top
    try {
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      if (lastUser) {
        const el = document.getElementById(`msg-${lastUser.id}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
          return;
        }
      }
      if (endRef.current) {
        endRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
      }
    } catch (e) {
      // ignore
    }
  }, [messages, isLoading]);

  const handleSendMessage = async (content: string) => {
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 25000); // 25s timeout
      // Build backend URL dynamically so frontend served on a different host
      // can call the backend on the same server. If you'd rather set an
      // explicit URL, set VITE_BACKEND_URL in env and Vite will expose it.
      const backendHost = window.location.hostname;
      const backendPort = import.meta.env.VITE_BACKEND_PORT || '8000';
      const backendProtocol = window.location.protocol;
      const backendUrl = (import.meta.env.VITE_BACKEND_URL) || `${backendProtocol}//${backendHost}:${backendPort}`;
      const resp = await fetch(`${backendUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: content, top_k: 5 }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!resp.ok) {
        throw new Error(`API error ${resp.status}`);
      }
      const data = await resp.json();
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: data.answer || "답변을 가져올 수 없습니다.",
        sources: (data.sources || []).map((s: any) => s.url || s),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `오류: ${err.message || err}`,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full w-full mx-auto bg-background rounded-3xl shadow-elegant border border-border/50 overflow-hidden backdrop-blur-sm">
      <ScrollArea className="flex-1 px-6 py-6">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center space-y-3 animate-fade-in">
              <p className="text-lg text-muted-foreground">
                궁금한 점을 질문해주세요. 출처와 함께 답변해드립니다.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                id={message.id}
                role={message.role}
                content={message.content}
                sources={message.sources}
              />
            ))}
            <div ref={endRef} />
            {isLoading && (
              <div className="flex justify-start mb-4">
                <div className="bg-primary/10 p-4 rounded-lg shadow-sm border border-primary/20">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:0.2s]" />
                    <div className="w-2 h-2 bg-primary rounded-full animate-bounce [animation-delay:0.4s]" />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </ScrollArea>
      <div className="p-4 border-t border-border/30 bg-background/98">
        <ChatInput onSend={handleSendMessage} disabled={isLoading} />
      </div>
    </div>
  );
};
