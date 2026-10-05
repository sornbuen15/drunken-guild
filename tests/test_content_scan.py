# mypy: ignore-errors
"""Tests for the shared scanner — DG-443.

Every "looks like a real secret" input below is built at test time, never a
whole literal pasted into this file, so nothing here is itself a real-looking
token a secret scanner (gitleaks included) would have reason to flag.
"""

from __future__ import annotations

import base64
import json
import re

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


# ============================================================================
# DG-443 review round 2 — a parametrized corpus, built at runtime.
#
# Every realistic secret shape below is assembled from pieces at test-call
# time, never a whole literal in this file's own source text, so nothing
# here is itself something gitleaks (or any other scanner run over this
# repository's own history) has reason to flag.
# ============================================================================


def _secret_value(length: int = 20) -> str:
    """A realistic-length, non-placeholder secret *value* — never a key
    name, which is what every "must flag" row below actually tests."""
    return "v3rys3cr3tValue" + "x" * (length - 15)


def _pem_begin_line(kind: str = "RSA ") -> str:
    """A PEM private key's BEGIN line, assembled from pieces rather than
    typed as one literal — ``kind`` is e.g. ``"RSA "``, ``"EC "``, ``""``."""
    dashes = "-" * 5
    return f"{dashes}BEGIN {kind}PRIVATE KEY{dashes}"


def _github_pat() -> str:
    return "github_pat_" + "A" * 22 + "_" + "B" * 59


def _stripe_key(prefix: str = "sk", env: str = "live") -> str:
    return f"{prefix}_{env}_" + "C" * 24


def _slack_webhook() -> str:
    return (
        "https://hooks.slack.com/services/" + "T" * 9 + "/" + "B" * 9 + "/" + "D" * 24
    )


def _google_api_key() -> str:
    return "AIza" + "E" * 35


def _discord_webhook() -> str:
    return "https://discord.com/api/webhooks/" + "1" * 18 + "/" + "F" * 40


def _json_row(key: str, value: str) -> str:
    return json.dumps({key: value})


def _yaml_row(key: str, value: str) -> str:
    return f"{key}: {value}"


def _toml_row(key: str, value: str) -> str:
    return f'{key} = "{value}"'


def _dotenv_row(key: str, value: str) -> str:
    return f"{key}={value}"


def _shell_row(key: str, value: str) -> str:
    return f"export {key}={value}"


def _prose_row(key: str, value: str) -> str:
    """Deliberately *not* a key=value shape — prose mentioning the word,
    never followed by a separator and a value. Used only in the "must NOT
    flag" corpus."""
    return f"Remember to set your {key.replace('_', ' ').lower()} before deploying."


_SENSITIVE_KEY_NAMES = (
    "password",
    "api_key",
    "STRIPE_SECRET_KEY",
    "DB_PASSWORD",
    "AWS_SECRET_ACCESS_KEY",
    "private_key",
    "credential",
    "auth_token",
)

_FORMATS = (
    ("json", _json_row),
    ("yaml", _yaml_row),
    ("toml", _toml_row),
    ("dotenv", _dotenv_row),
    ("shell", _shell_row),
)


def _must_flag_generic_rows() -> list[tuple[str, str]]:
    rows = []
    for key in _SENSITIVE_KEY_NAMES:
        for fmt_name, fmt in _FORMATS:
            rows.append((f"{fmt_name}:{key}", fmt(key, _secret_value())))
    return rows


def _must_flag_dedicated_rows() -> list[tuple[str, str]]:
    return [
        ("pem_rsa", _pem_begin_line("RSA ")),
        ("pem_ec", _pem_begin_line("EC ")),
        ("pem_openssh", _pem_begin_line("OPENSSH ")),
        ("pem_generic", _pem_begin_line("")),
        ("github_pat", _github_pat()),
        ("stripe_sk_live", _stripe_key("sk", "live")),
        ("stripe_sk_test", _stripe_key("sk", "test")),
        ("stripe_rk_live", _stripe_key("rk", "live")),
        ("slack_webhook", _slack_webhook()),
        ("google_api_key", _google_api_key()),
        ("discord_webhook", _discord_webhook()),
        ("unc_path", r"\\fileserver\share\secrets\keys.json"),
        ("root_path", "/root/.ssh/id_rsa"),
        ("mnt_path", "/mnt/c/Users/alice/.drunken/secrets.json"),
    ]


