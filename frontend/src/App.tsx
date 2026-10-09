import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { AgentLog } from "./components/AgentLog";
import { InspectionSheet } from "./components/InspectionSheet";
import { JobList } from "./components/JobList";
import { LearnNext } from "./components/LearnNext";
import { Logo } from "./components/marks";
import { PipelineRail, type StageState } from "./components/PipelineRail";
import { ProfileSummary } from "./components/ProfileSummary";
import { CHANNEL, SaveFromLinkedIn } from "./components/SaveFromLinkedIn";
import { SetupForm, type StartInput } from "./components/SetupForm";
import { TailorPanel } from "./components/TailorPanel";
import { captureFromHash } from "./bookmarklet";
import type { Health, RunEvent, RunStatus, RunView, SavedJob } from "./types";
import { useNarrow } from "./useNarrow";

const REFRESH_ON_DONE = new Set(["parse_cv", "triage", "score_rank", "verify", "report", "pick_jobs"]);

/** The Send to CV Matcher button opens the app with "#save=..." in a small window: that window only saves the job. */
export default function App() {
  const [saveRequest] = useState(() => (window.location.hash.startsWith("#save=") ? { capture: captureFromHash(window.location.hash) } : null));
  return saveRequest ? <SaveFromLinkedIn capture={saveRequest.capture} /> : <Workbench />;
}

function Workbench() {
  const [health, setHealth] = useState<Health | null>(null);
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
  const sheetRef = useRef<HTMLElement>(null);
  const [saved, setSaved] = useState<SavedJob[]>([]);
  const [linkedInNudge, setLinkedInNudge] = useState(0);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setBackendDown(true));
    return () => closeStream.current();
  }, []);

  // Jobs saved from LinkedIn: load them, and follow along when the button saves a new one.
  const loadSaved = useCallback((nudge: boolean) => {
    api.saved
      .list()
      .then((res) => {
        setSaved(res.jobs);
        if (nudge && res.count > 0) setLinkedInNudge((n) => n + 1);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    window.name = "cv-matcher"; // the save window's "Open CV Matcher" link comes back to this tab
    loadSaved(true);
    let ch: BroadcastChannel | null = null;
    try {
      ch = new BroadcastChannel(CHANNEL);
      ch.onmessage = (e) => e.data?.type === "saved" && loadSaved(true);
    } catch {
      /* no BroadcastChannel: the visibility check below still catches up */
    }
    const onVisible = () => document.visibilityState === "visible" && loadSaved(false);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      ch?.close();
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [loadSaved]);

  const removeSaved = (id: string) => api.saved.remove(id).then((res) => setSaved(res.jobs)).catch((e: Error) => setError(e.message));
  const clearSaved = () => api.saved.clear().then((res) => setSaved(res.jobs)).catch((e: Error) => setError(e.message));

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
    // When the form sits above the results (small screens), bring the results into view.
    if (window.matchMedia?.("(max-width: 900px)").matches) sheetRef.current?.scrollIntoView({ block: "start" });
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
      <header className="topbar">
        <p className="wordmark">
          <Logo />
          CV Matcher
        </p>
        <p className="topbar-status">
          {health
            ? `${health.llm.configured ? `Using ${health.llm.model}` : "Offline mode"}${
                saved.length ? `, ${saved.length} job${saved.length > 1 ? "s" : ""} saved from LinkedIn` : ""
              }`
            : backendDown
              ? "Server not running"
              : "Connecting..."}
        </p>
      </header>

      <div className="workspace">
        <aside className="desk" aria-label="Your search">
          <SetupForm
            health={health}
            busy={busy}
            onStart={start}
            saved={saved}
            onRemoveSaved={removeSaved}
            onClearSaved={clearSaved}
            linkedInNudge={linkedInNudge}
          />
        </aside>

        <main className="sheet" ref={sheetRef} aria-live="polite">
          {backendDown && (
            <p className="banner" role="alert">
              The app cannot reach its server. Start it with <code>start.bat</code> (or <code>uvicorn app.main:app --port 8000</code> in the
              backend folder), then reload this page.
            </p>
          )}

          <PipelineRail stages={stages} status={status} view={view} events={events} compact={ranked.length > 0} />

          {error && (
            <div className="error" role="alert">
              <strong>The run stopped.</strong> {error}
            </div>
          )}

          {view?.profile && <ProfileSummary view={view} />}

          {ranked.length > 0 && (
            <section className="results" aria-label="Ranked jobs">
              <div className="results-list">
                <h2 className="section-title">
                  Best matches <span className="section-count">{ranked.length} jobs, best first</span>
                </h2>
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
              {!narrow && openJob && (
                <div className="results-detail">
                  <InspectionSheet job={openJob} units={units} />
                </div>
              )}
            </section>
          )}

          {awaiting && (
            <div className="pickbar" role="region" aria-label="Choose jobs to tailor for">
              <p>
                {picked.length === 0
                  ? "Tick up to 3 jobs, and the agent rewrites your CV bullets for them."
                  : picked.length === 3
                    ? "3 jobs ticked. That is the most at once."
                    : `${picked.length} job${picked.length > 1 ? "s" : ""} ticked. You can add ${3 - picked.length} more.`}
              </p>
              <button className="cta" type="button" disabled={!picked.length} onClick={tailor}>
                Tailor my CV for {picked.length || "these"} job{picked.length === 1 ? "" : "s"}
              </button>
            </div>
          )}

          {view && <LearnNext items={view.learn_next} total={ranked.length} />}
          {view && <TailorPanel bullets={view.tailored} ranked={ranked} llm={view.mode.llm} />}

          {view?.has_report && runId && (
            <p className="report">
              <a className="button-secondary" href={api.reportUrl(runId)} download>
                Download the report
              </a>
              <span>A Markdown file with the ranking, the evidence, what to learn and your tailored bullets.</span>
            </p>
          )}

          <AgentLog events={events} startTs={startTs} />
        </main>
      </div>
    </div>
  );
}
