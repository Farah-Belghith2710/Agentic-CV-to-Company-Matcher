import { useState } from "react";
import type { EvidenceUnit, Judgment, RankedJob } from "../types";
import { Hl, PenMark, ScoreCircle, countMet, fitBand, pct, reqViews } from "./marks";

const lineNo = (id: string) => id.replace(/^E/, "");
const sentence = (s: string) => s[0].toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : ".");

/** The judge writes terse notes ("asks 2+ yrs, CV shows ~0.4"); say them the way a person would. */
function humanNote(note: string): string {
  const parts = note
    .split("; ")
    .map((n) => n.trim())
    .filter((n) => n && !n.startsWith("closest CV line"));
  return parts
    .map((n) => {
      let m: RegExpMatchArray | null;
      if (n === "student") return "You are a student, which is what they ask for.";
      if (n === "asks for a student") return "They want someone who is still a student.";
      if (n === "different field of study") return "Your degree is in a different field.";
      if (n === "no education section found") return "Your CV has no education section.";
      if (n === "not judged by the model") return "The model did not judge this one.";
      if ((m = n.match(/^asks ([\d.]+)\+ yrs, CV shows ~([\d.]+)$/))) {
        const have = Number(m[2]);
        return `They ask for ${m[1]}+ years; your CV shows ${have < 1 ? "less than a year" : `about ${have}`}.`;
      }
      if ((m = n.match(/^has (.+), not (.+)$/))) return `You have ${m[1]}, but not ${m[2]} itself.`;
      if ((m = n.match(/^only indirect evidence for (.+)$/))) return `Only indirect evidence of ${m[1]}.`;
      if ((m = n.match(/^(.+) implied by (.+)$/))) return `${m[1]} follows from ${m[2]} in your CV.`;
      if ((m = n.match(/^related: (.+)$/))) return `Your CV shows something close: ${m[1]}.`;
      return sentence(n);
    })
    .join(" ");
}

/** One requirement with the line of your CV behind it (other lines can be swapped in). */
function Requirement({ j, text, kind, units }: { j: Judgment; text: string; kind: "must" | "nice"; units: Record<string, EvidenceUnit> }) {
  const ids = j.evidence_ids.filter((id) => units[id]);
  const [shown, setShown] = useState<string | null>(ids[0] ?? null);
  const current = shown && ids.includes(shown) ? shown : (ids[0] ?? null);
  return (
    <li className={`req is-${j.verdict}`}>
      <PenMark verdict={j.verdict} size={20} />
      <div className="req-body">
        <p className="req-text">
          <Hl verdict={j.verdict} kind={kind}>
            {text}
          </Hl>
        </p>
        {current ? (
          <p className="evidence">
            <span className="evidence-where">Your CV, line {lineNo(current)}:</span> <q>{units[current].text}</q>
            {ids.length > 1 && (
              <span className="evidence-more">
                {" "}
                Also{" "}
                {ids
                  .filter((id) => id !== current)
                  .map((id, i, rest) => (
                    <span key={id}>
                      <button type="button" className="line-link" onClick={() => setShown(id)} onMouseEnter={() => setShown(id)} title={units[id].text}>
                        line {lineNo(id)}
                      </button>
                      {i < rest.length - 2 ? ", " : i === rest.length - 2 ? " and " : ""}
                    </span>
                  ))}
                .
              </span>
            )}
          </p>
        ) : (
          <p className="evidence is-none">Nothing in your CV shows this.</p>
        )}
        {j.gap_type === "wording" && j.cv_term && j.jd_term && (
          <p className="note note-wording">
            You write “{j.cv_term}”; the posting says “{j.jd_term}”.
          </p>
        )}
        {j.missing_skills.length > 0 && j.verdict === "partial" && <p className="note note-missing">Missing: {j.missing_skills.join(", ")}.</p>}
        {j.note && j.gap_type !== "wording" && humanNote(j.note) && <p className="note">{humanNote(j.note)}</p>}
      </div>
    </li>
  );
}

