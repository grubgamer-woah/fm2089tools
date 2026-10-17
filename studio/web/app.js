'use strict';
const $ = s => document.querySelector(s);
const PAGE = 200;
const COLORS = {E8F5: '#303030', E8F6: '#ff5a5a', E8F7: '#ffe14d', E8F8: '#6aa8ff', E8F9: null};
const S = {config: null, entries: [], project: {}, font: null, group: 'story', page: 0, current: null, filtered: [], dirty: false, checkTimer: null};

async function api(path, body) {
  const opts = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: typeof body === 'string' ? body : JSON.stringify(body)};
  const r = await fetch(path, opts);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
const esc = s => s.replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const fmt = n => n.toLocaleString('en-US');
function flash(text) { $('#saved').textContent = text; clearTimeout(flash.t); flash.t = setTimeout(() => $('#saved').textContent = '', 4000); }

async function start() {
  S.config = await api('/api/config');
  $('#project-path').textContent = S.config.project;
  if (!S.config.rom) {
    $('#rom-missing').hidden = false; $('#app').hidden = true; $('#tabs').hidden = true;
    $('#rom-problem').textContent = S.config.rom_problem;
    $('#base').textContent = 'No ROM loaded';
    for (const b of ['#build', '#validate', '#import']) $(b).disabled = true;
    return;
  }
  $('#rom-missing').hidden = true; $('#app').hidden = false; $('#tabs').hidden = false;
  for (const b of ['#build', '#validate', '#import']) $(b).disabled = false;
  $('#base').textContent = 'ROM: ' + S.config.rom;
  const [cat, font] = await Promise.all([api('/api/catalog'), api('/api/font')]);
  S.entries = cat.entries; S.project = cat.project;
  S.font = font;
  S.font.bitmaps = font.glyphs.map(([w, rb, b64]) => [w, rb, b64 ? Uint8Array.from(atob(b64), c => c.charCodeAt(0)) : null]);
  S.byId = Object.fromEntries(S.entries.map(e => [e.id, e]));
  const params = new URLSearchParams(location.hash.slice(1));
  if (params.get('group')) S.group = params.get('group');
  renderTabs(); fillFiles(); applyFilter();
  if (params.get('id') && S.byId[params.get('id')]) select(params.get('id'));
}

function translated(e) { return S.project[e.id] && S.project[e.id].en !== undefined; }
function progress() {
  const t = S.entries.filter(translated).length;
  $('#progress').textContent = `${fmt(t)} of ${fmt(S.entries.length)} strings translated (${(100 * t / S.entries.length).toFixed(1)}%)`;
}

function renderTabs() {
  const nav = $('#tabs'); nav.innerHTML = '';
  for (const [key, label] of S.config.groups) {
    const all = S.entries.filter(e => e.group === key);
    const done = all.filter(translated).length;
    const b = document.createElement('button');
    b.className = key === S.group ? 'active' : '';
    b.innerHTML = `${esc(label)}<small>${fmt(done)}/${fmt(all.length)}</small>`;
    b.onclick = () => { S.group = key; S.page = 0; $('#file').value = ''; renderTabs(); fillFiles(); applyFilter(); };
    nav.appendChild(b);
  }
  progress();
}

function fillFiles() {
  const sel = $('#file');
  const files = [...new Set(S.entries.filter(e => e.group === S.group).map(e => e.file))];
  sel.innerHTML = '<option value="">All files</option>' + files.map(f => `<option>${esc(f)}</option>`).join('');
}

function applyFilter() {
  const q = $('#search').value.trim().toLowerCase();
  const file = $('#file').value, status = $('#status').value, empty = $('#empty').checked;
  S.filtered = S.entries.filter(e => {
    if (e.group !== S.group && !q) return false;
    if (file && e.file !== file) return false;
    const p = S.project[e.id] || {};
    if (!empty && !e.jp.trim() && p.en === undefined) return false;
    if (status === 'todo' && p.en !== undefined) return false;
    if (status === 'translated' && p.en === undefined) return false;
    if (status === 'done' && !p.done) return false;
    if (status === 'notdone' && (p.en === undefined || p.done)) return false;
    if (status === 'noted' && !p.note) return false;
    if (q) return (e.id + '\n' + e.jp + '\n' + (p.en || '') + '\n' + (p.note || '')).toLowerCase().includes(q);
    return true;
  });
  const pages = Math.max(1, Math.ceil(S.filtered.length / PAGE));
  S.page = Math.min(S.page, pages - 1);
  renderRows();
}

