"""Fabrication check: how often does tailoring add claims that are not in your CV?

Runs the full agent on each sample CV, tailors bullets for the top N jobs, then compares:
  * verifier OFF = the rewriter's first draft for each bullet (what you would ship without a check)
  * verifier ON  = the final bullet after the rewrite -> verify loop
Automatic metric: share of bullets that add a number or a tool/skill absent from the original.
Also writes a CSV so you can hand-label subtler fabrications (scope, outcomes, seniority).

Usage (from the backend folder):
    python -m eval.fabrication_check --llm      # meaningful numbers need a real LLM
    python -m eval.fabrication_check            # offline: plumbing check only (see note printed)
"""
from __future__ import annotations

import argparse
import csv
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.graph import GRAPH, RunContext  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from app.tailor import deterministic_problems  # noqa: E402
from app.text import clean_text  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--top", type=int, default=3, help="jobs to tailor for, per CV")
    ap.add_argument("--cvs-dir", default=str(BACKEND / "data" / "sample_cvs"))
    ap.add_argument("--out", default=str(BACKEND / "eval" / "fabrication_review.csv"))
    args = ap.parse_args()
    llm = LLMClient() if args.llm else None
    if args.llm and not llm.enabled:
        sys.exit("No LLM configured: set LLM_MODEL / LLM_API_KEY in backend/.env, or drop --llm.")

    rows = []
    for path in sorted(Path(args.cvs_dir).glob("*.txt")):
        cfg = {"configurable": {"thread_id": uuid.uuid4().hex, "ctx": RunContext(llm=llm)}}
        payload = {"cv_text": clean_text(path.read_text(encoding="utf-8")), "options": {"source": "demo", "auto_select": args.top}}
        for _ in GRAPH.stream(payload, cfg, stream_mode="updates"):
            pass
        state = GRAPH.get_state(cfg).values
        titles = {j["id"]: j["title"] for j in state["pool"]}
        for b in state.get("tailored", []):
            first = b["attempts"][0]["text"] if b["attempts"] else b["original"]
            rows.append(
                {
                    "cv": path.stem,
                    "job": titles.get(b["job_id"], b["job_id"]),
                    "evidence_id": b["evidence_id"],
                    "original": b["original"],
                    "verifier_off": first,
                    "verifier_on": b["final"],
                    "off_violation": "; ".join(deterministic_problems(b["original"], first)),
                    "on_violation": "; ".join(deterministic_problems(b["original"], b["final"])),
                    "status": b["status"],
                    "attempts": len(b["attempts"]),
                    "your_label_off (ok/fabricated)": "",
                    "your_label_on (ok/fabricated)": "",
                }
            )
    if not rows:
        sys.exit("Nothing was tailored.")
    off = sum(1 for r in rows if r["off_violation"]) / len(rows)
    on = sum(1 for r in rows if r["on_violation"]) / len(rows)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    mode = f"LLM {settings.llm_model}" if args.llm else "offline rules"
    print(f"Tailored bullets: {len(rows)} ({mode})")
    print("| | Bullets adding numbers/tools not in the original |")
    print("|---|---|")
    print(f"| Verifier off (first draft) | {off:.0%} |")
    print(f"| Verifier on (final) | {on:.0%} |")
    print(f"\nCSV for hand labelling: {args.out}")
    if not args.llm:
        print("\nNote: offline, the first draft is a deliberate keyword-stuffing baseline, so the 'off' number is not a"
              " measurement of any model. Run with --llm for numbers you can put on a resume.")


if __name__ == "__main__":
    main()
