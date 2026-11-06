// FM2089 Online Script: the team edits the script together in the browser; the desktop Studio builds the patch.
// Data (Firestore): meta/access (team list), meta/script (pack info, font widths), meta/speakers,
// files/{file} (one per game text file: its lines, English, notes, who edited what), history, presence.
import * as fb from './firebase.js';
import { firebaseConfig } from './firebase-config.js';

const PAGE = 200;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fmt = n => Number(n).toLocaleString('en-US');
const when = t => { const d = t?.toDate ? t.toDate() : t ? new Date(t) : null; return d ? d.toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}) : 'just now'; };
const S = {files: {}, entries: [], byId: {}, speakers: {en: {}, seed: {}}, presence: {}, group: 'story', page: 0, filtered: [], current: null,
           sync: {}, timers: {}, start: {}, conflict: {}, loaded: false};

const params = new URLSearchParams(location.search);
const app = fb.initializeApp(firebaseConfig);
const auth = fb.getAuth(app);
const emulator = params.has('emulator');
const db = emulator ? fb.initializeFirestore(app, {})
  : fb.initializeFirestore(app, {localCache: fb.persistentLocalCache({tabManager: fb.persistentMultipleTabManager()})});
if (emulator) {
  fb.connectAuthEmulator(auth, `http://${location.hostname}:9099`, {disableWarnings: true});
  fb.connectFirestoreEmulator(db, location.hostname, 8080);
}
const ref = (...path) => fb.doc(db, ...path);

// ---------- signing in and the team list ----------

function gate(html) {
  $('#gate').innerHTML = html; $('#gate').hidden = false;
  $('#app').hidden = true; $('#tabs').hidden = true;
}

if (firebaseConfig.projectId === 'PASTE-HERE') {
  gate('<h2>Not set up yet</h2><p>Paste your Firebase project\'s settings into <code>public/firebase-config.js</code>, then deploy again (see online/README.md).</p>');
} else {
  fb.onAuthStateChanged(auth, user => user ? signedIn(user) : signedOut());
}

function signedOut() {
  $('#actions').hidden = true; $('#base').textContent = 'Not signed in';
  gate(`<h2>Sign in</h2><p>The script is only open to the translation team. Sign in with the Google account the team admin added.</p>
    <div class="gate-buttons"><button id="signin" class="primary">Sign in with Google</button></div>`);
  $('#signin').onclick = () => (emulator && params.get('as') ? emulatorSignIn(params.get('as'))
    : fb.signInWithPopup(auth, new fb.GoogleAuthProvider())).catch(err => alert('Sign-in failed: ' + err.message));
}

// Testing only (?emulator&as=name@example.com with the Firebase emulators running): a made-up Google account
function emulatorSignIn(email) {
  const token = JSON.stringify({sub: email, email, email_verified: true, name: email.split('@')[0]});
  return fb.signInWithCredential(auth, fb.GoogleAuthProvider.credential(token));
}

async function signedIn(user) {
  S.user = user; S.email = (user.email || '').toLowerCase(); S.name = user.displayName || S.email.split('@')[0];
  $('#base').textContent = `Signed in as ${S.name} (${S.email})`;
  let access;
  try {
    access = await fb.getDoc(ref('meta', 'access'));
  } catch (err) {
    return gate(`<h2>No access yet</h2><p>You are signed in as <b>${esc(S.email)}</b>, which is not on the team list.
      Ask the team admin to add this address under <b>Team</b>, then reload this page.</p>
      <div class="gate-buttons"><button id="out">Use another account</button></div>`), $('#out').onclick = () => fb.signOut(auth);
  }
  if (!access.exists()) {
    gate(`<h2>New editor</h2><p>Nobody runs this editor yet. As the first person here you can become its admin: you pick who else
      can see and edit the script, and you upload the script from the desktop Studio.</p>
      <div class="gate-buttons"><button id="claim" class="primary">Make me the admin (${esc(S.email)})</button><button id="out">Sign out</button></div>`);
    $('#out').onclick = () => fb.signOut(auth);
    $('#claim').onclick = async () => {
      await fb.setDoc(ref('meta', 'access'), {admins: [S.email], editors: [], names: {[S.email]: S.name}});
      signedIn(user);
    };
    return;
  }
  S.access = access.data();
  S.isAdmin = S.access.admins.includes(S.email);
  $('#actions').hidden = false; $('#team').hidden = !S.isAdmin; $('#upload').hidden = !S.isAdmin;
  if (!(S.access.names || {})[S.email] && S.isAdmin) fb.updateDoc(ref('meta', 'access'), new fb.FieldPath('names', S.email), S.name).catch(() => {});
  startListening();
}

$('#signout').onclick = async () => { await leave(); await fb.signOut(auth); location.reload(); };

// ---------- live data ----------

