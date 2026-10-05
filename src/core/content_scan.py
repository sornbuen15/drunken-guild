"""One content scanner for a credential, an identity or a real machine path
landing somewhere it should not — DG-443, applying the Boss's rule: an
AI-layer file "may live in the config repo and be copied in, provided it
holds no credential, no identity and no real path."

**One implementation, two callers.** :mod:`core.layer_copy` calls this before
a single byte is copied from the config repo into a project (refuses);
:mod:`core.doctor` calls the same functions, read-only, against files already
sitting in a project's checkout (flags). Neither grows its own regex.

**Three kinds of finding, plus one non-finding that still refuses:**

* ``token`` — a credential-shaped literal: a GitHub/Atlassian/Slack/AWS token,
  a JWT, a ``Bearer``/``Basic`` header, or a generic
  ``api_key = <something long>`` assignment.
* ``userinfo`` — ``scheme://user:secret@host``, for *any* scheme — a
  credential embedded in a URL is still a credential even behind a scheme
  this module otherwise treats as a safe reference.
* ``email`` — an e-mail address, i.e. an identity. RFC 2606's reserved
  documentation domains (``example.com``/``.org``/``.net``) are exempt, since
  those are never a real person's address.
* ``path`` — a real, machine-specific absolute path: a drive letter,
  ``/Users/`` or ``/home/``. ``~/...`` is never flagged — it is portable by
  construction, which is exactly why :mod:`core.secrets`' own examples use it.
* a file that cannot be read as text at all (a NUL byte, or a decode failure)
  is **not** silently skipped — see :func:`scan_file`.

**Why `scheme://` is not simply masked away (DG-443 review, comment 11482).**
An earlier draft of this module masked *every* `env://`, `file://`, `op://`,
`keyring://` and `literal://` span before running the email/path checks, so
that a legitimate reference like ``file://~/.drunken/secrets.json#jira.alpha``
never tripped the path check on its own body. That is too generous:
``file:///C:/Users/alice/secrets.json`` and ``file:///home/alice/.env`` are
schemes too, and they *are* real, machine-specific paths — masking the whole
match would have let exactly the leak this module exists to catch walk
through disguised behind three slashes. ``file://`` is therefore only masked
when its body looks like a reference (``~/...`` or a plain relative path);
an absolute body is left exposed to the path check. ``literal://`` is never
masked at all: it is "the deliberate, visible way to inline a *non-secret*
value" (:mod:`core.secrets`), so a real token typed after it is still a real
token, not a reference the author gets a free pass on.

**The generic key=value rule matches the *name*, not the whole word (DG-443
review round 2).** ``\bpassword\b`` never fires inside ``DB_PASSWORD`` —
``\b`` needs a transition between a word character and a non-word one, and
``_`` is itself a word character, so there is no boundary either side of
``PASSWORD`` in ``DB_PASSWORD=...``. The sensitive-name check below matches
the name as a *substring* instead (still case-insensitive), so
``STRIPE_SECRET_KEY=``, ``DB_PASSWORD=`` and ``AWS_SECRET_ACCESS_KEY=`` all
still fire — the cost is a key like ``passwordless_login: true`` also
matching, which an empty-or-reference-shaped value (see
:func:`_looks_like_a_real_value`) still has to clear before it is a finding.

**Known false positive, accepted rather than special-cased (LOW, DG-443
review round 2).** ``https://user@github.com/repo`` reads as the e-mail
``user@github.com`` — a bare userinfo segment with no password looks exactly
like ``local-part@domain`` once the ``https://`` in front of it is not
itself masked (only `env://`/`op://`/`keyring://`/a portable `file://` are).
Accepted: narrowing the email pattern to somehow tell "a URL's username" from
"a real address" generically is not attempted here, and the cost is one
extra, honest refusal naming a file — not a missed credential.

**THE LIMIT, STATED PLAINLY (DG-443 review round 3).** This module is a
line-oriented, pattern-based *defence in depth* control, not a guarantee.
It cannot and does not promise to catch every way a credential could be
written — an unknown provider's token shape, one split across more than
two lines, one built at runtime by concatenation, one encoded in a form
none of these patterns recognise. **The primary control is that the
config repo is the Boss's own private repository** (REQ-020); this module
exists to catch an honest mistake on the way in and on re-scan, not to be
the only thing standing between a real credential and exposure. Nothing in
this module's own text, nor any caller's remediation message, should ever
say or imply "safe" or "clean" about content that passed every pattern
here — only that no *known* shape was found.

**`-u` is not a substring of `-su` (DG-443 review round 4).** Round 3's
curl/wget rule matched only the bare `-u`/`--user` flag — a short-option
*cluster* ending in `u` (`-su`, `-sSu`, `-fsSu`, `-sSLu`, curl/wget's own
convention for combining single-letter flags) was invisible to it, and
was reproduced end to end: copied in, unredacted, by `drunken-init
--config-repo`, with `drunken-doctor` reporting the result clean. Fixed
by matching any `-[A-Za-z]*u` cluster, not only the two literal flags,
with a lookbehind so this never fires inside a longer word. The same
fix also makes the separator between the flag and the value properly
optional — `-u"name:pass"`, glued on with no space or `=` at all, did
not match the old pattern either.

**PowerShell literals (DG-443 review round 4), narrowly.** A quoted
literal next to `ConvertTo-SecureString ... -AsPlainText` or inside a
`PSCredential(...)` call is exactly as much "a credential typed where
only a reference belongs" as any other shape here — `$var`/`Read-Host`
(reading it from the environment or the operator, not typing it) never
match, because there is no quoted literal on that line for either rule
to find at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, FrozenSet, Iterable, Sequence, Tuple

from .errors import ValidationError

#: The sibling file, in a config repo project folder, that names an exact,
#: explained exception to one specific finding — never a blanket switch.
#: See :func:`parse_allowlist`. Never copied into a project: it is not on
#: :mod:`core.ai_layer`'s list, so the existing walk already skips it.
ALLOWLIST_FILENAME: Final = ".drunken-scan-allow"

Kind = str  # "token" | "userinfo" | "email" | "path" | "unscannable"


@dataclass(frozen=True)
class Finding:
    """One thing :func:`scan_text` would refuse on.

    ``matched`` is the raw text that tripped the pattern — kept only for the
    allowlist's exact-text comparison and deliberately never put in a message
    a caller prints; use :meth:`describe` for that.
    """

    file: str
    line: int
    kind: Kind
    matched: str

    def describe(self) -> str:
        """A safe-to-print summary: shape and length, never the value."""
        if self.kind == "unscannable":
            return f"{self.file}:{self.line}: cannot scan {self.file}: not UTF-8 text"
        return (
            f"{self.file}:{self.line}: looks like a {self.kind}-shaped value "
            f"({len(self.matched)} characters) — refusing rather than guessing "
            "it is safe."
        )


AllowEntry = Tuple[str, str, str]  # (relative_file, kind, exact_text)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # GitHub classic (ghp_/gho_/ghu_/ghs_/ghr_) and fine-grained PATs.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}\b"),  # Atlassian
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),  # Slack token
    re.compile(
        r"\bhooks\.slack\.com/services/[A-Za-z0-9]+/[A-Za-z0-9]+/[A-Za-z0-9]+\b"
    ),  # Slack incoming webhook
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{10,}\b"),  # Stripe secret key
    re.compile(r"\brk_(?:live|test)_[A-Za-z0-9]{10,}\b"),  # Stripe restricted key
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),  # Google API key
    re.compile(
        r"\bdiscord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]+\b"
    ),  # Discord webhook
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),  # JWT
    # Discord bot token: three dot-separated base64url segments (also how a
    # JWT looks, shape-for-shape — a line can trip both; that is tolerated
    # rather than engineered around, since either reading still refuses).
    re.compile(r"\b[A-Za-z0-9_\-]{24,28}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{16,}=*"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{16,}"),
    # A PEM private key's own BEGIN line — the line alone is enough; the key
    # material that follows does not need to be present or matched.
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(r"(?i)--(?:http-)?password[ =]+\S{4,}"),
    # Azure (and Azure-shaped SAS) connection strings and signatures — not
    # covered by the generic sensitive-key rule, which only recognises a
    # bare `key`/`secret`/`token`/... name, not Azure's own compound names.
    re.compile(r"(?i)\bAccountKey\s*=\s*\S{20,}"),
    re.compile(r"(?i)\bSharedAccessKey\s*=\s*\S{10,}"),
    re.compile(r"(?i)\bSharedAccessSignature\s*=\s*\S{10,}"),
    re.compile(r"[?&]sig=[A-Za-z0-9%+/=]{10,}"),  # a SAS signature in a URL
)

#: Key *names* (DG-443 review round 2) this module treats as sensitive when
#: found immediately before a ``:``/``=`` assignment — JSON (`"key": "value"`),
#: YAML (`key: value`), TOML/INI (`key = "value"`), `.env` (`KEY=value`) and
#: shell (`export KEY=value`) are one rule, not five: all of them are, at the
#: character level, "a name, then optional quotes, then `:` or `=`, then a
#: value". Matched as a *substring* of the key — see the module docstring for
#: why `\b` cannot be used here — so `STRIPE_SECRET_KEY`, `DB_PASSWORD` and
#: `AWS_SECRET_ACCESS_KEY` all still match despite the leading `_`.
_SENSITIVE_KEY_NAME: Final = (
    r"(?:passwd|password|secret|token|api[_-]?key|private[_-]?key|credential|auth)"
)

# `export`/quotes/key/separator/quotes/value, generically across JSON, YAML,
# TOML, INI, `.env` and shell — one capture for the value, quotes optional on
# either side of it. The value itself is validated by
# `_looks_like_a_real_value` below, not by this pattern: a regex cannot also
# tell "empty" or "a template placeholder" from "a real secret" cleanly.
_GENERIC_ASSIGNMENT_RE: Final = re.compile(
    r"(?i)(?:export\s+)?[\"'`]?([A-Za-z0-9_.\-]*"
    + _SENSITIVE_KEY_NAME
    + r"[A-Za-z0-9_.\-]*)[\"'`]?\s*[:=]\s*[\"'`]?([^\s\"'`]*)"
)

#: A value this module declines to treat as "real" even though it matched a
#: sensitive key's assignment — empty, or itself a reference/placeholder
#: rather than a literal (DG-443 review round 2's explicit negatives:
#: `API_KEY=`, `"password": ""`, `"password": "${SECRET}"`).
_PLACEHOLDER_VALUE_RE: Final = re.compile(
    r"^(?:\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*%|<[^>]*>)$"
)

_MIN_GENERIC_VALUE_LENGTH: Final = 4


def _looks_like_a_real_value(value: str) -> bool:
    """Whether *value* (already quote-stripped) is worth refusing on at
    all — not empty, not a shell/Docker/Windows variable expansion, not an
    angle-bracket placeholder, and long enough to be more than a token
    stand-in for "there is nothing here yet"."""
    if len(value) < _MIN_GENERIC_VALUE_LENGTH:
        return False
    if _PLACEHOLDER_VALUE_RE.match(value):
        return False
    return True


_EMAIL_RE: Final = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_RESERVED_EMAIL_DOMAINS: Final = ("example.com", "example.org", "example.net")

# Drive letter with either slash direction (`C:\` or the `file:///C:/...`
# form), the POSIX home-directory roots, `/root/`, any `/mnt/...` mount (the
# WSL convention for a Windows drive, but not anchored to one drive letter),
# and a UNC share (`\\server\share\...`). `~/...` is never in this list.
_PATH_RE: Final = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'<>]*"
    r"|/Users/[^\s\"'<>]*"
    r"|/home/[^\s\"'<>]*"
    r"|/root/[^\s\"'<>]*"
    r"|/mnt/[^\s\"'<>]*"
    r"|\\\\[^\s\"'<>\\]+\\[^\s\"'<>]*"
    r")"
)

# `scheme://user:secret@host` — any scheme, including ones this module
# otherwise treats as a reference. Checked before any masking, below.
_USERINFO_RE: Final = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^/\s@]+:[^/\s@]+@")

# A reference this module may mask before the email/path checks — see the
# module docstring for why `file://` only sometimes qualifies, and why
# `literal://` never does.
_REFERENCE_RE: Final = re.compile(r"\b(env|op|keyring|file)://([^\s\"'<>]*)")


def _is_reference_like_file_body(body: str) -> bool:
    """Whether *body* (a `file://` reference's body) reads as a portable
    reference rather than a real, absolute, machine-specific path.

    True for `~/...` and any plain relative path; false for anything that
    starts with `/`, `//` or a drive letter — those are exactly the shapes
    the path check exists to catch, scheme or not.
    """
    if body.startswith("~/") or body.startswith("~\\"):
        return True
    if body.startswith("/") or body.startswith("\\"):
        return False
    if re.match(r"^[A-Za-z]:[\\/]", body):
        return False
    return True


def _mask_reference_spans(line: str) -> str:
    """*line* with every reference-shaped `env://`/`op://`/`keyring://` span,
    and every portable `file://` span, blanked out (same length, so no line
    this runs on ever shifts a later match's column) — `literal://` and an
    absolute-bodied `file://` are left exposed. Only used to prepare input
    for the email/path checks; the token and userinfo checks always see the
    unmasked line.
    """
    out = line
    for match in reversed(list(_REFERENCE_RE.finditer(line))):
        scheme, body = match.group(1), match.group(2)
        if scheme in ("env", "op", "keyring") or (
            scheme == "file" and _is_reference_like_file_body(body)
        ):
            start, end = match.span()
            out = out[:start] + (" " * (end - start)) + out[end:]
    return out


def _email_is_reserved(match_text: str) -> bool:
    domain = match_text.rsplit("@", 1)[-1].lower()
    return any(
        domain == reserved or domain.endswith("." + reserved)
        for reserved in _RESERVED_EMAIL_DOMAINS
    )


#: A line that is a sensitive key and *only* a sensitive key — nothing
#: after the separator but optional whitespace, an optional YAML block
#: scalar indicator (``|``, ``>``, ``|-``, ``>-``, ...), and an optional
#: trailing comma (the JSON "value is on the next line" shape). DG-443
#: review round 3: a value is not always on the *same* line as its key —
#: see :func:`scan_text`'s look-ahead, which this feeds.
_KEY_ONLY_RE: Final = re.compile(
    r"(?i)^\s*[\"'`]?([A-Za-z0-9_.\-]*"
    + _SENSITIVE_KEY_NAME
    + r"[A-Za-z0-9_.\-]*)[\"'`]?\s*:\s*([|>][+-]?)?,?\s*$"
)

#: A netrc-shaped line: ``machine``/``default``/``login``/``password`` as
#: the *first* token (case-insensitive). Deliberately not "the word
#: appears anywhere" — netrc's own grammar always starts a line this way,
#: and anchoring to the start is what keeps ordinary prose from tripping
#: this (see the module's "must NOT flag" corpus for the one shape that
#: still can: prose that itself opens with the literal word "password").
_NETRC_LINE_RE: Final = re.compile(r"(?i)^\s*(?:machine|default|login|password)\b")

#: Within a line :data:`_NETRC_LINE_RE` already matched, the
#: ``password <value>`` pair itself (netrc separates fields with
#: whitespace, never ``:``/``=``).
_NETRC_PASSWORD_RE: Final = re.compile(r"(?i)\bpassword[ \t]+(\S{4,})")

#: curl/wget basic-auth, as *any* short-option cluster ending in ``u``
#: (DG-443 review round 4) — ``-u``, ``-su``, ``-sSu``, ``-fsSu``,
#: ``-sSLu``, ... — not only the bare ``-u`` round 3 caught, since
#: ``-u`` is not a *substring* of ``-su`` and the earlier pattern missed
#: every clustered form entirely (reproduced end to end: copied
#: unredacted by `drunken-init --config-repo`, doctor reported OK). Also
#: matches ``--user``. The lookbehind keeps this from firing inside a
#: longer token (so a word that merely *ends* in a hyphen-letter run is
#: never mistaken for a flag); the separator group is optional so a
#: quote glued directly onto the flag (``-u"name:pass"``, no space or
#: ``=``) still matches, not only ``-u name:pass`` / ``-u=name:pass``.
#: The password half is captured alone, validated the same way as every
#: other rule (:func:`_looks_like_a_real_value`) before becoming a
#: finding — a bare ``-u``/``-su`` with no ``user:pass`` shaped value at
#: all (``ls -u``, ``sort -u file``, ``uniq -u file``) never matches in
#: the first place, since there is no literal ``:`` for the pattern to
#: anchor on.
_CURL_USER_FLAG_RE: Final = re.compile(
    r"(?<![A-Za-z0-9_-])(?:-[A-Za-z]*u|--user)(?:=|\s+)?"
    r"[\"']?[^\s\"':]+:(?!//)([^\s\"']+)"
)

#: A PowerShell literal secret (DG-443 review round 4): either
#: ``ConvertTo-SecureString`` together with ``-AsPlainText`` on the same
#: line, or a ``PSCredential(`` constructor call — both only when a
#: quoted literal is actually present on that line; ``$var``/
#: ``Read-Host`` (no quoted literal at all, or a quoted reference that
#: :func:`_looks_like_a_real_value` already rejects) never match.
_PS_SECURE_STRING_RE: Final = re.compile(r"(?i)ConvertTo-SecureString")
_PS_AS_PLAIN_TEXT_RE: Final = re.compile(r"(?i)-AsPlainText\b")
_PS_CREDENTIAL_RE: Final = re.compile(r"(?i)PSCredential\s*\(")
_PS_QUOTED_LITERAL_RE: Final = re.compile(r"[\"']([^\"']+)[\"']")


def _quote_stripped(value: str) -> str:
    """*value* with one matching pair of leading/trailing quote characters
    (``"``, ``'``, `````) removed, if present — otherwise unchanged.

    DG-443 review round 3: used so an allowlist entry's ``exact_text`` and
    a :class:`Finding`'s own ``matched`` value compare equal regardless of
    which quote style (or none) each happens to use — see
    :func:`apply_allowlist`.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        return value[1:-1]
    return value


def scan_text(text: str, filename: str) -> list[Finding]:
    """Every :class:`Finding` in *text*, reported as *filename*.

    Line numbers come from splitting on universal newlines
    (:meth:`str.splitlines`), so CRLF never shifts them. Order of findings
    within a file follows line order; order across kinds on the same line is
    userinfo, token, email, path.

    **A value is not always on the same line as its key (DG-443 review
    round 3).** A YAML block scalar (``key: |`` / ``key: >-`` with the real
    value indented on the next line) and a pretty-printed JSON value on its
    own line (``"key":`` then ``"value"`` next) both put the credential one
    line below the key that names it. This still reports the *key's* line
    number, not the value's — the key is what makes a reader able to find
    it, and the value itself was never captured into ``matched`` (only
    whether one is present, via :func:`_looks_like_a_real_value`).
    """
    lines = text.splitlines()
    findings: list[Finding] = []
    for index, line in enumerate(lines):
        findings.extend(_scan_one_line(lines, index, line, filename))
    return findings


def _scan_one_line(
    lines: list[str], index: int, line: str, filename: str
) -> list[Finding]:
    """Every :class:`Finding` on *line* (``lines[index]``) alone — split
    out of :func:`scan_text` purely to keep that function's own cyclomatic
    complexity low; the line-by-line contract is unchanged."""
    line_number = index + 1
    findings = _scan_unmasked_line(line, line_number, filename)
    masked = _mask_reference_spans(line)
    findings.extend(_scan_masked_line(lines, index, masked, line_number, filename))
    return findings


def _scan_unmasked_line(line: str, line_number: int, filename: str) -> list[Finding]:
    """The checks that always see *line* exactly as written — a reference
    span is never a userinfo credential, a dedicated token shape, or a
    netrc ``password <value>`` pair, so none of these need masking first."""
    findings: list[Finding] = []

    for match in _USERINFO_RE.finditer(line):
        findings.append(Finding(filename, line_number, "userinfo", match.group()))

    for pattern in _TOKEN_PATTERNS:
        for match in pattern.finditer(line):
            findings.append(Finding(filename, line_number, "token", match.group()))

    netrc_match = _NETRC_LINE_RE.match(line) and _NETRC_PASSWORD_RE.search(line)
    if netrc_match and _looks_like_a_real_value(netrc_match.group(1)):
        findings.append(Finding(filename, line_number, "token", netrc_match.group(1)))

    for match in _CURL_USER_FLAG_RE.finditer(line):
        password = match.group(1)
        if _looks_like_a_real_value(password):
            findings.append(Finding(filename, line_number, "token", password))

    findings.extend(_scan_powershell_literal(line, line_number, filename))

    return findings


def _scan_powershell_literal(
    line: str, line_number: int, filename: str
) -> list[Finding]:
    """A quoted literal secret on a PowerShell line (DG-443 review round
    4): ``ConvertTo-SecureString "..." -AsPlainText`` or
    ``PSCredential("...", ...)`` — only when a quoted literal is actually
    present, and only the first one that looks real (see
    :data:`_PS_SECURE_STRING_RE` for why ``$var``/``Read-Host`` never
    match at all)."""
    is_secure_string_line = _PS_SECURE_STRING_RE.search(
        line
    ) and _PS_AS_PLAIN_TEXT_RE.search(line)
    is_credential_line = _PS_CREDENTIAL_RE.search(line)
    if not (is_secure_string_line or is_credential_line):
        return []

    findings: list[Finding] = []
    for literal_match in _PS_QUOTED_LITERAL_RE.finditer(line):
        value = literal_match.group(1)
        if _looks_like_a_real_value(value):
            findings.append(Finding(filename, line_number, "token", value))
    return findings


def _scan_masked_line(
    lines: list[str], index: int, masked: str, line_number: int, filename: str
) -> list[Finding]:
    """The checks that run against *masked* (the reference-spans-blanked
    form of this line) — a generic key=value assignment, a key-only line
    whose value is on the next line, an e-mail address, and a real path."""
    findings: list[Finding] = []

    for match in _GENERIC_ASSIGNMENT_RE.finditer(masked):
        value = match.group(2)
        if _looks_like_a_real_value(value):
            findings.append(Finding(filename, line_number, "token", value))

    if _KEY_ONLY_RE.match(masked):
        next_value = _next_line_value(lines, index)
        if next_value is not None and _looks_like_a_real_value(next_value):
            findings.append(Finding(filename, line_number, "token", next_value))

    for match in _EMAIL_RE.finditer(masked):
        if not _email_is_reserved(match.group()):
            findings.append(Finding(filename, line_number, "email", match.group()))

    for match in _PATH_RE.finditer(masked):
        findings.append(Finding(filename, line_number, "path", match.group()))

    return findings


def _next_line_value(lines: list[str], key_index: int) -> str | None:
    """The line immediately after *lines[key_index]*, read as a bare value
    — quotes and a trailing comma stripped — or ``None`` when there is no
    next line at all.

    Deliberately the *immediate* next line only, blank or not — not "skip
    ahead to the next non-blank line". A YAML block scalar followed by a
    blank line (``key: |`` then nothing indented before the next sibling
    key starts) has no value at all, and skipping the blank to reach that
    sibling key would misread the sibling's own text as this key's value.
    A blank immediate line reads here as an empty string, which
    :func:`_looks_like_a_real_value` already rejects on length alone.

    Also does not require the value line to be more indented than the key
    line: a YAML block scalar's value conventionally is, but a
    pretty-printed JSON value on its own line is typically indented the
    *same* amount as sibling keys, not further — requiring "more indented"
    would silently miss the JSON shape this is also meant to catch.
    """
    if key_index + 1 >= len(lines):
        return None
    stripped = lines[key_index + 1].strip().rstrip(",")
    return _quote_stripped(stripped)


def scan_file(path: Path, filename: str) -> list[Finding]:
    """:func:`scan_text` over *path*'s own content, reported as *filename*.

    The one place this module reads a file from disk, so
    :mod:`core.layer_copy` (a config repo's copy) and :mod:`core.doctor` (a
    project's own, already-copied checkout) never grow two ways of deciding
    what "cannot be read as text" means.

    A NUL byte, or a decode failure under ``"utf-8-sig"`` (which also
    transparently strips a leading BOM when there is one), is **not** a
    silent skip: the AI layer is text, by rule, with no carve-out for a file
    that happens not to be — this returns a single ``"unscannable"``
    :class:`Finding` instead, which a caller treats exactly like any other
    refusal.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [Finding(filename, 0, "unscannable", str(exc))]

    if b"\x00" in raw:
        return [Finding(filename, 0, "unscannable", "contains a NUL byte")]

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [Finding(filename, 0, "unscannable", str(exc))]

    return scan_text(text, filename)


def scan_allowlist_file(
    path: Path, filename: str = ALLOWLIST_FILENAME
) -> list[Finding]:
    """:func:`scan_file` over *path*, with every well-formed allow-entry
    *row* blanked out first.

    An allow entry's own ``exact_text`` column necessarily holds the very
    text it excuses — that is the whole point of an exact-text match — so
    scanning it the same way as any other file would always flag the
    allowlist's own structured data. What this still catches is anything
    *else* in the file: a stray line someone pasted outside the four-column
    format, which is exactly as unexpected there as it would be anywhere
    else. Line numbers are preserved (blanked rows become empty lines, not
    removed), so a finding's line still points at the right place.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [Finding(filename, 0, "unscannable", str(exc))]
    if b"\x00" in raw:
        return [Finding(filename, 0, "unscannable", "contains a NUL byte")]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [Finding(filename, 0, "unscannable", str(exc))]

    scrubbed_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            scrubbed_lines.append("")
            continue
        fields = line.split("\t")
        if len(fields) == 4 and all(f.strip() for f in fields[:3]):
            scrubbed_lines.append("")  # a well-formed row; see the docstring
        else:
            scrubbed_lines.append(line)

    return scan_text("\n".join(scrubbed_lines), filename)


def parse_allowlist(
    text: str, *, source_name: str = ALLOWLIST_FILENAME
) -> FrozenSet[AllowEntry]:
    """Parse *text* as `.drunken-scan-allow`: one entry per non-blank,
    non-``#``-comment line, tab-separated as ``file\\tkind\\texact_text\\treason``.

    Exact-text match only, by design — no wildcard, no regex, no "allow this
    whole file": every entry names exactly the one finding it excuses, and a
    human-readable reason, both visible in a diff. A line with the wrong
    number of fields is reported rather than silently ignored (half of an
    allowlist entry excuses nothing by accident).
    """
    entries: set[AllowEntry] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 4 or not all(f.strip() for f in fields[:3]):
            raise ValidationError(
                f"{source_name}:{line_number}: expected 4 tab-separated fields "
                "(file, kind, exact_text, reason), not well-formed.",
                remediation=(
                    "Write the line as "
                    "'<relative file>\\t<kind>\\t<exact matched text>\\t<reason>', "
                    "or remove it."
                ),
            )
        relative_file, kind, exact_text, _reason = fields
        entries.add((relative_file.strip(), kind.strip(), exact_text))
    return frozenset(entries)


def apply_allowlist(
    findings: Iterable[Finding], allow: FrozenSet[AllowEntry]
) -> list[Finding]:
    """*findings* with every exact (file, kind, matched-text) triple in
    *allow* removed. Not consumed/counted — the same entry may excuse the
    same finding in more than one scan of the same content without needing
    to be listed twice.

    **Quote style is not part of the match (DG-443 review round 3).** Both
    sides — a finding's own ``matched`` value and an allowlist entry's
    ``exact_text`` — are compared with one matching pair of leading/
    trailing quote characters stripped first (:func:`_quote_stripped`), so
    an allowlist author writing the value quoted (``"the-value"``) still
    excuses a finding whose own ``matched`` happened to be stored unquoted,
    or the reverse. Everything else about the comparison stays exact: this
    is quote-style tolerance, not a fuzzy or partial match.
    """
    normalized_allow = {
        (file, kind, _quote_stripped(text)) for file, kind, text in allow
    }
    return [
        f
        for f in findings
        if (f.file, f.kind, _quote_stripped(f.matched)) not in normalized_allow
    ]


__all__: Sequence[str] = (
    "ALLOWLIST_FILENAME",
    "AllowEntry",
    "Finding",
    "apply_allowlist",
    "parse_allowlist",
    "scan_allowlist_file",
    "scan_file",
    "scan_text",
)
