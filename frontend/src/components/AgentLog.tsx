import { useEffect, useRef } from "react";
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

export function AgentLog({ events, startTs }: { events: RunEvent[]; startTs: number | null }) {
  const box = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const logs = events.filter((e) => e.type === "log");
  return (
    <section className="log" aria-label="Agent log">
      <h2 className="panel-title">What the agent is doing</h2>
      <div
        className="log-lines"
        ref={box}
        role="log"
        aria-live="polite"
        onScroll={(e) => {
          const el = e.currentTarget;
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
        }}
      >
        {logs.length === 0 && <p className="log-empty">Steps appear here as the agent works.</p>}
        {logs.map((e) => (
          <div key={e.seq} className={`log-line lvl-${e.level ?? "info"}`}>
            <span className="log-time">{startTs ? `+${(e.ts - startTs).toFixed(1)}s` : ""}</span>
            <span className="log-tag">{TAG[e.node ?? ""] ?? e.node}</span>
            <span className="log-msg">{e.message}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