function startListening() {
  fb.onSnapshot(ref('meta', 'access'), snap => { if (snap.exists()) S.access = snap.data(); });
  fb.onSnapshot(ref('meta', 'script'), snap => {
    if (!snap.exists()) {
      S.meta = null;
      gate(S.isAdmin
        ? `<h2>Upload the script</h2><p>In the desktop Studio, click <b>Online pack</b>. It saves <code>FM2089 online script.json</code> in its
           exports folder. Upload that file here and the team can start editing.</p><div class="gate-buttons"><button id="gate-upload" class="primary">Upload pack</button></div>`
        : '<h2>No script yet</h2><p>The team admin has not uploaded the script yet. This page fills in by itself once they do.</p>');
      if (S.isAdmin) $('#gate-upload').onclick = () => $('#pack-file').click();
      return;
    }
    S.meta = snap.data();
    S.layout = JSON.parse(S.meta.layout);
    S.chars = S.layout.chars; S.glyphs = S.layout.glyphs;
    S.faces = JSON.parse(S.meta.faces || '{}'); S.portraits = JSON.parse(S.meta.portraits || '{}');
    if (S.loaded) renderRows();
    if (!S.listening) listenFiles();
  });
  fb.onSnapshot(ref('meta', 'speakers'), snap => {
    S.speakers = snap.exists() ? snap.data() : {en: {}, seed: {}};
    if (S.loaded) { renderRows(); if (S.current) refreshEditor(true); }
  });
  fb.onSnapshot(fb.collection(db, 'presence'), snap => {
    snap.docChanges().forEach(ch => ch.type === 'removed' ? delete S.presence[ch.doc.id] : (S.presence[ch.doc.id] = ch.doc.data()));
    renderPresence();
  });
  heartbeat(); setInterval(heartbeat, 60000);
  addEventListener('pagehide', () => { commitAll(); leave(); });
}

function listenFiles() {
  S.listening = true;
  $('#progress').textContent = 'Loading the script…';
  fb.onSnapshot(fb.collection(db, 'files'), snap => {
    const changed = new Set();
    snap.docChanges().forEach(ch => {
      if (ch.type === 'removed') { delete S.files[ch.doc.id]; return; }
      const old = S.files[ch.doc.id];
      const data = ch.doc.data();
      S.files[ch.doc.id] = data;
      if (old && old.entries.length === data.entries.length) {
        for (const e of data.entries) if (S.byId[e.id]) S.byId[e.id].doc = data;
        for (const f of ['en', 'note']) for (const id of new Set([...Object.keys(old[f] || {}), ...Object.keys(data[f] || {})]))
          if ((old[f] || {})[id] !== (data[f] || {})[id]) changed.add(id);
      } else changed.add('*');
    });
    if (changed.has('*') || !S.loaded) buildIndex();
    else { applyFilter(true); progress(); renderTabs(); if (S.current && changed.has(S.current)) refreshEditor(false); }
    const mine = snap.metadata.hasPendingWrites;
    $('#saved').textContent = mine ? 'Saving…' : 'All changes saved';
  });
}

function buildIndex() {
  const all = [];
  for (const [file, d] of Object.entries(S.files)) {
    if (!d.entries) continue;
    for (const e of d.entries) { e.fileDoc = file; all.push(e); }
  }
  all.sort((a, b) => a.pos - b.pos);
  S.entries = all;
  S.byId = Object.fromEntries(all.map(e => [e.id, {e, doc: S.files[e.fileDoc]}]));
  if (!all.length) return;
  $('#gate').hidden = true; $('#app').hidden = false; $('#tabs').hidden = false;
  $('#base').textContent = `Signed in as ${S.name} · script uploaded ${S.meta.made || ''}${S.meta.uploaded ? ' by ' + S.meta.uploaded.n : ''}`;
  progress();
  if (!S.loaded) {
    S.loaded = true;
    const hash = new URLSearchParams(location.hash.slice(1));
    if (S.layout.groups.some(([k]) => k === hash.get('group'))) S.group = hash.get('group');
    renderTabs(); fillFiles(); applyFilter();
    if (hash.get('id') && S.byId[hash.get('id')]) select(hash.get('id'));
  } else {
    renderTabs(); fillFiles(); applyFilter(true);
    if (S.current) refreshEditor(false);
  }
}

const docOf = id => S.byId[id].doc;
const textOf = (id, field = 'en') => (docOf(id)[field] || {})[id] || '';
const seedOf = (id, field = 'en') => (docOf(id)[field === 'en' ? 'seed' : 'seedNote'] || {})[id] || '';
const speakerEn = jp => (S.speakers.en || {})[jp] || S.layout.default_speakers[jp] || '';
function faceImg(jp, cls = 'face') {
  let face = S.faces[jp] || (S.layout.default_faces || {})[jp] || '';
  if (face === '-') face = '';
  if (face && S.portraits[face]) return `<img class="${cls}" src="data:image/png;base64,${S.portraits[face]}" alt="" title="${esc(face)}">`;
  const letter = (speakerEn(jp) || jp).replace(/«[^»]*»/g, '').charAt(0) || '?';
  return `<span class="${cls} no-face" title="No portrait">${esc(letter)}</span>`;
}
const changedOnline = id => textOf(id) !== seedOf(id) || textOf(id, 'note') !== seedOf(id, 'note');

// ---------- length check (same rules as the desktop Studio) ----------

