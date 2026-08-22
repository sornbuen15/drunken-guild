"""What a run actually cost, read from what the host already wrote.

DG-95. The ticket's complaint was that no claim about token efficiency in this
project could be checked: *"needed before any claim of 'this saves tokens' can
be substantiated with data rather than assumption."* The claim has been made
more than once — ``minify_issues`` exists for it, DG-227 was cut for it, the
board's retirement was argued partly on it — and nothing has ever produced a
number.

**Nothing here instruments anything.** The host writes per-message usage into
its own transcripts, one JSON object per line, and each record carries the git
branch it was written on. Under this project's branch convention that branch
carries a Jira key, so *cost per ticket* is a read rather than a measurement,
and it works retroactively over every session already on disk.

Three decisions are load-bearing:

**The directory name is a guess; ``cwd`` is the authority.** Transcripts live in
a directory named after the working directory with every non-alphanumeric
character replaced by a dash. That scheme belongs to another tool and is not a
contract, so it is used only to *narrow* the search — a prefix match, so a
worktree of the same project is found — and every record then has to prove
itself by the ``cwd`` it carries. Without that check, ``drunken-guild-old`` would
be counted as ``drunken-guild``: a confidently wrong number, which is worse than
no number.

**An unknown model costs ``None``, never ``0.0``.** Zero reads as "this was
free" and is indistinguishable from a real answer. This is S4's shape — the
dead credential that returned an empty list instead of an error — and it is the
failure this module exists to avoid, so it must not commit it.

**Rates are an operator input, not a constant in this file.** Prices change,
differ by contract, and are not knowable from inside a process. A table
hardcoded here would keep answering long after it stopped being true, and every
answer would look authoritative. So the default output is *tokens*, which are a
fact, and money appears only when someone supplies the rates.

What it cannot see: Antigravity's usage, which lives under a directory
``CLAUDE.md`` puts out of bounds. Two agents work this repo and this counts one
of them, so every report says so rather than presenting a total that will be
read as the whole bill.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Iterable, Iterator, Optional

#: Where the host keeps its transcripts. Overridable like everything in
#: :mod:`core.paths`, and for the same reason — a container, a different host,
#: or a test must be able to point this somewhere else. It is deliberately
#: *not* in ``core.paths``: that module is about where drunken-guild keeps its
#: own state, and this is another tool's data that we only read.
ENV_TRANSCRIPT_ROOT: Final = "DRUNKEN_TRANSCRIPT_ROOT"
DEFAULT_TRANSCRIPT_ROOT: Final = "~/.claude/projects"

#: The host that wrote what this module reads, named in every report.
SOURCE: Final = "Claude Code transcripts"

#: Said out loud in every report. See the module docstring.
COVERS: Final = (
    "Claude Code sessions on this machine only. Antigravity's usage is not "
    "included: it lives under ~/.gemini/antigravity-cli/brain/, which CLAUDE.md "
    "puts out of bounds. Two agents work this repo and this counts one."
)

#: A Jira key anywhere in a branch name. Case-insensitive, because a branch is
#: typed by hand and Jira's own spelling is uppercase.
_TICKET: Final = re.compile(r"([A-Za-z][A-Za-z0-9]*)-([0-9]+)")

#: Every rate a model needs before any money may be reported for it.
_RATE_FIELDS: Final = ("input", "output", "cache_read", "cache_creation")

_KEYS: Final = ("ticket", "branch", "session", "model", "day")

#: Stands in for "this work belongs to no ticket" — trunk commits, mostly.
NONE_KEY: Final = "(none)"


def transcript_root() -> Path:
    """The directory holding the host's transcripts."""
    raw = os.environ.get(ENV_TRANSCRIPT_ROOT) or DEFAULT_TRANSCRIPT_ROOT
    return Path(os.path.expandvars(raw)).expanduser()


