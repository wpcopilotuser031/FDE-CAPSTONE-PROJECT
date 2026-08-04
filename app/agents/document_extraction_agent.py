from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from app.agents.llm_gateway import LLMGatewayError, call_llm_json
from app.config import DATA_DIR
from app.data_loader import load_json

DOCUMENT_EXTRACTION_ROLE = "document_code_extraction"

# ICD-10 pattern: letter + 2 digits + optional decimal + 1-4 alphanumeric
_ICD10_PATTERN = re.compile(r"\b([A-TV-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?)\b")

# CPT pattern: exactly 5 digits, optionally followed by one letter modifier
# Covers full CPT range 00100-99499; excludes short runs likely to be dates/IDs
_CPT_PATTERN = re.compile(r"\b((?:[0-9][0-9]{4})[A-Z]?)\b")

_LLM_SYSTEM_PROMPT = (
    "You are a clinical coding specialist. "
    "Analyze the provided referral document text and extract all medical codes found. "
    "Return ONLY a JSON object with this exact structure:\n"
    "{\n"
    '  "diagnosis_codes": [{"code": "ICD-10 code", "description": "description"}],\n'
    '  "procedure_codes": [{"code": "CPT code", "description": "description"}],\n'
    '  "clinical_summary": "one sentence summary of the referral"\n'
    "}\n"
    "For diagnosis_codes extract ICD-10 codes (format: letter + digits, e.g. I10, E11.9, M54.5). "
    "For procedure_codes extract CPT codes (5-digit numeric codes, e.g. 93000, 99213, 72148). "
    "If a code is explicitly mentioned in the document, always include it. "
    "If a code is not present but a condition is described, infer the most likely ICD-10 or CPT code. "
    "Return only the JSON object with no additional text."
)


def _load_icd10_lookup() -> dict[str, str]:
    try:
        return load_json(DATA_DIR / "icd10_codes.json")
    except Exception:  # noqa: BLE001
        return {}


def _load_cpt_lookup() -> dict[str, str]:
    try:
        return load_json(DATA_DIR / "cpt_codes.json")
    except Exception:  # noqa: BLE001
        return {}


