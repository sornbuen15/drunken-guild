# mypy: ignore-errors
"""DG-451. One hardened git caller, not two.

``core.exclude.run_git`` strips every ``GIT_*`` environment variable before
it ever runs ``git`` (see that module's docstring for why a fixed strip list
was wrong). ``core.doctor.tracked_ai_layer_paths`` ran a second, unstripped
``subprocess.run(["git", "ls-files", "-z"])`` instead, so a leaked
``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE`` could make it misreport.

Fixing that one call is not the same as there being no second call left
anywhere in ``src/`` — the next module to need git is exactly as likely to
open a fresh ``subprocess.run(["git", ...])`` as this one was. This scans
``src/`` for that literal shape and fails on anything found outside
``core.exclude`` (where ``run_git`` is defined) and the short, named
allowlist below.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import Final

SRC_ROOT: Final = Path(__file__).resolve().parent.parent / "src"

#: Paths relative to `src/`, each with the reason a raw git subprocess call
#: there is allowed to exist outside `core.exclude.run_git`. Keep this short
#: — a long allowlist is this check giving up on itself.
ALLOWLIST: Final[dict[str, str]] = {
    "core/exclude.py": (
        "defines run_git itself: the one unstripped call every other "
        "module routes through, not a second implementation beside it "
        "(DG-451)."
    ),
}

#: `subprocess` functions that actually launch a process. `DEVNULL`,
#: `PIPE`, `TimeoutExpired` and friends are not calls, and are already
#: excluded by only matching `ast.Call` nodes.
_SUBPROCESS_RUN_NAMES: Final = frozenset(
    {"run", "Popen", "call", "check_output", "check_call"}
)


def _is_subprocess_call(func: ast.expr) -> bool:
    """Whether *func* is ``subprocess.<run|Popen|call|...>``.

    Matched as ``subprocess.<name>`` only — the attribute form every call in
    this codebase uses (``import subprocess``, never
    ``from subprocess import run``). Nothing here does the latter today;
    see the module docstring on this being a literal-pattern scan rather
    than a general one.
    """
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _SUBPROCESS_RUN_NAMES
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def _first_arg_is_literal_git(call: ast.Call) -> bool:
    """Whether *call*'s first positional argument is a literal ``["git", ...]``.

    Only a literal ``list``/``tuple`` whose first element is the literal
    string ``"git"`` counts. A command built through a variable —
    ``cmd = ["git", *args]; subprocess.run(cmd)``, or the executable named
    by one — is not a literal here and this deliberately does not try to
    trace it; see the module docstring.
    """
    if not call.args:
        return False
    first = call.args[0]
    if not isinstance(first, (ast.List, ast.Tuple)) or not first.elts:
        return False
    head = first.elts[0]
    return isinstance(head, ast.Constant) and head.value == "git"


def find_raw_git_subprocess_calls(source: str, filename: str = "<test>") -> list[int]:
    """Line numbers in *source* carrying a raw ``subprocess.<fn>(["git", ...])``.

    Takes source text rather than a path so the scanner itself — this
    function — can be exercised directly against a synthetic snippet,
    independent of what currently sits in ``src/``.
    """
    tree = ast.parse(source, filename=filename)
    hits: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and _is_subprocess_call(node.func)
            and _first_arg_is_literal_git(node)
        ):
            hits.append(node.lineno)
    return hits


class TestTheScannerItselfOnSyntheticSource:
    """Exercises the scanner function in isolation, independent of whatever
    `src/` currently contains — these would read the same before and after
    the DG-451 fix, which is the point: they are about the *detector*, not
    about today's code being clean.
    """

    def test_a_literal_git_list_is_found(self) -> None:
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                return subprocess.run(["git", "status"], cwd=".")
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_a_literal_git_tuple_is_also_found(self) -> None:
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                return subprocess.Popen(("git", "log"))
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_shutil_which_git_is_not_a_subprocess_call_and_is_not_flagged(
        self,
    ) -> None:
        """`shutil.which("git")` only *looks up* git on PATH — it never
        starts a process, and nothing about it can be redirected by a
        leaked `GIT_*` variable. A scanner fooled by the string "git"
        anywhere in a call would flag this; it must not.
        """
        source = textwrap.dedent(
            """
            import shutil

            def f():
                return shutil.which("git")
            """
        )
        assert find_raw_git_subprocess_calls(source) == []

    def test_a_non_git_subprocess_call_is_not_flagged(self) -> None:
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                return subprocess.run(["uv", "tool", "dir"])
            """
        )
        assert find_raw_git_subprocess_calls(source) == []

    def test_run_git_itself_is_not_double_counted_as_a_violation(self) -> None:
        """The pattern `core.exclude.run_git` itself contains —
        `subprocess.run(["git", *args], ...)` — is exactly this shape, and
        the scanner is expected to find it: the allowlist in the real test
        below is what excuses `core/exclude.py`, not the scanner pretending
        not to see it. This just pins that the scanner does see it, so the
        allowlist is doing real work rather than hiding an already-blind
        scanner.
        """
        source = textwrap.dedent(
            """
            import subprocess

            def run_git(args, repo_root):
                return subprocess.run(["git", *args], cwd=repo_root)
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_mutation_scanner_is_blind_to_a_variable_built_command_stated_limit(
        self,
    ) -> None:
        """Stated limitation, verified rather than merely claimed: a command
        list assembled through a variable is a real blind spot of this
        literal-pattern scanner, and this pins that it stays a blind spot
        rather than silently starting to matter. Nothing in `src/` builds a
        git command this way today (checked by hand during DG-451); if that
        ever changes, this test is the signal to replace the scanner with
        something that traces data flow instead.
        """
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                cmd = ["git", "status"]
                return subprocess.run(cmd)
            """
        )
        assert find_raw_git_subprocess_calls(source) == [], (
            "this is the scanner's known, accepted blind spot — a hit here "
            "would mean the scanner got smarter than this test expected, "
            "which is fine, but then this test (and the docstring above) "
            "need updating rather than silently going stale"
        )


