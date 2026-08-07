from __future__ import annotations

from typing import Any

import chromadb

from app.config import CHROMA_DIR, DATA_DIR
from app.data_loader import load_json
from app.rag.embeddings import HashEmbeddingFunction

COLLECTION_NAME = "referral_history"


class ReferralHistoryIndex:
    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.embedding_fn = HashEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
        )

    def rebuild(self) -> None:
        referrals = load_json(DATA_DIR / "referrals.json")
        existing = self.collection.get(include=[])
        existing_ids = existing.get("ids", [])
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        ids: list[str] = []
        docs: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for referral in referrals:
            referral_id = str(referral.get("referral_id", "")).strip()
            patient_id = str(referral.get("patient_id", "")).strip()
            diagnosis = str(referral.get("diagnosis", "")).strip()
            specialty = str(referral.get("specialty", "")).strip()
            status = str(referral.get("status", "")).strip()
            priority = str(referral.get("priority", "")).strip()
            submitted_at = str(referral.get("submitted_at", "")).strip()
            missing_docs = referral.get("documents_missing") or []
            missing_text = ", ".join(str(item) for item in missing_docs if str(item).strip()) or "none"

            summary_text = (
                f"Referral {referral_id} for patient {patient_id}: {diagnosis}. "
                f"Specialty: {specialty}. Status: {status}. Priority: {priority}. "
                f"Submitted at {submitted_at}. Missing documents: {missing_text}."
            )

            ids.append(referral_id)
            docs.append(summary_text)
            metadatas.append(
                {
                    "referral_id": referral_id,
                    "patient_id": patient_id,
                    "diagnosis": diagnosis,
                    "specialty": specialty,
                    "status": status,
                    "priority": priority,
                    "submitted_at": submitted_at,
                    "target_wait_days": str(referral.get("target_wait_days", "")),
                    "documents_missing": missing_text,
                    "source_summary": summary_text,
                }
            )

        if ids:
            self.collection.add(ids=ids, documents=docs, metadatas=metadatas)

    def query(self, text: str, top_k: int = 5) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            self.rebuild()

        results = self.collection.query(query_texts=[text], n_results=top_k)
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        entries: list[dict[str, Any]] = []
        for metadata, distance in zip(metadatas, distances, strict=False):
            if not isinstance(metadata, dict):
                continue
            entry = dict(metadata)
            entry["distance"] = float(distance)
            entries.append(entry)
        return entries

    def get_referral(self, referral_id: str) -> dict[str, Any] | None:
        if not referral_id:
            return None
        referrals = load_json(DATA_DIR / "referrals.json")
        referral_id_lower = referral_id.strip().lower()
        for row in referrals:
            if str(row.get("referral_id", "")).strip().lower() == referral_id_lower:
                return dict(row)
        return None

    def get_referrals_for_patient(self, patient_id: str, max_results: int = 20) -> list[dict[str, Any]]:
        if not patient_id:
            return []
        referrals = load_json(DATA_DIR / "referrals.json")
        patient_id_lower = patient_id.strip().lower()
        matched = [dict(row) for row in referrals if str(row.get("patient_id", "")).strip().lower() == patient_id_lower]
        return matched[:max_results]
