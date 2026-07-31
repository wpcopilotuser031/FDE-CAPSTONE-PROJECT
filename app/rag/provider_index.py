from __future__ import annotations

from typing import Any

import chromadb

from app.config import CHROMA_DIR, COLLECTION_NAME, DATA_DIR
from app.data_loader import load_json
from app.rag.embeddings import HashEmbeddingFunction


class ProviderIndex:
    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.embedding_fn = HashEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
        )

    def rebuild(self) -> None:
        providers = load_json(DATA_DIR / "providers.json")
        existing = self.collection.get(include=[])
        existing_ids = existing.get("ids", [])
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        ids = [provider["provider_id"] for provider in providers]
        docs = [
            " | ".join(
                [
                    provider["provider_name"],
                    provider["specialty"],
                    provider["location"],
                    " ".join(provider["insurance_networks"]),
                    provider.get("bio", ""),
                ]
            )
            for provider in providers
        ]
        metadatas = []
        for provider in providers:
            metadatas.append(
                {
                    "provider_id": provider["provider_id"],
                    "provider_name": provider["provider_name"],
                    "specialty": provider["specialty"],
                    "location": provider["location"],
                    "state": provider["state"],
                    "next_available_date": provider["next_available_date"],
                    "bio": provider.get("bio", ""),
                    "insurance_networks": "|".join(provider["insurance_networks"]),
                }
            )

        self.collection.add(ids=ids, documents=docs, metadatas=metadatas)

    def query(self, text: str, top_k: int = 10) -> list[dict[str, Any]]:
        count = self.collection.count()
        if count == 0:
            self.rebuild()

        results = self.collection.query(query_texts=[text], n_results=top_k)
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        providers: list[dict[str, Any]] = []
        for metadata, distance in zip(metadatas, distances, strict=False):
            provider = dict(metadata)
            provider["insurance_networks"] = provider.get("insurance_networks", "").split("|")
            provider["distance"] = float(distance)
            providers.append(provider)
        return providers
