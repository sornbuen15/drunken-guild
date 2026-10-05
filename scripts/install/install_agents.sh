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
LOCAL_SKILLS_DIR="$PROJECT_ROOT/skills"
GLOBAL_SKILLS_DIR="$HOME/.claude/skills"
SOURCES_JSON="$LOCAL_AGENTS_DIR/_sources.json"

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
    # install -- see install_skills.sh for the incident this came from.
    echo -e "${RED}Unrecognized argument: ${1}${NC}" >&2
    echo "Usage: $0 [--index-only]" >&2
    exit 1
    ;;
esac

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   Claude Agents Installer                      ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Project:  $PROJECT_ROOT"
echo -e "  Source:   $LOCAL_AGENTS_DIR"
echo -e "  Target:   $GLOBAL_AGENTS_DIR"

if [ "$INDEX_ONLY" = true ]; then
  echo -e "${YELLOW}  --index-only: rebuilding agents/INDEX.md, installing nothing${NC}"
fi
echo ""

if [ ! -d "$LOCAL_AGENTS_DIR" ]; then
  echo -e "${RED}Error: agents/ directory not found at $LOCAL_AGENTS_DIR${NC}"
  echo -e "${RED}Make sure you are running this from inside the drunken-guild repo.${NC}"
  exit 1
fi

# DG-402, reviewer finding (PR #150, CRITICAL). A broken `python3` on PATH
# can exit 0 and print nothing at all for *any* script -- reproduced with a
# stub standing in for a misbehaving shim. Both the generator below and the
# role-skill gate further down depend on python3 actually running, so this
# probes it up front, once, with an answer that cannot be mistaken for any
# real script's output: anything other than exactly `ok` refuses outright,
# before either depends on it silently.
if [ -f "$SOURCES_JSON" ]; then
  _PY3_PROBE="$(python3 -c 'print("ok")' 2>/dev/null </dev/null || true)"
  if [ "$_PY3_PROBE" != "ok" ]; then
    echo -e "${RED}Error: python3 did not answer as expected (got: '${_PY3_PROBE}').${NC}" >&2
    echo -e "${RED}This script needs a working python3 on PATH to generate agents/*.md${NC}" >&2
    echo -e "${RED}and to verify each role's skill dependency. Check PATH for a broken${NC}" >&2
    echo -e "${RED}shim (a pyenv-win shim caused exactly this once) and re-run.${NC}" >&2
    exit 1
  fi
fi

# DG-402. agents/<role>.md is generated from skills/roles/<role>/SKILL.md +
# agents/_sources.json (model, tools -- Claude-only concepts no portable skill
# frontmatter should carry). One Python script, not re-implemented per
# platform, is what keeps this byte-identical to install_agents.ps1's output
# (DG-280/DG-378/DG-380's lesson applied to a new generated-and-committed
# artefact). This writes only inside the repository's own agents/ -- never
# under $GLOBAL_AGENTS_DIR -- so it runs in both --index-only and a real
# install.
if [ -f "$SOURCES_JSON" ]; then
  if ! python3 "$SCRIPT_DIR/_generate_agents.py" \
      "$LOCAL_AGENTS_DIR" "$LOCAL_SKILLS_DIR" "$SOURCES_JSON"; then
    echo -e "${RED}Error: regenerating agents/*.md from skills/roles/ failed.${NC}" >&2
    exit 1
  fi
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
MISSING_ROLE_SKILL=false

