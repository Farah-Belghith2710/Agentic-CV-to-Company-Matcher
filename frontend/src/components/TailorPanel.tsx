import { wordDiff } from "../diff";
import type { RankedJob, TailoredBullet } from "../types";

function Redline({ before, after }: { before: string; after: string }) {
  if (before === after) return <p className="redline">{after}</p>;
  return (
    <p className="redline">
      {wordDiff(before, after).map((part, i) =>
        part.kind === "same" ? (
          <span key={i}>{part.text}</span>
        ) : part.kind === "add" ? (
          <ins key={i}>{part.text}</ins>
        ) : (
          <del key={i}>{part.text}</del>
        ),
      )}
    </p>
  );
}

export function TailorPanel({ bullets, ranked, llm }: { bullets: TailoredBullet[]; ranked: RankedJob[]; llm: boolean }) {
  if (!bullets.length) return null;
  const byJob = new Map<string, TailoredBullet[]>();
  bullets.forEach((b) => byJob.set(b.job_id, [...(byJob.get(b.job_id) ?? []), b]));
  const titles = Object.fromEntries(ranked.map((r) => [r.job_id, `${r.job.title}, ${r.job.company}`]));
  const rejected = bullets.reduce((n, b) => n + b.attempts.filter((a) => !a.ok).length, 0);
  return (
    <section className="tailor" aria-label="Tailored bullets">
      <h2 className="panel-title">Tailored bullets</h2>
      <p className="muted">
        Every rewrite is checked against your original bullet: a draft that adds a number, a tool or (with an LLM) any claim you did
        not make is sent back. {rejected > 0 ? `${rejected} draft${rejected > 1 ? "s were" : " was"} rejected this run.` : ""}
        {!llm && " Offline mode only aligns wording with the posting; its first draft deliberately keyword-stuffs to show the check working."}
      </p>
      {[...byJob.entries()].map(([jobId, list]) => (
        <div key={jobId} className="tailor-job">
          <h3 className="tailor-title">{titles[jobId] ?? jobId}</h3>
          {list.map((b) => {
            const failed = b.attempts.filter((a) => !a.ok);
            const last = b.attempts[b.attempts.length - 1];
            return (
              <article key={b.evidence_id} className={`bullet is-${b.status}`}>
                <header className="bullet-head">
                  <span className="bullet-id">{b.evidence_id}</span>
                  <span className="muted small">{b.context}</span>
                  <span className={`stamp stamp-${b.status}`}>
                    {b.status === "verified" ? `Verified, attempt ${b.attempts.length}` : b.status === "kept_original" ? "Kept your original" : "Checking"}
                  </span>
                </header>
                <Redline before={b.original} after={b.final || b.original} />
                {last?.note && <p className="muted small">{last.note}</p>}
                {b.targets.length > 0 && <p className="muted small">Supports: {b.targets.map((t) => t.replace(/[.;]+$/, "")).join("; ")}</p>}
                {failed.length > 0 && (
                  <details className="drafts">
                    <summary>
                      {failed.length} rejected draft{failed.length > 1 ? "s" : ""}
                    </summary>
                    {failed.map((d, i) => (
                      <div key={i} className="draft">
                        <Redline before={b.original} after={d.text} />
                        <p className="draft-why">Rejected: {d.problems.join("; ")}</p>
                      </div>
                    ))}
                  </details>
                )}
              </article>
            );
          })}
        </div>
      ))}
    </section>
  );
}
