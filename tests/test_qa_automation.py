from scripts.qa_automation import _matches_ticket_key


def test_matches_ticket_key_exact() -> None:
    assert _matches_ticket_key("DT-65", "feature/DT-65-qa-round-integration-gate")
    assert _matches_ticket_key("DT-65", "DT-65: fix the thing")


def test_matches_ticket_key_rejects_substring_of_longer_key() -> None:
    # Regression test: a short ticket key must not match as a substring of
    # a longer one sharing the same prefix (DT-6 is a literal substring of
    # DT-65, DT-60..DT-69), which previously caused the round-integration
    # gate to test/merge/approve the wrong PR under the wrong ticket.
    assert not _matches_ticket_key("DT-6", "feature/DT-65-qa-round-integration-gate")
    assert not _matches_ticket_key("DT-6", "DT-60: something else")
    assert not _matches_ticket_key("DT-6", "DT-600")


def test_matches_ticket_key_rejects_when_preceded_by_alnum() -> None:
    assert not _matches_ticket_key("DT-65", "XDT-65-branch")


def test_matches_ticket_key_matches_at_string_boundaries() -> None:
    assert _matches_ticket_key("DT-6", "DT-6")
    assert _matches_ticket_key("DT-6", "DT-6-fix-thing")
