"""DG-477: a subprocess spawned by a test does not inherit an in-process
monkeypatch, only its environment.

`conftest.hermetic_drunken_home` and `conftest.forbid_real_registry_access`
(DG-460) make every *in-process* `ProjectRegistry()` call hermetic by
patching `__init__` and setting `$DRUNKEN_HOME`. Neither reaches a child
process: a test that calls `subprocess.run(..., env={...})` with a hand-built
dict replaces the whole environment for that child, dropping `DRUNKEN_HOME`
(and the deleted `DRUNKEN_REGISTRY_PATH` / `DRUNKEN_AUTH_DB`) along with it,
so a nested interpreter resolves the operator's real registry path — never
opened here, but reproduced by the DG-460 reviewer with a stripped, copied
environment.

This is a static check, not a runtime guard: it reads every file under
`tests/` with `ast` and fails naming the file and line of any
`subprocess.run` / `.Popen` / `.check_output` / `.check_call` / `.call` whose
`env=` is built from scratch rather than derived from `os.environ` (which
already carries whatever the autouse fixtures set), or that at least
explicitly forwards a `DRUNKEN_*` variable. A call with no `env=` at all
inherits the whole parent environment and needs no check.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent

_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "check_output", "check_call", "call"})

_MAX_NAME_LOOKUP_DEPTH = 5


def _is_os_environ(node: ast.AST) -> bool:
    """True for the bare expression `os.environ`."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _is_os_environ_copy(node: ast.AST) -> bool:
    """True for `os.environ.copy()`."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "copy"
        and _is_os_environ(node.func.value)
    )


def _is_dict_of_os_environ(node: ast.AST) -> bool:
    """True for `dict(os.environ)`, the other common copy idiom."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and len(node.args) == 1
        and (_is_os_environ(node.args[0]) or _is_os_environ_copy(node.args[0]))
    )


def _has_drunken_key(node: ast.Dict) -> bool:
    """True if a dict literal names a `DRUNKEN_*` key outright.

    An env dict that explicitly sets one of these has not dropped the
    sandbox; it opted into it by hand instead of inheriting it.
    """
    for key in node.keys:
        if (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and key.value.startswith("DRUNKEN_")
        ):
            return True
    return False


def _is_sandboxed_env_expr(
    node: ast.AST,
    assignments: dict[str, list[ast.Assign]],
    before_lineno: int,
    depth: int = 0,
) -> bool:
    """True if *node* is an env= expression that carries the sandbox forward.

    Recognised as safe: `os.environ` itself, `os.environ.copy()`,
    `dict(os.environ)`, a dict literal that unpacks any of those
    (`{**os.environ, ...}`), a dict literal naming a `DRUNKEN_*` key
    outright, or a local variable name whose nearest preceding assignment
    resolves to one of the above.
    """
    if depth > _MAX_NAME_LOOKUP_DEPTH:
        return False

    if (
        _is_os_environ(node)
        or _is_os_environ_copy(node)
        or _is_dict_of_os_environ(node)
    ):
        return True

    if isinstance(node, ast.Dict):
        if _has_drunken_key(node):
            return True
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None and _is_sandboxed_env_expr(
                value, assignments, before_lineno, depth + 1
            ):
                return True
        return False

    if isinstance(node, ast.Name):
        candidates = [
            assign
            for assign in assignments.get(node.id, [])
            if assign.lineno < before_lineno
        ]
        if not candidates:
            return False
        latest = max(candidates, key=lambda assign: assign.lineno)
        return _is_sandboxed_env_expr(
            latest.value, assignments, before_lineno, depth + 1
        )

    return False


def _is_subprocess_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _SUBPROCESS_FUNCS
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def _simple_name_assignments(tree: ast.AST) -> dict[str, list[ast.Assign]]:
    """Every `name = <expr>` in the module, keyed by name.

    Deliberately flat (no per-function scoping): good enough to resolve the
    "build it in a local, pass the local" shape these tests use, and a
    false negative here only means this check misses a case it should
    still catch -- not that it reports a safe call as unsafe.
    """
    out: dict[str, list[ast.Assign]] = defaultdict(list)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            out[node.targets[0].id].append(node)
    return out


def find_unsandboxed_subprocess_env_calls(source: str, filename: str) -> list[str]:
    """Every `subprocess.*` call in *source* whose `env=` drops the sandbox.

    Returns one message per offending call, naming *filename* and the line.
    A call with no `env=` keyword inherits the whole parent environment
    (DRUNKEN_* included) and is never flagged.
    """
    tree = ast.parse(source, filename=filename)
    assignments = _simple_name_assignments(tree)
    violations: list[str] = []

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_subprocess_call(node)):
            continue
        env_keyword = next((kw for kw in node.keywords if kw.arg == "env"), None)
        if env_keyword is None:
            continue
        if _is_sandboxed_env_expr(env_keyword.value, assignments, node.lineno):
            continue
        violations.append(
            f"{filename}:{node.lineno}: subprocess env= is built from scratch "
            "without carrying the sandboxed DRUNKEN_* variables (or "
            "os.environ) forward -- a child process could resolve the "
            "operator's real registry path (DG-477). Build it from "
            "os.environ.copy() or {**os.environ, ...} instead."
        )

    return violations


