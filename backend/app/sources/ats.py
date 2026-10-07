"""Company career boards through the public, documented, keyless APIs of three applicant
tracking systems. These are the feeds companies publish to power their own careers pages.

  Greenhouse  GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
  Lever       GET https://api.lever.co/v0/postings/{site}?mode=json   (EU: api.eu.lever.co)
  Ashby       GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import Job
from ..text import clean_text, html_to_text
from .http import SourceError, get_json

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


@dataclass
class BoardSpec:
    ats: str | None  # greenhouse | lever | ashby | None (= try all)
    slug: str
    raw: str


def parse_board_spec(raw: str) -> BoardSpec:
    """Accepts 'stripe', 'greenhouse:stripe', or a careers URL on one of the three ATS domains."""
    s = raw.strip().rstrip("/")
    patterns = [
        ("greenhouse", r"(?:job-)?boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?(?:embed/job_board\?for=)?([^/?#&]+)"),
        ("lever", r"jobs(?:\.eu)?\.lever\.co/([^/?#]+)"),
        ("lever", r"api(?:\.eu)?\.lever\.co/v0/postings/([^/?#]+)"),
        ("ashby", r"jobs\.ashbyhq\.com/([^/?#]+)"),
        ("ashby", r"api\.ashbyhq\.com/posting-api/job-board/([^/?#]+)"),
    ]
    for ats, pat in patterns:
        m = re.search(pat, s, flags=re.I)
        if m:
            return BoardSpec(ats, m.group(1), raw)
    m = re.match(r"^(greenhouse|lever|ashby)\s*:\s*(.+)$", s, flags=re.I)
    if m:
        return BoardSpec(m.group(1).lower(), m.group(2).strip(), raw)
    return BoardSpec(None, s, raw)


def _workplace(text: str, flag: bool | None = None) -> str:
    t = (text or "").lower()
    if flag or "remote" in t or "télétravail" in t or "teletravail" in t:
        return "hybrid" if "hybrid" in t else "remote"
    if "hybrid" in t or "hybride" in t:
        return "hybrid"
    return "onsite" if t.strip() else "unknown"


def _nice_company(slug: str) -> str:
    return re.sub(r"[-_.]+", " ", slug).strip().title()


def fetch_greenhouse(token: str) -> list[Job]:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {"content": "true"}, allow_404=True)
    if not data:
        return []
    board = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}", allow_404=True) or {}
    company = board.get("name") or _nice_company(token)
    jobs = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        desc = html_to_text(j.get("content", ""))
        jobs.append(
            Job(
                id=f"greenhouse:{token}:{j.get('id')}",
                source="greenhouse",
                source_label="Greenhouse",
                company=company,
                title=(j.get("title") or "").strip(),
                location=loc,
                workplace=_workplace(loc),
                url=j.get("absolute_url") or "",
                posted_at=j.get("first_published") or j.get("updated_at"),
                description=desc,
                tags=[d.get("name", "") for d in j.get("departments", []) if d.get("name")],
                attribution=f"{company} careers (Greenhouse)",
            )
        )
    return jobs


def _lever_description(p: dict) -> str:
    parts = [p.get("descriptionPlain") or html_to_text(p.get("description", ""))]
    for lst in p.get("lists", []) or []:
        title = (lst.get("text") or "").strip()
        body = html_to_text(lst.get("content", ""))
        parts.append(f"{title}\n{body}" if title else body)
    if p.get("additionalPlain"):
        parts.append(p["additionalPlain"])
    return clean_text("\n\n".join(x for x in parts if x))


def fetch_lever(site: str) -> list[Job]:
    data = None
    for host in ("https://api.lever.co", "https://api.eu.lever.co"):
        data = get_json(f"{host}/v0/postings/{site}", {"mode": "json"}, allow_404=True)
        if data:
            break
    if not data or not isinstance(data, list):
        return []
    jobs = []
    for p in data:
        cats = p.get("categories") or {}
        loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        wp = (p.get("workplaceType") or "").replace("on-site", "onsite")
        jobs.append(
            Job(
                id=f"lever:{site}:{p.get('id')}",
                source="lever",
                source_label="Lever",
                company=_nice_company(site),
                title=(p.get("text") or "").strip(),
                location=loc or "",
                workplace=wp if wp in {"remote", "hybrid", "onsite"} else _workplace(loc),
                url=p.get("hostedUrl") or "",
                posted_at=str(p.get("createdAt")) if p.get("createdAt") else None,
                description=_lever_description(p),
                tags=[t for t in (cats.get("team"), cats.get("department"), cats.get("commitment")) if t],
                attribution=f"{_nice_company(site)} careers (Lever)",
            )
        )
    return jobs


def fetch_ashby(name: str) -> list[Job]:
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{name}", {"includeCompensation": "true"}, allow_404=True)
    if not data:
        return []
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        wp = (j.get("workplaceType") or "").lower().replace("onsite", "onsite")
        loc = j.get("location") or ""
        url = j.get("jobUrl") or ""
        jid = j.get("id") or url.rstrip("/").split("/")[-1]
        jobs.append(
            Job(
                id=f"ashby:{name}:{jid}",
                source="ashby",
                source_label="Ashby",
                company=_nice_company(name),
                title=(j.get("title") or "").strip(),
                location=loc,
                workplace=wp if wp in {"remote", "hybrid", "onsite"} else _workplace(loc, j.get("isRemote")),
                url=url,
                posted_at=j.get("publishedAt"),
                description=j.get("descriptionPlain") and clean_text(j["descriptionPlain"]) or html_to_text(j.get("descriptionHtml", "")),
                tags=[t for t in (j.get("department"), j.get("team"), j.get("employmentType")) if t],
                attribution=f"{_nice_company(name)} careers (Ashby)",
            )
        )
    return jobs


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def fetch_board(raw: str) -> tuple[str, list[Job]]:
    """Fetch one company board. Returns (description for the log, jobs)."""
    spec = parse_board_spec(raw)
    if not SLUG_RE.match(spec.slug):
        raise SourceError(f"'{raw}' is not a valid board name.")
    order = [spec.ats] if spec.ats else ["greenhouse", "lever", "ashby"]
    for ats in order:
        jobs = FETCHERS[ats](spec.slug)
        if jobs:
            return f"{spec.slug} via {ats.title()}", jobs
    tried = ", ".join(a.title() for a in order)
    raise SourceError(f"No open jobs found for '{spec.slug}' on {tried}.")
