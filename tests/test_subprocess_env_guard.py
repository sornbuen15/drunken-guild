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
`tests/` with `ast` and fails, naming the file and line, on any
`subprocess`/`os`/`asyncio` call that spawns a child process with a hand-built
`env=` that does not provably carry the sandbox forward. A call with no
`env=` at all (and no `**kwargs` that could be hiding one) inherits the whole
parent environment and is never flagged; `os.system`/`os.popen` take no `env=`
parameter at all and are never flagged either.

Round 2 (DG-477 review, Jira comment 11674, PASS WITH CONDITIONS): the first
version of this check had two HIGH-severity gaps closed here --

1. A dict literal naming *any* `DRUNKEN_*` key was treated as safe regardless
   of that key's *value*, so `env={"DRUNKEN_HOME": "/real/operator/home"}`
   passed clean. A `DRUNKEN_*` override is now safe only when its value is
   provably sandboxed: a `tmp_path`/`tmp_path_factory`-derived expression or a
   variable that is itself a fixture parameter of the enclosing test. A
   string literal, `Path.home()`, `os.path.expanduser(...)`, or anything else
   this check cannot trace to one of those sources is flagged.
2. Only the assignment that built `env` was inspected -- a later
   `env.pop("DRUNKEN_HOME", None)`, `del env["DRUNKEN_HOME"]`, `env.clear()`,
   or `env.update(...)` / `env[...] = ...` / `env.setdefault(...)` that
   overwrites a `DRUNKEN_*` key with an unsandboxed value passed clean even
   though it strips the sandbox right back out before the subprocess call.
   Every statement between the variable's assignment and its use as `env=`,
   in the same function, is now walked for exactly these mutations.

Caveat this check does not cover (LOW, noted rather than fixed): "no `env=`
at all is safe" relies on the sandbox fixtures in `conftest.py` being
*function-scoped* and *autouse*. A module- or session-scoped fixture that
builds a registry, or spawns a subprocess, *before* the function-scoped
`hermetic_drunken_home`/`forbid_real_registry_access` guards are in effect
for that test is not something a per-call static check can see at all --
that needs a fixture-ordering review, not this.
"""

from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent

_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
_OS_NO_ENV_FUNCS = frozenset({"system", "popen"})
_OS_SPAWN_E_FUNCS = frozenset({"spawnve", "spawnle", "spawnvpe", "spawnlpe"})
_ASYNCIO_FUNCS = frozenset({"create_subprocess_exec", "create_subprocess_shell"})

#: `subprocess.Popen(args, bufsize, executable, stdin, stdout, stderr,
#: preexec_fn, close_fds, shell, cwd, env, ...)` -- `env` is the 11th
#: positional parameter. Nobody in this repository passes it positionally
#: today; this is "best effort" cover for the shape, not a claim every test
#: here exercises it.
_POPEN_ENV_POSITION = 10

_MAX_DEPTH = 6

#: Calls this check cannot prove safe or unsafe (env hidden behind forwarded
#: **kwargs, or an opaque function-parameter env=) and that a human has
#: reviewed and accepted anyway. Each entry must carry a reason here, not
#: just in the call site.
_ALLOWLISTED_UNPROVABLE: frozenset[tuple[str, int]] = frozenset(
    {
        # test_operator_inventory_push.py::_run -- `env.update(extra_env)`
        # where `extra_env` is a caller-supplied dict this check cannot see
        # into. Every current call site passes a literal dict of
        # PRE_COMMIT_* keys (no DRUNKEN_*), and `_run` itself now asserts
        # that at runtime before the update -- a future call site adding a
        # DRUNKEN_* override would fail that assert, not silently reach the
        # subprocess.
        (str(Path("tests") / "test_operator_inventory_push.py"), 95),
    }
)


# --------------------------------------------------------------------------
# Safe-source recognisers
# --------------------------------------------------------------------------


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
    """True for plain `dict(os.environ)` -- no extra overrides."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and len(node.args) == 1
        and not node.keywords
        and (_is_os_environ(node.args[0]) or _is_os_environ_copy(node.args[0]))
    )


def _derives_from_os_environ(node: ast.AST) -> bool:
    return (
        _is_os_environ(node)
        or _is_os_environ_copy(node)
        or _is_dict_of_os_environ(node)
    )


#: Fixtures defined in `tests/conftest.py` that *return* a path under a
#: per-test scratch directory, and so are as safe a provenance source for a
#: `DRUNKEN_*` override as `tmp_path` itself -- each entry here must name
#: the fixture and say why it qualifies, the same discipline
#: `_ALLOWLISTED_UNPROVABLE` already applies to call sites. Deliberately
#: empty today: `hermetic_drunken_home` (DG-460) *sets* `$DRUNKEN_HOME`
#: itself and returns nothing a test could reuse, and no other fixture in
#: `tests/conftest.py` hands back a scratch path by name. An expression
#: naming a fixture not on this list is rejected (DG-484) -- add it here,
#: with a reason, rather than widening what counts as "provenance".
_SANDBOX_FIXTURE_ALLOWLIST: frozenset[str] = frozenset()


def _is_safe_leaf_name(node: ast.AST, ctx: "_FunctionContext") -> bool:
    """True for a bare `tmp_path`, a `tmp_path_factory.mktemp(...)` call, or
    a name on `_SANDBOX_FIXTURE_ALLOWLIST` -- the only tokens a `/` join or
    an f-string placeholder may be built from (DG-484). Anything else,
    including a parameter that merely *looks* like a fixture, is rejected."""
    if isinstance(node, ast.Name):
        return node.id == "tmp_path" or node.id in _SANDBOX_FIXTURE_ALLOWLIST
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "mktemp"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "tmp_path_factory"
    )


def _is_safe_join_operand(node: ast.AST, ctx: "_FunctionContext") -> bool:
    """A right-hand `/` operand: a safe leaf, or a string literal that is
    not a `..` segment -- DG-484 (low): `tmp_path / '..' / '..'` can walk
    back out of the scratch directory, so `..` is rejected even though it
    is "just a literal"."""
    if _is_safe_leaf_name(node, ctx):
        return True
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value != ".."
    )