# DG-402, HIGH review finding. Claude Code skips a subagent's `skills:`
# preload silently when the named skill is not installed -- "If a listed
# skill is missing or disabled ... Claude Code skips it and logs a warning
# to the debug log" (https://code.claude.com/docs/en/subagents) -- so a
# worker/reviewer/manager installed before its role skill would run with
# effectively no role prompt and no visible error at all. Refuse per role
# adapter instead, naming the missing skill and the command to run first.
#
# A real script file (`_role_skill.py`), not an inline multi-line `python3
# -c '...'`: the inline form broke under a `pyenv-win` shim on at least one
# machine, in a way that silently disabled this whole safety check (see that
# script's own docstring).
#
# `</dev/null` is load-bearing, not tidiness: this function is called from
# inside `while read -r agent_file; do ... ; done < "$_agent_list"`, so fd 0
# is the loop's own input file. Without the redirect, python3 inherits that
# same fd, and on at least one observed run it consumed the remaining lines
# of `$_agent_list` out from under the `read` -- the loop silently processed
# only the first agent file and exited clean, which is a worse failure than
# a loud one: fewer than three role adapters installed, zero complaint.
#
# CRITICAL review finding (PR #150): the previous version of this function
# ended in `|| true` and the caller refused only on a *non-empty* result,
# so a helper that failed outright, or printed nothing at all, read as "no
# dependency" and installed anyway -- fail *open*, the opposite of what a
# safety gate must do. There is deliberately no `|| true` here any more:
# this function's own exit status is the caller's signal, and the caller
# (below) treats a non-zero exit **and** an empty result as refusals in
# their own right, never as "no dependency".
_role_skill() {
  if [ ! -f "$SOURCES_JSON" ]; then
    printf '%s\n' "-"
    return 0
  fi
  python3 "$SCRIPT_DIR/_role_skill.py" "$SOURCES_JSON" "$1" </dev/null
}

# INDEX.md is generated below, not an agent. It lives in agents/ so the repo
# carries the same index the install does, which means the discovery glob has
# to exclude it or the next run would install the index as a 14th agent.
_agent_list=$(mktemp)
find "$LOCAL_AGENTS_DIR" -maxdepth 1 -type f -name "*.md" '!' -name "INDEX.md" \
  | sort > "$_agent_list"

# Build INDEX.md in a temp file and replace atomically at the end. AGENTS.md
# routes all agent discovery through this file, so a run that installs agents
# without refreshing it leaves a live dangling reference.
TEMP_INDEX=$(mktemp)
cat > "$TEMP_INDEX" << 'HEADER'
# Agent Index

Map a task to the agent that owns it. Read this before delegating — do NOT guess agent
names or paths from memory.

Generated by `scripts/install/install_agents` (.sh and .ps1 write identical bytes). Do not
edit by hand; edit the agent frontmatter instead.

HEADER

while IFS= read -r agent_file; do
  agent_name="$(basename "$agent_file" .md)"
  TARGET_FILE="$GLOBAL_AGENTS_DIR/$agent_name.md"

  if [ "$INDEX_ONLY" = false ]; then
    # `if ROLE_SKILL=$(...); then ... else ...; fi` is the form that keeps
    # `set -e` from killing the whole script on a non-zero exit here, and
    # is also what makes `$?` inside the `else` branch reliably reflect
    # `_role_skill`'s own exit status (not some other command's) --
    # written out instead of `|| true`'d away, which is the exact pattern
    # that failed open before.
    if ROLE_SKILL="$(_role_skill "$agent_name")"; then
      :
    else
      _rc=$?
      echo -e "${RED}  [x] Refusing: could not verify ${agent_name}'s role-skill dependency -- python3 $SCRIPT_DIR/_role_skill.py exited ${_rc}.${NC}" >&2
      echo -e "${RED}      Check python3 on PATH for a broken shim and re-run install_agents.sh.${NC}" >&2
      MISSING_ROLE_SKILL=true
      continue
    fi
    if [ -z "$ROLE_SKILL" ]; then
      echo -e "${RED}  [x] Refusing: the check for ${agent_name}'s role-skill dependency printed nothing (expected a skill name or '-').${NC}" >&2
      echo -e "${RED}      Treating silence as unverifiable, not as \"no dependency\" -- check python3 on PATH and re-run.${NC}" >&2
      MISSING_ROLE_SKILL=true
      continue
    fi
    if [ "$ROLE_SKILL" != "-" ] && [ ! -f "$GLOBAL_SKILLS_DIR/$ROLE_SKILL/SKILL.md" ]; then
      echo -e "${RED}  [x] Refusing: ${agent_name} needs the '${ROLE_SKILL}' skill, not installed at $GLOBAL_SKILLS_DIR/$ROLE_SKILL/SKILL.md${NC}" >&2
      echo -e "${RED}      Run install_skills.sh first, then re-run install_agents.sh.${NC}" >&2
      MISSING_ROLE_SKILL=true
      continue
    fi
  fi

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

if [ "$MISSING_ROLE_SKILL" = true ]; then
  echo "" >&2
  echo -e "${RED}Install refused for one or more role adapters -- see above.${NC}" >&2
  exit 1
fi


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
