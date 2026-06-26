---
name: electron-ipc-protocol
description: Standardized instructions and patterns for implementing secure Electron IPC (Inter-Process Communication) between the React frontend and Node.js backend.
---

# Electron IPC Protocol

This skill provides the standard operating procedure for IPC in our Electron applications.

## Rules
1. **Context Isolation**: Must always be `true`.
2. **Node Integration**: Must always be `false` in the renderer process.
3. **Preload Scripts**: All IPC must go through a secure preload script exposing a typed API via `contextBridge.exposeInMainWorld`.
4. **Channel Naming**: Use colon-separated domain names for channels (e.g., `system:getUser`, `window:minimize`).

## Pattern Example

**Main Process (`main.js` or `ipc.ts`):**
```javascript
const { ipcMain } = require('electron');

ipcMain.handle('data:fetch', async (event, args) => {
    // Process and return data
    return { success: true, data: '...' };
});
```

**Preload Script (`preload.js`):**
```javascript
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    fetchData: (args) => ipcRenderer.invoke('data:fetch', args)
});
```

**Renderer Process (React Component):**
```javascript
// using window.electronAPI.fetchData(...)
```
