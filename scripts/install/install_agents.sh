#!/bin/bash
# Deploy agents from this repo to ~/.claude/agents/
# Works from any directory and any clone location.
# Usage: bash scripts/install/install_agents.sh

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

# Antigravity reads the same roster from its own tree, in its own shape: one
# directory per agent holding a SKILL.md, rather than a flat <name>.md.
#
# Those files used to be committed as .agents/skills/<name>/SKILL.md and kept in
# step by hand. Twelve of the fifteen differed from their source only in the two
# lines rewritten below; three had silently drifted, and principal-engineer's
# copy had fallen to 78 lines against 311 while still describing an orchestrator
# retired two tickets earlier. Generating them removes the copy that can drift.
#
# Both are overridable: a machine that keeps Antigravity elsewhere, or that has
# moved to a different Gemini model, sets the variable rather than editing this.
ANTIGRAVITY_AGENTS_DIR="${ANTIGRAVITY_AGENTS_DIR:-$HOME/.gemini/config/skills}"

# The model is a *tier* mapping, not one constant. The hand-maintained twins
# encoded it consistently across all fifteen and nobody had written it down:
# the four agents that reason rather than execute ran on the larger model on
# both sides, and the ten executors on the faster one. Flattening that to a
# single value would have quietly demoted principal-engineer and the three
# specialists, which is the kind of change that shows up as worse output weeks
# later and is never traced back to an install script.
ANTIGRAVITY_MODEL_LARGE="${ANTIGRAVITY_MODEL_LARGE:-gemini-2.5-pro}"
ANTIGRAVITY_MODEL_FAST="${ANTIGRAVITY_MODEL_FAST:-gemini-2.5-flash}"

# --index-only rebuilds the repository's INDEX.md and writes nothing else --
# not to ~/.claude, not to Antigravity, not to any target. It exists because
# the index is generated but also committed, so it goes stale on any change to
# a skill's name or description, and the only way to refresh it used to be to
# perform an install. An agent that must not install had no way to keep a
# tracked file correct, and hand-editing it drifts from the generator's output
# by a byte or two per line, which is worse than stale.
INDEX_ONLY=false
if [ "${1:-}" = "--index-only" ]; then
  INDEX_ONLY=true
fi

# An unrecognised tier is reported, never silently mapped. A new Claude model
# id landing here should make somebody read this function, not inherit whatever
# the fallback happens to be.
_antigravity_model() {
  case "$1" in
    *opus*)   printf '%s' "$ANTIGRAVITY_MODEL_LARGE" ;;
    *sonnet*) printf '%s' "$ANTIGRAVITY_MODEL_FAST" ;;
    *)
      echo -e "${YELLOW}  [!] $2: unmapped model '$1' — using $ANTIGRAVITY_MODEL_FAST.${NC}" >&2
      echo -e "${YELLOW}      Add its tier to _antigravity_model in this script.${NC}" >&2
      printf '%s' "$ANTIGRAVITY_MODEL_FAST"
      ;;
  esac
}

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Agents Installer                      ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Project:  $PROJECT_ROOT"
echo -e "  Source:   $LOCAL_AGENTS_DIR"
echo -e "  Target:   $GLOBAL_AGENTS_DIR"

# Written to only if it already exists. Creating it would mean conjuring an
# Antigravity install on a machine that has none, and the directory is not ours
# -- on the machine this was written for it holds 30 Apache-2.0 skills shipped
# by Google plus Antigravity's own template. We add files beside them and never
# remove or replace the directory.
INSTALL_ANTIGRAVITY=false
if [ "$INDEX_ONLY" = true ]; then
  echo -e "${YELLOW}  --index-only: rebuilding agents/INDEX.md, installing nothing${NC}"
elif [ -d "$ANTIGRAVITY_AGENTS_DIR" ]; then
  INSTALL_ANTIGRAVITY=true
  echo -e "  Also:     $ANTIGRAVITY_AGENTS_DIR ($ANTIGRAVITY_MODEL_LARGE / $ANTIGRAVITY_MODEL_FAST)"
