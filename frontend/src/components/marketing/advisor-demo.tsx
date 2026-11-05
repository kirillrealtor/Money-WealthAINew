"use client";

import { useEffect, useReducer, useSyncExternalStore } from "react";
import { Sparkles } from "lucide-react";
import { Mark } from "@/components/brand/logo";

/** SSR-safe prefers-reduced-motion subscription (no setState-in-effect). */
function usePrefersReducedMotion() {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

/**
 * Scripted marketing illustration, not a live model call or streaming backend.
 * Thinking dots and typewritten replies animate fixed synthetic examples.
 * Respects prefers-reduced-motion (shows the final state, no animation).
 */
type Turn = {
  q: string;
  tools: string;
  a: { text: string; em?: boolean }[];
};

const TURNS: Turn[] = [
  {
    q: "How am I doing on dining out this month?",
    tools: "Budgets · Transactions",
    a: [
      { text: "You've spent " },
      { text: "$312.40", em: true },
      { text: " of your " },
      { text: "$450", em: true },
      { text: " dining budget — 69% used with 9 days left. You're pacing right on track." },
    ],
  },
  {
    q: "Can I afford a $1,200 flight in August?",
    tools: "Cash flow · Goals",
    a: [
      { text: "Yes — after rent and your " },
      { text: "$833", em: true },
      { text: " goal contribution, you'll have about " },
      { text: "$1,640", em: true },
      { text: " of free cash. It fits without touching your Emergency Fund." },
    ],
  },
  {
    q: "What's my highest-interest debt?",
    tools: "Debt accounts",
    a: [
      { text: "Your card at " },
      { text: "22.9% APR", em: true },
      { text: ". Paying it first (avalanche) saves you " },
      { text: "$1,180", em: true },
      { text: " versus snowball. Want a payoff plan?" },
    ],
  },
];

type Phase = "thinking" | "typing" | "done";
type State = { turn: number; phase: Phase; chars: number };

function reducer(s: State, a: { type: "tick" } | { type: "phase"; phase: Phase } | { type: "next" }): State {
  switch (a.type) {
    case "phase":
      return { ...s, phase: a.phase, chars: 0 };
    case "tick":
      return { ...s, chars: s.chars + 1 };
    case "next":
      return { turn: (s.turn + 1) % TURNS.length, phase: "thinking", chars: 0 };
  }
}

function fullText(turn: Turn) {
  return turn.a.map((p) => p.text).join("");
}

export function AdvisorDemo() {
  const [state, dispatch] = useReducer(reducer, { turn: 0, phase: "thinking", chars: 0 });
  const reduced = usePrefersReducedMotion();

  const turn = TURNS[state.turn];
  const total = fullText(turn).length;

  useEffect(() => {
    if (reduced) {
      // No motion: just show fully typed, hold, advance slowly.
      if (state.phase !== "done") dispatch({ type: "phase", phase: "done" });
      const t = setTimeout(() => dispatch({ type: "next" }), 5000);
      return () => clearTimeout(t);
    }
    if (state.phase === "thinking") {
      const t = setTimeout(() => dispatch({ type: "phase", phase: "typing" }), 1100);
      return () => clearTimeout(t);
    }
    if (state.phase === "typing") {
      if (state.chars >= total) {
        const t = setTimeout(() => dispatch({ type: "phase", phase: "done" }), 50);
        return () => clearTimeout(t);
      }
      const t = setTimeout(() => dispatch({ type: "tick" }), 18);
      return () => clearTimeout(t);
    }
    // done → hold, then next
    const t = setTimeout(() => dispatch({ type: "next" }), 2600);
    return () => clearTimeout(t);
  }, [state, total, reduced]);

  // Build the partially-typed answer.
  const typed = renderTyped(turn, reduced ? total : state.chars);

  return (
    <div className="relative">
      <p className="mb-4 text-xs text-fg-subtle">Illustrative conversation with synthetic figures.</p>
      <div className="space-y-4">
        {/* user */}
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand/15 px-4 py-2.5 text-sm text-fg ring-1 ring-brand/20">
            {turn.q}
          </div>
        </div>

        {/* assistant */}
        <div className="flex gap-3">
          <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-ink ring-1 ring-brand/30">
            <Mark className="size-4" />
          </span>
          <div className="min-h-[3rem] max-w-[88%] rounded-2xl rounded-tl-md bg-surface-2/70 px-4 py-3 ring-1 ring-line">
            {state.phase === "thinking" && !reduced ? (
              <Thinking />
            ) : (
              <>
                <p className="text-sm leading-relaxed text-fg">
                  {typed}
                  {state.phase === "typing" && !reduced && (
                    <span className="ml-0.5 inline-block h-4 w-[2px] -translate-y-[1px] animate-pulse bg-brand align-middle" />
                  )}
                </p>
                {state.phase === "done" && (
                  <div className="mt-3 flex items-center gap-2 text-xs text-fg-subtle">
                    <span className="rounded-md bg-hover px-2 py-1 ring-1 ring-line">
                      ↳ checked <span className="text-fg-muted">{turn.tools}</span>
                    </span>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* progress dots */}
      <div className="mt-5 flex justify-center gap-1.5">
        {TURNS.map((_, i) => (
          <span
            key={i}
            className={`h-1 rounded-full transition-all duration-300 ${
              i === state.turn ? "w-6 bg-brand" : "w-1.5 bg-hover-strong"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

function renderTyped(turn: Turn, chars: number) {
  const out: React.ReactNode[] = [];
  let remaining = chars;
  turn.a.forEach((part, i) => {
    if (remaining <= 0) return;
    const slice = part.text.slice(0, remaining);
    remaining -= part.text.length;
    out.push(
      part.em ? (
        <span key={i} className="font-medium text-fg tnum">
          {slice}
        </span>
      ) : (
        <span key={i}>{slice}</span>
      ),
    );
  });
  return out;
}

function Thinking() {
  return (
    <span className="flex items-center gap-2 text-sm text-fg-subtle">
      <Sparkles className="size-3.5 text-brand" />
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 rounded-full bg-brand"
            style={{ animation: `think 1.4s ease-in-out ${i * 0.18}s infinite` }}
          />
        ))}
      </span>
      <span>thinking — checking your data…</span>
    </span>
  );
}
