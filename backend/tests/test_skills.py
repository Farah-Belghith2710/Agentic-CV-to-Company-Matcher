from app.skills import canonical, find_languages, find_skills, same_wording, skills_in, with_implied


def test_aliases_map_to_canonical_names():
    assert canonical("sklearn") == "scikit-learn"
    assert canonical("AMDEC") == "FMEA"
    assert canonical("Power-BI") == "Power BI"
    assert canonical("k8s") == "Kubernetes"
    assert canonical("GMAO") == "CMMS"
    assert canonical("not a skill at all") is None


def test_french_and_english_terms_are_found():
    found = skills_in("Analyse vibratoire, maintenance préventive et AMDEC sur GMAO (SAP PM).")
    assert {"Vibration analysis", "Preventive maintenance", "FMEA", "CMMS", "SAP PM"} <= found


def test_ambiguous_words_are_not_skills():
    text = "R&D engineer. I excel at teamwork. Rust removal on rails. Go/No-Go reviews. Power transformers maintenance."
    found = skills_in(text)
    assert not ({"R", "Excel", "Rust", "Go", "Deep learning"} & found)


def test_short_language_names_count_inside_lists():
    assert {"Python", "R", "C", "C++", "SQL"} <= skills_in("Languages: Python, R, C/C++, SQL")


def test_members_are_marked():
    hits = {h.surface: h for h in find_skills("Dashboards in Plotly, vibration data, data visualization")}
    assert hits["Plotly"].member and hits["Plotly"].skill == "Data visualization"
    assert hits["vibration data"].weak
    assert not hits["data visualization"].member


def test_implied_skills():
    implied = with_implied({"SAP PM", "PyTorch"})
    assert implied["CMMS"] == "SAP PM"
    assert implied["Machine learning"] == "PyTorch"


def test_language_levels():
    assert find_languages("Fluent in French (C1) and English; Arabic: native. Allemand: notions") == {
        "French": 4, "English": 4, "Arabic": 5, "German": 1,
    }
    assert find_languages("Langues : Arabe (langue maternelle), Français (courant), Anglais (B2)") == {
        "Arabic": 5, "French": 4, "English": 3,
    }


def test_same_wording():
    assert same_wording("Excel avancé", "Excel")
    assert same_wording("modélisation des données", "Modélisation de données")
    assert same_wording("statistiques", "statistique")
    assert not same_wording("Postgres", "PostgreSQL")  # worth aligning
    assert not same_wording("AMDEC", "FMEA")
