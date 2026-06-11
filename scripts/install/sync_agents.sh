#!/bin/bash

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'
RED='\033[0;31m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_AGENTS_DIR="$SCRIPT_DIR/../agents"
GLOBAL_AGENTS_DIR="$HOME/.claude/agents"

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Agents Synchronizer                  ${NC}"
echo -e "${BLUE}=================================================${NC}"

if [ ! -d "$LOCAL_AGENTS_DIR" ]; then
  echo -e "${RED}Error: agents directory not found at $LOCAL_AGENTS_DIR${NC}"
  exit 1
fi

mkdir -p "$GLOBAL_AGENTS_DIR"

echo -e "\nSource: $LOCAL_AGENTS_DIR"
echo -e "Target: $GLOBAL_AGENTS_DIR\n"

NEW_COUNT=0
UPDATED_COUNT=0

_agent_list=$(mktemp)
find "$LOCAL_AGENTS_DIR" -maxdepth 1 -type f -name "*.md" | sort > "$_agent_list"

while IFS= read -r agent_file; do
  agent_name="$(basename "$agent_file" .md)"

  TARGET_FILE="$GLOBAL_AGENTS_DIR/$agent_name.md"

  IS_NEW=false
  [ ! -f "$TARGET_FILE" ] && IS_NEW=true

  rsync -a --checksum "$agent_file" "$TARGET_FILE" 2>/dev/null

  if [ "$IS_NEW" = true ]; then
    echo -e "${GREEN}  [+] Installed:${NC} $agent_name"
    NEW_COUNT=$((NEW_COUNT + 1))
  else
    echo -e "  [*] Updated:   $agent_name"
    UPDATED_COUNT=$((UPDATED_COUNT + 1))
  fi

done < "$_agent_list"
rm -f "$_agent_list"

echo -e "\n${GREEN}Sync complete.${NC}"
echo -e "  ${NEW_COUNT} new  |  ${UPDATED_COUNT} updated"
echo -e "  Agents installed to: $GLOBAL_AGENTS_DIR"
