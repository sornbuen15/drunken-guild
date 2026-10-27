'use strict';

// Exercise the shipped browser script without adding a frontend dependency.
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const script = readFileSync(join(__dirname, '../src/core/dashboard/app.js'), 'utf8');

class Element {
  constructor() {
    this.children = []; this.listeners = {}; this.dataset = {};
    this.hidden = false; this.textContent = ''; this.value = 'all';
    this.classList = {toggle() {}};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this.textContent = ''; }
  get options() { return this.children; }
  setAttribute() {}
  addEventListener(event, callback) { this.listeners[event] = callback; }
}
function snapshot(mode, id) {
  return {mode, observed_at: new Date().toISOString(), projects: [{id: 'alpha'}],
    sessions: [{session_id: id, provider: 'Claude Code', activity: 'busy', project_id: 'alpha'}],
    session_sources: [{provider: 'Claude Code', status: 'available'}], saved_sessions: []};
}
function setup() {
  const elements = new Map(); const requests = []; const timers = [];
  const get = id => {if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);};
  const tabs = ['all', 'busy', 'idle', 'unknown'].map(status => {
    const element = new Element(); element.dataset.status = status; return element;
  });
  const document = {hidden: false, getElementById: get, createElement: () => new Element(), querySelectorAll: () => tabs};
  const context = vm.createContext({document, AbortController, Date,
    setTimeout, clearTimeout, setInterval: callback => timers.push(callback),
    fetch: url => new Promise((resolve, reject) => requests.push({url, resolve, reject})),
    window: {scrollTo() {}}});
  vm.runInContext(script, context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  const respond = async data => {requests.at(-1).resolve({ok: true, json: async () => data}); await flush();};
  const text = element => element.textContent + element.children.map(text).join(' ');
  return {get, requests, timers, document, respond, flush, text,
    click: id => get(id).listeners.click(),
    change: (id, value) => get(id).listeners.change({target: {value}})};
}

test('switching mode clears previous records and counters before the next response', async () => {
  const ui = setup(); await ui.respond(snapshot('live', 'live-alpha'));
  ui.click('mode-demo');
  const before = ui.text(ui.get('sessions-body'));
  const counter = ui.get('stat-total').textContent;
  await ui.respond(snapshot('demo', 'demo-alpha'));
  assert.doesNotMatch(before, /live-alpha/);
  assert.equal(counter, '—');
});

test('failed live load cannot leave demo details or source records on screen', async () => {
  const ui = setup(); await ui.respond(snapshot('live', 'live-alpha'));
  ui.click('mode-demo'); await ui.respond(snapshot('demo', 'demo-alpha'));
  ui.click('mode-live'); ui.requests.at(-1).reject(new Error('offline')); await ui.flush();
  assert.equal(ui.get('detail-content').hidden, true);
  assert.doesNotMatch(ui.text(ui.get('detail-content')), /demo-alpha/);
  assert.equal(ui.get('source-list').children.length, 0);
  assert.equal(ui.get('stat-total').textContent, '—');
  assert.match(ui.get('error-banner').textContent, /could not be read/);
});

test('a response from the wrong data mode is rejected', async () => {
  const ui = setup(); await ui.respond(snapshot('demo', 'demo-alpha'));
  assert.equal(ui.get('error-banner').hidden, false);
  assert.doesNotMatch(ui.text(ui.get('sessions-body')), /demo-alpha/);
});

test('a failed refresh preserves same-mode records with a stale warning', async () => {
  const ui = setup(); await ui.respond(snapshot('live', 'live-alpha'));
  ui.click('refresh'); ui.requests.at(-1).reject(new Error('offline')); await ui.flush();
  assert.match(ui.text(ui.get('sessions-body')), /live-alpha/);
  assert.match(ui.get('updated').textContent, /Stale snapshot/);
  assert.equal(ui.get('error-banner').hidden, false);
});

test('mode switch resets the provider filter to show the new roster', async () => {
  const ui = setup(); const data = snapshot('live', 'live-alpha');
  data.session_sources.push({provider: 'Codex', status: 'unsupported'});
  await ui.respond(data); ui.change('provider-filter', 'Codex'); ui.click('mode-demo');
  const demo = snapshot('demo', 'demo-alpha'); demo.session_sources = data.session_sources;
  await ui.respond(demo);
  assert.equal(ui.get('provider-filter').value, 'all');
  assert.match(ui.text(ui.get('sessions-body')), /demo-alpha/);
});

test('hidden tabs and pending requests do not duplicate discovery requests', async () => {
  const ui = setup(); await ui.respond(snapshot('live', 'live-alpha'));
  ui.get('auto-refresh').checked = true; ui.document.hidden = true;
  ui.timers[0](); assert.equal(ui.requests.length, 1);
  ui.document.hidden = false; ui.timers[0](); ui.timers[0]();
  assert.equal(ui.requests.length, 2);
  await ui.respond(snapshot('live', 'live-beta'));
});

test('unavailable discovery is distinct from a successful empty roster', async () => {
  const ui = setup(); const data = snapshot('live', 'live-alpha');
  data.sessions = []; data.session_sources = [{provider: 'Claude Code', status: 'error'}];
  await ui.respond(data);
  assert.match(ui.text(ui.get('sessions-body')), /Live discovery unavailable/);
  assert.doesNotMatch(ui.text(ui.get('sessions-body')), /No live sessions detected/);
});
