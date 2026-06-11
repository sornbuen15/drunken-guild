#!/bin/bash
# Kanban board read interface — delegates to the unified kanban.js CLI.
# Usage: see kanban.js next-id | list <lane> | list-all | get <TASK-ID>
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$SCRIPT_DIR/kanban.js" "$@"
