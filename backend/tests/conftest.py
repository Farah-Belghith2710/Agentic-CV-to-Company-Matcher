import os
import sys
import tempfile
from pathlib import Path

# Deterministic, offline, no disk cache, no model downloads.
os.environ["CACHE_ENABLED"] = "false"
os.environ["EMBEDDINGS"] = "tfidf"
os.environ["FORCE_OFFLINE"] = "true"
# Jobs "saved from LinkedIn" during tests go to a throwaway file, never to backend/data.
os.environ["SAVED_PATH"] = os.path.join(tempfile.mkdtemp(prefix="cvm-tests-"), "saved_postings.json")

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

SAMPLES = BACKEND / "data" / "sample_cvs"


def sample_text(name: str) -> str:
    from app.text import clean_text

    return clean_text((SAMPLES / f"{name}.txt").read_text(encoding="utf-8"))
