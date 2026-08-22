#!/bin/bash
# Kanban board write interface — delegates to the unified kanban.js CLI.
# Usage: see kanban.js create <lane> <NNN> <slug> <file> | move <ID> <lane> | done <ID>
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$SCRIPT_DIR/kanban.js" "$@"
