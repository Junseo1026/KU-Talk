import { ExternalLink } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ChatMessageProps {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
}

export const ChatMessage = ({ id, role, content, sources }: ChatMessageProps) => {
  const isUser = role === "user";

  // Show user messages on the right and assistant on the left
  return (
    <div id={`msg-${id}`} data-role={role} className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4 animate-slide-up`}>
      <Card
        className={`max-w-[75%] p-4 ${
          isUser
            ? "bg-primary text-white shadow-md border-0"
            : "bg-primary/10 text-foreground shadow-sm border border-primary/20"
        } rounded-lg`}
      >
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>
            
            {sources && sources.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border/30">
                <p className="text-xs font-medium mb-2 text-muted-foreground">출처:</p>
                <div className="flex flex-col gap-2">
                  {sources.map((source, index) => (
                    <a
                      key={index}
                      href={source}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 text-xs hover:text-primary transition-colors group"
                    >
                      <Badge variant="outline" className="gap-1">
                        <ExternalLink className="h-3 w-3" />
                        <span className="group-hover:underline">링크 {index + 1}</span>
                      </Badge>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
};
