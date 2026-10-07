"""Runs: each analysis executes the LangGraph agent in a background thread and records an event
log that the API streams to the browser (Server-Sent Events)."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any

from langgraph.types import Command

from .config import settings
from .graph import GRAPH, NODE_ORDER, PipelineError, RunContext
from .llm import LLMClient
from .scoring import Preferences

TERMINAL = {"done", "error"}


@dataclass
class Run:
    id: str
    options: dict
    cv_label: str
    ctx: RunContext
    created: float = field(default_factory=time.time)
    status: str = "queued"  # queued | running | awaiting_selection | done | error
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None

    @property
    def config(self) -> dict:
        return {"configurable": {"thread_id": self.id, "ctx": self.ctx}, "recursion_limit": 60}

    def push(self, event: dict) -> None:
        with self.lock:
            event = {**event, "seq": len(self.events) + 1}
            event.setdefault("ts", time.time())
            self.events.append(event)

    def events_since(self, seq: int) -> list[dict]:
        with self.lock:
            return self.events[seq:]

    def set_status(self, status: str, message: str = "") -> None:
        self.status = status
        self.push({"type": "status", "status": status, "message": message})


class RunManager:
    def __init__(self, keep: int = 25) -> None:
        self.keep = keep
        self.runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def create(self, cv_text: str, options: dict, cv_label: str, use_llm: bool) -> Run:
        llm = LLMClient() if (use_llm and settings.llm_configured) else None
        ctx = RunContext(llm=llm, prefs=Preferences(location=options.get("location", ""), remote_ok=options.get("remote_ok", True)))
        run = Run(id=uuid.uuid4().hex[:12], options=options, cv_label=cv_label, ctx=ctx)
        with self._lock:
            self.runs[run.id] = run
            if len(self.runs) > self.keep:  # forget the oldest runs (CV text lives only in memory)
                for old in sorted(self.runs.values(), key=lambda r: r.created)[: len(self.runs) - self.keep]:
                    if old.status in TERMINAL | {"awaiting_selection"}:
                        self.runs.pop(old.id, None)
        payload = {"run_id": run.id, "cv_text": cv_text, "options": options}
        self._start(run, payload)
        return run

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def select(self, run: Run, job_ids: list[str]) -> None:
        if run.status != "awaiting_selection":
            raise ValueError(f"This run is {run.status}, not waiting for a selection.")
        self._start(run, Command(resume=job_ids))

    def _start(self, run: Run, payload: Any) -> None:
        run.set_status("running")
        run.thread = threading.Thread(target=self._execute, args=(run, payload), daemon=True)
        run.thread.start()

    def _execute(self, run: Run, payload: Any) -> None:
        try:
            for mode, chunk in GRAPH.stream(payload, run.config, stream_mode=["custom", "updates"]):
                if mode == "custom" and isinstance(chunk, dict):
                    run.push(chunk)
                elif mode == "updates":
                    run.snapshot = dict(GRAPH.get_state(run.config).values)
            state = GRAPH.get_state(run.config)
            run.snapshot = dict(state.values)
            if state.next:
                run.set_status("awaiting_selection", "Pick 1-3 jobs to tailor your CV for.")
            else:
                run.set_status("done", "Finished.")
        except PipelineError as exc:
            run.error = str(exc)
            run.push({"type": "log", "node": "pipeline", "level": "error", "message": str(exc)})
            run.set_status("error", str(exc))
        except Exception as exc:  # unexpected bug: keep the server alive and show a useful message
            traceback.print_exc()
            run.error = f"Unexpected error: {exc.__class__.__name__}: {exc}"
            run.push({"type": "log", "node": "pipeline", "level": "error", "message": run.error})
            run.set_status("error", run.error)


manager = RunManager()


def run_view(run: Run) -> dict:
    """Everything the UI needs, in one JSON document."""
    st = run.snapshot
    jobs = {j["id"]: j for j in st.get("pool", [])}
    shortlist = {s["job_id"]: s for s in st.get("shortlist", [])}
    reasons = st.get("triage_reasons", {})
    ranked = []
    for a in st.get("analyses", []):
        j = jobs.get(a["job_id"], {})
        sl = shortlist.get(a["job_id"], {})
        ranked.append(
            {
                **a,
                "job": {k: j.get(k) for k in ("id", "title", "company", "location", "workplace", "url", "source", "source_label", "attribution", "posted_at")},
                "description": (j.get("description") or "")[:6000],
                "bm25": sl.get("bm25"),
                "semantic": sl.get("semantic"),
                "triage_reason": reasons.get(a["job_id"], ""),
            }
        )
    llm = run.ctx.llm
    return {
        "id": run.id,
        "status": run.status,
        "error": run.error,
        "created": run.created,
        "cv_label": run.cv_label,
        "options": {k: v for k, v in run.options.items() if k != "pasted"},
        "mode": {"llm": bool(llm), "model": llm.cfg.llm_model if llm else None},
        "redaction": st.get("redaction", {}),
        "profile": st.get("profile"),
        "units": st.get("units", []),
        "queries": st.get("queries", []),
        "query_log": st.get("query_log", []),
        "pool_size": len(jobs),
        "relevant_count": len(st.get("relevant", [])),
        "similarity": st.get("similarity"),
        "ranked": ranked,
        "learn_next": st.get("learn_next", []),
        "selected": st.get("selected", []),
        "tailored": st.get("tailored", []),
        "has_report": bool(st.get("report_md")),
        "warnings": st.get("warnings", []),
        "llm_stats": llm.stats.as_dict() if llm else None,
        "nodes": NODE_ORDER,
        "event_count": len(run.events),
    }
