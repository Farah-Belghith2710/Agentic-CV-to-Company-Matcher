"""Jobs you saved from LinkedIn with the "Send to CV Matcher" button, kept in a small JSON file.

The button runs in your own browser, on the LinkedIn page you are reading, and hands this app what
that page shows: title, company, location and the description. Nothing here ever contacts LinkedIn.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone

from pydantic import BaseModel

from .config import settings
from .schemas import Job
from .sources.linkedin import header_facts, parse_linkedin_text, strip_heading, workplace_from
from .text import clean_text

MAX_SAVED = 100
MAX_DESCRIPTION = 30_000
_lock = threading.Lock()
_JOB_ID = re.compile(r"/jobs/view/(?:[^/?#]*?-)?(\d{6,})|[?&]currentJobId=(\d{6,})")


class Capture(BaseModel):
    """What the button sends: fields read from the page, and the page text as a fallback."""

    url: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    top: str = ""  # the header of the posting (workplace type, employment type, date)
    description: str = ""
    page_text: str = ""  # whole page, used when the description element was not found
    selection: str = ""  # text you selected yourself; wins over everything else


class CaptureError(ValueError):
    pass


def linkedin_job_id(url: str) -> str:
    m = _JOB_ID.search(url or "")
    return (m.group(1) or m.group(2)) if m else ""


def _one_line(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def job_from_capture(c: Capture) -> Job:
    selection = clean_text(c.selection or "")
    description = strip_heading(clean_text(c.description or ""))
    parsed = parse_linkedin_text(c.page_text) if c.page_text and (len(description) < 120 or not c.title.strip()) else None
    if len(selection) >= 200:
        description = selection
    elif len(description) < 120 and parsed and len(parsed.description) >= 120:
        description = parsed.description
    if len(description) < 80:
        raise CaptureError(
            "The job description was not found on that page. On LinkedIn, select the description text with your mouse, "
            "then click the button again."
        )
    title = _one_line(c.title, 160) or (parsed.title if parsed else "") or "LinkedIn job"
    company = _one_line(c.company, 120) or (parsed.company if parsed else "")
    location = _one_line(c.location, 120) or (parsed.location if parsed else "")
    workplace, internship = header_facts(clean_text(c.top or ""))
    if workplace == "unknown" and parsed:
        workplace = parsed.workplace
    if workplace == "unknown":
        workplace = workplace_from(f"{location}\n{description[:600]}")
    internship = internship or bool(parsed and parsed.internship)

    job_id = linkedin_job_id(c.url)
    url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else (c.url if c.url.startswith("https://") and "/jobs/" in c.url else "")
    ident = job_id or hashlib.sha1(f"{title}|{company}".lower().encode("utf-8")).hexdigest()[:12]
    return Job(
        id=f"linkedin:{ident}",
        source="linkedin",
        source_label="LinkedIn",
        company=company or "Company not shown",
        title=title,
        location=location,
        workplace=workplace,
        url=url,
        description=description[:MAX_DESCRIPTION],
        tags=["Internship"] if internship else [],
        attribution="Saved by you from LinkedIn",
    )


def _read() -> list[dict]:
    path = settings.saved_path
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("jobs", []) if isinstance(data, dict) else data
    return [it for it in items if isinstance(it, dict) and it.get("id")]


def _write(items: list[dict]) -> None:
    path = settings.saved_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    payload = {"note": "Jobs you saved from LinkedIn with the Send to CV Matcher button. Safe to delete.", "jobs": items}
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_saved() -> list[dict]:
    with _lock:
        return _read()


def load_jobs() -> list[Job]:
    return [Job.model_validate(it) for it in list_saved()]


def add(capture: Capture) -> tuple[Job, bool, int]:
    """Save a posting (newest first). Saving the same LinkedIn job again replaces it."""
    job = job_from_capture(capture)
    with _lock:
        items = _read()
        rest = [it for it in items if it.get("id") != job.id]
        created = len(rest) == len(items)
        if created and len(items) >= MAX_SAVED:
            raise CaptureError(f"You already have {MAX_SAVED} saved jobs. Remove a few in CV Matcher, then try again.")
        entry = {**job.model_dump(), "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        items = [entry, *rest]
        _write(items)
    return job, created, len(items)


def remove(job_id: str) -> int:
    with _lock:
        items = [it for it in _read() if it.get("id") != job_id]
        _write(items)
        return len(items)


def clear() -> None:
    with _lock:
        _write([])


def summary(item: dict) -> dict:
    """What the app shows in the list of saved jobs."""
    return {
        "id": item["id"],
        "title": item.get("title", ""),
        "company": item.get("company", ""),
        "location": item.get("location", ""),
        "workplace": item.get("workplace", "unknown"),
        "url": item.get("url", ""),
        "internship": "Internship" in (item.get("tags") or []),
        "saved_at": item.get("saved_at"),
    }
