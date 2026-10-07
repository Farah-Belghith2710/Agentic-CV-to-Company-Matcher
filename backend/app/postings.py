"""Understanding the layout of a job posting: which lines are requirements, nice-to-haves,
duties, or boilerplate (benefits, company intro, legal)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .text import fold, strip_bullet

JOB_HEADERS: dict[str, list[str]] = {
    "must": [
        "requirements", "required", "required skills", "required qualifications", "minimum qualifications",
        "basic qualifications", "qualifications", "what you bring", "what we're looking for", "what we are looking for",
        "who you are", "your profile", "about you", "you have", "you should have", "must have", "must-have",
        "must haves", "skills and experience", "skills & experience", "experience", "key requirements",
        "profil recherche", "votre profil", "profil", "competences requises", "prerequis", "exigences",
        "ce que nous recherchons", "qualifications requises", "vous avez", "anforderungen", "ihr profil",
        "dein profil", "was du mitbringst", "das bringst du mit", "was sie mitbringen", "technical skills",
    ],
    "nice": [
        "nice to have", "nice-to-have", "nice to haves", "bonus", "bonus points", "preferred qualifications",
        "preferred", "pluses", "a plus", "it's a plus", "would be great", "extra credit", "good to have",
        "un plus", "atouts", "serait un plus", "souhaite", "souhaitable", "idealement", "competences appreciees",
        "wunschenswert", "von vorteil", "plus",
    ],
    "duties": [
        "responsibilities", "what you'll do", "what you will do", "the role", "your role", "role", "your mission",
        "missions", "vos missions", "mission", "taches", "vos responsabilites", "responsabilites", "in this role",
        "day to day", "deine aufgaben", "ihre aufgaben", "aufgaben", "what you will work on", "key responsibilities",
    ],
    "skip": [
        "benefits", "what we offer", "we offer", "perks", "perks and benefits", "why join us", "why us",
        "compensation", "salary", "avantages", "nous offrons", "ce que nous offrons", "pourquoi nous rejoindre",
        "about us", "about the company", "who we are", "our company", "qui sommes-nous", "qui sommes nous",
        "a propos", "wir bieten", "uber uns", "equal opportunity", "diversity", "how to apply", "application process",
        "recruitment process", "processus de recrutement", "location", "the company", "l'entreprise", "entreprise",
    ],
}
_LOOKUP = {h: k for k, hs in JOB_HEADERS.items() for h in hs}

NICE_CUE = re.compile(
    r"\b(nice to have|a plus|is a plus|bonus|preferred|preferably|ideally|advantage|is an asset|desirable|"
    r"un plus|un atout|serait apprecie|apprecie|souhaite|souhaitable|idealement|von vorteil|wunschenswert)\b"
)
MUST_CUE = re.compile(
    r"\b(required|must|mandatory|essential|minimum|at least|obligatoire|exige|indispensable|requis|imperatif|zwingend)\b"
)
SKIP_LINE = re.compile(r"\b(equal opportunity|we are an equal|accommodation|visa sponsorship|salary range|benefits include)\b")


@dataclass
class PostingLine:
    section: str  # must | nice | duties | skip | intro
    text: str
    is_bullet: bool


def header_kind(line: str) -> str | None:
    s = line.strip().strip("#*_=—-•").strip()
    if not s or len(s) > 70 or s.endswith(".") or re.search(r":\s*\S", s):
        return None
    s = s.rstrip(":").strip()
    f = re.sub(r"\s+", " ", fold(s)).strip(" :!?")
    if f in _LOOKUP:
        return _LOOKUP[f]
    for h, kind in _LOOKUP.items():
        if len(h) > 5 and f.startswith(h) and len(f.split()) <= 7:
            return kind
    return None


def split_posting(description: str) -> list[PostingLine]:
    out: list[PostingLine] = []
    section = "intro"
    for raw in description.split("\n"):
        if not raw.strip():
            continue
        kind = header_kind(raw)
        if kind:
            section = kind
            continue
        is_b, content = strip_bullet(raw)
        if not content:
            continue
        out.append(PostingLine(section, content, is_b))
    return out


def requirement_lines(description: str) -> list[tuple[str, str]]:
    """(kind, text) candidates for requirements. kind is must or nice."""
    lines = split_posting(description)
    has_req_section = any(pl.section in ("must", "nice") for pl in lines)
    out: list[tuple[str, str]] = []
    for pl in lines:
        f = fold(pl.text)
        if SKIP_LINE.search(f):
            continue
        if pl.section in ("must", "nice"):
            kind = pl.section
            if kind == "must" and NICE_CUE.search(re.sub(r"\([^)]*\)", " ", f)):
                kind = "nice"
            out.append((kind, pl.text))
        elif not has_req_section and pl.section in ("intro", "duties"):
            if re.search(r"\b(experience|knowledge|proficien|familiar|degree|skills?|years?|fluent|ability|"
                         r"experience|maitrise|connaissance|diplome|ans d'experience|bac\s*\+)", f):
                kind = "nice" if NICE_CUE.search(f) else "must"
                out.append((kind, pl.text))
    return out


def content_chunks(description: str, limit: int = 18) -> list[str]:
    """Lines that describe the work and the profile (used for retrieval), skipping boilerplate."""
    lines = split_posting(description)
    ranked = [pl for pl in lines if pl.section in ("must", "nice")] + [pl for pl in lines if pl.section == "duties"]
    ranked += [pl for pl in lines if pl.section == "intro" and len(pl.text.split()) >= 5]
    chunks = []
    for pl in ranked:
        if len(pl.text) >= 12 and not SKIP_LINE.search(fold(pl.text)):
            chunks.append(pl.text[:300])
        if len(chunks) >= limit:
            break
    return chunks or [description[:300]]
