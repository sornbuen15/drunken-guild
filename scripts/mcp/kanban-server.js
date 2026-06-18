#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');

const BOARD_DIR = process.env.KANBAN_BOARD_DIR || path.join('.claude', 'board');
const VALID_LANES = ['backlog', 'todo', 'in-progress', 'done'];
const LOCK_FILE = path.join(BOARD_DIR, '.kanban.lock');
const LOCK_STALE_MS = 5000;
const LOCK_RETRIES = 10;
const LOCK_DELAY_MS = 50;
const CLAIM_TTL_MS = (parseInt(process.env.KANBAN_CLAIM_TTL_SECONDS || '1800', 10)) * 1000;

// ─── Lock ─────────────────────────────────────────────────────────────────────

function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function acquireLock() {
  fs.mkdirSync(BOARD_DIR, { recursive: true });
  for (let i = 0; i < LOCK_RETRIES; i++) {
    if (fs.existsSync(LOCK_FILE)) {
      const age = Date.now() - fs.statSync(LOCK_FILE).mtimeMs;
      if (age > LOCK_STALE_MS) {
        try { fs.unlinkSync(LOCK_FILE); } catch (_) { }
      }
    }
    try {
      const fd = fs.openSync(LOCK_FILE, 'wx');
      fs.closeSync(fd);
      return;
    } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      sleepSync(LOCK_DELAY_MS);
    }
  }
  throw new Error(`Cannot acquire lock after ${LOCK_RETRIES} attempts`);
}

function releaseLock() {
  try { fs.unlinkSync(LOCK_FILE); } catch (_) { }
}

// ─── Board helpers ─────────────────────────────────────────────────────────────

function computeNextId() {
  let max = 0;
  for (const lane of VALID_LANES) {
    const dir = path.join(BOARD_DIR, lane);
    if (!fs.existsSync(dir)) continue;
    for (const f of fs.readdirSync(dir)) {
      const m = f.match(/^TASK-(\d+)_/);
      if (m) max = Math.max(max, parseInt(m[1], 10));
    }
  }
  return max + 1;
}

function findTask(taskId) {
  for (const lane of VALID_LANES) {
    const dir = path.join(BOARD_DIR, lane);
    if (!fs.existsSync(dir)) continue;
    const f = fs.readdirSync(dir).find(name => name.startsWith(taskId + '_'));
    if (f) return { lane, file: f, fullPath: path.join(dir, f) };
  }
  return null;
}

