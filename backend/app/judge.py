"""Evidence judging: for each requirement, is it met, partially met or missing in the CV,
and which CV lines prove it? Every met/partial verdict must cite evidence units ("no evidence,
no credit"): LLM verdicts that cite nothing valid are downgraded to missing."""
from __future__ import annotations

import re

import numpy as np

from .llm import LLMClient
from .retrieval import thresholds
from .schemas import EvidenceUnit, Judgment, JobRequirements, LLMJudgments, Profile, Requirement
from .skills import SKILLS, canonical, find_languages, find_skills, norm_key, related, same_wording, with_implied
from .text import fold

SECTION_PRIORITY = {"experience": 0, "projects": 1, "summary": 2, "certifications": 3, "other": 4, "skills": 5, "education": 6, "languages": 7}
RANK = {"missing": 0, "partial": 1, "met": 2}
ANY_OF_RE = re.compile(r"\b(or|ou|oder)\b")
TOOL_KINDS = {"tool", "platform", "language", "standard"}


class SkillIndex:
    """Where each skill appears in the CV: skill -> [(unit_id, surface, is_member)], plus implied skills."""

    def __init__(self, units: list[EvidenceUnit]) -> None:
        self.units = {u.id: u for u in units}
        self.hits: dict[str, list[tuple[str, str, bool]]] = {}
        self.strong: set[str] = set()
        for u in sorted(units, key=lambda u: SECTION_PRIORITY.get(u.section, 9)):
            for h in find_skills(u.text):
                lst = self.hits.setdefault(h.skill, [])
                if not h.weak:
                    self.strong.add(h.skill)
                if not any(x[0] == u.id and x[1] == h.surface for x in lst):
                    lst.append((u.id, h.surface, h.member))
        self.implied_by = {k: v for k, v in with_implied(set(self.hits)).items() if v}
        self.text = fold(" \n ".join(u.text for u in units))

    def has(self, skill: str) -> bool:
        return skill in self.hits or skill in self.implied_by

    def weak_only(self, skill: str) -> bool:
        """The CV shows this skill only through indirect wording (e.g. 'vibration data')."""
        src = self._src(skill)
        return src is not None and src not in self.strong

    def _src(self, skill: str) -> str | None:
        return skill if skill in self.hits else self.implied_by.get(skill)

    def keys(self, skill: str) -> set[str]:
        return {norm_key(s) for _, s, _ in self.hits.get(skill, [])}

    def evidence(self, skill: str, n: int = 2, key: str | None = None) -> list[str]:
        ids: list[str] = []
        for uid, surface, _ in self.hits.get(self._src(skill) or "", []):
            if key and norm_key(surface) != key:
                continue
            if uid not in ids:
                ids.append(uid)
        return ids[:n]

    def plain_surface(self, skill: str) -> str | None:
        """How the CV names the skill itself (not a member tool), if it does."""
        for _, surface, member in self.hits.get(skill, []):
            if not member:
                return surface
        return None

    def related_to(self, skill: str) -> str | None:
        for other in self.hits:
            if related(skill, other):
                return other
        return None


def _years_verdict(req: Requirement, profile: Profile) -> str:
    need = req.min_years or 0
    have = profile.years_experience + profile.internship_months / 24
    if have >= need:
        return "met"
    if have >= need * 0.5 or (need <= 2 and profile.internship_months >= 3):
        return "partial"
    return "missing"


def _language_verdict(req: Requirement, profile: Profile) -> str:
    levels = {l.name: l.level for l in profile.languages}
    wanted = find_languages(req.text)
    verdicts = []
    for lang in req.languages:
        need = max(3, wanted.get(lang, 3))
        lvl = levels.get(lang, 0)
        verdicts.append("met" if lvl >= need else ("partial" if lvl > 0 else "missing"))
    return min(verdicts, key=lambda v: RANK[v]) if verdicts else "missing"


