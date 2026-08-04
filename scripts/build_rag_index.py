"""
Force-rebuild the ChromaDB RAG provider index from providers.json.

Run this before starting services to ensure the vector index is
in sync with the current providers.json data:

    python scripts/build_rag_index.py
"""
import sys
from pathlib import Path

# Ensure repo root is on the path so app imports work.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.rag.provider_index import ProviderIndex  # noqa: E402

if __name__ == "__main__":
    print("Rebuilding ChromaDB RAG provider index from providers.json ...")
    index = ProviderIndex()
    index.rebuild()
    count = index.collection.count()
    print(f"Index rebuild complete — {count} providers indexed.")
