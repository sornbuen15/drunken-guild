# Local agent dashboard

The dashboard shows local session metadata and Guild-managed tasks in one browser.

From a prepared development checkout:

```powershell
uv run drunken-hub --web
```

Open `http://127.0.0.1:8765`. Stop the server with Ctrl+C in its terminal.
Use `--port 8766` to select another local port, or `--registry <path>` to use an
isolated project registry. The existing text and `--json` views remain available.

To submit work to Claude Code or Codex, start it with control enabled:

```powershell
uv run drunken-hub --web --control
```

Select a registered project and an available CLI, enter the task and submit it.
Each new task gets its own Git worktree from the registered project's current
commit; uncommitted changes are not copied. The Dashboard shows its queue state,
activity, final response, and reported subagents. Follow-up resumes that managed
agent session in the same worktree. Cancel stops only a Guild-owned task. Jobs
continue while the browser is closed but are marked interrupted if the Hub
process stops. The job history is bounded to 200 entries and private to the
machine; worktrees and task records are not removed automatically.

Control applies only to tasks submitted through this Dashboard. Existing
desktop or terminal sessions remain observation-only. Aider and Antigravity
are inventoried when their known commands are on the Hub process's PATH but
cannot yet receive Dashboard tasks.

## What you can inspect

- Live sessions, with project and activity filters, search and a details panel.
- The source and observation time for each session. Auto-refresh runs every fifteen
  seconds while the page is visible; a failed refresh marks retained data stale.
- Source availability, including successful empty results and unsupported providers.
- Saved metadata in a separate section; stored records are not proof of live activity.
  A Codex task can report its own allowlisted session metadata through
  `core.session_store.save_session_metadata`. Point `DRUNKEN_SESSION_METADATA_PATH`
  at an isolated local file for a proof run and label the agent self-reported.
  Verify its session ID against the task's own `CODEX_THREAD_ID`; do not infer
  a live activity state or machine-wide Codex coverage from a saved record.
- An explicitly labeled Demo mode for exploring the interface with sample data.
  Changing modes clears the previous roster, details and counters before loading;
  a failed load cannot leave sample records displayed as live observations.

Claude discovery uses the existing `claude agents --json` adapter. Codex,
Aider and Antigravity machine-wide live discovery remain unsupported. A source
reporting busy or idle does not identify the task being performed; an unreported
task stays unknown. Guild-owned Claude jobs use its stream to report subagent
activity. Guild-owned Codex jobs also query `codex app-server` for child-thread
metadata: `codex exec --json` alone can omit their creation. When that metadata
is unavailable, the subagent count is marked unknown. The Hub retains task
metadata and final output, not full transcripts or reasoning.

## Tailnet access

The backend remains bound to `127.0.0.1`. If Tailscale Serve is already in use,
give the Guild a separate HTTPS port rather than replacing its existing route.
For example, with local port 8765 and an unused tailnet HTTPS port 8443:

```powershell
uv run drunken-hub --web --control --port 8765 `
  --web-origin https://<node>.<tailnet>.ts.net:8443 `
  --web-user <allowed-tailscale-login>
tailscale serve --bg --https=8443 http://127.0.0.1:8765
tailscale serve status
```

Open the reported `https://...:8443` URL from an allowed tailnet device.
Tailscale Serve supplies `Tailscale-User-Login` and strips a caller-supplied
version of that header. The Hub accepts the exact configured login and HTTPS
origin; POST actions additionally require a page token. Tailscale Funnel is
not an authenticated substitute. Ensure the node's tailnet access rules allow
only intended users. Stop the Hub with Ctrl+C; remove this Serve route with
`tailscale serve --https=8443 off` when it is no longer needed.

The HTTP server binds to `127.0.0.1` and rejects foreign Host and Origin headers.
Assets are packaged with the Python runtime; no frontend build or network relay is
required for local-only use. Discovery snapshots are not persisted; managed job
metadata is saved locally for restart recovery.

The JRPG menu styling uses system fonts and CSS only, with no animation loop or extra
frontend dependencies. Hidden tabs do not poll. Tabs share a twelve-second server
snapshot cache so multiple open views do not duplicate agent-discovery processes.

## Browser-script regression checks

With Node.js available, run `node --test tests/dashboard_ui.test.cjs`. This uses
Node's built-in test runner and a minimal DOM fixture, with no package installation.
It checks mode isolation, failed loads, stale refreshes, provider reset and polling.
The CI dashboard UI job runs these checks separately from the Python matrix.
It complements browser layout checks; it does not replace them.