else
  echo -e "${YELLOW}  Antigravity not found at $ANTIGRAVITY_AGENTS_DIR — skipping that variant${NC}"
fi
echo ""

if [ ! -d "$LOCAL_AGENTS_DIR" ]; then
  echo -e "${RED}Error: agents/ directory not found at $LOCAL_AGENTS_DIR${NC}"
  echo -e "${RED}Make sure you are running this from inside the drunken-guild repo.${NC}"
  exit 1
fi

if [ "$INDEX_ONLY" = false ]; then
  mkdir -p "$GLOBAL_AGENTS_DIR"
fi

# Prefer rsync; fall back to cp if not available.
if command -v rsync >/dev/null 2>&1; then
  _copy_file() { rsync -a --checksum "$1" "$2" 2>/dev/null; }
else
  echo -e "${YELLOW}  rsync not found — using cp (all files will be copied)${NC}"
  _copy_file() { cp "$1" "$2"; }
fi

NEW_COUNT=0
UPDATED_COUNT=0
# Counted separately, because the two targets are genuinely different places and
# a single pair of counters can only describe one of them. The run that first
# generated all fifteen Antigravity agents reported "0 new | 15 updated" -- true
# of ~/.claude, and completely wrong about the fifteen directories it had just
# created. A green line over work that did not happen is the failure this
# repository exists to prevent, and reporting *more* work than happened is the
# same defect wearing the other sign.
AG_NEW_COUNT=0
AG_UPDATED_COUNT=0

# INDEX.md is generated below, not an agent. It lives in agents/ so the repo
# carries the same index the install does, which means the discovery glob has
# to exclude it or the next run would install the index as a 14th agent.
_agent_list=$(mktemp)
find "$LOCAL_AGENTS_DIR" -maxdepth 1 -type f -name "*.md" '!' -name "INDEX.md" \
  | sort > "$_agent_list"

# Build INDEX.md in a temp file and replace atomically at the end. CLAUDE.md
# routes all agent discovery through this file, so a run that installs agents
# without refreshing it leaves a live dangling reference.
TEMP_INDEX=$(mktemp)
cat > "$TEMP_INDEX" << 'HEADER'
# Agent Index

Map a task to the agent that owns it. Read this before delegating — do NOT guess agent
names or paths from memory.

Generated by `scripts/install/install_agents.sh`. Do not edit by hand; edit the agent
frontmatter instead.

HEADER

while IFS= read -r agent_file; do
  agent_name="$(basename "$agent_file" .md)"
  TARGET_FILE="$GLOBAL_AGENTS_DIR/$agent_name.md"

  IS_NEW=false
  [ ! -f "$TARGET_FILE" ] && IS_NEW=true

  if [ "$INDEX_ONLY" = false ]; then
    _copy_file "$agent_file" "$TARGET_FILE"
  fi

  if [ "$INDEX_ONLY" = true ]; then
    :
  elif [ "$IS_NEW" = true ]; then
    echo -e "${GREEN}  [+] Installed:${NC} $agent_name"
    NEW_COUNT=$((NEW_COUNT + 1))
  else
    echo -e "  [*] Updated:   $agent_name"
    UPDATED_COUNT=$((UPDATED_COUNT + 1))
  fi

  # The Antigravity variant, generated from the same file rather than stored.
  # Exactly two per-agent differences are legitimate, and both are mechanical:
  # the model it runs on, and where its skill index lives. sed rather than a
  # template so that any other edit to the agent reaches both variants without
  # what the edit was.
  if [ "$INSTALL_ANTIGRAVITY" = true ]; then
    _ag_dir="$ANTIGRAVITY_AGENTS_DIR/$agent_name"
    if [ -f "$_ag_dir/SKILL.md" ]; then
      AG_UPDATED_COUNT=$((AG_UPDATED_COUNT + 1))
    else
      AG_NEW_COUNT=$((AG_NEW_COUNT + 1))
    fi
    mkdir -p "$_ag_dir"
    # `|| true` for the same reason as every other grep in this file.
    _claude_model=$(grep -m1 "^model: " "$agent_file" | sed 's/^model: //' || true)
    _ag_model=$(_antigravity_model "$_claude_model" "$agent_name")
    sed -e "s|^model: .*|model: $_ag_model|" \
        -e "s|~/\.claude/skills/INDEX\.md|~/.gemini/config/skills/INDEX.md|g" \
        "$agent_file" > "$_ag_dir/SKILL.md"
  fi

  # Every extraction here is a grep that can legitimately find nothing, and
  # under `set -euo pipefail` an unmatched grep would kill the whole run --
  # exactly the failure that left 29 of 30 skills stale for two months. Hence
  # `|| true` on each, deliberately.
  DESC=$(grep -m1 "^description: " "$agent_file" 2>/dev/null \
    | sed 's/^description: //' | python3 "$SCRIPT_DIR/_truncate.py" 200 || true)
  MODEL=$(grep -m1 "^model: " "$agent_file" 2>/dev/null | sed 's/^model: //' || true)

  echo "- \`${agent_name}\` (\`${MODEL}\`) — ${DESC}" >> "$TEMP_INDEX"
  echo "  Path: \$HOME/.claude/agents/${agent_name}.md" >> "$TEMP_INDEX"
  echo "" >> "$TEMP_INDEX"

