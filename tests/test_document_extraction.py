"""
Tests for Document Code Extraction Agent, MCP tool, and API endpoint.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from app.agents.document_extraction_agent import (
    document_extraction_agent,
    _regex_extract_codes,
    _enrich_with_lookup,
)
from app.mcp_server.tools import extract_diagnosis_and_procedure_codes


# ──────────────────────────────────────────────────────────────
# Sample referral document text
# ──────────────────────────────────────────────────────────────

SAMPLE_DOC = """
REFERRAL DOCUMENT
Patient: John Doe
Diagnoses:
1. Essential hypertension — ICD-10: I10
2. Type 2 diabetes mellitus without complications — ICD-10: E11.9
3. Hyperlipidemia, unspecified — ICD-10: E78.5
Procedures:
1. Routine 12-lead ECG — CPT: 93000
2. Comprehensive metabolic panel — CPT: 80053
3. Hemoglobin A1C — CPT: 83036
"""

MINIMAL_DOC = "Patient has chest pain I25.10 and needs ECG 93000."

EMPTY_DOC = ""


# ──────────────────────────────────────────────────────────────
# Regex extraction tests
# ──────────────────────────────────────────────────────────────

def test_regex_extracts_icd10_codes() -> None:
    icd10_lookup = {"I10": "Essential hypertension", "E11.9": "Type 2 diabetes mellitus"}
    cpt_lookup = {}
    dx, px = _regex_extract_codes(SAMPLE_DOC, icd10_lookup, cpt_lookup)
    codes = [item["code"] for item in dx]
    assert "I10" in codes
    assert "E11.9" in codes


def test_regex_extracts_cpt_codes() -> None:
    icd10_lookup = {}
    cpt_lookup = {"93000": "Electrocardiogram", "80053": "Comprehensive metabolic panel"}
    dx, px = _regex_extract_codes(SAMPLE_DOC, icd10_lookup, cpt_lookup)
    codes = [item["code"] for item in px]
    assert "93000" in codes
    assert "80053" in codes


def test_regex_uses_lookup_description() -> None:
    icd10_lookup = {"I10": "Essential (primary) hypertension"}
    cpt_lookup = {}
    dx, _ = _regex_extract_codes("Patient: I10 hypertension", icd10_lookup, cpt_lookup)
    assert dx[0]["description"] == "Essential (primary) hypertension"


def test_regex_deduplicates_codes() -> None:
    icd10_lookup = {}
    cpt_lookup = {}
    text = "I10 hypertension. Diagnosis: I10. Again: I10."
    dx, _ = _regex_extract_codes(text, icd10_lookup, cpt_lookup)
    assert len([item for item in dx if item["code"] == "I10"]) == 1


# ──────────────────────────────────────────────────────────────
# Agent tests
# ──────────────────────────────────────────────────────────────

def test_agent_requires_document_text() -> None:
    result = document_extraction_agent({})
    assert result["diagnosis_codes"] == []
    assert result["procedure_codes"] == []
    assert "document_text is required" in result["missing_information"]


def test_agent_empty_text_returns_missing() -> None:
    result = document_extraction_agent({"document_text": "  "})
    assert "document_text is required" in result["missing_information"]


def test_agent_regex_fallback_extracts_codes() -> None:
    """When LLM is unavailable, regex fallback should still extract codes."""
    with patch("app.agents.document_extraction_agent.call_llm_json", side_effect=Exception("LLM unavailable")):
        result = document_extraction_agent({"document_text": SAMPLE_DOC})
    dx_codes = [item["code"] for item in result["diagnosis_codes"]]
    px_codes = [item["code"] for item in result["procedure_codes"]]
    assert "I10" in dx_codes
    assert "E11.9" in dx_codes
    assert "93000" in px_codes
    assert result["decision_trace"]["extraction_method"] in {"regex", "llm+regex_fallback"}


def test_agent_llm_extraction(monkeypatch) -> None:
    def mock_llm(*args, **kwargs):
        return {
            "diagnosis_codes": [
                {"code": "I10", "description": "Essential hypertension"},
                {"code": "E11.9", "description": "Type 2 DM"},
            ],
            "procedure_codes": [
                {"code": "93000", "description": "ECG"},
            ],
            "clinical_summary": "Patient referred for cardiac evaluation.",
        }

    monkeypatch.setattr("app.agents.document_extraction_agent.call_llm_json", mock_llm)
    result = document_extraction_agent({"document_text": SAMPLE_DOC})
    assert result["total_diagnosis_codes"] == 2
    assert result["total_procedure_codes"] == 1
    assert result["clinical_summary"] == "Patient referred for cardiac evaluation."
    assert result["decision_trace"]["extraction_method"] == "llm"


def test_agent_preserves_document_id() -> None:
    with patch("app.agents.document_extraction_agent.call_llm_json", side_effect=Exception("LLM unavailable")):
        result = document_extraction_agent({"document_text": MINIMAL_DOC, "document_id": "DOC-TEST-001"})
    assert result["document_id"] == "DOC-TEST-001"


def test_agent_has_decision_trace() -> None:
    with patch("app.agents.document_extraction_agent.call_llm_json", side_effect=Exception("LLM unavailable")):
        result = document_extraction_agent({"document_text": MINIMAL_DOC})
    assert "decision_trace" in result
    assert result["decision_trace"]["capability"] == "document_code_extraction"


def test_agent_has_extracted_at_timestamp() -> None:
    with patch("app.agents.document_extraction_agent.call_llm_json", side_effect=Exception("LLM unavailable")):
        result = document_extraction_agent({"document_text": MINIMAL_DOC})
    assert "extracted_at" in result
    assert result["extracted_at"]  # Non-empty string


# ──────────────────────────────────────────────────────────────
# MCP tool layer tests
# ──────────────────────────────────────────────────────────────

def test_mcp_tool_returns_structured_result() -> None:
    with patch("app.mcp_server.tools.call_llm_json", side_effect=Exception("LLM unavailable")):
        result = extract_diagnosis_and_procedure_codes(SAMPLE_DOC, document_id="DOC-MCP-001")
    assert isinstance(result, dict)
    assert "diagnosis_codes" in result
    assert "procedure_codes" in result
    assert "extracted_at" in result
    assert "extraction_method" in result


def test_mcp_tool_llm_path(monkeypatch) -> None:
    def mock_llm(*args, **kwargs):
        return {
            "diagnosis_codes": [{"code": "I10", "description": "Hypertension"}],
            "procedure_codes": [{"code": "93000", "description": "ECG"}],
            "clinical_summary": "Hypertension referral.",
        }

    monkeypatch.setattr("app.mcp_server.tools.call_llm_json", mock_llm)
    result = extract_diagnosis_and_procedure_codes(SAMPLE_DOC)
    assert result["extraction_method"] == "llm"
    assert result["total_diagnosis_codes"] == 1
    assert result["total_procedure_codes"] == 1


def test_mcp_tool_empty_text() -> None:
    with patch("app.mcp_server.tools.call_llm_json", side_effect=Exception("LLM unavailable")):
        result = extract_diagnosis_and_procedure_codes("")
    assert result["diagnosis_codes"] == []
    assert result["procedure_codes"] == []


# ──────────────────────────────────────────────────────────────
# Enrichment helper
# ──────────────────────────────────────────────────────────────

def test_enrich_replaces_generic_description() -> None:
    lookup = {"I10": "Essential (primary) hypertension"}
    codes = [{"code": "I10", "description": "some llm description"}]
    enriched = _enrich_with_lookup(codes, lookup)
    assert enriched[0]["description"] == "Essential (primary) hypertension"


def test_enrich_keeps_llm_description_when_no_lookup() -> None:
    lookup = {}
    codes = [{"code": "Z99.99", "description": "LLM inferred code"}]
    enriched = _enrich_with_lookup(codes, lookup)
    assert enriched[0]["description"] == "LLM inferred code"
