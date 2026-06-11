# Kanban board write interface — delegates to the unified kanban.js CLI.
# Usage: see kanban.js create <lane> <NNN> <slug> <file> | move <ID> <lane> | done <ID>
# Requirements: Node.js 18+
node "$PSScriptRoot/kanban.js" @args
