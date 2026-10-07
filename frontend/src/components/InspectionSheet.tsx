import { useState } from "react";
import type { EvidenceUnit, RankedJob } from "../types";
import { Balloon, HarveyBall, pct } from "./marks";

export function InspectionSheet({ job, units }: { job: RankedJob; units: Record<string, EvidenceUnit> }) {
  const [hover, setHover] = useState<string | null>(null);
  const reqs = Object.fromEntries(job.requirements.requirements.map((r) => [r.id, r]));
  const counts = (kind: "must" | "nice") => {
    const js = job.judgments.filter((j) => reqs[j.req_id]?.kind === kind);
    return { met: js.filter((j) => j.verdict === "met").length, total: js.length };
  };
  const must = counts("must");
  const nice = counts("nice");
  const jr = job.requirements;
  return (
    <article className="sheet" aria-label={`Inspection of ${job.job.title}`}>
      <header className="sheet-head">
        <div>
          <h2 className="sheet-title">{job.job.title}</h2>
          <p className="muted">
            {job.job.company}, {job.job.location || "location not stated"}
            {job.job.workplace !== "unknown" ? ` (${job.job.workplace})` : ""}
          </p>
          <p className="attribution">
            {job.job.url ? (
              <a href={job.job.url} target="_blank" rel="noreferrer" className="link">
                Open the posting
              </a>
            ) : null}
            <span className="muted">{job.job.attribution || job.job.source_label}</span>
          </p>
        </div>
        <div className="sheet-score">
          <span className="fit fit-large">{Math.round(job.fit * 100)}</span>
          <span className="muted">fit</span>
        </div>
      </header>

      <dl className="sheet-facts">
        <div>
          <dt>Must-haves met</dt>
          <dd>
            {must.met} of {must.total} <span className="muted">({pct(job.must_coverage)} with partial credit)</span>
          </dd>
        </div>
        <div>
          <dt>Nice-to-haves met</dt>
          <dd>
            {nice.met} of {nice.total}
          </dd>
        </div>
        <div>
          <dt>Level asked</dt>
          <dd>
            {jr.seniority === "unspecified" ? "not stated" : jr.seniority}
            {jr.min_years ? `, ${jr.min_years}+ years` : ""}
          </dd>
        </div>
        {jr.languages.length > 0 && (
          <div>
            <dt>Languages</dt>
            <dd>{jr.languages.join(", ")}</dd>
          </div>
        )}
      </dl>

      {job.flags.length > 0 && (
        <ul className="sheet-flags">
          {job.flags.map((f) => (
            <li key={f.message} className={`flag flag-${f.kind}`}>
              {f.message}
            </li>
          ))}
        </ul>
      )}
      {job.downgraded > 0 && (
        <p className="guard">
          {job.downgraded} verdict{job.downgraded > 1 ? "s" : ""} from the model cited no real line of your CV and{" "}
          {job.downgraded > 1 ? "were" : "was"} set to missing.
        </p>
      )}

      <table className="reqs">
        <caption className="visually-hidden">Requirements and the evidence from your CV</caption>
        <thead>
          <tr>
            <th scope="col">
              <span className="visually-hidden">Verdict</span>
            </th>
            <th scope="col">Requirement</th>
            <th scope="col">Evidence in your CV</th>
          </tr>
        </thead>
        <tbody>
          {job.judgments.map((j) => {
            const r = reqs[j.req_id];
            if (!r) return null;
            const first = j.evidence_ids.find((id) => units[id]);
            const shown = (hover && j.evidence_ids.includes(hover) ? hover : first) ?? null;
            return (
              <tr key={j.req_id} className={`req is-${j.verdict}`}>
                <td className="req-mark">
                  <HarveyBall verdict={j.verdict} />
                </td>
                <td className="req-text">
                  <span>{r.text}</span>
                  <span className={`kind kind-${r.kind}`}>{r.kind === "must" ? "must-have" : "nice-to-have"}</span>
                </td>
                <td className="req-evidence">
                  {j.evidence_ids.length > 0 ? (
                    <>
                      <span className="balloons">
                        {j.evidence_ids.map((id) => (
                          <Balloon
                            key={id}
                            id={id}
                            title={units[id]?.text ?? id}
                            active={hover === id}
                            onFocus={() => setHover(id)}
                            onBlur={() => setHover(null)}
                          />
                        ))}
                      </span>
                      {shown && units[shown] && <q className="quote">{units[shown].text}</q>}
                    </>
                  ) : (
                    <span className="muted">No line in your CV shows this.</span>
                  )}
                  {j.gap_type === "wording" && j.cv_term && j.jd_term && (
                    <span className="note note-wording">
                      You write “{j.cv_term}”; the posting says “{j.jd_term}”.
                    </span>
                  )}
                  {j.missing_skills.length > 0 && j.verdict !== "met" && (
                    <span className="note note-missing">Missing: {j.missing_skills.join(", ")}</span>
                  )}
                  {j.note && j.gap_type !== "wording" && !j.note.startsWith("closest CV line") && (
                    <span className="note">{j.note}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <details className="posting">
        <summary>Read the posting</summary>
        <pre className="posting-text">{job.description}</pre>
        <p className="muted small">
          Why it was shortlisted: {job.triage_reason || "ranked by retrieval"}. BM25 {job.bm25?.toFixed(2) ?? "–"}, semantic{" "}
          {job.semantic?.toFixed(2) ?? "–"}. Requirements read by {jr.source === "llm" ? "the LLM" : "rules"}.
        </p>
      </details>
    </article>
  );
}