function renderRows() {
  const rows = $('#rows'); rows.innerHTML = '';
  const slice = S.filtered.slice(S.page * PAGE, (S.page + 1) * PAGE);
  for (const e of slice) rows.appendChild(rowEl(e));
  const pages = Math.max(1, Math.ceil(S.filtered.length / PAGE));
  $('#count').textContent = `${fmt(S.filtered.length)} entries` + ($('#search').value.trim() ? ' (all groups)' : '');
  $('#page').textContent = `Page ${S.page + 1} of ${pages}`;
  $('#prev-page').disabled = S.page === 0; $('#next-page').disabled = S.page >= pages - 1;
}

function rowEl(e) {
  const p = S.project[e.id] || {};
  const b = document.createElement('button');
  b.className = 'row' + (S.current === e.id ? ' active' : '');
  b.dataset.id = e.id;
  const badges = (p.done ? '<span class="badge done">done</span> ' : '') + (p.note ? '<span class="badge">note</span>' : '');
  b.innerHTML = `<div class="meta"><span>${esc(e.file.replace('MsgLabels_', ''))} #${e.index}</span><span>${badges}</span></div>` +
    `<div class="jp">${esc(e.jp) || '<i>(empty)</i>'}</div>` +
    `<div class="en ${p.en === undefined ? 'none' : ''}">${p.en === undefined ? 'Not translated' : esc(p.en) || '(blank)'}</div>`;
  b.onclick = () => select(e.id);
  return b;
}

function refreshRow(id) {
  const old = document.querySelector(`.row[data-id="${CSS.escape(id)}"]`);
  if (old) old.replaceWith(rowEl(S.byId[id]));
}

async function select(id) {
  if (S.dirty && S.current && S.current !== id) await save(false);
  S.current = id; S.dirty = false;
  document.querySelectorAll('.row.active').forEach(r => r.classList.remove('active'));
  const row = document.querySelector(`.row[data-id="${CSS.escape(id)}"]`);
  if (row) row.classList.add('active');
  history.replaceState(null, '', `#group=${S.group}&id=${encodeURIComponent(id)}`);
  renderEditor();
}

function jpHtml(text) {
  return esc(text).replace(/«([^»]+)»/g, (m, body) => {
    const code = body.split(':')[0].toUpperCase();
    const title = S.config.controls[code] || (code.startsWith('G') ? 'Glyph with no known character' : 'Unknown control code');
    return `<span class="tag" data-tag="${esc(m)}" title="${esc(title)} — click to insert">${esc(m)}</span>`;
  });
}

