# Local agent dashboard

The dashboard shows the Hub's local session metadata in a browser. It is read-only.

From a prepared development checkout:

```powershell
uv run drunken-hub --web
```

Open `http://127.0.0.1:8765`. Stop the server with Ctrl+C in its terminal.
Use `--port 8766` to select another local port, or `--registry <path>` to use an
isolated project registry. The existing text and `--json` views remain available.

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

Claude discovery uses the existing `claude agents --json` adapter. Codex and Gemini
live discovery remain unsupported. A source reporting busy or idle does not identify
the task being performed; an unreported task stays unknown. This view does not read
transcripts, control agents or infer progress from operating-system processes.

The HTTP server binds to `127.0.0.1` and rejects foreign Host and Origin headers.
Assets are packaged with the Python runtime; no frontend build or network relay is
required. No session data is uploaded or persisted by the dashboard.

The JRPG menu styling uses system fonts and CSS only, with no animation loop or extra
frontend dependencies. Hidden tabs do not poll. Tabs share a twelve-second server
snapshot cache so multiple open views do not duplicate agent-discovery processes.

## Browser-script regression checks

With Node.js available, run `node --test tests/dashboard_ui.test.cjs`. This uses
Node's built-in test runner and a minimal DOM fixture, with no package installation.
It checks mode isolation, failed loads, stale refreshes, provider reset and polling.
The CI dashboard UI job runs these checks separately from the Python matrix.
It complements browser layout checks; it does not replace them.
