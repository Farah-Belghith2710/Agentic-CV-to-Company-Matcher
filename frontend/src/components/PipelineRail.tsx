import type { RunStatus } from "../types";

export interface StageState {
  starts: number;
  done: number;
  active: boolean;
}

const PHASES: { title: string; nodes: string[]; loop?: { node: string; label: (n: number) => string } }[] = [
  { title: "Read CV", nodes: ["parse_cv"] },
  {
    title: "Search",
    nodes: ["plan_queries", "fetch_jobs", "triage", "refine_queries"],
    loop: { node: "refine_queries", label: (n) => `search widened ${n}×` },
  },
  { title: "Rank", nodes: ["shortlist", "extract_requirements", "judge_evidence", "score_rank"] },
  { title: "You pick", nodes: ["pick_jobs"] },
  { title: "Tailor", nodes: ["rewrite", "verify"], loop: { node: "rewrite", label: (n) => `redrafted ${n}×` } },
  { title: "Report", nodes: ["report"] },
];

const NODE_LABEL: Record<string, string> = {
  parse_cv: "redact and split",
  plan_queries: "plan queries",
  fetch_jobs: "fetch postings",
  triage: "triage",
  refine_queries: "refine",
  shortlist: "shortlist",
  extract_requirements: "requirements",
  judge_evidence: "evidence",
  score_rank: "score",
  pick_jobs: "choose jobs",
  rewrite: "rewrite",
  verify: "verify",
  report: "write report",
};

export function PipelineRail({ stages, status }: { stages: Record<string, StageState>; status: RunStatus | "idle" }) {
  return (
    <ol className="rail" aria-label="Agent progress">
      {PHASES.map((p, i) => {
        const started = p.nodes.some((n) => (stages[n]?.starts ?? 0) > 0);
        const active = p.nodes.some((n) => stages[n]?.active) || (p.title === "You pick" && status === "awaiting_selection");
        const finished = !active && started && (p.nodes.every((n) => !stages[n] || stages[n].done >= stages[n].starts) || status === "done");
        const state = active ? "active" : finished ? "done" : "pending";
        const loops = p.loop ? (stages[p.loop.node]?.starts ?? 0) - (p.loop.node === "rewrite" ? 1 : 0) : 0;
        return (
          <li key={p.title} className={`phase is-${state}`} aria-current={active ? "step" : undefined}>
            <div className="phase-head">
              <span className="phase-no">{i + 1}</span>
              <span className="phase-title">{p.title}</span>
            </div>
            <ul className="phase-nodes">
              {p.nodes.map((n) => {
                const s = stages[n];
                const nodeState = s?.active ? "active" : s && s.done > 0 ? "done" : "pending";
                return (
                  <li key={n} className={`node is-${nodeState}`}>
                    {NODE_LABEL[n]}
                  </li>
                );
              })}
            </ul>
            {p.loop && loops > 0 && <span className="phase-loop">{p.loop.label(loops)}</span>}
          </li>
        );
      })}
    </ol>
  );
}
