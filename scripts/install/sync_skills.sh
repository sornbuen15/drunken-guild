#!/bin/bash
# Deploy skills from this repo to ~/.claude/skills/
# Works from any directory and any clone location.
# Usage: bash scripts/install/sync_skills.sh

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Resolve the project root from this script's location — works regardless of
# where the repo is cloned or which directory the user runs this from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOCAL_SKILLS_DIR="$PROJECT_ROOT/skills"
GLOBAL_SKILLS_DIR="$HOME/.claude/skills"
INDEX_FILE="$GLOBAL_SKILLS_DIR/INDEX.md"

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Skills Installer                      ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Project:  $PROJECT_ROOT"
echo -e "  Source:   $LOCAL_SKILLS_DIR"
echo -e "  Target:   $GLOBAL_SKILLS_DIR"
echo ""

if [ ! -d "$LOCAL_SKILLS_DIR" ]; then
  echo -e "${RED}Error: skills/ directory not found at $LOCAL_SKILLS_DIR${NC}"
  echo -e "${RED}Make sure you are running this from inside the ai-team-toolkit repo.${NC}"
  exit 1
fi

mkdir -p "$GLOBAL_SKILLS_DIR"

# Prefer rsync (checksum-based, skips unchanged files).
# Fall back to cp if rsync is not available.
if command -v rsync >/dev/null 2>&1; then
  _copy_dir() { rsync -a --checksum "$1/" "$2/" 2>/dev/null; }
else
  echo -e "${YELLOW}  rsync not found — using cp (all files will be copied)${NC}"
  _copy_dir() {
    mkdir -p "$2"
    cp -r "$1/." "$2/"
  }
fi

NEW_COUNT=0
UPDATED_COUNT=0

_skill_list=$(mktemp)
find "$LOCAL_SKILLS_DIR" -type f -name "SKILL.md" | sort > "$_skill_list"

# Build INDEX.md in a temp file and replace atomically at the end.
TEMP_INDEX=$(mktemp)
cat > "$TEMP_INDEX" << 'HEADER'
# Skill Index

Map task keywords to their absolute skill file paths. Load ONLY the relevant skill before executing.

HEADER

while IFS= read -r skill_file; do
  skill_dir="$(dirname "$skill_file")"
  skill_name="$(basename "$skill_dir")"

  [ "$skill_name" = "skills" ] && continue

  TARGET_DIR="$GLOBAL_SKILLS_DIR/$skill_name"

  IS_NEW=false
  [ ! -d "$TARGET_DIR" ] && IS_NEW=true

  _copy_dir "$skill_dir" "$TARGET_DIR"

  if [ "$IS_NEW" = true ]; then
    echo -e "${GREEN}  [+] Installed:${NC} $skill_name"
    NEW_COUNT=$((NEW_COUNT + 1))
  else
    echo -e "  [*] Updated:   $skill_name"
    UPDATED_COUNT=$((UPDATED_COUNT + 1))
  fi

  # Extract trigger from YAML description field (e.g. "Trigger on /foo") or
  # fall back to legacy Trigger/Keywords line for older skill formats.
  TRIGGER=$(grep -m1 "Trigger/Keywords:" "$skill_file" \
    | sed 's/.*Trigger\/Keywords:\*\* //' \
    | grep -oE '/[a-zA-Z][a-zA-Z-]+' \
    | head -1)
  if [ -z "$TRIGGER" ]; then
    TRIGGER=$(grep -E "Trigger on /[a-zA-Z]" "$skill_file" \
      | grep -oE '/[a-zA-Z][a-zA-Z-]+' \
      | head -1)
  fi

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

mv "$TEMP_INDEX" "$INDEX_FILE"
cp "$INDEX_FILE" "$LOCAL_SKILLS_DIR/INDEX.md"

echo ""
echo -e "${GREEN}Done.${NC} $NEW_COUNT new  |  $UPDATED_COUNT updated"
echo -e "  INDEX.md: $INDEX_FILE"
