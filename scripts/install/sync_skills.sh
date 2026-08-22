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

# Antigravity reads the same skills from its own tree. Unlike the agents, a
# skill needs no rewriting on the way across -- nothing under skills/ names a
# per-agent index path -- so this is the same directory, installed twice.
ANTIGRAVITY_SKILLS_DIR="${ANTIGRAVITY_SKILLS_DIR:-$HOME/.gemini/config/skills}"
INDEX_FILE="$GLOBAL_SKILLS_DIR/INDEX.md"

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Skills Installer                      ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Project:  $PROJECT_ROOT"
echo -e "  Source:   $LOCAL_SKILLS_DIR"
echo -e "  Target:   $GLOBAL_SKILLS_DIR"

# Written to only if it already exists, and only ever *added to*. That
# directory is shared: alongside ours it holds ~30 Apache-2.0 skills shipped by
# Google and Antigravity's own template, none of which have another copy on
# this machine. Never replace the directory, never sync with --delete, and do
# not create it -- a machine with no Antigravity should not grow a config for
# one because an installer ran.
INSTALL_ANTIGRAVITY=false
if [ -d "$ANTIGRAVITY_SKILLS_DIR" ]; then
  INSTALL_ANTIGRAVITY=true
  echo -e "  Also:     $ANTIGRAVITY_SKILLS_DIR"
else
  echo -e "${YELLOW}  Antigravity not found at $ANTIGRAVITY_SKILLS_DIR — skipping that variant${NC}"
fi
echo ""

if [ ! -d "$LOCAL_SKILLS_DIR" ]; then
  echo -e "${RED}Error: skills/ directory not found at $LOCAL_SKILLS_DIR${NC}"
  echo -e "${RED}Make sure you are running this from inside the drunken-ai-team repo.${NC}"
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

# Skills install by basename, so two of the same name in different groups would
# land on top of each other and only the last would survive. Refuse rather than
# pick one.
_dupes=$(while IFS= read -r f; do basename "$(dirname "$f")"; done < "$_skill_list" | sort | uniq -d)
if [ -n "$_dupes" ]; then
  echo -e "${RED}Error: two skills share a directory name, and they install to the same place:${NC}"
  echo "$_dupes" | sed 's/^/  /'
  rm -f "$_skill_list"
  exit 1
fi

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

  if [ "$INSTALL_ANTIGRAVITY" = true ]; then
    _copy_dir "$skill_dir" "$ANTIGRAVITY_SKILLS_DIR/$skill_name"
  fi

  if [ "$IS_NEW" = true ]; then
    echo -e "${GREEN}  [+] Installed:${NC} $skill_name"
    NEW_COUNT=$((NEW_COUNT + 1))
  else
    echo -e "  [*] Updated:   $skill_name"
    UPDATED_COUNT=$((UPDATED_COUNT + 1))
  fi

  # Every extraction below is optional, and every one of them is a grep that
  # can legitimately find nothing. Under `set -euo pipefail` an unmatched grep
  # returns 1, pipefail propagates it, and the assignment kills the whole run.
  #
  # That is not hypothetical: when skills gained YAML frontmatter the
  # `Trigger/Keywords:` line went away, this script began exiting 1 on the
  # second skill, and it printed a green "Updated" for the first one on its way
  # out. 29 of 30 skills sat stale for weeks because the failure looked like a
  # short success. Hence `|| true` on each, deliberately.
  TRIGGER=$(grep -m1 "Trigger/Keywords:" "$skill_file" 2>/dev/null \
    | sed 's/.*Trigger\/Keywords:\*\* //' \
    | grep -oE '/[a-zA-Z][a-zA-Z-]+' \
    | head -1 || true)
  if [ -z "$TRIGGER" ]; then
    TRIGGER=$(grep -E "Trigger on /[a-zA-Z]" "$skill_file" 2>/dev/null \
      | grep -oE '/[a-zA-Z][a-zA-Z-]+' \
      | head -1 || true)
  fi

  # Prefer the frontmatter description -- it is what Claude reads to decide
  # whether a skill is relevant. Fall back to the body line for older formats.
  DESC=$(awk '/^description: >/{f=1; next} f && /^  /{sub(/^  /,""); printf "%s ", $0; next} f{exit}' "$skill_file" \
    | cut -c1-160 || true)
  if [ -z "$DESC" ]; then
    DESC=$(grep -m1 "\*\*Description:\*\*" "$skill_file" 2>/dev/null \
      | sed 's/.*\*\*Description:\*\* //' \
      | cut -c1-160 || true)
  fi

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

# Anything installed that this repo does not produce. Reported, never deleted:
# removing is the operator's call, and a stale skill still being offered to
# every session is worth knowing about either way.
#
# skills/.external lists third-party skills that legitimately have no source
# here, so they are not named every run.
EXTERNAL_FILE="$LOCAL_SKILLS_DIR/.external"
_installed=$(find "$GLOBAL_SKILLS_DIR" -mindepth 2 -maxdepth 2 -name "SKILL.md" \
  -exec dirname {} \; | xargs -n1 basename 2>/dev/null | sort -u)
_ours=$(while IFS= read -r f; do basename "$(dirname "$f")"; done \
  < <(find "$LOCAL_SKILLS_DIR" -type f -name "SKILL.md") | sort -u)
_external=""
[ -f "$EXTERNAL_FILE" ] && _external=$(grep -vE '^\s*(#|$)' "$EXTERNAL_FILE" | sort -u)

_orphans=$(comm -23 <(echo "$_installed") <(printf '%s\n%s\n' "$_ours" "$_external" | sort -u))
if [ -n "$_orphans" ]; then
  echo ""
  echo -e "${YELLOW}Installed but not produced here:${NC}"
  echo "$_orphans" | sed 's|^|  ~/.claude/skills/|'
  echo -e "  Left in place. Add to skills/.external if intended, or remove them yourself."
fi

# Group directories from an older sync that copied the tree instead of
# flattening it. This script installs by basename and can never create one, so
# anything shaped like a group is a leftover holding a frozen old copy.
_groups=$(find "$GLOBAL_SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d \
  '!' -exec test -e "{}/SKILL.md" ';' -print | xargs -n1 basename 2>/dev/null | sort)
if [ -n "$_groups" ]; then
  echo ""
  echo -e "${YELLOW}Leftover group directories from an older sync:${NC}"
  echo "$_groups" | sed 's|^|  ~/.claude/skills/|'
  echo -e "  They hold stale duplicates of skills that now live at the top level."
fi
