# mypy: ignore-errors
"""DG-514 Gate D. Wraps ``scripts/release_smoke.py`` as a pytest test, deselected by default the
same way the repository's ``e2e`` and ``routing`` marks already are (see ``pyproject.toml``) --
this one is slow for a different reason (a real ``uv build`` and ``uv venv`` per run, several
minutes, not a live network call), but belongs out of the default run for the same reason: run on
purpose, before a tag, never on every plain ``pytest``.

Run directly: ``uv run pytest -m integration tests/test_release_smoke.py -s``
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_smoke  # noqa: E402 - path set up above, this module lives outside src/


@pytest.mark.integration
def test_release_smoke_passes_end_to_end(capsys) -> None:
    """The whole point of this file: run the real smoke test and fail loudly, with the full
    PASS/FAIL table, if the release candidate it just built and installed is not actually ready —
    this is what must be run, deliberately, before any 2.0.2 tag."""
    exit_code = release_smoke.main()
    captured = capsys.readouterr()
    with capsys.disabled():
        print(captured.out)
    assert exit_code == 0, (
        "the release smoke test failed -- see the PASS/FAIL table above for which check, and do "
        f"not tag until every line is PASS\n{captured.out}"
    )
