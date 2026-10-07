"""FastAPI server: start runs, stream their progress (SSE), resume after job selection, serve the report.

Run with:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import BACKEND_DIR, DATA_DIR, settings
from .cv_parser import CVError, extract_pdf_text
from .graph import GRAPH
from .retrieval import similarity_status
from .runs import TERMINAL, manager, run_view
from .sources import load_snapshot
from .text import clean_text

app = FastAPI(title="CV-to-Job Matcher", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLES_DIR = DATA_DIR / "sample_cvs"
SAMPLES = {
    "lina": {"file": "lina_haddad_reliability", "name": "Lina Haddad", "headline": "Reliability & maintenance engineering student", "language": "English"},
    "alex": {"file": "alex_moreau_backend", "name": "Alex Moreau", "headline": "Backend software engineer, 4 years", "language": "English"},
    "sami": {"file": "sami_gharbi_analyste", "name": "Sami Gharbi", "headline": "Analyste de données, 2 ans", "language": "French"},
}
MAX_UPLOAD = 5 * 1024 * 1024
MAX_TEXT = 60_000
SOURCES = {"demo", "companies", "keywords", "paste"}


@app.get("/api/health")
def health() -> dict:
    try:
        snapshot_jobs = len(load_snapshot())
    except Exception:
        snapshot_jobs = 0
    host = re.sub(r"^https?://", "", settings.llm_base_url).split("/")[0]
    return {
        "ok": True,
        "llm": {"configured": settings.llm_configured, "model": settings.llm_model or None, "host": host if settings.llm_configured else None},
        "similarity": similarity_status(),
        "snapshot": {"file": settings.snapshot_path.name, "jobs": snapshot_jobs},
    }


@app.get("/api/samples")
def samples() -> list[dict]:
    return [{"id": k, **{x: v[x] for x in ("name", "headline", "language")}} for k, v in SAMPLES.items()]


@app.get("/api/samples/{sample_id}.pdf")
def sample_pdf(sample_id: str):
    s = SAMPLES.get(sample_id)
    path = SAMPLES_DIR / f"{s['file']}.pdf" if s else None
    if not path or not path.exists():
        raise HTTPException(404, "Unknown sample.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/api/graph", response_class=PlainTextResponse)
def graph_mermaid() -> str:
    return GRAPH.get_graph().draw_mermaid()


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@app.post("/api/runs")
async def create_run(
    cv_file: UploadFile | None = File(None),
    cv_text: str = Form(""),
    sample_id: str = Form(""),
    source: str = Form("demo"),
    companies: str = Form(""),
    keywords: str = Form(""),
    pasted: str = Form(""),
    location: str = Form(""),
    remote_ok: str = Form("true"),
    use_llm: str = Form("true"),
) -> dict:
    if source not in SOURCES:
        raise HTTPException(400, f"Unknown job source '{source}'.")
    label = "pasted text"
    text = ""
    if cv_file is not None and cv_file.filename:
        data = await cv_file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(400, "That file is over 5 MB. Upload a smaller PDF or paste the text.")
        name = cv_file.filename.lower()
        try:
            if name.endswith(".pdf") or data[:4] == b"%PDF":
                text = await asyncio.to_thread(extract_pdf_text, data)
            elif name.endswith((".txt", ".md")):
                text = clean_text(data.decode("utf-8", errors="replace"))
            else:
                raise HTTPException(400, "Upload a PDF or a .txt file, or paste your CV text.")
        except CVError as exc:
            raise HTTPException(400, str(exc)) from exc
        label = cv_file.filename
    elif sample_id:
        s = SAMPLES.get(sample_id)
        if not s:
            raise HTTPException(400, "Unknown sample CV.")
        text = clean_text((SAMPLES_DIR / f"{s['file']}.txt").read_text(encoding="utf-8"))
        label = f"Sample: {s['name']}"
    elif cv_text.strip():
        text = clean_text(cv_text[:MAX_TEXT])
    if len(text) < 200:
        raise HTTPException(400, "Add your CV first: upload a PDF, paste the text, or pick a sample.")
    if source == "companies" and not companies.strip():
        raise HTTPException(400, "List at least one company board, for example: stripe, notion, linear.")
    if source == "paste" and len(pasted.strip()) < 80:
        raise HTTPException(400, "Paste the full text of at least one job posting.")
    options = {
        "source": source,
        "companies": companies[:2000],
        "keywords": keywords[:300],
        "pasted": pasted[:MAX_TEXT],
        "location": location[:120],
        "remote_ok": _bool(remote_ok, True),
    }
    run = manager.create(text, options, label, use_llm=_bool(use_llm, True))
    return {"run_id": run.id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = manager.get(run_id)
    if not run:
        raise HTTPException(404, "This run no longer exists (the server keeps the last 25 runs in memory).")
    return run_view(run)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = 0):
    run = manager.get(run_id)
    if not run:
        raise HTTPException(404, "Unknown run.")
    last = request.headers.get("last-event-id")
    if last and last.isdigit():
        after = int(last)

    async def stream():
        seq, last_ping = after, time.time()
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                break
            for ev in run.events_since(seq):
                seq = ev["seq"]
                yield f"id: {seq}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if run.status in TERMINAL and not run.events_since(seq):
                yield f"data: {json.dumps({'type': 'end', 'status': run.status})}\n\n"
                break
            if time.time() - last_ping > 15:
                last_ping = time.time()
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


class Selection(BaseModel):
    job_ids: list[str]


@app.post("/api/runs/{run_id}/select")
def select_jobs(run_id: str, body: Selection) -> dict:
    run = manager.get(run_id)
    if not run:
        raise HTTPException(404, "Unknown run.")
    if not 1 <= len(body.job_ids) <= 3:
        raise HTTPException(400, "Pick between 1 and 3 jobs.")
    try:
        manager.select(run, body.job_ids)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}


@app.get("/api/runs/{run_id}/report.md")
def report(run_id: str):
    run = manager.get(run_id)
    md = run.snapshot.get("report_md") if run else None
    if not md:
        raise HTTPException(404, "The report is not ready yet.")
    return Response(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="cv-match-report-{run_id}.md"'},
    )


# Serve the built React app (frontend/dist) when it exists, so one server is enough in production.
DIST = BACKEND_DIR.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
