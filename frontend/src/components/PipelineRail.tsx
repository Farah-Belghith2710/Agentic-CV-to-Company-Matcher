import type { RunEvent, RunStatus, RunView } from "../types";
import { PenBox, PenMark, listJoin } from "./marks";

export interface StageState {
  starts: number;
  done: number;
  active: boolean;
}

interface Phase {
  key: "read" | "search" | "rank" | "pick" | "tailor" | "report";
  short: string;
  todo: string;
  nodes: string[];
  you?: boolean;
}

const PHASES: Phase[] = [
  { key: "read", short: "Read CV", todo: "Read your CV and take out your name and contact details", nodes: ["parse_cv"] },
  { key: "search", short: "Search", todo: "Search for postings that fit your profile", nodes: ["plan_queries", "fetch_jobs", "triage", "refine_queries"] },
  { key: "rank", short: "Rank", todo: "Check each posting requirement by requirement, then rank them", nodes: ["shortlist", "extract_requirements", "judge_evidence", "score_rank"] },
  { key: "pick", short: "Your pick", todo: "Wait for you to pick up to 3 jobs", nodes: ["pick_jobs"], you: true },
  { key: "tailor", short: "Tailor", todo: "Rewrite your CV bullets for those jobs, without inventing anything", nodes: ["rewrite", "verify"] },
  { key: "report", short: "Report", todo: "Write a report you can download", nodes: ["report"] },
];

type State = "done" | "active" | "pending" | "failed";

function phaseState(p: Phase, stages: Record<string, StageState>, status: RunStatus | "idle"): State {
  const started = p.nodes.some((n) => (stages[n]?.starts ?? 0) > 0);
  const active = p.nodes.some((n) => stages[n]?.active) || (!!p.you && status === "awaiting_selection");
  if (status === "error" && started && (active || p.nodes.some((n) => stages[n] && stages[n].done < stages[n].starts))) return "failed";
  if (active) return "active";
  const finished = started && (p.nodes.every((n) => !stages[n] || stages[n].done >= stages[n].starts) || status === "done");
  return finished ? "done" : "pending";
}

function times(n: number) {
  return n === 1 ? "once" : n === 2 ? "twice" : `${n} times`;
}

function doneNote(p: Phase, view: RunView | null, stages: Record<string, StageState>): string | null {
  if (!view) return null;
  switch (p.key) {
    case "read": {
      const removed = Object.entries(view.redaction)
        .filter(([, n]) => n > 0)
        .map(([k, n]) => `${n} ${k}${n > 1 ? "s" : ""}`);
      return removed.length ? `Took out ${listJoin(removed)} before reading.` : "Found nothing personal to take out.";
    }
    case "search": {
      if (!view.pool_size) return null;
      const widened = stages.refine_queries?.starts ?? 0;
      return `Kept ${view.relevant_count} relevant postings out of ${view.pool_size}${widened ? `, after widening the search ${times(widened)}` : ""}.`;
    }
    case "rank":
      return view.ranked.length ? `Looked closely at the best ${view.ranked.length}.` : null;
    case "pick":
      return view.selected.length ? `You picked ${view.selected.length} job${view.selected.length > 1 ? "s" : ""}.` : null;
    case "tailor": {
      const n = view.tailored.length;
      if (!n) return null;
      const rejected = view.tailored.reduce((a, b) => a + b.attempts.filter((x) => !x.ok).length, 0);
      return `Rewrote ${n} bullet${n > 1 ? "s" : ""}; the checker sent back ${rejected} draft${rejected === 1 ? "" : "s"}.`;
    }
    case "report":
      return "Ready to download at the bottom of the page.";
  }
}

/** The agent's to-do list. Full while it works; one line once the ranking is on screen. */
export function PipelineRail({
  stages,
  status,
  view,
  events,
  compact,
}: {
  stages: Record<string, StageState>;
  status: RunStatus | "idle";
  view: RunView | null;
  events: RunEvent[];
  compact: boolean;
}) {
  if (compact) {
    return (
      <ol className="checkline" aria-label="Agent progress">
        {PHASES.map((p) => {
          const s = phaseState(p, stages, status);
          return (
            <li key={p.key} className={`checkline-item is-${s}${p.you ? " is-you" : ""}`} aria-current={s === "active" ? "step" : undefined}>
              {s === "failed" ? <PenMark verdict="missing" size={16} label={false} /> : <PenBox checked={s === "done"} size={17} />}
              {p.short}
              <span className="visually-hidden">{s === "done" ? " (done)" : s === "active" ? " (now)" : s === "failed" ? " (stopped)" : ""}</span>
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <section className="checklist" aria-label="What the agent does">
      <h2 className="section-title">What the agent does</h2>
      <ol className="checklist-items">
        {PHASES.map((p) => {
          const s = phaseState(p, stages, status);
          let note: string | null = null;
          if (s === "done") note = doneNote(p, view, stages);
          else if (s === "active")
            note = p.you
              ? "Your turn: tick up to 3 jobs in the list."
              : ([...events].reverse().find((e) => e.type === "log" && e.node && p.nodes.includes(e.node))?.message ?? null);
          return (
            <li key={p.key} className={`check-item is-${s}${p.you ? " is-you" : ""}`} aria-current={s === "active" ? "step" : undefined}>
              {s === "failed" ? <PenMark verdict="missing" size={20} label={false} /> : <PenBox checked={s === "done"} draw />}
              <div>
                <p className="check-text">
                  {p.todo}
                  <span className="visually-hidden">{s === "done" ? " (done)" : s === "active" ? " (working on it)" : s === "failed" ? " (stopped)" : ""}</span>
                </p>
                {note && <p className="check-note">{note}</p>}
              </div>
            </li>
          );
        })}
      </ol>
      {status === "idle" && (
        <p className="checklist-key">
          In the results, every requirement gets a highlighter: <mark className="hl hl-met hl-must">your CV shows it</mark>,{" "}
          <mark className="hl hl-partial hl-must">only partly</mark> or <mark className="hl hl-missing hl-must">not in your CV</mark>.
        </p>
      )}
    </section>
  );
}
