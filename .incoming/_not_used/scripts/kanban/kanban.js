#!/usr/bin/env node
'use strict';

/**
 * Unified cross-platform Kanban board CLI.
 * Replaces kanban_read.sh / kanban_write.sh / kanban_read.ps1 / kanban_write.ps1.
 *
 * Usage:
 *   node kanban.js next-id
 *   node kanban.js list   <backlog|todo|in-progress|done>
 *   node kanban.js list-all
 *   node kanban.js get    <TASK-ID>
 *   node kanban.js create <lane> <NNN> <slug> <content-file>
 *   node kanban.js move   <TASK-ID> <target-lane>
 *   node kanban.js done   <TASK-ID>
 *
 * Environment:
 *   KANBAN_BOARD_DIR  Override the board root (default: .claude/board)
 *
 * Requires: Node.js 18+
 */

const fs   = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const BOARD_DIR     = process.env.KANBAN_BOARD_DIR
  ? process.env.KANBAN_BOARD_DIR
  : path.join('.claude', 'board');

const VALID_LANES   = ['backlog', 'todo', 'in-progress', 'done'];
const LOCK_FILE     = path.join(BOARD_DIR, '.kanban.lock');
const LOCK_STALE_MS = 5000; // lock older than this is considered abandoned
const LOCK_RETRIES  = 10;
const LOCK_DELAY_MS = 50;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function usage() {
  console.log('Usage:');
  console.log('  kanban.js next-id');
  console.log('  kanban.js list   <backlog|todo|in-progress|done>');
  console.log('  kanban.js list-all');
  console.log('  kanban.js get    <TASK-ID>');
  console.log('  kanban.js create <lane> <NNN> <slug> <content-file>');
  console.log('  kanban.js move   <TASK-ID> <target-lane>');
  console.log('  kanban.js done   <TASK-ID>');
  process.exit(1);
}

function isValidLane(lane) {
  return VALID_LANES.includes(lane);
}

/** Search every lane for a file whose name starts with <taskId>_. Returns full path or null. */
function findTaskFile(taskId) {
  for (const lane of VALID_LANES) {
    const laneDir = path.join(BOARD_DIR, lane);
    if (!fs.existsSync(laneDir)) continue;
    const files = fs.readdirSync(laneDir)
      .filter(f => f.startsWith(taskId + '_') && f.endsWith('.md'));
    if (files.length > 0) return path.join(laneDir, files[0]);
  }
  return null;
}

/** Scan every lane and return the next unused integer ID. */
function computeNextId() {
  let max = 0;
  for (const lane of VALID_LANES) {
    const laneDir = path.join(BOARD_DIR, lane);
    if (!fs.existsSync(laneDir)) continue;
    for (const f of fs.readdirSync(laneDir)) {
      const m = f.match(/^TASK-(\d+)/);
      if (m) {
        const n = parseInt(m[1], 10);
        if (n > max) max = n;
      }
    }
  }
  return max + 1;
}

/** Extract a single YAML frontmatter field value. Returns null when absent. */
function frontmatterField(content, field) {
  const m = content.match(new RegExp(`^${field}:\\s*(.+)`, 'm'));
  return m ? m[1].trim() : null;
}

/** Synchronous sleep (Atomics.wait works on the Node.js main thread, Node 18+). */
function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

// ---------------------------------------------------------------------------
// File lock — guards next-id scan + file create as one atomic operation
// ---------------------------------------------------------------------------
function acquireLock() {
  fs.mkdirSync(BOARD_DIR, { recursive: true });

  for (let attempt = 0; attempt < LOCK_RETRIES; attempt++) {
    // Auto-clear a lock left behind by a crashed process
    if (fs.existsSync(LOCK_FILE)) {
      const age = Date.now() - fs.statSync(LOCK_FILE).mtimeMs;
      if (age > LOCK_STALE_MS) {
        try { fs.unlinkSync(LOCK_FILE); } catch (_) { /* already gone */ }
      }
    }

    try {
      // 'wx' = exclusive create: succeeds for exactly one caller; others get EEXIST
      const fd = fs.openSync(LOCK_FILE, 'wx');
      fs.closeSync(fd);
      return; // lock acquired
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
      sleepSync(LOCK_DELAY_MS);
    }
  }

  console.log(`Error: could not acquire board lock after ${LOCK_RETRIES} attempts`);
  process.exit(1);
}

function releaseLock() {
  try { fs.unlinkSync(LOCK_FILE); } catch (_) { /* already gone */ }
}

// ---------------------------------------------------------------------------
// Command implementations
// ---------------------------------------------------------------------------
function cmdNextId() {
  const n = computeNextId();
  console.log(String(n).padStart(3, '0'));
}

