import { Fragment, useEffect, useState, type ReactNode } from "react";
import type { Health, SavedJob, Source } from "../types";
import { LinkedInSaved } from "./LinkedInSaved";

export interface StartInput {
  file: File | null;
  cvText: string;
  source: Source;
  companies: string;
  keywords: string;
  pasted: string;
  location: string;
  remoteOk: boolean;
  useLlm: boolean;
}

type CvMode = "upload" | "paste";

const MIN_PASTE = 200;

const SOURCES: { id: Source; title: string; detail: (h: Health | null, saved: number) => string }[] = [
  {
    id: "linkedin",
    title: "Jobs you saved from LinkedIn",
    detail: (_h, n) => (n ? `${n} saved with the Send to CV Matcher button` : "Save them one by one while you browse LinkedIn"),
  },
  { id: "demo", title: "Example postings", detail: (h) => `${h?.snapshot.jobs ?? 40} made-up postings that come with the app; works offline` },
  { id: "companies", title: "Company career pages", detail: () => "Live openings from companies that use Greenhouse, Lever or Ashby" },
  { id: "keywords", title: "Remote job boards", detail: () => "Live openings from Remotive and Arbeitnow" },
  { id: "paste", title: "Postings you paste", detail: () => "Copied from LinkedIn, a company site, anywhere" },
];

function Step({ no, title, children }: { no: number; title: string; children: ReactNode }) {
  return (
    <fieldset className="step">
      <legend>
        <span className="step-no">{no}.</span> {title}
      </legend>
      {children}
    </fieldset>
  );
}

