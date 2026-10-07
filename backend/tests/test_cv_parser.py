from conftest import sample_text

from app.cv_parser import date_ranges, heuristic_profile, redact, segment


def test_redaction_removes_contact_details_but_keeps_dates():
    text = "Jane Doe\nParis | jane.doe@example.com | +33 6 12 34 56 78 | linkedin.com/in/jane\nExperience\nEngineer 2021 - 2023"
    red, counts = redact(text)
    assert "jane.doe" not in red and "34 56" not in red and "linkedin" not in red and "Jane Doe" not in red
    assert "2021 - 2023" in red
    assert counts["email"] == 1 and counts["phone"] == 1 and counts["link"] == 1 and counts["name"] == 1


def test_segmentation_gives_verbatim_evidence_units():
    red, _ = redact(sample_text("lina_haddad_reliability"))
    units, sections, header = segment(red)
    bullets = [u for u in units if u.kind == "bullet"]
    assert len(bullets) == 9
    assert bullets[0].text.startswith("Built a Weibull analysis")
    assert "Medjerda Rail Services" in bullets[0].context
    assert [u.id for u in units] == [f"E{i}" for i in range(1, len(units) + 1)]
    assert all(u.text in red for u in units if u.kind == "bullet")


def test_skills_sublabels_stay_in_skills_section():
    red, _ = redact(sample_text("alex_moreau_backend"))
    units, _, _ = segment(red)
    skills_lines = [u.text for u in units if u.section == "skills"]
    assert any(t.startswith("Languages: Python") for t in skills_lines)
    langs = [u.text for u in units if u.section == "languages"]
    assert langs == ["French (native), English (fluent, C1)"]


def test_profiles_of_the_samples():
    for name, seniority, years, intern in [
        ("lina_haddad_reliability", "student", 0.0, 5),
        ("sami_gharbi_analyste", "mid", 2.2, 6),
    ]:
        red, _ = redact(sample_text(name))
        units, sections, header = segment(red)
        p = heuristic_profile(red, units, sections, header)
        assert p.seniority == seniority
        assert abs(p.years_experience - years) < 0.3
        assert p.internship_months == intern


def test_date_ranges_en_fr():
    assert date_ranges("Jul 2025 - Aug 2025") == [(2025 * 12 + 6, 2025 * 12 + 8)]
    assert len(date_ranges("Fév 2024 - Juil 2024")) == 1
    assert len(date_ranges("Sept 2024 - aujourd'hui")) == 1
