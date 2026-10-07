"""Download the multilingual embedding model ahead of time (about 220 MB, once).

Usage (from the backend folder, venv active):  python scripts/warm_up.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval import get_similarity, similarity_status  # noqa: E402

sim = get_similarity(log=lambda msg, *a: print(msg))
print("Similarity backend:", similarity_status())
if sim.name != "fastembed":
    print("The embedding model could not be loaded; the app will use TF-IDF. Check your connection or set EMBEDDINGS=tfidf.")
