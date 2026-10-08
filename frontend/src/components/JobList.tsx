import type { ReactNode } from "react";
import type { RankedJob } from "../types";
import { Hl, PenBox, PenMark, fitBand, reqLabel, reqViews } from "./marks";

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
        const tailored = tailoredIds.includes(r.job_id);
        const full = picked.length >= 3 && !isPicked;
        const open = activeId === r.job_id;
        const views = reqViews(r);
        const must = views.filter((v) => v.kind === "must");
        const nice = views.filter((v) => v.kind === "nice");
        const workplace =
          r.job.workplace !== "unknown" && r.job.workplace !== "onsite" && !r.job.location.toLowerCase().includes(r.job.workplace) ? `, ${r.job.workplace}` : "";
        return (
          <li key={r.job_id} className={`job${open ? " is-open" : ""}${isPicked || tailored ? " is-picked" : ""}`}>
            <button type="button" className="job-main" onClick={() => onOpen(r.job_id)} aria-expanded={open}>
              <span className="job-rank">{r.rank}</span>
              <span className="job-body">
                <span className="job-title">{r.job.title}</span>
                <span className="job-meta">
                  {r.job.company}, {r.job.location || "location not stated"}
                  {workplace}
                </span>
                <span className="job-reqs">
                  {must.map((v) => (
                    <Hl key={v.id} verdict={v.verdict} kind="must" title={v.req.text}>
                      {v.verdict !== "met" && <PenMark verdict={v.verdict} size={13} label={false} />}
                      {reqLabel(v.req)}
                    </Hl>
                  ))}
                  {nice.length > 0 && (
                    <span className="job-nice">
                      <span className="visually-hidden">Nice to have: </span>
                      {nice.map((v) => (
                        <Hl key={v.id} verdict={v.verdict} kind="nice" title={v.req.text}>
                          {v.verdict !== "met" && <PenMark verdict={v.verdict} size={12} label={false} />}
                          {reqLabel(v.req)}
                        </Hl>
                      ))}
                    </span>
                  )}
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
              <span className={`job-fit band-${fitBand(r.fit)}`}>
                <span className="fit-num">{Math.round(r.fit * 100)}</span>
                <span className="fit-label">fit</span>
              </span>
            </button>
            {(selectable || tailored) && (
              <label className={`pick${isPicked || tailored ? " is-picked" : ""}${!selectable || full ? " is-disabled" : ""}`}>
                <input
                  type="checkbox"
                  className="visually-hidden"
                  checked={isPicked || tailored}
                  disabled={!selectable || full}
                  onChange={() => onTogglePick(r.job_id)}
                />
                <PenBox checked={isPicked || tailored} draw size={18} />
                {tailored ? "Tailored for this job" : "Tailor my CV for this job"}
              </label>
            )}
            {renderDetail && open && <div className="job-detail">{renderDetail(r.job_id)}</div>}
          </li>
        );
      })}
    </ol>
  );
}
