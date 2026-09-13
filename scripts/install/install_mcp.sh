#!/bin/bash
# Print the MCP server configuration, or write it to a file.
# Usage: bash scripts/install/install_mcp.sh [--out FILE]
#
# There is nothing to generate any more, and that is the point.
#
# This used to be a thin wrapper over `drunken-config`, because the config was
# derived per project: it carried `--project <id>`, so the file decided which
# Jira each server talked to. That is what made it worth generating from the
# registry rather than hand-writing -- and it is also what an entry registered
# at *user* scope could pin, handing every session on the machine one project's
# board while reporting success (DG-341).
#
# Every tool takes the project as its first argument now, so this configuration
# is identical for every project and carries no project at all. A constant needs
# no generator, and `drunken-config` is retired (DG-356).
#
# Two things it deliberately does not do:
#
# * **No absolute paths.** The command form depends on `uv tool install .`
#   having run. An absolute path here is one machine's directory layout written
#   into another repository's history.
# * **No merging into a host's own config file.** That needs to read what is
#   already there and prune only what this project owns, which is
#   `scripts/onboard_project.py --merge-mcp-config`. Printing a document and
#   editing somebody's home directory are different operations, and the second
#   one should say so.

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

OUT=""
STALE_PROJECT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --out)  OUT="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,4p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*) echo -e "${RED}Unknown option: $1${NC}" >&2
        echo "  Usage: bash scripts/install/install_mcp.sh [--out FILE]" >&2
        exit 2 ;;
    # A project id used to be required here, so every note, script and habit
    # that learned this command passes one. Accepted and ignored with a notice,
    # the same way the server itself now treats a stale `--project`: refusing it
    # would turn a cosmetic staleness into a failed onboarding, and the config
    # is identical for every project anyway.
    *)  STALE_PROJECT="$1"; shift ;;
  esac
done

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}   MCP Server Configuration                     ${NC}"
echo -e "${BLUE}=================================================${NC}"
[ -n "$OUT" ] && echo -e "  Out:      $OUT"
if [ -n "$STALE_PROJECT" ]; then
  echo -e "${YELLOW}  Ignoring '$STALE_PROJECT': this config carries no project (DG-341).${NC}"
  echo -e "${YELLOW}  Every tool takes the project id as its first argument instead.${NC}"
fi
echo ""

DOCUMENT='{
  "mcpServers": {
    "drunken-jira-mcp": { "command": "drunken-jira-mcp" }
  }
}'

if [ -n "$OUT" ]; then
  printf '%s\n' "$DOCUMENT" > "$OUT"
  echo ""
  echo -e "${GREEN}Done.${NC} Wrote $OUT"
else
  printf '%s\n' "$DOCUMENT"
  echo ""
  echo -e "${GREEN}Done.${NC} Printed only — nothing was written."
  echo -e "  Add ${YELLOW}--out <file>${NC} to write it."
fi

echo ""
echo -e "  The same file is correct for every project: each tool takes the"
echo -e "  registry project id as its first argument, so nothing here chooses one."
echo ""
echo -e "  Verify a credential actually resolves before trusting it:"
echo -e "    drunken-doctor --project <project-id>"
echo -e "  A green line means the credential authenticates. It does ${YELLOW}not${NC} mean the"
echo -e "  Jira project key exists — check that yourself the first time (DG-260)."
