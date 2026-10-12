# Example — a report, this ticket's own kind of document

The finding, first. Then the evidence a reader needs to believe it, nothing else.

**Finding:** the install script leaves retired skills installed alongside new ones.

| evidence | value |
|---|---|
| installed directories | 45 |
| shipped by this repo | 11 |
| retired, still installed | 34 |

Reproduced with `install_skills.sh --prune` (dry run), no `--prune-apply`.

**Fix:** `--prune --prune-apply` removes only names on the tracked retired list.
