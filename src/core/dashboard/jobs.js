'use strict';
(() => {
  const get = id => document.getElementById(id);
  const view = {data: null, selected: null, parent: null, pending: false, request: null, sending: false};
  const terminal = new Set(['completed','failed','cancelled','interrupted','needs_attention']);
  const make = (tag, text, cls) => {const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (cls) element.className = cls; return element;};
  const stamp = value => value ? new Date(value).toLocaleString() : 'No event yet';
  const demo = () => get('mode-demo').getAttribute('aria-pressed') === 'true';
  const title = status => ({queued:'Queued',running:'Working',completed:'Finished',failed:'Failed',cancelled:'Cancelled',interrupted:'Interrupted',needs_attention:'Needs attention'})[status] || status;
  function options(select, entries) {
    const chosen = select.value;
    select.replaceChildren(...entries.map(([value,label]) => {const option = make('option', label); option.value = value; return option;}));
    if (entries.some(([value]) => value === chosen)) select.value = chosen;
  }
  function detail() {
    const job = view.data?.jobs.find(item => item.id === view.selected);
    const target = get('job-detail'); target.replaceChildren();
    get('job-followup').disabled = !job || !terminal.has(job.status) || !job.session_id || demo();
    get('job-cancel').disabled = !job || terminal.has(job.status) || demo();
    if (!job) {target.append(make('p','Select a task to see its activity, subagents and result.')); return;}
    target.append(make('h3', `${job.provider} · ${job.project_id}`), make('p', job.prompt), make('p', `${title(job.status)} · ${job.activity}`), make('small', `Last event: ${stamp(job.observed_at)}`));
    if (job.workspace) target.append(make('p', `Workspace: ${job.workspace}`, 'job-path'));
    target.append(make('h4','Subagents'));
    const children = Object.values(job.children || {});
    if (!children.length) {
      const coverage = job.subagent_coverage;
      const message = coverage === 'unavailable' ? 'Codex subagent monitoring is unavailable for this task; the count is unknown.' : coverage === 'pending' ? 'Checking Codex child threads…' : 'No subagent events reported for this task.';
      target.append(make('p',message,coverage === 'unavailable' ? 'job-warning' : undefined));
    }
    for (const child of children) {
      const row = make('div', undefined, 'child-job');
      row.append(make('strong', child.task), make('p', `${child.role || 'Subagent'} · ${title(child.status)} · ${child.activity}`));
      if (child.parent_id && job.children[child.parent_id]) row.append(make('small', `Parent: ${job.children[child.parent_id].task}`));
      target.append(row);
    }
    if (job.status === 'needs_attention') target.append(make('p','The agent reported a permission block. This version does not answer permission requests automatically; inspect the result before sending a follow-up.', 'job-warning'));
    if (job.result) target.append(make('h4','Result'), make('pre', job.result, 'job-output'));
    if (job.diagnostic) target.append(make('h4','Runner messages'), make('pre', job.diagnostic, 'job-output'));
  }
  function render() {
    const data = view.data;
    const disabled = !data?.enabled || demo();
    get('job-submit').disabled = disabled || view.sending;
    get('job-availability').textContent = demo() ? 'Demo mode: job controls are disabled.' : data?.enabled ? 'Claude / Codex · one task at a time · tasks keep running when you close this page.' : 'Monitoring only. Start the Hub with --web --control to enable task submission.';
    if (!data) return;
    const focused = document.activeElement?.id;
    const list = get('job-list'); list.replaceChildren();
    if (!data.jobs.length) list.append(make('p','No managed tasks yet. Submit a task to see its work and subagents here.'));
    for (const job of [...data.jobs].reverse()) {
      const button = make('button', undefined, job.id === view.selected ? 'job-card selected' : 'job-card');
      button.type = 'button'; button.id = `job-${job.id}`;
      const count = job.subagent_coverage === 'unavailable' ? 'Subagent count unknown' : `${Object.keys(job.children || {}).length} subagent(s)`;
      button.append(make('strong', `${job.provider} · ${job.project_id}`), make('span', title(job.status)), make('p', job.prompt.slice(0,180)), make('small', `${count} · ${stamp(job.observed_at || job.created_at)}`));
      button.addEventListener('click', () => {view.selected = job.id; render();}); list.append(button);
    }
    detail();
    if (focused?.startsWith('job-') && document.getElementById(focused)) document.getElementById(focused).focus({preventScroll:true});
  }
  async function load() {
    if (view.pending) return;
    view.pending = true;
    const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch('/api/jobs', {cache:'no-store',signal:controller.signal});
      if (!response.ok) throw new Error('Task monitor unavailable. Last displayed state may be stale.');
      const data = await response.json();
      if (!Array.isArray(data.jobs) || !Array.isArray(data.projects)) throw new Error('Invalid task monitor response');
      view.data = data;
      options(get('job-project'), data.projects.map(project => [project,project]));
      options(get('job-provider'), data.providers.filter(provider => provider.cli_status === 'found').map(provider => [provider.provider,provider.provider]));
      get('job-connection').textContent = `Connected · ${new Date().toLocaleTimeString()}`;
      render();
    } catch (error) {get('job-connection').textContent = error.message;}
    finally {clearTimeout(timeout);view.pending = false;}
  }
  async function command(url, payload) {
    if (demo() || !view.data?.enabled) throw new Error('Select Live data with job control enabled');
    const response = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json','X-Guild-Token':view.data.csrf_token},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Command failed');
    return data.job;
  }
  get('job-form').addEventListener('submit', async event => {
    event.preventDefault(); if (view.sending) return;
    const payload = {project_id:get('job-project').value,provider:get('job-provider').value,prompt:get('job-prompt').value,parent_id:view.parent};
    const signature = JSON.stringify(payload);
    if (!view.request || view.request.signature !== signature) view.request = {signature,id:crypto.randomUUID()};
    view.sending = true; render();
    try {
      const job = await command('/api/jobs',{...payload,request_id:view.request.id});
      view.selected = job.id; view.request = null; view.parent = null;
      get('job-prompt').value = ''; get('job-context').textContent = 'New tasks start in a separate worktree from the project’s current commit. Uncommitted changes are not copied.';
      get('job-message').textContent = 'Task accepted into the queue.'; await load();
    } catch (error) {get('job-message').textContent = error.message;}
    finally {view.sending = false;render();}
  });
  get('job-followup').addEventListener('click', () => {
    const job = view.data.jobs.find(item => item.id === view.selected); if (!job) return;
    view.parent = job.id; get('job-project').value = job.project_id; get('job-provider').value = job.provider;
    get('job-context').textContent = 'Follow-up: continues the selected agent session in its existing task worktree.';
    get('job-prompt').focus();
  });
  get('job-new').addEventListener('click', () => {view.parent = null;get('job-context').textContent = 'New task in a separate worktree from the current project commit.';get('job-prompt').focus();});
  get('job-cancel').addEventListener('click', async () => {
    if (!view.selected) return;
    try {await command(`/api/jobs/${view.selected}/cancel`,{});get('job-message').textContent = 'Cancellation requested.';await load();}
    catch (error) {get('job-message').textContent = error.message;}
  });
  for (const mode of ['mode-live','mode-demo']) get(mode).addEventListener('click', () => setTimeout(render,0));
  setInterval(() => {if (!document.hidden) load();},5000);
  load();
})();
