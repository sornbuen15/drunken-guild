#!/bin/bash
# Deploy skills from this repo to ~/.claude/skills/
# Works from any directory and any clone location.
# Usage: bash scripts/install/install_skills.sh

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

# --index-only rebuilds the repository's INDEX.md and writes nothing else --
# not to ~/.claude, not to any target. It exists because
# the index is generated but also committed, so it goes stale on any change to
# a skill's name or description, and the only way to refresh it used to be to
# perform an install. An agent that must not install had no way to keep a
# tracked file correct, and hand-editing it drifts from the generator's output
# by a byte or two per line, which is worse than stale.
INDEX_ONLY=false
case "${1:-}" in
  "") ;;
  --index-only) INDEX_ONLY=true ;;
  *)
    # DG-302: an unrecognized flag used to fall through here and run a real
    # install -- `--help`, typed to check usage, did exactly that. Anything
    # this script does not know must refuse, not proceed.
    echo -e "${RED}Unrecognized argument: ${1}${NC}" >&2
    echo "Usage: $0 [--index-only]" >&2
    exit 1
    ;;
esac
INDEX_FILE="$GLOBAL_SKILLS_DIR/INDEX.md"

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Skills Installer                      ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Project:  $PROJECT_ROOT"
echo -e "  Source:   $LOCAL_SKILLS_DIR"
echo -e "  Target:   $GLOBAL_SKILLS_DIR"

if [ "$INDEX_ONLY" = true ]; then
  echo -e "${YELLOW}  --index-only: rebuilding skills/INDEX.md, installing nothing${NC}"
fi
echo ""

if [ ! -d "$LOCAL_SKILLS_DIR" ]; then
  echo -e "${RED}Error: skills/ directory not found at $LOCAL_SKILLS_DIR${NC}"
  echo -e "${RED}Make sure you are running this from inside the drunken-guild repo.${NC}"
  exit 1
fi

if [ "$INDEX_ONLY" = false ]; then
  mkdir -p "$GLOBAL_SKILLS_DIR"
fi

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

  if [ "$INDEX_ONLY" = false ]; then
    _copy_dir "$skill_dir" "$TARGET_DIR"
  fi

  if [ "$INDEX_ONLY" = true ]; then
    :
  elif [ "$IS_NEW" = true ]; then
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
  # The slash command must be the one that *follows* "Trigger on". Matching the
  # first `/word` on the line instead published `scrutinize` as `/more`, taken
  # from the phrase "a simpler/more elegant approach" earlier in its own
  # description. An index that names the wrong command is worse than one that
  # names none: the agent types it and gets nothing.
  TRIGGER=$(grep -m1 "Trigger/Keywords:" "$skill_file" 2>/dev/null \
    | sed 's/.*Trigger\/Keywords:\*\* //' \
    | grep -oE '/[a-zA-Z][a-zA-Z-]+' \
    | head -1 || true)
  if [ -z "$TRIGGER" ]; then
    TRIGGER=$(grep -oE 'Trigger on `?/[a-zA-Z][a-zA-Z-]*' "$skill_file" 2>/dev/null \
      | head -1 \
      | grep -oE '/[a-zA-Z][a-zA-Z-]*' || true)
  fi

  # The description is what an agent reads to decide whether a skill is
  # relevant at all, and CLAUDE.md routes every lookup through this index -- so
  # a blank one makes the skill effectively invisible. The previous extractor
  # understood only the folded `description: >` form, and nine of the skills
  # here write it on one line, so nine were published with no description.
  #
  # Both frontmatter forms are handled below, quoted or not, with the old
  # `**Description:**` body line kept as a fallback for anything older.
  DESC=$(awk '
    NR == 1 && $0 == "---" { fm = 1; next }
    fm && $0 == "---" { exit }
    fm && /^description:[[:space:]]*[>|]/ { block = 1; next }
    block && /^[[:space:]]+[^[:space:]]/ { sub(/^[[:space:]]+/, ""); printf "%s ", $0; next }
    block { exit }
    fm && /^description:[[:space:]]*[^[:space:]]/ {
      sub(/^description:[[:space:]]*/, "")
      sub(/^"/, ""); sub(/"$/, "")
      printf "%s", $0
      exit
    }
  ' "$skill_file" | python3 "$SCRIPT_DIR/_truncate.py" 160 || true)
  if [ -z "$DESC" ]; then
    DESC=$(grep -m1 "\*\*Description:\*\*" "$skill_file" 2>/dev/null \
      | sed 's/.*\*\*Description:\*\* //' \
      | python3 "$SCRIPT_DIR/_truncate.py" 160 || true)
  fi
  if [ -z "$DESC" ]; then
    echo -e "${YELLOW}  [!] $skill_name has no description — it will be invisible in the index.${NC}"
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


# The index is generated *and* committed, so what this writes has to be exactly
# what survives a commit. Every entry appends a blank line, which leaves the
# file ending in one -- and `end-of-file-fixer` strips it, so the generator and
# the commit hook disagreed about the same file forever. DG-280.
_trimmed=$(mktemp)
printf '%s\n' "$(cat "$TEMP_INDEX")" > "$_trimmed"
mv "$_trimmed" "$TEMP_INDEX"
if [ "$INDEX_ONLY" = true ]; then
  mv "$TEMP_INDEX" "$LOCAL_SKILLS_DIR/INDEX.md"
  echo ""
  echo -e "${GREEN}Done.${NC} Rebuilt $LOCAL_SKILLS_DIR/INDEX.md. Nothing was installed."
  exit 0
fi

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
