"""The agent: a LangGraph state machine with two self-correction loops and a human checkpoint.

  parse_cv -> plan_queries -> fetch_jobs -> triage --(too few relevant)--> refine_queries -> fetch_jobs ...
                                              \\--(enough)--> shortlist -> extract_requirements
  -> judge_evidence -> score_rank -> pick_jobs (interrupt: you choose 1-3 jobs)
  -> rewrite -> verify --(a draft was rejected)--> rewrite ...
                      \\--(all verified or out of attempts)--> report

Every node streams log lines (LangGraph "custom" stream) that the UI shows live.
"""
from __future__ import annotations

import functools
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import judge as judge_mod
from . import requirements as req_mod
from .config import settings
from .cv_parser import heuristic_profile, redact, segment
from .llm import LLMClient, LLMError
from .report import build_report
from .retrieval import get_similarity, shortlist as rank_shortlist, similarity_status, triage as triage_jobs
from .roles import ROLE_FAMILIES, family_scores
from .schemas import (
    Draft,
    EvidenceUnit,
    Job,
    JobAnalysis,
    JobRequirements,
    Judgment,
    LanguageSkill,
    LearnItem,
    LLMProfile,
    LLMQueries,
    Profile,
    TailoredBullet,
)
from .scoring import Preferences, coverage, flags_for, learn_next
from .skills import canonical, find_languages
from . import saved as saved_jobs
from .sources import SourceError, fetch_arbeitnow, fetch_board, fetch_remotive, load_snapshot, parse_pasted

# Postings you picked yourself (pasted, or saved from LinkedIn): no search, no triage, all analysed.
USER_SOURCES = {"paste", "linkedin"}
USER_SOURCE_CAP = 30
from .tailor import heuristic_draft, llm_draft, pick_bullets, verify as verify_bullet
from .text import truncate


class PipelineError(RuntimeError):
    """An error the user can act on (shown as-is in the UI)."""


class MatchState(TypedDict, total=False):
    run_id: str
    cv_text: str
    options: dict
    redaction: dict
    profile: dict
    units: list[dict]
    queries: list[str]
    query_log: list[dict]
    refine_round: int
    pool: list[dict]
    fetched_queries: list[str]
    relevant: list[str]
    triage_reasons: dict
    rejected_titles: list[str]
    shortlist: list[dict]
    similarity: str
    requirements: dict
    judgments: dict
    analyses: list[dict]
    learn_next: list[dict]
    selected: list[str]
    tailored: list[dict]
    tailor_round: int
    report_md: str
    warnings: list[str]


@dataclass
class RunContext:
    """Per-run objects that must not live in the checkpointed state."""

    llm: LLMClient | None
    prefs: Preferences = field(default_factory=Preferences)

    @property
    def use_llm(self) -> bool:
        return self.llm is not None and self.llm.enabled


def _ctx(config: RunnableConfig) -> RunContext:
    return config["configurable"]["ctx"]


class NodeLog:
    def __init__(self, node: str) -> None:
        self.node = node
        try:
            self._write = get_stream_writer()
        except Exception:
            self._write = lambda _chunk: None

    def __call__(self, message: str, level: str = "info", **data: Any) -> None:
        self._write({"type": "log", "node": self.node, "level": level, "message": message, "data": data, "ts": time.time()})

    def event(self, **payload: Any) -> None:
        self._write({"node": self.node, "ts": time.time(), **payload})


def node(name: str) -> Callable:
    """Decorator: emits stage start/done events around a node."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: MatchState, config: RunnableConfig):
            log = NodeLog(name)
            log.event(type="stage", status="start")
            t0 = time.time()
            out = fn(state, config, log)
            log.event(type="stage", status="done", ms=int((time.time() - t0) * 1000))
            return out

        return wrapper

    return deco


def _jobs(state: MatchState) -> dict[str, Job]:
    return {j["id"]: Job.model_validate(j) for j in state.get("pool", [])}


def _profile(state: MatchState) -> Profile:
    return Profile.model_validate(state["profile"])


def _units(state: MatchState) -> list[EvidenceUnit]:
    return [EvidenceUnit.model_validate(u) for u in state.get("units", [])]


def _parallel(items: list, fn: Callable, workers: int):
    """Run fn(item) in a thread pool; yields (item, result_or_exception) as they finish."""
    if workers <= 1:
        for it in items:
            try:
                yield it, fn(it)
            except Exception as exc:  # surfaced by the caller
                yield it, exc
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fn, it): it for it in items}
        for f in as_completed(futs):
            try:
                yield futs[f], f.result()
            except Exception as exc:
                yield futs[f], exc


# --- Nodes --------------------------------------------------------------------------------
PROFILE_SYSTEM = """You read a CV (contact details are redacted) and return a structured profile.
Only use facts written in the CV. Skills: list tools, technologies and methods as written.
years_experience counts professional work only (exclude internships and studies).
target_titles: 3-5 realistic job titles for this person's next role."""


