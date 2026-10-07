from app.cv_parser import heuristic_profile, redact, segment
from app.judge import judge_heuristic
from app.requirements import extract_heuristic, title_seniority
from app.retrieval import TfidfSimilarity
from app.schemas import Job, JobRequirements, Judgment, JobAnalysis, Requirement
from app.scoring import coverage, learn_next

CV = """Sam Example
Maintenance Engineer
Tunis, Tunisia

EXPERIENCE
Maintenance Intern | Example Plant
Jul 2025 - Sep 2025
• Ran an AMDEC on the packaging line and updated plans in the GMAO (SAP PM).
• Collected vibration data on pumps for the condition monitoring team.
• Built a Python dashboard with pandas for MTBF tracking.

EDUCATION
Engineering degree, Industrial Engineering | 2024 - 2027 (expected)

SKILLS
Power BI, Excel, SQL

LANGUAGES
Arabic (native), French (fluent), English (B2)
"""

POSTING = """About us
We make boxes.

Requirements
• FMEA practice.
• SAP PM or IBM Maximo.
• Vibration analysis.
• Fluent French and good English.
• 1 to 3 years of experience in maintenance (internships accepted).
• SQL.

Nice to have
• Power BI or Tableau.
• Kubernetes.
"""


def _setup():
    red, _ = redact(CV)
    units, sections, header = segment(red)
    profile = heuristic_profile(red, units, sections, header)
    job = Job(id="j1", source="pasted", source_label="x", company="Box Co", title="Maintenance Engineer", description=POSTING)
    return profile, units, job


def test_requirements_must_nice_and_short_lines():
    jr = extract_heuristic(Job(id="j", source="x", source_label="x", company="c", title="t", description=POSTING))
    texts = {r.text: r for r in jr.requirements}
    assert texts["SQL."].kind == "must"  # short lines with a skill are kept
    assert texts["Kubernetes."].kind == "nice"
    assert texts["1 to 3 years of experience in maintenance (internships accepted)."].min_years == 1
    assert all(r.id == f"R{i}" for i, r in enumerate(jr.requirements, start=1))


def test_title_seniority():
    assert title_seniority("Stage PFE - Maintenance prédictive", None) == "intern"
    assert title_seniority("Senior Data Scientist", None) == "senior"
    assert title_seniority("Data Analyst", 3) == "mid"


def test_judge_or_logic_weak_evidence_and_wording():
    profile, units, job = _setup()
    jr = extract_heuristic(job)
    judgments = {jr.requirements[int(j.req_id[1:]) - 1].text: j for j in judge_heuristic(jr, profile, units, TfidfSimilarity())}
    fmea = judgments["FMEA practice."]
    assert fmea.verdict == "met" and fmea.cv_term == "AMDEC" and fmea.jd_term == "FMEA"
    assert judgments["SAP PM or IBM Maximo."].verdict == "met"  # any-of
    assert judgments["Vibration analysis."].verdict == "partial"  # only "vibration data": indirect evidence
    assert judgments["Fluent French and good English."].verdict == "met"
    assert judgments["Kubernetes."].verdict == "missing"
    for j in judgments.values():
        if j.verdict != "missing":
            assert j.evidence_ids, "met/partial must cite evidence"


def test_coverage_and_learn_next():
    jr = JobRequirements(
        requirements=[
            Requirement(id="R1", text="a", kind="must", skills=["Kubernetes"]),
            Requirement(id="R2", text="b", kind="must", skills=["Python"]),
            Requirement(id="R3", text="c", kind="nice", skills=["Go"]),
        ]
    )
    js = [
        Judgment(req_id="R1", verdict="missing", missing_skills=["Kubernetes"]),
        Judgment(req_id="R2", verdict="met"),
        Judgment(req_id="R3", verdict="partial", missing_skills=["Go"]),
    ]
    fit, must, nice = coverage(jr, js)
    assert must == 0.5 and nice == 0.5 and abs(fit - (0.75 * 0.5 + 0.25 * 0.5)) < 1e-9
    a = JobAnalysis(job_id="j", requirements=jr, judgments=js, fit=fit, must_coverage=must, nice_coverage=nice)
    items = {i.skill: i for i in learn_next([a])}
    assert items["Kubernetes"].unlocks == 1 and items["Kubernetes"].must_count == 1
    assert items["Go"].unlocks == 0
    assert items["Kubernetes"].fit_gain > items["Go"].fit_gain