def _is_safe_join(node: ast.AST, ctx: "_FunctionContext") -> bool:
    """True for a bare safe leaf, or a chain of `/` whose left side is
    itself safe and whose right side is a safe leaf or a non-`..` string
    literal -- `tmp_path / "a" / "b"`, not `tmp_path / helper()`."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _is_safe_join(node.left, ctx) and _is_safe_join_operand(node.right, ctx)
    return _is_safe_leaf_name(node, ctx)


def _is_safe_wrapped(node: ast.AST, ctx: "_FunctionContext") -> bool:
    """True for `str(X)`, `Path(X)`, or `os.fspath(X)` where *X* is itself
    provenance-safe -- the only wrappers this check unwraps. A call to
    anything else (a helper, `Path.home`, `os.path.expanduser`) is rejected
    outright: SCOPE's "reject ... a Call" means *any* unrecognised one,
    not just the ones that happen to look suspicious."""
    if not isinstance(node, ast.Call) or node.keywords or len(node.args) != 1:
        return False
    func = node.func
    is_str_or_path = isinstance(func, ast.Name) and func.id in {"str", "Path"}
    is_os_fspath = (
        isinstance(func, ast.Attribute)
        and func.attr == "fspath"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    )
    if not (is_str_or_path or is_os_fspath):
        return False
    return _is_provenance_safe(node.args[0], ctx)


def _is_safe_fstring(node: ast.AST, ctx: "_FunctionContext") -> bool:
    """True for an f-string built only of plain text and placeholders that
    are themselves provenance-safe -- `f"{tmp_path}/{tmp_path_factory.mktemp('x')}"`,
    not `f"{tmp_path}/{Path.home()}"`: every `FormattedValue` must resolve,
    and a conversion/format-spec is rejected as unrecognised rather than
    assumed harmless."""
    if not isinstance(node, ast.JoinedStr):
        return False
    for value in node.values:
        if isinstance(value, ast.Constant):
            continue
        if (
            isinstance(value, ast.FormattedValue)
            and value.format_spec is None
            and _is_provenance_safe(value.value, ctx)
        ):
            continue
        return False
    return True


def _is_provenance_safe(node: ast.AST, ctx: "_FunctionContext") -> bool:
    """True if *node*'s outermost shape is provably one of: a bare
    `tmp_path`/allow-listed name, `tmp_path_factory.mktemp(...)`,
    `str(...)`/`Path(...)`/`os.fspath(...)` of one of these, a `/` join of
    these (literal segments allowed, `..` is not), or an f-string built
    only from these and plain text (DG-484).

    Anything else -- another `Name` (an unlisted fixture, a module), a
    `Call` this doesn't recognise (`Path.home()`, `os.path.expanduser`, a
    helper that may ignore its argument), or a conditional expression -- is
    rejected outright. Mentioning a safe name *somewhere inside* a larger
    expression this function doesn't trace is not provenance; only the
    shapes above are.
    """
    return (
        _is_safe_join(node, ctx)
        or _is_safe_wrapped(node, ctx)
        or _is_safe_fstring(node, ctx)
    )


def _string_key(node: ast.AST | None) -> str | None:
    """The literal string a dict key / subscript / `.pop()` argument names,
    or `None` if it is not a plain string constant (a dynamic key is treated
    as "could be anything, including a DRUNKEN_* one" by every caller)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


#: Only the registry-resolution variables DG-460's fixtures sandbox --
#: `core.paths.ENV_HOME` / `ENV_REGISTRY` / `ENV_AUTH_DB`. Deliberately not
#: "any DRUNKEN_* key": `DRUNKEN_NO_REGISTERED_PROJECTS` is a real,
#: unrelated opt-out flag an existing test passes through `env.update()`,
#: and flagging every `DRUNKEN_*` name would make that a false offender.
_SANDBOX_ENV_VARS = frozenset(
    {"DRUNKEN_HOME", "DRUNKEN_REGISTRY_PATH", "DRUNKEN_AUTH_DB"}
)


def _is_drunken_key(key: str | None) -> bool:
    """A dynamic/unresolvable key is assumed to possibly be one of
    `_SANDBOX_ENV_VARS` -- fail closed rather than silently trusting it."""
    return key is None or key in _SANDBOX_ENV_VARS


# --------------------------------------------------------------------------
# Per-scope context: local assignments and mutations of `env`-like dicts
# --------------------------------------------------------------------------


@dataclass
class _Mutation:
    lineno: int
    kind: str  # "clear" | "pop" | "del" | "setitem" | "update_item" | "setdefault"
    key: str | None
    value: ast.AST | None


@dataclass
class _FunctionContext:
    assignments: dict[str, list[ast.Assign]] = field(
        default_factory=lambda: defaultdict(list)
    )
    mutations: dict[str, list[_Mutation]] = field(
        default_factory=lambda: defaultdict(list)
    )
    param_names: set[str] = field(default_factory=set)