FIELD_CONCEPTS = {
    "mechanical": ["mechanical", "mecanique", "maschinenbau"],
    "electromechanical": ["electromechanical", "electromecanique"],
    "industrial": ["industrial", "industriel", "industrielle"],
    "electrical": ["electrical", "electrique", "electrotechnique", "elektrotechnik"],
    "computer science": ["computer science", "informatique", "informatik", "software engineering"],
    "data science": ["data science", "science des donnees"],
    "statistics": ["statistic", "statistique", "statistik"],
    "mathematics": ["mathemat"],
    "physics": ["physics", "physique", "physik"],
    "chemical": ["chemical", "chimie", "chimique", "chemie"],
    "civil": ["civil engineering", "genie civil"],
    "energy": ["energy", "energie", "energetique"],
    "maintenance": ["maintenance"],
    "reliability": ["reliability", "fiabilite", "dependability", "surete de fonctionnement", "rams"],
    "aerospace": ["aerospace", "aeronautique", "aeronautic"],
    "accounting": ["accounting", "comptabilite"],
}
GENERIC_ENGINEERING = re.compile(r"\b(engineering|engineer|ingenieurs?|genie|ingenieur)\b")
STUDENT_REQ_RE = re.compile(r"\b(student|etudiante?s?|final[- ]year|derniere annee|fin d'etudes|laufendes studium|enrolled|currently studying)\b")


def _concepts(text: str) -> set[str]:
    f = fold(text)
    return {c for c, words in FIELD_CONCEPTS.items() if any(w in f for w in words)}


def _education_verdict(req: Requirement, units: list[EvidenceUnit], profile: Profile) -> tuple[str, list[str], str]:
    edu = [u for u in units if u.section == "education"]
    f = fold(req.text)
    verdicts, notes = [], []
    if STUDENT_REQ_RE.search(f):
        verdicts.append("met" if profile.seniority == "student" else "partial")
        notes.append("student" if profile.seniority == "student" else "asks for a student")
    if not edu:
        return "missing", [], "no education section found"
    wanted, have = _concepts(req.text), _concepts(" ".join(u.text for u in edu))
    best = edu[0]
    if wanted:
        common = wanted & have
        verdicts.append("met" if common else "partial")
        if common:
            best = next((u for u in edu if _concepts(u.text) & common), edu[0])
        else:
            notes.append("different field of study")
    elif GENERIC_ENGINEERING.search(f):
        ok = any(GENERIC_ENGINEERING.search(fold(u.text)) for u in edu)
        verdicts.append("met" if ok else "partial")
    else:
        verdicts.append("met")
    verdict = min(verdicts, key=lambda v: RANK[v])
    return verdict, [best.id], "; ".join(notes)


_GENERIC = re.compile(
    r"\b(\d+\+?|years?|yrs|ans|annees|jahre|of|in|a|an|the|de|d|en|minimum|at|least|experience|experiences|professional|"
    r"professionnelle|relevant|similar|role|roles|position|work|working|industry|field|domaine|poste|similaire|und|mit)\b"
)


def _has_topic(text: str) -> bool:
    """True if a years-of-experience requirement also names a domain ("2+ years in DevOps")."""
    rest = _GENERIC.sub(" ", fold(text))
    return len(re.findall(r"[a-z]{3,}", rest)) >= 1


def _combine(verdicts: list[str]) -> str:
    if not verdicts:
        return "missing"
    if all(v == "met" for v in verdicts):
        return "met"
    if any(v in ("met", "partial") for v in verdicts):
        return "partial"
    return "missing"


