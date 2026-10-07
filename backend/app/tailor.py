"""Bullet tailoring with a verifier that blocks invented claims.

The rewriter may: use the posting's terms for skills the bullet already shows (sklearn ->
scikit-learn, AMDEC -> AMDEC (FMEA)), reorder, tighten, strengthen a weak opening verb.
The verifier rejects any draft that adds a number or a tool/skill the original bullet does not
contain, grows too long, or (with an LLM) makes a claim the original does not support.
Rejected drafts go back to the rewriter with the reasons, at most MAX_REWRITE_ATTEMPTS times;
if no draft passes, the original bullet is kept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .llm import LLMClient
from .postings import requirement_lines
from .schemas import Alignment, EvidenceUnit, Job, JobAnalysis, LLMClaimCheck, LLMRewrite, TailoredBullet
from .skills import SKILLS, find_skills, is_french_surface, related, same_wording, skills_in, with_implied
from .text import fold, guess_language

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


# --- Selection ----------------------------------------------------------------------------
@dataclass
class JobTerms:
    """How the posting names each skill: its preferred plain term, and every spelling it uses."""

    preferred: dict[str, str]
    keys: dict[str, set[str]]


def job_terms(job: Job) -> JobTerms:
    req_text = "\n".join(t for _, t in requirement_lines(job.description))
    preferred: dict[str, str] = {}
    keys: dict[str, set[str]] = {}
    for source in (req_text, f"{job.title}\n{job.description}"):
        for h in find_skills(source):
            keys.setdefault(h.skill, set()).add(h.key)
            if not h.member:
                preferred.setdefault(h.skill, h.surface)
    return JobTerms(preferred, keys)


def alignments_for(text: str, terms: JobTerms) -> list[Alignment]:
    """Skills the bullet names differently from the posting (true synonyms only, never member tools)."""
    out: list[Alignment] = []
    seen: set[str] = set()
    for h in find_skills(text):
        if h.member or h.skill in seen or h.skill not in terms.preferred:
            continue
        if h.key in terms.keys.get(h.skill, set()) or same_wording(h.surface, terms.preferred[h.skill]):
            continue  # the posting already uses this wording (or a trivial variant of it)
        out.append(Alignment(cv_term=h.surface, jd_term=terms.preferred[h.skill], skill=h.skill))
        seen.add(h.skill)
    return out


def pick_bullets(job: Job, analysis: JobAnalysis, units: list[EvidenceUnit], n: int) -> list[TailoredBullet]:
    """Choose the experience/project bullets that best support this job's requirements."""
    bullets = {u.id: u for u in units if u.kind == "bullet"}
    reqs = {r.id: r for r in analysis.requirements.requirements}
    terms = job_terms(job)
    job_skills = set(terms.keys)
    title_skills = skills_in(job.title)
    score: dict[str, float] = {}
    targets: dict[str, list[str]] = {}
    for uid, u in bullets.items():
        mine = set(with_implied(skills_in(u.text)))
        sc = 0.0
        for j in analysis.judgments:
            r = reqs.get(j.req_id)
            if not r or j.verdict == "missing":
                continue
            if uid in j.evidence_ids or (mine & set(r.skills)):
                sc += (2.0 if r.kind == "must" else 1.0) * (1.0 if j.verdict == "met" else 0.6)
                targets.setdefault(uid, []).append(r.text)
        sc += 1.0 * len(mine & title_skills) + 0.3 * len(mine & job_skills)
        sc += 0.5 * len(alignments_for(u.text, terms))
        if sc > 0:
            score[uid] = sc
    chosen = sorted(score, key=lambda k: (-score[k], int(k[1:])))[:n]
    out = []
    for uid in sorted(chosen, key=lambda k: int(k[1:])):
        u = bullets[uid]
        out.append(
            TailoredBullet(
                job_id=job.id,
                evidence_id=uid,
                original=u.text,
                context=u.context,
                targets=list(dict.fromkeys(targets.get(uid, [])))[:3],
                alignments=alignments_for(u.text, terms),
            )
        )
    return out


# --- Verification -------------------------------------------------------------------------
def deterministic_problems(original: str, draft: str) -> list[str]:
    problems: list[str] = []
    if not draft.strip():
        return ["empty draft"]
    orig_nums = {n.replace(",", ".") for n in NUM_RE.findall(original)}
    new_nums = [n for n in NUM_RE.findall(draft) if n.replace(",", ".") not in orig_nums]
    if new_nums:
        problems.append("adds numbers not in your bullet: " + ", ".join(dict.fromkeys(new_nums)))
    allowed = set(with_implied(skills_in(original)))
    added = [s for s in dict.fromkeys(h.skill for h in find_skills(draft)) if s not in allowed]
    if added:
        problems.append("mentions tools/skills not in your bullet: " + ", ".join(added))
    if len(draft) > max(len(original) * 1.6, len(original) + 90):
        problems.append("much longer than the original")
    return problems


CLAIM_SYSTEM = """You verify a rewritten CV bullet against the original bullet.
A claim is UNSUPPORTED if the rewrite adds something the original does not state or clearly imply:
a new tool, technology, method, metric, number, scale, scope, responsibility, outcome, or seniority (e.g. "led").
Allowed: rephrasing, reordering, a stronger but equivalent verb, and the listed terminology swaps.
Return supported=true only if every claim in the rewrite is supported by the original."""