function check(e, text) {
  const errors = [], warnings = [];
  let full = text;
  if (e.speaker) {
    let name = speakerEn(e.speaker);
    if (!name) { name = e.speaker; warnings.push(`The speaker "${e.speaker}" has no English name yet`); }
    full = `${name}:` + (e.speaker_own_line ? '\n' : ' ') + text;
  }
  full = full.split(S.layout.hero[0]).join(S.layout.hero[1]);
  const widths = [0];
  const missing = new Set();
  for (let i = 0; i < full.length; i++) {
    const ch = full[i];
    if (ch === '\n') { widths.push(0); continue; }
    if (ch === '«') {
      const end = full.indexOf('»', i);
      if (end < 0) { errors.push('A « tag is not closed with »'); continue; }
      const tag = full.slice(i + 1, end).trim().toUpperCase();
      if (tag.startsWith('G:')) widths[widths.length - 1] += S.glyphs[parseInt(tag.slice(2), 16)] || 0;
      i = end; continue;
    }
    if (ch in S.chars) widths[widths.length - 1] += S.chars[ch]; else missing.add(ch);
  }
  for (const ch of missing) errors.push(`The game font has no "${ch}"` + ('“”'.includes(ch) ? ' (use a straight " instead)' : '‘’'.includes(ch) ? " (use a straight ' instead)" : ''));
  const limit = e.limit, dialogue = S.layout.dialogue_groups.includes(e.group);
  widths.forEach((w, n) => {
    if (w > S.layout.screen_width) errors.push(`Line ${n + 1} is ${w} px, wider than the DS screen (${S.layout.screen_width} px)`);
    else if (w > limit) warnings.push(dialogue ? `Line ${n + 1} is ${w} px; the text box wraps mid-word past ${limit} px`
                                                : `Line ${n + 1} is ${w} px; the widest Japanese line in this file is ${limit} px`);
  });
  if (widths.length > (e.lines || 1)) warnings.push(`${widths.length} lines; the Japanese has ${e.lines || 1}`);
  const codes = [...new Set((e.body || '').match(/«(?!g:)[^»]+»/g) || [])];
  const have = new Set((text.toUpperCase().match(/«(?!G:)[^»]+»/g) || []));
  const lost = codes.filter(c => !have.has(c.toUpperCase()));
  if (lost.length) warnings.push('Codes from the Japanese are missing: ' + lost.join(' '));
  return {errors, warnings, widths, limit};
}

// ---------- list ----------

// Same totals as the desktop Studio: text the game never shows is left out; text the game already writes in
// English or fills in itself counts as translated
const translated = e => !!textOf(e.id) || !!e.english || !!e.codes;
function progress() {
  const all = S.entries.filter(e => !e.unused), t = all.filter(translated).length;
  $('#progress').textContent = `${fmt(t)} of ${fmt(all.length)} strings translated (${(100 * t / all.length).toFixed(1)}%)`;
  $('#progress').title = `Leaves out ${fmt(S.entries.length - all.length)} strings that are not shown in game.`;
  const typed = all.filter(e => textOf(e.id)), mtl = typed.filter(e => (docOf(e.id).mtl || {})[e.id]).length;
  const online = all.filter(e => changedOnline(e.id)).length, pct = typed.length ? 100 * mtl / typed.length : 0;
  $('#mtl-text').textContent = `MTL ${pct.toFixed(1)}% · ${fmt(mtl)} of ${fmt(typed.length)} translated strings · ${fmt(online)} changed online since the last upload`;
  $('#mtl-fill').style.width = pct + '%';
  $('#mtlbar').hidden = false;
}

function visible(e) { return !($('#hide-unused').checked && e.unused); }

function renderTabs() {
  const counts = {};
  for (const e of S.entries) if (visible(e)) {
    const c = counts[e.group] ||= [0, 0]; c[0]++; if (translated(e)) c[1]++;
  }
  $('#tabs').innerHTML = S.layout.groups.map(([k, label]) =>
    `<button data-g="${esc(k)}" class="${k === S.group ? 'active' : ''}">${esc(label)}<small>${fmt((counts[k] || [0, 0])[1])}/${fmt((counts[k] || [0])[0])}</small></button>`).join('');
  for (const b of $('#tabs').querySelectorAll('button')) b.onclick = () => { S.group = b.dataset.g; S.page = 0; renderTabs(); fillFiles(); applyFilter(); setHash(); };
}

function fillFiles() {
  const files = [...new Set(S.entries.filter(e => e.group === S.group).map(e => e.file))];
  const keep = $('#file').value;
  $('#file').innerHTML = '<option value="">All files</option>' + files.map(f => `<option>${esc(f)}</option>`).join('');
  if (files.includes(keep)) $('#file').value = keep;
}

