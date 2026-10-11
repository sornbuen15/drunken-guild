# mypy: ignore-errors
"""DG-451 (review follow-up on PR #146, Jira comment 11458). One hardened
git caller, not two.

``core.exclude.run_git`` strips every ``GIT_*`` environment variable before
it ever runs ``git`` (see that module's docstring for why a fixed strip list
was wrong). ``core.doctor.tracked_ai_layer_paths`` ran a second, unstripped
``subprocess.run(["git", "ls-files", "-z"])`` instead, so a leaked
``GIT_DIR``/``GIT_WORK_TREE``/``GIT_INDEX_FILE`` could make it misreport.

Fixing that one call is not the same as there being no second call left
anywhere in ``src/`` — the next module to need git is exactly as likely to
open a fresh one as this one was. This scans ``src/`` for the shapes that
launch a process naming ``git`` and fails on anything found outside
``core.exclude`` (where ``run_git`` is defined) and the short, named
allowlist below.

What it catches, each proven by its own test below and by a mutation run
against the implementation (pasted into the PR body rather than kept here —
a mutation that stays in the tree is not a mutation):

* ``subprocess.run``/``Popen``/``call``/``check_output``/``check_call`` —
  however the module is imported: ``import subprocess``,
  ``import subprocess as sp``, or a bare name via
  ``from subprocess import run`` / ``from subprocess import run as r``.
* A literal ``["git", ...]``/``("git", ...)`` first argument, **or** a
  string first argument whose first word is ``git`` — ``"git status"``,
  with or without ``shell=True``.
* ``os.system``/``os.popen`` on a string starting with ``git``, under the
  same import-aliasing rules as above.
* A first list/tuple element that is a bare name **bound at module level**
  to the literal string ``"git"`` (``GIT = "git"``;
  ``subprocess.run([GIT, ...])``).

Stated limit, verified rather than merely claimed
(``test_mutation_scanner_is_blind_to_a_variable_built_command_stated_limit``
below): a command assembled at runtime — built inside a function, read from
a config, concatenated — is not caught. This is a literal/import-aliasing
scan, not a dataflow one, and module-level name resolution is the one piece
of "where did this value come from" it does. Nothing in ``src/`` builds a
git command any other way today (checked by hand during this review); if
that changes, the pinned test above is the signal to replace this scanner
with something that traces data flow instead of extending it further.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import Final, Optional

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

#: `os` functions that run a string through a shell on their own, the same
#: class of risk as `subprocess.run(..., shell=True)`.
_OS_RUN_NAMES: Final = frozenset({"system", "popen"})


def _collect_aliases(
    tree: ast.Module,
) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """How *tree*'s own imports and module-level assignments name things.

    Three results:

    * ``module_alias``: every name bound to the ``subprocess`` or ``os``
      module itself — ``{"subprocess": "subprocess", "sp": "subprocess"}``
      for ``import subprocess`` plus ``import subprocess as sp``.
    * ``func_alias``: every name bound *directly* to one of the run
      functions via ``from subprocess import run`` (optionally
      ``as alias``) or the `os` equivalents — mapped to a canonical
      ``"subprocess.run"``/``"os.system"``-style string so the caller
      doesn't need to know which module it came from.
    * ``module_level_git_names``: names assigned the literal string
      ``"git"`` by a plain ``NAME = "git"`` at module top level — not
      inside a function or class, and not through tuple/multiple
      assignment, which this does not attempt to unpack. A name
      reassigned later to something else still counts: this is a
      conservative, over-matching approximation on purpose, because a
      false alarm here costs a human one look, and a missed real one is
      the thing DG-451 exists to stop.
    """
    module_alias: dict[str, str] = {}
    func_alias: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "os"):
                    module_alias[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                names = _SUBPROCESS_RUN_NAMES
                canonical_module = "subprocess"
            elif node.module == "os":
                names = _OS_RUN_NAMES
                canonical_module = "os"
            else:
                continue
            for alias in node.names:
                if alias.name in names:
                    bound = alias.asname or alias.name
                    func_alias[bound] = f"{canonical_module}.{alias.name}"

    module_level_git_names = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and node.value.value == "git"
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    return module_alias, func_alias, module_level_git_names


def _canonical_callee(
    call: ast.Call, module_alias: dict[str, str], func_alias: dict[str, str]
) -> Optional[str]:
    """``"subprocess.run"``/``"os.system"`` *call* actually resolves to, or
    ``None`` if it is neither — resolved through *this file's own* imports,
    not by the literal spelling at the call site.
    """
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        module = module_alias.get(func.value.id)
        if module == "subprocess" and func.attr in _SUBPROCESS_RUN_NAMES:
            return f"subprocess.{func.attr}"
        if module == "os" and func.attr in _OS_RUN_NAMES:
            return f"os.{func.attr}"
        return None
    if isinstance(func, ast.Name):
        return func_alias.get(func.id)
    return None


def _first_word(text: str) -> str:
    stripped = text.strip()
    return stripped.split()[0] if stripped else ""


def _arg_names_git(arg: ast.expr, module_level_git_names: set[str]) -> bool:
    """Whether *arg* — a call's first positional argument — names ``git``.

    A literal ``["git", ...]``/``("git", ...)``, a literal string whose
    first word is ``git`` (covers ``"git status"`` with or without
    ``shell=True`` — this does not look at the ``shell=`` keyword at all,
    since the risk is the same either way), or a bare name this module
    binds at module level to the literal string ``"git"``.
    """
    if isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
        head = arg.elts[0]
        if isinstance(head, ast.Constant) and head.value == "git":
            return True
        if isinstance(head, ast.Name) and head.id in module_level_git_names:
            return True
        return False
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return _first_word(arg.value) == "git"
    return False


def find_raw_git_subprocess_calls(source: str, filename: str = "<test>") -> list[int]:
    """Line numbers in *source* carrying a raw call that launches ``git``.

    Takes source text rather than a path so the scanner itself — this
    function — can be exercised directly against a synthetic snippet,
    independent of what currently sits in ``src/``. Import aliasing and
    module-level name resolution are per-file: a name this file binds has
    no effect on how another file's calls are read.
    """
    tree = ast.parse(source, filename=filename)
    module_alias, func_alias, module_level_git_names = _collect_aliases(tree)

    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        canonical = _canonical_callee(node, module_alias, func_alias)
        if canonical is None:
            continue
        if _arg_names_git(node.args[0], module_level_git_names):
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
        list assembled *inside a function* is a real blind spot of this
        scanner — it only resolves names bound at module level, not a
        local. This pins that it stays a blind spot rather than silently
        starting to matter. Nothing in `src/` builds a git command this way
        today (checked by hand during DG-451); if that ever changes, this
        test is the signal to replace the scanner with something that
        traces data flow instead.
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

    def test_aliased_module_import_is_caught(self) -> None:
        """`import subprocess as sp` must be resolved back to `subprocess`
        before the attribute is matched — the reviewer's reproduction (PR
        #146, Jira comment 11458): the pre-follow-up scanner matched only
        the literal name `subprocess`, so this read as clean."""
        source = textwrap.dedent(
            """
            import subprocess as sp

            def f():
                return sp.run(["git", "status"])
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_aliased_os_module_import_is_caught(self) -> None:
        source = textwrap.dedent(
            """
            import os as _os

            def f():
                return _os.system("git status")
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_bare_name_from_import_is_caught(self) -> None:
        """`from subprocess import run` then a bare `run(...)` call, with
        no `subprocess.` attribute at all — the second half of the same
        reviewer finding."""
        source = textwrap.dedent(
            """
            from subprocess import run

            def f():
                return run(["git", "status"])
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_bare_name_from_import_with_as_alias_is_caught(self) -> None:
        source = textwrap.dedent(
            """
            from subprocess import run as r, Popen, check_output

            def f():
                r(["git", "status"])
                Popen(("git", "log"))
                return check_output(["git", "diff"])
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5, 6, 7]

    def test_bare_name_from_os_import_with_as_alias_is_caught(self) -> None:
        source = textwrap.dedent(
            """
            from os import system as run_shell

            def f():
                return run_shell("git status")
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_unrelated_from_import_name_is_not_a_false_match(self) -> None:
        """`from subprocess import DEVNULL` binds a name that is not one of
        the run functions at all — it must never be treated as a callable
        alias just because it came from `subprocess`."""
        source = textwrap.dedent(
            """
            from subprocess import DEVNULL
            import subprocess

            def f():
                return subprocess.run(["uv", "x"], stdout=DEVNULL)
            """
        )
        assert find_raw_git_subprocess_calls(source) == []

    def test_string_command_with_shell_true_is_caught(self) -> None:
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                return subprocess.run("git status", shell=True)
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_string_command_without_shell_is_also_caught(self) -> None:
        """No `shell=True` at all — `subprocess.run("git status")` treats
        the whole string as a single (nonexistent) executable name and
        would fail at run time, but the *shape* is exactly as wrong as the
        `shell=True` case and must be caught the same way, not excused for
        being additionally broken."""
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                return subprocess.run("git status")
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_a_non_git_string_command_is_not_flagged(self) -> None:
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                return subprocess.run("uv tool dir", shell=True)
            """
        )
        assert find_raw_git_subprocess_calls(source) == []

    def test_os_system_git_is_caught(self) -> None:
        source = textwrap.dedent(
            """
            import os

            def f():
                return os.system("git status")
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_os_popen_git_is_caught(self) -> None:
        source = textwrap.dedent(
            """
            import os

            def f():
                return os.popen("git log")
            """
        )
        assert find_raw_git_subprocess_calls(source) == [5]

    def test_os_system_non_git_is_not_flagged(self) -> None:
        source = textwrap.dedent(
            """
            import os

            def f():
                return os.system("uv tool dir")
            """
        )
        assert find_raw_git_subprocess_calls(source) == []

    def test_module_level_git_name_in_a_list_is_caught(self) -> None:
        """`GIT = "git"` at module scope, then `[GIT, ...]` as the first
        argument — the reviewer's third finding."""
        source = textwrap.dedent(
            """
            import subprocess

            GIT = "git"

            def f():
                return subprocess.run([GIT, "status"])
            """
        )
        assert find_raw_git_subprocess_calls(source) == [7]

    def test_a_function_local_name_bound_to_git_is_not_caught(self) -> None:
        """The module-level resolution above is deliberately scoped to
        module level only — a *local* `git = "git"` inside a function is
        not resolved, which is the same stated limitation as the
        variable-built-list test above, from a different angle."""
        source = textwrap.dedent(
            """
            import subprocess

            def f():
                git = "git"
                return subprocess.run([git, "status"])
            """
        )
        assert find_raw_git_subprocess_calls(source) == []

    def test_a_module_level_name_bound_to_something_else_is_not_caught(self) -> None:
        source = textwrap.dedent(
            """
            import subprocess

            UV = "uv"

            def f():
                return subprocess.run([UV, "tool", "dir"])
            """
        )
        assert find_raw_git_subprocess_calls(source) == []


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
            "a raw call launching git was found in src/ outside "
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
