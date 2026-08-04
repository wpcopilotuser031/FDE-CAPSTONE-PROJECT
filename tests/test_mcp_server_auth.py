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


def test_authorize_insurance_tools_allow_care_agent_user_role(monkeypatch) -> None:
    monkeypatch.setenv("MCP_INTERNAL_KEY", "test-internal-key")
    _authorize_tool_call(
        "patient_insurance_profile",
        "insurance_validation",
        "test-internal-key",
        user_role="care_agent",
    )


def test_authorize_insurance_tools_reject_provider_user_role(monkeypatch) -> None:
    monkeypatch.setenv("MCP_INTERNAL_KEY", "test-internal-key")
    try:
        _authorize_tool_call(
            "insurance_eligibility",
            "insurance_validation",
            "test-internal-key",
            user_role="provider",
        )
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not permitted" in str(exc)