function applyFilter(keepPage) {
  const q = $('#search').value.trim().toLowerCase(), file = $('#file').value, status = $('#status').value;
  S.filtered = S.entries.filter(e => {
    if (e.group !== S.group || !visible(e)) return false;
    if (!(e.body || '').trim() && !textOf(e.id)) return false;
    if (file && e.file !== file) return false;
    const en = textOf(e.id), note = textOf(e.id, 'note');
    if (status === 'todo' && (en || e.codes || e.english)) return false;
    if (status === 'translated' && !en) return false;
    if (status === 'changed' && !changedOnline(e.id)) return false;
    if (status === 'noted' && !note) return false;
    if (status === 'mtl' && !(docOf(e.id).mtl || {})[e.id]) return false;
    if (status === 'warn') { if (!en) return false; const c = check(e, en); if (!c.errors.length && !c.warnings.length) return false; }
    if (q && ![e.id, e.body, en, note, e.speaker && speakerEn(e.speaker)].some(t => (t || '').toLowerCase().includes(q))) return false;
    return true;
  });
  if (!keepPage) S.page = 0;
  S.page = Math.min(S.page, Math.max(0, Math.ceil(S.filtered.length / PAGE) - 1));
  renderRows();
}

function colorOf(email) {
  let h = 0; for (const c of email || '') h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h} 70% 62%)`;
}

function othersOn(id) {
  const now = Date.now();
  return Object.entries(S.presence).filter(([uid, p]) => uid !== S.user.uid && p.id === id && fresh(p, now)).map(([, p]) => p);
}
const fresh = (p, now = Date.now()) => p.t?.toMillis ? now - p.t.toMillis() < 180000 : true;

function renderRows() {
  if (!S.loaded) return;
  const rows = S.filtered.slice(S.page * PAGE, (S.page + 1) * PAGE);
  let html = '', scene = '';
  for (const e of rows) {
    if (S.group === 'story' && e.mission != null) {
      const label = `Mission ${e.mission}${e.mission_title ? ' · ' + e.mission_title : ''} · ${e.scene}`;
      if (label !== scene) { html += `<div class="scene-head">${esc(label)}</div>`; scene = label; }
    }
    const en = textOf(e.id);
    const who = othersOn(e.id).map(p => `<i style="background:${colorOf(p.e)}" title="${esc(p.n)} is on this line"></i>`).join('');
    const badges = [changedOnline(e.id) ? '<span class="badge person">changed online</span>' : '',
                    (docOf(e.id).mtl || {})[e.id] ? '<span class="badge warn">MTL</span>' : '',
                    e.unused ? `<span class="badge hidden">${esc(e.unused)}</span>` : ''].join(' ');
    html += `<button class="row ${e.speaker ? 'has-face' : ''} ${e.id === S.current ? 'active' : ''}" data-id="${esc(e.id)}" role="listitem">
      ${e.speaker ? faceImg(e.speaker) + '<div class="row-text">' : ''}<div class="meta"><span>${esc(e.file)} #${e.index} <span class="here">${who}</span></span><span>${badges}</span></div>
      ${e.speaker ? `<div class="speaker">${esc(speakerEn(e.speaker) || e.speaker)}</div>` : ''}
      <div class="jp">${esc(e.body)}</div>
      <div class="en ${en ? '' : 'none'}">${en ? esc(en) : (e.english ? 'already English in game' : e.codes ? 'filled in by the game' : 'not translated')}</div>${e.speaker ? '</div>' : ''}</button>`;
  }
  $('#rows').innerHTML = html || '<p class="empty-editor" style="padding:14px">Nothing matches.</p>';
  for (const b of $('#rows').querySelectorAll('.row')) b.onclick = () => select(b.dataset.id);
  const pages = Math.max(1, Math.ceil(S.filtered.length / PAGE));
  $('#count').textContent = `${fmt(S.filtered.length)} lines`;
  $('#page').textContent = `Page ${S.page + 1} of ${pages}`;
  $('#prev').disabled = S.page === 0; $('#next').disabled = S.page >= pages - 1;
}

$('#prev').onclick = () => { S.page--; renderRows(); $('#rows').scrollTop = 0; };
$('#next').onclick = () => { S.page++; renderRows(); $('#rows').scrollTop = 0; };
let searchTimer;
$('#search').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => applyFilter(), 200); };
$('#file').onchange = $('#status').onchange = () => applyFilter();
$('#hide-unused').onchange = () => { renderTabs(); applyFilter(); };

function setHash() { history.replaceState(null, '', `#group=${encodeURIComponent(S.group)}${S.current ? '&id=' + encodeURIComponent(S.current) : ''}`); }

// ---------- editing ----------

function select(id) {
  commitAll();
  S.current = id;
  const {e} = S.byId[id];
  if (e.group !== S.group) { S.group = e.group; renderTabs(); fillFiles(); applyFilter(); }
  for (const r of $('#rows').querySelectorAll('.row')) r.classList.toggle('active', r.dataset.id === id);
  S.sync = {en: textOf(id), note: textOf(id, 'note')}; S.conflict = {};
  renderEditor();
  setHash(); heartbeat();
}

