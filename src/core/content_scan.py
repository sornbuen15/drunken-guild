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
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),  # GitHub (ghp_/gho_/ghu_/ghs_/ghr_)
    re.compile(r"\bATATT[A-Za-z0-9_\-=]{20,}\b"),  # Atlassian
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),  # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),  # JWT
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{16,}=*"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{16,}"),
    re.compile(r"(?i)\b(api[_\-]?key|token|secret|password)\s*[=:]\s*\S{8,}"),
)

_EMAIL_RE: Final = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_RESERVED_EMAIL_DOMAINS: Final = ("example.com", "example.org", "example.net")

# Drive letter with either slash direction (`C:\` or the `file:///C:/...` form),
# plus the two POSIX home-directory roots. `~/...` is never in this list.
_PATH_RE: Final = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'<>]*|/Users/[^\s\"'<>]*|/home/[^\s\"'<>]*)"
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


def scan_text(text: str, filename: str) -> list[Finding]:
    """Every :class:`Finding` in *text*, reported as *filename*.

    Line numbers come from splitting on universal newlines
    (:meth:`str.splitlines`), so CRLF never shifts them. Order of findings
    within a file follows line order; order across kinds on the same line is
    userinfo, token, email, path.
    """
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in _USERINFO_RE.finditer(line):
            findings.append(Finding(filename, line_number, "userinfo", match.group()))

        for pattern in _TOKEN_PATTERNS:
            for match in pattern.finditer(line):
                findings.append(Finding(filename, line_number, "token", match.group()))

        masked = _mask_reference_spans(line)

        for match in _EMAIL_RE.finditer(masked):
            if _email_is_reserved(match.group()):
                continue
            findings.append(Finding(filename, line_number, "email", match.group()))

        for match in _PATH_RE.finditer(masked):
            findings.append(Finding(filename, line_number, "path", match.group()))

    return findings


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
    """
    return [f for f in findings if (f.file, f.kind, f.matched) not in allow]


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
