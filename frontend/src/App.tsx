import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { AgentLog } from "./components/AgentLog";
import { InspectionSheet } from "./components/InspectionSheet";
import { JobList } from "./components/JobList";
import { LearnNext } from "./components/LearnNext";
import { HarveyBall } from "./components/marks";
import { PipelineRail, type StageState } from "./components/PipelineRail";
import { ProfileSummary } from "./components/ProfileSummary";
import { SetupForm, type StartInput } from "./components/SetupForm";
import { TailorPanel } from "./components/TailorPanel";
import type { Health, RunEvent, RunStatus, RunView, Sample } from "./types";
import { useNarrow } from "./useNarrow";

const REFRESH_ON_DONE = new Set(["parse_cv", "score_rank", "verify", "report", "pick_jobs"]);

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [backendDown, setBackendDown] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [view, setView] = useState<RunView | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [stages, setStages] = useState<Record<string, StageState>>({});
  const [status, setStatus] = useState<RunStatus | "idle">("idle");
  const [error, setError] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const narrow = useNarrow();
  const closeStream = useRef<() => void>(() => {});
  const pollTimer = useRef<number | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.samples()])
      .then(([h, s]) => {
        setHealth(h);
        setSamples(s);
      })
      .catch(() => setBackendDown(true));
    return () => closeStream.current();
  }, []);

  const refresh = useCallback((id: string) => {
    api
      .run(id)
      .then((v) => {
        setView(v);
        setStatus(v.status);
        if (v.error) setError(v.error);
        setActiveJob((cur) => cur ?? v.ranked[0]?.job_id ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const onEvent = useCallback(
    (id: string, e: RunEvent) => {
      setEvents((prev) => (prev.length && prev[prev.length - 1].seq >= e.seq ? prev : [...prev, e]));
      if (e.type === "stage" && e.node) {
        setStages((prev) => {
          const cur = prev[e.node!] ?? { starts: 0, done: 0, active: false };
          const next =
            e.status === "start" ? { starts: cur.starts + 1, done: cur.done, active: true } : { starts: cur.starts, done: cur.done + 1, active: false };
          return { ...prev, [e.node!]: next };
        });
        if (e.status === "done" && REFRESH_ON_DONE.has(e.node)) refresh(id);
      }
      if (e.type === "status" && e.status) {
        setStatus(e.status as RunStatus);
        if (e.status !== "running") refresh(id);
        if (e.status === "awaiting_selection") setStages((prev) => ({ ...prev, pick_jobs: { ...(prev.pick_jobs ?? { starts: 1, done: 0 }), active: true } }));
      }
      if (e.type === "end") refresh(id);
    },
    [refresh],
  );

  const listen = useCallback(
    (id: string) => {
      closeStream.current();
      closeStream.current = api.events(
        id,
        (e) => onEvent(id, e),
        () => {
          // Stream dropped (server restart, sleep): fall back to polling until the run ends.
          if (pollTimer.current) window.clearInterval(pollTimer.current);
          pollTimer.current = window.setInterval(() => refresh(id), 1500);
        },
      );
    },
    [onEvent, refresh],
  );

  useEffect(() => {
    if ((status === "done" || status === "error") && pollTimer.current) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, [status]);

  const start = async (input: StartInput) => {
    closeStream.current();
    setError(null);
    setView(null);
    setEvents([]);
    setStages({});
    setActiveJob(null);
    setPicked([]);
    setStatus("running");
    try {
      const { run_id } = await api.start(input);
      setRunId(run_id);
      listen(run_id);
    } catch (e) {
      setStatus("error");
      setError((e as Error).message);
    }
  };

  const tailor = async () => {
    if (!runId || !picked.length) return;
    try {
      setStatus("running");
      setStages((prev) => ({ ...prev, pick_jobs: { ...(prev.pick_jobs ?? { starts: 1, done: 0 }), active: false } }));
      await api.select(runId, picked);
    } catch (e) {
      setError((e as Error).message);
      refresh(runId);
    }
  };

  const ranked = view?.ranked ?? [];
  const units = Object.fromEntries((view?.units ?? []).map((u) => [u.id, u]));
  const openJob = ranked.find((r) => r.job_id === activeJob) ?? (narrow ? undefined : ranked[0]);
  const awaiting = status === "awaiting_selection";
  const busy = status === "running" || status === "queued";
  const startTs = events[0]?.ts ?? null;

  return (
    <div className="app">
      <header className="titleblock">
        <div className="brand">
          <h1>CV Matcher</h1>
          <p>Ranks real job postings against your CV, shows the line of your CV behind every verdict, and tailors bullets without inventing anything.</p>
        </div>
        <dl className="titleblock-cells">
          <div>
            <dt>Engine</dt>
            <dd>{health ? (health.llm.configured ? health.llm.model : "Offline rules") : "..."}</dd>
          </div>
          <div>
            <dt>Snapshot</dt>
            <dd>{health ? `${health.snapshot.jobs} postings` : "..."}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>{runId ?? "none yet"}</dd>
          </div>
        </dl>
      </header>

      {backendDown && (
        <p className="banner" role="alert">
          The API is not answering on port 8000. Start it with <code>uvicorn app.main:app --reload --port 8000</code> in the backend
          folder, then reload this page.
        </p>
      )}

      <main className="workspace">
        <aside className="side">
          <SetupForm health={health} samples={samples} busy={busy} onStart={start} />
          <AgentLog events={events} startTs={startTs} />
        </aside>

        <section className="board" aria-live="polite">
          <PipelineRail stages={stages} status={status} />

          {error && (
            <div className="error" role="alert">
              <strong>The run stopped.</strong> {error}
            </div>
          )}

          {!view?.profile && status === "idle" && (
            <div className="empty">
              <h2>See how your CV holds up against each requirement</h2>
              <p>
                Pick a CV and a job source, then run. The agent searches, keeps the relevant postings, splits each one into
                must-haves and nice-to-haves, and checks every requirement against the lines of your CV.
              </p>
              <ul className="legend" aria-label="How to read the results">
                <li>
                  <HarveyBall verdict="met" /> A line of your CV shows it
                </li>
                <li>
                  <HarveyBall verdict="partial" /> Related or weaker evidence
                </li>
                <li>
                  <HarveyBall verdict="missing" /> Nothing in your CV shows it
                </li>
                <li>
                  <span className="balloon balloon-static">3</span> The CV line that proves it (hover to read)
                </li>
              </ul>
            </div>
          )}

          {view?.profile && <ProfileSummary view={view} />}

          {ranked.length > 0 && (
            <div className="results">
              <div className="results-list">
                <h2 className="panel-title">Ranked by fit</h2>
                <JobList
                  ranked={ranked}
                  activeId={openJob?.job_id ?? null}
                  onOpen={(id) => setActiveJob((cur) => (narrow && cur === id ? "" : id))}
                  selectable={awaiting}
                  picked={picked}
                  onTogglePick={(id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < 3 ? [...p, id] : p))}
                  tailoredIds={view?.selected ?? []}
                  renderDetail={narrow && openJob ? () => <InspectionSheet job={openJob} units={units} /> : undefined}
                />
              </div>
              {!narrow && openJob && <InspectionSheet job={openJob} units={units} />}
            </div>
          )}

          {awaiting && (
            <div className="pickbar" role="region" aria-label="Choose jobs to tailor for">
              <p>
                {picked.length === 0
                  ? "Tick up to 3 jobs to tailor your CV bullets for."
                  : `${picked.length} job${picked.length > 1 ? "s" : ""} picked.`}
              </p>
              <button className="primary" type="button" disabled={!picked.length} onClick={tailor}>
                Tailor my CV for {picked.length || "these"} job{picked.length === 1 ? "" : "s"}
              </button>
            </div>
          )}

          {view && <LearnNext items={view.learn_next} total={ranked.length} />}
          {view && <TailorPanel bullets={view.tailored} ranked={ranked} llm={view.mode.llm} />}

          {view?.has_report && runId && (
            <div className="report">
              <a className="primary" href={api.reportUrl(runId)} download>
                Download the report (Markdown)
              </a>
              <span className="muted">Rankings, evidence, skills to learn and the tailored bullets, with sources.</span>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
