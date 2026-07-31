from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


class LLMGatewayError(RuntimeError):
    pass


# Ensure .env is loaded for direct Streamlit execution paths.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)


def _gateway_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/v1/messages"


def _extract_json_text(raw_text: str) -> str:
    # Accept strict JSON response or JSON inside fenced code blocks.
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    stripped = raw_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return stripped[first_brace : last_brace + 1].strip()

    return stripped


def call_llm_json(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> dict[str, Any]:
    model = (os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL") or "").strip()
    api_key = (os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "").strip()
    base_url = (os.getenv("LLM_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL") or "").strip()

    if not model or not api_key or not base_url:
        raise LLMGatewayError("LLM environment variables are not configured.")

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": user_prompt}],
        "system": system_prompt,
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(_gateway_endpoint(base_url), headers=headers, json=payload)
            response.raise_for_status()
            response_json = response.json()
    except Exception as exc:  # noqa: BLE001
        raise LLMGatewayError(f"LLM gateway call failed: {exc}") from exc

    content = response_json.get("content", [])
    text_chunks = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_chunks.append(block.get("text", ""))

    raw_text = "\n".join(chunk for chunk in text_chunks if chunk).strip()
    if not raw_text:
        raise LLMGatewayError("LLM returned an empty response.")

    json_text = _extract_json_text(raw_text)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise LLMGatewayError("LLM did not return valid JSON.") from exc
