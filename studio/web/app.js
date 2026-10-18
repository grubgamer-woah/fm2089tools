'use strict';
const $ = s => document.querySelector(s);
const PAGE = 200;
const COLORS = {E8F5: '#303030', E8F6: '#ff5a5a', E8F7: '#ffe14d', E8F8: '#6aa8ff', E8F9: null};
const S = {config: null, entries: [], project: {}, speakers: {}, defaultSpeakers: {}, faces: {}, defaultFaces: {}, portraits: [], speakerCounts: {}, font: null, group: 'story', page: 0, current: null, filtered: [], dirty: false, checkTimer: null};

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
    for (const b of ['#build', '#validate', '#import', '#titles']) $(b).disabled = true;
    return;
  }
  $('#rom-missing').hidden = true; $('#app').hidden = false; $('#tabs').hidden = false;
  for (const b of ['#build', '#validate', '#import', '#titles']) $(b).disabled = false;
  $('#base').textContent = 'ROM: ' + S.config.rom;
  const [cat, font] = await Promise.all([api('/api/catalog'), api('/api/font')]);
  S.entries = cat.entries; S.project = cat.project;
  S.speakers = cat.speakers; S.defaultSpeakers = cat.default_speakers;
  S.faces = cat.faces; S.defaultFaces = cat.default_faces; S.portraits = cat.portraits;
  S.speakerCounts = {};
  for (const e of S.entries) if (e.speaker) S.speakerCounts[e.speaker] = (S.speakerCounts[e.speaker] || 0) + 1;
  S.font = font;
  S.font.bitmaps = font.glyphs.map(([w, rb, b64]) => [w, rb, b64 ? Uint8Array.from(atob(b64), c => c.charCodeAt(0)) : null]);
  S.byId = Object.fromEntries(S.entries.map(e => [e.id, e]));
  const params = new URLSearchParams(location.hash.slice(1));
  if (S.config.groups.some(([key]) => key === params.get('group'))) S.group = params.get('group');
  renderTabs(); fillFiles(); applyFilter();
  if (params.get('id') && S.byId[params.get('id')]) select(params.get('id'));
}

function faceOf(jp) { const f = S.faces[jp] || S.defaultFaces[jp] || ''; return f === '-' ? '' : f; }
function faceImg(jp, cls = 'face') {
  const face = faceOf(jp);
  if (face) return `<img class="${cls}" src="/api/portrait?face=${encodeURIComponent(face)}" alt="" title="${esc(face)}">`;
  const letter = (speakerEn(jp) || jp).replace(/«[^»]*»/g, '').charAt(0) || '?';
  return `<span class="${cls} no-face" title="No portrait picked">${esc(letter)}</span>`;
}

function sceneLabel(e) { return `Mission ${e.mission}${e.mission_title ? ' · ' + e.mission_title : ''} · ${e.scene}`; }

function speakerEn(jp) { return S.speakers[jp] || S.defaultSpeakers[jp] || ''; }
function speakerLabel(e) {
  if (!e.speaker) return '';
  const en = speakerEn(e.speaker);
  return en && en !== e.speaker ? `${en} · ${e.speaker}` : e.speaker;
}
// The text as the game shows it: the Studio adds the speaker prefix itself.
function fullText(e, body) {
  if (!e.speaker) return body;
  return (speakerEn(e.speaker) || e.speaker) + ':' + (e.speaker_own_line ? '\n' : ' ') + body;
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
  const first = {};
  for (const e of S.entries) if (e.group === S.group && !first[e.file]) first[e.file] = e;
  const files = Object.keys(first), story = files.some(f => first[f].mission);
  $('#file-label').textContent = story ? 'Mission' : 'File';
  sel.innerHTML = `<option value="">${story ? 'All missions' : 'All files'}</option>` +
    files.map(f => `<option value="${esc(f)}">${esc(first[f].mission ? sceneLabel(first[f]) : f)}</option>`).join('');
  const counts = {};
  for (const e of S.entries) if (e.group === S.group && e.speaker) counts[e.speaker] = (counts[e.speaker] || 0) + 1;
  const names = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  $('#speaker').innerHTML = '<option value="">All speakers</option>' + (names.length ? '<option value="-">No speaker</option>' : '') +
    names.map(n => `<option value="${esc(n)}">${esc(speakerEn(n) && speakerEn(n) !== n ? speakerEn(n) + ' · ' + n : n)} (${counts[n]})</option>`).join('');
  $('#speaker-box').hidden = !names.length;
}