function renderEditor() {
  const e = S.byId[S.current]; const p = S.project[e.id] || {};
  const tags = [...new Set(e.jp.match(/«(?!g:)[^»]+»/g) || [])];
  $('#editor').innerHTML = `
    <h2>${esc(e.id)}</h2>
    <div class="sub">${esc(e.file)} · string ${e.index} · ${e.lines} line(s) · widest Japanese line ${e.jp_width} px (file max ${e.file_width} px)</div>
    <label>Japanese</label><div class="jp-box">${jpHtml(e.jp) || '<i>(empty)</i>'}</div>
    <div class="field"><label for="en">English</label>
      <textarea id="en" spellcheck="true" placeholder="Type the English text. Enter = new line in game.">${esc(p.en || '')}</textarea>
      ${tags.length ? `<div class="codes"><span class="widths">Insert code:</span>${tags.map(t => `<button data-insert="${esc(t)}" title="${esc(S.config.controls[t.slice(1, 5).toUpperCase()] || '')}">${esc(t)}</button>`).join('')}</div>` : ''}
      <div class="preview-wrap"><canvas id="preview"></canvas></div>
      <div class="widths" id="widths"></div>
      <ul class="msgs" id="msgs"></ul>
    </div>
    <div class="field"><label for="note">Note (not put in the game)</label><input id="note" value="${esc(p.note || '')}"></div>
    <div class="buttons">
      <button id="save" class="primary" title="Ctrl+Enter">Save entry</button>
      <label class="check"><input id="done" type="checkbox" ${p.done ? 'checked' : ''}> Done</label>
      <button id="copy-jp" title="Copy the Japanese (with its codes) into the English box">Copy Japanese</button>
      <button id="clear" title="Remove the English so the game keeps the Japanese">Use Japanese</button>
      <span class="spacer"></span>
      <button id="prev" title="Alt+Up">◀ Previous</button><button id="next" title="Alt+Down">Next ▶</button>
    </div>`;
  const en = $('#en');
  en.oninput = () => { S.dirty = true; scheduleCheck(); };
  $('#note').oninput = () => { S.dirty = true; };
  $('#done').onchange = () => save(true);
  $('#save').onclick = () => save(true);
  $('#clear').onclick = async () => { en.value = ''; S.dirty = true; await save(true, true); };
  $('#copy-jp').onclick = () => { en.value = e.jp; S.dirty = true; scheduleCheck(); en.focus(); };
  $('#prev').onclick = () => step(-1); $('#next').onclick = () => step(1);
  document.querySelectorAll('[data-insert], .tag').forEach(b => b.onclick = () => insert(b.dataset.insert || b.dataset.tag));
  scheduleCheck(0);
}

function insert(text) {
  const en = $('#en'); const [a, b] = [en.selectionStart, en.selectionEnd];
  en.value = en.value.slice(0, a) + text + en.value.slice(b);
  en.selectionStart = en.selectionEnd = a + text.length; en.focus();
  S.dirty = true; scheduleCheck();
}

function step(d) {
  const i = S.filtered.findIndex(e => e.id === S.current) + d;
  if (i < 0 || i >= S.filtered.length) return;
  const page = Math.floor(i / PAGE);
  if (page !== S.page) { S.page = page; renderRows(); }
  select(S.filtered[i].id).then(() => {
    const row = document.querySelector(`.row[data-id="${CSS.escape(S.filtered[i].id)}"]`);
    if (row) row.scrollIntoView({block: 'nearest'});
    $('#en').focus();
  });
}

function scheduleCheck(delay = 250) {
  clearTimeout(S.checkTimer);
  S.checkTimer = setTimeout(check, delay);
}

async function check() {
  const id = S.current; const text = $('#en').value;
  const shown = text || S.byId[id].jp;
  drawPreview(shown, S.byId[id]);
  if (!text) { $('#msgs').innerHTML = ''; $('#widths').textContent = 'Preview shows the Japanese because there is no English yet.'; return; }
  const r = await api('/api/check', {id, en: text});
  if (id !== S.current) return;
  $('#widths').textContent = `Line widths: ${r.widths.join(' / ')} px · warning above ${r.limit} px · screen is ${S.config.screen_width} px`;
  $('#msgs').innerHTML = r.errors.map(m => `<li class="error">✖ ${esc(m)}</li>`).join('') + r.warnings.map(m => `<li class="warning">⚠ ${esc(m)}</li>`).join('');
}

function glyphFor(ch) { const g = S.font.lookup[ch]; return g === undefined ? null : g; }

function layout(text) {
  // returns lines of [glyph | {var:true}] with colours
  const lines = [[]]; let color = null;
  const re = /«([^»]*)»|\n|[\s\S]/g; let m;
  while ((m = re.exec(text))) {
    if (m[0] === '\n') { lines.push([]); continue; }
    if (m[1] !== undefined) {
      const body = m[1].toUpperCase();
      if (body.startsWith('G:')) { lines[lines.length - 1].push({g: parseInt(body.slice(2), 16), color}); continue; }
      const code = body.split(':')[0];
      if (code in COLORS) { color = COLORS[code]; continue; }
      if (code === 'E801') { lines[lines.length - 1].push({v: true}); continue; }
      continue;
    }
    const g = glyphFor(m[0]);
    lines[lines.length - 1].push(g === null ? {bad: true} : {g, color});
  }
  return lines;
}

