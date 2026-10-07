"""Text helpers: cleaning, accent folding, HTML to text, tokenizing, language guess."""
from __future__ import annotations

import html
import re
import unicodedata
from functools import lru_cache

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
PUNCT_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", "​": "",
}
BULLET_CHARS = "•●▪◦‣∙·○■□◆◇➢➤►▶✓✔☑❖→⁃*–-"


def is_private_use(ch: str) -> bool:
    return "" <= ch <= ""


def clean_text(text: str) -> str:
    """Normalize ligatures, quotes, dashes and odd PDF bullet glyphs; keep line structure."""
    for a, b in LIGATURES.items():
        text = text.replace(a, b)
    for a, b in PUNCT_MAP.items():
        text = text.replace(a, b)
    # PDF icon fonts (Wingdings, FontAwesome) extract as private-use characters: treat as bullets.
    text = "".join("•" if is_private_use(c) else c for c in text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    lines = [re.sub(r"[ ]{2,}", " ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    blank = 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


@lru_cache(maxsize=8192)
def fold_char(c: str) -> str:
    mapped = PUNCT_MAP.get(c)
    if mapped is not None and len(mapped) == 1:
        return mapped
    decomposed = unicodedata.normalize("NFKD", c)
    base = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    if len(base) != 1:
        base = c
    low = base.lower()
    return low if len(low) == 1 else base


def fold(text: str) -> str:
    """Lowercase + strip accents while keeping the exact same length (1 char -> 1 char)."""
    return "".join(fold_char(c) for c in text)


_TAG_BLOCK = re.compile(r"</?(p|div|br|ul|ol|h[1-6]|tr|table|section|article|header|footer)\b[^>]*>", re.I)
_TAG_LI = re.compile(r"<li\b[^>]*>", re.I)
_TAG_STRONG_LINE = re.compile(r"<(strong|b)\b[^>]*>(.*?)</\1>", re.I | re.S)
_TAG_ANY = re.compile(r"<[^>]+>")


def html_to_text(raw: str | None) -> str:
    """Convert job-board HTML (possibly entity-escaped, as Greenhouse does) to clean text lines."""
    if not raw:
        return ""
    text = raw
    if "&lt;" in text and "<" not in text[:200]:
        text = html.unescape(text)
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.I | re.S)
    text = _TAG_LI.sub("\n• ", text)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = _TAG_BLOCK.sub("\n", text)
    text = _TAG_ANY.sub("", text)
    text = html.unescape(text)
    return clean_text(text)


WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-/]*[a-z0-9+#]|[a-z0-9]")

STOPWORDS = set(
    """
a an the and or of to in on for with at by from as is are be been being was were this that these those it its
our your you we they their them he she his her i me my not no but if then so than too very can will would should
could may might must have has had do does did done into over under about across per via within without also all any
each other more most some such only own same just up out off again further once here there when where why how what
which who whom whose while during before after above below between both few nor s t don now etc e g ie eg
le la les un une des du de d l et ou au aux en dans par pour sur avec sans sous chez est sont etre ete avoir a ce
cet cette ces qui que quoi dont ou se sa son ses leur leurs nos notre votre vos vous nous il elle ils elles on ne
pas plus moins tres tout tous toute toutes comme aussi ainsi afin lors entre vers
der die das und oder ein eine einer eines mit fur von zu im in auf ist sind wir sie du ihr dein deine unser
""".split()
)


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    toks = WORD_RE.findall(fold(text))
    out = []
    for t in toks:
        t = t.strip(".-/")
        if not t or (not keep_stopwords and t in STOPWORDS):
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


_LANG_HINTS = {
    "en": {"the", "and", "with", "you", "will", "for", "our", "experience", "team", "of"},
    "fr": {"le", "la", "les", "et", "des", "avec", "vous", "pour", "une", "nous", "experience", "equipe"},
    "de": {"und", "der", "die", "das", "mit", "sie", "fur", "wir", "ihre", "erfahrung", "du", "dein"},
}


def guess_language(text: str) -> str:
    words = re.findall(r"[a-z]+", fold(text[:4000]))
    if not words:
        return "en"
    scores = {lang: sum(1 for w in words if w in hints) for lang, hints in _LANG_HINTS.items()}
    return max(scores, key=lambda k: scores[k])


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9À-Ý])", text)
    return [p.strip() for p in parts if p.strip()]


def strip_bullet(line: str) -> tuple[bool, str]:
    s = line.strip()
    m = re.match(r"^(?:[" + re.escape(BULLET_CHARS) + r"]+|\(?\d{1,2}[.)])\s+", s)
    if m:
        return True, s[m.end():].strip()
    if s[:1] in "•●▪◦‣∙○■□◆◇➢➤►▶✓✔☑❖" and len(s) > 1:
        return True, s[1:].strip()
    return False, s


def truncate(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"
