"""Away mode — the switch that makes "I'm going out" reach the machine.

Layer B of the approval problem was solved by DT-232: when the *agent*
decides it needs permission, it asks over Discord and parks. Layer A is the
harness asking "Allow this tool call?" before the agent runs at all. The model
never sees that question, so no skill, instruction or sentence in chat has
ever been able to redirect it -- which is exactly why telling Claude "I'm
going out" did not work, and was never going to.

The PreToolUse hook can answer that question, but only if it knows the Boss is
away. It is a separate process with no conversation and no memory, so the only
thing it can consult is a file. This is that file.

Deliberately not a Discord command or a daemon field: the hook has to be able
to read it with no network, no daemon, and no import that can fail.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from core import paths


def away_flag_path() -> paths.ResolvedPath:
    """Re-exported so callers do not need both modules for one question."""
    return paths.away_flag_path()


def status() -> dict[str, Any]:
    """The flag's contents, or an empty-but-valid 'present' state.

    Unreadable state reads as *present*, not away (principle 4, with the
    direction chosen rather than defaulted). Wrongly reading "away" would
    route tool calls at a Boss who is sitting right there, and stall the work
    on a question nobody knows was asked. Wrongly reading "present" only
    costs a terminal prompt.
    """
    path = away_flag_path().path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"away": False, "since": None, "note": ""}
    if not isinstance(data, dict):
        return {"away": False, "since": None, "note": ""}
    return {
        "away": bool(data.get("away", False)),
        "since": data.get("since"),
        "note": data.get("note", ""),
    }


def is_away() -> bool:
    return bool(status()["away"])


def set_away(note: str = "") -> dict[str, Any]:
    paths.ensure_home()
    path = away_flag_path().path
    payload = {"away": True, "since": time.time(), "note": note}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def clear_away() -> dict[str, Any]:
    paths.ensure_home()
    path = away_flag_path().path
    payload: dict[str, Any] = {"away": False, "since": None, "note": ""}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _describe(state: dict[str, Any]) -> str:
    if not state["away"]:
        return f"present — permission prompts stay in the terminal\n{away_flag_path().path}"
    since = state.get("since")
    when = (
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since))
        if since
        else "unknown"
    )
    note = f"\nnote:  {state['note']}" if state["note"] else ""
    return (
        f"away since {when} — permission prompts go to Discord{note}\n"
        f"{away_flag_path().path}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="drunken-away",
        description=(
            "Tell the machine the Boss has stepped out, so the PreToolUse hook "
            "routes permission prompts to Discord instead of the terminal."
        ),
    )
    parser.add_argument(
        "state", choices=("on", "off", "status"), nargs="?", default="status"
    )
    parser.add_argument(
        "--note", default="", help="Free text shown alongside the flag."
    )
    args = parser.parse_args(argv)

    if args.state == "on":
        print(_describe(set_away(args.note)))
    elif args.state == "off":
        print(_describe(clear_away()))
    else:
        print(_describe(status()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
