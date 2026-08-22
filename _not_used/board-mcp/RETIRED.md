# Retired — `drunken-board-mcp` and its tests

**Retired:** 2026-08-22 · **Was:** `src/board_mcp/` and three test modules under `tests/`
**Replaced by:** Jira, through `drunken-jira-mcp`. There is no local board.

## Why the tools went (DG-250)

A board sitting next to Jira is a **second surface that can disagree with the first**. That is the
failure this project spent whole sessions curing — four surfaces disagreeing in DG-249, one
credential copied to three places in DG-248.

The evidence was already on disk when the decision was made: this project's own board held three
cards, last touched 2026-07-22, still using the `DAGY-` prefix that DG-244 retired, while every
real ticket of that period went through Jira and never touched it. It also cost 2,162 tokens per
request for a server nothing should call.

Jira is the only coordination surface now. The **assignee** says whose work a ticket is; the
**status** says where it is.

**What is genuinely lost:** the board expired a claim after `CLAIM_TTL_SECONDS` and released it. A
Jira assignee never expires, so a ticket left assigned to an agent that died stays that way until a
human looks. That is a ten-second fix by a human, weighed against a class of silent disagreement
that costs weeks.

## Why the package went (DG-265)

The tools were retired in DG-250, but the **server kept shipping**. `pyproject.toml` still exposed
`board_mcp.server:main` as a console script and `board_mcp` was in `packages`, so `pip install` put
a runnable `drunken-board-mcp` on the PATH of everyone who installed this — and
`verify_clean_install.sh` started it by name to prove it answered a handshake.

It survived that long for a reason that had quietly expired. Removing a shipped entry point is a
breaking change, so it was worth weighing while `drunken-guild` was thought to inherit
`drunken-team`'s `v2.3.0`. Then every tag was deleted and the count restarted at `v1.0.0`. **A
package that has never been released has no compatibility to protect**, so shipping a dead server
from day one stopped being an inheritance and became a choice.

## What is here

```
board_mcp/                        the server and its board model
test_board_mcp.py                 830 lines
test_board_security.py            183 lines — S1 and S2
test_board_registry_source.py      40 lines — the registry-path fix
```

The tests moved with the code rather than being deleted. They are the record of what the board was
proven to do, and they would be needed intact if anyone ever revived it.

## What still guards this

Removing the code is not what stops it coming back — a copied config or a restored line would do
that silently. Three tests do:

- `tests/test_mcp_config.py::test_a_retired_server_is_not_packaged_again` — fails if the console
  script is declared again.
- `tests/test_mcp_config.py::test_a_retired_server_is_not_quietly_wired_back_in` — fails if it
  reappears in `.mcp.json`.
- `tests/test_config_gen.py::test_board_mcp_is_not_in_the_server_list` — fails if onboarding starts
  declaring it into new projects again, which it did until DG-228.

Kept, not deleted. An agent does not delete.
