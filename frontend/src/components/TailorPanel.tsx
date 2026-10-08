import { wordDiff } from "../diff";
import type { RankedJob, TailoredBullet } from "../types";
import { PenMark } from "./marks";

/** The rewriter's notes, said the way a person would. */
function plainNote(note: string): string {
  if (note.startsWith("no safe wording change")) return "It already uses the posting's words, so it stays as you wrote it";
  if (note.startsWith("aligned terminology")) return "Now uses the posting's words for the same skills";
  return note[0].toUpperCase() + note.slice(1);
}

function Redline({ before, after }: { before: string; after: string }) {
  if (before === after) return <p className="redline">{after}</p>;
  return (
    <p className="redline">
      {wordDiff(before, after).map((part, i) =>
        part.kind === "same" ? <span key={i}>{part.text}</span> : part.kind === "add" ? <ins key={i}>{part.text}</ins> : <del key={i}>{part.text}</del>,
      )}
    </p>
  );
}

export function TailorPanel({ bullets, ranked, llm }: { bullets: TailoredBullet[]; ranked: RankedJob[]; llm: boolean }) {
  if (!bullets.length) return null;
  const byJob = new Map<string, TailoredBullet[]>();
  bullets.forEach((b) => byJob.set(b.job_id, [...(byJob.get(b.job_id) ?? []), b]));
  const titles = Object.fromEntries(ranked.map((r) => [r.job_id, { title: r.job.title, company: r.job.company }]));
  const rejected = bullets.reduce((n, b) => n + b.attempts.filter((a) => !a.ok).length, 0);
  return (
    <section className="tailor" aria-label="Tailored bullets">
      <h2 className="section-title">Your bullets, tailored</h2>
      <p className="section-lede">
        Each rewrite is checked against your original bullet. A draft that adds a number, a tool or (with an LLM) any claim you did not make is
        sent back{rejected > 0 ? `; ${rejected} draft${rejected > 1 ? "s were" : " was"} sent back this time` : ""}.
        {!llm && " Without an LLM the rewrite only borrows the posting's words, and its first draft overdoes it on purpose so you can see the check at work."}
      </p>
      <p className="diff-key">
        <ins>added</ins> <del>removed</del>
      </p>
      {[...byJob.entries()].map(([jobId, list]) => (
        <section key={jobId} className="tailor-job" aria-label={titles[jobId]?.title ?? jobId}>
          <h3 className="tailor-title">
            {titles[jobId]?.title ?? jobId}
            {titles[jobId] && <span>, {titles[jobId].company}</span>}
          </h3>
          <ol className="bullets">
            {list.map((b) => {
              const failed = b.attempts.filter((a) => !a.ok);
              const last = b.attempts[b.attempts.length - 1];
              return (
                <li key={b.evidence_id} className={`bullet is-${b.status}`}>
                  <p className="bullet-meta">
                    Line {b.evidence_id.replace(/^E/, "")} of your CV, {b.context}
                  </p>
                  <Redline before={b.original} after={b.final || b.original} />
                  <p className={`bullet-status status-${b.status}`}>
                    {b.status === "verified" && <PenMark verdict="met" size={16} label={false} />}
                    {b.status === "verified"
                      ? `Passed the check${b.attempts.length > 1 ? ` on attempt ${b.attempts.length}` : ""}`
                      : b.status === "kept_original"
                        ? "No safe rewrite found, so your original stays"
                        : "Being checked"}
                    {last?.note ? `. ${plainNote(last.note)}` : ""}.
                  </p>
                  {b.targets.length > 0 && <p className="bullet-note">For: {b.targets.map((t) => t.replace(/[.;]+$/, "")).join("; ")}.</p>}
                  {failed.length > 0 && (
                    <details className="drafts">
                      <summary>
                        {failed.length} draft{failed.length > 1 ? "s" : ""} sent back
                      </summary>
                      {failed.map((d, i) => (
                        <div key={i} className="draft">
                          <Redline before={b.original} after={d.text} />
                          <p className="draft-why">Why: {d.problems.join("; ")}.</p>
                        </div>
                      ))}
                    </details>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </section>
  );
}
