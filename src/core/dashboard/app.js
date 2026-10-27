'use strict';

const $ = (id) => document.getElementById(id);
const state = { data: null, mode: 'live', status: 'all', provider: 'all', project: 'all', search: '', selected: null, pending: false, failed: false };
const activity = (record) => ['busy', 'idle'].includes(record.activity) ? record.activity : 'unknown';
const label = (value) => ({busy: 'Working', idle: 'Idle', unknown: 'Unknown'})[value] || value;
const time = (value) => value && !Number.isNaN(new Date(value).valueOf()) ? new Date(value).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : 'Not reported';
const key = (record, index) => `${record.source || ''}:${record.session_id || record.project_path || index}`;
function node(tag, className, text) { const element = document.createElement(tag); if (className) element.className = className; if (text !== undefined) element.textContent = text; return element; }
function badge(value) { const element = node('span', `badge ${value}`); element.append(node('span', `status-dot ${value}`), node('span', '', label(value))); return element; }
function mark(provider) { return node('span', `agent-mark ${provider === 'Codex' ? 'codex' : ''}`, provider === 'Codex' ? '⌘' : provider === 'Gemini CLI' ? '✧' : '✳'); }
function field(title, value) { const element = node('div', 'detail-field'); element.append(node('div', 'field-label', title), node('div', 'detail-value', value || 'Not reported')); return element; }

async function refresh() {
  if (state.pending) return;
  state.pending = true; $('refresh').disabled = true; $('updated').textContent = 'Refreshing…';
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(state.mode === 'demo' ? '/api/demo' : '/api/snapshot', {cache:'no-store', signal:controller.signal});
    if (!response.ok) throw new Error('Snapshot unavailable');
    const data = await response.json();
    if (data.mode !== state.mode || !Array.isArray(data.sessions) || !Array.isArray(data.session_sources) || !Array.isArray(data.projects)) throw new Error('Invalid snapshot');
    state.data = data; state.failed = false; $('error-banner').hidden = true;
    renderProjects(); render();
  } catch (_) {
    state.failed = true;
    $('error-banner').textContent = state.data ? 'Refresh failed. Showing the last successful snapshot; session activity may be stale. Retry when the local source is available.' : 'The local Hub could not be read. Check the registry and metadata files, then select Refresh.';
    $('error-banner').hidden = false; $('updated').textContent = state.data ? `Stale snapshot · ${time(state.data.observed_at)}` : 'Connection unavailable';
    if (!state.data) renderEmpty('No snapshot available', 'The local data source has not returned a usable snapshot.');
  } finally { clearTimeout(timeout); state.pending = false; $('refresh').disabled = false; }
}

function renderProjects() {
  const providerSelect = $('provider-filter'); providerSelect.replaceChildren();
  const providers = Array.from(new Set([...state.data.session_sources.map(source => source.provider), ...state.data.sessions.map(record => record.provider)].filter(Boolean))).sort();
  for (const [value, text] of [['all', 'All agents'], ...providers.map(provider => [provider, provider])]) {const option = node('option','',text);option.value=value;providerSelect.append(option);}
  if (!providers.includes(state.provider)) state.provider = 'all'; providerSelect.value = state.provider;
  const previous = state.project; const select = $('project-filter'); select.replaceChildren();
  for (const [value, text] of [['all','All projects'], ...state.data.projects.map(p => [p.id,p.id]), ['__unregistered','Unregistered'], ['__unknown','Unknown project']]) {
    const option = node('option', '', text); option.value = value; select.append(option);
  }
  state.project = Array.from(select.options).some(o => o.value === previous) ? previous : 'all'; select.value = state.project;
  $('sidebar-project-count').textContent = state.data.projects.length;
  const nav = $('project-nav'); nav.replaceChildren();
  for (const project of state.data.projects) {
    const button = node('button', state.project === project.id ? 'selected' : ''); button.append(node('span','project-swatch'), node('span','',project.id));
    button.addEventListener('click', () => {state.project = state.project === project.id ? 'all' : project.id; renderProjects(); render();}); nav.append(button);
  }
  if (!state.data.projects.length) nav.append(node('div','empty-saved','No registered projects'));
}