def slug_for(project_path: str | os.PathLike[str]) -> str:
    """The transcript directory name the host derives from *project_path*.

    Every character that is not alphanumeric becomes a dash, the leading slash
    included: ``/Users/you/Projects/drunken-guild`` is stored as
    ``-Users-you-Projects-drunken-guild``.

    Inferred from what is on disk rather than from any documented contract,
    which is why nothing downstream trusts it on its own.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(project_path))


@dataclass(frozen=True)
class Usage:
    """Tokens billed for one message.

    Cache is kept separate rather than folded into the input total. It is not a
    rounding detail: on this project cache reads outnumber output tokens by
    roughly three hundred to one, and they are the only figure a caching change
    moves. A single total would hide exactly the thing worth measuring.
    """

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_creation: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_creation

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input + other.input,
            self.output + other.output,
            self.cache_read + other.cache_read,
            self.cache_creation + other.cache_creation,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Usage":
        """Read a host ``usage`` object. A missing field is zero, not absent:
        on a fully cached turn ``input_tokens`` simply does not appear, and
        that means none were billed."""

        def count(name: str) -> int:
            value = payload.get(name)
            return value if isinstance(value, int) else 0

        return cls(
            input=count("input_tokens"),
            output=count("output_tokens"),
            cache_read=count("cache_read_input_tokens"),
            cache_creation=count("cache_creation_input_tokens"),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "input": self.input,
            "output": self.output,
            "cache_read": self.cache_read,
            "cache_creation": self.cache_creation,
            "total": self.total,
        }


@dataclass(frozen=True)
class Record:
    """One billed message, with everything needed to attribute it."""

    session: str
    timestamp: str
    branch: Optional[str]
    model: str
    usage: Usage


@dataclass
class Rollup:
    """Everything charged under one key."""

    usage: Usage = field(default_factory=Usage)
    messages: int = 0
    models: set[str] = field(default_factory=set)
    _sessions: set[str] = field(default_factory=set)
    first: str = ""
    last: str = ""

    @property
    def sessions(self) -> int:
        """Distinct sessions, not messages. Two messages in one session is one
        run, and counting messages would make a chatty session look like many."""
        return len(self._sessions)

    def add(self, record: Record) -> None:
        self.usage = self.usage + record.usage
        self.messages += 1
        self.models.add(record.model)
        self._sessions.add(record.session)
        if record.timestamp:
            self.first = min(self.first or record.timestamp, record.timestamp)
            self.last = max(self.last, record.timestamp)


def _under(child: str, parent: str) -> bool:
    """Whether *child* is *parent* or sits inside it, compared as paths.

    String prefixing would count ``/tmp/proj-other`` as inside ``/tmp/proj``.
    """
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
    except (ValueError, OSError):
        return False
    return True


def iter_records(
    root: str | os.PathLike[str], project_path: str | os.PathLike[str]
) -> Iterator[Record]:
    """Every billed message belonging to *project_path*, under transcript *root*.

    Tolerant by construction. A missing root yields nothing — a fresh machine
    has no transcripts, and that is an answer rather than an error. A line that
    does not parse is skipped: these files are another tool's private format and
    are appended to while being read, so the last line is routinely half
    written, and losing the whole file over it would be absurd.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return

    prefix = slug_for(project_path)
    for directory in sorted(root_path.iterdir()):
        if not directory.is_dir() or not directory.name.startswith(prefix):
            continue
        for transcript in sorted(directory.glob("*.jsonl")):
            yield from _read_transcript(transcript, str(project_path))


def _read_transcript(path: Path, project_path: str) -> Iterator[Record]:
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            record = _parse_line(line, project_path)
            if record is not None:
                yield record


def _parse_line(line: str, project_path: str) -> Optional[Record]:
    try:
        raw = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None

    # The directory name only narrowed the search. This is the check that
    # decides whether the record is ours.
    cwd = raw.get("cwd")
    if not isinstance(cwd, str) or not _under(cwd, project_path):
        return None

    message = raw.get("message")
    if not isinstance(message, dict):
        return None
    payload = message.get("usage")
    if not isinstance(payload, dict):
        return None

    return Record(
        session=str(raw.get("sessionId") or ""),
        timestamp=str(raw.get("timestamp") or ""),
        branch=raw.get("gitBranch") or None,
        model=str(message.get("model") or "unknown"),
        usage=Usage.from_payload(payload),
    )


def ticket_of(branch: Optional[str]) -> Optional[str]:
    """The Jira key a branch name carries, or ``None``.

    ``None`` for ``develop`` and ``main`` rather than a guess: trunk carries the
    largest share of records by far, and filing them under an invented heading
    would put a real number somewhere it does not belong.
    """
    if not branch:
        return None
    match = _TICKET.search(branch)
    if not match:
        return None
    return f"{match.group(1).upper()}-{match.group(2)}"


def _key_of(record: Record, key: str) -> str:
    if key == "ticket":
        return ticket_of(record.branch) or NONE_KEY
    if key == "branch":
        return record.branch or NONE_KEY
    if key == "session":
        return record.session or NONE_KEY
    if key == "model":
        return record.model
    if key == "day":
        return record.timestamp[:10] or NONE_KEY
    raise ValueError(f"Unknown grouping {key!r}. Choose one of: {', '.join(_KEYS)}.")


def roll_up(records: Iterable[Record], key: str = "ticket") -> dict[str, Rollup]:
    """Sum *records* under *key*."""
    rolled: dict[str, Rollup] = {}
    for record in records:
        rolled.setdefault(_key_of(record, key), Rollup()).add(record)
    return rolled


def load_rates(path: str | os.PathLike[str]) -> dict[str, dict[str, float]]:
    """Read a rates file: ``{model: {input, output, cache_read, cache_creation}}``
    in USD per million tokens.

    A missing or unreadable file reads as *no rates*, which shows up as tokens
    with no cost beside them — visibly missing rather than silently wrong.
    Principle 4, applied to money.
    """
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        str(model): {str(k): float(v) for k, v in rates.items() if _is_number(v)}
        for model, rates in loaded.items()
        if isinstance(rates, dict)
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def cost_usd(
    usage: Usage, model: str, rates: dict[str, dict[str, float]]
) -> Optional[float]:
    """What *usage* cost on *model*, or ``None`` if that cannot be said.

    ``None`` rather than ``0.0`` for an unpriced model, and ``None`` rather than
    a partial sum for a partially priced one: a rate table missing its cache
    entry would understate the answer here by two orders of magnitude, and the
    number would look exactly as authoritative as a correct one.
    """
    table = rates.get(model)
    if not table or any(field_ not in table for field_ in _RATE_FIELDS):
        return None
    return (
        usage.input * table["input"]
        + usage.output * table["output"]
        + usage.cache_read * table["cache_read"]
        + usage.cache_creation * table["cache_creation"]
    ) / 1_000_000


