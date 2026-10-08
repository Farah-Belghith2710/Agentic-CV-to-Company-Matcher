import type { ReactNode } from "react";
import type { RankedJob, Requirement, Verdict } from "../types";

/** Plain words for each verdict, read out by screen readers and shown in tooltips. */
export const VERDICT_WORDS: Record<Verdict, string> = { met: "in your CV", partial: "partly in your CV", missing: "not in your CV" };

/* Pen strokes, drawn by hand in a 20 x 20 box. */
const PEN: Record<Verdict, string> = {
  met: "M3.6 10.9c1.5 1.1 2.8 2.6 3.9 4.5 2.2-4.7 5-8.4 8.8-11.4",
  partial: "M2.8 11.4c1.7-2.6 3.4-2.7 4.9-.4 1.5 2.4 3.2 2.5 4.9-.1 1.2-1.8 2.5-2.2 4.5-1.1",
  missing: "M4.8 4.9c3.4 3.2 6.9 6.9 10.4 10.5M15.1 4.5c-3.4 3.3-7 7.2-10.5 11.1",
};

/** The mark a person makes in the margin: a tick, a wavy "sort of", or a cross. */
export function PenMark({ verdict, size = 18, label = true }: { verdict: Verdict; size?: number; label?: boolean }) {
  return (
    <svg
      className={`pen pen-${verdict}`}
      width={size}
      height={size}
      viewBox="0 0 20 20"
      role={label ? "img" : undefined}
      aria-label={label ? VERDICT_WORDS[verdict] : undefined}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={PEN[verdict]} pathLength={1} />
    </svg>
  );
}

/** A hand-drawn checkbox. `draw` animates the tick the moment it appears. */
export function PenBox({ checked, draw = false, size = 20 }: { checked: boolean; draw?: boolean; size?: number }) {
  return (
    <svg className={`penbox${checked ? " is-checked" : ""}${draw ? " is-drawn" : ""}`} width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path className="penbox-box" d="M3.4 3.8c4.5-.5 8.9-.6 13.4-.3.3 4.4.4 8.8.1 13.1-4.5.4-9 .3-13.4 0-.4-4.3-.4-8.6-.1-12.8Z" />
      {checked && <path className="penbox-tick" d="M5.4 10.3c1.3.9 2.4 2.1 3.2 3.7 1.9-3.9 4.4-7.1 7.9-9.9" pathLength={1} />}
    </svg>
  );
}

/** Highlighter on a requirement: a full swipe for must-haves, a swipe under the words for nice-to-haves. */
export function Hl({ verdict, kind = "must", title, children }: { verdict: Verdict | "asked"; kind?: "must" | "nice"; title?: string; children: ReactNode }) {
  return (
    <mark className={`hl hl-${verdict} hl-${kind}`} title={title}>
      {children}
      {verdict !== "asked" && <span className="visually-hidden"> ({VERDICT_WORDS[verdict]})</span>}
    </mark>
  );
}

/** A loose pen circle around the fit score. */
export function ScoreCircle() {
  return (
    <svg className="score-circle" viewBox="0 0 120 76" aria-hidden="true" focusable="false">
      <path d="M66 8C38 5 10 15 7 35c-3 21 25 34 58 33 31-1 51-14 49-33C112 17 90 6 57 8c-10 .6-18 2.4-25 5.6" pathLength={1} />
    </svg>
  );
}

/** Wordmark tick: the one thing the app does, ticking requirements off. */
export function Logo() {
  return (
    <svg className="logo" width="26" height="26" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path className="logo-hl" d="M1.5 6.2c5.5-.9 11.3-1.1 17-.4l-.3 9.4c-5.6.6-11.2.6-16.8-.2Z" />
      <path className="logo-tick" d="M4 10.4c1.6 1.1 2.9 2.6 3.9 4.6 2.3-4.9 5.2-8.8 9.2-12" />
    </svg>
  );
}

const lcFirst = (s: string) => (/^[A-Z][a-z]/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);

/** A short name for a requirement, for the job list: "Python", "French and English", "2+ years of vibration analysis". */
export function reqLabel(r: Requirement): string {
  const years = r.min_years ? `${Number.isInteger(r.min_years) ? r.min_years : r.min_years.toFixed(1)}+ years` : "";
  if (r.category === "language" && r.languages.length) return r.languages.join(" and ");
  if (r.category === "education") return /ing[ée]nieur|engineer/i.test(r.text) ? "Engineering degree" : "Degree";
  if (r.category === "experience" && years) return r.skills[0] ? `${years} of ${lcFirst(r.skills[0])}` : `${years} of experience`;
  if (r.skills.length) return r.skills[0];
  if (r.languages.length) return r.languages.join(" and ");
  const words = r.text.replace(/[.;:]+$/, "").split(/\s+/);
  return words.length > 4 ? `${words.slice(0, 4).join(" ")}…` : words.join(" ");
}

export interface ReqView {
  id: string;
  verdict: Verdict;
  kind: "must" | "nice";
  req: Requirement;
}

/** Requirements of a job with their verdicts, in the posting's order. */
export function reqViews(job: RankedJob): ReqView[] {
  const reqs = new Map(job.requirements.requirements.map((r) => [r.id, r]));
  const out: ReqView[] = [];
  for (const j of job.judgments) {
    const r = reqs.get(j.req_id);
    if (r) out.push({ id: j.req_id, verdict: j.verdict, kind: r.kind, req: r });
  }
  return out;
}

export function countMet(views: ReqView[], kind: "must" | "nice") {
  const group = views.filter((v) => v.kind === kind);
  return { met: group.filter((v) => v.verdict === "met").length, total: group.length };
}

export type FitBand = "high" | "mid" | "low";

export function fitBand(fit: number): FitBand {
  return fit >= 0.75 ? "high" : fit >= 0.5 ? "mid" : "low";
}

export function pct(x: number | null | undefined): string {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`;
}

/** "1 email, 1 phone and 1 link" */
export function listJoin(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
