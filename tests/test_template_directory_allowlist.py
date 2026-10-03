# mypy: ignore-errors
"""DG-433. Closes a gap DG-430 (PR 130) left open on purpose.

`test_instruction_file_pointers.py`'s `_template_dirs_read_by()` derives the
directories `scaffold.py` reads a packaged template from by a regex over
*`scaffold.py`'s own source text*, matching only the one call shape that
exists there today: `resources.files("core").joinpath("templates/...")`. The
reviewer showed two ways that passes silently:

1. A second real template read written another way, e.g.
   ``resources.files("core") / "templates/other/X.md"`` -- the regex looks
   for the literal text ``joinpath("templates/`` and never matches a ``/``
   operator.
2. A template read anywhere other than `scaffold.py` -- `init.py`,
   `doctor.py`, an installer -- since the derivation only ever calls
   ``inspect.getsource(scaffold)``.

Both gaps share one shape: a *new template-bearing directory appears under
`src/core/templates/` and nothing notices*, whatever read it or however the
read was spelled. Rather than widen the extractor to chase every call shape
across every file that might one day read a packaged template -- open-ended,
and still only as good as the last shape anyone thought to add -- this is
the smaller fix: a plain static list of every directory actually shipped
there, checked bidirectionally against what is really on disk. A directory
appearing on either side without the other catches it, independent of any
source-code shape.

The pointer is bidirectional: `src/core/scaffold.py` carries a comment next
to its packaged-template reads naming this module, so an editor adding a
new one meets the rule coming from either direction.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _template_dirs_read_by_joinpath_regex(source: str) -> set[str]:
    """A standalone replica of DG-430's own derivation
    (`test_instruction_file_pointers._template_dirs_read_by`), kept here
    only to prove the gap this ticket is about is real: it matches the one
    call shape that exists in `scaffold.py` today,
    ``resources.files("core").joinpath("templates/...")``, and nothing
    else. Never used by the directory-level check below -- only by the
    proof test that shows the regex is blind to a different call shape."""
    prefixes: set[str] = set()
    for rel in re.findall(r'joinpath\("(templates/[^"]+)"\)', source):
        prefix = "src/core/" + rel.rsplit("/", 1)[0] + "/"
        prefixes.add(prefix)
    return prefixes


#: Every directory that actually holds a shipped template file under
#: `src/core/templates/`, relative to REPO_ROOT, trailing slash. Add a
#: directory here in the same change that adds it on disk --
#: `test_every_shipped_template_directory_is_listed` fails otherwise,
#: whichever file reads it and however the read is spelled.
KNOWN_TEMPLATE_DIRS: frozenset[str] = frozenset({"src/core/templates/"})


def _shipped_template_dirs(root: Path) -> set[str]:
    """Every directory under ``root / "src/core/templates"`` that holds at
    least one file, walked from disk rather than restated -- so a directory
    added without a matching list entry is exactly what this exists to
    catch."""
    templates_root = root / "src" / "core" / "templates"
    if not templates_root.is_dir():
        return set()
    dirs: set[str] = set()
    for path in templates_root.rglob("*"):
        if path.is_file():
            dirs.add(path.parent.relative_to(root).as_posix() + "/")
    return dirs


def test_every_shipped_template_directory_is_listed() -> None:
    shipped = _shipped_template_dirs(REPO_ROOT)
    missing = shipped - KNOWN_TEMPLATE_DIRS
    assert not missing, (
        f"{sorted(missing)!r} holds a packaged template file but is not in "
        "KNOWN_TEMPLATE_DIRS in this file -- add it in the same change, "
        "whatever reads it and however the read is spelled"
    )


def test_every_listed_directory_is_real() -> None:
    """The other direction: a listed directory that holds no file -- never
    created, or removed on disk without the list being updated -- is drift
    of its own and must not be silently tolerated."""
    shipped = _shipped_template_dirs(REPO_ROOT)
    stale = KNOWN_TEMPLATE_DIRS - shipped
    assert not stale, (
        f"{sorted(stale)!r} is listed in KNOWN_TEMPLATE_DIRS but holds no "
        "shipped template file on disk -- remove it, or add the file it "
        "was meant to cover"
    )


# --- Proof the gaps DG-430 left open are real, and that the directory-level
# check above catches both without caring which file or call shape caused a
# new directory to exist. Each builds a scratch repository layout under
# tmp_path -- never the tracked tree -- with a new, genuinely unlisted
# directory under src/core/templates/, and shows the static check fires.


def test_the_old_source_regex_misses_a_different_call_shape() -> None:
    """Mutation 1: a second real template read written with the `/`
    operator instead of `.joinpath(...)`. `_template_dirs_read_by()` --
    DG-430's own derivation, scoped to `scaffold.py`'s source text -- finds
    nothing for it, proving the gap this ticket is about is real."""
    fake_source = (
        'template = resources.files("core") / "templates/other/BRAND_NEW.md"\n'
    )

    prefixes = _template_dirs_read_by_joinpath_regex(fake_source)

    assert prefixes == set(), (
        "the source-regex derivation found a prefix for a `/`-operator read "
        "-- it should find none, since that is exactly the call shape it "
        "cannot see"
    )


def test_a_new_call_shape_reading_an_unlisted_directory_is_caught(
    tmp_path: Path,
) -> None:
    """Mutation 1, the other half: whatever call shape produced it, a new
    *directory* under `src/core/templates/` that nothing added to
    KNOWN_TEMPLATE_DIRS is caught by the directory-level check, unlike the
    source-regex derivation proven blind to it above."""
    fake_root = tmp_path / "fake-repo"
    new_dir = fake_root / "src" / "core" / "templates" / "other"
    new_dir.mkdir(parents=True)
    (new_dir / "BRAND_NEW.md").write_text("new packaged template\n", encoding="utf-8")
    # The one directory that is genuinely listed, mirrored so the proof is
    # about the *new* directory only.
    (fake_root / "src" / "core" / "templates" / "AGENTS.md").write_text(
        "existing template\n", encoding="utf-8"
    )

    shipped = _shipped_template_dirs(fake_root)
    missing = shipped - KNOWN_TEMPLATE_DIRS

    assert missing == {"src/core/templates/other/"}, (
        "the directory-level check did not flag the new, unlisted "
        "directory the different call shape would have read from"
    )


def test_a_read_outside_scaffold_py_reading_an_unlisted_directory_is_caught(
    tmp_path: Path,
) -> None:
    """Mutation 2: a template read added to a file other than `scaffold.py`
    -- `doctor.py`, `init.py`, an installer -- is invisible to DG-430's
    derivation, which only ever inspects `scaffold.py`'s own source. The
    directory-level check does not care which file did the reading: a new,
    unlisted directory under `src/core/templates/` is caught the same way
    regardless."""
    fake_root = tmp_path / "fake-repo"
    new_dir = fake_root / "src" / "core" / "templates" / "doctor_only"
    new_dir.mkdir(parents=True)
    (new_dir / "DOCTOR_EXTRA.md").write_text(
        "read only by doctor.py\n", encoding="utf-8"
    )
    (fake_root / "src" / "core" / "templates" / "AGENTS.md").write_text(
        "existing template\n", encoding="utf-8"
    )

    # DG-430's own derivation never looks at doctor.py at all -- there is no
    # source to hand it. The directory-level check needs no such source.
    shipped = _shipped_template_dirs(fake_root)
    missing = shipped - KNOWN_TEMPLATE_DIRS

    assert missing == {"src/core/templates/doctor_only/"}, (
        "the directory-level check did not flag the new, unlisted "
        "directory a read outside scaffold.py would have used"
    )
