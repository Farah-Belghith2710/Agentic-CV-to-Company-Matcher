"""Ranking evaluation: does the requirement-level pipeline rank jobs better than plain similarity?

For every labelled CV, the same labelled postings are ranked by four methods and scored with
NDCG@5 (graded relevance 0/1/2, same definition as sklearn.metrics.ndcg_score):

  1. TF-IDF cosine, whole CV vs whole posting   (the classic keyword baseline)
  2. Embedding cosine, whole CV vs whole posting (the "cosine similarity" idea; needs fastembed)
  3. Hybrid retrieval: BM25 + line-level semantic MaxSim, fused with RRF (this project's shortlist step)
  4. Full pipeline: requirement extraction + evidence judging -> fit score (this project's ranking)

Usage (from the backend folder):
    python -m eval.run_eval                 # offline rules (no API key)
    python -m eval.run_eval --llm           # uses the LLM configured in .env for steps 4
    python -m eval.run_eval --labels my_labels.json --jobs data/my_snapshot.json --cvs-dir my_cvs
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import judge as judge_mod  # noqa: E402
from app import requirements as req_mod  # noqa: E402
from app.config import settings  # noqa: E402
from app.cv_parser import heuristic_profile, redact, segment  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from app.retrieval import FastEmbedSimilarity, get_similarity, shortlist, similarity_status  # noqa: E402
from app.scoring import coverage  # noqa: E402
from app.sources import load_snapshot  # noqa: E402
from app.text import clean_text, tokenize  # noqa: E402


def ndcg_at_k(labels_in_rank_order: list[int], k: int = 5) -> float:
    def dcg(rels: list[int]) -> float:
        return sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))

    ideal = dcg(sorted(labels_in_rank_order, reverse=True))
    return dcg(labels_in_rank_order) / ideal if ideal > 0 else 0.0


def plain_tfidf_scores(cv: str, docs: list[str]) -> np.ndarray:
    toks = [Counter(tokenize(t)) for t in [cv] + docs]
    df: Counter = Counter()
    for t in toks:
        df.update(t.keys())
    vocab = {w: i for i, w in enumerate(df)}
    n = len(toks)
    m = np.zeros((n, len(vocab)), dtype=np.float32)
    for r, t in enumerate(toks):
        for w, c in t.items():
            m[r, vocab[w]] = (1 + math.log(c)) * (math.log((1 + n) / (1 + df[w])) + 1)
    m /= np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
    return m[1:] @ m[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(BACKEND / "eval" / "labels.json"))
    ap.add_argument("--jobs", default=str(settings.snapshot_path))
    ap.add_argument("--cvs-dir", default=str(BACKEND / "data" / "sample_cvs"))
    ap.add_argument("--llm", action="store_true", help="use the configured LLM for requirement extraction and judging")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))["cvs"]
    jobs = {j.id: j for j in load_snapshot(Path(args.jobs))}
    llm = LLMClient() if args.llm else None
    if args.llm and not llm.enabled:
        sys.exit("No LLM configured: set LLM_MODEL / LLM_API_KEY in backend/.env, or drop --llm.")
    sim = get_similarity()
    methods = ["TF-IDF cosine (whole documents)", "Embedding cosine (whole documents)", "Hybrid retrieval (BM25 + MaxSim, RRF)", "Full pipeline (requirement-level fit)"]
    results: dict[str, list[float]] = {m: [] for m in methods}

    for cv_name, cv_labels in labels.items():
        text = clean_text((Path(args.cvs_dir) / f"{cv_name}.txt").read_text(encoding="utf-8"))
        red, _ = redact(text)
        units, sections, header = segment(red)
        profile = heuristic_profile(red, units, sections, header)
        ids = [i for i in cv_labels if i in jobs]
        missing = set(cv_labels) - set(ids)
        if missing:
            print(f"warning: {len(missing)} labelled job ids not found in {args.jobs}")
        docs = [f"{jobs[i].title}\n{jobs[i].description}" for i in ids]
        rel = [cv_labels[i] for i in ids]

        def score(order_scores: np.ndarray | list[float]) -> float:
            order = np.argsort(-np.asarray(order_scores, dtype=float), kind="stable")
            return ndcg_at_k([rel[i] for i in order], args.k)

        results[methods[0]].append(score(plain_tfidf_scores(red, docs)))
        if isinstance(sim, FastEmbedSimilarity):
            results[methods[1]].append(score(sim.matrix(docs, [red])[:, 0]))
        ranked = shortlist([jobs[i] for i in ids], profile, units, k=len(ids))
        rrf = {r.job_id: r.rrf for r in ranked}
        results[methods[2]].append(score([rrf[i] for i in ids]))
        fits = []
        for i in ids:
            jr, _ = req_mod.extract(jobs[i], llm)
            js, _, _ = judge_mod.judge(jr, profile, units, llm, sim, jobs[i].title)
            fit, _, _ = coverage(jr, js)
            fits.append(fit + 1e-3 * rrf[i])  # retrieval breaks ties
        results[methods[3]].append(score(fits))
        print(f"{cv_name}: " + ", ".join(f"{m.split(' (')[0]}={results[m][-1]:.3f}" for m in methods if results[m]))

    print(f"\nNDCG@{args.k} over {len(labels)} CVs x {sum(len(v) for v in labels.values()) // max(1, len(labels))} labelled jobs "
          f"(similarity backend: {similarity_status()}; judging: {'LLM ' + settings.llm_model if args.llm else 'offline rules'})\n")
    print("| Method | NDCG@%d |" % args.k)
    print("|---|---|")
    for m in methods:
        print(f"| {m} | {np.mean(results[m]):.3f} |" if results[m] else f"| {m} | n/a (embedding model unavailable) |")


if __name__ == "__main__":
    main()
