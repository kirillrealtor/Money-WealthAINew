"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Sparkles, ArrowUp, ThumbsUp, ThumbsDown, AlertTriangle, History, Plus } from "lucide-react";
import { Mark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth/context";
import { useSendMessage, useFeedback, useChatList, useChatLoader } from "@/lib/api/advisor";
import { ApiRequestError } from "@/lib/api/client";
import { ChatMarkdown } from "@/components/advisor/chat-markdown";

type Msg =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; content: string; messageId: string; tools: string[]; fresh: boolean }
  | { id: string; role: "error"; content: string };

const SUGGESTIONS = [
  "How am I doing on my budgets this month?",
  "What should I focus on to hit my goals faster?",
  "Where is most of my money going?",
  "Help me build a debt payoff plan.",
  "Plan me a perfect budgeting plan to manage expenses properly"
];

export default function AdvisorPage() {
  const { user } = useAuth();
  const send = useSendMessage();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [chatId, setChatId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const loadChat = useChatLoader();
  const scrollRef = useRef<HTMLDivElement>(null);

  function newChat() {
    setMessages([]);
    setChatId(undefined);
  }

  async function openChat(id: string) {
    setHistoryOpen(false);
    try {
      const msgs = await loadChat(id);
      setChatId(id);
      setMessages(
        msgs.map((m) =>
          m.role === "assistant"
            ? { id: m.message_id, role: "assistant", content: m.content, messageId: m.message_id, tools: [], fresh: false }
            : { id: m.message_id, role: "user", content: m.content },
        ),
      );
    } catch {
      toast.error("Couldn't load that conversation.");
    }
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function submit(text: string) {
    const msg = text.trim();
    if (!msg || send.isPending) return;
    setInput("");
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: msg }]);
    try {
      const res = await send.mutateAsync({ message: msg, chat_id: chatId });
      setChatId(res.chat_id);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.response,
          messageId: res.message_id,
          tools: res.tool_calls_made,
          fresh: true,
        },
      ]);
    } catch (err) {
      const code = err instanceof ApiRequestError ? err.payload.code : "";
      const serverMsg = err instanceof ApiRequestError ? err.payload.message : "";
      const content =
        code === "AI_UNAVAILABLE"
          ? "The advisor is temporarily unavailable. Every other feature keeps working — please try again in a moment."
          : code === "RATE_LIMITED"
            ? // RATE_LIMITED covers both the per-minute cap and the daily token
              // budget — show the server's specific reason when it has one.
              serverMsg || "You're sending messages quickly — give it a few seconds and try again."
            : "Something went wrong reaching the advisor. Please try again.";
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: "error", content }]);
    }
  }

  const empty = messages.length === 0;

  return (
    <div className="mx-auto flex h-[calc(100dvh-7rem)] max-w-3xl flex-col">
      {/* header */}
      <div className="flex items-center justify-between pb-4">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-medium tracking-tight">Advisor</h1>
          <Badge tone="brand"><Sparkles className="size-3.5" /> Grounded</Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)}>
            <History className="size-4" /> History
          </Button>
          <Button variant="ghost" size="sm" onClick={newChat}>
            <Plus className="size-4" /> New
          </Button>
        </div>
      </div>

      <ChatHistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} onSelect={openChat} />

      {/* thread */}
      <div
        ref={scrollRef}
        role="log"
        aria-live="polite"
        aria-label="Advisor conversation"
        className="flex-1 space-y-5 overflow-y-auto pb-4 pr-1"
      >
        {empty ? (
          <Welcome onPick={submit} name={user?.full_name?.split(" ")[0]} />
        ) : (
          messages.map((m) => <MessageBubble key={m.id} msg={m} />)
        )}
        {send.isPending && <Thinking />}
      </div>

      {/* composer */}
      <Composer value={input} onChange={setInput} onSend={() => submit(input)} disabled={send.isPending} />
    </div>
  );
}

function ChatHistoryDialog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSelect: (id: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Conversations" description="Your recent advisor chats.">
        {open && <HistoryList onSelect={onSelect} />}
      </DialogContent>
    </Dialog>
  );
}