def judge_heuristic(jr: JobRequirements, profile: Profile, units: list[EvidenceUnit], sim) -> list[Judgment]:
    idx = SkillIndex(units)
    pool = [u for u in units if u.section != "languages"]
    lang_unit = next((u.id for u in units if u.section == "languages"), None)
    exp_units = [u.id for u in units if u.section == "experience"][:2]
    free = [
        r for r in jr.requirements
        if not r.skills and not r.languages and r.category != "education" and (not r.min_years or _has_topic(r.text))
    ]
    # Bullets are compared together with their role/company line, which often carries the domain.
    sims = sim.matrix([r.text for r in free], [f"{u.context} {u.text}".strip() for u in pool]) if free and pool else None
    t_met, t_partial = thresholds(sim)
    out: list[Judgment] = []
    for r in jr.requirements:
        verdicts: list[str] = []
        evidence: list[str] = []
        missing: list[str] = []
        notes: list[str] = []
        cv_term = jd_term = None
        wording = False
        if r.min_years:
            verdicts.append(_years_verdict(r, profile))
            notes.append(f"asks {r.min_years:g}+ yrs, CV shows ~{profile.years_experience:g}")
            if not r.skills:
                evidence += exp_units
        if r.languages:
            verdicts.append(_language_verdict(r, profile))
            if lang_unit:
                evidence.append(lang_unit)
        if r.category == "education" and not r.skills:
            v, ev, note = _education_verdict(r, units, profile)
            verdicts.append(v)
            evidence += ev
            if note:
                notes.append(note)
        # --- skills ---
        jd_hits = find_skills(r.text)
        skill_v: list[tuple[str, str, list[str], str]] = []  # (label, verdict, evidence, note)
        for s in r.skills:
            name = s if s in SKILLS else (canonical(s) or s)
            mine = [h for h in jd_hits if h.skill == name]
            # The posting names a specific product (e.g. "DAX", "Helm") rather than the skill itself.
            specific = name in SKILLS and bool(mine) and all(h.member for h in mine) and SKILLS[name].kind in TOOL_KINDS
            if name in SKILLS and idx.has(name):
                jd_keys = {h.key for h in mine}
                if specific and not (jd_keys & idx.keys(name)):
                    skill_v.append((mine[0].surface, "partial", idx.evidence(name), f"has {name}, not {mine[0].surface}"))
                    continue
                key = next(iter(jd_keys & idx.keys(name)), None) if specific else None
                if idx.weak_only(name):
                    skill_v.append((name, "partial", idx.evidence(name), f"only indirect evidence for {name}"))
                    continue
                note = f"{name} implied by {idx.implied_by[name]}" if (name in idx.implied_by and name not in idx.hits) else ""
                skill_v.append((name, "met", idx.evidence(name, key=key), note))
                if not note:
                    plain_jd = next((h.surface for h in mine if not h.member), None)
                    plain_cv = idx.plain_surface(name)
                    if plain_jd and plain_cv and not (jd_keys & idx.keys(name)) and not same_wording(plain_cv, plain_jd):
                        cv_term, jd_term, wording = plain_cv, plain_jd, True
            elif name in SKILLS and (rel := idx.related_to(name)):
                skill_v.append((name, "partial", idx.evidence(rel), f"related: {rel}"))
            elif name not in SKILLS and re.search(r"(?<![\w])" + re.escape(fold(name)) + r"(?![\w])", idx.text):
                pos = next((u.id for u in units if fold(name) in fold(u.text)), None)
                skill_v.append((name, "met", [pos] if pos else [], ""))
            else:
                skill_v.append((name, "missing", [], ""))
        if skill_v:
            if len(skill_v) > 1 and ANY_OF_RE.search(fold(r.text)):
                best = max(skill_v, key=lambda x: RANK[x[1]])
                chosen = [best]
                if best[1] != "met":
                    missing.append(best[0])
            else:
                chosen = skill_v
                missing += [lbl for lbl, v, _, _ in skill_v if v != "met"]
            skill_verdicts = [v for _, v, _, _ in chosen]
            if r.min_years and all(v == "missing" for v in skill_verdicts):
                verdicts = ["missing"]  # years of a skill you do not have
            verdicts += skill_verdicts
            for _, v, ev, note in chosen:
                evidence += ev
                if note:
                    notes.append(note)
        # --- free text ---
        if r in free and sims is not None:
            row = sims[free.index(r)]
            j = int(np.argmax(row))
            score = float(row[j])
            v = "met" if score >= t_met else ("partial" if score >= t_partial else "missing")
            verdicts.append(v)
            if v != "missing":
                evidence.append(pool[j].id)
            notes.append(f"closest CV line similarity {score:.2f}")
        verdict = _combine(verdicts)
        gap = "wording" if (verdict == "met" and wording) else ("none" if verdict == "met" else "skill")
        out.append(
            Judgment(
                req_id=r.id,
                verdict=verdict,  # type: ignore[arg-type]
                evidence_ids=list(dict.fromkeys(evidence))[:3] if verdict != "missing" else [],
                note="; ".join(notes)[:160],
                gap_type=gap,  # type: ignore[arg-type]
                cv_term=cv_term if gap == "wording" else None,
                jd_term=jd_term if gap == "wording" else None,
                missing_skills=list(dict.fromkeys(missing)) if verdict != "met" else [],
            )
        )
    return out


