from app.schemas import Alignment
from app.tailor import apply_alignments, deterministic_problems

ORIGINAL = "Ran an AMDEC on the bogie maintenance process with 5 technicians and ranked 38 failure modes."


def test_verifier_accepts_terminology_alignment():
    draft = "Ran an AMDEC (FMEA) on the bogie maintenance process with 5 technicians and ranked 38 failure modes."
    assert deterministic_problems(ORIGINAL, draft) == []


def test_verifier_rejects_new_numbers_and_tools():
    draft = "Led an FMEA with 5 technicians using Python, ranking 38 failure modes and cutting downtime by 20%."
    problems = " ".join(deterministic_problems(ORIGINAL, draft))
    assert "20" in problems and "Python" in problems


def test_verifier_rejects_rambling_drafts():
    assert deterministic_problems("Built dashboards.", "Built dashboards " + "and more " * 30)


def test_apply_alignments_formats():
    al = [Alignment(cv_term="AMDEC", jd_term="FMEA", skill="FMEA"), Alignment(cv_term="sklearn", jd_term="scikit-learn", skill="scikit-learn")]
    assert apply_alignments("AMDEC with sklearn", al) == "AMDEC (FMEA) with scikit-learn"
    gm = [Alignment(cv_term="GMAO", jd_term="CMMS", skill="CMMS")]
    assert apply_alignments("plans in the GMAO (SAP PM)", gm) == "plans in the GMAO/CMMS (SAP PM)"