class TestTheCheckItselfCatchesAnOffender:
    """Proves the check is not vacuous, against literal source strings --
    never against a real subprocess, so this never itself spawns a child
    that could reach anything real."""

    def test_a_dict_literal_with_no_drunken_key_is_flagged(self) -> None:
        source = (
            "import subprocess\nsubprocess.run(['python'], env={'PATH': '/usr/bin'})\n"
        )
        violations = find_unsandboxed_subprocess_env_calls(source, "offender.py")
        assert len(violations) == 1, violations
        assert "offender.py:2" in violations[0]

    def test_a_locally_built_dict_passed_by_name_is_also_flagged(self) -> None:
        source = (
            "import subprocess\n"
            "env = {'PATH': '/usr/bin', 'LANG': 'C'}\n"
            "subprocess.run(['python'], env=env)\n"
        )
        violations = find_unsandboxed_subprocess_env_calls(source, "offender2.py")
        assert len(violations) == 1, violations

    def test_a_call_with_no_env_kwarg_is_not_flagged(self) -> None:
        source = "import subprocess\nsubprocess.run(['git', 'status'])\n"
        assert find_unsandboxed_subprocess_env_calls(source, "fine.py") == []

    def test_os_environ_copy_is_not_flagged(self) -> None:
        source = (
            "import os, subprocess\nsubprocess.run(['python'], env=os.environ.copy())\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "fine2.py") == []

    def test_unpacking_os_environ_in_a_dict_literal_is_not_flagged(self) -> None:
        source = (
            "import os, subprocess\n"
            "subprocess.run(['python'], env={**os.environ, 'LC_ALL': 'C'})\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "fine3.py") == []

    def test_a_dict_literal_naming_a_drunken_key_is_not_flagged(self) -> None:
        """An author who writes `DRUNKEN_HOME` by hand has thought about the
        sandbox, even without deriving from os.environ."""
        source = (
            "import subprocess\n"
            "subprocess.run(['python'], env={'DRUNKEN_HOME': '/tmp/x'})\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "fine4.py") == []

    def test_dict_of_os_environ_is_not_flagged(self) -> None:
        source = (
            "import os, subprocess\nsubprocess.run(['python'], env=dict(os.environ))\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "fine6.py") == []

    def test_a_local_dict_derived_from_os_environ_then_passed_by_name_is_not_flagged(
        self,
    ) -> None:
        source = (
            "import os, subprocess\n"
            "env = os.environ.copy()\n"
            "env['LC_ALL'] = 'C'\n"
            "subprocess.run(['python'], env=env)\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "fine5.py") == []


class TestMutatingTheCheckLosesCoverage:
    """Documents what the check depends on by breaking each dependency in
    turn and showing a known offender stops being caught -- the mutation
    side of "prove it is not vacuous."."""

    _OFFENDER = (
        "import subprocess\nsubprocess.run(['python'], env={'PATH': '/usr/bin'})\n"
    )

    def test_removing_the_env_keyword_check_misses_it(self) -> None:
        """Mutation: treat every subprocess call as fine regardless of
        env=. The real check must not behave this way."""

        def _mutated_always_safe(source: str, filename: str) -> list[str]:
            return []  # pretend env= is never worth inspecting

        real = find_unsandboxed_subprocess_env_calls(self._OFFENDER, "x.py")
        mutated = _mutated_always_safe(self._OFFENDER, "x.py")
        assert real != [] and mutated == [], (
            "the mutation that ignores env= entirely must disagree with "
            "the real check on this offender"
        )

    def test_treating_every_dict_literal_as_sandboxed_misses_it(self) -> None:
        """Mutation: `_is_sandboxed_env_expr` returns True for any ast.Dict
        without inspecting its keys or unpacking."""

        def _mutated_is_sandboxed_env_expr(
            node: ast.AST,
            assignments: dict[str, list[ast.Assign]],
            before_lineno: int,
            depth: int = 0,
        ) -> bool:
            return (
                isinstance(node, ast.Dict)
                or _is_os_environ(node)
                or (isinstance(node, ast.Call))
            )

        tree = ast.parse(self._OFFENDER, filename="x.py")
        assignments = _simple_name_assignments(tree)
        call = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and _is_subprocess_call(n)
        )
        env_value = next(kw.value for kw in call.keywords if kw.arg == "env")

        real_flags_it = not _is_sandboxed_env_expr(env_value, assignments, call.lineno)
        mutated_flags_it = not _mutated_is_sandboxed_env_expr(
            env_value, assignments, call.lineno
        )
        assert real_flags_it and not mutated_flags_it, (
            "the mutation that treats any dict literal as sandboxed must "
            "disagree with the real check on this offender"
        )


class TestEveryExistingSubprocessCallInTestsPasses:
    """ACCEPTANCE: every subprocess call already in tests/ passes the check."""

    def test_no_test_file_builds_an_unsandboxed_subprocess_env(self) -> None:
        all_violations: list[str] = []
        for path in sorted(TESTS_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            all_violations.extend(
                find_unsandboxed_subprocess_env_calls(
                    source, str(path.relative_to(REPO_ROOT))
                )
            )
        assert all_violations == [], (
            "found subprocess calls that drop the sandboxed environment:\n"
            + "\n".join(all_violations)
        )
