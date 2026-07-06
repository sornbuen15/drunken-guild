# Plan v2: Discord as a Remote Control (Headless Agent Architecture)

## 🎯 1. Core Vision
The ultimate goal of this project is to use **Discord as the universal Remote Control** for the Drunken-Team agents.
- **Location Agnostic:** The Boss can be anywhere (on a phone, at a cafe) and command the Mac at home.
- **Headless Execution:** Agents run in the background (Headless). They do not need to take over the active Antigravity IDE UI.
- **Asynchronous Approvals:** If an Agent needs permission (e.g., to delete files or make a major architectural decision), it asks the Boss in Discord and goes to sleep. It waits for the Boss's reaction (👍/👎) to proceed.

## 🏗 2. Architecture & Data Flow (End-to-End)

### Phase 1: Receiving Orders (Discord -> Mac)
1. **The Trigger:** Boss sends a message in the designated Discord channel (e.g., `!principal สร้างหน้า Login ให้หน่อย`).
2. **The Listener:** `drunken-listen` (the Discord Bot running as a background service) receives the message.
3. **The Spawner:** The bot parses the command and executes `subprocess.Popen(["agy", ...])`.
4. **The Agent:** A brand new Antigravity agent is spawned in the background (Headless). It reads the context and starts coding.

### Phase 2: The Silent Wait Protocol (Agent -> Discord)
1. **The Block:** The background Agent encounters a strict rule (e.g., "Do not delete files without permission").
2. **The Outbox:** The Agent writes a JSON message containing the question to `.agents/discord_outbox.json`.
3. **The Sleep:** The Agent uses the `schedule` tool to set a wakeup timer and **immediately stops executing** (Ends its turn). *This fulfills the "No Scan นิ้ว" (No busy polling) rule.*
4. **The Notification:** The Discord Bot (monitoring the outbox) detects the new file, formats the question, and sends it to the Boss in Discord.

### Phase 3: The Boss's Approval (Discord -> Agent)
1. **The Decision:** Boss reads the Discord message and reacts with 👍 (Approve) or 👎 (Reject).
2. **The Inbox:** The Discord Bot detects the reaction and writes the result into `.agents/discord_inbox.json` (while clearing the outbox).
3. **The Awakening:** The Agent wakes up from its schedule, reads the `discord_inbox.json`, processes the Boss's decision, and continues coding or aborts the operation.

## 🚀 3. Implementation Steps & Checklist

- [x] **Agent Spawner:** `DiscordRunner` successfully spawns `agy` in the background (Fixed: no longer blocking Discord).
- [x] **Discord Bot Core:** `drunken-listen` is running and connecting to Discord.
- [ ] **Outbox/Inbox Watcher:** Implement a background task inside `drunken-listen` (or a separate worker) to monitor `.agents/discord_outbox.json` and send messages to Discord.
- [ ] **Reaction Listener:** Implement an event listener in `drunken-listen` to capture Boss's 👍/👎 reactions and write to `.agents/discord_inbox.json`.
- [ ] **E2E Test:** Run a full test. Boss sends a command -> Agent asks for permission via outbox -> Boss approves via Discord reaction -> Agent resumes work.

## 💡 4. Conclusion
By strictly adhering to this architecture, we completely eliminate the need for the Antigravity IDE UI to be visible during Discord operations. The Mac simply acts as the physical server, and Discord becomes the sole Interface for the Boss.
