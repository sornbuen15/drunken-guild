#!/bin/bash
# Print the MCP server configuration for a project, or write it to a file.
# Usage: bash scripts/install/install_mcp.sh <project-id> [--host|--repo] [--out FILE]
#
# This is deliberately a THIN WRAPPER over `drunken-config`, not a generator.
#
# The plan for this phase called for a third install script that emits a
# `.mcp.json` snippet with an absolute path. `drunken-config` already does
# that, and does more of it: it reads the project registry rather than guessing,
# it knows the difference between a repository's own config and a host
# application's, and with `--out` on `--kind host` it *merges* so the host's
# other servers survive. Writing a second emitter here would have produced two
# things that answer the same question and can disagree -- which is the failure
# this whole repository exists to cure.
#
# So this script contributes the one thing that was genuinely missing: an entry
# point that sits beside install_skills.sh and install_agents.sh, so the three
# layers are installed the same way and nobody has to know that the third one
# happens to be a Python console script.

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PROJECT=""
KIND="host"
OUT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --host) KIND="host"; shift ;;
    --repo) KIND="mcp"; shift ;;
    --out)  OUT="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,4p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*) echo -e "${RED}Unknown option: $1${NC}" >&2; exit 2 ;;
    *)  PROJECT="$1"; shift ;;
  esac
done

if [ -z "$PROJECT" ]; then
  echo -e "${RED}Error: no project id given.${NC}" >&2
  echo "  Usage: bash scripts/install/install_mcp.sh <project-id> [--host|--repo] [--out FILE]" >&2
  echo "  Registered projects come from ~/.drunken/projects.json; drunken-doctor lists them." >&2
  exit 2
fi

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   MCP Server Configuration                     ${NC}"
echo -e "${BLUE}=================================================${NC}"
echo -e "  Project:  $PROJECT"
echo -e "  Kind:     $KIND"
[ -n "$OUT" ] && echo -e "  Out:      $OUT"
echo ""

# Prefer the installed console script; fall back to running it out of the
# checkout. The fallback exists so this works before `uv tool install`, which
# is exactly when somebody is most likely to be running it.
if command -v drunken-config >/dev/null 2>&1; then
  _config() { drunken-config "$@"; }
elif command -v uv >/dev/null 2>&1; then
  echo -e "${YELLOW}  drunken-config is not on PATH — running it from the checkout.${NC}"
  echo -e "${YELLOW}  \`uv tool install .\` puts it on PATH permanently.${NC}"
  echo ""
  _config() { (cd "$PROJECT_ROOT" && uv run drunken-config "$@"); }
else
  echo -e "${RED}Error: neither drunken-config nor uv is available.${NC}" >&2
  echo "  Install uv (https://docs.astral.sh/uv/) or run \`uv tool install .\` first." >&2
  exit 1
fi

# `--kind host` writes absolute paths, which is the whole point: a config that
# says `uv run` with a relative PYTHONPATH works only from inside this checkout
# and fails silently the moment it is copied into a consuming project.
#
# `--kind mcp` is the names-only form, for a repository whose own .mcp.json
# should not carry one machine's directory layout into another repo's history.
if [ -n "$OUT" ]; then
  _config --project "$PROJECT" --kind "$KIND" --out "$OUT"
  echo ""
  echo -e "${GREEN}Done.${NC} Wrote $OUT"
  if [ "$KIND" = "host" ]; then
    echo -e "  Merged, so any other servers already configured there are untouched."
  fi
else
  _config --project "$PROJECT" --kind "$KIND"
  echo ""
  echo -e "${GREEN}Done.${NC} Printed only — nothing was written."
  echo -e "  Add ${YELLOW}--out <file>${NC} to write it."
fi

echo ""
echo -e "  Verify the credential actually resolves before trusting this:"
echo -e "    drunken-doctor --project $PROJECT"
echo -e "  A green line means the credential authenticates. It does ${YELLOW}not${NC} mean the"
echo -e "  Jira project key exists — check that yourself the first time (DG-260)."
