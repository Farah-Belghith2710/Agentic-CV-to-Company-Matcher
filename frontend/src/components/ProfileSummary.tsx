import type { RunView } from "../types";

const LEVEL = ["", "basic", "intermediate", "good", "fluent", "native"];

export function ProfileSummary({ view }: { view: RunView }) {
  const p = view.profile;
  if (!p) return null;
  const removed = Object.entries(view.redaction).filter(([, n]) => n > 0);
  const extra = p.skills.length - 16;
  const rounds = view.query_log.length;
  return (
    <section className="profile" aria-label="What was read from your CV">
      <div className="profile-main">
        <h2 className="panel-title">Read from your CV</h2>
        <p className="profile-headline">{p.headline || view.cv_label}</p>
        <p className="muted">
          {p.seniority === "student" ? "Student" : `${p.seniority[0].toUpperCase()}${p.seniority.slice(1)}-level`},{" "}
          {p.years_experience >= 0.5 ? `about ${p.years_experience} years of professional experience` : "no professional experience yet"}
          {p.internship_months ? `${p.years_experience >= 0.5 ? " plus" : ","} ${p.internship_months} months of internships` : ""}.{" "}
          {p.languages.map((l) => `${l.name} (${LEVEL[l.level]})`).join(", ")}
        </p>
        <ul className="chips" aria-label="Skills found">
          {p.skills.slice(0, 16).map((s) => (
            <li key={s} className="chip">
              {s}
            </li>
          ))}
          {extra > 0 && <li className="chip chip-more">+{extra} more</li>}
        </ul>
      </div>
      <dl className="profile-facts">
        <div>
          <dt>Redacted first</dt>
          <dd>{removed.length ? removed.map(([k, n]) => `${n} ${k}${n > 1 ? "s" : ""}`).join(", ") : "nothing found"}</dd>
        </div>
        <div>
          <dt>Searched for</dt>
          <dd>
            {view.queries.length ? view.queries.join(", ") : "your pasted postings"}
            {rounds > 1 && <span className="muted"> ({rounds - 1} widening round{rounds > 2 ? "s" : ""})</span>}
          </dd>
        </div>
        <div>
          <dt>Postings</dt>
          <dd>
            {view.relevant_count} relevant of {view.pool_size}, top {view.ranked.length} analysed
          </dd>
        </div>
        <div>
          <dt>Engine</dt>
          <dd>
            {view.mode.llm ? `LLM: ${view.mode.model}` : "Offline rules"}
            {view.similarity ? `; similarity: ${view.similarity.split(" (")[0]}` : ""}
            {view.llm_stats ? `; ${view.llm_stats.calls} LLM calls, ${view.llm_stats.cache_hits} cached` : ""}
          </dd>
        </div>
      </dl>
    </section>
  );
}
