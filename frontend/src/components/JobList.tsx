import type { ReactNode } from "react";
import type { RankedJob } from "../types";
import { CoverageBar } from "./marks";

export function JobList({
  ranked,
  activeId,
  onOpen,
  selectable,
  picked,
  onTogglePick,
  tailoredIds,
  renderDetail,
}: {
  ranked: RankedJob[];
  activeId: string | null;
  onOpen: (id: string) => void;
  selectable: boolean;
  picked: string[];
  onTogglePick: (id: string) => void;
  tailoredIds: string[];
  /** On narrow screens the details open inline, right under the job. */
  renderDetail?: (id: string) => ReactNode;
}) {
  return (
    <ol className="jobs" aria-label="Ranked jobs">
      {ranked.map((r) => {
        const isPicked = picked.includes(r.job_id);
        const full = picked.length >= 3 && !isPicked;
        return (
          <li key={r.job_id} className={`job${activeId === r.job_id ? " is-open" : ""}`}>
            <button type="button" className="job-main" onClick={() => onOpen(r.job_id)} aria-expanded={activeId === r.job_id}>
              <span className="job-rank">{r.rank}</span>
              <span className="job-text">
                <span className="job-title">{r.job.title}</span>
                <span className="job-meta">
                  {r.job.company}
                  <span className="sep" aria-hidden="true" />
                  {r.job.location || "Location not stated"}
                  {r.job.workplace !== "unknown" && r.job.workplace !== "onsite" ? `, ${r.job.workplace}` : ""}
                </span>
                {r.flags.length > 0 && (
                  <span className="job-flags">
                    {r.flags.map((f) => (
                      <span key={f.message} className={`flag flag-${f.kind}`}>
                        {f.message}
                      </span>
                    ))}
                  </span>
                )}
              </span>
              <span className="job-score">
                <span className="fit" aria-label={`Fit ${Math.round(r.fit * 100)} out of 100`}>
                  {Math.round(r.fit * 100)}
                </span>
                <CoverageBar label="Must" value={r.must_coverage} />
                <CoverageBar label="Nice" value={r.nice_coverage} />
              </span>
            </button>
            {(selectable || tailoredIds.includes(r.job_id)) && (
              <label className={`pick${isPicked ? " is-picked" : ""}`}>
                <input
                  type="checkbox"
                  checked={isPicked || tailoredIds.includes(r.job_id)}
                  disabled={!selectable || full}
                  onChange={() => onTogglePick(r.job_id)}
                />
                {tailoredIds.includes(r.job_id) ? "Tailored" : "Tailor for this job"}
              </label>
            )}
            {renderDetail && activeId === r.job_id && <div className="job-detail">{renderDetail(r.job_id)}</div>}
          </li>
        );
      })}
    </ol>
  );
}
