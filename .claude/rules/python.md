---
paths:
  - "src/**/*.py"
  - "scripts/**/*.py"
  - "tests/**/*.py"
  - "pyproject.toml"
---

# The Python half

<!-- Moved out of CLAUDE.md in DG-360. Every rule here is about code under
     `src/`, `scripts/` or `tests/`, so `paths:` above loads it when a session
     reaches one of those files and never otherwise. -->

## Tests

**A test for a bug or a security finding must be seen failing first.** A test written after the fix
proves only that it compiles. Say so in the PR when you have done it, and quote what the failure
said — the test id and the assertion. "Tests added" is not that.

Match the surrounding test style. Assertions carry the reason they exist, not just the expectation.

**A test that asserts a value which is only true in passing is worse than no test.** Two in this
repository asserted an empty tuple and an arbitrary flag in a fixture; both passed while the thing
they were named for was broken (DG-358). Assert the subject, not the state of the day.

## Which gates cover which half

The Python gates — `ruff`, `mypy`, `pytest`, `bandit`, `pip-audit` — cover **`src/`, `tests/` and
`scripts/` only.** The AI layer is markdown and has no type checker; what guards it is
`scripts/check_doc_drift.py` and review.

CI knows the difference: a job reports whether any non-markdown file changed, and the test matrix
and clean-install read that. The secret scan and the doc-drift check are **not** gated and run on
every push, because a secret pasted into a README is still a secret.

**`uv sync --extra dev` is required, and a fresh clone does not have it.** Without pytest in
`.venv`, `uv run pytest` falls through to whatever `pytest` is on PATH — a different interpreter,
whose site-packages may carry an editable install claiming `core`, `scripts` and the rest. That is
not hypothetical: it ran this repository's suite against `~/Projects/drunken-team` for two rounds of
review, green the whole time, with coverage reading 0% because nothing in `src/` was ever imported
(DG-268). `tests/conftest.py` now fails the run at session start rather than letting it pass, and
names the fix.

**`verify_clean_install.sh` installs from `git archive HEAD`, not the working tree.** So it tests the
last commit — run it after committing, and read the line saying which source it used. It reported 20
passed on a `pyproject.toml` naming a package directory that had been retired, because the directory
was still on disk holding nothing but a `__pycache__` that `git rm` does not remove (DG-355).

## Things that will bite you here

- **Config precedence is fixed, and nothing discovers a file by climbing.** Per field: an
  **environment variable** wins, then the **registry**, then the project's own `.agents/*.json`. An
  env var is explicit and named — that is how a container passes a different identity in. A `.env`
  found by walking up the tree is neither, and it used to be loaded into `os.environ` first, so it
  arrived disguised as rule 1 and *outranked* the registry. Nothing reads a `.env` now.
  `os.getcwd()` plus a loop over `os.path.dirname` is the signature — grep for it, do not reason
  about it.
- **Never let import-time failure be a failure mode.** Anything that can fail must fail inside a
  tool call, so the caller reads a message instead of watching a server vanish. Use
  `core/errors.py` — every error carries a remediation, because "unknown project 'alpha'" only tells
  an agent to give up.
- **Every outbound HTTP call goes through `core/http.py`.** One `# nosec`, on the guard itself.
- **A tool refuses rather than guesses which project it is about.** Every `jira_*` tool takes the
  registry project id as its first argument, and a missing or unknown one is refused with the
  registered ids named (DG-341). No fallback to a single registered project, to the first key in the
  registry file, or to the working directory: a server that guessed filed work onto another
  project's board and reported success.
- **`drunken-doctor` checks that a credential works, not that a project exists.** It printed
  `OK … (project ALPHA)` while Jira answered *"No project could be found"* (DG-260). Verify a project
  key against the API before trusting a green line. The same shape twice over: a check whose default
  root list was empty read every host config as fine (DG-358), and its ai_layer check reports ours
  are installed without noticing what else is (DG-359). **Ask what a check cannot see.**
- **Never edit `uv.lock` with a global `sed`** (DG-327). The pre-commit hook's `uv run` re-locks it
  the moment `pyproject.toml` changes — check `git diff --numstat uv.lock` and know why each line
  moved.
- `uv run pytest` failing with `No module named 'scripts'` on a stale venv means `uv sync --extra dev`.
