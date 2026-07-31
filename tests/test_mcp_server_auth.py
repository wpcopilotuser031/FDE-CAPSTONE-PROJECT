from app.mcp_server.server import _authorize_tool_call


def test_authorize_tool_call_accepts_allowed_use_case(monkeypatch) -> None:
    monkeypatch.setenv("MCP_INTERNAL_KEY", "test-internal-key")
    _authorize_tool_call("provider_candidates", "specialist_recommendation", "test-internal-key")


def test_authorize_tool_call_rejects_invalid_key(monkeypatch) -> None:
    monkeypatch.setenv("MCP_INTERNAL_KEY", "test-internal-key")
    try:
        _authorize_tool_call("provider_candidates", "specialist_recommendation", "wrong-key")
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "Unauthorized MCP caller" in str(exc)


def test_authorize_tool_call_rejects_disallowed_use_case(monkeypatch) -> None:
    monkeypatch.setenv("MCP_INTERNAL_KEY", "test-internal-key")
    try:
        _authorize_tool_call("insurance_eligibility", "provider_discovery", "test-internal-key")
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not allowed" in str(exc)


def test_authorize_tool_call_rejects_unknown_use_case(monkeypatch) -> None:
    monkeypatch.setenv("MCP_INTERNAL_KEY", "test-internal-key")
    try:
        _authorize_tool_call("provider_candidates", "unknown_use_case", "test-internal-key")
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not recognized" in str(exc)
