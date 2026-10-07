"""Retrieval: BM25 + semantic "MaxSim" ranking fused with reciprocal rank fusion (RRF).

Semantic similarity uses a small multilingual embedding model through fastembed (ONNX, no
PyTorch). If it is unavailable (offline, EMBEDDINGS=tfidf), a TF-IDF model is used instead.

Why MaxSim instead of one cosine between the whole CV and the whole posting: whole-document
embeddings blur everything together (and small models truncate long text). Here every posting
line is compared with every CV evidence line, and a posting scores well when most of its lines
find a close match somewhere in the CV.
"""
from __future__ import annotations

import math
import threading
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .config import settings
from .postings import content_chunks
from .roles import query_matches_title
from .schemas import EvidenceUnit, Job, Profile
from .skills import skills_in
from .text import tokenize


# --- Similarity backends ------------------------------------------------------------------
class TfidfSimilarity:
    name = "tfidf"

    @staticmethod
    def _tokens(text: str) -> list[str]:
        words = tokenize(text)
        toks = list(words)
        toks += [f"sk:{s.lower()}" for s in skills_in(text)] * 2
        toks += [f"{a}_{b}" for a, b in zip(words, words[1:])]
        # word-internal 4-grams catch morphology across forms and languages (rail/railway, maintenance/maintenir)
        toks += [f"#{w[i:i + 4]}" for w in words if len(w) >= 4 for i in range(len(w) - 3)]
        return toks

    def matrix(self, a: list[str], b: list[str]) -> np.ndarray:
        docs = [Counter(self._tokens(t)) for t in a + b]
        df: Counter = Counter()
        for d in docs:
            df.update(d.keys())
        n = len(docs)
        vocab = {t: i for i, t in enumerate(df)}
        mat = np.zeros((n, max(1, len(vocab))), dtype=np.float32)
        for r, d in enumerate(docs):
            for t, c in d.items():
                mat[r, vocab[t]] = (1 + math.log(c)) * (math.log((1 + n) / (1 + df[t])) + 1)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        mat = mat / np.where(norms == 0, 1, norms)
        return mat[: len(a)] @ mat[len(a):].T


class FastEmbedSimilarity:
    name = "fastembed"

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name=model_name, cache_dir=str(settings.cache_dir / "models"))
        self._memo: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    def _embed(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if t not in self._memo]
        if missing:
            vecs = list(self.model.embed(missing, batch_size=64))
            with self._lock:
                for t, v in zip(missing, vecs):
                    v = np.asarray(v, dtype=np.float32)
                    self._memo[t] = v / (np.linalg.norm(v) or 1.0)
                if len(self._memo) > 50_000:
                    self._memo.clear()
        return np.stack([self._memo[t] for t in texts]) if texts else np.zeros((0, 1), dtype=np.float32)

    def matrix(self, a: list[str], b: list[str]) -> np.ndarray:
        if not a or not b:
            return np.zeros((len(a), len(b)), dtype=np.float32)
        return self._embed(a) @ self._embed(b).T


_sim = None
_sim_note = "not loaded yet"
_sim_lock = threading.Lock()


def get_similarity(log=None):
    """Return the similarity backend, loading the embedding model on first use."""
    global _sim, _sim_note
    with _sim_lock:
        if _sim is not None:
            return _sim
        if settings.embeddings in ("auto", "fastembed"):
            try:
                if log:
                    log("Loading the multilingual embedding model (the first run downloads about 220 MB)...")
                _sim = FastEmbedSimilarity(settings.embed_model)
                _sim.matrix(["warm up"], ["warm up"])
                _sim_note = f"fastembed ({settings.embed_model.split('/')[-1]})"
                return _sim
            except Exception as exc:  # offline, missing package, download blocked...
                _sim_note = f"tfidf (embeddings unavailable: {exc.__class__.__name__})"
                if log:
                    log(f"Embedding model unavailable ({exc.__class__.__name__}); falling back to TF-IDF.", "warn")
        else:
            _sim_note = "tfidf"
        _sim = TfidfSimilarity()
        return _sim