function parseFrontmatter(content) {
  const m = content.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return {};
  const fm = {};
  for (const line of m[1].split('\n')) {
    const kv = line.match(/^([\w_]+):\s*(.*)$/);
    if (!kv) continue;
    const [, key, raw] = kv;
    const v = raw.trim();
    if (v.startsWith('[')) {
      try {
        fm[key] = JSON.parse(v.replace(/'/g, '"'));
      } catch {
        fm[key] = v.slice(1, -1).split(',').map(s => s.trim()).filter(Boolean);
      }
    } else {
      fm[key] = v.replace(/^["']|["']$/g, '');
    }
  }
  return fm;
}

function setFrontmatterField(content, field, value) {
  const re = new RegExp(`^${field}:[^\n]*$`, 'm');
  if (re.test(content)) return content.replace(re, `${field}: ${value}`);
  return content.replace(/^(---\n[\s\S]*?)(---)/m, `$1${field}: ${value}\n$2`);
}

function removeFrontmatterField(content, field) {
  return content.replace(new RegExp(`^${field}:[^\n]*\n`, 'm'), '');
}

function taskSummary(lane, file, fullPath) {
  const content = fs.readFileSync(fullPath, 'utf8');
  const fm = parseFrontmatter(content);
  const id = (file.match(/^(TASK-\d+)/) || [])[1] || file;
  return {
    id,
    title: fm.title || '(no title)',
    priority: fm.priority || '?',
    assigned_to: fm.assigned_to || '?',
    depends_on: fm.depends_on || [],
    blocks: fm.blocks || [],
    claimed_at: fm.claimed_at || null,
    claimed_by: fm.claimed_by || null,
    lane,
  };
}

// ─── Tool handlers ─────────────────────────────────────────────────────────────

function toolNextId() {
  const nnn = computeNextId();
  return { id: `TASK-${String(nnn).padStart(3, '0')}`, nnn };
}

function toolCreateTask({ lane, slug, content }) {
  if (!VALID_LANES.includes(lane)) throw new Error(`Invalid lane: ${lane}`);
  acquireLock();
  try {
    const nnn = computeNextId();
    const padded = String(nnn).padStart(3, '0');
    const dir = path.join(BOARD_DIR, lane);
    fs.mkdirSync(dir, { recursive: true });
    const file = `TASK-${padded}_${slug}.md`;
    const dest = path.join(dir, file);
    if (fs.existsSync(dest)) throw new Error(`${dest} already exists`);
    fs.writeFileSync(dest, content, 'utf8');
    return { ok: true, id: `TASK-${padded}`, path: dest };
  } finally {
    releaseLock();
  }
}

function toolClaimTask({ task_id, agent_slug }) {
  acquireLock();
  try {
    const found = findTask(task_id);
    if (!found) return { ok: false, reason: 'task_not_found' };
    if (found.lane !== 'todo') return { ok: false, reason: `wrong_lane: ${found.lane}` };

    const content = fs.readFileSync(found.fullPath, 'utf8');
    const fm = parseFrontmatter(content);
    const assignee = (fm.assigned_to || '').replace('@', '');
    const requester = agent_slug.replace('@', '');

    if (assignee && assignee !== requester) {
      return { ok: false, reason: `assignee_mismatch: assigned to ${fm.assigned_to}` };
    }
    if (fm.claimed_at) {
      const age = Date.now() - new Date(fm.claimed_at).getTime();
      if (age < CLAIM_TTL_MS) {
        return { ok: false, reason: `already_claimed_by: ${fm.claimed_by || 'unknown'} at ${fm.claimed_at}` };
      }
      // stale claim — fall through and overwrite
    }

    const iso = new Date().toISOString();
    let updated = setFrontmatterField(content, 'claimed_at', iso);
    updated = setFrontmatterField(updated, 'claimed_by', agent_slug);
    fs.writeFileSync(found.fullPath, updated, 'utf8');
    return { ok: true, id: task_id, claimed_at: iso };
  } finally {
    releaseLock();
  }
}

function toolReleaseClaim({ task_id, agent_slug }) {
  acquireLock();
  try {
    const found = findTask(task_id);
    if (!found) return { ok: false, reason: 'task_not_found' };

    const content = fs.readFileSync(found.fullPath, 'utf8');
    const fm = parseFrontmatter(content);
    const claimant = (fm.claimed_by || '').replace('@', '');
    const requester = agent_slug.replace('@', '');

    if (claimant && claimant !== requester && requester !== 'principal-engineer') {
      return { ok: false, reason: `claim_owned_by: ${fm.claimed_by}` };
    }

    let updated = removeFrontmatterField(content, 'claimed_at');
    updated = removeFrontmatterField(updated, 'claimed_by');
    fs.writeFileSync(found.fullPath, updated, 'utf8');
    return { ok: true, id: task_id };
  } finally {
    releaseLock();
  }
}

function toolMoveTask({ task_id, target_lane, agent_slug }) {
  if (!VALID_LANES.includes(target_lane)) throw new Error(`Invalid lane: ${target_lane}`);
  acquireLock();
  try {
    const found = findTask(task_id);
    if (!found) return { ok: false, reason: 'task_not_found' };

    if (target_lane === 'in-progress') {
      const content = fs.readFileSync(found.fullPath, 'utf8');
      const fm = parseFrontmatter(content);
      const requester = (agent_slug || '').replace('@', '');

      if (!fm.claimed_at) {
        return { ok: false, reason: 'not_claimed: call board_claim_task first' };
      }
      const claimant = (fm.claimed_by || '').replace('@', '');
      if (claimant && claimant !== requester) {
        return { ok: false, reason: `claim_owned_by: ${fm.claimed_by}` };
      }

      // WIP=1 check: no other in-progress task assigned to this agent
      const ipDir = path.join(BOARD_DIR, 'in-progress');
      if (fs.existsSync(ipDir)) {
        for (const f of fs.readdirSync(ipDir)) {
          const fc = fs.readFileSync(path.join(ipDir, f), 'utf8');
          const ffm = parseFrontmatter(fc);
          if ((ffm.assigned_to || '').replace('@', '') === requester) {
            const activeId = (f.match(/^(TASK-\d+)/) || [])[1] || f;
            return { ok: false, reason: `wip_limit_exceeded: ${activeId} already in-progress for ${agent_slug}` };
          }
        }
      }
    }

    const destDir = path.join(BOARD_DIR, target_lane);
    fs.mkdirSync(destDir, { recursive: true });
    fs.renameSync(found.fullPath, path.join(destDir, found.file));
    return { ok: true, id: task_id, from: found.lane, to: target_lane };
  } finally {
    releaseLock();
  }
}

function toolDoneTask({ task_id, agent_slug }) {
  acquireLock();
  try {
    const found = findTask(task_id);
    if (!found) return { ok: false, reason: 'task_not_found' };
    if (found.lane !== 'in-progress') {
      return { ok: false, reason: `wrong_lane: ${found.lane}` };
    }

    if (agent_slug) {
      const content = fs.readFileSync(found.fullPath, 'utf8');
      const fm = parseFrontmatter(content);
      const claimant = (fm.claimed_by || '').replace('@', '');
      const requester = agent_slug.replace('@', '');
      if (claimant && claimant !== requester) {
        return { ok: false, reason: `assignee_mismatch: claimed by ${fm.claimed_by}` };
      }
    }

    const doneDir = path.join(BOARD_DIR, 'done');
    fs.mkdirSync(doneDir, { recursive: true });
    fs.renameSync(found.fullPath, path.join(doneDir, found.file));
    return { ok: true, id: task_id };
  } finally {
    releaseLock();
  }
}

function toolGetTask({ task_id }) {
  const found = findTask(task_id);
  if (!found) return { ok: false, reason: 'task_not_found' };
  const content = fs.readFileSync(found.fullPath, 'utf8');
  const fm = parseFrontmatter(content);
  return { ok: true, id: task_id, lane: found.lane, file: found.file, frontmatter: fm, content };
}

function toolListLane({ lane }) {
  if (!VALID_LANES.includes(lane)) throw new Error(`Invalid lane: ${lane}`);
  const dir = path.join(BOARD_DIR, lane);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(f => f.endsWith('.md'))
    .map(f => taskSummary(lane, f, path.join(dir, f)));
}

function toolSummary() {
  const lanes = {};
  for (const lane of VALID_LANES) {
    const dir = path.join(BOARD_DIR, lane);
    if (!fs.existsSync(dir)) { lanes[lane] = []; continue; }
    lanes[lane] = fs.readdirSync(dir)
      .filter(f => f.endsWith('.md'))
      .map(f => taskSummary(lane, f, path.join(dir, f)));
  }

  // Collect stale claim candidates (read phase — no lock needed)
  const staleIds = (lanes.todo || [])
    .filter(t => t.claimed_at && (Date.now() - new Date(t.claimed_at).getTime()) > CLAIM_TTL_MS)
    .map(t => t.id);

  // Release each stale claim under lock (double-checked locking: re-verify before writing)
  for (const taskId of staleIds) {
    acquireLock();
    try {
      const found = findTask(taskId);
      if (!found) continue;
      const c = fs.readFileSync(found.fullPath, 'utf8');
      const fm = parseFrontmatter(c);
      // Re-check under lock — another agent may have already reclaimed or released
      if (!fm.claimed_at) continue;
      if ((Date.now() - new Date(fm.claimed_at).getTime()) < CLAIM_TTL_MS) continue;
      let updated = removeFrontmatterField(c, 'claimed_at');
      updated = removeFrontmatterField(updated, 'claimed_by');
      fs.writeFileSync(found.fullPath, updated, 'utf8');
      const summary = (lanes.todo || []).find(t => t.id === taskId);
      if (summary) { summary.claimed_at = null; summary.claimed_by = null; summary._stale_claim_released = true; }
    } finally {
      releaseLock();
    }
  }

  return {
    counts: Object.fromEntries(VALID_LANES.map(l => [l, (lanes[l] || []).length])),
    lanes,
  };
}

function toolOrchestrate({ task_ids }) {
  const tasks = [];
  for (const id of task_ids) {
    const found = findTask(id);
    if (!found) continue;
    const content = fs.readFileSync(found.fullPath, 'utf8');
    const fm = parseFrontmatter(content);
    tasks.push({
      id,
      title: fm.title || '(no title)',
      assigned_to: fm.assigned_to || '?',
      priority: fm.priority || 'LOW',
      depends_on: (fm.depends_on || []).filter(d => task_ids.includes(d)),
    });
  }

  const taskMap = new Map(tasks.map(t => [t.id, t]));
  const levelMap = new Map();

  function getLevel(id) {
    if (levelMap.has(id)) return levelMap.get(id);
    const t = taskMap.get(id);
    if (!t) return 0;
    const deps = t.depends_on.filter(d => taskMap.has(d));
    if (deps.length === 0) { levelMap.set(id, 0); return 0; }
    const l = Math.max(...deps.map(getLevel)) + 1;
    levelMap.set(id, l);
    return l;
  }
  tasks.forEach(t => getLevel(t.id));

  const waveMap = new Map();
  for (const t of tasks) {
    const l = levelMap.get(t.id) || 0;
    if (!waveMap.has(l)) waveMap.set(l, []);
    waveMap.get(l).push(t);
  }

  const waves = Array.from(waveMap.entries())
    .sort(([a], [b]) => a - b)
    .map(([l, wTasks]) => {
      const agents = wTasks.map(t => t.assigned_to);
      const uniqueAgents = new Set(agents);
      const agentConflict = uniqueAgents.size < agents.length;
      const mode = wTasks.length > 1 ? 'parallel' : 'sequential';
      const rationale = wTasks.length === 1
        ? 'Single task in this wave.'
        : agentConflict
          ? `${wTasks.length} tasks share an agent — sub-sequence required within wave.`
          : `${wTasks.length} tasks, ${uniqueAgents.size} different agents, no mutual dependencies.`;
      return {
        wave: l + 1,
        mode,
        depends_on_wave: l > 0 ? l : null,
        agent_conflict: agentConflict,
        rationale,
        tasks: wTasks.map(t => ({
          id: t.id,
          assigned_to: t.assigned_to,
          title: t.title,
          priority: t.priority,
        })),
      };
    });

  return { total_tasks: tasks.length, waves };
}

function toolAgentContext({ task_id }) {
  const found = findTask(task_id);
  if (!found) return { ok: false, reason: 'task_not_found' };
  const content = fs.readFileSync(found.fullPath, 'utf8');
  const fm = parseFrontmatter(content);

  const objective = ((content.match(/## Objective\n([\s\S]*?)(?=\n##|$)/) || [])[1] || '').trim();
  const acBlock = (content.match(/## Acceptance Criteria\n([\s\S]*?)(?=\n##|$)/) || [])[1] || '';
  const criteria = acBlock.match(/- \[[ x]\] .+/g) || [];
  const notes = ((content.match(/## Technical Notes\n([\s\S]*?)(?=\n##|$)/) || [])[1] || '').trim();
  const filesInAC = [...new Set((acBlock.match(/`[^`]+\.[a-zA-Z]{1,6}`/g) || []))].map(s => s.slice(1, -1));

  return {
    task_id,
    lane: found.lane,
    title: fm.title || '',
    assigned_to: fm.assigned_to || '',
    priority: fm.priority || '',
    objective,
    acceptance_criteria: criteria,
    technical_notes: notes || null,
    relevant_files: filesInAC,
    depends_on: fm.depends_on || [],
    blocks: fm.blocks || [],
  };
}

// ─── query_project_context helpers ────────────────────────────────────────────

function extractMatchingSections(lines, keywords, maxLines) {
  const headingRe = /^(#{1,4})\s+(.+)$/;
  const sections = [];
  let i = 0;

  while (i < lines.length) {
    const hm = lines[i].match(headingRe);
    if (hm) {
      const level = hm[1].length;
      const title = hm[2];
      const start = i;
      i++;
      while (i < lines.length) {
        const nm = lines[i].match(headingRe);
        if (nm && nm[1].length <= level) break;
        i++;
      }
      const titleHit = keywords.some(kw => title.toLowerCase().includes(kw.toLowerCase()));
      const body = lines.slice(start + 1, i).join('\n');
      const bodyHit = !titleHit && keywords.some(kw => body.toLowerCase().includes(kw.toLowerCase()));
      if (titleHit || bodyHit) {
        sections.push({
          section_title: title,
          content: lines.slice(start, Math.min(i, start + maxLines)).join('\n'),
          line_start: start + 1,
          truncated: (i - start) > maxLines,
        });
      }
      continue;
    }
    i++;
  }

  // Fallback: inline keyword matches with ±3 lines of context
  if (sections.length === 0) {
    const seen = new Set();
    for (let j = 0; j < lines.length; j++) {
      if (keywords.some(kw => lines[j].toLowerCase().includes(kw.toLowerCase()))) {
        const s = Math.max(0, j - 3);
        const e = Math.min(lines.length, j + 7);
        const key = `${s}-${e}`;
        if (!seen.has(key)) {
          seen.add(key);
          sections.push({ section_title: '(inline match)', content: lines.slice(s, e).join('\n'), line_start: s + 1, truncated: false });
        }
        j = e;
      }
    }
  }

  return sections;
}

function toolQueryProjectContext({ files, keywords }) {
  if (!Array.isArray(files) || files.length === 0) throw new Error('files must be a non-empty array');
  if (!Array.isArray(keywords) || keywords.length === 0) throw new Error('keywords must be a non-empty array');

  const results = [];
  for (const filePath of files) {
    // Resolve short names like 'PROJECT_SPEC.md' to '.claude/PROJECT_SPEC.md'
    let resolved = filePath;
    if (!filePath.includes('/') && !filePath.startsWith('.')) {
      const candidate = path.join('.claude', filePath);
      if (fs.existsSync(candidate)) resolved = candidate;
    }
    if (!fs.existsSync(resolved)) {
      results.push({ file: filePath, error: 'file_not_found' });
      continue;
    }
    const lines = fs.readFileSync(resolved, 'utf8').split('\n');
    const sections = extractMatchingSections(lines, keywords, 60);
    for (const s of sections) results.push({ file: filePath, ...s });
  }

  return { results, total_matches: results.length };
}

// ─── Tool catalog ──────────────────────────────────────────────────────────────

const TOOLS = [
  {
    name: 'board_next_id',
    description: 'Returns the next available task ID (TASK-NNN). Call before creating a task to preview the ID.',
    inputSchema: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'board_create_task',
    description: 'Atomically creates a new task file in the specified lane under a file lock to prevent ID collisions.',
    inputSchema: {
      type: 'object',
      properties: {
        lane: { type: 'string', enum: VALID_LANES },
        slug: { type: 'string', description: 'Kebab-case filename slug, e.g. implement-jwt-auth' },
        content: { type: 'string', description: 'Full Markdown content including YAML frontmatter' },
      },
      required: ['lane', 'slug', 'content'],
    },
  },
  {
    name: 'board_claim_task',
    description: 'Atomically claims a todo/ task for the requesting agent. Validates assigned_to match and prevents concurrent double-claim. Must succeed before board_move_task to in-progress.',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: { type: 'string', description: 'Task ID, e.g. TASK-007' },
        agent_slug: { type: 'string', description: 'Agent slug, e.g. @fullstack-engineer' },
      },
      required: ['task_id', 'agent_slug'],
    },
  },
  {
    name: 'board_release_claim',
    description: 'Releases a stale or abandoned claim. Only the original claimant or @principal-engineer may release.',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: { type: 'string' },
        agent_slug: { type: 'string', description: 'Must match claimed_by, or be principal-engineer for override.' },
      },
      required: ['task_id', 'agent_slug'],
    },
  },
  {
    name: 'board_move_task',
    description: 'Moves a task between lanes. Moving to in-progress requires a prior board_claim_task call and enforces WIP=1 per agent.',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: { type: 'string' },
        target_lane: { type: 'string', enum: VALID_LANES },
        agent_slug: { type: 'string', description: 'Required when moving to in-progress.' },
      },
      required: ['task_id', 'target_lane', 'agent_slug'],
    },
  },
  {
    name: 'board_done_task',
    description: 'Moves a task from in-progress to done. Validates current lane and optionally validates agent identity.',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: { type: 'string' },
        agent_slug: { type: 'string' },
      },
      required: ['task_id', 'agent_slug'],
    },
  },
  {
    name: 'board_get_task',
    description: 'Returns the full content and parsed frontmatter of a single task, including its current lane.',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: { type: 'string' },
      },
      required: ['task_id'],
    },
  },
  {
    name: 'board_list_lane',
    description: 'Lists all tasks in a single lane as structured summaries (id, title, priority, assigned_to, depends_on, blocks, claim state).',
    inputSchema: {
      type: 'object',
      properties: {
        lane: { type: 'string', enum: VALID_LANES },
      },
      required: ['lane'],
    },
  },
  {
    name: 'board_summary',
    description: 'Returns a compact snapshot of all lanes: per-lane task counts plus structured summaries. Also auto-releases stale claims older than KANBAN_CLAIM_TTL_SECONDS (default 1800).',
    inputSchema: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'board_orchestrate',
    description: 'Reads depends_on / blocks fields of the supplied tasks and returns a dependency-resolved execution plan with tasks grouped into parallel waves in topological order.',
    inputSchema: {
      type: 'object',
      properties: {
        task_ids: {
          type: 'array',
          items: { type: 'string' },
          description: 'Task IDs to schedule, e.g. ["TASK-003","TASK-004","TASK-005"]',
        },
      },
      required: ['task_ids'],
    },
  },
  {
    name: 'board_agent_context',
    description: 'Returns a compact handoff envelope for a task (~100-150 tokens): id, title, objective, acceptance_criteria, technical_notes, relevant_files, depends_on, blocks. Pass this directly to a sub-agent instead of the full task markdown.',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: { type: 'string' },
      },
      required: ['task_id'],
    },
  },
  {
    name: 'query_project_context',
    description: 'Extracts only the relevant sections from project context files (PROJECT_SPEC.md, ARCHITECTURE.md, POLICY.md) matching the supplied keywords. Returns section title + content (~60 lines max per section). Use this instead of reading whole files to avoid context bloat.',
    inputSchema: {
      type: 'object',
      properties: {
        files: {
          type: 'array',
          items: { type: 'string' },
          description: 'File names or paths to search, e.g. ["POLICY.md", "ARCHITECTURE.md"]. Short names are resolved against .claude/ automatically.',
        },
        keywords: {
          type: 'array',
          items: { type: 'string' },
          description: 'Keywords to match against section headings and body text, e.g. ["authentication", "rate limiting"].',
        },
      },
      required: ['files', 'keywords'],
    },
  },
];

const TOOL_MAP = {
  board_next_id: toolNextId,
  board_create_task: toolCreateTask,
  board_claim_task: toolClaimTask,
  board_release_claim: toolReleaseClaim,
  board_move_task: toolMoveTask,
  board_done_task: toolDoneTask,
  board_get_task: toolGetTask,
  board_list_lane: toolListLane,
  board_summary: toolSummary,
  board_orchestrate: toolOrchestrate,
  board_agent_context: toolAgentContext,
  query_project_context: toolQueryProjectContext,
};

// ─── MCP JSON-RPC 2.0 over stdio ──────────────────────────────────────────────

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function handleRequest(req) {
  const { id, method, params } = req;

  // Notifications have no id — acknowledge silently
  if (id === undefined || id === null) return;

  if (method === 'initialize') {
    send({
      jsonrpc: '2.0', id,
      result: {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {} },
        serverInfo: { name: 'kanban-board-server', version: '1.1.0' },
      },
    });
    return;
  }

  if (method === 'tools/list') {
    send({ jsonrpc: '2.0', id, result: { tools: TOOLS } });
    return;
  }

  if (method === 'tools/call') {
    const { name, arguments: args } = params || {};
    const handler = TOOL_MAP[name];
    if (!handler) {
      send({ jsonrpc: '2.0', id, error: { code: -32601, message: `Unknown tool: ${name}` } });
      return;
    }
    try {
      const result = handler(args || {});
      send({
        jsonrpc: '2.0', id,
        result: { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] },
      });
    } catch (e) {
      send({
        jsonrpc: '2.0', id,
        result: {
          content: [{ type: 'text', text: JSON.stringify({ ok: false, error: e.message }) }],
          isError: true,
        },
      });
    }
    return;
  }

  if (method === 'ping') {
    send({ jsonrpc: '2.0', id, result: {} });
    return;
  }

  send({ jsonrpc: '2.0', id, error: { code: -32601, message: `Method not found: ${method}` } });
}

// ─── Stdin reader ──────────────────────────────────────────────────────────────

process.stderr.write(`[kanban-board-server v1.1.0] stdio mode started — BOARD_DIR: ${BOARD_DIR}\n`);
process.stderr.write('[kanban-board-server] Waiting for JSON-RPC on stdin. Send {"jsonrpc":"2.0","id":1,"method":"initialize",...} to begin.\n');

let buffer = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buffer += chunk;
  const lines = buffer.split('\n');
  buffer = lines.pop();
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let req;
    try {
      req = JSON.parse(trimmed);
    } catch (_) {
      // Malformed JSON: reply with a JSON-RPC 2.0 parse error instead of
      // swallowing the line, so the client is never left waiting silently.
      send({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } });
      continue;
    }
    try {
      handleRequest(req);
    } catch (e) {
      // A handler/dispatch failure must still produce a response so the client
      // does not hang. Echo back the request id when one is available.
      const id = (req && (req.id !== undefined)) ? req.id : null;
      send({ jsonrpc: '2.0', id, error: { code: -32603, message: `Internal error: ${e.message}` } });
    }
  }
});
process.stdin.on('end', () => {
  process.stderr.write('[kanban-board-server] stdin closed — exiting.\n');
  process.exit(0);
});
