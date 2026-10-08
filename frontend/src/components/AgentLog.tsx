import { useEffect, useRef, useState } from "react";
import type { RunEvent } from "../types";

const TAG: Record<string, string> = {
  parse_cv: "read",
  plan_queries: "plan",
  fetch_jobs: "fetch",
  triage: "triage",
  refine_queries: "refine",
  shortlist: "rank",
  extract_requirements: "reqs",
  judge_evidence: "judge",
  score_rank: "score",
  pick_jobs: "you",
  rewrite: "rewrite",
  verify: "verify",
  report: "report",
  pipeline: "error",
};

/** Everything the agent wrote down, folded away until you want it. */
export function AgentLog({ events, startTs }: { events: RunEvent[]; startTs: number | null }) {
  const box = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const [open, setOpen] = useState(false);
  const logs = events.filter((e) => e.type === "log");

  useEffect(() => {
    const el = box.current;
    if (el && open && pinned.current) el.scrollTop = el.scrollHeight;
  }, [logs.length, open]);

  if (!logs.length) return null;
  return (
    <details className="log" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>The agent's log ({logs.length} lines)</summary>
      <div
        className="log-lines"
        ref={box}
        role="log"
        tabIndex={0}
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
        }}
      >
        {logs.map((e) => (
          <div key={e.seq} className={`log-line lvl-${e.level ?? "info"}`}>
            <span className="log-time">{startTs ? `+${(e.ts - startTs).toFixed(1)}s` : ""}</span>
            <span className="log-tag">{TAG[e.node ?? ""] ?? e.node}</span>
            <span className="log-msg">{e.message}</span>
          </div>
        ))}
      </div>
    </details>
  );
}
