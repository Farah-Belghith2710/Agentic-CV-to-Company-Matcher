"""Save real postings to a snapshot file, so demos and evaluations are reproducible offline.

Examples (from the backend folder):
    python scripts/save_snapshot.py --companies "stripe, notion, jobs.lever.co/palantir" --out data/my_jobs.json
    python scripts/save_snapshot.py --remotive "data analyst" --out data/my_jobs.json

Then set SNAPSHOT_PATH=data/my_jobs.json in .env and pick "Saved snapshot" in the app.
Respect each source's terms: keep snapshots for personal use and credit the source.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sources import SourceError, fetch_board, fetch_remotive, save_snapshot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", default="", help="comma-separated board names or careers URLs")
    ap.add_argument("--remotive", default="", help="a search query for Remotive (remote jobs)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    jobs = []
    for spec in [c.strip() for c in args.companies.split(",") if c.strip()]:
        try:
            desc, found = fetch_board(spec)
            print(f"{desc}: {len(found)} postings")
            jobs += found
        except SourceError as exc:
            print(f"skip {spec}: {exc}")
    if args.remotive:
        found = fetch_remotive(args.remotive)
        print(f"Remotive '{args.remotive}': {len(found)} postings")
        jobs += found
    if not jobs:
        sys.exit("Nothing fetched.")
    save_snapshot(jobs, Path(args.out), note="Saved with scripts/save_snapshot.py; postings belong to their publishers.")
    print(f"Saved {len(jobs)} postings to {args.out}")


if __name__ == "__main__":
    main()
