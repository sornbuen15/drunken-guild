#!/usr/bin/env python3
"""Print the `skill` a role names in `agents/_sources.json`, or `-`.

DG-402, reviewer finding (PR #150, fails-open CRITICAL). The contract here
is deliberately strict, because the caller (`install_agents.sh`) must be
able to tell "no dependency" apart from "this failed" without guessing:

- Exit 0 means exactly one line was printed: either the role's skill name,
  or the literal sentinel `-` when the role has no entry (or no `skill`
  key) in the manifest. Exit 0 with no output, or with more than one line,
  never happens by construction here -- if it is ever observed, the
  caller must treat it as `python3` itself misbehaving, not as "no
  dependency" (a real failure mode, reproduced during review: a broken
  interpreter on `PATH` that exits 0 printing nothing for any script).
- Any error -- a missing/unreadable manifest, invalid JSON, a manifest
  that is not a JSON object -- is a non-zero exit with a message on
  stderr, never a bare `-` standing in for "I don't know".

`install_agents.sh` originally called a multi-line `python3 -c '...'` for
this, inline. On at least one machine that broke under a `pyenv-win` shim:
the shim mis-passed the multi-line `-c` argument, python raised an
`IndentationError` on what looked like leftover batch-file error-handling
text, and the surrounding `|| true` swallowed that failure into an empty
string -- silently disabling the whole safety check this script is part
of. `_truncate.py` and `_generate_agents.py` never had this problem
because neither passes a multi-line script through `-c`; this script
follows the same rule.
"""

from __future__ import annotations

import json
import sys

#: Printed when a role has no entry (or no `skill` key) in the manifest --
#: a real, legitimate "no dependency" answer, never confused with silence.
NO_DEPENDENCY = "-"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <sources_json> <role_name>", file=sys.stderr)
        return 2
    sources_json, role_name = argv[1], argv[2]

    try:
        with open(sources_json, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        print(f"{argv[0]}: cannot read {sources_json}: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"{argv[0]}: {sources_json} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print(f"{argv[0]}: {sources_json} is not a JSON object", file=sys.stderr)
        return 1

    entry = data.get(role_name)
    skill = entry.get("skill") if isinstance(entry, dict) else None
    print(skill if skill else NO_DEPENDENCY)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