function renderEditor() {
  const id = S.current, {e} = S.byId[id];
  const scene = e.mission != null ? `Mission ${e.mission}${e.mission_title ? ' · ' + e.mission_title : ''} · ${e.scene} · ` : '';
  $('#editor').innerHTML = `
    <h2>${esc(id)}</h2>
    <div class="sub">${esc(scene)}${esc(e.file)} #${e.index}</div>
    ${e.art ? `<div class="sub art">${esc(e.art)}</div>` : ''}
    ${e.speaker ? `<div class="speaker-bar">${faceImg(e.speaker, 'face big')}<span>Speaker</span><b>${esc(e.speaker)}</b><label class="inline">English name (every line)<input id="sp-en" value="${esc(speakerEn(e.speaker))}"></label></div>` : ''}
    <div class="jp-box">${esc(e.body)}</div>
    <div class="field"><label>English<textarea id="en" spellcheck="true">${esc(S.sync.en)}</textarea></label>
      <div class="widths" id="widths"></div><ul class="msgs" id="msgs"></ul><div id="live-en"></div></div>
    <div class="field"><label>Note<textarea id="note" class="note" rows="3">${esc(S.sync.note)}</textarea></label><div id="live-note"></div></div>
    <div class="editedby" id="editedby"></div>
    <div class="editedby" id="seed"></div>
    <details class="history" id="history"><summary>History of this line</summary><ol></ol></details>`;
  for (const field of ['en', 'note']) {
    const box = $('#' + field);
    box.onfocus = () => { S.start[field] = {id, value: box.value}; };
    box.oninput = () => { if (field === 'en') showCheck(); queueSave(id, field, box.value); };
    box.onblur = () => { flush(id, field); commit(field); };
  }
  if (e.speaker) $('#sp-en').onchange = ev => saveSpeaker(e.speaker, ev.target.value.trim());
  $('#history').ontoggle = () => $('#history').open && loadHistory(id);
  showCheck(); showMeta();
}

function showCheck() {
  const {e} = S.byId[S.current], text = $('#en').value;
  if (!text) { $('#widths').textContent = ''; $('#msgs').innerHTML = ''; return; }
  const c = check(e, text);
  $('#widths').textContent = `Line widths: ${c.widths.join(', ')} px (limit ${c.limit} px)`;
  $('#msgs').innerHTML = c.errors.map(m => `<li class="error">${esc(m)}</li>`).join('') + c.warnings.map(m => `<li class="warning">${esc(m)}</li>`).join('');
}

function showMeta() {
  const id = S.current, by = (docOf(id).by || {})[id];
  $('#editedby').textContent = by ? `Last changed online by ${by.n}, ${when(by.t)}` : 'Not changed online yet.';
  const seed = seedOf(id);
  $('#seed').innerHTML = textOf(id) !== seed ? `Last upload from the Studio: <code>${esc(seed || '(empty)')}</code>` : '';
  const others = othersOn(id);
  if (others.length) $('#editedby').textContent += ` · Also on this line now: ${others.map(p => p.n).join(', ')}`;
}

// A remote change to the open line: take it if you have not typed since, otherwise offer it.
function refreshEditor(speakersOnly) {
  const id = S.current;
  if (!id || !$('#en')) return;
  if (!speakersOnly) for (const field of ['en', 'note']) {
    const remote = textOf(id, field), box = $('#' + field), live = $('#live-' + field);
    if (remote === S.sync[field]) continue;
    if (box.value === S.sync[field] || box.value === remote) {
      const [a, b] = [box.selectionStart, box.selectionEnd];
      box.value = remote; S.sync[field] = remote; live.innerHTML = '';
      if (document.activeElement === box) box.setSelectionRange(a, b);
    } else {
      const by = (docOf(id).by || {})[id];
      // hold your saves on this box until you pick, so neither text is lost by accident
      S.conflict[field] = true; clearTimeout(S.timers[field]); S.timers[field] = null;
      live.innerHTML = `<div class="live">${esc(by ? by.n : 'Someone')} changed this ${field === 'en' ? 'English' : 'note'} while you were typing:
        <pre>${esc(remote || '(empty)')}</pre><button data-pick="theirs">Use their text</button> <button data-pick="mine">Keep mine</button>
        <span class="muted">Your text is not saved until you pick.</span></div>`;
      live.querySelector('[data-pick=theirs]').onclick = () => {
        S.conflict[field] = false; box.value = remote; S.sync[field] = remote; live.innerHTML = ''; if (field === 'en') showCheck();
      };
      live.querySelector('[data-pick=mine]').onclick = () => { S.conflict[field] = false; live.innerHTML = ''; save(id, field, box.value); };
    }
  }
  if (S.byId[id].e.speaker && document.activeElement !== $('#sp-en')) $('#sp-en').value = speakerEn(S.byId[id].e.speaker);
  showCheck(); showMeta();
}

function queueSave(id, field, value) {
  clearTimeout(S.timers[field]);
  if (S.conflict[field]) return;
  $('#saved').textContent = 'Typing…';
  S.timers[field] = setTimeout(() => save(id, field, value), 900);
}

function flush(id, field) {
  if (S.timers[field]) { clearTimeout(S.timers[field]); S.timers[field] = null; const box = $('#' + field); if (box) save(id, field, box.value); }
}

