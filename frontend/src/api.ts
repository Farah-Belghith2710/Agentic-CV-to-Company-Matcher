import type { Capture } from "./bookmarklet";
import type { Health, RunEvent, RunView, SavedJob, Source } from "./types";

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch("/api/health").then((r) => asJson<Health>(r)),
  run: (id: string) => fetch(`/api/runs/${id}`).then((r) => asJson<RunView>(r)),
  reportUrl: (id: string) => `/api/runs/${id}/report.md`,

  /** Jobs you saved from LinkedIn with the Send to CV Matcher button. */
  saved: {
    list: () => fetch("/api/saved").then((r) => asJson<{ count: number; jobs: SavedJob[] }>(r)),
    add: (capture: Capture) =>
      fetch("/api/saved", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(capture) }).then((r) =>
        asJson<{ created: boolean; count: number; job: SavedJob }>(r),
      ),
    remove: (id: string) => fetch(`/api/saved/${encodeURIComponent(id)}`, { method: "DELETE" }).then((r) => asJson<{ count: number; jobs: SavedJob[] }>(r)),
    clear: () => fetch("/api/saved", { method: "DELETE" }).then((r) => asJson<{ count: number; jobs: SavedJob[] }>(r)),
  },

  start: (input: {
    file: File | null;
    cvText: string;
    source: Source;
    companies: string;
    keywords: string;
    pasted: string;
    location: string;
    remoteOk: boolean;
    useLlm: boolean;
  }) => {
    const form = new FormData();
    if (input.file) form.append("cv_file", input.file);
    else form.append("cv_text", input.cvText);
    form.append("source", input.source);
    form.append("companies", input.companies);
    form.append("keywords", input.keywords);
    form.append("pasted", input.pasted);
    form.append("location", input.location);
    form.append("remote_ok", String(input.remoteOk));
    form.append("use_llm", String(input.useLlm));
    return fetch("/api/runs", { method: "POST", body: form }).then((r) => asJson<{ run_id: string }>(r));
  },

  select: (id: string, jobIds: string[]) =>
    fetch(`/api/runs/${id}/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_ids: jobIds }),
    }).then((r) => asJson<{ ok: boolean }>(r)),

  /** Live events (Server-Sent Events). Returns a function that closes the stream. */
  events: (id: string, onEvent: (e: RunEvent) => void, onDrop: () => void) => {
    const es = new EventSource(`/api/runs/${id}/events`);
    es.onmessage = (msg) => {
      const ev = JSON.parse(msg.data) as RunEvent;
      onEvent(ev);
      if (ev.type === "end") es.close();
    };
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) onDrop();
    };
    return () => es.close();
  },
};