function drawPreview(text, e) {
  const cv = $('#preview'); const ctx = cv.getContext('2d');
  const H = S.font.height, LH = H + 4, SC = 2, W = S.config.screen_width;
  const lines = layout(text);
  const widest = Math.max(W, ...lines.map(l => l.reduce((x, t) => x + (t.v ? 31 : t.bad ? 7 : ((S.font.bitmaps[t.g] || [0])[0] ? S.font.bitmaps[t.g][0] + S.font.spacing : 0)), 0)));
  cv.width = (widest + 8) * SC; cv.height = (lines.length * LH + 8) * SC;
  ctx.fillStyle = '#0b1020'; ctx.fillRect(0, 0, cv.width, cv.height);
  const limit = Math.max(e.file_width, e.jp_width);
  ctx.fillStyle = '#2b3550'; ctx.fillRect((4 + limit) * SC, 0, SC, cv.height);
  ctx.fillStyle = '#5a2b2b'; ctx.fillRect((4 + W) * SC, 0, SC, cv.height);
  const shades = [null, '#ffffff', '#9aa6a6', '#56615f'];  // 1 is the letter ink
  lines.forEach((line, li) => {
    let x = 4; const y = 4 + li * LH;
    for (const t of line) {
      if (t.v) { ctx.fillStyle = '#4b6a8a'; ctx.fillRect(x * SC, y * SC, 30 * SC, H * SC); x += 31; continue; }
      if (t.bad) { ctx.fillStyle = '#ff5a5a'; ctx.fillRect(x * SC, y * SC, 6 * SC, H * SC); x += 7; continue; }
      const [w, rb, px] = S.font.bitmaps[t.g] || [0, 0, null];
      if (px) for (let yy = 0; yy < H; yy++) for (let xx = 0; xx < w; xx++) {
        const v = (px[yy * rb + (xx >> 2)] >> ((xx & 3) * 2)) & 3;
        if (!v) continue;
        ctx.fillStyle = t.color && v === 1 ? t.color : shades[v];
        ctx.fillRect((x + xx) * SC, (y + yy) * SC, SC, SC);
      }
      x += w ? w + S.font.spacing : 0;
    }
  });
}

async function save(explicit, clearing = false) {
  const id = S.current; const en = $('#en').value; const note = $('#note').value; const done = $('#done').checked;
  const body = {id, note, done, en: clearing ? '' : (en === '' ? '' : en)};
  if (!clearing && en === '' && (S.project[id] || {}).en === undefined) delete body.en;
  const r = await api('/api/entry', body);
  if (!r.ok) {
    flash('Not saved: fix the errors first');
    $('#msgs').innerHTML = r.errors.map(m => `<li class="error">✖ ${esc(m)}</li>`).join('');
    return false;
  }
  if (Object.keys(r.entry).length) S.project[id] = r.entry; else delete S.project[id];
  S.dirty = false;
  flash(explicit ? 'Saved' : 'Saved previous entry');
  refreshRow(id); renderTabsCounts();
  return true;
}

function renderTabsCounts() {
  const buttons = $('#tabs').querySelectorAll('button');
  S.config.groups.forEach(([key], i) => {
    const all = S.entries.filter(e => e.group === key);
    buttons[i].querySelector('small').textContent = `${fmt(all.filter(translated).length)}/${fmt(all.length)}`;
  });
  progress();
}

function showJob(html) { const j = $('#job'); j.hidden = false; j.innerHTML = html; j.scrollIntoView({block: 'nearest'}); }
function problemList(problems) {
  if (!problems.length) return '<p class="ok">No problems found.</p>';
  return '<ul>' + problems.slice(0, 300).map(p => `<li class="${p.level === 'error' ? 'bad' : ''}"><a href="#" data-goto="${esc(p.id)}">${esc(p.id)}</a>: ${esc(p.message)}</li>`).join('') + '</ul>' +
    (problems.length > 300 ? `<p>…and ${problems.length - 300} more.</p>` : '');
}
function wireGoto() {
  document.querySelectorAll('[data-goto]').forEach(a => a.onclick = ev => {
    ev.preventDefault(); const e = S.byId[a.dataset.goto];
    S.group = e.group; $('#search').value = ''; $('#file').value = ''; renderTabs(); fillFiles(); applyFilter();
    const i = S.filtered.findIndex(x => x.id === e.id); if (i >= 0) { S.page = Math.floor(i / PAGE); renderRows(); }
    select(e.id);
  });
}

