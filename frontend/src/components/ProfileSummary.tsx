import { useState } from "react";
import type { RunView } from "../types";
import { listJoin } from "./marks";

const LEVEL = ["", "basic", "intermediate", "good", "fluent", "native"];
const SHOWN = 20;

export function ProfileSummary({ view }: { view: RunView }) {
  const [all, setAll] = useState(false);
  const p = view.profile;
  if (!p) return null;
  const removed = Object.entries(view.redaction)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${n} ${k}${n > 1 ? "s" : ""}`);
  const rounds = view.query_log.length;

  // How many of the ranked jobs ask for each skill. Those are marked and listed first.
  const asked = new Map<string, number>();
  for (const r of view.ranked) {
    for (const s of new Set(r.requirements.requirements.flatMap((q) => q.skills))) asked.set(s, (asked.get(s) ?? 0) + 1);
  }
  const skills = [...p.skills].sort((a, b) => (asked.get(b) ?? 0) - (asked.get(a) ?? 0));
  const shown = all ? skills : skills.slice(0, SHOWN);
  const hidden = skills.length - shown.length;
  const anyAsked = skills.some((s) => asked.get(s));
  const level =
    p.seniority === "student" ? "Student" : `${p.seniority[0].toUpperCase()}${p.seniority.slice(1)} level`;
  const experience =
    p.years_experience >= 0.5 ? `about ${p.years_experience} years of professional experience` : "no professional experience yet";

  return (
    <section className="profile" aria-label="What was read from your CV">
      <div className="profile-main">
        <h2 className="section-title">From your CV</h2>
        <p className="profile-headline">{p.headline || view.cv_label}</p>
        <p className="profile-line">
          {level}, {experience}
          {p.internship_months ? `${p.years_experience >= 0.5 ? " plus" : ","} ${p.internship_months} months of internships` : ""}.{" "}
          {p.languages.length > 0 && `${listJoin(p.languages.map((l) => `${l.name} (${LEVEL[l.level]})`))}.`}
        </p>
        <p className="skills">
          <span className="skills-label">Skills found: </span>
          {shown.map((s, i) => {
            const n = asked.get(s) ?? 0;
            return (
              <span key={s}>
                {n > 0 ? (
                  <span className="skill-asked" title={`${n} of your top ${view.ranked.length} jobs ask for this`}>
                    {s}
                    <sup>
                      <span className="visually-hidden">, asked for by </span>
                      {n}
                      <span className="visually-hidden"> jobs</span>
                    </sup>
                  </span>
                ) : (
                  s
                )}
                {i < shown.length - 1 ? ", " : hidden > 0 ? "" : "."}
              </span>
            );
          })}
          {hidden > 0 && (
            <>
              {" "}
              <button type="button" className="text-button" onClick={() => setAll(true)}>
                and {hidden} more
              </button>
            </>
          )}
        </p>
        {anyAsked && <p className="profile-note">The small number says how many of your top {view.ranked.length} jobs ask for that skill.</p>}
      </div>
      <dl className="profile-facts">
        <div>
          <dt>Taken out before reading</dt>
          <dd>{removed.length ? listJoin(removed) : "Nothing personal found"}</dd>
        </div>
        <div>
          <dt>Searched for</dt>
          <dd>
            {view.queries.length
              ? view.queries.join(", ")
              : view.options.source === "linkedin"
                ? "Nothing: you picked these jobs on LinkedIn"
                : "Nothing: you pasted the postings"}
            {rounds > 1 && (
              <span className="muted">
                {" "}
                ({rounds - 1} widening round{rounds > 2 ? "s" : ""})
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt>Postings</dt>
          <dd>
            {view.relevant_count} relevant out of {view.pool_size}
            {view.ranked.length > 0 && `; the best ${view.ranked.length} checked in detail`}
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
