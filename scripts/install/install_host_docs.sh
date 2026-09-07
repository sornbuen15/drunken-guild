#!/bin/bash
# Install the global host instruction file — templates/AGENTS.md.
# Usage: bash scripts/install/install_host_docs.sh [--apply] [--target FILE]
#
# Sits beside install_skills.sh and install_agents.sh because it is the same
# kind of step: something authored here, copied into a host's tree, by the
# operator and never by an agent.
#
# It is a SEPARATE script from install_agents.sh on purpose. That one writes
# agents into ~/.gemini/config/skills/ and runs often. This one overwrites the
# operator's global instruction file, which is a different blast radius — and an
# agent install that silently replaced it would be exactly the kind of surprise
# `_not_used/` exists to prevent.
#
# WHY THE GLOBAL FILE NEEDS REPLACING (DG-324):
#   The installed ~/.gemini/config/AGENTS.md still mandates the "Silent Wait
#   Protocol" — write .agents/discord_outbox.json, schedule a wake-up, end your
#   turn. This project's own .agents/AGENTS.md records that protocol as retired
#   and says to use request_boss_approval_async instead. Two files, one global
#   and one per project, giving opposite instructions; the global one is usually
#   read first. templates/AGENTS.md defers to the project file rather than
#   restating any of it, so the pair cannot drift apart again.

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SOURCE="$PROJECT_ROOT/templates/AGENTS.md"
TARGET="${HOST_AGENTS_MD:-$HOME/.gemini/config/AGENTS.md}"
TICKET="manual"
APPLY=false

while [ $# -gt 0 ]; do
  case "$1" in
    --apply)  APPLY=true; shift ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --source) SOURCE="${2:-}"; shift 2 ;;
    --ticket) TICKET="${2:-manual}"; shift 2 ;;
    -h|--help)
      sed -n '2,4p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo -e "${RED}Unknown option: $1${NC}" >&2; exit 2 ;;
  esac
done

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Host documents                               ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Source:  $SOURCE"
echo -e "  Target:  $TARGET"
echo ""

if [ ! -f "$SOURCE" ]; then
  echo -e "${RED}Error: $SOURCE does not exist.${NC}" >&2
  echo "  It is authored in this repository as templates/AGENTS.md (DG-322)." >&2
  exit 1
fi

TARGET_DIR="$(dirname "$TARGET")"
if [ ! -d "$TARGET_DIR" ]; then
  echo -e "${YELLOW}  $TARGET_DIR does not exist — no host is installed here.${NC}"
  echo -e "  Nothing to do."
  exit 0
fi

if [ -f "$TARGET" ]; then
  if cmp -s "$SOURCE" "$TARGET"; then
    echo -e "${GREEN}  Already identical. Nothing to do.${NC}"
    exit 0
  fi
  echo -e "${YELLOW}  Target exists and differs. Diff (target -> source):${NC}"
  echo ""
  diff -u "$TARGET" "$SOURCE" || true
  echo ""
else
  echo -e "  Target does not exist yet; it would be created."
  echo ""
fi

if [ "$APPLY" != true ]; then
  echo -e "${YELLOW}  Dry run — nothing written. Re-run with --apply.${NC}"
  exit 0
fi

# Back up before writing, using the convention already in that tree:
# <name>.pre-<TICKET>.bak, as left there by DG-277. An existing backup is kept —
# the first one holds the state before anything was replaced, and a second run
# must not overwrite it with the already-replaced copy.
if [ -f "$TARGET" ]; then
  BACKUP="$TARGET.pre-$TICKET.bak"
  if [ -e "$BACKUP" ]; then
    echo -e "  Backup   $(basename "$BACKUP") exists already — kept, not overwritten"
  else
    cp -p "$TARGET" "$BACKUP"
    echo -e "  Backup   $(basename "$BACKUP")"
  fi
fi

cp "$SOURCE" "$TARGET"
echo -e "${GREEN}  Written.${NC} $TARGET"
echo ""
echo -e "  This file defers to each project's own AGENTS.md. If a project has"
echo -e "  none, that is the gap to close next — not a reason to restate rules"
echo -e "  here, where they can contradict the project stating them differently."
