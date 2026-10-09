"""Job postings you collect from LinkedIn yourself, while you browse.

Nothing in this app contacts LinkedIn. Postings arrive in two ways, both started by you:
  * the "Send to CV Matcher" bookmark sends the job you are looking at (it reads the title, company,
    location and description from the page in your own browser);
  * the paste box accepts a whole LinkedIn job page copied with Ctrl+A, Ctrl+C.
This module turns the text of a copied LinkedIn page into clean fields, in English or French.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..text import clean_text

_APOS = "['’]"

# Where the posting starts and where it stops on a copied page.
DESC_START = re.compile(
    rf"^(about the job|job description|à propos de l{_APOS}offre d{_APOS}emploi|a propos de l{_APOS}offre d{_APOS}emploi|"
    rf"description du poste|description de l{_APOS}offre)$",
    re.I,
)
DESC_END = re.compile(
    rf"^(show less|see less|afficher moins|voir moins|show more|see more|afficher plus|voir plus|… ?more|\.\.\. ?more|"
    rf"set alert for similar jobs|créer une alerte.*|about the company|à propos de l{_APOS}entreprise|a propos de l{_APOS}entreprise|"
    rf"seniority level|niveau hiérarchique|employment type|type d{_APOS}emploi|looking for talent\?|people also viewed|"
    rf"similar jobs|offres d{_APOS}emploi similaires|more jobs.*|referrals increase your chances.*|see who you know|"
    rf"meet the hiring team|rencontrez l{_APOS}équipe de recrutement|benefits found in job post|"
    rf"get notified about new .*|sign in to create job alert|people you can reach out to)$",
    re.I,
)

_AGO_EN = r"(?:reposted\s+)?(?:\d+|an?|one)\s+(?:minute|hour|day|week|month|year)s?\s+ago"
_AGO_FR = r"(?:republié\s+)?il y a\s+(?:\d+|un|une)\s+\w+"
# Logged-in view: "Nabeul, Tunisia · 2 weeks ago · 37 applicants"
META_LINE = re.compile(rf"^(?P<loc>.+?)\s+[·•]\s+(?:{_AGO_EN}|{_AGO_FR})", re.I)
# Signed-out view: the date sits on its own line under the location.
AGO_LINE = re.compile(rf"^(?:{_AGO_EN}|{_AGO_FR})$", re.I)
APPLICANTS = re.compile(
    r"^(?:over |plus de )?\d[\d\s,.]*\s+(?:applicants?|candidats?|people clicked apply|personnes ont cliqué sur postuler)\b.*$", re.I
)

WORKPLACE_WORDS = {
    "remote": "remote", "à distance": "remote", "a distance": "remote", "télétravail": "remote",
    "hybrid": "hybrid", "hybride": "hybrid",
    "on-site": "onsite", "onsite": "onsite", "sur site": "onsite", "sur place": "onsite", "présentiel": "onsite",
}
INTERNSHIP_WORDS = {"internship", "stage", "stagiaire", "alternance", "apprenticeship"}
EMPLOYMENT_WORDS = INTERNSHIP_WORDS | {
    "full-time", "part-time", "contract", "temporary", "volunteer", "other", "freelance",
    "temps plein", "temps partiel", "cdi", "cdd", "contrat", "intérim", "bénévolat", "autre",
}

# LinkedIn's own interface, in English and French. None of these lines belongs to a posting.
UI_LINES = {
    "skip to main content", "home", "my network", "jobs", "messaging", "notifications", "me", "for business",
    "share", "show more options", "easy apply", "apply", "save", "saved", "promoted", "promoted by hirer",
    "actively reviewing applicants", "responses managed off linkedin", "show match details", "tailor my resume",
    "help me stand out", "use ai to assess how you fit", "message", "follow", "report this job", "sign in",
    "join now", "join or sign in", "sign in to save", "apply on company website", "new", "be an early applicant",
    "show all", "exclusive job seeker insights", "job poster", "linkedin", "dismiss", "close", "back", "more",
    "your job search", "job alert", "set alert", "retry premium", "try premium", "premium",
    "passer au contenu principal", "accueil", "réseau", "emplois", "messagerie", "vous", "pour les entreprises",
    "partager", "afficher plus d'options", "candidature simplifiée", "postuler", "enregistrer", "enregistré", "promu",
    "promu par le recruteur", "examine activement les candidatures", "réponses gérées en dehors de linkedin",
    "envoyer un message", "suivre", "signaler cette offre", "s'identifier", "s'inscrire", "nouveau",
    "postuler sur le site de l'entreprise", "voir les détails de la correspondance", "auteur de l'offre d'emploi",
}


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace(" ", " ")).strip()


def _is_ui(line: str) -> bool:
    low = line.lower().replace("’", "'").rstrip(".")
    return (
        low in UI_LINES
        or low in WORKPLACE_WORDS
        or low in EMPLOYMENT_WORDS
        or low.endswith(" logo")
        or low.startswith(("logo de ", "logo of "))
        or bool(APPLICANTS.match(low))
        or low.startswith(("try premium", "retry premium", "essayer premium", "save ", "enregistrer "))
        or bool(re.match(r"^\d+\s*(notifications?|new|nouveaux?)$", low))
    )


@dataclass
class LinkedInFields:
    title: str = ""
    company: str = ""
    location: str = ""
    workplace: str = "unknown"
    internship: bool = False
    description: str = ""


_PAGE_MARKERS = {
    "skip to main content", "my network", "easy apply", "show more options", "promoted by hirer", "report this job",
    "join now", "seniority level", "employment type", "job function", "set alert for similar jobs", "about the company",
    "passer au contenu principal", "candidature simplifiée", "signaler cette offre", "niveau hiérarchique",
    "type d'emploi", "afficher plus d'options", "à propos de l'entreprise",
}


def looks_like_linkedin(text: str) -> bool:
    """True when the text is a LinkedIn job page copied whole (rather than a clean posting)."""
    lines = [_norm(ln).replace("’", "'") for ln in text.split("\n")[:400]]
    if any(DESC_START.match(ln) for ln in lines) and any(_is_ui(ln) or META_LINE.match(ln) for ln in lines):
        return True
    hits = len({ln.lower() for ln in lines} & _PAGE_MARKERS)
    hits += any(APPLICANTS.match(ln) for ln in lines) + any(META_LINE.match(ln) for ln in lines)
    return hits >= 2 or "linkedin.com/jobs" in text.lower()


def workplace_from(text: str) -> str:
    """Remote, hybrid or on-site, from LinkedIn's own labels first, then from the wording."""
    lines = [_norm(ln).lower() for ln in text.split("\n")]
    for ln in lines:
        if ln in WORKPLACE_WORDS:
            return WORKPLACE_WORDS[ln]
    low = " ".join(lines)
    if re.search(r"\b(remote|télétravail|teletravail|à distance)\b", low):
        return "remote"
    if re.search(r"\b(hybrid|hybride)\b", low):
        return "hybrid"
    return "unknown"