function save(id, field, value) {
  S.timers[field] = null;
  if (S.conflict[field]) return;
  if (value === textOf(id, field)) { S.sync[field] = value; return; }
  S.sync[field] = value;
  const args = [new fb.FieldPath(field, id), value || fb.deleteField(), new fb.FieldPath('by', id), {n: S.name, e: S.email, t: fb.serverTimestamp()}];
  if (field === 'en') args.push(new fb.FieldPath('mtl', id), fb.deleteField());
  $('#saved').textContent = 'Saving…';
  fb.updateDoc(ref('files', S.byId[id].e.fileDoc), ...args)
    .then(() => { $('#saved').textContent = 'All changes saved'; $('#live-' + field) && ($('#live-' + field).innerHTML = ''); })
    .catch(err => { $('#saved').textContent = 'Not saved: ' + err.message; });
}

// one history item per finished edit (when you leave the box), not per keystroke
function commit(field) {
  const s = S.start[field];
  S.start[field] = null;
  if (!s || !S.byId[s.id] || S.conflict[field]) return;
  const box = $('#' + field), now = box && S.current === s.id ? box.value : textOf(s.id, field);
  if (now === s.value) return;
  fb.addDoc(fb.collection(db, 'history'), {id: s.id, field, old: s.value, new: now, n: S.name, e: S.email, t: fb.serverTimestamp()}).catch(() => {});
}

function commitAll() {
  if (!S.current) return;
  for (const f of ['en', 'note']) { flush(S.current, f); commit(f); }
}

function saveSpeaker(jp, en) {
  const old = speakerEn(jp);
  if (en === old) return;
  fb.updateDoc(ref('meta', 'speakers'), new fb.FieldPath('en', jp), en || fb.deleteField(),
               new fb.FieldPath('by', jp), {n: S.name, e: S.email, t: fb.serverTimestamp()})
    .catch(err => alert('Not saved: ' + err.message));
  fb.addDoc(fb.collection(db, 'history'), {id: jp, field: 'speaker', old, new: en, n: S.name, e: S.email, t: fb.serverTimestamp()}).catch(() => {});
}

async function loadHistory(id) {
  const list = $('#history ol');
  list.innerHTML = '<li>Loading…</li>';
  const snap = await fb.getDocs(fb.query(fb.collection(db, 'history'), fb.where('id', '==', id), fb.limit(100)));
  const items = snap.docs.map(d => d.data()).sort((a, b) => (b.t?.toMillis?.() || 0) - (a.t?.toMillis?.() || 0));
  if (S.current !== id) return;
  list.innerHTML = items.length ? items.map(h => `<li><b>${esc(h.n)}</b>, ${esc(when(h.t))} · ${h.field === 'note' ? 'note' : 'English'}<pre>${esc(h.new || '(empty)')}</pre>
    <span class="muted">was: ${esc(h.old || '(empty)')}</span></li>`).join('') : '<li>No changes online yet.</li>';
}

// ---------- who is online ----------

function heartbeat() {
  if (!S.user || !S.access) return;
  fb.setDoc(ref('presence', S.user.uid), {n: S.name, e: S.email, id: S.current || '', t: fb.serverTimestamp()}).catch(() => {});
}
function leave() { return S.user ? fb.deleteDoc(ref('presence', S.user.uid)).catch(() => {}) : Promise.resolve(); }

function renderPresence() {
  const now = Date.now();
  const people = Object.values(S.presence).filter(p => fresh(p, now));
  $('#online').innerHTML = people.map(p => `<span class="who" title="${esc(p.e)}${p.id ? ' · on ' + esc(p.id) : ''}"><i style="background:${colorOf(p.e)}"></i>${esc(p.n)}</span>`).join('');
  if (S.loaded) { renderRows(); if (S.current) showMeta(); }
}
setInterval(renderPresence, 60000);

// ---------- dialogs ----------

function dialog(html) { $('#dialog-body').innerHTML = html; if (!$('#dialog').open) $('#dialog').showModal(); }

$('#recent').onclick = async () => {
  dialog('<h3>Recent changes</h3><div class="recent"><ol><li>Loading…</li></ol></div>');
  const snap = await fb.getDocs(fb.query(fb.collection(db, 'history'), fb.orderBy('t', 'desc'), fb.limit(150)));
  const items = snap.docs.map(d => d.data());
  $('#dialog-body .recent ol').innerHTML = items.length ? items.map(h => `<li data-id="${esc(h.id)}"><b>${esc(h.n)}</b>, ${esc(when(h.t))} ·
      ${h.field === 'speaker' ? 'speaker name' : h.field === 'note' ? 'note' : 'English'} · <code>${esc(h.id)}</code><pre>${esc(h.new || '(empty)')}</pre></li>`).join('')
    : '<li>Nobody has changed anything online yet.</li>';
  for (const li of $('#dialog-body').querySelectorAll('li[data-id]')) li.onclick = () => { if (S.byId[li.dataset.id]) { $('#dialog').close(); select(li.dataset.id); } };
};

