# mypy: ignore-errors
"""Tests for the shared scanner — DG-443.

Every "looks like a real secret" input below is built at test time, never a
whole literal pasted into this file, so nothing here is itself a real-looking
token a secret scanner (gitleaks included) would have reason to flag.
"""

from __future__ import annotations

import base64
import json

import pytest

from core import content_scan
from core.errors import ValidationError


def _jwt() -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": "x"}).encode()).decode().rstrip("=")
    )
    signature = "s" * 27
    return f"eyJ{header}.eyJ{payload}.{signature}"


# -- positives --------------------------------------------------------------


def test_flags_a_github_token_shape() -> None:
    text = "token = " + "ghp_" + "a" * 36
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "token" for f in findings)


def test_flags_an_atlassian_token_shape() -> None:
    text = "ATATT" + "b" * 24
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "token" for f in findings)


def test_flags_a_slack_token_shape() -> None:
    text = "xoxb-" + "1" * 10 + "-" + "2" * 10 + "-" + "c" * 24
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "token" for f in findings)


def test_flags_an_aws_key_shape() -> None:
    text = "AKIA" + "Q" * 16
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "token" for f in findings)


def test_flags_a_jwt_shape() -> None:
    findings = content_scan.scan_text(_jwt(), "f")
    assert any(f.kind == "token" for f in findings)


def test_flags_a_bearer_header() -> None:
    text = "Authorization: Bearer " + "z" * 40
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "token" for f in findings)


def test_flags_a_generic_key_assignment() -> None:
    text = "api_key: " + "w" * 20
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "token" for f in findings)


def test_flags_an_email_address() -> None:
    text = "contact jane.doe@realcorp.test for access"
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "email" for f in findings)


def test_flags_a_windows_drive_path() -> None:
    text = r"C:\Users\argig\.drunken\secrets.json"
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "path" for f in findings)


def test_flags_a_users_path() -> None:
    findings = content_scan.scan_text("/Users/alex/project/.env", "f")
    assert any(f.kind == "path" for f in findings)


def test_flags_a_home_path() -> None:
    findings = content_scan.scan_text("/home/alex/project/.env", "f")
    assert any(f.kind == "path" for f in findings)


def test_flags_userinfo_in_any_scheme() -> None:
    text = "https://alice:" + "s3cr3t-value" + "@jira.example.com/path"
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "userinfo" for f in findings)


def test_flags_an_absolute_file_reference_with_a_drive_letter() -> None:
    text = r"file:///C:/Users/alice/secrets.json"
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "path" for f in findings)


def test_flags_an_absolute_file_reference_users() -> None:
    findings = content_scan.scan_text("file:///Users/alice/secrets.json", "f")
    assert any(f.kind == "path" for f in findings)


def test_flags_an_absolute_file_reference_home() -> None:
    findings = content_scan.scan_text("file:///home/alice/secrets.json", "f")
    assert any(f.kind == "path" for f in findings)


def test_flags_a_token_shaped_literal_scheme_body() -> None:
    text = "literal://" + "ghp_" + "a" * 36
    findings = content_scan.scan_text(text, "f")
    assert any(f.kind == "token" for f in findings)


def test_names_the_right_line_number() -> None:
    text = "one\ntwo\n" + ("ghp_" + "a" * 36) + "\nfour\n"
    findings = content_scan.scan_text(text, "f")
    assert any(f.line == 3 for f in findings)


# -- negatives ----------------------------------------------------------------


def test_does_not_flag_an_env_reference() -> None:
    findings = content_scan.scan_text("env://JIRA_TOKEN_ALPHA", "f")
    assert findings == []


def test_does_not_flag_a_file_reference_with_tilde() -> None:
    findings = content_scan.scan_text("file://~/.drunken/secrets.json#jira.alpha", "f")
    assert findings == []


def test_does_not_flag_an_op_reference() -> None:
    findings = content_scan.scan_text("op://vault/item/field", "f")
    assert findings == []


def test_does_not_flag_a_keyring_reference() -> None:
    findings = content_scan.scan_text("keyring://service/username", "f")
    assert findings == []


def test_does_not_flag_a_bare_tilde_path() -> None:
    findings = content_scan.scan_text("~/.drunken/registry.json", "f")
    assert findings == []


def test_does_not_flag_a_placeholder_email() -> None:
    findings = content_scan.scan_text("<your-email>", "f")
    assert findings == []


def test_does_not_flag_an_example_domain() -> None:
    findings = content_scan.scan_text("reach us at support@example.com", "f")
    assert findings == []


def test_does_not_flag_a_docs_url() -> None:
    findings = content_scan.scan_text("https://code.claude.com/docs/en/memory", "f")
    assert findings == []


def test_does_not_flag_a_relative_file_reference() -> None:
    findings = content_scan.scan_text("file://secrets/jira.json#alpha", "f")
    assert findings == []


# -- scan_file (read + decode) -----------------------------------------------


def test_scan_file_flags_a_nul_byte_as_unscannable(tmp_path) -> None:
    path = tmp_path / "bad.bin"
    path.write_bytes(b"\x00\x01\x02")
    findings = content_scan.scan_file(path, "bad.bin")
    assert findings and findings[0].kind == "unscannable"


def test_scan_file_flags_undecodable_bytes_as_unscannable(tmp_path) -> None:
    path = tmp_path / "bad-utf16.txt"
    path.write_bytes("hello".encode("utf-16"))
    findings = content_scan.scan_file(path, "bad-utf16.txt")
    assert findings and findings[0].kind == "unscannable"


def test_scan_file_strips_a_leading_bom_and_keeps_line_numbers(tmp_path) -> None:
    path = tmp_path / "bom.txt"
    content = "one\ntwo\n" + ("ghp_" + "a" * 36) + "\n"
    path.write_bytes(content.encode("utf-8-sig"))
    findings = content_scan.scan_file(path, "bom.txt")
    assert any(f.line == 3 and f.kind == "token" for f in findings)


def test_scan_file_reads_clean_text_with_no_findings(tmp_path) -> None:
    path = tmp_path / "clean.md"
    path.write_text("Nothing sensitive here.\n", encoding="utf-8")
    assert content_scan.scan_file(path, "clean.md") == []


# -- allowlist ----------------------------------------------------------------


def test_an_explicit_allow_entry_suppresses_one_finding() -> None:
    secret = "ghp_" + "a" * 36
    findings = content_scan.scan_text(secret, "f.md")
    allow = content_scan.parse_allowlist(f"f.md\ttoken\t{secret}\ttest fixture\n")
    assert content_scan.apply_allowlist(findings, allow) == []


def test_an_allow_entry_does_not_suppress_a_different_finding() -> None:
    secret_a = "ghp_" + "a" * 36
    secret_b = "ghp_" + "b" * 36
    text = secret_a + "\n" + secret_b
    findings = content_scan.scan_text(text, "f.md")
    allow = content_scan.parse_allowlist(f"f.md\ttoken\t{secret_a}\ttest fixture\n")
    remaining = content_scan.apply_allowlist(findings, allow)
    assert len(remaining) == 1
    assert remaining[0].matched == secret_b


def test_a_malformed_allowlist_line_is_reported_not_ignored() -> None:
    with pytest.raises(ValidationError):
        content_scan.parse_allowlist("only-two\tfields\n")


def test_an_allowlist_comment_and_blank_lines_are_skipped() -> None:
    allow = content_scan.parse_allowlist("# a comment\n\nf.md\ttoken\tXYZ\treason\n")
    assert ("f.md", "token", "XYZ") in allow
