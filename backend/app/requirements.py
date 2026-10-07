"""Turn a job posting into a list of requirements tagged must-have / nice-to-have."""
from __future__ import annotations

import re

from .cache import cache, make_key
from .llm import LLMClient
from .postings import requirement_lines
from .schemas import Job, JobRequirements, LLMRequirements, Requirement
from .skills import canonical, find_languages, find_skills
from .text import fold, guess_language, truncate

MAX_REQS = 14
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:(?:-|to|a|bis)\s*\d{1,2}\s*)?(?:years?|yrs|ans|annees|jahre)")
DEGREE_RE = re.compile(
    r"\b(degree|bachelor'?s?|master'?s?|msc|bsc|phd|engineering school|diplomee?s?|ingenieurs?|licence|bac\s*\+\s*\d|"
    r"grande ecole|studium|abschluss|graduate in|graduated|student|etudiante?s?|final[- ]year|derniere annee|"
    r"fin d'etudes|laufendes|vocational|bts)\b"
)
STUDENT_REQ_RE = re.compile(
    r"\b(student|etudiante?s?|final[- ]year|derniere annee|fin d'etudes|laufendes studium|enrolled|currently studying)\b"
)
SOFT_RE = re.compile(
    r"\b(team player|communication skills|communicat|autonom|proactive|curious|curiosity|motivated|passion|"
    r"rigueur|rigoureu|esprit d'equipe|sens de|organized|organised|detail[- ]oriented|self[- ]starter|"
    r"ownership|growth mindset|interpersonal|teamwork|travail en equipe|dynamique|adaptab|explain|"
    r"stakeholder|present findings)"
)
LANG_REQ_RE = re.compile(r"\b(fluent|fluency|speak|spoken|written|proficien|native|langue|language|maitrise|courant|bilingu|niveau|level|c1|c2|b2)\b")

SENIORITY_PATTERNS = [
    ("intern", r"\b(intern|internship|stagiaire|stage|pfe|apprentice|apprenticeship|alternance|alternant|werkstudent|praktikum|trainee)\b"),
    ("lead", r"\b(lead|principal|staff|head of|manager|chef|director|directeur|responsable)\b"),
    ("senior", r"\b(senior|sr|confirme|experimente|expert)\b"),
    ("junior", r"\b(junior|jr|graduate|entry[- ]level|debutant|jeune diplome|new grad)\b"),
]


def title_seniority(title: str, min_years: float | None) -> str:
    f = fold(title)
    for level, pat in SENIORITY_PATTERNS:
        if re.search(pat, f):
            return level
    if min_years is not None:
        if min_years >= 6:
            return "senior"
        if min_years >= 3:
            return "mid"
        return "junior"
    return "unspecified"


def _ordered_skills(text: str) -> list[str]:
    seen: list[str] = []
    for h in find_skills(text):
        if h.skill not in seen:
            seen.append(h.skill)
    return seen


def _categorize(text: str, skills: list[str], langs: list[str], years: float | None) -> str:
    f = fold(text)
    if years is not None:
        return "experience"
    if langs and not skills:
        return "language"
    if (DEGREE_RE.search(f) or STUDENT_REQ_RE.search(f)) and not skills:
        return "education"
    if "certif" in f and not skills:
        return "certification"
    if skills:
        return "skill"
    return "domain"


def extract_heuristic(job: Job) -> JobRequirements:
    reqs: list[Requirement] = []
    seen: set[str] = set()
    for kind, text in requirement_lines(job.description):
        f = fold(text)
        key = re.sub(r"\W+", " ", f).strip()[:90]
        skills = _ordered_skills(text)
        if key in seen or len(text) < 3 or (len(text) < 8 and not skills and not find_languages(text)):
            continue
        seen.add(key)
        langs = list(find_languages(text)) if LANG_REQ_RE.search(f) or len(text.split()) <= 6 else []
        m = YEARS_RE.search(f)
        years = float(m.group(1)) if m else None
        if not skills and not langs and years is None and not DEGREE_RE.search(f) and SOFT_RE.search(f):
            continue  # pure soft skill: not scored
        reqs.append(
            Requirement(
                id="",
                text=truncate(text, 220),
                kind=kind,  # type: ignore[arg-type]
                category=_categorize(text, skills, langs, years),
                skills=skills,
                min_years=years,
                languages=langs,
            )
        )
    reqs = _prioritize(reqs)
    min_years = max((r.min_years for r in reqs if r.min_years is not None and r.kind == "must"), default=None)
    return JobRequirements(
        requirements=reqs,
        seniority=title_seniority(job.title, min_years),
        min_years=min_years,
        languages=sorted({l for r in reqs for l in r.languages}),
        workplace=job.workplace,
        posting_language=guess_language(job.description),
        source="heuristic",
    )


