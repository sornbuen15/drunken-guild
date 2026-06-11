#!/bin/bash
# Deploy agents from this repo to ~/.claude/agents/
# Works from any directory and any clone location.
# Usage: bash scripts/install/sync_agents.sh

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_AGENTS_DIR="$PROJECT_ROOT/agents"
GLOBAL_AGENTS_DIR="$HOME/.claude/agents"

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Agents Installer                      ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Project:  $PROJECT_ROOT"
echo -e "  Source:   $LOCAL_AGENTS_DIR"
echo -e "  Target:   $GLOBAL_AGENTS_DIR"
echo ""

if [ ! -d "$LOCAL_AGENTS_DIR" ]; then
  echo -e "${RED}Error: agents/ directory not found at $LOCAL_AGENTS_DIR${NC}"
  echo -e "${RED}Make sure you are running this from inside the ai-team-toolkit repo.${NC}"
  exit 1
fi

mkdir -p "$GLOBAL_AGENTS_DIR"

# Prefer rsync; fall back to cp if not available.
if command -v rsync >/dev/null 2>&1; then
  _copy_file() { rsync -a --checksum "$1" "$2" 2>/dev/null; }
else
  echo -e "${YELLOW}  rsync not found — using cp (all files will be copied)${NC}"
  _copy_file() { cp "$1" "$2"; }
fi

NEW_COUNT=0
UPDATED_COUNT=0

_agent_list=$(mktemp)
find "$LOCAL_AGENTS_DIR" -maxdepth 1 -type f -name "*.md" | sort > "$_agent_list"

while IFS= read -r agent_file; do
  agent_name="$(basename "$agent_file" .md)"
  TARGET_FILE="$GLOBAL_AGENTS_DIR/$agent_name.md"

  IS_NEW=false
  [ ! -f "$TARGET_FILE" ] && IS_NEW=true

  _copy_file "$agent_file" "$TARGET_FILE"

  if [ "$IS_NEW" = true ]; then
    echo -e "${GREEN}  [+] Installed:${NC} $agent_name"
    NEW_COUNT=$((NEW_COUNT + 1))
  else
    echo -e "  [*] Updated:   $agent_name"
    UPDATED_COUNT=$((UPDATED_COUNT + 1))
  fi

done < "$_agent_list"
rm -f "$_agent_list"

echo ""
echo -e "${GREEN}Done.${NC} $NEW_COUNT new  |  $UPDATED_COUNT updated"
echo -e "  Agents: $GLOBAL_AGENTS_DIR"