def _param_names(scope_node: ast.AST) -> set[str]:
    if not isinstance(scope_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return set()
    args = scope_node.args
    names = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _update_call_pairs(call: ast.Call) -> list[tuple[str | None, ast.AST | None]]:
    """Every (key, value) an `.update(...)` call would set, as best as can
    be told statically: a literal-dict positional arg is read key by key, a
    non-literal positional arg (`.update(some_mapping)`) contributes one
    unresolvable pair, and each keyword argument is one pair of its own."""
    pairs: list[tuple[str | None, ast.AST | None]] = []
    if call.args and isinstance(call.args[0], ast.Dict):
        for key_node, value_node in zip(
            call.args[0].keys, call.args[0].values, strict=True
        ):
            pairs.append(
                (_string_key(key_node) if key_node is not None else None, value_node)
            )
    elif call.args:
        pairs.append((None, None))  # update(some_other_mapping) -- can't see its keys
    for kw in call.keywords:
        pairs.append((kw.arg, kw.value) if kw.arg is not None else (None, None))
    return pairs


def _mutation_for_method(call: ast.Call, method: str) -> list[_Mutation]:
    if method == "clear":
        return [_Mutation(call.lineno, "clear", None, None)]
    if method == "pop":
        key = _string_key(call.args[0]) if call.args else None
        return [_Mutation(call.lineno, "pop", key, None)]
    if method == "setdefault":
        key = _string_key(call.args[0]) if call.args else None
        value = call.args[1] if len(call.args) > 1 else None
        return [_Mutation(call.lineno, "setdefault", key, value)]
    if method == "update":
        return [
            _Mutation(call.lineno, "update_item", key, value)
            for key, value in _update_call_pairs(call)
        ]
    return []


def _record_method_mutation(
    call: ast.Call, mutations: dict[str, list[_Mutation]]
) -> None:
    """Notices `.pop()` / `.clear()` / `.update()` / `.setdefault()` calls on
    a local dict variable. The one function the "ignore mutations after the
    copy" mutation (see `TestMutationsAfterTheCopyAreTracked`) disables."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
        return
    mutations[func.value.id].extend(_mutation_for_method(call, func.attr))


def _record_assign(node: ast.Assign, ctx: _FunctionContext) -> None:
    if len(node.targets) != 1:
        return
    target = node.targets[0]
    if isinstance(target, ast.Name):
        ctx.assignments[target.id].append(node)
    elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
        key = _string_key(target.slice)
        ctx.mutations[target.value.id].append(
            _Mutation(node.lineno, "setitem", key, node.value)
        )


def _record_delete(node: ast.Delete, ctx: _FunctionContext) -> None:
    for target in node.targets:
        if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
            key = _string_key(target.slice)
            ctx.mutations[target.value.id].append(
                _Mutation(node.lineno, "del", key, None)
            )


def _build_function_context(scope_node: ast.AST) -> _FunctionContext:
    """Assignments and mutations declared *directly* in *scope_node*'s own
    body -- a nested `def`/`async def` gets its own context when the caller
    reaches it, so a variable in an outer function is never mistaken for one
    in an inner one, or vice versa."""
    ctx = _FunctionContext(param_names=_param_names(scope_node))

    def _walk(node: ast.AST, top: bool) -> None:
        if not top and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if isinstance(node, ast.Assign):
            _record_assign(node, ctx)
        elif isinstance(node, ast.Delete):
            _record_delete(node, ctx)
        elif isinstance(node, ast.Call):
            _record_method_mutation(node, ctx.mutations)
        for child in ast.iter_child_nodes(node):
            _walk(child, top=False)

    _walk(scope_node, top=True)
    return ctx


# --------------------------------------------------------------------------
# Safety resolution
# --------------------------------------------------------------------------


def _is_sandbox_value_source(
    node: ast.AST, ctx: _FunctionContext, before_lineno: int, depth: int = 0
) -> bool:
    """True if *node* -- a `DRUNKEN_*` override's *value* -- provably comes
    from a sandbox: its outermost shape is one `_is_provenance_safe`
    recognises (DG-484), it derives from `os.environ`, or it is a local
    variable name whose own, most recent assignment before *before_lineno*
    recursively does. A string literal, `Path.home()`,
    `os.path.expanduser(...)`, a helper call, a conditional expression, or
    a parameter/fixture not on `_SANDBOX_FIXTURE_ALLOWLIST` is NOT
    recognised -- fail closed rather than guess."""
    if depth > _MAX_DEPTH:
        return False
    if _is_provenance_safe(node, ctx):
        return True
    if _derives_from_os_environ(node):
        return True
    if isinstance(node, ast.Name):
        candidates = [
            a for a in ctx.assignments.get(node.id, []) if a.lineno < before_lineno
        ]
        if candidates:
            latest = max(candidates, key=lambda a: a.lineno)
            return _is_sandbox_value_source(latest.value, ctx, before_lineno, depth + 1)
    return False


def _dict_call_with_environ_and_overrides(
    node: ast.AST, ctx: _FunctionContext, before_lineno: int, depth: int
) -> bool | None:
    """Handles `dict(os.environ, DRUNKEN_HOME=...)`. Returns `None` if *node*
    is not this shape at all, else the safety verdict."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
    ):
        return None
    if not node.args or not (
        _is_os_environ(node.args[0]) or _is_os_environ_copy(node.args[0])
    ):
        return None
    for kw in node.keywords:
        if kw.arg is None:
            return False  # dict(os.environ, **unknown) -- cannot verify
        if kw.arg in _SANDBOX_ENV_VARS and not _is_sandbox_value_source(
            kw.value, ctx, before_lineno, depth + 1
        ):
            return False
    return True


def _is_provably_empty_dict(node: ast.AST) -> bool:
    return isinstance(node, ast.Dict) and not node.keys


def _dict_literal_is_safe(
    node: ast.Dict, ctx: _FunctionContext, before_lineno: int, depth: int
) -> bool:
    derives_from_environ = False
    overrides: list[tuple[str, ast.AST]] = []

    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            if _derives_from_os_environ(value) or (
                isinstance(value, ast.Name)
                and _resolve_env_safety(value, ctx, before_lineno, depth + 1)
            ):
                derives_from_environ = True
            elif _is_provably_empty_dict(value):
                pass  # unpacking {} adds nothing
            else:
                # Unpacking a mapping we cannot prove is free of DRUNKEN_*
                # overrides (e.g. `**(extra_env or {})`) -- fail closed
                # rather than assume it is harmless.
                return False
            continue
        key_name = _string_key(key)
        if key_name is not None and key_name in _SANDBOX_ENV_VARS:
            overrides.append((key_name, value))

    if derives_from_environ:
        return all(
            _is_sandbox_value_source(value, ctx, before_lineno, depth + 1)
            for _key, value in overrides
        )

    # No os.environ derivation at all: the dict replaces the whole
    # environment. Safe only if it explicitly overrides a DRUNKEN_* key with
    # a provably sandboxed value -- naming the key is not enough on its own.
    if not overrides:
        return False
    return all(
        _is_sandbox_value_source(value, ctx, before_lineno, depth + 1)
        for _key, value in overrides
    )