def _prioritize(reqs: list[Requirement]) -> list[Requirement]:
    must = [r for r in reqs if r.kind == "must"]
    nice = [r for r in reqs if r.kind == "nice"]
    keep = (must[:10] + nice)[:MAX_REQS]
    keep.sort(key=lambda r: reqs.index(r))
    for i, r in enumerate(keep, start=1):
        r.id = f"R{i}"
    return keep


SYSTEM = """You extract hiring requirements from job postings.
Rules:
- Return at most 12 concrete requirements: skills, tools, methods, domain experience, years of experience, education, languages, certifications.
- Skip benefits, company description, legal text and pure soft skills (e.g. "team player").
- kind = "must" when the posting presents it as required/minimum/essential (or in a requirements section without qualifier);
  kind = "nice" when it says preferred, bonus, plus, nice to have, ideally, asset, un plus, souhaité.
- Keep each requirement short (max 15 words) and in the posting's own wording and language.
- "skills" lists the tool/skill/method names inside that requirement, exactly as written.
- Never invent requirements that are not in the posting."""


def extract_llm(job: Job, llm: LLMClient) -> JobRequirements:
    user = (
        f"Job title: {job.title}\nCompany: {job.company}\nLocation: {job.location} ({job.workplace})\n\n"
        f"Posting:\n{job.description[:7000]}"
    )
    out = llm.complete_json("requirements", SYSTEM, user, LLMRequirements)
    reqs: list[Requirement] = []
    for r in out.requirements[:MAX_REQS]:
        text = truncate(r.text.strip(), 220)
        if not text:
            continue
        names: list[str] = []
        for s in list(r.skills) + _ordered_skills(text):
            c = canonical(s) or s.strip()
            if c and c not in names:
                names.append(c)
        f = fold(text)
        m = YEARS_RE.search(f)
        langs = list(find_languages(text)) if r.category == "language" or LANG_REQ_RE.search(f) else []
        reqs.append(
            Requirement(
                id="",
                text=text,
                kind=r.kind,
                category=r.category if r.category in {"skill", "experience", "education", "language", "certification", "domain"} else "skill",
                skills=names,
                min_years=float(m.group(1)) if m else None,
                languages=langs,
            )
        )
    reqs = _prioritize(reqs)
    min_years = out.min_years if out.min_years is not None else max(
        (r.min_years for r in reqs if r.min_years is not None and r.kind == "must"), default=None
    )
    seniority = out.seniority if out.seniority in {"intern", "junior", "mid", "senior", "lead"} else title_seniority(job.title, min_years)
    workplace = out.workplace if out.workplace in {"remote", "hybrid", "onsite"} else job.workplace
    return JobRequirements(
        requirements=reqs,
        seniority=seniority,
        min_years=min_years,
        languages=sorted({canonical_language(l) for l in out.languages} | {l for r in reqs for l in r.languages}),
        workplace=workplace,
        posting_language=guess_language(job.description),
        source="llm",
    )


def canonical_language(name: str) -> str:
    found = list(find_languages(name))
    return found[0] if found else name.strip().title()


def extract(job: Job, llm: LLMClient | None) -> tuple[JobRequirements, str | None]:
    """Returns (requirements, warning). Uses the LLM when available, heuristics otherwise or on failure."""
    if llm is None or not llm.enabled:
        return extract_heuristic(job), None
    key = make_key("reqs-v1", llm.cfg.llm_model, job.title, job.description)
    hit = cache.get("reqs", key)
    if hit:
        return JobRequirements.model_validate(hit), None
    try:
        jr = extract_llm(job, llm)
        if not jr.requirements:
            raise ValueError("no requirements returned")
        cache.set("reqs", key, jr.model_dump())
        return jr, None
    except Exception as exc:
        return extract_heuristic(job), f"LLM extraction failed for '{job.title}' ({exc}); used rules instead."