$('#speakers').onclick = () => {
  const counts = {};
  for (const e of S.entries) if (e.speaker) counts[e.speaker] = (counts[e.speaker] || 0) + 1;
  const names = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  dialog(`<h3>Speaker names</h3><p class="muted">Each name is used on every line that speaker says.</p>
    <div class="speaker-table">${names.map(jp => `<label>${esc(jp)}<small>${fmt(counts[jp])} lines</small><input data-jp="${esc(jp)}" value="${esc(speakerEn(jp))}"></label>`).join('')}</div>`);
  for (const input of $('#dialog-body').querySelectorAll('input[data-jp]')) input.onchange = () => saveSpeaker(input.dataset.jp, input.value.trim());
};

$('#team').onclick = () => renderTeam();
function renderTeam() {
  const a = S.access, names = a.names || {};
  const row = (email, role) => `<div><span>${esc(names[email] || '')} <code>${esc(email)}</code> · ${role}</span>
    ${email === S.email ? '<span class="muted">you</span>' : `<button data-rm="${esc(email)}">Remove</button>`}</div>`;
  dialog(`<h3>Team</h3><p class="muted">Only these Google accounts can open the script. Admins can also change this list and upload packs.</p>
    <div class="team-list">${a.admins.map(e => row(e, 'admin')).join('')}${a.editors.map(e => row(e, 'editor')).join('')}</div>
    <div class="team-add"><label>Google account email<input id="add-email" type="email" placeholder="name@gmail.com"></label>
      <label>Role<select id="add-role"><option value="editors">Editor</option><option value="admins">Admin</option></select></label>
      <button id="add" class="primary">Add</button></div>`);
  $('#add').onclick = async () => {
    const email = $('#add-email').value.trim().toLowerCase(), role = $('#add-role').value;
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return alert('That does not look like an email address.');
    const next = {admins: a.admins.filter(x => x !== email), editors: a.editors.filter(x => x !== email)};
    next[role].push(email);
    await fb.updateDoc(ref('meta', 'access'), next); S.access = {...a, ...next}; renderTeam();
  };
  for (const b of $('#dialog-body').querySelectorAll('[data-rm]')) b.onclick = async () => {
    const next = {admins: a.admins.filter(x => x !== b.dataset.rm), editors: a.editors.filter(x => x !== b.dataset.rm)};
    await fb.updateDoc(ref('meta', 'access'), next); S.access = {...a, ...next}; renderTeam();
  };
}

// ---------- uploading a pack from the desktop Studio ----------

$('#upload').onclick = () => $('#pack-file').click();
$('#pack-file').onchange = async ev => {
  const file = ev.target.files[0];
  ev.target.value = '';
  if (!file) return;
  let pack;
  try { pack = JSON.parse(await file.text()); } catch { return alert('That file is not an Online pack (not JSON).'); }
  if (pack.format !== 'fm2089-online-script') return alert('That file is not an Online pack. In the desktop Studio, click Online pack and upload the file it saves.');
  dialog('<h3>Uploading the script…</h3><p id="up-status">Preparing…</p>');
  try {
    const kept = await uploadPack(pack, msg => { $('#up-status').textContent = msg; });
    dialog(`<h3 class="ok">Script uploaded</h3><p>${fmt(pack.entries.length)} lines from the pack made ${esc(pack.made)}.
      ${kept ? `${fmt(kept)} line${kept === 1 ? '' : 's'} changed online kept ${kept === 1 ? 'its' : 'their'} online text.` : 'No lines had online changes to keep.'}</p>`);
  } catch (err) {
    dialog(`<h3 class="bad">Upload failed</h3><p>${esc(err.message)}</p>`);
  }
};

// Lines nobody changed online take the pack's text; lines changed online keep it. Either way the pack's text
// becomes the new "last upload", which Download changes compares against.
async function uploadPack(pack, status) {
  const byFile = {};
  pack.entries.forEach((e, pos) => { (byFile[e.file] ||= []).push({...e, pos}); });
  let kept = 0;
  const docs = Object.entries(byFile).map(([file, entries]) => {
    const old = S.files[file] || {};
    const d = {entries, en: {}, note: {}, seed: {}, seedNote: {}, mtl: {}, by: old.by || {}};
    for (const e of entries) {
      const t = pack.text[e.id] || {};
      for (const [field, seedField] of [['en', 'seed'], ['note', 'seedNote']]) {
        const fresh = t[field] || '', cur = (old[field] || {})[e.id] || '', seed = (old[seedField] || {})[e.id] || '';
        const value = old.entries && cur !== seed ? cur : fresh;
        if (old.entries && cur !== seed && cur !== fresh && field === 'en') kept++;
        if (value) d[field][e.id] = value;
        if (fresh) d[seedField][e.id] = fresh;
      }
      if (t.mtl && d.en[e.id] === (t.en || '')) d.mtl[e.id] = true;
    }
    return [file, d];
  });
  for (let i = 0; i < docs.length; i += 8) {
    status(`Saving files ${i + 1}-${Math.min(i + 8, docs.length)} of ${docs.length}…`);
    const batch = fb.writeBatch(db);
    for (const [file, d] of docs.slice(i, i + 8)) batch.set(ref('files', file), d);
    await batch.commit();
  }
  const sp = S.speakers || {}, en = {};
  for (const jp of new Set([...Object.keys(pack.speakers), ...Object.keys(sp.en || {})])) {
    const cur = (sp.en || {})[jp] || '', seed = (sp.seed || {})[jp] || '', fresh = pack.speakers[jp] || '';
    const value = Object.keys(sp.seed || {}).length && cur !== seed ? cur : fresh;
    if (value) en[jp] = value;
  }
  await fb.setDoc(ref('meta', 'speakers'), {en, seed: pack.speakers, by: sp.by || {}});
  const layout = {groups: pack.groups, dialogue_groups: pack.dialogue_groups, screen_width: pack.screen_width, hero: pack.hero,
                  default_speakers: pack.default_speakers, default_faces: pack.default_faces || {}, chars: pack.chars, glyphs: pack.glyphs};
  await fb.setDoc(ref('meta', 'script'), {made: pack.made, layout: JSON.stringify(layout), faces: JSON.stringify(pack.faces || {}), portraits: JSON.stringify(pack.portraits || {}),
                                          uploaded: {n: S.name, e: S.email, t: fb.serverTimestamp()}});
  return kept;
}

