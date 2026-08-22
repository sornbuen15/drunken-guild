# Retired — `scripts/create_pr.py`

**Retired:** 2026-08-22 (DG-274) · **Was:** `scripts/create_pr.py`
**Replaced by:** `gh pr create`, which every workflow here already uses.

It was never a tool. It is a one-shot script from a single 2026 pull request with the title,
branch, base and body **hardcoded in the source** — `"feat: restructure agents"`, head
`feat/restructure-agents` — and it POSTs to
`https://api.github.com/repos/sornbuen15/drunken-team/pulls`: the previous repository, which this
project is under standing instruction not to touch.

Running it today would either fail on a branch that does not exist, or open a pull request against
the wrong repository with a title describing work finished months ago.

Nothing imports it. The only reference was a line in `.env.example` naming the token it read.

Kept, not deleted. An agent does not delete.