function applyFilter() {
  const q = $('#search').value.trim().toLowerCase();
  const file = $('#file').value, status = $('#status').value, empty = $('#empty').checked, speaker = $('#speaker').value;
  S.filtered = S.entries.filter(e => {
    if (e.group !== S.group && !q) return false;
    if (file && e.file !== file) return false;
    if (speaker === '-' ? e.speaker : speaker && e.speaker !== speaker) return false;
    const p = S.project[e.id] || {};
    if (!empty && !e.jp.trim() && p.en === undefined) return false;
    if (status === 'todo' && p.en !== undefined) return false;
    if (status === 'translated' && p.en === undefined) return false;
    if (status === 'done' && !p.done) return false;
    if (status === 'notdone' && (p.en === undefined || p.done)) return false;
    if (status === 'noted' && !p.note) return false;
    if (q) return (e.id + '\n' + e.jp + '\n' + (p.en || '') + '\n' + (p.note || '') + '\n' + (e.speaker ? speakerEn(e.speaker) : '')).toLowerCase().includes(q);
    return true;
  });
  const pages = Math.max(1, Math.ceil(S.filtered.length / PAGE));
  S.page = Math.min(S.page, pages - 1);
  renderRows();
}

function renderRows() {
  const rows = $('#rows'); rows.innerHTML = '';
  const slice = S.filtered.slice(S.page * PAGE, (S.page + 1) * PAGE);
  let scene = null;
  for (const e of slice) {
    // A heading wherever a mission's base or battle part starts, as the game plays them
    if (e.mission && !$('#search').value.trim() && e.file !== scene) {
      const h = document.createElement('div'); h.className = 'scene-head'; h.textContent = sceneLabel(e);
      rows.appendChild(h); scene = e.file;
    }
    rows.appendChild(rowEl(e));
  }
  const pages = Math.max(1, Math.ceil(S.filtered.length / PAGE));
  $('#count').textContent = `${fmt(S.filtered.length)} entries` + ($('#search').value.trim() ? ' (all groups)' : '');
  $('#page').textContent = `Page ${S.page + 1} of ${pages}`;
  $('#prev-page').disabled = S.page === 0; $('#next-page').disabled = S.page >= pages - 1;
}