SYSTEM = """You are a strict technical recruiter checking a CV against job requirements.
For EACH requirement decide:
- "met": an evidence line directly demonstrates it (same skill/tool/experience, even if worded differently or in another language);
- "partial": only related or weaker evidence (adjacent tool, academic instead of professional, fewer years, lower language level);
- "missing": nothing in the evidence supports it.
Rules:
- Use ONLY the numbered evidence lines and candidate facts. Do not assume skills that are not written.
- Cite the evidence IDs (e.g. "E3") that support every met/partial verdict. No evidence ID means "missing".
- If the CV names the skill differently from the posting (e.g. "AMDEC" vs "FMEA", "sklearn" vs "scikit-learn"),
  fill cv_term and jd_term with both spellings.
- Keep notes under 15 words."""


def judge_llm(jr: JobRequirements, profile: Profile, units: list[EvidenceUnit], llm: LLMClient, job_title: str) -> tuple[list[Judgment], int]:
    reqs = "\n".join(f"{r.id} [{r.kind}] {r.text}" for r in jr.requirements)
    ev = "\n".join(
        f"{u.id} ({u.section}{'; ' + u.context[:70] if u.context else ''}): {u.text}" for u in units
    )
    langs = ", ".join(f"{l.name} (level {l.level}/5)" for l in profile.languages) or "not stated"
    facts = (
        f"~{profile.years_experience:g} years professional experience, {profile.internship_months} months of internships; "
        f"seniority: {profile.seniority}; languages: {langs}"
    )
    user = f"Job: {job_title}\n\nRequirements:\n{reqs}\n\nCV evidence (verbatim lines):\n{ev}\n\nCandidate facts: {facts}"
    out = llm.complete_json("judge", SYSTEM, user, LLMJudgments)
    valid_ids = {u.id for u in units}
    by_id = {j.req_id.strip(): j for j in out.judgments}
    idx = SkillIndex(units)
    judgments: list[Judgment] = []
    downgraded = 0
    for r in jr.requirements:
        j = by_id.get(r.id)
        if j is None:
            judgments.append(Judgment(req_id=r.id, verdict="missing", note="not judged by the model", gap_type="skill", missing_skills=list(r.skills)))
            continue
        ids = [e.strip() for e in j.evidence_ids if e.strip() in valid_ids]
        verdict = j.verdict
        note = j.note[:160]
        if verdict in ("met", "partial") and not ids:
            verdict = "missing"
            downgraded += 1
            note = "downgraded: no valid evidence cited"
        missing = [] if verdict == "met" else [s for s in r.skills if not (s in SKILLS and idx.has(s))] or (list(r.skills) if verdict == "missing" else [])
        wording = verdict == "met" and j.cv_term and j.jd_term and fold(j.cv_term) != fold(j.jd_term)
        judgments.append(
            Judgment(
                req_id=r.id,
                verdict=verdict,
                evidence_ids=ids[:3] if verdict != "missing" else [],
                note=note,
                gap_type="wording" if wording else ("none" if verdict == "met" else "skill"),
                cv_term=j.cv_term if wording else None,
                jd_term=j.jd_term if wording else None,
                missing_skills=missing,
            )
        )
    return judgments, downgraded


def judge(jr: JobRequirements, profile: Profile, units: list[EvidenceUnit], llm: LLMClient | None, sim, job_title: str):
    """Returns (judgments, downgraded_count, warning)."""
    if llm is not None and llm.enabled and jr.requirements:
        try:
            j, d = judge_llm(jr, profile, units, llm, job_title)
            return j, d, None
        except Exception as exc:
            return judge_heuristic(jr, profile, units, sim), 0, f"LLM judging failed for '{job_title}' ({exc}); used rules instead."
    return judge_heuristic(jr, profile, units, sim), 0, None
