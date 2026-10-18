# Local live-session discovery

This document records the source inventory and provider-neutral contract for DG-539. “Live” means
a session currently known to a running provider process or host runtime; saved history alone is not
evidence that a session is live. Discovery is read-only and must not read or retain transcript
content.

## Source inventory

| Source | What it can establish | Platform / coverage limits | Contract treatment |
|---|---|---|---|
| Claude Code `claude agents --json` | Emits active sessions as JSON; `--all` also includes completed background sessions. A Windows observation returned records with idle and busy status. | Official CLI documentation describes monitoring and dispatching parallel background sessions. It does not define a stable JSON schema or prove that every foreground session on every host is included. Windows observation is machine-specific; macOS needs its own evidence. | Implemented in DG-540 behind a five-second, read-only query. Normalize session ID, reported working path, start time, and exact `idle`/`busy` values; omit names and all other fields. Source health distinguishes available-empty, unavailable, and error. Verify schema and coverage per supported version and OS. |
| Codex app-server `thread/list`, `thread/loaded/list`, and `thread/status/changed` | `thread/list` pages stored thread records and includes runtime status; `thread/loaded/list` reports IDs loaded in that app-server process; notifications report status transitions for loaded threads. | This is scoped to a reachable app-server. Stored thread history is not proof of liveness, and a server cannot establish visibility of sessions owned by another server/process. The CLI proxy requires an explicit socket path; Windows/macOS runtime reachability and coverage of local CLI/Desktop sessions need testing. | Deferred to DG-542: API candidate, but Hub cannot yet discover a reachable endpoint. Treat stored-but-not-loaded records as not live; never infer machine-wide completeness from one server. |
| Gemini CLI `gemini --list-sessions` | Lists saved chat sessions for the current project, including dates, message counts, and first-message previews. | This is project-scoped saved history, not a live-session API; it does not establish idle/busy. The preview may contain user content, so Hub discovery must not call this command. | Excluded as a live source unless Gemini adds a separate live runtime/status interface. |
| Operating-system process inventory | Can establish that a process is running. Process APIs exist on Windows and POSIX systems. | A process is not necessarily one session: applications can host multiple sessions, spawn helpers, or run tools. Process existence does not establish session identity, project, or idle/busy. Command lines may contain prompts or secrets and must not be collected for discovery. | Possible gap detector only. Do not present a process as a confirmed session or infer status from CPU usage, process age, or a terminal window. |
| Other installed or future coding agents | No single local interface is defined by this project or the sources reviewed for DG-539. | Vendor-specific session stores and runtime APIs vary; application presence on `PATH` does not enumerate all installed applications or all their sessions. | Add a source adapter only after its live-session semantics, fields, and platform coverage are documented and tested. Preserve unknowns for unsupported sources. |

Primary references: [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference),
[Codex App Server](https://developers.openai.com/codex/app-server), and [Gemini CLI session
management](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/tutorials/session-management.md).

## Machine evidence snapshot (2026-10-18)

- **Windows:** A lookup of common CLI command names found Claude Code and Codex on `PATH`; this is
  not an inventory of GUI-only installs. A one-time `claude agents --json` observation returned
  two active records with `busy` and `idle` values. The DG-540 adapter now queries that source and
  separates its live records from saved Hub metadata. CLI behavior was observed on this Windows
  machine; full foreground/background coverage and other Claude versions remain untested. Codex
  session discovery was not tested.
- **macOS:** Existing compatibility evidence records Claude Code and Codex CLI availability, but
  Hub returned no session metadata. Claude live enumeration and Codex runtime-source reachability
  were not tested in that evidence. See [`AGENT-COMPATIBILITY.md`](AGENT-COMPATIBILITY.md).
- Gemini CLI was not found by the Windows `PATH` lookup. Its documented session-list command is
  included as a reviewed non-live source, not as evidence that Gemini is installed on either host.

These observations are machine-specific. They do not prove that every installed application or
session on either OS was enumerated.

## Initial implementation boundary

DG-540 starts with the source for which this inventory found a directly callable live-session
interface:

| Initial source | First implementation target | What remains unproven |
|---|---|---|
| Claude Code | Query `claude agents --json`; expose only session ID, reported working path, start time, exact idle/busy status, registration classification, source health, and observation time. | Windows CLI behavior was observed, but the full test suite could not run in this worktree. Stable schema, complete foreground-session coverage, and macOS parity remain unverified. |

This is an implementation target, not yet a supported compatibility claim. A source is supported
only for the OS/version where its live-session behavior is tested. The Hub must show per-source
query health and coverage so an empty successful result is distinguishable from an unavailable
source.

The following are explicitly not live sources in the initial implementation:

- Gemini CLI's documented list command returns saved project history, not live status.
- Codex app-server exposes runtime thread state, but its CLI proxy requires an explicit socket path.
  This Hub has no verified way to locate or attach to the running app-server, so Codex stays
  unsupported until that discovery path is tested; DG-542 tracks it.
- A process table can show processes but cannot safely map arbitrary processes to agent sessions or
  idle/busy state. Do not infer session records from process activity.
- Other providers, GUI-only apps, and sessions behind unreachable runtimes are not covered until an
  adapter is verified. DG-542 tracks extending this source inventory and adding adapters where a
  suitable live interface exists.

This phased boundary lets DG-540 deliver truthful Claude Code coverage without redefining REQ-037's
vendor-neutral end goal. Unsupported providers remain explicit gaps, not passes or hidden omissions.

## Provider-neutral record

Each adapter returns a record with these semantics:

| Field | Meaning |
|---|---|
| `session_id` | Identifier scoped to the source; do not derive it from transcript text. |
| `provider` | Provider/application name reported by the source; otherwise unknown. |
| `project_path` | Working project path reported by the source; otherwise unknown. |
| `registration` | `registered`, `unregistered`, or `unknown`, resolved separately from discovery using the reported path and local registry. |
| `activity` | `idle`, `busy`, or `unknown`; map only source states whose semantics have been verified. |
| `source` | Adapter/runtime that supplied the record. |
| `observed_at` | Local time the adapter observed the record, used to assess freshness. |
| `evidence` | `confirmed` only when the source identifies a live session; otherwise `candidate` or omitted, never silently promoted to a session. |

Missing or inaccessible fields remain unknown. Registration is `unregistered` only when the local
registry can be read and no registered root matches; otherwise it remains `unknown`. A stale result
must not be shown as current; a failed source query must be distinguishable from an empty successful
result. Registration matching must not filter sessions out. No adapter may read transcript bodies,
first-message previews, command-line arguments, or other prompt-bearing content.

## Coverage finding

The sources reviewed expose different slices: Claude has a CLI active-session view, Codex has
runtime state through each reachable app-server, and Gemini's documented list is saved history.
There is no verified cross-vendor API that enumerates every live session on a machine. A process
inventory cannot fill that gap without misclassifying processes or inferring idle/busy. Therefore,
“all” can currently be claimed only for sources with verified adapters on the tested OS and
versions. Unsupported or unreachable sources must remain explicit coverage unknowns. DG-540 must
not claim machine-wide completeness until this gap is resolved or the Boss accepts a narrower,
source-bounded claim through `/replan`.
