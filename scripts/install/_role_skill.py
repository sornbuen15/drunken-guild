#!/usr/bin/env python3
"""Print the `skill` a role names in `agents/_sources.json`, or nothing.

DG-402. `install_agents.sh` originally called a multi-line `python3 -c '...'`
for this, inline. On at least one machine that broke under a `pyenv-win`
shim: the shim mis-passed the multi-line `-c` argument, python raised an
`IndentationError` on what looked like leftover batch-file error-handling
text, and the surrounding `|| true` swallowed that failure into an empty
string -- silently disabling the whole safety check this script is part of
(it exists so `install_agents.sh`/`.ps1` can refuse to install a role
adapter whose skill is not installed). `_truncate.py` and
`_generate_agents.py` never had this problem because neither passes a
multi-line script through `-c`; this script follows the same rule.
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
        data = json.load(open(sources_json, encoding="utf-8"))
    except OSError:
        return 0
    except json.JSONDecodeError:
        return 0
    print(data.get(role_name, {}).get("skill", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
