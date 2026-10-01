<!--
DG-393 round 3 fixture only. A real file, deliberately sitting outside every
location `tests/test_instruction_file_pointers.py::_ALLOWED_PREFIXES` accepts,
so the test proving `templates/../tests/fixtures/stray/CLAUDE.md` does not
resolve has something real at the far end of the traversal to prove it
against -- a token resolving only because nothing exists at the target would
not have caught the bug `_resolves()` had before round 3.

`tests/fixtures/` is not in `_scan_files()`, so this file is never itself
scanned as a live instruction-file reference. It is not an adapter for
anything and no agent should read it.
-->
