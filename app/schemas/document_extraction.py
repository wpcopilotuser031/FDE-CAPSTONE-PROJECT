from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CodeItem(BaseModel):
    code: str = Field(..., description="ICD-10 or CPT code string")
    description: str = Field(..., description="Human-readable description of the code")


class DocumentExtractionRequest(BaseModel):
    document_text: str = Field(..., description="Raw text content of the referral document")
    document_id: str | None = Field(default=None, description="Optional document identifier")


class DocumentExtractionResponse(BaseModel):
    document_id: str | None = Field(default=None)
    diagnosis_codes: list[CodeItem] = Field(default_factory=list)
    procedure_codes: list[CodeItem] = Field(default_factory=list)
    clinical_summary: str | None = Field(default=None)
    total_diagnosis_codes: int = Field(default=0)
    total_procedure_codes: int = Field(default=0)
    extraction_method: str = Field(default="unknown")
    extracted_at: str = Field(...)
    decision_trace: dict[str, Any] = Field(default_factory=dict)
