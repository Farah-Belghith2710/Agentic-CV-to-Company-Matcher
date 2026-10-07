"""Keyword job boards with free public APIs.

Remotive  GET https://remotive.com/api/remote-jobs?search=...   (remote jobs)
          Terms: link back to the Remotive URL and name Remotive as the source; at most
          2 requests/minute (4 fetches/day recommended); do not resubmit jobs to other boards.
Arbeitnow GET https://www.arbeitnow.com/api/job-board-api?page=N  (mostly Germany/Europe)
"""
from __future__ import annotations

from ..schemas import Job
from ..text import html_to_text
from .http import get_json


def fetch_remotive(search: str, limit: int = 60) -> list[Job]:
    data = get_json("https://remotive.com/api/remote-jobs", {"search": search, "limit": limit}, ttl=6 * 3600) or {}
    jobs = []
    for j in data.get("jobs", []):
        loc = j.get("candidate_required_location") or "Remote"
        jobs.append(
            Job(
                id=f"remotive:{j.get('id')}",
                source="remotive",
                source_label="Remotive",
                company=j.get("company_name") or "Unknown company",
                title=(j.get("title") or "").strip(),
                location=f"Remote ({loc})" if "remote" not in loc.lower() else loc,
                workplace="remote",
                url=j.get("url") or "",
                posted_at=j.get("publication_date"),
                description=html_to_text(j.get("description", "")),
                tags=[t for t in [j.get("category"), j.get("job_type")] if t],
                attribution="Job via Remotive (remotive.com)",
            )
        )
    return jobs


def fetch_arbeitnow(pages: int = 2) -> list[Job]:
    jobs = []
    for page in range(1, pages + 1):
        data = get_json("https://www.arbeitnow.com/api/job-board-api", {"page": page}, ttl=6 * 3600) or {}
        for j in data.get("data", []):
            remote = bool(j.get("remote"))
            loc = j.get("location") or ""
            jobs.append(
                Job(
                    id=f"arbeitnow:{j.get('slug')}",
                    source="arbeitnow",
                    source_label="Arbeitnow",
                    company=j.get("company_name") or "Unknown company",
                    title=(j.get("title") or "").strip(),
                    location=(f"{loc} (remote)" if remote and loc else loc) or ("Remote" if remote else ""),
                    workplace="remote" if remote else "onsite",
                    url=j.get("url") or "",
                    posted_at=str(j.get("created_at")) if j.get("created_at") else None,
                    description=html_to_text(j.get("description", "")),
                    tags=list(j.get("tags") or []) + list(j.get("job_types") or []),
                    attribution="Job via Arbeitnow (arbeitnow.com)",
                )
            )
        if not data.get("data"):
            break
    return jobs
