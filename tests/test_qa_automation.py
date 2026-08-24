from scripts.qa_automation import _matches_ticket_key, _uv_env_error


def test_matches_ticket_key_exact() -> None:
    assert _matches_ticket_key("DG-65", "feature/DG-65-qa-round-integration-gate")
    assert _matches_ticket_key("DG-65", "DG-65: fix the thing")


def test_matches_ticket_key_rejects_substring_of_longer_key() -> None:
    # Regression test: a short ticket key must not match as a substring of
    # a longer one sharing the same prefix (DG-6 is a literal substring of
    # DG-65, DG-60..DG-69), which previously caused the round-integration
    # gate to test/merge/approve the wrong PR under the wrong ticket.
    assert not _matches_ticket_key("DG-6", "feature/DG-65-qa-round-integration-gate")
    assert not _matches_ticket_key("DG-6", "DG-60: something else")
    assert not _matches_ticket_key("DG-6", "DG-600")


def test_matches_ticket_key_rejects_when_preceded_by_alnum() -> None:
    assert not _matches_ticket_key("DG-65", "XDG-65-branch")


def test_matches_ticket_key_matches_at_string_boundaries() -> None:
    assert _matches_ticket_key("DG-6", "DG-6")
    assert _matches_ticket_key("DG-6", "DG-6-fix-thing")


def test_uv_env_error_detects_resolution_failure() -> None:
    # Regression test: a branch cut before a dependency/Python-version fix
    # landed on develop can't resolve its environment via `uv run` at all —
    # that must be reported as an environment problem, not blamed on the
    # ticket's own code as a "Pytest failed" result.
    stderr = (
        "error: No solution found when resolving dependencies:\n"
        "  Because mcp>=1.1.2 depends on Python>=3.10 and your project "
        "requires Python>=3.8, we can conclude that your project's "
        "requirements are unsatisfiable."
    )
    result = _uv_env_error(stderr)
    assert result is not None
    assert "rebased" in result
    assert stderr in result


def test_uv_env_error_ignores_real_test_failures() -> None:
    stderr = "FAILED tests/test_thing.py::test_x - AssertionError: assert 1 == 2"
    assert _uv_env_error(stderr) is None