export function InspectionSheet({ job, units }: { job: RankedJob; units: Record<string, EvidenceUnit> }) {
  const views = reqViews(job);
  const texts = Object.fromEntries(views.map((v) => [v.id, v.req.text]));
  const must = countMet(views, "must");
  const nice = countMet(views, "nice");
  const jr = job.requirements;
  const band = fitBand(job.fit);
  const level = jr.seniority === "unspecified" ? "not stated" : jr.seniority;

  const groups = [
    { kind: "must" as const, title: "Must-haves", count: must, rows: job.judgments.filter((j) => views.find((v) => v.id === j.req_id)?.kind === "must") },
    { kind: "nice" as const, title: "Nice to have", count: nice, rows: job.judgments.filter((j) => views.find((v) => v.id === j.req_id)?.kind === "nice") },
  ].filter((g) => g.rows.length > 0);

  return (
    <article className="detail" aria-label={`Details for ${job.job.title}`}>
      <header className="detail-head">
        <div>
          <h2 className="detail-title">{job.job.title}</h2>
          <p className="detail-meta">
            {job.job.company}, {job.job.location || "location not stated"}
            {job.job.workplace !== "unknown" && !job.job.location.toLowerCase().includes(job.job.workplace) ? ` (${job.job.workplace})` : ""}
          </p>
          <p className="detail-source">
            {job.job.url && (
              <a href={job.job.url} target="_blank" rel="noreferrer">
                Open the posting
              </a>
            )}
            <span>{job.job.attribution || job.job.source_label}</span>
          </p>
        </div>
        <div className={`detail-score band-${band}`} aria-label={`Fit ${Math.round(job.fit * 100)} out of 100`}>
          <ScoreCircle key={job.job_id} />
          <span className="fit-num">{Math.round(job.fit * 100)}</span>
        </div>
      </header>

      <p className="detail-summary">
        Your CV covers {must.met} of {must.total} must-haves
        {nice.total ? ` and ${nice.met} of ${nice.total} nice-to-haves` : ""}
        {job.must_coverage !== null && must.met < must.total ? ` (${pct(job.must_coverage)} of the must-haves, counting partial matches)` : ""}. Level asked:{" "}
        {level}
        {jr.min_years ? `, ${jr.min_years}+ years` : ""}.{jr.languages.length ? ` Languages: ${jr.languages.join(", ")}.` : ""}
      </p>

      {job.flags.length > 0 && (
        <ul className="detail-flags">
          {job.flags.map((f) => (
            <li key={f.message} className={`flag flag-${f.kind}`}>
              {f.message}
            </li>
          ))}
        </ul>
      )}
      {job.downgraded > 0 && (
        <p className="guard">
          {job.downgraded} verdict{job.downgraded > 1 ? "s" : ""} from the model cited no real line of your CV, so {job.downgraded > 1 ? "they were" : "it was"} marked as
          missing.
        </p>
      )}

      {groups.map((g) => (
        <section key={g.kind} className="req-group" aria-label={g.title}>
          <h3>
            {g.title}
            <span>
              {g.count.met} of {g.count.total} in your CV
            </span>
          </h3>
          <ol className="reqs">
            {g.rows.map((j) => (
              <Requirement key={`${job.job_id}-${j.req_id}`} j={j} text={texts[j.req_id]} kind={g.kind} units={units} />
            ))}
          </ol>
        </section>
      ))}

      <details className="posting">
        <summary>Read the whole posting</summary>
        <pre className="posting-text">{job.description}</pre>
        <p className="posting-why">
          Shortlisted because: {job.triage_reason || "ranked by retrieval"}. BM25 {job.bm25?.toFixed(2) ?? "–"}, semantic {job.semantic?.toFixed(2) ?? "–"}.
          Requirements read by {jr.source === "llm" ? "the LLM" : "rules"}.
        </p>
      </details>
    </article>
  );
}
