"""CV ingestion: PDF text extraction, redaction, evidence segmentation and an offline profile.

Evidence units are always produced deterministically from the CV text (in both modes), so every
quote shown as evidence is verbatim from the CV, never paraphrased by a model.
"""
from __future__ import annotations

import io
import re
from datetime import date

from .roles import ROLE_FAMILIES, family_scores
from .schemas import EvidenceUnit, LanguageSkill, Profile
from .skills import SKILLS, find_languages, find_skills, skills_in
from .text import clean_text, fold, guess_language, split_sentences, strip_bullet


class CVError(ValueError):
    pass


# --- PDF ----------------------------------------------------------------------------------
def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages[:6]]
    except Exception as exc:  # pypdf raises many exception types on broken files
        raise CVError(f"Could not read this PDF ({exc.__class__.__name__}). Paste your CV text instead.") from exc
    text = clean_text("\n".join(pages))
    if len(re.sub(r"\s", "", text)) < 200:
        raise CVError("Almost no text could be extracted (the PDF may be scanned). Paste your CV text instead.")
    return text


# --- Redaction ----------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(r"(?:https?://|www\.)\S+|(?:linkedin\.com|github\.com|gitlab\.com)/\S+", re.I)
PHONE_CAND_RE = re.compile(r"(?<![\w/])\+?\(?\d[\d\s().-]{6,}\d(?![\w/])")
YEAR_RANGE_RE = re.compile(r"^\(?\s*(19|20)\d{2}\s*[-–]\s*(19|20)\d{2}\s*\)?$")
ADDRESS_RE = re.compile(
    r"\b\d{1,4}\s*,?\s*(?:rue|avenue|av\.|street|st\.|road|rd\.|boulevard|bd|blvd|lane|impasse|cité|cite)\b[^\n,;|]*",
    re.I,
)
HEADER_WORDS = {"curriculum", "vitae", "resume", "cv", "profile", "profil", "summary", "experience", "skills"}


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Remove contact details before anything is sent to an LLM. Returns (text, counts)."""
    counts = {"email": 0, "phone": 0, "link": 0, "name": 0, "address": 0}

    def sub(rx: re.Pattern, token: str, kind: str, s: str) -> str:
        def repl(m: re.Match) -> str:
            counts[kind] += 1
            return token

        return rx.sub(repl, s)

    text = sub(EMAIL_RE, "[email]", "email", text)
    text = sub(URL_RE, "[link]", "link", text)

    def phone_repl(m: re.Match) -> str:
        cand = m.group(0)
        digits = re.sub(r"\D", "", cand)
        if not 8 <= len(digits) <= 15 or YEAR_RANGE_RE.match(cand.strip()):
            return cand
        if re.search(r"(19|20)\d{2}\s*[-–]\s*(19|20)\d{2}", cand):
            return cand
        counts["phone"] += 1
        return "[phone]"

    text = PHONE_CAND_RE.sub(phone_repl, text)
    text = sub(ADDRESS_RE, "[address]", "address", text)

    lines = text.split("\n")
    for i, ln in enumerate(lines[:3]):
        s = ln.strip()
        words = s.split()
        if (
            2 <= len(words) <= 4
            and not re.search(r"[\d@\[\]|:,]", s)
            and all(w[:1].isupper() for w in words if w[:1].isalpha())
            and not ({fold(w) for w in words} & HEADER_WORDS)
            and not skills_in(s)
        ):
            name = s
            counts["name"] += 1
            text = text.replace(name, "[name]")
            break
    return text, counts


# --- Sections -----------------------------------------------------------------------------
SECTION_HEADERS: dict[str, list[str]] = {
    "summary": [
        "summary", "professional summary", "profile", "professional profile", "about me", "about", "objective",
        "career objective", "personal statement", "profil", "profil professionnel", "resume", "a propos",
        "a propos de moi", "objectif", "objectif professionnel", "presentation",
    ],
    "experience": [
        "experience", "experiences", "work experience", "professional experience", "employment", "employment history",
        "work history", "internships", "internship", "relevant experience", "experience professionnelle",
        "experiences professionnelles", "parcours professionnel", "stages", "stage", "berufserfahrung",
    ],
    "projects": [
        "projects", "project", "academic projects", "personal projects", "selected projects", "key projects",
        "projets", "projet", "projets academiques", "projets personnels", "realisations", "projets realises",
    ],
    "education": [
        "education", "academic background", "academic record", "formation", "formations", "etudes", "diplomes",
        "cursus", "parcours academique", "ausbildung", "education and training",
    ],
    "skills": [
        "skills", "technical skills", "core skills", "key skills", "competencies", "core competencies", "tools",
        "technologies", "tech stack", "skills and tools", "competences", "competences techniques", "outils",
        "outils et technologies", "savoir-faire", "kenntnisse", "it skills", "software", "logiciels",
    ],
    "certifications": [
        "certifications", "certification", "certificates", "licenses", "licences", "certificats", "trainings",
        "formations complementaires", "courses", "cours",
    ],
    "languages": ["languages", "language", "langues", "langue", "sprachen"],
    "other": [
        "interests", "hobbies", "centres d'interet", "activites", "activities", "extracurricular activities",
        "volunteering", "benevolat", "vie associative", "awards", "honors", "distinctions", "publications",
        "references", "leadership", "achievements",
    ],
}
_HEADER_LOOKUP = {h: sec for sec, hs in SECTION_HEADERS.items() for h in hs}
_HEADER_INLINE_RE = re.compile(
    r"^(" + "|".join(sorted((re.escape(h) for h in _HEADER_LOOKUP), key=len, reverse=True)) + r")\s*[:\-|]\s*(.+)$"
)


def detect_header(line: str) -> tuple[str, str] | None:
    """Return (section, inline_content) if the line is a section heading."""
    s = line.strip().strip("#*_=—-:|•").strip()
    if not s or len(s) > 60:
        return None
    f = re.sub(r"\s+", " ", fold(s)).strip(" :")
    if f in _HEADER_LOOKUP:
        return _HEADER_LOOKUP[f], ""
    m = _HEADER_INLINE_RE.match(f)
    if m:
        content = s[len(s) - len(m.group(2)):].strip()
        return _HEADER_LOOKUP[m.group(1)], content
    return None


MONTHS = {
    "jan": 1, "january": 1, "janv": 1, "janvier": 1, "feb": 2, "february": 2, "fev": 2, "fevr": 2, "fevrier": 2,
    "mar": 3, "march": 3, "mars": 3, "apr": 4, "april": 4, "avr": 4, "avril": 4, "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6, "jul": 7, "july": 7, "juil": 7, "juillet": 7, "aug": 8, "august": 8,
    "aout": 8, "sep": 9, "sept": 9, "september": 9, "septembre": 9, "oct": 10, "october": 10, "octobre": 10,
    "nov": 11, "november": 11, "novembre": 11, "dec": 12, "december": 12, "decembre": 12,
}
_MONTH_RX = "|".join(sorted(MONTHS, key=len, reverse=True))
_POINT = rf"(?:(?:(?P<{{p}}m>{_MONTH_RX})\.?\s+)?(?:(?P<{{p}}n>\d{{1,2}})\s*/\s*)?(?P<{{p}}y>(?:19|20)\d{{2}}))"
_PRESENT = r"(?P<present>present|current|now|today|ongoing|aujourd'hui|present|actuel|actuellement|en cours|heute|date)"
DATE_RANGE_RE = re.compile(
    _POINT.replace("{p}", "a") + r"\s*(?:-|to|a|au|until|jusqu'a|bis)\s*(?:" + _POINT.replace("{p}", "b") + "|" + _PRESENT + ")"
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DURATION_RE = re.compile(r"\(?\b(\d{1,2})\s*(?:months?|mois|monate)\b", re.I)
INTERN_RE = re.compile(
    r"\b(intern|internship|stagiaire|pfe|pfa|apprenti|apprentice|alternance|alternant|werkstudent|praktikum|trainee)\b"
    r"|\bstage\s+(?:de|d'|pfe|pfa|ingenieur|technicien|ouvrier|d'ete|en)\b|^\s*stage\b",
    re.M,
)
STUDENT_RE = re.compile(
    r"\b(student|etudiant|etudiante|eleve[- ]ingenieur|final[- ]year|derniere annee|fin d'etudes|undergraduate|graduating)\b"
)
EDU_ONGOING_RE = re.compile(r"\b(expected|en cours|ongoing|present|aujourd'hui|actuellement)\b")


def _month_index(m: re.Match, p: str) -> int | None:
    y = m.group(f"{p}y")
    if not y:
        return None
    month = 1
    if m.group(f"{p}m"):
        month = MONTHS.get(m.group(f"{p}m").rstrip("."), 1)
    elif m.group(f"{p}n"):
        month = max(1, min(12, int(m.group(f"{p}n"))))
    return int(y) * 12 + month - 1


def date_ranges(text: str) -> list[tuple[int, int]]:
    today = date.today()
    now_idx = today.year * 12 + today.month - 1
    out = []
    for m in DATE_RANGE_RE.finditer(fold(text)):
        a = _month_index(m, "a")
        b = now_idx if m.group("present") else _month_index(m, "b")
        if a is None or b is None:
            continue
        if not (m.group("am") or m.group("an")):  # bare years: "2021 - 2023" ~ mid-2021 to mid-2023
            a += 6
            if not (m.group("present") or m.group("bm") or m.group("bn")):
                b += 5
                if b < a:
                    b = a + 5
        if b >= a:
            out.append((a, min(b, now_idx) + 1))
    return out


def _merge_months(intervals: list[tuple[int, int]]) -> int:
    total, cur = 0, None
    for a, b in sorted(intervals):
        if cur is None:
            cur = [a, b]
        elif a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            total += cur[1] - cur[0]
            cur = [a, b]
    if cur:
        total += cur[1] - cur[0]
    return total


ROLE_WORDS = re.compile(
    r"\b(engineer|ingenieur|intern|stagiaire|analyst|analyste|developer|developpeur|technician|technicien|manager|"
    r"responsable|consultant|scientist|assistant|lead|head|officer|specialist|coordinator|planner|apprenti)\b"
)


def looks_like_meta(line: str) -> bool:
    f = fold(line)
    words = line.split()
    if DATE_RANGE_RE.search(f) or (YEAR_RE.search(f) and len(words) <= 12):
        return True
    if "|" in line and len(words) <= 16:
        return True
    if len(words) <= 9 and ROLE_WORDS.search(f) and not line.rstrip().endswith("."):
        return True
    if len(words) <= 6 and not line.rstrip().endswith((".", ";")):
        caps = sum(1 for w in words if w[:1].isupper())
        return caps >= max(1, len(words) - 1)
    return False


def split_entries(lines: list[str]) -> list[list[str]]:
    """Group experience lines into entries: header/meta lines followed by their bullets."""
    entries: list[list[str]] = []
    cur: list[str] = []
    has_body = False
    for ln in lines:
        if not ln.strip():
            continue
        is_b, content = strip_bullet(ln)
        is_meta = not is_b and looks_like_meta(content)
        if is_meta and has_body and cur:
            entries.append(cur)
            cur, has_body = [], False
        cur.append(ln)
        if not is_meta:
            has_body = True
    if cur:
        entries.append(cur)
    return entries


def _split_long(text: str, limit: int = 420) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for sent in split_sentences(text):
        if cur and len(cur) + len(sent) > limit:
            chunks.append(cur.strip())
            cur = ""
        cur += " " + sent
    if cur.strip():
        chunks.append(cur.strip())
    return chunks or [text[:limit]]


def segment(text: str) -> tuple[list[EvidenceUnit], dict[str, list[str]], list[str]]:
    """Split a (redacted) CV into evidence units. Returns (units, raw section lines, header lines)."""
    sections: dict[str, list[str]] = {}
    order: list[tuple[str, list[str]]] = []
    current = "header"
    buf: list[str] = []
    for ln in text.split("\n"):
        hd = detect_header(ln)
        # "Languages: Python, SQL" inside a skills block is a sub-label, not a new section.
        if hd and hd[1] and (current == "skills" or (hd[0] == "languages" and len(skills_in(hd[1])) >= 2)):
            hd = None
        if hd:
            order.append((current, buf))
            current, buf = hd[0], []
            if hd[1]:
                buf.append(hd[1])
            continue
        buf.append(ln)
    order.append((current, buf))
    for sec, lines in order:
        sections.setdefault(sec, []).extend(lines)

    raw_units: list[tuple[str, str, str, str]] = []  # (section, text, context, kind)
    header_lines = [ln.strip() for ln in sections.get("header", []) if ln.strip()]

    for sec, lines in order:
        lines = [ln for ln in lines if ln.strip()]
        if not lines or sec == "header":
            continue
        if sec == "summary":
            para = " ".join(strip_bullet(ln)[1] for ln in lines)
            for chunk in _split_long(para):
                raw_units.append((sec, chunk, "", "summary"))
        elif sec in ("experience", "projects"):
            meta: list[str] = []
            last_was_bullet = False
            for ln in lines:
                is_b, content = strip_bullet(ln)
                if not content:
                    continue
                ctx = " | ".join(meta[-2:])
                if is_b:
                    raw_units.append((sec, content, ctx, "bullet"))
                    last_was_bullet = True
                    continue
                prev = raw_units[-1] if raw_units and raw_units[-1][0] == sec and last_was_bullet else None
                if prev and (content[:1].islower() or not prev[1].rstrip().endswith((".", "!", "?", ";"))) and not looks_like_meta(content):
                    raw_units[-1] = (prev[0], prev[1].rstrip() + " " + content, prev[2], prev[3])
                elif looks_like_meta(content):
                    if last_was_bullet:
                        meta = []
                    meta.append(content)
                    last_was_bullet = False
                elif len(content.split()) >= 6:
                    raw_units.append((sec, content, ctx, "bullet"))
                    last_was_bullet = True
                else:
                    meta.append(content)
                    last_was_bullet = False
        elif sec == "skills":
            merged: list[str] = []
            for ln in lines:
                content = strip_bullet(ln)[1]
                if not content:
                    continue
                # PDF line wraps: "..., Weibull analysis," + "MTBF/MTTR, RCM basics" / "(SAP PM)" / "de données"
                if merged and (merged[-1].rstrip().endswith((",", "/", "&", "-")) or content[:1].islower() or content[:1] == "("):
                    merged[-1] = merged[-1].rstrip() + " " + content
                else:
                    merged.append(content)
            for content in merged:
                if len(content) >= 2:
                    raw_units.append((sec, content, "", "skills"))
        elif sec == "education":
            entry: list[str] = []
            for ln in lines:
                content = strip_bullet(ln)[1]
                starts_new = bool(YEAR_RE.search(content)) or bool(
                    re.search(r"\b(master|bachelor|licence|engineering degree|diplome|ingenieur|cycle|bac|phd|msc|bsc|degree|baccalaureat)\b", fold(content))
                )
                if entry and starts_new and any(YEAR_RE.search(e) for e in entry):
                    raw_units.append((sec, " — ".join(entry), "", "education"))
                    entry = []
                if entry and not YEAR_RE.search(entry[-1]) and not entry[-1].rstrip().endswith((".", ";", ":", ")")):
                    entry[-1] = entry[-1].rstrip() + " " + content  # a wrapped line
                else:
                    entry.append(content)
            if entry:
                raw_units.append((sec, " — ".join(entry), "", "education"))
        elif sec == "languages":
            raw_units.append((sec, "; ".join(strip_bullet(ln)[1] for ln in lines), "", "languages"))
        else:
            for ln in lines:
                content = strip_bullet(ln)[1]
                if len(content.split()) >= 3:
                    raw_units.append((sec, content, "", "line"))

    if len(raw_units) < 3:  # unstructured CV: fall back to line/sentence units
        raw_units = []
        for ln in text.split("\n")[1:]:
            content = strip_bullet(ln)[1]
            if len(content.split()) >= 5:
                for chunk in _split_long(content):
                    raw_units.append(("other", chunk, "", "line"))

    units: list[EvidenceUnit] = []
    for sec, txt, ctx, kind in raw_units:
        for chunk in _split_long(txt.strip()):
            if len(chunk) >= 3:
                units.append(EvidenceUnit(id=f"E{len(units) + 1}", section=sec, text=chunk, context=ctx, kind=kind))
    return units, sections, header_lines


# --- Offline profile ----------------------------------------------------------------------
KNOWN_PLACES = [
    "Tunis", "Ariana", "Ben Arous", "La Marsa", "Sfax", "Sousse", "Monastir", "Bizerte", "Nabeul", "Gabes", "Gabès",
    "Kairouan", "Tunisia", "Tunisie", "Paris", "Lyon", "Marseille", "Toulouse", "Lille", "Nantes", "Grenoble",
    "France", "Berlin", "Munich", "Hamburg", "Germany", "Montreal", "Montréal", "Quebec", "Canada", "London", "UK",
    "Brussels", "Belgium", "Geneva", "Switzerland", "Casablanca", "Rabat", "Morocco", "Algiers", "Dubai", "Doha",
    "Madrid", "Barcelona", "Milan", "Amsterdam", "Lisbon",
]


def heuristic_profile(text: str, units: list[EvidenceUnit], sections: dict[str, list[str]], header: list[str]) -> Profile:
    found = find_skills(text)
    counts: dict[str, int] = {}
    for h in found:
        counts[h.skill] = counts.get(h.skill, 0) + 1
    skills = sorted(counts, key=lambda s: (-counts[s], s))

    headline = ""
    for ln in header[:5]:
        if "[" in ln or "@" in ln or len(ln) < 4:
            continue
        if any(p.lower() in ln.lower() for p in KNOWN_PLACES) and len(ln.split()) <= 4:
            continue
        headline = ln
        break

    summary_text = " ".join(u.text for u in units if u.section == "summary")
    fam = family_scores(skills, f"{headline} {summary_text}")
    top = [f for f, sc in fam.most_common(3) if sc > 0]
    titles: list[str] = []
    for f in top[:2]:
        titles.extend(ROLE_FAMILIES[f]["titles"])
    if not titles:
        titles = ["engineer"]

    pro: list[tuple[int, int]] = []
    intern: list[tuple[int, int]] = []
    for entry in split_entries(sections.get("experience", [])):
        block = fold("\n".join(entry))
        rngs = date_ranges(block)
        is_intern = bool(INTERN_RE.search(block))
        if not rngs:
            m = DURATION_RE.search(block)
            if m:
                (intern if is_intern else pro).append((0, int(m.group(1))))
            continue
        (intern if is_intern else pro).extend(rngs)
    years = round(_merge_months(pro) / 12, 1)
    intern_months = _merge_months(intern)

    edu_text = fold("\n".join(sections.get("education", [])))
    student = bool(STUDENT_RE.search(fold(f"{headline} {summary_text}"))) or bool(EDU_ONGOING_RE.search(edu_text))
    this_year = date.today().year
    for y in re.findall(r"\b(20\d{2})\b", edu_text):
        if int(y) > this_year or (int(y) == this_year and date.today().month < 7):
            student = True
    if student and years < 1:
        seniority = "student"
    elif years < 2:
        seniority = "junior"
    elif years < 5:
        seniority = "mid"
    elif years < 9:
        seniority = "senior"
    else:
        seniority = "lead"

    lang_src = "\n".join(sections.get("languages", [])) or text
    langs = [LanguageSkill(name=n, level=l) for n, l in sorted(find_languages(lang_src).items(), key=lambda x: -x[1])]

    location = ""
    for ln in header[:6]:
        for place in KNOWN_PLACES:
            if re.search(r"(?<![\w])" + re.escape(place) + r"(?![\w])", ln):
                location = place
                break
        if location:
            break

    education = [u.text for u in units if u.section == "education"][:4]
    domains = [ROLE_FAMILIES[f]["label"] for f in top]
    return Profile(
        headline=headline,
        target_titles=titles,
        skills=skills,
        domains=domains,
        years_experience=years,
        internship_months=intern_months,
        seniority=seniority,
        languages=langs,
        education=education,
        location=location,
        cv_language=guess_language(text),
        source="heuristic",
    )


def known_skill(name: str) -> bool:
    return name in SKILLS
