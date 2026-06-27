import pytest
import pytest_mock
from drunken_team.routes.serve_dashboard import AGENTS_METADATA


def test_agents_metadata() -> None:
    """Ensure all required agents are correctly defined in metadata."""
    assert "principal-engineer" in AGENTS_METADATA
    assert "devops-engineer" in AGENTS_METADATA

    archmage = AGENTS_METADATA["principal-engineer"]
    assert archmage["name"] == "ARCHMAGE"
    assert "Gemini 2.5 Pro" in archmage["model"]


def test_telemetry_endpoint_authorization_fail_safe(
    monkeypatch: pytest.MonkeyPatch, mocker: pytest_mock.MockerFixture
) -> None:
    """Fail-Safe: Should return 500 if server has no EDGE_TELEMETRY_API_KEY"""
    from drunken_team.routes.serve_dashboard import Handler

    monkeypatch.delenv("EDGE_TELEMETRY_API_KEY", raising=False)

    mock_handler = mocker.MagicMock()
    mock_handler.path = "/api/telemetry"
    mock_handler.headers = {"Content-Length": "2"}
    mock_handler.rfile.read.return_value = b"{}"

    # Manually invoke handle_post_telemetry
    Handler.handle_post_telemetry(mock_handler, {})

    mock_handler.send_error_response.assert_called_with(
        "Server is not configured to accept telemetry (missing API key).", code=500
    )


def test_telemetry_endpoint_unauthorized(
    monkeypatch: pytest.MonkeyPatch, mocker: pytest_mock.MockerFixture
) -> None:
    """Should return 401 if client sends invalid API key"""
    from drunken_team.routes.serve_dashboard import Handler

    monkeypatch.setenv("EDGE_TELEMETRY_API_KEY", "secret-key-123")

    mock_handler = mocker.MagicMock()
    mock_handler.path = "/api/telemetry"
    mock_handler.headers = {"Content-Length": "2", "Authorization": "Bearer wrong-key"}
    mock_handler.rfile.read.return_value = b"{}"

    Handler.handle_post_telemetry(mock_handler, {})

    mock_handler.send_error_response.assert_called_with(
        "Unauthorized edge node.", code=401
    )


def test_telemetry_endpoint_authorized(
    monkeypatch: pytest.MonkeyPatch, mocker: pytest_mock.MockerFixture
) -> None:
    """Should return 200/success if client sends correct API key"""
    from drunken_team.routes.serve_dashboard import Handler

    monkeypatch.setenv("EDGE_TELEMETRY_API_KEY", "secret-key-123")

    mock_handler = mocker.MagicMock()
    mock_handler.path = "/api/telemetry"
    mock_handler.headers = {"Content-Length": "2", "X-API-Key": "secret-key-123"}
    mock_handler.rfile.read.return_value = b"{}"

    Handler.handle_post_telemetry(mock_handler, {})

    mock_handler.send_json_response.assert_called_with({"status": "telemetry_accepted"})