async function validate() {
  if (S.dirty) await save(true);
  const r = await api('/api/validate', {});
  const errors = r.problems.filter(p => p.level === 'error').length;
  showJob(`<h3>Validation</h3><p>${errors} errors, ${r.problems.length - errors} warnings.</p>${problemList(r.problems)}`);
  wireGoto();
}

async function build() {
  if (S.dirty && !(await save(true))) return;
  $('#build').disabled = true;
  try {
    await api('/api/build', {});
    showJob('<h3>Building…</h3><pre id="joblog"></pre>');
    for (;;) {
      await new Promise(r => setTimeout(r, 500));
      const j = await api('/api/job');
      const log = $('#joblog'); if (log) log.textContent = j.log.join('\n');
      if (!j.running) {
        const r = j.result;
        if (r.ok) {
          showJob(`<h3 class="ok">Build finished</h3>
            <p>Patch: <code>${esc(r.patch)}</code> (${fmt(r.patch_size)} bytes)<br>Patched ROM: <code>${esc(r.rom)}</code><br>
            ${fmt(r.translated)} translated strings in ${r.files.length} text files.</p>
            <button id="open-build">Open build folder</button>${r.problems.length ? `<p>${r.problems.length} warnings:</p>` + problemList(r.problems) : ''}`);
          $('#open-build').onclick = () => api('/api/open', {path: r.folder});
          wireGoto();
        } else {
          showJob(`<h3 class="bad">Build stopped</h3><p>${esc(r.message || '')}</p>${r.problems ? problemList(r.problems) : ''}${r.trace ? `<pre>${esc(r.trace)}</pre>` : ''}`);
          wireGoto();
        }
        break;
      }
    }
  } catch (err) { showJob(`<h3 class="bad">Build failed</h3><p>${esc(err.message)}</p>`); }
  $('#build').disabled = false;
}

async function importFile(file) {
  const text = await file.text();
  const r = await api('/api/import', text);
  const cat = await api('/api/catalog'); S.project = cat.project;
  renderTabs(); applyFilter(); if (S.current) renderEditor();
  showJob(`<h3>Import finished</h3><p>${fmt(r.imported)} English strings imported.${r.unknown_count ? ` ${r.unknown_count} rows had unknown IDs (for example ${esc(r.unknown.slice(0, 5).join(', '))}).` : ''}</p>`);
}

$('#search').oninput = () => { S.page = 0; applyFilter(); };
$('#file').onchange = $('#status').onchange = $('#empty').onchange = () => { S.page = 0; applyFilter(); };
$('#prev-page').onclick = () => { S.page--; renderRows(); $('#rows').scrollTop = 0; };
$('#next-page').onclick = () => { S.page++; renderRows(); $('#rows').scrollTop = 0; };
$('#validate').onclick = validate;
$('#build').onclick = build;
$('#import').onclick = () => $('#import-file').click();
$('#import-file').onchange = ev => { if (ev.target.files[0]) importFile(ev.target.files[0]); ev.target.value = ''; };
$('#retry').onclick = async () => { await api('/api/reload', {}); start(); };
document.addEventListener('keydown', ev => {
  if (!S.current) return;
  if (ev.ctrlKey && ev.key === 'Enter') { ev.preventDefault(); save(true); }
  if (ev.altKey && ev.key === 'ArrowDown') { ev.preventDefault(); step(1); }
  if (ev.altKey && ev.key === 'ArrowUp') { ev.preventDefault(); step(-1); }
});
window.addEventListener('beforeunload', ev => { if (S.dirty) { ev.preventDefault(); ev.returnValue = ''; } });
start().catch(err => { $('#base').textContent = 'Error: ' + err.message; });