def is_internship(text: str) -> bool:
    return any(_norm(ln).lower() in INTERNSHIP_WORDS for ln in text.split("\n"))


def header_facts(header: str) -> tuple[str, bool]:
    """Workplace type and internship flag from the top of a posting, as the button reads it.

    There the labels can share a line ("On-site Internship Easy Apply"), so words are searched for.
    """
    low = _norm(header).lower()
    if re.search(r"\b(hybrid|hybride)\b", low):
        workplace = "hybrid"
    elif re.search(r"\b(remote|télétravail|teletravail)\b|à distance", low):
        workplace = "remote"
    elif re.search(r"\b(on-site|onsite)\b|sur site|sur place", low):
        workplace = "onsite"
    else:
        workplace = "unknown"
    internship = bool(re.search(r"\b(internship|stage|stagiaire|alternance|apprenticeship)\b", low))
    return workplace, internship


def strip_heading(description: str) -> str:
    """Drop a leading "About the job" line (it comes along when the description is read from the page)."""
    lines = description.strip().split("\n")
    while lines and (not lines[0].strip() or DESC_START.match(_norm(lines[0]))):
        lines.pop(0)
    return "\n".join(lines).strip()


def parse_linkedin_text(text: str) -> LinkedInFields:
    """Pull the title, company, location and description out of a copied LinkedIn job page."""
    lines = [ln for ln in (_norm(x) for x in clean_text(text).split("\n")) if ln]
    out = LinkedInFields()
    start = next((i for i, ln in enumerate(lines) if DESC_START.match(ln)), None)
    head = lines[:start] if start is not None else lines[:60]

    meta_at = None
    for i, ln in enumerate(head):
        m = META_LINE.match(ln)
        if m:
            out.location = m.group("loc").strip()
            before = [x for x in head[:i] if not _is_ui(x)]
            out.title = before[-1] if before else ""
            out.company = before[-2] if len(before) > 1 else ""
            meta_at = i
            break
        if AGO_LINE.match(ln):
            before = [x for x in head[:i] if not _is_ui(x)]
            if len(before) >= 3:
                out.title, out.company, out.location = before[-3], before[-2], before[-1]
            elif len(before) == 2:
                out.title, out.company = before
            meta_at = i
            break

    body_from = None
    if start is not None:
        body_from = start + 1
    elif meta_at is not None:
        # Signed-out page: the posting follows the buttons under the date.
        j = meta_at + 1
        while j < len(lines) and (_is_ui(lines[j]) or AGO_LINE.match(lines[j])):
            j += 1
        body_from = j
    if body_from is not None:
        end = next((j for j in range(body_from + 1, len(lines)) if DESC_END.match(lines[j])), len(lines))
        out.description = "\n".join(lines[body_from:end]).strip()

    top = "\n".join(head[: (meta_at or 0) + 12])
    out.workplace = workplace_from(top)
    out.internship = is_internship(top)
    if not out.title:
        out.title = next((x for x in head if not _is_ui(x) and len(x) <= 120), "")
    return out
