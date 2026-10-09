"""Local job sources: the bundled demo snapshot (or your own saved snapshot) and pasted postings."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from ..config import settings
from ..schemas import Job
from ..text import clean_text
from .linkedin import looks_like_linkedin, parse_linkedin_text


def load_snapshot(path: Path | None = None) -> list[Job]:
    p = path or settings.snapshot_path
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data["jobs"] if isinstance(data, dict) else data
    return [Job.model_validate(j) for j in items]


def save_snapshot(jobs: list[Job], path: Path, note: str = "") -> None:
    payload = {"note": note, "jobs": [j.model_dump() for j in jobs]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_pasted(text: str) -> list[Job]:
    """One or more postings pasted by the user, separated by a line containing only '---'.

    Optional first lines 'Title: ...', 'Company: ...', 'Location: ...', 'URL: ...' are picked up;
    otherwise the first line is used as the title. A whole LinkedIn job page copied with Ctrl+A is
    recognised: its menus and buttons are dropped and the title, company and location are read from it.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*-{3,}\s*\n", clean_text(text)) if b.strip()]
    jobs = []
    for i, block in enumerate(blocks[:10], start=1):
        meta: dict[str, str] = {}
        lines = block.split("\n")
        body_start = 0
        for idx, ln in enumerate(lines[:6]):
            m = re.match(r"^(title|company|location|url|poste|entreprise|lieu)\s*:\s*(.+)$", ln.strip(), flags=re.I)
            if m:
                key = {"poste": "title", "entreprise": "company", "lieu": "location"}.get(m.group(1).lower(), m.group(1).lower())
                meta[key] = m.group(2).strip()
                body_start = idx + 1
        body = "\n".join(lines[body_start:]).strip() or block
        title = meta.get("title") or lines[0].strip()[:90]
        loc = meta.get("location", "")
        low = f"{loc} {body[:600]}".lower()
        workplace = "remote" if ("remote" in low or "télétravail" in low) else ("hybrid" if "hybrid" in low else "unknown")
        if looks_like_linkedin(block):
            li = parse_linkedin_text(block)
            if len(li.description) >= 80:
                body = li.description
                title = meta.get("title") or li.title[:120] or title
                if li.company and "company" not in meta:
                    meta["company"] = li.company
                loc = meta.get("location") or li.location
                workplace = li.workplace if li.workplace != "unknown" else workplace
        digest = hashlib.sha1(block.encode("utf-8")).hexdigest()[:10]
        jobs.append(
            Job(
                id=f"pasted:{digest}",
                source="pasted",
                source_label="Pasted posting",
                company=meta.get("company", f"Pasted posting {i}"),
                title=title,
                location=loc,
                workplace=workplace,
                url=meta.get("url", ""),
                description=body,
                attribution="Pasted by you",
            )
        )
    return jobs