function filteredSessions() {
  return state.data.sessions.map((record,index) => ({...record,_key:key(record,index)})).filter(record => {
    const projectMatches = state.project === 'all' || (state.project === '__unregistered' ? record.registration === 'unregistered' : state.project === '__unknown' ? !record.project_id && record.registration !== 'unregistered' : record.project_id === state.project);
    const text = [record.provider,record.project_id,record.project_path,record.session_id,record.reported_task].filter(Boolean).join(' ').toLowerCase();
    return projectMatches && (state.provider === 'all' || record.provider === state.provider) && (state.status === 'all' || activity(record) === state.status) && text.includes(state.search.toLowerCase());
  });
}

function renderEmpty(title, description) {
  const row = node('tr'); const cell = node('td','empty-table'); cell.colSpan = 5; cell.append(node('strong','',title), node('span','',description)); row.append(cell); $('sessions-body').replaceChildren(row);
}

function clearSnapshot() {
  state.data = null; state.selected = null; state.failed = false;
  for (const id of ['stat-total','stat-busy','stat-idle','stat-unknown']) $(id).textContent = '—';
  for (const id of ['nav-total','session-count','saved-count','sidebar-project-count']) $(id).textContent = '—';
  for (const id of ['source-list','saved-list','project-nav']) $(id).replaceChildren();
  for (const [id, title] of [['provider-filter','All agents'],['project-filter','All projects']]) {
    const option = node('option','',title); option.value = 'all'; $(id).replaceChildren(option); $(id).value = 'all';
  }
  $('result-count').textContent = ''; $('error-banner').hidden = true;
  renderDetails();
  renderEmpty('Loading selected mode…', 'Waiting for a snapshot from the selected data source.');
}

function render() {
  const data = state.data; if (!data) return;
  $('demo-banner').hidden = data.mode !== 'demo';
  $('stat-total').textContent = data.sessions.length; $('nav-total').textContent = data.sessions.length; $('session-count').textContent = data.sessions.length;
  for (const value of ['busy','idle','unknown']) $(`stat-${value}`).textContent = data.sessions.filter(r => activity(r) === value).length;
  if (!state.failed) $('updated').textContent = `${data.mode === 'demo' ? 'Demo updated' : 'Observed'} ${time(data.observed_at)}`;
  const records = filteredSessions(); $('result-count').textContent = `${records.length} shown`;
  if (!records.some(r => r._key === state.selected)) state.selected = records[0]?._key || null;
  const body = $('sessions-body'); body.replaceChildren();
  for (const record of records) {
    const row = node('tr',record._key === state.selected ? 'selected' : ''); row.tabIndex = 0; row.setAttribute('aria-label', `${record.provider || 'Unknown agent'}, ${record.project_id || 'Unknown project'}, ${label(activity(record))}. View session details.`);
    const identity = node('td'); const agent = node('div','agent-cell'); const names = node('div'); names.append(node('div','agent-name',record.provider || 'Unknown agent'),node('div','session-id',record.session_id || 'ID not reported')); agent.append(mark(record.provider),names); identity.append(agent);
    const project = node('td'); project.append(node('div','project-name',record.project_id || (record.registration === 'unregistered' ? 'Unregistered' : 'Unknown project')),node('div','registration-hint',record.registration || 'unknown'));
    const status = node('td'); status.append(badge(activity(record)));
    const task = node('td'); task.append(node('div',`task-text ${record.reported_task ? '' : 'muted'}`,record.reported_task || 'Not reported'));
    row.append(identity,project,status,task,node('td','chevron','›'));
    const select = () => {state.selected = record._key; render();}; row.addEventListener('click',select); row.addEventListener('keydown',e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault();select();}}); body.append(row);
  }
  if (!records.length) {
    if (data.sessions.length) renderEmpty('No sessions match these filters', 'Try another project, status or search term.');
    else if (!data.session_sources.some(source => source.status === 'available')) renderEmpty('Live discovery unavailable', 'No available source can confirm live sessions. Check source coverage below; the number of running sessions is unknown.');
    else renderEmpty('No live sessions detected', 'Available sources returned no sessions. Unsupported or unavailable providers are outside this observation; see source coverage below.');
  }
  renderDetails(records.find(r => r._key === state.selected)); renderSources(); renderSaved();
}