// ---------- downloads for the desktop Studio ----------

function saveFile(name, text, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], {type}));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
const stamp = () => { const d = new Date(), p = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}${p(d.getMinutes())}`; };

// Same .md the Studio's Export script writes (studio/tools/scriptio.py): "Old" = the last upload, "New" = the online text,
// so Import script / Import multiple can tell when a line was also changed in the Studio since the upload.
function fence(text) { const runs = (text.match(/~{3,}/g) || []).map(r => r.length); return '~'.repeat(Math.max(2, ...runs) + 1); }
function block(label, text) { const f = fence(text); return [`${label}:`, f + 'text', ...(text ? [text] : []), f, '']; }

function changesMd() {
  const out = [], seedSp = S.speakers.seed || {}, enSp = S.speakers.en || {};
  let count = 0;
  for (const jp of Object.keys({...seedSp, ...enSp}).sort()) {
    if ((seedSp[jp] || '') === (enSp[jp] || '')) continue;
    out.push('---', '', `## Speaker name: ${jp}`, '', ...block('Old name', seedSp[jp] || ''), ...block('New name', enSp[jp] || ''));
    count++;
  }
  for (const e of S.entries) {
    const parts = [];
    for (const [field, word] of [['en', 'English'], ['note', 'note']]) {
      const old = seedOf(e.id, field), now = textOf(e.id, field);
      if (old !== now) { parts.push(...block(`Old ${word}`, old), ...block(`New ${word}`, now)); count++; }
    }
    if (!parts.length) continue;
    out.push('---', '', `## ${e.id}`, '');
    if (e.speaker) out.push(`Speaker: ${e.speaker} (${speakerEn(e.speaker) || 'no English name'})`, '');
    out.push(...block('Japanese', e.body || ''), ...parts);
  }
  const head = ['# FM2089 script changes', '', '- From: the online script', `- Exported: ${stamp().replace(/ (\d\d)(\d\d)$/, ' $1:$2')}`,
    `- Changes since: the online script's last upload (${S.meta.made})`, `- Changes: ${count}`, '',
    'Load this file with **Import script** (or several at once with **Import multiple**) in the FM2089 Translation Studio.',
    'Only the "New" blocks are read in; "Old" is what the sender started from, so the Studio can tell when both of you changed a line.', ''];
  return {text: [...head, ...out].join('\n').trimEnd() + '\n', count};
}

$('#download').onclick = () => {
  const {text, count} = changesMd();
  if (!count) return dialog(`<h3>Nothing changed online</h3><p>No line differs from the last upload (${esc(S.meta.made)}).
    Use <b>Download full script</b> for the whole script.</p>`);
  saveFile(`FM2089 online changes - ${stamp()}.md`, text, 'text/markdown');
  dialog(`<h3 class="ok">Downloaded ${fmt(count)} change${count === 1 ? '' : 's'}</h3><p>In the desktop Studio, click <b>Import script</b> and pick the file.
    Lines you also changed in the Studio since the last upload are shown so you can pick which text to keep. Then build the patch as usual.</p>`);
};

$('#download-full').onclick = () => {
  const entries = {};
  for (const e of S.entries) {
    const en = textOf(e.id), note = textOf(e.id, 'note');
    if (!en && !note) continue;
    entries[e.id] = {...(en && {en}), ...(note && {note}), ...((docOf(e.id).mtl || {})[e.id] && {mtl: true})};
  }
  const data = {application: 'fm2089-translation-studio', version: 1, saved: new Date().toISOString().slice(0, 19),
                speakers: S.speakers.en || {}, faces: JSON.parse(S.meta.faces || '{}'), entries};
  saveFile(`FM2089 online script - ${stamp()}.json`, JSON.stringify(data, null, 1), 'application/json');
  dialog(`<h3 class="ok">Downloaded the full script</h3><p>In the desktop Studio, <b>Import script</b> takes every line from this file that differs
    from yours, without asking. To keep lines you changed in the Studio, use <b>Download changes</b> instead.</p>`);
};