def _resolve_name_with_mutations(
    name: str, ctx: _FunctionContext, before_lineno: int, depth: int
) -> bool:
    candidates = [a for a in ctx.assignments.get(name, []) if a.lineno < before_lineno]
    if not candidates:
        return False
    latest_assign = max(candidates, key=lambda a: a.lineno)
    state = _resolve_env_safety(latest_assign.value, ctx, before_lineno, depth + 1)

    relevant = sorted(
        (
            m
            for m in ctx.mutations.get(name, [])
            if latest_assign.lineno < m.lineno < before_lineno
        ),
        key=lambda m: m.lineno,
    )
    for mutation in relevant:
        if mutation.kind == "clear":
            state = False  # wipes every key, sandbox included
        elif mutation.kind in ("pop", "del"):
            if _is_drunken_key(mutation.key):
                state = (
                    False  # strips the sandbox var back out before the child sees it
                )
        elif mutation.kind in ("setitem", "update_item", "setdefault"):
            if _is_drunken_key(mutation.key):
                if mutation.value is not None and _is_sandbox_value_source(
                    mutation.value, ctx, before_lineno, depth + 1
                ):
                    state = True
                else:
                    state = False
        # non-DRUNKEN_* key mutations don't change whether the sandbox var survives
    return state


def _resolve_env_safety(
    node: ast.AST, ctx: _FunctionContext, before_lineno: int, depth: int = 0
) -> bool:
    if depth > _MAX_DEPTH:
        return False

    dict_call_verdict = _dict_call_with_environ_and_overrides(
        node, ctx, before_lineno, depth
    )
    if dict_call_verdict is not None:
        return dict_call_verdict

    if _derives_from_os_environ(node):
        return True

    if isinstance(node, ast.Dict):
        return _dict_literal_is_safe(node, ctx, before_lineno, depth)

    if isinstance(node, ast.Name):
        if node.id in ctx.assignments:
            return _resolve_name_with_mutations(node.id, ctx, before_lineno, depth)
        # A bare function parameter with no local history: an opaque,
        # pre-built env handed in from outside. Cannot prove it carries the
        # sandbox forward -- flagged rather than trusted (DG-477 review
        # finding #4: "env from a function parameter" is unprovable).
        return False

    return False


# --------------------------------------------------------------------------
# Call-shape recognition: subprocess.*, os.system/popen/spawn*e, asyncio.*
# --------------------------------------------------------------------------


@dataclass
class _Aliases:
    subprocess_modules: set[str] = field(default_factory=set)
    os_modules: set[str] = field(default_factory=set)
    asyncio_modules: set[str] = field(default_factory=set)
    direct_subprocess_funcs: dict[str, str] = field(default_factory=dict)
    direct_os_funcs: dict[str, str] = field(default_factory=dict)
    direct_asyncio_funcs: dict[str, str] = field(default_factory=dict)


def _record_import(node: ast.Import, aliases: _Aliases) -> None:
    for alias in node.names:
        bound = alias.asname or alias.name
        if alias.name == "subprocess":
            aliases.subprocess_modules.add(bound)
        elif alias.name == "os":
            aliases.os_modules.add(bound)
        elif alias.name == "asyncio":
            aliases.asyncio_modules.add(bound)


def _record_import_from(node: ast.ImportFrom, aliases: _Aliases) -> None:
    if node.module == "subprocess":
        target, allowed = aliases.direct_subprocess_funcs, _SUBPROCESS_FUNCS
    elif node.module == "os":
        target, allowed = aliases.direct_os_funcs, _OS_NO_ENV_FUNCS | _OS_SPAWN_E_FUNCS
    elif node.module == "asyncio":
        target, allowed = aliases.direct_asyncio_funcs, _ASYNCIO_FUNCS
    else:
        return
    for alias in node.names:
        if alias.name in allowed:
            target[alias.asname or alias.name] = alias.name


def _collect_aliases(tree: ast.AST) -> _Aliases:
    aliases = _Aliases()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _record_import(node, aliases)
        elif isinstance(node, ast.ImportFrom):
            _record_import_from(node, aliases)
    return aliases


def _call_kind_for_attribute(func: ast.Attribute, aliases: _Aliases) -> str | None:
    if not isinstance(func.value, ast.Name):
        return None
    base, attr = func.value.id, func.attr
    if base in aliases.subprocess_modules and attr in _SUBPROCESS_FUNCS:
        return "popen_like" if attr == "Popen" else "keyword_only"
    if base in aliases.os_modules:
        if attr in _OS_NO_ENV_FUNCS:
            return "no_env"
        if attr in _OS_SPAWN_E_FUNCS:
            return "spawn_e"
    if base in aliases.asyncio_modules and attr in _ASYNCIO_FUNCS:
        return "keyword_only"
    return None


def _call_kind_for_name(func: ast.Name, aliases: _Aliases) -> str | None:
    if func.id in aliases.direct_subprocess_funcs:
        original = aliases.direct_subprocess_funcs[func.id]
        return "popen_like" if original == "Popen" else "keyword_only"
    if func.id in aliases.direct_os_funcs:
        original = aliases.direct_os_funcs[func.id]
        return "no_env" if original in _OS_NO_ENV_FUNCS else "spawn_e"
    if func.id in aliases.direct_asyncio_funcs:
        return "keyword_only"
    return None