done < "$_agent_list"
rm -f "$_agent_list"


# The index is generated *and* committed, so what this writes has to be exactly
# what survives a commit. Every entry appends a blank line, which leaves the
# file ending in one -- and `end-of-file-fixer` strips it, so the generator and
# the commit hook disagreed about the same file forever. DG-280.
_trimmed=$(mktemp)
printf '%s\n' "$(cat "$TEMP_INDEX")" > "$_trimmed"
mv "$_trimmed" "$TEMP_INDEX"
if [ "$INDEX_ONLY" = true ]; then
  mv "$TEMP_INDEX" "$LOCAL_AGENTS_DIR/INDEX.md"
  echo ""
  echo -e "${GREEN}Done.${NC} Rebuilt $LOCAL_AGENTS_DIR/INDEX.md. Nothing was installed."
  exit 0
fi

INDEX_FILE="$GLOBAL_AGENTS_DIR/INDEX.md"
mv "$TEMP_INDEX" "$INDEX_FILE"
cp "$INDEX_FILE" "$LOCAL_AGENTS_DIR/INDEX.md"

echo ""
echo -e "${GREEN}Done.${NC} $NEW_COUNT new  |  $UPDATED_COUNT updated"
echo -e "  Agents:   $GLOBAL_AGENTS_DIR"
echo -e "  INDEX.md: $INDEX_FILE"
if [ "$INSTALL_ANTIGRAVITY" = true ]; then
  echo -e "  Antigravity: $AG_NEW_COUNT new  |  $AG_UPDATED_COUNT updated"
  echo -e "               $ANTIGRAVITY_AGENTS_DIR/<agent>/SKILL.md"
fi

# Anything installed that this repo does not produce. Reported, never deleted:
# removing is the operator's call, and a stale agent still being offered to
# every session is worth knowing about either way.
_installed=$(find "$GLOBAL_AGENTS_DIR" -maxdepth 1 -type f -name "*.md" \
  '!' -name "INDEX.md" -exec basename {} .md ';' | sort -u)
_ours=$(find "$LOCAL_AGENTS_DIR" -maxdepth 1 -type f -name "*.md" \
  '!' -name "INDEX.md" -exec basename {} .md ';' | sort -u)
_orphans=$(comm -23 <(echo "$_installed") <(echo "$_ours"))
if [ -n "$_orphans" ]; then
  echo ""
  echo -e "${YELLOW}Installed but not produced here:${NC}"
  echo "$_orphans" | sed 's|^|  ~/.claude/agents/|;s|$|.md|'
  echo -e "  Left in place. Add the source to agents/, or remove them yourself."
fi