function HistoryList({ onSelect }: { onSelect: (id: string) => void }) {
  const { data, isLoading } = useChatList();
  if (isLoading) return <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-12" />)}</div>;
  if (!data || data.length === 0)
    return <p className="py-8 text-center text-sm text-fg-subtle">No past conversations yet.</p>;
  return (
    <div className="max-h-[60vh] space-y-1.5 overflow-y-auto">
      {data.map((c) => (
        <button
          key={c.chat_id}
          onClick={() => onSelect(c.chat_id)}
          className="block w-full rounded-[12px] px-3 py-2.5 text-left transition-colors hover:bg-hover"
        >
          <p className="truncate text-sm text-fg">{c.preview ?? "Conversation"}</p>
          <p className="text-xs text-fg-subtle">
            {new Date(c.started_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </p>
        </button>
      ))}
    </div>
  );
}

function Welcome({ onPick, name }: { onPick: (s: string) => void; name?: string }) {
  return (
    <div className="flex flex-col items-center pt-10 text-center">
      <span className="grid size-14 place-items-center rounded-2xl bg-ink ring-1 ring-brand/30">
        <Mark className="size-8" />
      </span>
      <h2 className="mt-5 text-2xl font-medium tracking-tight">
        Hi {name || "there"} — ask me anything about your{" "}
        <span className="font-display italic text-aurora">money.</span>
      </h2>
      <p className="mt-2 max-w-md text-sm text-fg-muted">
        I answer from your real data — and I won&apos;t invent numbers.
      </p>
      <div className="mt-7 grid w-full gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="glass rounded-[14px] px-4 py-3 text-left text-sm text-fg-muted transition-all hover:text-fg hover:ring-glow"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand/15 px-4 py-2.5 text-sm text-fg ring-1 ring-brand/20">
          {msg.content}
        </div>
      </div>
    );
  }
  if (msg.role === "error") {
    return (
      <div className="flex gap-3">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-warning/15 ring-1 ring-warning/30">
          <AlertTriangle className="size-4 text-warning" />
        </span>
        <div className="max-w-[85%] rounded-2xl rounded-tl-md border border-warning/25 bg-warning/5 px-4 py-3 text-sm text-fg-muted">
          {msg.content}
        </div>
      </div>
    );
  }
  return <AssistantBubble msg={msg} />;
}

function AssistantBubble({ msg }: { msg: Extract<Msg, { role: "assistant" }> }) {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-ink ring-1 ring-brand/30">
        <Mark className="size-4" />
      </span>
      <div className="min-w-0 max-w-[85%]">
        <div
          className={`rounded-2xl rounded-tl-md bg-surface-2/70 px-4 py-3 text-sm leading-relaxed text-fg ring-1 ring-line ${
            msg.fresh ? "animate-rise" : ""
          }`}
        >
          <ChatMarkdown>{msg.content}</ChatMarkdown>
        </div>
        <Feedback messageId={msg.messageId} />
      </div>
    </div>
  );
}

function Feedback({ messageId }: { messageId: string }) {
  const fb = useFeedback();
  const [done, setDone] = useState<null | "up" | "down">(null);
  function rate(rating: -1 | 1, kind: "up" | "down") {
    setDone(kind);
    fb.mutate({ messageId, rating }, { onError: () => toast.error("Couldn't send feedback.") });
  }
  return (
    <div className="mt-2 flex items-center gap-1">
      <button onClick={() => rate(1, "up")} aria-label="Helpful" disabled={!!done}
        className={`grid size-7 place-items-center rounded-lg transition-colors ${done === "up" ? "text-positive" : "text-fg-subtle hover:text-fg"}`}>
        <ThumbsUp className="size-3.5" />
      </button>
      <button onClick={() => rate(-1, "down")} aria-label="Not helpful" disabled={!!done}
        className={`grid size-7 place-items-center rounded-lg transition-colors ${done === "down" ? "text-negative" : "text-fg-subtle hover:text-fg"}`}>
        <ThumbsDown className="size-3.5" />
      </button>
    </div>
  );
}

function Thinking() {
  return (
    <div className="flex gap-3">
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-ink ring-1 ring-brand/30">
        <Mark className="size-4" />
      </span>
      <div className="flex items-center gap-2 rounded-2xl rounded-tl-md bg-surface-2/70 px-4 py-3 text-sm text-fg-subtle ring-1 ring-line">
        <span className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span key={i} className="size-1.5 rounded-full bg-brand" style={{ animation: `think 1.4s ease-in-out ${i * 0.18}s infinite` }} />
          ))}
        </span>
        thinking — checking your data…
      </div>
    </div>
  );
}

function Composer({
  value,
  onChange,
  onSend,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea up to its max height as the user types.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  return (
    <div className="glass rounded-[18px] p-2">
      <div className="flex items-end gap-2">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value.slice(0, 2000))}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          rows={1}
          aria-label="Message the advisor"
          placeholder="Ask about your budgets, goals, debt…"
          className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-fg outline-none placeholder:text-fg-subtle"
        />
        <Button size="icon" onClick={onSend} disabled={disabled || !value.trim()} aria-label="Send">
          <ArrowUp className="size-4" />
        </Button>
      </div>
      <p className="px-3 pb-1 text-[11px] text-fg-subtle">
        Educational information, not financial advice. Press Enter to send.
      </p>
    </div>
  );
}
