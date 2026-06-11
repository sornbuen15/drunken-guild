#!/bin/bash

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Resolve paths relative to the script's location — works from anywhere
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_SKILLS_DIR="$SCRIPT_DIR/../skills"
GLOBAL_SKILLS_DIR="$HOME/.claude/skills"
INDEX_FILE="$GLOBAL_SKILLS_DIR/INDEX.md"

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Agentic Skills Synchronizer          ${NC}"
echo -e "${BLUE}=================================================${NC}"

if [ ! -d "$LOCAL_SKILLS_DIR" ]; then
  echo -e "${RED}Error: skills directory not found at $LOCAL_SKILLS_DIR${NC}"
  exit 1
fi

mkdir -p "$GLOBAL_SKILLS_DIR"

echo -e "\nSource: $LOCAL_SKILLS_DIR"
echo -e "Target: $GLOBAL_SKILLS_DIR\n"

NEW_COUNT=0
UPDATED_COUNT=0

_skill_list=$(mktemp)
find "$LOCAL_SKILLS_DIR" -type f -name "SKILL.md" | sort > "$_skill_list"

# Build INDEX.md in a temp file — replaced atomically at the end
TEMP_INDEX=$(mktemp)
cat > "$TEMP_INDEX" << 'HEADER'
# Skill Index

Map task keywords to their absolute skill file paths. Load ONLY the relevant skill before executing.

HEADER

# Use sort for deterministic INDEX order; paths have no spaces so newline split is safe
while IFS= read -r skill_file; do
  skill_dir="$(dirname "$skill_file")"
  skill_name="$(basename "$skill_dir")"

  [ "$skill_name" = "skills" ] && continue

  TARGET_DIR="$GLOBAL_SKILLS_DIR/$skill_name"

  IS_NEW=false
  [ ! -d "$TARGET_DIR" ] && IS_NEW=true

  # --checksum syncs based on file content, not timestamps
  # Removed -u (skip newer on destination) to ensure project is always source of truth
  rsync -a --checksum "$skill_dir/" "$TARGET_DIR/" 2>/dev/null

  if [ "$IS_NEW" = true ]; then
    echo -e "${GREEN}  [+] Installed:${NC} $skill_name"
    NEW_COUNT=$((NEW_COUNT + 1))
  else
    echo -e "  [*] Updated:   $skill_name"
    UPDATED_COUNT=$((UPDATED_COUNT + 1))
  fi

  # Extract the first /command from Trigger/Keywords line
  TRIGGER=$(grep -m1 "Trigger/Keywords:" "$skill_file" \
    | sed 's/.*Trigger\/Keywords:\*\* //' \
    | grep -oE '/[a-zA-Z][a-zA-Z-]+' \
    | head -1)

  # Extract the Description line
  DESC=$(grep -m1 "\*\*Description:\*\*" "$skill_file" \
    | sed 's/.*\*\*Description:\*\* //' \
    | cut -c1-80)

  if [ -n "$TRIGGER" ]; then
    echo "- \`${skill_name}\` (\`${TRIGGER}\`) — ${DESC}" >> "$TEMP_INDEX"
  else
    echo "- \`${skill_name}\` — ${DESC}" >> "$TEMP_INDEX"
  fi
  echo "  Path: \$HOME/.claude/skills/${skill_name}/SKILL.md" >> "$TEMP_INDEX"
  echo "" >> "$TEMP_INDEX"

done < "$_skill_list"
rm -f "$_skill_list"

# Atomically replace the global INDEX — single write, no partial state
mv "$TEMP_INDEX" "$INDEX_FILE"

# Keep a local copy so CLAUDE.md skill_routing can read it without a sync
cp "$INDEX_FILE" "$LOCAL_SKILLS_DIR/INDEX.md"

echo -e "\n${GREEN}Sync complete.${NC}"
echo -e "  ${NEW_COUNT} new  |  ${UPDATED_COUNT} updated"
echo -e "  INDEX.md regenerated: $INDEX_FILE"
echo -e "  INDEX.md mirrored:    $LOCAL_SKILLS_DIR/INDEX.md"