def _call_kind(call: ast.Call, aliases: _Aliases) -> str | None:
    """One of "popen_like" (positional env possible), "keyword_only" (env
    only ever arrives as a keyword), "spawn_e" (env is the last positional
    argument), "no_env" (the function takes no env= at all), or `None` (not
    a call this check recognises)."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return _call_kind_for_attribute(func, aliases)
    if isinstance(func, ast.Name):
        return _call_kind_for_name(func, aliases)
    return None


def _find_env_argument(call: ast.Call, kind: str) -> tuple[ast.AST | None, bool]:
    """Returns `(env_expression, hidden_in_unknown_kwargs)`. `env_expression`
    is `None` when there genuinely is no `env=` to check (safe: full
    inherit) -- unless `hidden_in_unknown_kwargs` is True, meaning a
    forwarded `**something` could be carrying one this check cannot see."""
    env_kw = next((kw for kw in call.keywords if kw.arg == "env"), None)
    if env_kw is not None:
        return env_kw.value, False

    has_double_star = any(kw.arg is None for kw in call.keywords)

    if kind == "popen_like" and len(call.args) > _POPEN_ENV_POSITION:
        return call.args[_POPEN_ENV_POSITION], False
    if kind == "spawn_e" and call.args:
        return call.args[-1], False

    return None, has_double_star


def _evaluate_call(
    call: ast.Call, aliases: _Aliases, ctx: _FunctionContext
) -> str | None:
    kind = _call_kind(call, aliases)
    if kind is None or kind == "no_env":
        return None

    env_expr, hidden_in_kwargs = _find_env_argument(call, kind)
    if env_expr is None:
        if hidden_in_kwargs:
            return (
                "env= may be hidden inside forwarded **kwargs here -- cannot "
                "prove it carries the sandboxed DRUNKEN_* variables forward "
                "(DG-477)"
            )
        return None  # no env= at all: full inherit, safe

    if _resolve_env_safety(env_expr, ctx, call.lineno):
        return None

    return (
        "subprocess env= is built from scratch without provably carrying "
        "the sandboxed DRUNKEN_* variables (or os.environ) forward -- a "
        "child process could resolve the operator's real registry path "
        "(DG-477). Build it from os.environ.copy() or {**os.environ, ...}, "
        "or override DRUNKEN_* keys with a tmp_path-derived value."
    )


def find_unsandboxed_subprocess_env_calls(source: str, filename: str) -> list[str]:
    """Every subprocess-spawning call in *source* whose `env=` drops the
    sandbox, or might be hiding one inside forwarded `**kwargs`. Returns one
    message per offending call, naming *filename* and the line."""
    tree = ast.parse(source, filename=filename)
    aliases = _collect_aliases(tree)
    violations: list[str] = []
    contexts: dict[int, _FunctionContext] = {}

    def _context_for(scope_node: ast.AST) -> _FunctionContext:
        key = id(scope_node)
        if key not in contexts:
            contexts[key] = _build_function_context(scope_node)
        return contexts[key]

    def _visit(node: ast.AST, scope_node: ast.AST) -> None:
        if isinstance(node, ast.Call):
            message = _evaluate_call(node, aliases, _context_for(scope_node))
            if (
                message is not None
                and (filename, node.lineno) not in _ALLOWLISTED_UNPROVABLE
            ):
                violations.append(f"{filename}:{node.lineno}: {message}")
        next_scope = (
            node
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            else scope_node
        )
        for child in ast.iter_child_nodes(node):
            _visit(child, next_scope)

    _visit(tree, tree)
    return violations


# --------------------------------------------------------------------------
# File discovery (DG-477 review finding #3: recursive, and provably exhaustive)
# --------------------------------------------------------------------------


def discover_test_files(root: Path) -> list[Path]:
    """Every `.py` file under *root*, recursively, except bytecode caches."""
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def find_all_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in discover_test_files(root):
        source = path.read_text(encoding="utf-8")
        try:
            display_name = str(path.relative_to(REPO_ROOT))
        except ValueError:
            display_name = str(path)  # root is outside the repo (a scratch dir)
        violations.extend(find_unsandboxed_subprocess_env_calls(source, display_name))
    return violations


def _independent_recursive_py_file_count(root: Path) -> int:
    """Counts `.py` files by a completely different route (`os.walk`) than
    `discover_test_files` (`Path.rglob`), so the two can be compared without
    one secretly being a copy of the other."""
    count = 0
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        count += sum(1 for name in filenames if name.endswith(".py"))
    return count


# ==========================================================================
# Tests
# ==========================================================================


class TestBaselineSafeIdioms:
    """The idioms every existing call in tests/ actually uses."""

    def test_a_dict_literal_with_no_drunken_key_and_no_environ_is_flagged(self) -> None:
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
        assert len(find_unsandboxed_subprocess_env_calls(source, "offender2.py")) == 1

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


class TestOverrideValueMustComeFromASandboxSource:
    """DG-477 review, HIGH #1: a `DRUNKEN_*` key's *value* must be checked,
    not just its presence."""

    _LITERAL_PATH_OFFENDER = (
        "import subprocess\n"
        "def test_x():\n"
        "    subprocess.run(['python'], env={'DRUNKEN_HOME': '/real/operator/home'})\n"
    )
    _DICT_CALL_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    subprocess.run(['python'], env=dict(os.environ, DRUNKEN_HOME='/real/home'))\n"
    )
    _PATH_HOME_OFFENDER = (
        "import subprocess\n"
        "from pathlib import Path\n"
        "def test_x():\n"
        "    subprocess.run(['python'], env={'DRUNKEN_HOME': str(Path.home())})\n"
    )
    _EXPANDUSER_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    subprocess.run(['python'], env={'DRUNKEN_HOME': os.path.expanduser('~')})\n"
    )
    _TMP_PATH_OVERRIDE_IS_SAFE = (
        "import subprocess\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(['python'], env={'DRUNKEN_HOME': str(tmp_path / 'home')})\n"
    )
    #: DG-484: a parameter is no longer trusted just because it is *a*
    #: parameter of the enclosing test -- `sandbox_home` is not
    #: `tmp_path`, not `tmp_path_factory`-derived, and not on the
    #: documented allow-list in `tests/conftest.py` (which defines no such
    #: fixture), so this must now be flagged rather than trusted.
    _UNLISTED_FIXTURE_PARAM_OFFENDER = (
        "import os, subprocess\n"
        "def test_x(sandbox_home):\n"
        "    subprocess.run(\n"
        "        ['python'], env=dict(os.environ, DRUNKEN_HOME=str(sandbox_home))\n"
        "    )\n"
    )

    def test_a_literal_real_looking_path_is_flagged(self) -> None:
        assert (
            len(
                find_unsandboxed_subprocess_env_calls(
                    self._LITERAL_PATH_OFFENDER, "x.py"
                )
            )
            == 1
        )

    def test_dict_of_environ_with_a_literal_drunken_override_is_flagged(self) -> None:
        assert (
            len(find_unsandboxed_subprocess_env_calls(self._DICT_CALL_OFFENDER, "x.py"))
            == 1
        )

    def test_path_home_as_the_override_value_is_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(self._PATH_HOME_OFFENDER, "x.py")
            != []
        )

    def test_expanduser_as_the_override_value_is_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(self._EXPANDUSER_OFFENDER, "x.py")
            != []
        )

    def test_a_tmp_path_derived_override_is_not_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._TMP_PATH_OVERRIDE_IS_SAFE, "x.py"
            )
            == []
        )

    def test_an_unlisted_fixture_parameter_override_is_now_flagged(self) -> None:
        """DG-484: superseded by `TestOverrideValueRequiresRealProvenance`
        below -- "any parameter of the enclosing test" is no longer enough
        on its own."""
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._UNLISTED_FIXTURE_PARAM_OFFENDER, "x.py"
            )
            != []
        )

    def test_removing_the_value_check_misses_the_literal_path_offender(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A REAL mutation of the production `_is_sandbox_value_source` --
        the exact function this module's own checker calls -- patched to
        always say "safe", reproducing the escape hatch the reviewer found.
        The unmutated check must disagree with this mutant."""
        module = sys.modules[__name__]
        assert (
            find_unsandboxed_subprocess_env_calls(self._LITERAL_PATH_OFFENDER, "x.py")
            != []
        )

        monkeypatch.setattr(module, "_is_sandbox_value_source", lambda *a, **k: True)

        assert (
            find_unsandboxed_subprocess_env_calls(self._LITERAL_PATH_OFFENDER, "x.py")
            == []
        ), (
            "the mutation that trusts any override value regardless of its "
            "source must miss this offender -- if it doesn't, the real "
            "check isn't actually depending on _is_sandbox_value_source"
        )