class TestSrcHasNoRawGitSubprocessCallOutsideTheHelper:
    def test_no_raw_git_subprocess_call_outside_the_allowlist(self) -> None:
        violations: list[str] = []
        for py_file in sorted(SRC_ROOT.rglob("*.py")):
            relative = py_file.relative_to(SRC_ROOT).as_posix()
            if relative in ALLOWLIST:
                continue
            hits = find_raw_git_subprocess_calls(
                py_file.read_text(encoding="utf-8"), filename=str(py_file)
            )
            if hits:
                violations.append(f"{relative}:{','.join(map(str, hits))}")

        assert not violations, (
            'raw subprocess.run(["git", ...]) found in src/ outside '
            "core.exclude.run_git and the allowlist above this test — route "
            f"it through core.exclude.run_git instead: {violations}"
        )

    def test_mutation_reintroducing_a_raw_git_call_is_caught(
        self, tmp_path: Path
    ) -> None:
        """Seen failing first against a real reintroduction (pasted into the
        PR body): a scratch module placed under `src/` with a raw
        `subprocess.run(["git", ...])` call must make the full-repository
        test above fail, naming that file. This proxies the real `src/`
        scan at a throwaway root so the mutation never has to touch the
        actual tree, while exercising the exact same walk-and-scan code
        path as the test above.
        """
        fake_src = tmp_path / "src"
        (fake_src / "core").mkdir(parents=True)
        (fake_src / "core" / "exclude.py").write_text(
            "import subprocess\n\n"
            "def run_git(args, repo_root):\n"
            '    return subprocess.run(["git", *args], cwd=repo_root)\n',
            encoding="utf-8",
        )
        mutated = fake_src / "core" / "some_new_module.py"
        mutated.write_text(
            "import subprocess\n\n"
            "def ask_git_something(repo_root):\n"
            '    return subprocess.run(["git", "status"], cwd=repo_root)\n',
            encoding="utf-8",
        )

        violations: list[str] = []
        for py_file in sorted(fake_src.rglob("*.py")):
            relative = py_file.relative_to(fake_src).as_posix()
            if relative in ALLOWLIST:
                continue
            hits = find_raw_git_subprocess_calls(
                py_file.read_text(encoding="utf-8"), filename=str(py_file)
            )
            if hits:
                violations.append(f"{relative}:{','.join(map(str, hits))}")

        assert violations == ["core/some_new_module.py:4"], (
            "a raw git subprocess call reintroduced anywhere under src/ "
            f"must be caught and named. Got {violations!r}"
        )
