"""Role families: job titles (EN/FR) plus the skills that signal them.

Used to guess target titles from a CV (offline mode), to plan/refine search queries, and to
decide whether a posting title is relevant during triage.
"""
from __future__ import annotations

import re
from collections import Counter

from .text import fold

ROLE_FAMILIES: dict[str, dict] = {
    "reliability": {
        "label": "Reliability & maintenance engineering",
        "titles": ["reliability engineer", "maintenance engineer"],
        "synonyms": [
            "asset integrity engineer", "condition monitoring engineer", "maintenance planner", "RAMS engineer",
            "ingénieur fiabilité", "ingénieur maintenance", "responsable maintenance", "predictive maintenance",
            "maintenance methods engineer", "ingénieur méthodes maintenance",
        ],
        "signals": [
            "Reliability engineering", "FMEA", "Fault tree analysis", "Reliability block diagrams", "Weibull analysis",
            "MTBF/MTTR", "RCM", "TPM", "Preventive maintenance", "Predictive maintenance", "Condition monitoring",
            "Vibration analysis", "Thermography", "Oil analysis", "CMMS", "SAP PM", "IBM Maximo", "Maintenance planning",
            "Maintenance KPIs", "Root cause analysis", "Asset management", "Rotating equipment", "Remaining useful life",
            "Survival analysis", "Spare parts management", "OEE",
        ],
    },
    "data_science": {
        "label": "Data science & machine learning",
        "titles": ["data scientist", "machine learning engineer"],
        "synonyms": [
            "ML engineer", "AI engineer", "applied scientist", "data science", "ingénieur IA", "ingénieur machine learning",
            "MLOps engineer", "research engineer",
        ],
        "signals": [
            "Machine learning", "Deep learning", "scikit-learn", "PyTorch", "TensorFlow", "Keras", "XGBoost", "LightGBM",
            "Statistics", "Time series analysis", "Anomaly detection", "Forecasting", "Feature engineering", "NLP",
            "Computer vision", "LLMs", "MLOps", "MLflow", "Survival analysis", "Remaining useful life", "pandas", "NumPy",
        ],
    },
    "data_analytics": {
        "label": "Data & BI analytics",
        "titles": ["data analyst"],
        "synonyms": [
            "business intelligence analyst", "BI analyst", "analytics engineer", "reporting analyst", "analyste de données",
            "analyste BI", "data analyst junior", "business analyst",
        ],
        "signals": [
            "SQL", "Power BI", "Tableau", "Looker", "Excel", "Data visualization", "Data analysis", "Statistics",
            "Power Query", "dbt", "Data modeling", "A/B testing", "pandas",
        ],
    },
    "software": {
        "label": "Software engineering",
        "titles": ["software engineer", "backend developer"],
        "synonyms": [
            "full-stack developer", "fullstack developer", "frontend developer", "web developer", "backend engineer",
            "développeur", "développeur full stack", "ingénieur logiciel", "platform engineer", "python developer",
        ],
        "signals": [
            "JavaScript", "TypeScript", "React", "Node.js", "FastAPI", "Django", "Flask", "Spring Boot", "REST APIs",
            "GraphQL", "Docker", "Kubernetes", "CI/CD", "Git", "PostgreSQL", "Java", "Go", "C#", "Automated testing",
            "HTML/CSS", "AWS", "Next.js",
        ],
    },
    "data_engineering": {
        "label": "Data engineering",
        "titles": ["data engineer"],
        "synonyms": ["analytics engineer", "big data engineer", "ingénieur data", "ETL developer"],
        "signals": ["Spark", "Airflow", "Kafka", "dbt", "Snowflake", "BigQuery", "Databricks", "ETL pipelines", "Data warehousing", "SQL"],
    },
    "industrial": {
        "label": "Industrial, process & quality engineering",
        "titles": ["process engineer", "quality engineer"],
        "synonyms": [
            "industrial engineer", "methods engineer", "continuous improvement engineer", "production engineer",
            "lean engineer", "ingénieur méthodes", "ingénieur qualité", "ingénieur process", "ingénieur industriel",
        ],
        "signals": [
            "Lean manufacturing", "Six Sigma", "SPC", "OEE", "ISO 9001", "IATF 16949", "Root cause analysis",
            "Minitab", "FMEA", "Discrete-event simulation", "Project management",
        ],
    },
    "automation": {
        "label": "Automation & controls",
        "titles": ["automation engineer", "controls engineer"],
        "synonyms": ["PLC programmer", "instrumentation engineer", "SCADA engineer", "ingénieur automatisme", "automaticien", "electrical engineer"],
        "signals": [
            "PLC programming", "Siemens TIA Portal", "Rockwell Studio 5000", "SCADA/HMI", "Industrial protocols",
            "IoT", "MQTT", "Embedded systems", "Sensors & instrumentation", "Electrical maintenance", "LabVIEW",
        ],
    },
    "mechanical": {
        "label": "Mechanical design",
        "titles": ["mechanical engineer", "design engineer"],
        "synonyms": ["mechanical design engineer", "ingénieur mécanique", "ingénieur conception", "CAD engineer"],
        "signals": ["SolidWorks", "CATIA", "AutoCAD", "Creo", "Mechanical design", "GD&T", "Finite element analysis", "ANSYS", "Abaqus"],
    },
}

_TITLE_PATTERNS = {
    fam: [fold(t) for t in spec["titles"] + spec["synonyms"]] for fam, spec in ROLE_FAMILIES.items()
}


def family_scores(skills: list[str], text: str = "") -> Counter:
    """Score each role family by skill signals (+ explicit title mentions in the text)."""
    scores: Counter = Counter()
    sset = set(skills)
    for fam, spec in ROLE_FAMILIES.items():
        scores[fam] += sum(1 for s in spec["signals"] if s in sset)
    folded = fold(text)
    for fam, pats in _TITLE_PATTERNS.items():
        for p in pats:
            if p and re.search(r"(?<![\w])" + re.escape(p), folded):
                scores[fam] += 2
    return scores


TITLE_WORD_EQUIV = {
    "ingenieur": "engineer", "ingenieure": "engineer", "developpeur": "developer", "developpeuse": "developer",
    "analyste": "analyst", "donnees": "data", "fiabilite": "reliability", "technicien": "technician",
    "technicienne": "technician", "responsable": "manager", "chef": "lead", "stagiaire": "intern",
    "logiciel": "software", "automaticien": "automation",
}


def title_tokens(title: str) -> list[str]:
    toks = re.findall(r"[a-z0-9+#]+", fold(title))
    return [TITLE_WORD_EQUIV.get(t, t) for t in toks]


def query_matches_title(query: str, title: str) -> bool:
    """All meaningful words of the query appear in the title (prefix match tolerates plurals)."""
    q = [t for t in title_tokens(query) if len(t) > 1 and t not in {"junior", "senior", "de", "des", "en", "of", "and"}]
    t = title_tokens(title)
    if not q:
        return False

    def has(word: str) -> bool:
        stem = word[:6] if len(word) > 6 else word
        return any(tok == word or (len(word) > 4 and tok.startswith(stem)) for tok in t)

    return all(has(w) for w in q)