class TestOverrideValueRequiresRealProvenance:
    """DG-484 (found in DG-477 review round 2, non-blocking): "mentions
    `tmp_path` or a fixture parameter anywhere in the expression" let an
    expression that *also* reaches the real home pass clean, because it
    never checked where the value's *outermost* shape actually came from.
    Every offender here is a real snippet parsed by the real, unmutated
    checker -- not a monkeypatched stand-in for it."""

    _FSTRING_MIXING_TMP_PATH_AND_REAL_HOME_OFFENDER = (
        "import subprocess\n"
        "from pathlib import Path\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(\n"
        "        ['python'],\n"
        "        env={'DRUNKEN_HOME': f'{tmp_path}/{Path.home()}'},\n"
        "    )\n"
    )
    _CONDITIONAL_EXPRESSION_OFFENDER = (
        "import subprocess\n"
        "from pathlib import Path\n"
        "def test_x(tmp_path, cond):\n"
        "    subprocess.run(\n"
        "        ['python'],\n"
        "        env={\n"
        "            'DRUNKEN_HOME': str(tmp_path) if cond else str(Path.home())\n"
        "        },\n"
        "    )\n"
    )
    _HELPER_CALL_IGNORING_ITS_ARGUMENT_OFFENDER = (
        "import subprocess\n"
        "def helper(_unused):\n"
        "    return '/real/operator/home'\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(\n"
        "        ['python'], env={'DRUNKEN_HOME': helper(tmp_path)}\n"
        "    )\n"
    )
    _PARENT_TRAVERSAL_OFFENDER = (
        "import subprocess\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(\n"
        "        ['python'],\n"
        "        env={'DRUNKEN_HOME': str(tmp_path / '..' / '..')},\n"
        "    )\n"
    )
    _STRING_CONCAT_WITH_OS_ENVIRON_OFFENDER = (
        "import os, subprocess\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(\n"
        "        ['python'],\n"
        "        env={'DRUNKEN_HOME': str(tmp_path) + os.environ['HOME']},\n"
        "    )\n"
    )
    _SLASH_JOIN_OF_LITERAL_SEGMENTS_IS_SAFE = (
        "import subprocess\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(\n"
        "        ['python'], env={'DRUNKEN_HOME': str(tmp_path / 'a' / 'b')}\n"
        "    )\n"
    )
    _FSTRING_OF_ONLY_TMP_PATH_AND_LITERAL_TEXT_IS_SAFE = (
        "import subprocess\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(\n"
        "        ['python'], env={'DRUNKEN_HOME': f'{tmp_path}/home'}\n"
        "    )\n"
    )
    _OS_FSPATH_OF_TMP_PATH_IS_SAFE = (
        "import os, subprocess\n"
        "def test_x(tmp_path):\n"
        "    subprocess.run(\n"
        "        ['python'], env={'DRUNKEN_HOME': os.fspath(tmp_path)}\n"
        "    )\n"
    )
    _TMP_PATH_FACTORY_MKTEMP_IS_SAFE = (
        "import subprocess\n"
        "def test_x(tmp_path_factory):\n"
        "    subprocess.run(\n"
        "        ['python'],\n"
        "        env={\n"
        "            'DRUNKEN_HOME': str(tmp_path_factory.mktemp('home'))\n"
        "        },\n"
        "    )\n"
    )

    def test_fstring_mixing_tmp_path_and_path_home_is_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._FSTRING_MIXING_TMP_PATH_AND_REAL_HOME_OFFENDER, "x.py"
            )
            != []
        )

    def test_conditional_expression_between_a_safe_and_an_unsafe_value_is_flagged(
        self,
    ) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._CONDITIONAL_EXPRESSION_OFFENDER, "x.py"
            )
            != []
        )

    def test_a_helper_call_that_ignores_tmp_path_is_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._HELPER_CALL_IGNORING_ITS_ARGUMENT_OFFENDER, "x.py"
            )
            != []
        )

    def test_parent_traversal_segments_are_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._PARENT_TRAVERSAL_OFFENDER, "x.py"
            )
            != []
        )

    def test_string_concatenation_with_os_environ_is_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._STRING_CONCAT_WITH_OS_ENVIRON_OFFENDER, "x.py"
            )
            != []
        )

    def test_a_slash_join_of_only_tmp_path_and_literal_segments_is_not_flagged(
        self,
    ) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._SLASH_JOIN_OF_LITERAL_SEGMENTS_IS_SAFE, "x.py"
            )
            == []
        )

    def test_an_fstring_of_only_tmp_path_and_literal_text_is_not_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._FSTRING_OF_ONLY_TMP_PATH_AND_LITERAL_TEXT_IS_SAFE, "x.py"
            )
            == []
        )

    def test_os_fspath_of_tmp_path_is_not_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._OS_FSPATH_OF_TMP_PATH_IS_SAFE, "x.py"
            )
            == []
        )

    def test_tmp_path_factory_mktemp_is_not_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._TMP_PATH_FACTORY_MKTEMP_IS_SAFE, "x.py"
            )
            == []
        )

    def test_a_fixture_on_the_documented_allowlist_is_not_flagged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The allow-list mechanism itself: a name added to it is trusted
        bare, the same way `tmp_path` is -- proven by extending the real,
        production allow-list rather than by stubbing the function that
        reads it."""
        module = sys.modules[__name__]
        source = (
            "import subprocess\n"
            "def test_x(sandbox_home):\n"
            "    subprocess.run(\n"
            "        ['python'], env={'DRUNKEN_HOME': str(sandbox_home)}\n"
            "    )\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []

        monkeypatch.setattr(
            module, "_SANDBOX_FIXTURE_ALLOWLIST", frozenset({"sandbox_home"})
        )

        assert find_unsandboxed_subprocess_env_calls(source, "x.py") == []

    def test_removing_the_provenance_check_misses_every_offender_above(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A REAL mutation of the production `_is_provenance_safe` -- always
        `True` -- reproducing the DG-484 finding exactly: every offender
        above must stop being flagged once this always says "safe"."""
        module = sys.modules[__name__]
        offenders = [
            self._FSTRING_MIXING_TMP_PATH_AND_REAL_HOME_OFFENDER,
            self._CONDITIONAL_EXPRESSION_OFFENDER,
            self._HELPER_CALL_IGNORING_ITS_ARGUMENT_OFFENDER,
            self._PARENT_TRAVERSAL_OFFENDER,
            self._STRING_CONCAT_WITH_OS_ENVIRON_OFFENDER,
        ]
        for offender in offenders:
            assert find_unsandboxed_subprocess_env_calls(offender, "x.py") != []

        monkeypatch.setattr(module, "_is_provenance_safe", lambda *a, **k: True)

        for offender in offenders:
            assert find_unsandboxed_subprocess_env_calls(offender, "x.py") == [], (
                "a provenance check that always says 'safe' must miss "
                "every DG-484 offender above"
            )

    def test_removing_the_call_rejection_misses_the_helper_offender(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A REAL mutation that treats any `Call` as automatically safe --
        the specific gap named in SCOPE ("reject any expression that also
        contains ... a Call"). `_is_safe_wrapped` is the function that
        would otherwise reject `helper(tmp_path)`; patched to always agree,
        it must miss that offender."""
        module = sys.modules[__name__]
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._HELPER_CALL_IGNORING_ITS_ARGUMENT_OFFENDER, "x.py"
            )
            != []
        )

        monkeypatch.setattr(module, "_is_safe_wrapped", lambda *a, **k: True)

        assert (
            find_unsandboxed_subprocess_env_calls(
                self._HELPER_CALL_IGNORING_ITS_ARGUMENT_OFFENDER, "x.py"
            )
            == []
        ), "a check that treats any Call as safe must miss the helper() offender"

    def test_removing_the_allowlist_check_trusts_any_unlisted_fixture(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A REAL mutation of `_is_safe_leaf_name` that drops the
        allow-list membership test, trusting *any* bare name the way the
        pre-DG-484 code trusted any fixture parameter."""
        module = sys.modules[__name__]
        source = (
            "import subprocess\n"
            "def test_x(sandbox_home):\n"
            "    subprocess.run(\n"
            "        ['python'], env={'DRUNKEN_HOME': str(sandbox_home)}\n"
            "    )\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []

        real_is_safe_leaf_name = module._is_safe_leaf_name

        def _trusts_any_name(node: ast.AST, ctx: object) -> bool:
            if isinstance(node, ast.Name):
                return True
            return bool(real_is_safe_leaf_name(node, ctx))

        monkeypatch.setattr(module, "_is_safe_leaf_name", _trusts_any_name)

        assert find_unsandboxed_subprocess_env_calls(source, "x.py") == [], (
            "a check that trusts any bare Name, allow-listed or not, must "
            "miss the unlisted fixture offender"
        )


class TestMutationsAfterTheCopyAreTracked:
    """DG-477 review, HIGH #2: a sandbox-derived `env` can still be stripped
    or overwritten between its assignment and the subprocess call."""

    _POP_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    env = os.environ.copy()\n"
        "    env.pop('DRUNKEN_HOME', None)\n"
        "    subprocess.run(['python'], env=env)\n"
    )
    _DEL_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    env = dict(os.environ)\n"
        "    del env['DRUNKEN_HOME']\n"
        "    subprocess.run(['python'], env=env)\n"
    )
    _CLEAR_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    env = os.environ.copy()\n"
        "    env.clear()\n"
        "    subprocess.run(['python'], env=env)\n"
    )
    _UPDATE_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    env = os.environ.copy()\n"
        "    env.update({'DRUNKEN_HOME': '/real/home'})\n"
        "    subprocess.run(['python'], env=env)\n"
    )
    _SETITEM_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    env = os.environ.copy()\n"
        "    env['DRUNKEN_HOME'] = '/real/home'\n"
        "    subprocess.run(['python'], env=env)\n"
    )
    _SETDEFAULT_OFFENDER = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    env = os.environ.copy()\n"
        "    env.setdefault('DRUNKEN_HOME', '/real/home')\n"
        "    subprocess.run(['python'], env=env)\n"
    )
    _SAFE_REASSIGNMENT = (
        "import os, subprocess\n"
        "def test_x(tmp_path):\n"
        "    env = os.environ.copy()\n"
        "    env['DRUNKEN_HOME'] = str(tmp_path / 'home')\n"
        "    subprocess.run(['python'], env=env)\n"
    )
    _UNRELATED_KEY_MUTATION_IS_SAFE = (
        "import os, subprocess\n"
        "def test_x():\n"
        "    env = os.environ.copy()\n"
        "    env['PATH'] = '/usr/bin'\n"
        "    subprocess.run(['python'], env=env)\n"
    )

    @pytest.mark.parametrize(  # type: ignore[misc]
        "offender",
        [
            _POP_OFFENDER,
            _DEL_OFFENDER,
            _CLEAR_OFFENDER,
            _UPDATE_OFFENDER,
            _SETITEM_OFFENDER,
            _SETDEFAULT_OFFENDER,
        ],
        ids=["pop", "del", "clear", "update", "setitem", "setdefault"],
    )
    def test_each_removal_or_unsafe_overwrite_is_flagged(self, offender: str) -> None:
        assert find_unsandboxed_subprocess_env_calls(offender, "x.py") != []

    def test_a_tmp_path_derived_reassignment_is_not_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(self._SAFE_REASSIGNMENT, "x.py") == []
        )

    def test_mutating_an_unrelated_key_is_not_flagged(self) -> None:
        assert (
            find_unsandboxed_subprocess_env_calls(
                self._UNRELATED_KEY_MUTATION_IS_SAFE, "x.py"
            )
            == []
        )

    def test_ignoring_mutations_after_the_copy_misses_the_pop_offender(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A REAL mutation of the production `_record_method_mutation` --
        the function that notices `.pop`/`.clear`/`.update`/`.setdefault` --
        patched to a no-op. The unmutated check must disagree."""
        module = sys.modules[__name__]
        assert find_unsandboxed_subprocess_env_calls(self._POP_OFFENDER, "x.py") != []

        monkeypatch.setattr(
            module, "_record_method_mutation", lambda call, mutations: None
        )

        assert (
            find_unsandboxed_subprocess_env_calls(self._POP_OFFENDER, "x.py") == []
        ), (
            "a check that never records .pop()/.clear()/.update()/."
            "setdefault() must miss this offender"
        )


class TestFileDiscoveryIsExhaustive:
    """DG-477 review, MEDIUM #3: recursive, and provably so -- skipping a
    file by name must be detectable, not just theoretically possible."""

    def test_discover_test_files_is_recursive(self, tmp_path: Path) -> None:
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "test_nested.py").write_text("", encoding="utf-8")
        found = discover_test_files(tmp_path)
        assert any(p.parent != tmp_path for p in found), (
            "discover_test_files must find .py files in subdirectories, not "
            "just the top level"
        )

    def test_count_matches_an_independent_directory_walk(self) -> None:
        assert len(
            discover_test_files(TESTS_DIR)
        ) == _independent_recursive_py_file_count(TESTS_DIR)

    def test_skipping_a_file_by_name_breaks_the_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A REAL mutation of the production `discover_test_files`, applied
        via monkeypatch to the actual symbol `find_all_violations` calls --
        not a hand-copied reimplementation sitting beside it (the gap the
        reviewer named directly)."""
        module = sys.modules[__name__]
        real_discover = module.discover_test_files

        def _skips_one_file(root: Path) -> list[Path]:
            return [p for p in real_discover(root) if p.name != "test_install_prune.py"]

        monkeypatch.setattr(module, "discover_test_files", _skips_one_file)

        assert len(
            module.discover_test_files(TESTS_DIR)
        ) != _independent_recursive_py_file_count(TESTS_DIR), (
            "skipping one file by name must disagree with the independent walk"
        )

    def test_skipping_a_file_hides_an_offender_injected_into_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same mutation, shown to actually hide a real offender -- the
        exact scenario named in review: "skip test_install_prune.py in the
        loop while an offender is injected there."."""
        (tmp_path / "test_a_safe_file.py").write_text(
            "import subprocess\nsubprocess.run(['git', 'status'])\n", encoding="utf-8"
        )
        (tmp_path / "test_install_prune.py").write_text(
            "import subprocess\nsubprocess.run(['python'], env={'PATH': '/usr/bin'})\n",
            encoding="utf-8",
        )
        module = sys.modules[__name__]

        assert module.find_all_violations(tmp_path) != [], (
            "unmutated, the injected offender in test_install_prune.py must be caught"
        )

        real_discover = module.discover_test_files

        def _skips_prune(root: Path) -> list[Path]:
            return [p for p in real_discover(root) if p.name != "test_install_prune.py"]

        monkeypatch.setattr(module, "discover_test_files", _skips_prune)

        assert module.find_all_violations(tmp_path) == [], (
            "the mutated discovery, which skips test_install_prune.py by "
            "name, must miss the offender injected into exactly that file"
        )


class TestOtherSubprocessShapesAreRecognised:
    """DG-477 review, MEDIUM #4 (best effort): aliasing, os/asyncio
    equivalents, and what this check cannot determine at all."""

    def test_from_import_run_is_still_checked(self) -> None:
        source = "from subprocess import run\ndef test_x():\n    run(['python'], env={'PATH': '/usr/bin'})\n"
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []

    def test_aliased_subprocess_module_is_still_checked(self) -> None:
        source = (
            "import subprocess as sp\n"
            "def test_x():\n"
            "    sp.run(['python'], env={'PATH': '/usr/bin'})\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []

    def test_os_system_is_never_flagged(self) -> None:
        """`os.system` takes no `env=` parameter at all -- it always
        inherits the parent process environment, so there is nothing to
        drop and nothing to check."""
        source = "import os\ndef test_x():\n    os.system('echo hi')\n"
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") == []

    def test_os_popen_is_never_flagged(self) -> None:
        source = "import os\ndef test_x():\n    os.popen('echo hi')\n"
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") == []

    def test_os_spawnve_with_a_hand_built_env_is_flagged(self) -> None:
        source = (
            "import os\n"
            "def test_x():\n"
            "    os.spawnve(os.P_WAIT, '/bin/true', ['true'], {'PATH': '/usr/bin'})\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []

    def test_asyncio_create_subprocess_exec_with_a_hand_built_env_is_flagged(
        self,
    ) -> None:
        source = (
            "import asyncio\n"
            "async def test_x():\n"
            "    await asyncio.create_subprocess_exec('true', env={'PATH': '/usr/bin'})\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []

    def test_env_hidden_in_forwarded_kwargs_is_flagged_as_unprovable(self) -> None:
        source = (
            "import subprocess\n"
            "def test_x(extra_kwargs):\n"
            "    subprocess.run(['python'], **extra_kwargs)\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []

    def test_a_positional_popen_env_argument_is_checked(self) -> None:
        source = (
            "import subprocess\n"
            "def test_x():\n"
            "    subprocess.Popen(\n"
            "        ['true'], -1, None, None, None, None, None, True, True, None,\n"
            "        {'PATH': '/usr/bin'},\n"
            "    )\n"
        )
        assert find_unsandboxed_subprocess_env_calls(source, "x.py") != []


class TestEveryExistingSubprocessCallInTestsPasses:
    """ACCEPTANCE: every subprocess call already in tests/ passes the check."""

    def test_no_test_file_builds_an_unsandboxed_subprocess_env(self) -> None:
        violations = find_all_violations(TESTS_DIR)
        assert violations == [], (
            "found subprocess calls that drop the sandboxed environment:\n"
            + "\n".join(violations)
        )
