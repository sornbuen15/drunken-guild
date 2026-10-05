#!/usr/bin/env python3
"""Print the `skill` a role names in `agents/_sources.json`.

DG-402, reviewer finding (PR #150, round 2, fails-open HIGH). An earlier
version of this script printed the sentinel `-` for "no dependency" when a
role had no entry, or no `skill` key, in the manifest. That sentinel was
itself a fail-open: a manifest edit that dropped or typo'd a role's `skill`
key produced `-`, exit 0, and the caller installed that adapter anyway --
the gate bypassed by the exact kind of mistake it exists to catch.
Reproduced on review two ways: a manifest copy with one role's `skill` key
removed, and a stub `python3` answering `-` outright.

Every role adapter this repository ships needs its own skill, so there is
no such thing as "no dependency" here any more. The contract is now
simpler and stricter:

- Exit 0 means exactly one line was printed: the role's own, non-empty
  `skill` name, read from the manifest's own `skill` string.
- Any other case is a non-zero exit with a message on stderr, and no
  stdout a caller could mistake for an answer: a missing/unreadable
  manifest, invalid JSON, a manifest that is not a JSON object, a role
  absent from the manifest, or a `skill` value that is missing, empty or
  not a string.

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
    if not isinstance(entry, dict):
        print(
            f"{argv[0]}: {role_name!r} has no entry in {sources_json}",
            file=sys.stderr,
        )
        return 1

    skill = entry.get("skill")
    if not isinstance(skill, str) or not skill.strip():
        print(
            f"{argv[0]}: {role_name!r}'s 'skill' in {sources_json} is "
            "missing, empty or not a string",
            file=sys.stderr,
        )
        return 1

    print(skill)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