def build_report(
    root: str | os.PathLike[str],
    project_path: str | os.PathLike[str],
    key: str = "ticket",
    rates: Optional[dict[str, dict[str, float]]] = None,
) -> dict[str, Any]:
    """A complete, serialisable report, sorted by total tokens descending."""
    rates = rates or {}
    rolled = roll_up(iter_records(root, project_path), key=key)

    rows: list[dict[str, Any]] = []
    totals = Usage()
    for name, group in sorted(
        rolled.items(), key=lambda item: item[1].usage.total, reverse=True
    ):
        totals = totals + group.usage
        rows.append(
            {
                key: name,
                "sessions": group.sessions,
                "messages": group.messages,
                "models": sorted(group.models),
                "first": group.first,
                "last": group.last,
                "cost_usd": _group_cost(group, rates),
                **group.usage.to_dict(),
            }
        )

    return {
        "project": str(project_path),
        "source": SOURCE,
        "covers": COVERS,
        "grouped_by": key,
        "rows": rows,
        "totals": totals.to_dict(),
        "priced": bool(rates),
    }


def _group_cost(group: Rollup, rates: dict[str, dict[str, float]]) -> Optional[float]:
    """A group's cost, or ``None`` if any model in it is unpriced.

    Not the sum of the priced ones. A mixed group where one model has no rate
    would otherwise report a number that is real, smaller than the truth, and
    indistinguishable from a complete answer.
    """
    if len(group.models) != 1:
        return None
    return cost_usd(group.usage, next(iter(group.models)), rates)


def _fmt(number: int) -> str:
    for unit, size in (("B", 1_000_000_000), ("M", 1_000_000), ("k", 1_000)):
        if number >= size:
            return f"{number / size:.1f}{unit}"
    return str(number)


def render(report: dict[str, Any]) -> str:
    """The report as a table, with the caveat attached to it rather than to the
    documentation someone may not read."""
    key = report["grouped_by"]
    lines = [
        f"usage for {report['project']}  (grouped by {key})",
        f"source: {report['source']}",
        "",
        f"{key:28} {'sessions':>8} {'msgs':>6} {'output':>9} {'cache rd':>9} "
        f"{'total':>9} {'cost':>10}",
    ]
    for row in report["rows"]:
        cost = f"${row['cost_usd']:.2f}" if row["cost_usd"] is not None else "-"
        lines.append(
            f"{row[key][:28]:28} {row['sessions']:>8} {row['messages']:>6} "
            f"{_fmt(row['output']):>9} {_fmt(row['cache_read']):>9} "
            f"{_fmt(row['total']):>9} {cost:>10}"
        )

    totals = report["totals"]
    lines += [
        "",
        f"{'TOTAL':28} {'':>8} {'':>6} {_fmt(totals['output']):>9} "
        f"{_fmt(totals['cache_read']):>9} {_fmt(totals['total']):>9}",
        "",
        f"⚠ {report['covers']}",
    ]
    if not report["priced"]:
        lines.append(
            "⚠ No rates supplied, so no cost is shown. Tokens are a fact; a "
            "price is an input — pass --rates <file> with USD per million "
            "tokens per model. Nothing here guesses one."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="drunken-usage",
        description=(
            "Report token usage for a project, read from the host's own "
            "transcripts. Nothing is instrumented and nothing is sent anywhere."
        ),
    )
    parser.add_argument("--project", help="Registered project id.")
    parser.add_argument(
        "--path", help="Project directory, if it is not a registered project."
    )
    parser.add_argument("--by", choices=_KEYS, default="ticket")
    parser.add_argument(
        "--rates",
        help=(
            "JSON file of USD per million tokens per model: "
            '{"model": {"input": 15, "output": 75, "cache_read": 1.5, '
            '"cache_creation": 18.75}}. Without it, tokens only.'
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit the raw report.")
    args = parser.parse_args(argv)

    path = args.path
    if not path and args.project:
        # Imported here rather than at module scope: a registry that cannot be
        # read must not stop `--path` from working. Principle 8.
        from core.context import ProjectContext

        try:
            # root_path(), not git_root_path(): under DG-250's layout the
            # repository is a subdirectory of the registered project, and a
            # session run from the wrapper is still that project's cost.
            path = str(ProjectContext.build(args.project).root_path())
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            print(f"[drunken-usage] Could not resolve project {args.project!r}: {exc}")
            return 1
    if not path:
        path = os.getcwd()

    report = build_report(
        transcript_root(),
        path,
        key=args.by,
        rates=load_rates(args.rates) if args.rates else {},
    )
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
