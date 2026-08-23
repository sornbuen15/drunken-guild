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

## If you need it back

`scripts/lock_deps.sh` no longer writes it. Regenerate with the same tool that
compiles the rest:

```bash
uv pip compile pyproject.toml -o requirements.txt
```

Restoring the file is not enough on its own. Give it a reader first, or it will
drift again exactly as it did.
