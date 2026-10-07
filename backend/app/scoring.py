"""Deterministic scoring: fit score, separate flags (location, language, seniority) and the
"learn next" table. No LLM here, so the same judgments always give the same numbers."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import Flag, Job, JobAnalysis, JobRequirements, Judgment, LearnItem, Profile
from .text import fold

VALUE = {"met": 1.0, "partial": 0.5, "missing": 0.0}
MUST_WEIGHT = 0.75


def coverage(jr: JobRequirements, judgments: list[Judgment]) -> tuple[float, float | None, float | None]:
    by_id = {j.req_id: j for j in judgments}
    must = [VALUE[by_id[r.id].verdict] for r in jr.requirements if r.kind == "must" and r.id in by_id]
    nice = [VALUE[by_id[r.id].verdict] for r in jr.requirements if r.kind == "nice" and r.id in by_id]
    must_cov = sum(must) / len(must) if must else None
    nice_cov = sum(nice) / len(nice) if nice else None
    if must_cov is None and nice_cov is None:
        fit = 0.0
    elif must_cov is None:
        fit = nice_cov or 0.0
    elif nice_cov is None:
        fit = must_cov
    else:
        fit = MUST_WEIGHT * must_cov + (1 - MUST_WEIGHT) * nice_cov
    return round(fit, 4), must_cov, nice_cov


@dataclass
class Preferences:
    location: str = ""
    remote_ok: bool = True


REGIONS = {
    "tunisia": {"tunisia", "tunisie", "africa", "emea", "mena", "north africa", "maghreb"},
    "tunisie": {"tunisia", "tunisie", "africa", "emea", "mena", "north africa", "maghreb"},
    "tunis": {"tunisia", "tunisie", "africa", "emea", "mena", "north africa", "maghreb"},
    "sfax": {"tunisia", "tunisie", "africa", "emea", "mena"},
    "sousse": {"tunisia", "tunisie", "africa", "emea", "mena"},
    "france": {"france", "eu", "europe", "emea", "european union"},
    "paris": {"france", "eu", "europe", "emea"},
    "lyon": {"france", "eu", "europe", "emea"},
    "germany": {"germany", "deutschland", "eu", "europe", "emea", "dach"},
    "berlin": {"germany", "deutschland", "eu", "europe", "emea", "dach"},
    "morocco": {"morocco", "maroc", "africa", "emea", "mena"},
    "canada": {"canada", "north america", "americas"},
    "uk": {"uk", "united kingdom", "europe", "emea"},
    "london": {"uk", "united kingdom", "europe", "emea"},
}
OPEN_WORLD = re.compile(r"\b(worldwide|anywhere|global|international|any location|all locations)\b")
REGION_WORDS = re.compile(
    r"\b(us|usa|u\.s\.|united states|north america|americas|canada|uk|united kingdom|eu|europe|emea|latam|apac|asia|"
    r"germany|france|spain|portugal|netherlands|poland|india|brazil|mexico|africa|mena)\b"
)


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", fold(s)) if len(t) >= 3}


def flags_for(job: Job, jr: JobRequirements, profile: Profile, prefs: Preferences) -> list[Flag]:
    out: list[Flag] = []
    workplace = jr.workplace if jr.workplace != "unknown" else job.workplace
    loc = fold(job.location or "")
    user_loc = fold(prefs.location or profile.location or "")
    user_regions: set[str] = set()
    for key, regs in REGIONS.items():
        if key in user_loc:
            user_regions |= regs | {key}
    if workplace == "remote":
        regions = set(REGION_WORDS.findall(loc))
        if regions and not OPEN_WORLD.search(loc) and user_regions and not (regions & user_regions):
            out.append(Flag(kind="location", message=f"Remote, but limited to {job.location}"))
    elif user_loc and loc:
        if not (_tokens(user_loc) & _tokens(loc)) and not (user_regions & _tokens(loc)):
            what = "Hybrid" if workplace == "hybrid" else "On-site"
            out.append(Flag(kind="location", message=f"{what} in {job.location}"))

    levels = {l.name: l.level for l in profile.languages}
    for lang in jr.languages:
        if levels.get(lang, 0) < 3:
            out.append(Flag(kind="language", message=f"Asks for {lang}"))
    implicit = {"de": "German", "fr": "French"}.get(jr.posting_language)
    if implicit and levels.get(implicit, 0) < 3 and implicit not in jr.languages:
        out.append(Flag(kind="language", message=f"Posting is written in {implicit}"))

    order = {"student": 0, "intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4}
    cand = order.get(profile.seniority, 1)
    need = order.get(jr.seniority)
    if need is not None and need - cand >= 2:
        out.append(Flag(kind="seniority", message=f"{jr.seniority.title()}-level role; your CV reads {profile.seniority}"))
    elif jr.min_years and jr.min_years > profile.years_experience + 1.5:
        have = "less than a year" if profile.years_experience < 0.5 else f"about {profile.years_experience:g}"
        out.append(Flag(kind="seniority", message=f"Asks {jr.min_years:g}+ years; your CV shows {have}"))
    elif jr.seniority == "intern" and cand >= 2:
        out.append(Flag(kind="seniority", message="Internship; your CV reads more experienced"))
    return out


def _simulate(jr: JobRequirements, judgments: list[Judgment], skill: str) -> list[Judgment]:
    """Judgments as they would be if the candidate learned `skill`."""
    new = []
    for j in judgments:
        if skill in j.missing_skills:
            rest = [s for s in j.missing_skills if s != skill]
            verdict = "met" if not rest else ("partial" if j.verdict == "missing" else j.verdict)
            new.append(j.model_copy(update={"verdict": verdict, "missing_skills": rest}))
        else:
            new.append(j)
    return new


def learn_next(analyses: list[JobAnalysis], limit: int = 12) -> list[LearnItem]:
    skills: dict[str, dict] = {}
    for a in analyses:
        kinds = {r.id: r.kind for r in a.requirements.requirements}
        for j in a.judgments:
            if j.verdict == "met":
                continue
            for s in j.missing_skills:
                st = skills.setdefault(s, {"jobs": set(), "must": set()})
                st["jobs"].add(a.job_id)
                if kinds.get(j.req_id) == "must":
                    st["must"].add(a.job_id)
    items: list[LearnItem] = []
    for s, st in skills.items():
        gain, unlocks = 0.0, 0
        for a in analyses:
            if a.job_id not in st["jobs"]:
                continue
            sim = _simulate(a.requirements, a.judgments, s)
            fit, must_cov, _ = coverage(a.requirements, sim)
            gain += max(0.0, fit - a.fit)
            if a.must_coverage is not None and a.must_coverage < 1.0 and must_cov == 1.0:
                unlocks += 1
        n = len(st["jobs"])
        items.append(
            LearnItem(
                skill=s,
                jobs_requiring=n,
                must_count=len(st["must"]),
                unlocks=unlocks,
                fit_gain=round(gain / n, 4) if n else 0.0,
                job_ids=sorted(st["jobs"]),
            )
        )
    items.sort(key=lambda x: (-x.unlocks, -x.must_count, -x.jobs_requiring, -x.fit_gain, x.skill))
    return items[:limit]