function rowEl(e) {
  const p = S.project[e.id] || {};
  const b = document.createElement('button');
  b.className = 'row' + (e.speaker ? ' has-face' : '') + (S.current === e.id ? ' active' : '');
  b.dataset.id = e.id;
  const badges = (p.done ? '<span class="badge done">done</span> ' : '') + (p.note ? '<span class="badge">note</span>' : '');
  b.innerHTML = (e.speaker ? faceImg(e.speaker) + '<div class="row-text">' : '') + `<div class="meta"><span>${esc(e.file.replace('MsgLabels_', ''))} #${e.index}</span><span>${badges}</span></div>` +
    (e.speaker ? `<div class="speaker">${esc(speakerLabel(e))}</div>` : '') +
    `<div class="jp">${esc(e.speaker ? e.body : e.jp) || '<i>(empty)</i>'}</div>` +
    `<div class="en ${p.en === undefined ? 'none' : ''}">${p.en === undefined ? 'Not translated' : esc(p.en) || '(blank)'}</div>` +
    (e.speaker ? '</div>' : '');
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
  const tags = [...new Set(e.body.match(/«(?!g:)[^»]+»/g) || [])];
  $('#editor').innerHTML = `
    <h2>${esc(e.id)}</h2>
    <div class="sub">${esc(e.file)} · string ${e.index} · ${e.lines} line(s) · widest Japanese line ${e.jp_width} px (file max ${e.file_width} px)</div>
    ${e.art ? `<div class="sub art">${esc(e.art)}</div>` : ''}
    ${e.speaker ? `<div class="speaker-bar"><button id="face-pick" class="face-button" title="Pick this speaker's portrait">${faceImg(e.speaker, 'face big')}</button><span>Speaker <b>${esc(e.speaker)}</b> · ${fmt(S.speakerCounts[e.speaker])} lines</span>
      <label class="inline">English name <input id="speaker-en" value="${esc(S.speakers[e.speaker] || '')}" placeholder="${esc(S.defaultSpeakers[e.speaker] || 'Not translated yet')}"></label>
      <button id="speaker-save" title="Changes this name on every line this speaker says">Save name everywhere</button></div>` : ''}
    <label>Japanese${e.speaker ? ' (the speaker name is added automatically)' : ''}</label><div class="jp-box">${jpHtml(e.body) || '<i>(empty)</i>'}</div>
    <div class="field"><label for="en">English</label>
      <textarea id="en" spellcheck="true" placeholder="Type the English text. Enter = new line in game.">${esc(p.en || '')}</textarea>
      ${tags.length ? `<div class="codes"><span class="widths">Insert code:</span>${tags.map(t => `<button data-insert="${esc(t)}" title="${esc(S.config.controls[t.slice(1, 5).toUpperCase()] || '')}">${esc(t)}</button>`).join('')}</div>` : ''}
      <div class="preview-wrap"><canvas id="preview"></canvas></div>
      <div class="widths" id="widths"></div>
      <ul class="msgs" id="msgs"></ul>
    </div>
    <div class="field"><label for="note">Note (not put in the game)</label><textarea id="note" class="note" rows="2">${esc(p.note || '')}</textarea></div>
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
  if (e.speaker) {
    $('#speaker-save').onclick = () => saveSpeaker(e.speaker, $('#speaker-en').value);
    $('#face-pick').onclick = () => showFacePicker(e.speaker);
    $('#speaker-en').onkeydown = ev => { if (ev.key === 'Enter') { ev.preventDefault(); saveSpeaker(e.speaker, $('#speaker-en').value); } };
  }
  $('#copy-jp').onclick = () => { en.value = e.body; S.dirty = true; scheduleCheck(); en.focus(); };
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
  const shown = text ? fullText(S.byId[id], text) : S.byId[id].jp;
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

async function saveSpeaker(jp, en) {
  const r = await api('/api/speaker', {jp, en});
  if (!r.ok) { flash('Name not saved: ' + r.errors.join(', ')); return false; }
  S.speakers = r.speakers;
  flash(`Speaker name saved for ${fmt(S.speakerCounts[jp])} lines`);
  const keep = $('#speaker').value; fillFiles(); $('#speaker').value = keep;
  renderRows(); if (S.current) { const pending = $('#en') && $('#en').value; renderEditor(); if (pending !== undefined && S.dirty) $('#en').value = pending; scheduleCheck(0); }
  return true;
}

async function saveFace(jp, face) {
  const r = await api('/api/speaker', {jp, face});
  if (!r.ok) { flash('Portrait not saved: ' + r.errors.join(', ')); return; }
  S.faces = r.faces;
  flash(`Portrait saved for ${fmt(S.speakerCounts[jp])} lines`);
  renderRows();
  if (S.current && S.byId[S.current].speaker === jp) {
    const pending = $('#en').value, note = $('#note').value, dirty = S.dirty;
    renderEditor(); if (dirty) { $('#en').value = pending; $('#note').value = note; S.dirty = true; scheduleCheck(0); }
  }
}

function showFacePicker(jp, back) {
  const current = faceOf(jp);
  showJob(`<h3>Portrait for ${esc(speakerEn(jp) && speakerEn(jp) !== jp ? speakerEn(jp) + ' · ' + jp : jp)}</h3>
    <p>Pick the face shown next to this speaker's lines. It is only shown in the Studio and does not change the game.</p>
    <div class="face-grid">${S.portraits.map(f => `<button data-face="${esc(f)}" class="${f === current ? 'picked' : ''}" title="${esc(f)}"><img class="face big" src="/api/portrait?face=${encodeURIComponent(f)}" alt=""><small>${esc(f)}</small></button>`).join('')}
      <button data-face="" class="${current ? '' : 'picked'}"><span class="face big no-face">–</span><small>None</small></button></div>
    ${back ? '<p><button id="face-back">Back to speakers</button></p>' : ''}`);
  document.querySelectorAll('[data-face]').forEach(b => b.onclick = async () => {
    // The built-in match needs no override; "-" means no portrait for this speaker
    const face = b.dataset.face || '-';
    await saveFace(jp, face === (S.defaultFaces[jp] || '-') ? '' : face);
    if (back) back(); else $('#job').hidden = true;
  });
  if (back) $('#face-back').onclick = back;
}

function showSpeakers() {
  const names = Object.keys(S.speakerCounts).sort((a, b) => S.speakerCounts[b] - S.speakerCounts[a]);
  const done = names.filter(n => speakerEn(n)).length;
  showJob(`<h3>Speakers</h3><p>${done} of ${names.length} speaker names have English. Each name is used on every line that speaker says.</p>
    <div class="speaker-table">${names.map(n => `<div class="speaker-cell"><button class="face-button" data-pick="${esc(n)}" title="Pick a portrait">${faceImg(n)}</button>
    <label class="inline"><span>${esc(n)} <small>${fmt(S.speakerCounts[n])}</small></span>
    <input data-speaker="${esc(n)}" value="${esc(S.speakers[n] || '')}" placeholder="${esc(S.defaultSpeakers[n] || '')}"></label></div>`).join('')}</div>`);
  document.querySelectorAll('[data-speaker]').forEach(i => i.onchange = () => saveSpeaker(i.dataset.speaker, i.value));
  document.querySelectorAll('[data-pick]').forEach(b => b.onclick = () => showFacePicker(b.dataset.pick, showSpeakers));
}

// Mission title screens: the Japanese picture next to the English one as the game will show it
async function showTitles(note = '') {
  const r = await api('/api/titles');
  const done = r.titles.filter(t => t.english).length;
  const stamp = Date.now();
  showJob(`<h3>Mission titles</h3>
    <p>${done} of ${r.titles.length} title screens have an English picture. Pictures are 256×256 or 256×192 PNGs (the DS shows the top 256×192);
    the right-hand picture is how the game will show it (16-color tiles). Pick several files at once: <code>m10.png</code> or <code>mtittle_bg_10…png</code> goes to title 10.</p>
    <p><button id="title-add" class="primary">Add pictures…</button> ${note}</p>
    <div class="title-grid">${r.titles.map(t => `<div class="title-cell">
      <div class="title-head"><b>Title ${String(t.number).padStart(2, '0')}</b><span>${t.english ? 'English' : '<span class="muted">Japanese kept</span>'}</span></div>
      <div class="title-pics"><img src="/api/title.png?name=${t.name}&kind=jp" alt="Japanese title ${t.number}" loading="lazy">
      ${t.english ? `<img src="/api/title.png?name=${t.name}&kind=en&t=${stamp}" alt="English title ${t.number}" loading="lazy">` : '<span class="title-empty">No English picture</span>'}</div>
      <div class="buttons"><button data-title-pick="${t.name}">${t.english ? 'Replace…' : 'Add…'}</button>${t.english ? `<button data-title-remove="${t.name}">Remove</button>` : ''}</div>
    </div>`).join('')}</div>`);
  const input = $('#title-files');
  $('#title-add').onclick = () => { input.dataset.name = ''; input.multiple = true; input.click(); };
  document.querySelectorAll('[data-title-pick]').forEach(b => b.onclick = () => { input.dataset.name = b.dataset.titlePick; input.multiple = false; input.click(); });
  document.querySelectorAll('[data-title-remove]').forEach(b => b.onclick = async () => {
    if (!confirm('Remove this English picture? The game will show the Japanese title again.')) return;
    await fetch('/api/title?name=' + b.dataset.titleRemove, {method: 'POST'});
    showTitles('Removed.');
  });
}

function titleNumber(fileName) {
  const m = fileName.match(/(?:mtittle_bg_|^m|\D)(\d{1,2})(?!\d)/i);
  return m ? +m[1] : null;
}

async function uploadTitles(files, name) {
  const names = (await api('/api/titles')).titles.map(t => t.name);
  const done = [], failed = [];
  for (const f of files) {
    const target = name || 'mtittle_bg_' + String(titleNumber(f.name)).padStart(2, '0');
    if (!names.includes(target)) { failed.push(`${f.name}: no title screen with that number`); continue; }
    flash(`Converting ${f.name}…`);
    const r = await (await fetch('/api/title?name=' + target, {method: 'POST', headers: {'Content-Type': 'image/png'}, body: f})).json();
    if (r.ok) done.push(f.name); else failed.push(`${f.name}: ${r.error}`);
  }
  showTitles(`${done.length} picture${done.length === 1 ? '' : 's'} added.` +
    (failed.length ? `<span class="bad"> Not added: ${failed.map(esc).join('; ')}</span>` : ''));
}

async function restartStudio() {
  const building = (await api('/api/job')).running;
  if (!confirm(building ? 'A build is running and will be stopped. Restart the Studio anyway?' : 'Restart the Studio? Your saved work is kept.')) return;
  if (S.current && S.dirty) await save(false);
  const before = S.config && S.config.started;
  flash('Restarting…');
  try { await api('/api/restart', {}); } catch (err) { /* the old server may close before it answers */ }
  for (let i = 0; i < 120; i++) {
    await new Promise(r => setTimeout(r, 500));
    try {
      const c = await (await fetch('/api/config', {cache: 'no-store'})).json();
      if (c.started !== before) { location.reload(); return; }
    } catch (err) { /* still starting */ }
  }
  flash('The Studio did not come back. Double-click Launch Studio.pyw to start it.');
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
            ${fmt(r.translated)} translated strings and ${fmt(r.titles || 0)} mission titles in ${r.files.length} files.</p>
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
  const cat = await api('/api/catalog'); S.project = cat.project; S.speakers = cat.speakers;
  renderTabs(); applyFilter(); if (S.current) renderEditor();
  showJob(`<h3>Import finished</h3><p>${fmt(r.imported)} English strings imported.${r.unknown_count ? ` ${r.unknown_count} rows had unknown IDs (for example ${esc(r.unknown.slice(0, 5).join(', '))}).` : ''}</p>`);
}

$('#search').oninput = () => { S.page = 0; applyFilter(); };
$('#file').onchange = $('#status').onchange = $('#empty').onchange = () => { S.page = 0; applyFilter(); };
$('#prev-page').onclick = () => { S.page--; renderRows(); $('#rows').scrollTop = 0; };
$('#next-page').onclick = () => { S.page++; renderRows(); $('#rows').scrollTop = 0; };
$('#validate').onclick = validate;
$('#restart').onclick = restartStudio;
$('#speakers').onclick = showSpeakers;
$('#titles').onclick = () => showTitles();
$('#title-files').onchange = ev => { const files = [...ev.target.files]; if (files.length) uploadTitles(files, ev.target.dataset.name); ev.target.value = ''; };
$('#speaker').onchange = () => { S.page = 0; applyFilter(); };
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