@pytest.mark.parametrize(
    "case_id,text",
    _must_flag_generic_rows(),
    ids=lambda v: v if isinstance(v, str) else v,
)
def test_must_flag_generic_key_value_corpus(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings, f"{case_id!r} ({text!r}) was not flagged at all"


@pytest.mark.parametrize("case_id,text", _must_flag_dedicated_rows())
def test_must_flag_dedicated_pattern_corpus(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings, f"{case_id!r} ({text!r}) was not flagged at all"


def _must_not_flag_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("example_domain_email", "reach us at support@example.com"),
        ("ssh_user_host", "ssh user@host"),
        ("home_env_var", "$HOME/x"),
        ("tilde_path", "~/x"),
        ("env_reference", "env://JIRA_TOKEN"),
        ("op_reference", "op://vault/item/field"),
        ("file_tilde_reference", "file://~/.drunken/secrets.json#jira.alpha"),
        ("empty_dotenv_value", "API_KEY="),
        ("empty_json_value", _json_row("password", "")),
        ("templated_json_value", json.dumps({"password": "${SECRET}"})),
    ]
    for key in ("password", "api_key", "STRIPE_SECRET_KEY"):
        rows.append((f"prose:{key}", _prose_row(key, "")))
    return rows


@pytest.mark.parametrize("case_id,text", _must_not_flag_rows())
def test_must_not_flag_corpus(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings == [], f"{case_id!r} ({text!r}) was wrongly flagged: {findings}"


# -- mutations: each new pattern, removed, turns its row(s) red -------------


def test_mutation_removing_the_generic_assignment_rule_misses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        content_scan, "_GENERIC_ASSIGNMENT_RE", re_compile_never_matches()
    )
    text = _json_row("password", _secret_value())
    assert content_scan.scan_text(text, "f") == []


def test_mutation_removing_the_pem_pattern_misses_a_pem_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patterns = tuple(
        p
        for p in content_scan._TOKEN_PATTERNS  # noqa: SLF001
        if "PRIVATE KEY" not in p.pattern
    )
    monkeypatch.setattr(content_scan, "_TOKEN_PATTERNS", patterns)
    assert content_scan.scan_text(_pem_begin_line(), "f") == []


def test_mutation_removing_the_github_pat_pattern_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patterns = tuple(
        p
        for p in content_scan._TOKEN_PATTERNS  # noqa: SLF001
        if "github_pat_" not in p.pattern
    )
    monkeypatch.setattr(content_scan, "_TOKEN_PATTERNS", patterns)
    assert content_scan.scan_text(_github_pat(), "f") == []


def test_mutation_removing_the_stripe_pattern_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patterns = tuple(
        p
        for p in content_scan._TOKEN_PATTERNS  # noqa: SLF001
        if "sk_(?:live" not in p.pattern
    )
    monkeypatch.setattr(content_scan, "_TOKEN_PATTERNS", patterns)
    assert content_scan.scan_text(_stripe_key(), "f") == []


def test_mutation_removing_the_mnt_path_alternative_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrowed = re.compile(
        r"(?:(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'<>]*|/Users/[^\s\"'<>]*|/home/[^\s\"'<>]*)"
    )
    monkeypatch.setattr(content_scan, "_PATH_RE", narrowed)
    assert content_scan.scan_text("/mnt/c/drunken/secrets.json", "f") == []


def re_compile_never_matches() -> "re.Pattern[str]":
    return re.compile(r"(?!)")


# ============================================================================
# DG-443 review round 3 — curl/wget basic-auth flags, cloud connection
# strings/headers, multi-line YAML/JSON values, netrc, and the allowlist's
# quote-style robustness. Same rule as round 2: every secret-shaped input
# built at test time, nothing real-looking in this file's own source text.
# ============================================================================


def _curl_cmd(flag: str, sep: str, value: str) -> str:
    """Assembles a curl basic-auth command line from pieces joined at
    *call* time, never as one contiguous ``flag`` + username + ``:`` +
    password literal in this file's own source — gitleaks' own default
    ruleset has a rule for exactly that shape, and a synthetic value built
    at runtime does not stop it matching *source text* that happens to
    read that way. Joining the pieces with ``+`` keeps the file's literal
    text free of the shape while the string this test actually scans is
    assembled identically either way.
    """
    user_part = "alice" + ":" + value
    return "curl " + flag + sep + user_part + " " + "https://example.atlassian.net"


def _curl_basic_auth_rows() -> list[tuple[str, str]]:
    value = _secret_value()
    return [
        ("curl_dash_u_space", _curl_cmd("-u", " ", value)),
        ("curl_dash_u_eq", _curl_cmd("-u", "=", value)),
        ("curl_user_long", _curl_cmd("--user", " ", value)),
        ("curl_user_long_eq", _curl_cmd("--user", "=", value)),
        ("wget_dash_u", "wget " + _curl_cmd("-u", " ", value)[len("curl ") :]),
        ("curl_password_space", "curl --password " + value + " https://x"),
        ("curl_password_eq", "curl --password=" + value + " https://x"),
        ("curl_http_password", "curl --http-password " + value + " https://x"),
    ]


def _curl_basic_auth_negative_rows() -> list[tuple[str, str]]:
    return [
        ("curl_dash_u_no_value", "curl -u https://example.atlassian.net"),
        ("ls_dash_u_unrelated_flag", "ls -u /some/directory"),
        ("curl_user_no_colon", "curl --user aliceonly https://example.atlassian.net"),
    ]


@pytest.mark.parametrize("case_id,text", _curl_basic_auth_rows())
def test_must_flag_curl_basic_auth_corpus(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings, f"{case_id!r} ({text!r}) was not flagged at all"


@pytest.mark.parametrize("case_id,text", _curl_basic_auth_negative_rows())
def test_must_not_flag_curl_basic_auth_negatives(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings == [], f"{case_id!r} ({text!r}) was wrongly flagged: {findings}"


def test_mutation_removing_the_curl_user_pattern_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patterns = tuple(
        p
        for p in content_scan._TOKEN_PATTERNS  # noqa: SLF001
        if "-u|--user" not in p.pattern
    )
    monkeypatch.setattr(content_scan, "_TOKEN_PATTERNS", patterns)
    text = _curl_cmd("-u", " ", _secret_value())
    assert content_scan.scan_text(text, "f") == []


def test_mutation_removing_the_curl_password_pattern_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patterns = tuple(
        p
        for p in content_scan._TOKEN_PATTERNS  # noqa: SLF001
        if "http-)?password" not in p.pattern
    )
    monkeypatch.setattr(content_scan, "_TOKEN_PATTERNS", patterns)
    assert (
        content_scan.scan_text(f"curl --password {_secret_value()} https://x", "f")
        == []
    )


# -- cloud connection strings / headers --------------------------------------


def _cloud_rows() -> list[tuple[str, str]]:
    value = "Q" * 32 + "=="
    return [
        ("azure_account_key", f"AccountKey={value}"),
        ("azure_shared_access_key", f"SharedAccessKey={value}"),
        ("azure_sas_signature_kv", f"SharedAccessSignature={value}"),
        (
            "sas_sig_query_string",
            f"https://x.blob.core.windows.net/c?sig={value}&se=2030",
        ),
        (
            "azure_connection_string",
            f"DefaultEndpointsProtocol=https;AccountName=acct;AccountKey={value}",
        ),
    ]


def _cloud_negative_rows() -> list[tuple[str, str]]:
    return [
        ("azure_account_key_empty", "AccountKey="),
        ("sig_as_prose", "the sig looked wrong in the diff, please check it"),
    ]


@pytest.mark.parametrize("case_id,text", _cloud_rows())
def test_must_flag_cloud_connection_string_corpus(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings, f"{case_id!r} ({text!r}) was not flagged at all"


@pytest.mark.parametrize("case_id,text", _cloud_negative_rows())
def test_must_not_flag_cloud_connection_string_negatives(
    case_id: str, text: str
) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings == [], f"{case_id!r} ({text!r}) was wrongly flagged: {findings}"


def test_mutation_removing_the_account_key_pattern_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patterns = tuple(
        p
        for p in content_scan._TOKEN_PATTERNS  # noqa: SLF001
        if "AccountKey" not in p.pattern
    )
    monkeypatch.setattr(content_scan, "_TOKEN_PATTERNS", patterns)
    assert content_scan.scan_text("AccountKey=" + "Q" * 32, "f") == []


def test_mutation_removing_the_sas_sig_pattern_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patterns = tuple(
        p
        for p in content_scan._TOKEN_PATTERNS  # noqa: SLF001
        if "[?&]sig=" not in p.pattern
    )
    monkeypatch.setattr(content_scan, "_TOKEN_PATTERNS", patterns)
    text = "https://x.blob.core.windows.net/c?sig=" + "Q" * 20
    assert content_scan.scan_text(text, "f") == []


# -- multi-line YAML block scalar / JSON value-on-next-line ------------------


def _multiline_rows() -> list[tuple[str, str]]:
    value = _secret_value()
    return [
        ("yaml_block_literal", f"password: |\n  {value}\n"),
        ("yaml_block_folded_strip", f"api_key: >-\n  {value}\n"),
        ("json_value_next_line", '"password":\n  "' + value + '"\n'),
    ]


def _multiline_negative_rows() -> list[tuple[str, str]]:
    return [
        ("yaml_block_non_sensitive_key", f"description: |\n  {_secret_value()}\n"),
        ("yaml_block_empty", "password: |\n\nnext_key: fine\n"),
    ]


@pytest.mark.parametrize("case_id,text", _multiline_rows())
def test_must_flag_multiline_value_corpus(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings, f"{case_id!r} ({text!r}) was not flagged at all"
    assert findings[0].line == 1, (
        f"{case_id!r}: must report the KEY line, not the value line. Got {findings}"
    )


@pytest.mark.parametrize("case_id,text", _multiline_negative_rows())
def test_must_not_flag_multiline_negatives(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings == [], f"{case_id!r} ({text!r}) was wrongly flagged: {findings}"


def test_mutation_removing_the_lookahead_misses_the_yaml_block_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(content_scan, "_KEY_ONLY_RE", re.compile(r"(?!)"))
    text = f"password: |\n  {_secret_value()}\n"
    assert content_scan.scan_text(text, "f") == []


# -- netrc ---------------------------------------------------------------


def _netrc_rows() -> list[tuple[str, str]]:
    value = _secret_value()
    return [
        (
            "netrc_machine_line",
            f"machine example.atlassian.net login alice password {value}",
        ),
        ("netrc_password_only_line", f"password {value}"),
        ("netrc_default_line", f"default login alice password {value}"),
    ]


def _netrc_negative_rows() -> list[tuple[str, str]]:
    return [
        ("prose_not_netrc_shaped", f"the password manager stored {('x' * 10)} safely"),
    ]


@pytest.mark.parametrize("case_id,text", _netrc_rows())
def test_must_flag_netrc_corpus(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings, f"{case_id!r} ({text!r}) was not flagged at all"


@pytest.mark.parametrize("case_id,text", _netrc_negative_rows())
def test_must_not_flag_netrc_negatives(case_id: str, text: str) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings == [], f"{case_id!r} ({text!r}) was wrongly flagged: {findings}"


def test_mutation_removing_the_netrc_rule_misses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(content_scan, "_NETRC_LINE_RE", re.compile(r"(?!)"))
    text = f"machine example.atlassian.net login alice password {_secret_value()}"
    assert content_scan.scan_text(text, "f") == []


# -- allowlist quote-style robustness ----------------------------------------


def test_allowlist_matches_regardless_of_quote_style_on_either_side() -> None:
    text = _json_row("password", _secret_value())
    findings = content_scan.scan_text(text, "f.json")
    assert findings and findings[0].kind == "token"

    # The allowlist entry names the *value*, quoted differently than
    # scan_text itself stored it internally.
    allow = content_scan.parse_allowlist(
        f'f.json\ttoken\t"{_secret_value()}"\treason\n'
    )
    assert content_scan.apply_allowlist(findings, allow) == []


def test_allowlist_unquoted_entry_matches_a_quoted_finding() -> None:
    text = _json_row("password", _secret_value())
    findings = content_scan.scan_text(text, "f.json")

    allow = content_scan.parse_allowlist(f"f.json\ttoken\t{_secret_value()}\treason\n")
    assert content_scan.apply_allowlist(findings, allow) == []


# -- already covered by the existing generic rule (hyphen is already in the
# key-name prefix/suffix character class) — documented with a test, not a
# new pattern.


@pytest.mark.parametrize(
    "case_id,text",
    [
        ("x_api_key_header", "X-Api-Key: " + _secret_value()),
        ("x_auth_token_header", "X-Auth-Token: " + _secret_value()),
        ("client_secret_key", "client_secret: " + _secret_value()),
    ],
)
def test_header_and_client_secret_style_keys_already_flag(
    case_id: str, text: str
) -> None:
    findings = content_scan.scan_text(text, "f")
    assert findings, f"{case_id!r} ({text!r}) was not flagged at all"
