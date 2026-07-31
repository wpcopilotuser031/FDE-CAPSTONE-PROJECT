from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(..., description="JSON-RPC version. Must be '2.0'.")
    method: str = Field(..., description="JSON-RPC method name.")
    params: dict[str, Any] = Field(default_factory=dict, description="Method parameters.")
    id: str | int | None = Field(default=None, description="Correlation id for request/response pairing.")