def llm_claim_problems(original: str, draft: str, alignments: list[Alignment], llm: LLMClient) -> list[str]:
    swaps = "; ".join(f"{a.cv_term} -> {a.jd_term}" for a in alignments) or "none"
    user = f"Original bullet:\n{original}\n\nRewritten bullet:\n{draft}\n\nAllowed terminology swaps: {swaps}"
    out = llm.complete_json("verify", CLAIM_SYSTEM, user, LLMClaimCheck)
    if out.supported and not out.unsupported_claims:
        return []
    claims = [c for c in out.unsupported_claims if c.strip()] or ["the checker found an unsupported claim"]
    return ["unsupported claim: " + "; ".join(claims[:3])]


def verify(b: TailoredBullet, draft: str, llm: LLMClient | None) -> list[str]:
    problems = deterministic_problems(b.original, draft)
    if not problems and llm is not None and llm.enabled:
        try:
            problems = llm_claim_problems(b.original, draft, b.alignments, llm)
        except Exception as exc:  # keep going with the deterministic checks only
            b.feedback = f"(claim check unavailable: {exc.__class__.__name__})"
    return problems


# --- Rewriting ----------------------------------------------------------------------------
WEAK_STARTS = [
    (r"^(participated in|took part in|was involved in)\s+", "Contributed to "),
]


def apply_alignments(text: str, alignments: list[Alignment]) -> str:
    """Use the posting's term. Translations and acronyms keep your term too: 'AMDEC (FMEA)'."""
    for a in alignments:
        pos = text.find(a.cv_term)
        if pos < 0:
            continue
        keep_both = is_french_surface(a.skill, a.cv_term) or (a.cv_term.isupper() and len(a.cv_term) <= 6)
        if keep_both:
            followed_by_paren = text[pos + len(a.cv_term): pos + len(a.cv_term) + 2].startswith(" (")
            repl = f"{a.cv_term}/{a.jd_term}" if followed_by_paren else f"{a.cv_term} ({a.jd_term})"
        else:
            repl = a.jd_term
        text = text[:pos] + repl + text[pos + len(a.cv_term):]
    return text


def upgrade_verb(text: str) -> str:
    for pat, repl in WEAK_STARTS:
        if re.match(pat, text, flags=re.I):
            return re.sub(pat, repl, text, count=1, flags=re.I)
    return text[:1].upper() + text[1:]


def heuristic_draft(b: TailoredBullet, analysis: JobAnalysis, attempt: int) -> tuple[str, str]:
    """Offline tailor (no LLM): it only aligns terminology, which is always safe.

    Its FIRST draft deliberately behaves like a naive keyword-stuffing tool (it bolts on a skill the
    posting wants but your CV lacks), so you can watch the verifier reject it without an API key.
    """
    text = upgrade_verb(apply_alignments(b.original, b.alignments))
    if attempt == 1:
        mine = set(with_implied(skills_in(b.original)))
        kinds = {r.id: r.kind for r in analysis.requirements.requirements}
        gaps = [
            (0 if kinds.get(j.req_id) == "must" else 1, s)
            for j in analysis.judgments
            for s in j.missing_skills
            if s in SKILLS and s not in mine
        ]
        if gaps:
            skill = sorted(gaps, key=lambda g: g[0])[0][1]
            if guess_language(b.original) == "fr":
                verb = "avec"
            else:
                verb = "using" if SKILLS[skill].kind in ("tool", "platform", "language") else "applying"
            base = text.rstrip()
            end = "." if base.endswith(".") else ""
            stuffed = base.rstrip(".") + f", {verb} {skill}" + end
            return stuffed, f"keyword-stuffing baseline: added '{skill}', which the posting wants"
    if text == b.original:
        return text, "no safe wording change: the bullet already uses the posting's terms"
    return text, "aligned terminology with the posting"


REWRITE_SYSTEM = """You tailor ONE CV bullet to a job posting without inventing anything.
You may: reorder the sentence to lead with what the job cares about; use the posting's term for a skill the bullet
ALREADY shows (only the listed terminology swaps); tighten wording; use a stronger but equivalent verb.
You must NOT add tools, technologies, methods, numbers, metrics, scope, outcomes or responsibilities that the
original bullet does not state. Keep it one sentence, at most 35 words, in the same language as the original."""


def llm_draft(b: TailoredBullet, job: Job, llm: LLMClient) -> tuple[str, str]:
    swaps = "\n".join(f"- {a.cv_term} -> {a.jd_term}" for a in b.alignments) or "- none"
    targets = "\n".join(f"- {t}" for t in b.targets) or "- (general relevance)"
    fb = f"\nYour previous draft was rejected: {b.feedback}\nFix exactly that." if b.feedback else ""
    user = (
        f"Job: {job.title} at {job.company}\nRequirements this bullet supports:\n{targets}\n"
        f"Allowed terminology swaps:\n{swaps}\n\nOriginal bullet:\n{b.original}{fb}"
    )
    out = llm.complete_json("rewrite", REWRITE_SYSTEM, user, LLMRewrite, strong=True, temperature=0.3)
    return out.rewritten.strip().strip('"'), "; ".join(out.changes)[:160]
