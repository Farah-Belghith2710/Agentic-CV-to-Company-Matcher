"""Data models shared by the pipeline, the API and the LLM prompts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["met", "partial", "missing"]
ReqKind = Literal["must", "nice"]


# --- CV -----------------------------------------------------------------------------------
class EvidenceUnit(BaseModel):
    id: str
    section: str  # experience | projects | skills | summary | education | certifications | languages | other
    text: str
    context: str = ""  # role / company line above a bullet
    kind: str = "bullet"  # bullet | skills | summary | education | line


class LanguageSkill(BaseModel):
    name: str
    level: int = 3  # 1 basic .. 5 native


class Profile(BaseModel):
    headline: str = ""
    target_titles: list[str] = []
    skills: list[str] = []
    domains: list[str] = []
    years_experience: float = 0.0
    internship_months: int = 0
    seniority: str = "junior"  # student | junior | mid | senior | lead
    languages: list[LanguageSkill] = []
    education: list[str] = []
    location: str = ""
    cv_language: str = "en"
    source: str = "heuristic"


# --- Jobs ---------------------------------------------------------------------------------
class Job(BaseModel):
    id: str
    source: str  # demo | greenhouse | lever | ashby | remotive | arbeitnow | pasted
    source_label: str
    company: str
    title: str
    location: str = ""
    workplace: str = "unknown"  # remote | hybrid | onsite | unknown
    url: str = ""
    posted_at: str | None = None
    description: str = ""
    tags: list[str] = []
    attribution: str | None = None


class Requirement(BaseModel):
    id: str
    text: str
    kind: ReqKind = "must"
    category: str = "skill"  # skill | experience | education | language | certification | domain | other
    skills: list[str] = []
    min_years: float | None = None
    languages: list[str] = []


class JobRequirements(BaseModel):
    requirements: list[Requirement] = []
    seniority: str = "unspecified"  # intern | junior | mid | senior | lead | unspecified
    min_years: float | None = None
    languages: list[str] = []
    workplace: str = "unknown"
    posting_language: str = "en"
    source: str = "heuristic"


class Judgment(BaseModel):
    req_id: str
    verdict: Verdict
    evidence_ids: list[str] = []
    note: str = ""
    gap_type: Literal["none", "wording", "skill"] = "none"
    cv_term: str | None = None
    jd_term: str | None = None
    missing_skills: list[str] = []


class Flag(BaseModel):
    kind: str  # location | language | seniority
    message: str


class JobAnalysis(BaseModel):
    job_id: str
    requirements: JobRequirements
    judgments: list[Judgment]
    fit: float = 0.0
    must_coverage: float | None = None
    nice_coverage: float | None = None
    flags: list[Flag] = []
    retrieval_score: float = 0.0
    rank: int = 0
    downgraded: int = 0


class LearnItem(BaseModel):
    skill: str
    jobs_requiring: int
    must_count: int
    unlocks: int
    fit_gain: float
    job_ids: list[str]


# --- Tailoring ----------------------------------------------------------------------------
class Alignment(BaseModel):
    cv_term: str
    jd_term: str
    skill: str


class Draft(BaseModel):
    text: str
    ok: bool
    problems: list[str] = []
    note: str = ""


class TailoredBullet(BaseModel):
    job_id: str
    evidence_id: str
    original: str
    context: str = ""
    final: str = ""
    status: Literal["pending", "verified", "kept_original"] = "pending"
    attempts: list[Draft] = []
    targets: list[str] = []
    alignments: list[Alignment] = []
    feedback: str = ""
    draft: str = ""
    draft_note: str = ""


# --- LLM output schemas (what the model must return) ---------------------------------------
class LLMLanguage(BaseModel):
    name: str
    level: str = Field("", description="native | fluent | advanced | intermediate | basic")


class LLMProfile(BaseModel):
    headline: str = Field("", description="One-line professional headline")
    target_titles: list[str] = Field(default_factory=list, description="3-5 job titles this person fits or aims at")
    skills: list[str] = Field(default_factory=list, description="Technical skills, tools and methods named in the CV")
    domains: list[str] = Field(default_factory=list, description="Professional domains, e.g. reliability engineering")
    years_experience: float = Field(0, description="Years of professional experience, internships excluded")
    seniority: str = Field("junior", description="student | junior | mid | senior | lead")
    languages: list[LLMLanguage] = Field(default_factory=list)
    location: str = ""


class LLMQueries(BaseModel):
    queries: list[str] = Field(description="3-5 short job-search queries (1-4 words each)")
    rationale: str = Field("", description="One sentence explaining the choice")


class LLMRequirement(BaseModel):
    text: str = Field(description="The requirement, short, in the posting's words")
    kind: ReqKind = Field("must", description="must = required/minimum; nice = preferred/bonus/plus")
    category: str = Field("skill", description="skill | experience | education | language | certification | domain")
    skills: list[str] = Field(default_factory=list, description="Tool/skill names mentioned in this requirement")


class LLMRequirements(BaseModel):
    requirements: list[LLMRequirement]
    seniority: str = Field("unspecified", description="intern | junior | mid | senior | lead | unspecified")
    min_years: float | None = Field(None, description="Minimum years of experience asked, if stated")
    languages: list[str] = Field(default_factory=list, description="Human languages required")
    workplace: str = Field("unknown", description="remote | hybrid | onsite | unknown")


class LLMJudgment(BaseModel):
    req_id: str
    verdict: Verdict
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = Field("", description="Max 15 words")
    cv_term: str | None = Field(None, description="How the CV phrases the matching skill, if it differs")
    jd_term: str | None = Field(None, description="How the posting phrases it")


class LLMJudgments(BaseModel):
    judgments: list[LLMJudgment]


class LLMRewrite(BaseModel):
    rewritten: str
    changes: list[str] = Field(default_factory=list, description="What you changed, briefly")


class LLMClaimCheck(BaseModel):
    supported: bool
    unsupported_claims: list[str] = Field(default_factory=list)