def _regex_extract_codes(
    text: str,
    icd10_lookup: dict[str, str],
    cpt_lookup: dict[str, str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Fallback regex-based extraction when LLM is unavailable."""
    diagnosis_codes: list[dict[str, str]] = []
    procedure_codes: list[dict[str, str]] = []

    seen_icd: set[str] = set()
    seen_cpt: set[str] = set()

    for match in _ICD10_PATTERN.finditer(text):
        code = match.group(1).upper()
        if code not in seen_icd:
            seen_icd.add(code)
            description = icd10_lookup.get(code, "Diagnosis code extracted from document")
            diagnosis_codes.append({"code": code, "description": description})

    for match in _CPT_PATTERN.finditer(text):
        code = match.group(1)
        if code not in seen_cpt:
            seen_cpt.add(code)
            description = cpt_lookup.get(code, "Procedure code extracted from document")
            procedure_codes.append({"code": code, "description": description})

    return diagnosis_codes, procedure_codes


def _enrich_with_lookup(
    codes: list[dict[str, str]],
    lookup: dict[str, str],
) -> list[dict[str, str]]:
    """Replace generic LLM descriptions with authoritative lookup descriptions when available."""
    enriched = []
    for item in codes:
        code = item.get("code", "").upper().strip()
        description = lookup.get(code) or item.get("description", "")
        enriched.append({"code": code, "description": description})
    return enriched


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def document_extraction_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Extract ICD-10 diagnosis codes and CPT procedure codes from referral document text.

    Input payload:
        document_text (str, required): Raw text content of the referral document.
        document_id (str, optional): Reference document identifier for audit trail.

    Returns a structured result with diagnosis_codes, procedure_codes, and clinical_summary.
    """
    document_text = str(payload.get("document_text", "")).strip()
    document_id = str(payload.get("document_id", "")).strip()

    decision_trace: dict[str, Any] = {
        "capability": DOCUMENT_EXTRACTION_ROLE,
        "caller_role": DOCUMENT_EXTRACTION_ROLE,
        "mcp_enabled": _use_mcp_tools(),
        "tools_invoked": [],
        "extraction_method": "none",
        "human_review_required": False,
    }

    if not document_text:
        return {
            "document_id": document_id or None,
            "diagnosis_codes": [],
            "procedure_codes": [],
            "clinical_summary": None,
            "missing_information": ["document_text is required"],
            "extracted_at": _utc_now(),
            "decision_trace": decision_trace,
        }

    icd10_lookup = _load_icd10_lookup()
    cpt_lookup = _load_cpt_lookup()

    diagnosis_codes: list[dict[str, str]] = []
    procedure_codes: list[dict[str, str]] = []
    clinical_summary: str | None = None
    llm_used = False

    # Attempt LLM-assisted extraction first
    try:
        user_prompt = (
            f"Referral document text:\n\n{document_text[:4000]}\n\n"
            "Extract all ICD-10 diagnosis codes and CPT procedure codes from the document above."
        )
        llm_result = call_llm_json(_LLM_SYSTEM_PROMPT, user_prompt, max_tokens=600)

        raw_dx = llm_result.get("diagnosis_codes", [])
        raw_px = llm_result.get("procedure_codes", [])
        clinical_summary = str(llm_result.get("clinical_summary", "")).strip() or None

        if isinstance(raw_dx, list) and isinstance(raw_px, list):
            diagnosis_codes = _enrich_with_lookup(raw_dx, icd10_lookup)
            procedure_codes = _enrich_with_lookup(raw_px, cpt_lookup)
            decision_trace["extraction_method"] = "llm"
            decision_trace["tools_invoked"].append("call_llm_json")
            llm_used = True

    except (LLMGatewayError, Exception):  # noqa: BLE001
        # Graceful fallback to regex extraction
        pass

    # If LLM did not produce useful codes, fall back to regex
    if not llm_used or (not diagnosis_codes and not procedure_codes):
        rx_dx, rx_px = _regex_extract_codes(document_text, icd10_lookup, cpt_lookup)
        if not diagnosis_codes:
            diagnosis_codes = rx_dx
        if not procedure_codes:
            procedure_codes = rx_px
        decision_trace["extraction_method"] = "llm+regex_fallback" if llm_used else "regex"

    # Deduplicate codes preserving first occurrence
    seen: set[str] = set()
    unique_dx: list[dict[str, str]] = []
    for item in diagnosis_codes:
        if item["code"] not in seen:
            seen.add(item["code"])
            unique_dx.append(item)

    seen = set()
    unique_px: list[dict[str, str]] = []
    for item in procedure_codes:
        if item["code"] not in seen:
            seen.add(item["code"])
            unique_px.append(item)

    return {
        "document_id": document_id or None,
        "diagnosis_codes": unique_dx,
        "procedure_codes": unique_px,
        "clinical_summary": clinical_summary,
        "total_diagnosis_codes": len(unique_dx),
        "total_procedure_codes": len(unique_px),
        "extracted_at": _utc_now(),
        "decision_trace": decision_trace,
    }


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.document_code_extraction.v1",
        "capability": DOCUMENT_EXTRACTION_ROLE,
        "display_name": "Document Code Extraction Agent",
        "description": (
            "Extracts ICD-10 diagnosis codes and CPT procedure codes from uploaded referral "
            "documents using LLM-assisted analysis with regex-based fallback."
        ),
        "input_contract": {
            "required": ["document_text"],
            "optional": ["document_id"],
        },
        "rbac_role": DOCUMENT_EXTRACTION_ROLE,
        "mcp_tools": ["extract_codes"],
    }


__all__ = [
    "DOCUMENT_EXTRACTION_ROLE",
    "build_agent_card",
    "document_extraction_agent",
]
