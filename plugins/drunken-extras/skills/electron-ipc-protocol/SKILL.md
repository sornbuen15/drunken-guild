---
name: electron-ipc-protocol
description: >
  The single IPC contract for Electron applications — context isolation, the preload bridge,
  channel naming, and validating everything that crosses the process boundary. Apply whenever
  the user is writing or reviewing communication between an Electron main process and a
  renderer, wiring a preload script, exposing an API on `window`, or asking why something in
  the renderer cannot reach the file system — even if they never say "IPC".
  Trigger on /electron-ipc.
---

# Skill: Electron IPC Protocol
**Version:** v1.0.0
**Description:** The standard operating procedure for Inter-Process Communication in Electron applications — one contract, secure by construction.

---

<system_prompt>
  <role>
    When this skill applies, treat the gap between the Electron main process and the renderer as
    a trust boundary, not a plumbing detail.

    The main process holds Node.js and the user's file system. The renderer runs web content.
    Every message that crosses between them is a request from a less-trusted context into a
    more-trusted one, and is reviewed as such. The preload script is the only door, and this
    file is the shape of that door.
  </role>

  <execution_rules>
    <rule priority="FATAL" name="Context Isolation Is Always On">
      `contextIsolation: true` and `nodeIntegration: false` in every `BrowserWindow`.
      These are the boundary itself. A task that appears to need either one relaxed has a
      design problem upstream — surface it rather than turning the boundary off.
    </rule>

    <rule priority="FATAL" name="One Door: The Preload Bridge">
      All IPC goes through a preload script that exposes a **named, typed API** via
      `contextBridge.exposeInMainWorld`. Expose functions, never objects with power.

      Never place `ipcRenderer`, `require`, `process`, or any Node module on `window`. Exposing
      `ipcRenderer` directly hands the renderer every channel at once and makes the allowlist
      below unenforceable.
    </rule>

    <rule priority="FATAL" name="Validate On The Main Side">
      An `ipcMain.handle` callback receives whatever the renderer sent, including whatever an
      injected script sent. Validate shape and value before acting.

      A path, a shell command, or a URL arriving from the renderer is checked against an
      allowlist — never passed through to `fs`, `shell.openExternal`, or `child_process` as
      given. This is the single most common way an Electron app turns an XSS into
      arbitrary code execution on the user's machine.
    </rule>

    <rule priority="HIGH" name="Channel Naming Is Domain-Scoped">
      Colon-separated, domain first: `system:getUser`, `window:minimize`, `data:fetch`.
      The domain prefix is what makes the surface reviewable — you can read the list of
      channels and see what the renderer is allowed to reach.
    </rule>

    <rule priority="HIGH" name="Invoke For Request/Response, Send For Events">
      `ipcRenderer.invoke` / `ipcMain.handle` for anything that returns a value — it is
      promise-based and carries errors back.
      `webContents.send` / `ipcRenderer.on` for main-initiated events the renderer subscribes to.
      Do not build request/response out of two one-way sends; the correlation logic you would
      write is the thing `invoke` already does correctly.
    </rule>

    <rule priority="HIGH" name="Errors Cross The Boundary Too">
      A rejected handler surfaces in the renderer as a rejected promise. Return a failure the
      renderer can act on. Never swallow an error in the main process and resolve as if it
      succeeded — the renderer then renders a success state over a failure.
    </rule>
  </execution_rules>

  <pattern>
    **Main process** (`main.js` / `ipc.ts`):
    ```javascript
    const { ipcMain } = require('electron');

    ipcMain.handle('data:fetch', async (event, args) => {
      // Validate before acting. args came from the renderer.
      if (typeof args?.id !== 'string') {
        throw new Error('data:fetch requires a string id');
      }
      return { success: true, data: await lookup(args.id) };
    });
    ```

    **Preload** (`preload.js`) — the whole renderer-visible surface:
    ```javascript
    const { contextBridge, ipcRenderer } = require('electron');

    contextBridge.exposeInMainWorld('electronAPI', {
      fetchData: (args) => ipcRenderer.invoke('data:fetch', args),
    });
    ```

    **Renderer** (React component):
    ```javascript
    const result = await window.electronAPI.fetchData({ id });
    ```

    Note what the renderer cannot do: it cannot name a channel. It can only call the functions
    the preload chose to expose. That is the property worth protecting.
  </pattern>

  <constraints>
    <constraint priority="FATAL">Never set `contextIsolation: false` or `nodeIntegration: true`, for any reason, including "just for development".</constraint>
    <constraint priority="FATAL">Never expose `ipcRenderer`, `require`, `process`, `fs`, or any Node module on `window`.</constraint>
    <constraint priority="FATAL">Never pass a renderer-supplied path, command, or URL to `fs`, `shell`, or `child_process` without allowlist validation in the main process.</constraint>
    <constraint priority="HIGH">Never add a second IPC convention beside this one. If this contract does not fit a case, change the contract here rather than working around it locally.</constraint>
    <constraint priority="HIGH">This skill requires no MCP server. It is a code standard and runs anywhere Electron does.</constraint>
    <constraint priority="HIGH">All output must be in English.</constraint>
  </constraints>

  <output_format>
    When adding or reviewing IPC, report:
    - Channels: each one added or changed, with its payload and return shape
    - Validation: what checks each handler performs on its arguments
    - Preload surface: the exact functions now on `window`, and nothing implied
    - Boundary check: confirm `contextIsolation: true` and `nodeIntegration: false` are intact
    - Risks: anything the renderer can now reach that it could not before
  </output_format>
</system_prompt>
