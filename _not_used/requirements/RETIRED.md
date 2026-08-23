# requirements.txt — retired

Retired 2026-08-23 under DG-281. Kept rather than deleted, per `CLAUDE.md`:
marking a thing unused beats removing it.

## Why

Nothing read it. CI installs from `pyproject.toml`; `pip-audit --strict` reads
`requirements-dev.txt`. The Dockerfile does not use this file either — it
generates its own lock inline:

```dockerfile
RUN uv export --format requirements-txt --no-emit-project --no-dev \
        > /tmp/requirements.lock.txt \
 && uv tool install . --with-requirements /tmp/requirements.lock.txt
```

The only thing that touched it was `scripts/lock_deps.sh`, which wrote it.

By the time it was retired, recompiling it from `pyproject.toml` produced a
113-line diff — packages missing outright, not merely older versions. A
production lockfile nobody installs from is a claim about the project that
nothing checks, and this one had been wrong long enough to prove it.

## What replaced it

Nothing, because nothing depended on it.

- **Reproducible installs** come from `uv.lock`, exported on demand: the
  Dockerfile line above, and `core.config_gen.export_requirements()` for the
  `drunken-config` install command. That export writes `requirements.lock.txt`,
  which is gitignored on purpose — generated when needed, never committed, so
  it cannot drift.
- **The dev environment** comes from `uv sync --extra dev`.
  `requirements-dev.txt` is compiled from `pyproject.toml` and exists for
  `pip-audit` alone.

## Why the extension

The file is `requirements.txt.retired`, not `requirements.txt`, and the suffix is
load-bearing — do not "tidy" it back.

Dependabot alerts come from GitHub's dependency graph, which parses manifests by
filename anywhere in the repository. Retiring the file into `_not_used/` did not
take it out of that range: three alerts followed it here, all for `aiohttp
3.14.1`, a version nothing in this project installs — `uv.lock` resolves 3.14.3.

`.github/dependabot.yml` cannot fix that. Its `exclude-paths` option suppresses
automatic *pull requests*, not alerts, and the dependency graph offers no path
exclusion at all. A name the graph does not recognise as a manifest is the only
lever available (DG-290).

The cost of leaving it was not noise for its own sake: a genuine alert —
`cryptography` in `uv.lock`, DG-289 — was sitting in a list of four where three
were about software the project does not run.

## If you need it back

`scripts/lock_deps.sh` no longer writes it. Regenerate with the same tool that
compiles the rest:

```bash
uv pip compile pyproject.toml -o requirements.txt
```

Restoring the file is not enough on its own. Give it a reader first, or it will
drift again exactly as it did — and it will start raising alerts again the moment
it carries a manifest's name.
