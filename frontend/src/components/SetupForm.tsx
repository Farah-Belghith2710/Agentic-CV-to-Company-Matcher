import { useRef, useState } from "react";
import { api } from "../api";
import type { Health, Sample, Source } from "../types";

export interface StartInput {
  file: File | null;
  cvText: string;
  sampleId: string;
  source: Source;
  companies: string;
  keywords: string;
  pasted: string;
  location: string;
  remoteOk: boolean;
  useLlm: boolean;
}

type CvMode = "upload" | "sample" | "paste";

const SOURCES: { id: Source; title: string; detail: (h: Health | null) => string }[] = [
  { id: "demo", title: "Saved snapshot", detail: (h) => `${h?.snapshot.jobs ?? "40"} postings, works offline` },
  { id: "companies", title: "Company career boards", detail: () => "Live postings from Greenhouse, Lever or Ashby" },
  { id: "keywords", title: "Remote job boards", detail: () => "Remotive and Arbeitnow, searched with your titles" },
  { id: "paste", title: "Paste postings", detail: () => "Postings you copied from anywhere" },
];

export function SetupForm({
  health,
  samples,
  busy,
  onStart,
}: {
  health: Health | null;
  samples: Sample[];
  busy: boolean;
  onStart: (input: StartInput) => void;
}) {
  const [cvMode, setCvMode] = useState<CvMode>("sample");
  const [file, setFile] = useState<File | null>(null);
  const [sampleId, setSampleId] = useState("lina");
  const [cvText, setCvText] = useState("");
  const [source, setSource] = useState<Source>("demo");
  const [companies, setCompanies] = useState("");
  const [keywords, setKeywords] = useState("");
  const [pasted, setPasted] = useState("");
  const [location, setLocation] = useState("Tunis, Tunisia");
  const [remoteOk, setRemoteOk] = useState(true);
  const [useLlm, setUseLlm] = useState(true);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const cvReady = (cvMode === "upload" && file) || (cvMode === "sample" && sampleId) || (cvMode === "paste" && cvText.trim().length > 200);
  const jobsReady =
    source === "demo" || source === "keywords" || (source === "companies" && companies.trim()) || (source === "paste" && pasted.trim().length > 80);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onStart({
      file: cvMode === "upload" ? file : null,
      cvText: cvMode === "paste" ? cvText : "",
      sampleId: cvMode === "sample" ? sampleId : "",
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
      <fieldset className="step">
        <legend>
          <span className="step-no">1</span> Your CV
        </legend>
        <div className="tabs" role="tablist" aria-label="How to provide your CV">
          {(["upload", "sample", "paste"] as CvMode[]).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={cvMode === m} className="tab" onClick={() => setCvMode(m)}>
              {m === "upload" ? "Upload PDF" : m === "sample" ? "Use a sample" : "Paste text"}
            </button>
          ))}
        </div>
        {cvMode === "upload" && (
          <div
            className={`dropzone${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
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
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain"
              className="visually-hidden"
              id="cv-file"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <p>
                <strong>{file.name}</strong> <span className="muted">({Math.round(file.size / 1024)} KB)</span>{" "}
                <button type="button" className="link" onClick={() => setFile(null)}>
                  Remove
                </button>
              </p>
            ) : (
              <p>
                Drop your CV here (PDF or .txt), or{" "}
                <label htmlFor="cv-file" className="link">
                  choose a file
                </label>
              </p>
            )}
          </div>
        )}
        {cvMode === "sample" && (
          <div className="samples">
            {samples.map((s) => (
              <label key={s.id} className={`sample${sampleId === s.id ? " is-picked" : ""}`}>
                <input type="radio" name="sample" value={s.id} checked={sampleId === s.id} onChange={() => setSampleId(s.id)} />
                <span>
                  <span className="sample-name">{s.name}</span>
                  <span className="muted">
                    {s.headline}, in {s.language}
                  </span>
                </span>
                <a className="link sample-pdf" href={api.samplePdfUrl(s.id)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                  PDF
                </a>
              </label>
            ))}
            <p className="hint">Fictional people, made up to try the app.</p>
          </div>
        )}
        {cvMode === "paste" && (
          <textarea
            className="input"
            rows={7}
            value={cvText}
            onChange={(e) => setCvText(e.target.value)}
            placeholder="Paste the full text of your CV"
            aria-label="CV text"
          />
        )}
        <p className="hint">Your email, phone, links and name are removed before anything else happens. Nothing is stored on disk.</p>
      </fieldset>

      <fieldset className="step">
        <legend>
          <span className="step-no">2</span> Jobs to search
        </legend>
        <div className="sources">
          {SOURCES.map((s) => (
            <label key={s.id} className={`source${source === s.id ? " is-picked" : ""}`}>
              <input type="radio" name="source" value={s.id} checked={source === s.id} onChange={() => setSource(s.id)} />
              <span>
                <span className="source-title">{s.title}</span>
                <span className="muted">{s.detail(health)}</span>
              </span>
            </label>
          ))}
        </div>
        {source === "companies" && (
          <label className="field">
            <span>Companies</span>
            <input
              className="input"
              value={companies}
              onChange={(e) => setCompanies(e.target.value)}
              placeholder="stripe, notion, jobs.lever.co/palantir"
            />
            <span className="hint">Board names or careers-page URLs, separated by commas.</span>
          </label>
        )}
        {source === "keywords" && (
          <label className="field">
            <span>Extra keywords (optional)</span>
            <input className="input" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="predictive maintenance" />
            <span className="hint">Remotive allows 2 requests a minute, so results are cached for 6 hours.</span>
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
          </label>
        )}
      </fieldset>

      <fieldset className="step">
        <legend>
          <span className="step-no">3</span> Where you can work
        </legend>
        <label className="field">
          <span>Location</span>
          <input className="input" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Tunis, Tunisia" />
        </label>
        <label className="check">
          <input type="checkbox" checked={remoteOk} onChange={(e) => setRemoteOk(e.target.checked)} /> Remote roles are fine
        </label>
      </fieldset>

      <div className="engine">
        {health?.llm.configured ? (
          <label className="check">
            <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Use {health.llm.model} for
            judging and rewriting
          </label>
        ) : (
          <p className="hint">
            Offline mode: rule-based matching and terminology-only tailoring. Add an LLM key in <code>backend/.env</code> for full
            rewrites.
          </p>
        )}
      </div>

      <button className="primary" type="submit" disabled={busy || !cvReady || !jobsReady}>
        {busy ? "Running..." : "Find and rank jobs"}
      </button>
    </form>
  );
}