function renderDetails(record) {
  $('detail-empty').hidden = Boolean(record); $('detail-content').hidden = !record; const target = $('detail-content'); target.replaceChildren(); if (!record) return;
  const head = node('div','detail-head'); const heading = node('div'); heading.append(node('h2','',record.provider || 'Unknown agent'),badge(activity(record))); head.append(mark(record.provider),heading);
  const task = node('div','detail-task'); task.append(node('div','field-label','Reported task'),node('p','',record.reported_task || 'The source has not reported a task. Busy or idle status does not describe the work being performed.'));
  target.append(head,task,field('Project',record.project_id),field('Working directory',record.project_path),field('Registration',record.registration),node('div','detail-divider'),field('Source',record.source),field('Observed at',time(record.observed_at)),field('Started at',time(record.started_at)),field('Session ID',record.session_id));
}

function renderSources() {
  const target = $('source-list'); target.replaceChildren();
  for (const source of state.data.session_sources) {
    const row = node('div','source-row'); const info = node('div'); let description = 'Source could not be queried';
    if (source.status === 'available') description = `${source.session_count ?? 0} session(s) reported · ${time(source.observed_at)}`;
    if (source.status === 'unsupported') description = 'Live discovery is not supported yet';
    if (source.status === 'error') description = 'Query failed; session count is unknown';
    info.append(node('div','source-label',source.provider),node('div','source-description',description)); row.append(mark(source.provider),info,node('span',`source-state ${source.status}`,{available:'Connected',unsupported:'Not supported',unavailable:'Unavailable',error:'Query error'}[source.status] || 'Unknown')); target.append(row);
  }
}

function renderSaved() {
  const records = state.data.saved_sessions || []; $('saved-count').textContent = records.length; const target = $('saved-list'); target.replaceChildren();
  for (const record of records) {const row = node('div','saved-row'); const title = node('div'); title.append(node('strong','',`${record.agent || 'Unknown agent'} · ${record.project_id || 'Unknown project'}`),node('small','',record.reported_task || 'Task not reported')); row.append(title,node('span','',`Saved · ${time(record.updated_at)}`)); target.append(row);}
  if (!records.length) target.append(node('div','empty-saved','No saved session metadata. Live discovery works independently of stored records.'));
}

for (const button of document.querySelectorAll('[data-status]')) button.addEventListener('click', () => {state.status = button.dataset.status; for (const other of document.querySelectorAll('[data-status]')) {other.classList.toggle('selected',other === button);other.setAttribute('aria-pressed',String(other === button));} render();});
$('project-filter').addEventListener('change',e => {state.project = e.target.value;renderProjects();render();});
$('provider-filter').addEventListener('change',e => {state.provider = e.target.value;render();});
$('search').addEventListener('input',e => {state.search = e.target.value;render();});
$('refresh').addEventListener('click',refresh);
for (const mode of ['live','demo']) $(`mode-${mode}`).addEventListener('click',() => {if (state.pending || state.mode === mode) return;state.mode = mode;state.project = 'all';state.provider = 'all';state.search = '';$('search').value = '';state.status = 'all';clearSnapshot();for (const button of document.querySelectorAll('[data-status]')) {button.classList.toggle('selected',button.dataset.status === 'all');button.setAttribute('aria-pressed',String(button.dataset.status === 'all'));}for (const other of ['live','demo']) {$(`mode-${other}`).classList.toggle('selected',other === mode);$(`mode-${other}`).setAttribute('aria-pressed',String(other === mode));}$('demo-banner').hidden = mode !== 'demo';refresh();});
$('nav-overview').addEventListener('click',() => {window.scrollTo({top:0,behavior:'smooth'});state.project = 'all';if(state.data){renderProjects();render();}});
$('nav-sources').addEventListener('click',() => $('sources').scrollIntoView({behavior:'smooth',block:'center'}));
$('nav-saved').addEventListener('click',() => $('saved').scrollIntoView({behavior:'smooth',block:'center'}));
setInterval(() => {
  if (document.hidden) return;
  if ($('auto-refresh').checked) refresh();
  else if (state.data && !state.pending && !state.failed && Date.now()-new Date(state.data.observed_at).valueOf() > 30000) $('updated').textContent = `Snapshot is stale · ${time(state.data.observed_at)}`;
},15000);
refresh();
