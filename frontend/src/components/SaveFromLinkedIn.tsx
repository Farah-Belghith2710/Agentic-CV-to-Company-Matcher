import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Capture } from "../bookmarklet";
import type { SavedJob } from "../types";
import { Logo, PenMark } from "./marks";

export const CHANNEL = "cv-matcher";

type State =
  | { kind: "naming" }
  | { kind: "saving" }
  | { kind: "saved"; job: SavedJob; count: number; created: boolean }
  | { kind: "error"; message: string };

/** The small window the Send to CV Matcher button opens: it saves the posting and closes itself. */
export function SaveFromLinkedIn({ capture }: { capture: Capture | null }) {
  const needsName = !!capture && !capture.title?.trim();
  const [state, setState] = useState<State>(
    !capture
      ? { kind: "error", message: "This window did not receive a job. Go back to LinkedIn and click the button again." }
      : needsName
        ? { kind: "naming" }
        : { kind: "saving" },
  );
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState(capture?.company ?? "");
  const [toSave, setToSave] = useState<Capture | null>(capture);
  const closeTimer = useRef<number | null>(null);
  const started = useRef(false);
  const openedByButton = !!window.opener;

  const save = useCallback(
    (c: Capture) => {
      setToSave(c);
      setState({ kind: "saving" });
      api.saved
        .add(c)
        .then((res) => {
          setState({ kind: "saved", job: res.job, count: res.count, created: res.created });
          try {
            const ch = new BroadcastChannel(CHANNEL);
            ch.postMessage({ type: "saved", id: res.job.id });
            ch.close();
          } catch {
            /* older browser: the main window refreshes when you switch back to it */
          }
          if (openedByButton) closeTimer.current = window.setTimeout(() => window.close(), 2600);
        })
        .catch((e: Error) =>
          setState({
            kind: "error",
            message: /fetch|network/i.test(e.message) ? "CV Matcher is not running. Start it with start.bat, then click the button again." : e.message,
          }),
        );
    },
    [openedByButton],
  );

  useEffect(() => {
    if (started.current) return; // save once, even when React runs effects twice in development
    started.current = true;
    // The posting is in the address; take it out so a reload does not save it again.
    window.history.replaceState(null, "", "/");
    document.title = "Saving to CV Matcher";
    if (capture && !needsName) save(capture);
  }, [capture, needsName, save]);

  useEffect(() => () => void (closeTimer.current && window.clearTimeout(closeTimer.current)), []);

  return (
    <main className="save-view">
      <p className="wordmark">
        <Logo />
        CV Matcher
      </p>
      {state.kind === "naming" && capture && (
        <form
          className="save-name"
          onSubmit={(e) => {
            e.preventDefault();
            save({ ...capture, title: title.trim(), company: company.trim() });
          }}
        >
          <p className="save-lede">This page does not show the job's title. What is the job called?</p>
          <label className="field">
            <span>Job title</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus required />
          </label>
          <label className="field">
            <span>Company</span>
            <input className="input" value={company} onChange={(e) => setCompany(e.target.value)} />
          </label>
          <p className="save-actions">
            <button type="submit" className="cta" disabled={!title.trim()}>
              Save the job
            </button>
          </p>
        </form>
      )}
      {state.kind === "saving" && <p className="save-status">Saving the job...</p>}
      {state.kind === "saved" && (
        <>
          <p className="save-status is-saved">
            <PenMark verdict="met" size={22} label={false} />
            {state.created ? "Saved" : "Already saved, updated"}
          </p>
          <h1 className="save-title">{state.job.title}</h1>
          <p className="save-meta">
            {state.job.company}
            {state.job.location ? `, ${state.job.location}` : ""}
          </p>
          <p className="save-count">
            You have {state.count} job{state.count === 1 ? "" : "s"} from LinkedIn in CV Matcher.
          </p>
          <p className="save-actions">
            {openedByButton && <span className="muted">This window closes by itself.</span>}
            <a href="/" target="cv-matcher">
              Open CV Matcher
            </a>
          </p>
        </>
      )}
      {state.kind === "error" && (
        <>
          <p className="save-status is-error">
            <PenMark verdict="missing" size={22} label={false} />
            Not saved
          </p>
          <p className="save-error">{state.message}</p>
          <p className="save-actions">
            {toSave && (
              <button type="button" className="text-button" onClick={() => save(toSave)}>
                Try again
              </button>
            )}
            <button type="button" className="text-button" onClick={() => window.close()}>
              Close
            </button>
          </p>
        </>
      )}
    </main>
  );
}