def similarity_status() -> str:
    return _sim_note


def thresholds(sim) -> tuple[float, float]:
    """(met, partial) cosine thresholds for free-text requirements, per backend."""
    return (0.62, 0.48) if getattr(sim, "name", "") == "fastembed" else (0.38, 0.22)


# --- BM25 ---------------------------------------------------------------------------------
class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tfs = [Counter(d) for d in docs]
        self.lens = np.array([len(d) for d in docs], dtype=np.float32)
        self.avg = float(self.lens.mean()) if len(docs) else 0.0
        df: Counter = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.tfs), dtype=np.float32)
        q = Counter(query)
        for i, tf in enumerate(self.tfs):
            denom_norm = self.k1 * (1 - self.b + self.b * self.lens[i] / (self.avg or 1))
            s = 0.0
            for t, qw in q.items():
                f = tf.get(t)
                if f:
                    s += min(qw, 3) * self.idf.get(t, 0) * f * (self.k1 + 1) / (f + denom_norm)
            out[i] = s
        return out


def _job_tokens(job: Job) -> list[str]:
    text = f"{job.title}\n{job.title}\n{job.description}"
    return tokenize(text) + [f"sk:{s.lower()}" for s in skills_in(text)] * 2


def _cv_query(profile: Profile, units: list[EvidenceUnit]) -> list[str]:
    text = " ".join([profile.headline, " ".join(profile.target_titles)] + [u.text for u in units if u.section != "languages"])
    toks = list(dict.fromkeys(tokenize(text)))
    return toks + [f"sk:{s.lower()}" for s in profile.skills] * 2


# --- Triage & shortlist --------------------------------------------------------------------
@dataclass
class TriageResult:
    relevant: list[str]
    reasons: dict[str, str]
    rejected_titles: list[str]


def triage(jobs: list[Job], queries: list[str], profile: Profile, min_overlap: int | None = None) -> TriageResult:
    """A posting is relevant if a query matches its title, or it shares enough skills with the CV."""
    top_skills = set(profile.skills[:30])
    if min_overlap is None:
        min_overlap = 4 if len(top_skills) >= 12 else 3
    relevant, reasons, rejected = [], {}, []
    for job in jobs:
        hit_q = next((q for q in queries if query_matches_title(q, job.title)), None)
        if hit_q:
            relevant.append(job.id)
            reasons[job.id] = f"title matches '{hit_q}'"
            continue
        overlap = sorted(top_skills & skills_in(f"{job.title}\n{job.description}"))
        if len(overlap) >= min_overlap:
            relevant.append(job.id)
            reasons[job.id] = f"{len(overlap)} shared skills ({', '.join(overlap[:3])})"
        else:
            rejected.append(job.title)
    return TriageResult(relevant, reasons, rejected)


@dataclass
class Ranked:
    job_id: str
    bm25: float
    semantic: float
    rrf: float


def shortlist(jobs: list[Job], profile: Profile, units: list[EvidenceUnit], k: int, log=None) -> list[Ranked]:
    if not jobs:
        return []
    bm = BM25([_job_tokens(j) for j in jobs]).scores(_cv_query(profile, units))
    sim = get_similarity(log)
    cv_texts = [f"{u.context} {u.text}".strip() for u in units if u.section not in ("languages",)] or [profile.headline or "candidate"]
    sem = np.zeros(len(jobs), dtype=np.float32)
    for i, job in enumerate(jobs):
        chunks = [job.title] + content_chunks(job.description)
        m = sim.matrix(chunks, cv_texts)
        best = np.sort(m.max(axis=1))[::-1]
        sem[i] = float(best[: min(8, len(best))].mean())
    r_bm = np.argsort(np.argsort(-bm))
    r_sem = np.argsort(np.argsort(-sem))
    rrf = 1 / (60 + r_bm + 1) + 1 / (60 + r_sem + 1)
    order = np.argsort(-rrf)[:k]
    return [Ranked(jobs[i].id, float(bm[i]), float(sem[i]), float(rrf[i])) for i in order]