@node("parse_cv")
def parse_cv(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    text = state["cv_text"]
    redacted, counts = redact(text)
    removed = [f"{v} {k}{'s' if v > 1 else ''}" for k, v in counts.items() if v]
    log(f"Read {len(text):,} characters. Redacted before any processing: {', '.join(removed) or 'nothing found'}.")
    units, sections, header = segment(redacted)
    if len(units) < 2:
        raise PipelineError("Could not find any experience, project or skills lines in this CV. Try pasting the text.")
    kinds: dict[str, int] = {}
    for u in units:
        kinds[u.section] = kinds.get(u.section, 0) + 1
    log(f"Split the CV into {len(units)} evidence lines: " + ", ".join(f"{n} {k}" for k, n in kinds.items()) + ".")
    profile = heuristic_profile(redacted, units, sections, header)
    if ctx.use_llm:
        try:
            lp = ctx.llm.complete_json("profile", PROFILE_SYSTEM, redacted[:12000], LLMProfile)
            profile = _merge_profile(profile, lp)
            log("Profile enriched by the LLM (titles, domains, seniority).")
        except LLMError as exc:
            log(f"LLM profile step failed ({exc}); keeping the rule-based profile.", "warn")
    log(
        f"Profile: {profile.seniority}, ~{profile.years_experience:g} years professional"
        + (f" + {profile.internship_months} months of internships" if profile.internship_months else "")
        + f", {len(profile.skills)} skills ({', '.join(profile.skills[:6])}{'...' if len(profile.skills) > 6 else ''})."
    )
    return {
        "redaction": counts,
        "profile": profile.model_dump(),
        "units": [u.model_dump() for u in units],
        "warnings": [],
    }


def _merge_profile(p: Profile, lp: LLMProfile) -> Profile:
    skills = list(p.skills)
    for s in lp.skills:
        c = canonical(s) or s.strip()
        if c and c not in skills:
            skills.append(c)
    level_words = {"native": 5, "fluent": 4, "advanced": 4, "intermediate": 3, "basic": 1}
    langs = {l.name: l.level for l in p.languages}
    for l in lp.languages:
        found = list(find_languages(l.name))
        name = found[0] if found else l.name.strip().title()
        langs[name] = max(langs.get(name, 0), level_words.get(l.level.lower().strip(), 3))
    has_dates = p.years_experience > 0 or p.internship_months > 0
    return p.model_copy(
        update={
            "headline": lp.headline or p.headline,
            "target_titles": [t for t in lp.target_titles if t.strip()][:5] or p.target_titles,
            "skills": skills,
            "domains": lp.domains[:4] or p.domains,
            "years_experience": p.years_experience if has_dates else float(lp.years_experience or 0),
            "seniority": lp.seniority if lp.seniority in {"student", "junior", "mid", "senior", "lead"} else p.seniority,
            "languages": [LanguageSkill(name=k, level=v) for k, v in sorted(langs.items(), key=lambda x: -x[1])],
            "location": p.location or lp.location,
            "source": "llm",
        }
    )


QUERY_SYSTEM = """You plan job searches for a candidate. Propose 3-5 short queries (1-4 words: job titles or
specialties) that would surface openings this candidate is qualified for. Prefer job titles over single tools.
If the candidate's CV is in French or they live in a French-speaking country, include one French title."""


@node("plan_queries")
def plan_queries(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    opts = state["options"]
    if opts["source"] in USER_SOURCES:
        if opts["source"] == "linkedin":
            log("You picked these jobs on LinkedIn yourself, so there is nothing to search for.")
        else:
            log("You pasted the posting(s) yourself, so there is nothing to search for.")
        return {"queries": [], "query_log": [], "refine_round": 0}
    profile = _profile(state)
    extra = [k.strip() for k in opts.get("keywords", "").split(",") if k.strip()]
    # Start narrow (your strongest domain), broaden later only if too few postings are relevant.
    fams = [(f, sc) for f, sc in family_scores(profile.skills, profile.headline).most_common(2) if sc > 0]
    titles: list[str] = []
    for i, (f, sc) in enumerate(fams):
        if i == 0 or sc >= 0.6 * fams[0][1]:
            titles += ROLE_FAMILIES[f]["titles"]
    queries = list(dict.fromkeys(extra + (titles or profile.target_titles)))[:5]
    rationale = "your strongest domain first, from the skills and titles in your CV"
    if ctx.use_llm:
        try:
            summary = (
                f"Headline: {profile.headline}\nSeniority: {profile.seniority}\nDomains: {', '.join(profile.domains)}\n"
                f"Skills: {', '.join(profile.skills[:30])}\nLocation: {ctx.prefs.location or profile.location}\n"
                f"CV language: {profile.cv_language}"
            )
            out = ctx.llm.complete_json("plan", QUERY_SYSTEM, summary, LLMQueries)
            queries = list(dict.fromkeys(extra + [q.strip() for q in out.queries if q.strip()]))[:5] or queries
            rationale = out.rationale or rationale
        except LLMError as exc:
            log(f"LLM planning failed ({exc}); using titles from the CV.", "warn")
    log(f"Search plan: {', '.join(queries)} ({rationale}).", queries=queries)
    return {"queries": queries, "query_log": [{"round": 0, "queries": queries, "rationale": rationale}], "refine_round": 0}


@node("fetch_jobs")
def fetch_jobs(state: MatchState, config: RunnableConfig, log: NodeLog):
    opts = state["options"]
    source = opts["source"]
    pool = {j["id"]: j for j in state.get("pool", [])}
    fetched = list(state.get("fetched_queries", []))
    warnings = list(state.get("warnings", []))
    if source == "demo":
        if not pool:
            jobs = load_snapshot()
            pool = {j.id: j.model_dump() for j in jobs}
            log(f"Loaded {len(jobs)} postings from the snapshot ({settings.snapshot_path.name}).")
        else:
            log(f"Re-using the {len(pool)} snapshot postings with the new queries.")
    elif source == "paste":
        jobs = parse_pasted(opts.get("pasted", ""))
        pool = {j.id: j.model_dump() for j in jobs}
        log(f"Read {len(jobs)} pasted posting{'s' if len(jobs) != 1 else ''}.")
    elif source == "linkedin":
        jobs = saved_jobs.load_jobs()[:USER_SOURCE_CAP]
        pool = {j.id: j.model_dump() for j in jobs}
        log(f"Loaded {len(jobs)} job{'s' if len(jobs) != 1 else ''} you saved from LinkedIn.")
    elif source == "companies":
        if not pool:
            specs = [c.strip() for c in opts.get("companies", "").replace("\n", ",").split(",") if c.strip()][:15]
            for spec in specs:
                try:
                    desc, jobs = fetch_board(spec)
                    for j in jobs:
                        pool[j.id] = j.model_dump()
                    log(f"{desc}: {len(jobs)} open postings.")
                except SourceError as exc:
                    log(str(exc), "warn")
                    warnings.append(str(exc))
        else:
            log(f"Re-using the {len(pool)} postings already fetched from company boards.")
    elif source == "keywords":
        new_q = [q for q in state.get("queries", []) if q not in fetched][:2]
        if not new_q and not pool:
            new_q = state.get("queries", [])[:1]
        for q in new_q:
            try:
                jobs = fetch_remotive(q)
                for j in jobs:
                    pool[j.id] = j.model_dump()
                log(f"Remotive: {len(jobs)} remote postings for '{q}' (cached for 6 hours; Remotive allows 2 requests a minute).")
            except SourceError as exc:
                log(f"Remotive: {exc}", "warn")
                warnings.append(str(exc))
            fetched.append(q)
        if opts.get("include_arbeitnow", True) and not any(j["source"] == "arbeitnow" for j in pool.values()):
            try:
                jobs = fetch_arbeitnow(pages=2)
                for j in jobs:
                    pool[j.id] = j.model_dump()
                log(f"Arbeitnow: {len(jobs)} recent postings (mostly Europe).")
            except SourceError as exc:
                log(f"Arbeitnow: {exc}", "warn")
                warnings.append(str(exc))
    if not pool and source == "linkedin":
        raise PipelineError("You have no saved LinkedIn jobs. Open a job on LinkedIn and click the Send to CV Matcher button first.")
    if not pool:
        raise PipelineError(
            "No job postings could be loaded. Check the company names or your internet connection, or try the demo snapshot or a pasted posting."
        )
    return {"pool": list(pool.values()), "fetched_queries": fetched, "warnings": warnings}


def _min_relevant(pool_size: int) -> int:
    """How many relevant postings we want before shortlisting (enough to fill the shortlist)."""
    return max(1, min(settings.min_relevant, pool_size))


@node("triage")
def triage(state: MatchState, config: RunnableConfig, log: NodeLog):
    jobs = [Job.model_validate(j) for j in state["pool"]]
    if state["options"]["source"] in USER_SOURCES:
        ids = [j.id for j in jobs]
        if state["options"]["source"] == "linkedin":
            log(f"All {len(ids)} job(s) you saved from LinkedIn go straight to analysis.")
            reason = "saved by you from LinkedIn"
        else:
            log(f"All {len(ids)} pasted posting(s) go straight to analysis.")
            reason = "pasted by you"
        return {"relevant": ids, "triage_reasons": {i: reason for i in ids}, "rejected_titles": []}
    res = triage_jobs(jobs, state.get("queries", []), _profile(state))
    by_title = sum(1 for r in res.reasons.values() if r.startswith("title"))
    need = _min_relevant(len(jobs))
    level = "info" if len(res.relevant) >= need else "warn"
    log(
        f"{len(res.relevant)} of {len(jobs)} postings look relevant ({by_title} by title, "
        f"{len(res.relevant) - by_title} by shared skills); target is {need}.",
        level,
        relevant=len(res.relevant),
        total=len(jobs),
    )
    return {"relevant": res.relevant, "triage_reasons": res.reasons, "rejected_titles": res.rejected_titles[:40]}


def route_after_triage(state: MatchState) -> str:
    if state["options"]["source"] in USER_SOURCES:
        return "shortlist"
    need = _min_relevant(len(state.get("pool", [])))
    if len(state.get("relevant", [])) < need and state.get("refine_round", 0) < settings.max_refinements:
        return "refine_queries"
    return "shortlist"


REFINE_SYSTEM = """You improve a job search that returned too few relevant postings. Look at which titles matched and
which were rejected, then propose 3-5 NEW short queries (1-4 words) that are still a fit for the candidate:
synonyms, adjacent titles, French or English variants, or specialties. Do not repeat earlier queries."""


@node("refine_queries")
def refine_queries(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    profile = _profile(state)
    current = list(state.get("queries", []))
    rnd = state.get("refine_round", 0) + 1
    jobs = _jobs(state)
    relevant_titles = [jobs[i].title for i in state.get("relevant", []) if i in jobs][:12]
    rejected = state.get("rejected_titles", [])[:25]
    new: list[str] = []
    rationale = ""
    if ctx.use_llm:
        try:
            user = (
                f"Candidate: {profile.headline}; domains: {', '.join(profile.domains)}; skills: {', '.join(profile.skills[:25])}\n"
                f"Queries so far: {', '.join(current)}\nRelevant titles found: {'; '.join(relevant_titles) or 'none'}\n"
                f"Rejected titles (sample): {'; '.join(rejected) or 'none'}"
            )
            out = ctx.llm.complete_json("refine", REFINE_SYSTEM, user, LLMQueries)
            new = [q.strip() for q in out.queries if q.strip() and q.strip().lower() not in {c.lower() for c in current}]
            rationale = out.rationale
        except LLMError as exc:
            log(f"LLM refinement failed ({exc}); using related titles instead.", "warn")
    if not new:
        fams = [f for f, s in family_scores(profile.skills, profile.headline).most_common(3) if s > 0]
        for f in fams:
            for t in ROLE_FAMILIES[f]["titles"] + ROLE_FAMILIES[f]["synonyms"]:
                if t.lower() not in {c.lower() for c in current} and t not in new:
                    new.append(t)
                if len(new) >= 4 * rnd:
                    break
        new = new[4 * (rnd - 1): 4 * rnd] or new[:4]
        rationale = "related titles and French/English variants for your strongest domains"
    merged = list(dict.fromkeys(current + new))[:12]
    log(
        f"Only {len(state.get('relevant', []))} relevant postings. Round {rnd}: adding "
        + ", ".join(f"'{q}'" for q in new)
        + f" ({rationale}).",
        "warn",
        queries=merged,
    )
    qlog = list(state.get("query_log", [])) + [{"round": rnd, "queries": new, "rationale": rationale}]
    return {"queries": merged, "refine_round": rnd, "query_log": qlog}


@node("shortlist")
def shortlist(state: MatchState, config: RunnableConfig, log: NodeLog):
    jobs = _jobs(state)
    rel = [jobs[i] for i in state.get("relevant", []) if i in jobs]
    if not rel:
        log("No posting passed triage; ranking the whole pool instead.", "warn")
        rel = list(jobs.values())
    size = settings.shortlist_size
    if state["options"]["source"] in USER_SOURCES:
        size = max(size, min(len(rel), USER_SOURCE_CAP))  # you chose these: analyse every one
    ranked = rank_shortlist(rel, _profile(state), _units(state), size, log=log)
    log(
        f"Shortlisted {len(ranked)} of {len(rel)} with BM25 + semantic line matching (reciprocal rank fusion). "
        f"Similarity: {similarity_status()}."
    )
    return {"shortlist": [asdict(r) for r in ranked], "similarity": similarity_status()}


@node("extract_requirements")
def extract_requirements(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    jobs = _jobs(state)
    targets = [jobs[s["job_id"]] for s in state["shortlist"]]
    workers = settings.llm_concurrency if ctx.use_llm else 1
    out: dict[str, dict] = {}
    warnings = list(state.get("warnings", []))
    for job, res in _parallel(targets, lambda j: req_mod.extract(j, ctx.llm if ctx.use_llm else None), workers):
        if isinstance(res, Exception):
            jr, warn = req_mod.extract_heuristic(job), f"Requirement extraction failed for '{job.title}': {res}"
        else:
            jr, warn = res
        if warn:
            log(warn, "warn")
            warnings.append(warn)
        out[job.id] = jr.model_dump()
        n_must = sum(1 for r in jr.requirements if r.kind == "must")
        log(f"{truncate(job.title, 48)} ({job.company}): {n_must} must-haves, {len(jr.requirements) - n_must} nice-to-haves.")
    return {"requirements": out, "warnings": warnings}


@node("judge_evidence")
def judge_evidence(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    jobs = _jobs(state)
    profile, units = _profile(state), _units(state)
    sim = get_similarity()
    workers = settings.llm_concurrency if ctx.use_llm else 1
    items = list(state["requirements"].items())
    out: dict[str, dict] = {}
    warnings = list(state.get("warnings", []))
    total_down = 0

    def run(item):
        jid, jr = item
        return judge_mod.judge(JobRequirements.model_validate(jr), profile, units, ctx.llm if ctx.use_llm else None, sim, jobs[jid].title)

    for (jid, jr), res in _parallel(items, run, workers):
        if isinstance(res, Exception):
            judgments, down, warn = judge_mod.judge_heuristic(JobRequirements.model_validate(jr), profile, units, sim), 0, str(res)
        else:
            judgments, down, warn = res
        if warn:
            log(warn, "warn")
            warnings.append(warn)
        total_down += down
        counts = {v: sum(1 for j in judgments if j.verdict == v) for v in ("met", "partial", "missing")}
        log(
            f"{truncate(jobs[jid].title, 48)}: {counts['met']} met, {counts['partial']} partial, {counts['missing']} missing"
            + (f"; {down} verdict(s) without valid evidence downgraded" if down else "")
            + "."
        )
        out[jid] = {"judgments": [j.model_dump() for j in judgments], "downgraded": down}
    if total_down:
        log(f"Evidence guard: {total_down} 'met/partial' verdicts cited no valid CV line and were set to missing.", "warn")
    return {"judgments": out, "warnings": warnings}


@node("score_rank")
def score_rank(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    jobs = _jobs(state)
    profile = _profile(state)
    rrf = {s["job_id"]: s["rrf"] for s in state["shortlist"]}
    analyses: list[JobAnalysis] = []
    for jid, jr_d in state["requirements"].items():
        jr = JobRequirements.model_validate(jr_d)
        jd = state["judgments"].get(jid, {"judgments": [], "downgraded": 0})
        judgments = [Judgment.model_validate(j) for j in jd["judgments"]]
        fit, must, nice = coverage(jr, judgments)
        analyses.append(
            JobAnalysis(
                job_id=jid,
                requirements=jr,
                judgments=judgments,
                fit=fit,
                must_coverage=must,
                nice_coverage=nice,
                flags=flags_for(jobs[jid], jr, profile, ctx.prefs),
                retrieval_score=rrf.get(jid, 0.0),
                downgraded=jd.get("downgraded", 0),
            )
        )
    analyses.sort(key=lambda a: (-a.fit, -a.retrieval_score))
    for i, a in enumerate(analyses, start=1):
        a.rank = i
    learn = learn_next(analyses)
    if analyses:
        top = analyses[0]
        log(f"Top match: {jobs[top.job_id].title} at {jobs[top.job_id].company}, fit {round(top.fit * 100)}.")
    if learn:
        log("Learn next: " + ", ".join(f"{l.skill} (asked by {l.jobs_requiring}, unlocks {l.unlocks})" for l in learn[:3]) + ".")
    log("Waiting for you to pick 1-3 jobs to tailor your CV for.", "info")
    return {"analyses": [a.model_dump() for a in analyses], "learn_next": [l.model_dump() for l in learn]}


@node("pick_jobs")
def pick_jobs(state: MatchState, config: RunnableConfig, log: NodeLog):
    ids = [a["job_id"] for a in state.get("analyses", [])]
    auto = state["options"].get("auto_select")
    if auto is not None:
        choice = ids[: int(auto)]
    else:
        choice = interrupt({"type": "pick_jobs", "max": 3, "job_ids": ids})
    selected = [i for i in (choice or []) if i in ids][:3]
    jobs = _jobs(state)
    if selected:
        log("Tailoring for: " + "; ".join(jobs[i].title for i in selected) + ".")
    else:
        log("No job selected; skipping tailoring.")
    return {"selected": selected, "tailored": [], "tailor_round": 0}


def route_after_pick(state: MatchState) -> str:
    return "rewrite" if state.get("selected") else "report"


@node("rewrite")
def rewrite(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    jobs = _jobs(state)
    analyses = {a["job_id"]: JobAnalysis.model_validate(a) for a in state.get("analyses", [])}
    bullets = [TailoredBullet.model_validate(b) for b in state.get("tailored", [])]
    if not bullets:
        units = _units(state)
        for jid in state.get("selected", []):
            picked = pick_bullets(jobs[jid], analyses[jid], units, settings.bullets_per_job)
            bullets.extend(picked)
            log(f"{truncate(jobs[jid].title, 48)}: chose {', '.join(b.evidence_id for b in picked) or 'no'} bullet(s) to tailor.")
        if not bullets:
            log("None of your bullets supports these jobs' requirements, so there is nothing to tailor.", "warn")
    rnd = state.get("tailor_round", 0) + 1
    pending = [b for b in bullets if b.status == "pending"]

    def draft(b: TailoredBullet):
        attempt = len(b.attempts) + 1
        if ctx.use_llm:
            return llm_draft(b, jobs[b.job_id], ctx.llm)
        return heuristic_draft(b, analyses[b.job_id], attempt)

    workers = settings.llm_concurrency if ctx.use_llm else 1
    for b, res in _parallel(pending, draft, workers):
        if isinstance(res, Exception):
            b.draft, b.draft_note = b.original, f"rewriter failed ({res}); proposing the original"
        else:
            b.draft, b.draft_note = res
    if pending:
        log(f"Round {rnd}: drafted {len(pending)} bullet(s).")
    return {"tailored": [b.model_dump() for b in bullets], "tailor_round": rnd}


@node("verify")
def verify(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    jobs = _jobs(state)
    bullets = [TailoredBullet.model_validate(b) for b in state.get("tailored", [])]
    pending = [b for b in bullets if b.status == "pending"]
    workers = settings.llm_concurrency if ctx.use_llm else 1
    for b, res in _parallel(pending, lambda b: verify_bullet(b, b.draft, ctx.llm if ctx.use_llm else None), workers):
        problems = [f"verifier error: {res}"] if isinstance(res, Exception) else res
        b.attempts.append(Draft(text=b.draft, ok=not problems, problems=problems, note=b.draft_note))
        title = truncate(jobs[b.job_id].title, 40)
        if not problems:
            b.status, b.final, b.feedback = "verified", b.draft, ""
            log(f"✓ {b.evidence_id} for {title}: verified on attempt {len(b.attempts)}.", "success")
        else:
            b.feedback = "; ".join(problems)
            if len(b.attempts) >= settings.max_rewrite_attempts:
                b.status, b.final = "kept_original", b.original
                log(f"✗ {b.evidence_id} for {title}: no draft passed after {len(b.attempts)} attempts; keeping your original.", "warn")
            else:
                log(f"✗ {b.evidence_id} for {title}: rejected ({b.feedback}). Sending back to the rewriter.", "warn")
    return {"tailored": [b.model_dump() for b in bullets]}


def route_after_verify(state: MatchState) -> str:
    return "rewrite" if any(b["status"] == "pending" for b in state.get("tailored", [])) else "report"


@node("report")
def report(state: MatchState, config: RunnableConfig, log: NodeLog):
    ctx = _ctx(config)
    jobs = _jobs(state)
    md = build_report(
        _profile(state),
        _units(state),
        jobs,
        [JobAnalysis.model_validate(a) for a in state.get("analyses", [])],
        [LearnItem.model_validate(l) for l in state.get("learn_next") or []],
        [TailoredBullet.model_validate(b) for b in state.get("tailored", [])],
        {"mode": f"LLM ({ctx.llm.cfg.llm_model})" if ctx.use_llm else "offline rules", "similarity": state.get("similarity", "?")},
    )
    log("Report ready.", "success")
    return {"report_md": md}


def build_graph():
    g = StateGraph(MatchState)
    for name, fn in [
        ("parse_cv", parse_cv),
        ("plan_queries", plan_queries),
        ("fetch_jobs", fetch_jobs),
        ("triage", triage),
        ("refine_queries", refine_queries),
        ("shortlist", shortlist),
        ("extract_requirements", extract_requirements),
        ("judge_evidence", judge_evidence),
        ("score_rank", score_rank),
        ("pick_jobs", pick_jobs),
        ("rewrite", rewrite),
        ("verify", verify),
        ("report", report),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "parse_cv")
    g.add_edge("parse_cv", "plan_queries")
    g.add_edge("plan_queries", "fetch_jobs")
    g.add_edge("fetch_jobs", "triage")
    g.add_conditional_edges("triage", route_after_triage, {"refine_queries": "refine_queries", "shortlist": "shortlist"})
    g.add_edge("refine_queries", "fetch_jobs")
    g.add_edge("shortlist", "extract_requirements")
    g.add_edge("extract_requirements", "judge_evidence")
    g.add_edge("judge_evidence", "score_rank")
    g.add_edge("score_rank", "pick_jobs")
    g.add_conditional_edges("pick_jobs", route_after_pick, {"rewrite": "rewrite", "report": "report"})
    g.add_edge("rewrite", "verify")
    g.add_conditional_edges("verify", route_after_verify, {"rewrite": "rewrite", "report": "report"})
    g.add_edge("report", END)
    return g.compile(checkpointer=InMemorySaver())


GRAPH = build_graph()
NODE_ORDER = [
    "parse_cv", "plan_queries", "fetch_jobs", "triage", "refine_queries", "shortlist", "extract_requirements",
    "judge_evidence", "score_rank", "pick_jobs", "rewrite", "verify", "report",
]
