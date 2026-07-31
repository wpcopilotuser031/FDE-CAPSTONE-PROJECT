from typing import Any

from fastapi import FastAPI, HTTPException

from app.mcp_server.http_gateway import call_tool_http

app = FastAPI(
    title="Referral MCP HTTP Gateway",
    version="0.1.0",
    description="Dedicated MCP tool gateway with RBAC enforcement over HTTP.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/mcp/call")
def mcp_http_call(payload: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(payload.get("tool_name", "")).strip()
    arguments = payload.get("arguments")

    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required.")
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object.")

    try:
        result = call_tool_http(tool_name, arguments)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"result": result}