export function SetupForm({
  health,
  busy,
  onStart,
  saved,
  onRemoveSaved,
  onClearSaved,
  linkedInNudge,
}: {
  health: Health | null;
  busy: boolean;
  onStart: (input: StartInput) => void;
  saved: SavedJob[];
  onRemoveSaved: (id: string) => void;
  onClearSaved: () => void;
  /** Goes up when a job arrives from LinkedIn: the form then switches to that source. */
  linkedInNudge: number;
}) {
  const [cvMode, setCvMode] = useState<CvMode>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [cvText, setCvText] = useState("");
  const [source, setSource] = useState<Source>("demo");
  const [companies, setCompanies] = useState("");
  const [keywords, setKeywords] = useState("");
  const [pasted, setPasted] = useState("");
  const [location, setLocation] = useState("Tunis, Tunisia");
  const [remoteOk, setRemoteOk] = useState(true);
  const [useLlm, setUseLlm] = useState(true);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (linkedInNudge > 0) setSource("linkedin");
  }, [linkedInNudge]);

  const pastedChars = cvText.trim().length;
  const cvReady = (cvMode === "upload" && !!file) || (cvMode === "paste" && pastedChars > MIN_PASTE);
  const jobsReady =
    source === "demo" ||
    source === "keywords" ||
    (source === "linkedin" && saved.length > 0) ||
    (source === "companies" && !!companies.trim()) ||
    (source === "paste" && pasted.trim().length > 80);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onStart({
      file: cvMode === "upload" ? file : null,
      cvText: cvMode === "paste" ? cvText : "",
      source,
      companies,
      keywords,
      pasted,
      location,
      remoteOk,
      useLlm: useLlm && !!health?.llm.configured,
    });
  };

  return (
    <form className="setup" onSubmit={submit}>
      <Step no={1} title="Your CV">
        <div className="tabs" role="tablist" aria-label="How to give your CV">
          {(["upload", "paste"] as CvMode[]).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={cvMode === m} className="tab" onClick={() => setCvMode(m)}>
              {m === "upload" ? "Upload a file" : "Paste the text"}
            </button>
          ))}
        </div>

        {cvMode === "upload" &&
          (file ? (
            <div className="file">
              <span className="file-name">{file.name}</span>
              <span className="file-size">{Math.max(1, Math.round(file.size / 1024))} KB</span>
              <button type="button" className="text-button" onClick={() => setFile(null)}>
                Remove
              </button>
            </div>
          ) : (
            <label
              className={`dropzone${dragging ? " is-dragging" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const f = e.dataTransfer.files?.[0];
                if (f) setFile(f);
              }}
            >
              <input type="file" accept=".pdf,.txt,.md,application/pdf,text/plain" className="visually-hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <span className="drop-main">
                Drop your CV here, or <span className="drop-link">choose a file</span>
              </span>
              <span className="drop-sub">PDF or plain text</span>
            </label>
          ))}

        {cvMode === "paste" && (
          <>
            <textarea
              className="input"
              rows={7}
              value={cvText}
              onChange={(e) => setCvText(e.target.value)}
              placeholder="Paste the full text of your CV"
              aria-label="CV text"
              aria-describedby="paste-count"
            />
            <p className="hint" id="paste-count">
              {pastedChars > MIN_PASTE ? `${pastedChars} characters.` : `Paste all of it: at least ${MIN_PASTE} characters (${pastedChars} so far).`}
            </p>
          </>
        )}
        <p className="hint">Your name, email, phone number and links are taken out before anything else happens. Nothing is saved to disk.</p>
      </Step>

      <Step no={2} title="Where to look">
        <div className="sources" role="radiogroup" aria-label="Where to look for jobs">
          {SOURCES.map((s) => (
            <Fragment key={s.id}>
              <label className={`source${source === s.id ? " is-picked" : ""}`}>
                <input type="radio" name="source" value={s.id} checked={source === s.id} onChange={() => setSource(s.id)} />
                <span>
                  <span className="source-title">{s.title}</span>
                  <span className="source-detail">{s.detail(health, saved.length)}</span>
                </span>
              </label>
              {s.id === "linkedin" && source === "linkedin" && <LinkedInSaved saved={saved} onRemove={onRemoveSaved} onClear={onClearSaved} />}
            </Fragment>
          ))}
        </div>
        {source === "companies" && (
          <label className="field">
            <span>Companies</span>
            <input className="input" value={companies} onChange={(e) => setCompanies(e.target.value)} placeholder="stripe, notion, jobs.lever.co/palantir" />
            <span className="hint">Board names or careers-page links, separated by commas.</span>
          </label>
        )}
        {source === "keywords" && (
          <label className="field">
            <span>Extra keywords (optional)</span>
            <input className="input" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="predictive maintenance" />
            <span className="hint">Remotive allows two searches a minute, so results are kept for six hours.</span>
          </label>
        )}
        {source === "paste" && (
          <label className="field">
            <span>Postings</span>
            <textarea
              className="input"
              rows={6}
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              placeholder={"Title: Reliability Engineer\nCompany: ...\n\nRequirements\n- FMEA\n---\nNext posting..."}
            />
            <span className="hint">Put a line with only --- between two postings. A whole LinkedIn job page copied with Ctrl+A works too.</span>
          </label>
        )}
      </Step>

      <Step no={3} title="Where you can work">
        <label className="field">
          <span>City or country</span>
          <input className="input" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Tunis, Tunisia" />
        </label>
        <label className="check">
          <input type="checkbox" checked={remoteOk} onChange={(e) => setRemoteOk(e.target.checked)} /> Remote jobs are fine too
        </label>
      </Step>

      {health?.llm.configured ? (
        <label className="check engine">
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Use {health.llm.model} to judge and rewrite
        </label>
      ) : (
        <p className="hint engine">
          Running offline: matching by rules, and rewrites that only borrow the posting's words. Add an LLM key in <code>backend/.env</code> for
          real rewrites.
        </p>
      )}

      <div className="cta-dock">
        <button className="cta" type="submit" disabled={busy || !cvReady || !jobsReady}>
          {busy ? "Working..." : "Find and rank jobs"}
        </button>
        {!busy && !cvReady && <p className="hint cta-hint">Add your CV first.</p>}
      </div>
    </form>
  );
}