function cmdList(lane) {
  if (!lane) { console.log("Error: lane required for 'list'"); usage(); }

  const laneDir = path.join(BOARD_DIR, lane);
  if (!fs.existsSync(laneDir)) {
    console.log(`Lane '${lane}' does not exist at ${laneDir}`);
    process.exit(1);
  }

  const files = fs.readdirSync(laneDir)
    .filter(f => /^TASK-.*\.md$/.test(f))
    .sort();

  if (files.length === 0) { console.log('(empty)'); return; }

  for (const f of files) {
    const fullPath = path.join(laneDir, f);
    const content  = fs.readFileSync(fullPath, 'utf8');
    const id       = frontmatterField(content, 'id')          ?? '?';
    const priority = frontmatterField(content, 'priority')    ?? '?';
    const assigned = frontmatterField(content, 'assigned_to') ?? '?';
    const title    = frontmatterField(content, 'title')       ?? path.basename(fullPath);
    // Column widths match the original printf "%-12s %-8s %-20s %s" format
    console.log(`${id.padEnd(12)} ${priority.padEnd(8)} ${assigned.padEnd(20)} ${title}`);
  }
}

function cmdListAll() {
  for (const lane of VALID_LANES) {
    const laneDir = path.join(BOARD_DIR, lane);
    if (!fs.existsSync(laneDir)) continue;
    const count = fs.readdirSync(laneDir).filter(f => /^TASK-.*\.md$/.test(f)).length;
    console.log(`=== ${lane} (${count}) ===`);
    cmdList(lane);
    console.log('');
  }
}

function cmdGet(taskId) {
  if (!taskId) { console.log("Error: TASK-ID required for 'get'"); usage(); }

  const found = findTaskFile(taskId);
  if (!found) {
    console.log(`Error: ${taskId} not found in any lane`);
    process.exit(1);
  }
  console.log(`File: ${found}`);
  console.log('---');
  // Write file content as-is — process.stdout.write avoids adding an extra newline
  process.stdout.write(fs.readFileSync(found, 'utf8'));
}

function cmdCreate(lane, nnn, slug, contentFile) {
  if (!lane || !nnn || !slug || !contentFile) {
    console.log('Error: create requires lane, NNN, slug, and content-file');
    usage();
  }
  if (!isValidLane(lane)) {
    console.log(`Error: '${lane}' is not a valid lane. Valid lanes: ${VALID_LANES.join(' ')}`);
    process.exit(1);
  }
  if (!fs.existsSync(contentFile)) {
    console.log(`Error: content file '${contentFile}' not found`);
    process.exit(1);
  }

  acquireLock();
  try {
    // Re-compute the real next ID while holding the lock to prevent TOCTOU races.
    // If the caller's NNN was already taken by a concurrent write, bump to actual next.
    const actualNext = computeNextId();
    const requested  = parseInt(nnn, 10);
    const useN       = requested < actualNext ? actualNext : requested;
    const padded     = String(useN).padStart(3, '0');

    const targetDir = path.join(BOARD_DIR, lane);
    fs.mkdirSync(targetDir, { recursive: true });
    const dest = path.join(targetDir, `TASK-${padded}_${slug}.md`);

    if (fs.existsSync(dest)) {
      console.log(`Error: ${dest} already exists — refusing to overwrite`);
      process.exit(1);
    }

    fs.copyFileSync(contentFile, dest);
    console.log(`Created: ${dest}`);
  } finally {
    releaseLock();
  }
}

function cmdMove(taskId, targetLane) {
  if (!taskId || !targetLane) {
    console.log('Error: move requires TASK-ID and target-lane');
    usage();
  }
  if (!isValidLane(targetLane)) {
    console.log(`Error: '${targetLane}' is not a valid lane. Valid lanes: ${VALID_LANES.join(' ')}`);
    process.exit(1);
  }

  const src = findTaskFile(taskId);
  if (!src) {
    console.log(`Error: ${taskId} not found in any lane`);
    process.exit(1);
  }

  const targetDir = path.join(BOARD_DIR, targetLane);
  fs.mkdirSync(targetDir, { recursive: true });
  const dest = path.join(targetDir, path.basename(src));

  if (path.resolve(src) === path.resolve(dest)) {
    console.log(`Task ${taskId} is already in '${targetLane}'`);
    process.exit(0);
  }

  fs.renameSync(src, dest);
  // '→' matches the output of the original kanban_write.sh
  console.log(`Moved: ${taskId} → ${targetLane}/`);
  console.log(`File: ${dest}`);
}

function cmdDone(taskId) {
  if (!taskId) { console.log('Error: TASK-ID required'); usage(); }

  const src = findTaskFile(taskId);
  if (!src) {
    console.log(`Error: ${taskId} not found in any lane`);
    process.exit(1);
  }

  const targetDir = path.join(BOARD_DIR, 'done');
  fs.mkdirSync(targetDir, { recursive: true });
  const dest = path.join(targetDir, path.basename(src));

  fs.renameSync(src, dest);
  console.log(`Done: ${taskId} → done/`);
  console.log(`File: ${dest}`);
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
const [, , cmd, ...args] = process.argv;
if (!cmd) usage();

switch (cmd) {
  case 'next-id':  cmdNextId();                                        break;
  case 'list':     cmdList(args[0]);                                   break;
  case 'list-all': cmdListAll();                                       break;
  case 'get':      cmdGet(args[0]);                                    break;
  case 'create':   cmdCreate(args[0], args[1], args[2], args[3]);     break;
  case 'move':     cmdMove(args[0], args[1]);                          break;
  case 'done':     cmdDone(args[0]);                                   break;
  default:
    console.log(`Error: unknown command '${cmd}'`);
    usage();
}
