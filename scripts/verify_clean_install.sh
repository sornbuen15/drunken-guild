#!/usr/bin/env bash
#
# Clean-room verification: does drunken-team work for someone who is not us?
#
# Every check here runs in a scratch HOME and a scratch DRUNKEN_HOME, with the
# environment wiped, from a directory unrelated to any project. That matters
# because every failure in MCP-ARCHITECTURE.md §1 was invisible on a developer
# machine — the config the servers needed happened to be lying around, so the
# code looked correct right up until someone else ran it.
#
# Nothing here touches your real ~/.drunken, your registry, or any project.
#
# Usage:  ./scripts/verify_clean_install.sh
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
FAKE_HOME="$WORK/home"
STATE="$WORK/state"
PROJECT="$WORK/sample-project"
BIN=""

PASS=0
FAIL=0

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

say()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
ok()   { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }

# Run a command in a wiped environment with scratch HOME/DRUNKEN_HOME.
clean_run() {
  env -i \
    HOME="$FAKE_HOME" \
    PATH="$BIN:/usr/bin:/bin:/usr/sbin:/sbin" \
    DRUNKEN_HOME="$STATE" \
    "$@" 2>&1
}

check_contains() {  # description, needle, haystack
  if printf '%s' "$3" | grep -qF -- "$2"; then ok "$1"; else
    bad "$1"; printf '        expected to contain: %s\n' "$2"
  fi
}

check_absent() {
  if printf '%s' "$3" | grep -qF -- "$2"; then
    bad "$1"; printf '        should NOT contain: %s\n' "$2"
  else ok "$1"; fi
}

mkdir -p "$FAKE_HOME" "$PROJECT"

# ---------------------------------------------------------------------------
say "0. Install into a throwaway environment"
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "  uv is required: https://docs.astral.sh/uv/getting-started/installation/"
  exit 2
fi

VENV="$WORK/venv"
uv venv "$VENV" >/dev/null 2>&1
VIRTUAL_ENV="$VENV" uv pip install -q "$REPO" >/dev/null 2>&1
BIN="$VENV/bin"

if [ -x "$BIN/drunken-doctor" ]; then ok "installed from a clean checkout"; else
  bad "install failed"; exit 1
fi

python_version="$("$BIN/python" -c 'import sys;print(".".join(map(str,sys.version_info[:2])))')"
echo "        python $python_version"

# ---------------------------------------------------------------------------
say "1. Nothing configured — does it explain itself?"
# ---------------------------------------------------------------------------
out="$(clean_run "$BIN/drunken-doctor")"
status=$?

check_contains "reports the missing registry"        "No registry at" "$out"
check_contains "tells the user the exact fix"        "drunken-init"   "$out"
[ "$status" -ne 0 ] && ok "exits non-zero when something is broken" \
                    || bad "exited 0 despite a failure"

# The §1.3 regression: paths must not resolve inside the installed venv.
check_absent "no path resolves inside the venv"      "site-packages"  "$out"
check_contains "state directory comes from the env"  "DRUNKEN_HOME"   "$out"

# ---------------------------------------------------------------------------
say "2. Follow the printed instruction — does setup actually complete?"
# ---------------------------------------------------------------------------
out="$(clean_run "$BIN/drunken-init" --project sample --path "$PROJECT")"

check_contains "drunken-init registers the project"  "registered      : sample" "$out"
check_contains "writes a v2 registry"                "schema v2"                "$out"

if [ -f "$STATE/projects.json" ]; then ok "registry file created"; else bad "no registry written"; fi

# GNU stat first, BSD second. The other order silently misreports on Linux:
# `stat -f` there means "filesystem status", which succeeds and prints something
# entirely different, so the `||` fallback never fires.
perms="$(stat -c '%a' "$STATE" 2>/dev/null || stat -f '%Lp' "$STATE" 2>/dev/null)"
case "$perms" in
  700)          ok  "state directory is owner-only (700)" ;;
  [0-7][0-7][0-7]) bad "state directory is $perms, expected 700" ;;
  *)            bad "could not read permissions of $STATE (stat returned: $perms)" ;;
esac

out="$(clean_run "$BIN/drunken-doctor" --offline)"
status=$?
[ "$status" -eq 0 ] && ok "doctor is clean after following its own advice" \
                    || { bad "doctor still failing after setup"; printf '%s\n' "$out"; }

# ---------------------------------------------------------------------------
say "3. A token must not be able to enter the registry"
# ---------------------------------------------------------------------------
out="$(clean_run "$BIN/drunken-init" --project sample \
        --jira-url https://example.atlassian.net \
        --jira-email someone@example.com \
        --jira-project-key SAMPLE \
        --jira-credential 'ATATT3xFfGF0-EXAMPLE-NOT-A-REAL-TOKEN')"

check_contains "a bare token is rejected"       "no scheme"      "$out"
check_absent   "the rejection does not echo it" "ATATT3xFfGF0-EXAMPLE" "$out"
check_absent   "and it was not written to disk" "ATATT3xFfGF0" "$(cat "$STATE/projects.json")"

out="$(clean_run "$BIN/drunken-init" --project sample \
        --jira-url https://example.atlassian.net \
        --jira-email someone@example.com \
        --jira-project-key SAMPLE \
        --jira-credential 'env://SAMPLE_JIRA_TOKEN')"
check_contains "a reference is accepted" "registered" "$out"
check_contains "and stored as a reference" "env://SAMPLE_JIRA_TOKEN" "$(cat "$STATE/projects.json")"

# ---------------------------------------------------------------------------
say "4. A bad credential must fail loudly, not look like an empty board"
# ---------------------------------------------------------------------------
# Points at a host that cannot answer, which is enough to prove the check runs
# and reports rather than silently returning nothing.
out="$(env -i HOME="$FAKE_HOME" PATH="$BIN:/usr/bin:/bin" DRUNKEN_HOME="$STATE" \
        SAMPLE_JIRA_TOKEN="not-a-real-token" \
        "$BIN/drunken-doctor" --project sample 2>&1)"
status=$?

check_contains "the credential resolved from its reference" "env://SAMPLE_JIRA_TOKEN" "$out"
[ "$status" -ne 0 ] && ok "an unusable Jira credential is a failure" \
                    || bad "an unusable credential was reported as fine"
check_absent "the token itself never appears" "not-a-real-token" "$out"

# ---------------------------------------------------------------------------
say "5. The MCP servers start for a host that knows nothing about us"
# ---------------------------------------------------------------------------
# §1.1: they used to crash during import, so the host saw no tools at all and
# no error anywhere. Starting with zero config is the whole point — the agent
# needs to be able to call a tool and be *told* what is missing.
for server in drunken-jira-mcp drunken-board-mcp drunken-discord-mcp; do
  # The server logs to its own stderr, which the client inherits, so only the
  # last line is ours.
  count="$(clean_run "$BIN/python" - "$BIN/$server" <<'PY' | tail -n1
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main() -> None:
    async with stdio_client(StdioServerParameters(command=sys.argv[1])) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            print(len((await session.list_tools()).tools))

try:
    asyncio.run(main())
except Exception as exc:
    print(f"ERROR {type(exc).__name__}: {exc}")
PY
)"
  case "$count" in
    ''|*[!0-9]*) bad "$server did not hand-shake ($count)" ;;
    *)           ok  "$server hand-shakes with zero config ($count tools)" ;;
  esac
done

# ---------------------------------------------------------------------------
say "Result"
# ---------------------------------------------------------------------------
printf '  %d passed, %d failed\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
