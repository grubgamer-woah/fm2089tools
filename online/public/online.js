// FM2089 Online Studio: the desktop Studio's own page (studio/app.js, copied by dev/sync-studio.mjs) running in
// the browser, with its /api/... requests answered from the shared Firestore database instead of the Python server.
// Everything the team sees is the Studio's; this file adds sign-in, the team list, live updates from other people,
// pack uploads and the script download, and leaves out building (no ROM here).
//
// Database: meta/access (team), meta/script (pack date and layout), meta/font, meta/portraits, meta/speakers
// (names and portraits), meta/project (settings, credits), files/{file} (one per game text file: its entries and,
// per line, en / note / done / mtl / edited / hidden, the last uploaded text and who changed it), history, presence.
import * as fb from './firebase.js';
import { firebaseConfig } from './firebase-config.js';

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fmt = n => Number(n).toLocaleString('en-US');
const when = t => { const d = t?.toDate ? t.toDate() : null; return d ? d.toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}) : 'just now'; };
const FIELDS = ['en', 'note', 'done', 'mtl', 'edited', 'hidden'];
const O = {files: {}, byId: {}, speakers: {}, project: {}, presence: {}, claims: {}, started: false};

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
const now = () => fb.serverTimestamp();

// ---------- page frame: sign-in screen and the online buttons ----------

const gate = document.createElement('section');
gate.className = 'notice gate';
$('main').prepend(gate);
function showGate(html) { document.body.classList.add('gated'); gate.hidden = false; gate.innerHTML = html; }
function hideGate() { document.body.classList.remove('gated'); gate.hidden = true; }

// building needs the ROM, and mission titles, TSV and fonts are not wanted online
// (hidden rather than removed: the Studio's code still looks them up)
for (const id of ['#build', '#restart', '#fonts', '#export-web', '#export', '#titles']) $(id).style.display = 'none';
$('#stat-icons').closest('label').style.display = 'none';
$('#export-script').title = 'Download every line changed online since the last upload as a script .md; load it in the desktop Studio with Import script';
$('#import').title = 'Import a script (.md, .tsv, .txt or project.json) into the shared online script';
$('#import-multi').title = 'Import several scripts into the shared online script at once: changes only one of them makes go in, and you pick where they disagree';
$('footer').innerHTML = 'Edits save to the team\'s shared online script, and everyone signed in sees them. Build the patch in the desktop Studio: '
  + '<b>Export script</b> here, then <b>Import script</b> there.<span id="project-path" hidden></span>';
const actions = $('header .actions');
actions.insertAdjacentHTML('afterbegin', '<span id="online" class="online" aria-label="Who is online"></span>');
actions.insertAdjacentHTML('beforeend', `<button id="review" title="Accept, change or reject the team's suggested changes" hidden>Review</button>
  <button id="inbox" title="What happened to the changes you suggested">Inbox</button>
  <button id="recent" title="The latest changes anyone made">Recent changes</button>
  <button id="team" title="Who can see and edit the script" hidden>Team</button>
  <button id="upload" title="Upload the Online pack the desktop Studio saves" hidden>Upload pack</button>
  <button id="signout" title="Sign out">Sign out</button>`);
document.body.insertAdjacentHTML('beforeend', '<input id="pack-file" type="file" accept=".json,application/json" hidden>');

if (firebaseConfig.projectId === 'PASTE-HERE') {
  showGate('<h2>Not set up yet</h2><p>Paste the Firebase project\'s settings into <code>public/firebase-config.js</code> and deploy again (see online/README.md).</p>');
} else {
  fb.onAuthStateChanged(auth, user => user ? signedIn(user) : signedOut());
}

function signedOut() {
  showGate(`<h2>Sign in</h2><p>The script is only open to the translation team. Sign in with the Google account the team admin added.</p>
    <p><button id="signin" class="primary">Sign in with Google</button></p>`);
  $('#signin').onclick = () => (emulator && params.get('as') ? emulatorSignIn(params.get('as'))
    : fb.signInWithPopup(auth, new fb.GoogleAuthProvider())).catch(err => alert('Sign-in failed: ' + err.message));
}

// Testing only (?emulator&as=name@example.com with the Firebase emulators running): a made-up Google account
function emulatorSignIn(email) {
  const token = JSON.stringify({sub: email, email, email_verified: true, name: email.split('@')[0]});
  return fb.signInWithCredential(auth, fb.GoogleAuthProvider.credential(token));
}

$('#signout').onclick = async () => { await leave(); await fb.signOut(auth); location.reload(); };

async function signedIn(user) {
  O.user = user; O.email = (user.email || '').toLowerCase(); O.name = user.displayName || O.email.split('@')[0];
  $('#base').textContent = `Signed in as ${O.name}`;
  let access;
  try {
    access = await fb.getDoc(ref('meta', 'access'));
  } catch {
    showGate(`<h2>No access yet</h2><p>You are signed in as <b>${esc(O.email)}</b>, which is not on the team list.
      Ask the team admin to add this address under <b>Team</b>, then reload this page.</p><p><button id="out">Use another account</button></p>`);
    $('#out').onclick = () => fb.signOut(auth);
    return;
  }
  if (!access.exists()) {
    showGate(`<h2>New editor</h2><p>Nobody runs this editor yet. As the first person here you can become its admin: you pick who else
      can see and edit the script, and you upload the script from the desktop Studio.</p>
      <p><button id="claim" class="primary">Make me the admin (${esc(O.email)})</button> <button id="out">Sign out</button></p>`);
    $('#out').onclick = () => fb.signOut(auth);
    $('#claim').onclick = async () => { await fb.setDoc(ref('meta', 'access'), {admins: [O.email], editors: [], names: {[O.email]: O.name}}); signedIn(user); };
    return;
  }
  O.access = access.data();
  O.isAdmin = O.access.admins.includes(O.email);
  // reviewers (and admins) change the script directly and review everyone else's suggestions
  O.canReview = O.isAdmin || (O.access.reviewers || []).includes(O.email);
  $('#team').hidden = $('#upload').hidden = !O.isAdmin;
  $('#review').hidden = !O.canReview;
  if (!(O.access.names || {})[O.email] && O.isAdmin) fb.updateDoc(ref('meta', 'access'), new fb.FieldPath('names', O.email), O.name).catch(() => {});
  listen();
}

// ---------- live data from the database ----------

function listen() {
  fb.onSnapshot(ref('meta', 'access'), snap => {
    if (!snap.exists()) return;
    O.access = snap.data();
    const was = O.canReview;
    O.isAdmin = O.access.admins.includes(O.email);
    O.canReview = O.isAdmin || (O.access.reviewers || []).includes(O.email);
    $('#team').hidden = $('#upload').hidden = !O.isAdmin;
    $('#review').hidden = !O.canReview;
    if (was !== undefined && was !== O.canReview) alert('Your role on the team changed. The page will reload.') || location.reload();
  });
  fb.onSnapshot(ref('meta', 'script'), async snap => {
    if (!snap.exists()) {
      showGate(O.isAdmin
        ? `<h2>Upload the script</h2><p>In the desktop Studio, click <b>Online pack</b>: it saves <code>FM2089 online script.json</code> in its
           exports folder. Upload that file here and the team can start editing.</p><p><button id="gate-upload" class="primary">Upload pack</button></p>`
        : '<h2>No script yet</h2><p>The team admin has not uploaded the script yet. This page fills in by itself once they do.</p>');
      if (O.isAdmin) $('#gate-upload').onclick = () => $('#pack-file').click();
      return;
    }
    const meta = snap.data();
    if (meta.version !== 2) {
      showGate(`<h2>Upload the script again</h2><p>The script here came from an older Online pack. ${O.isAdmin
        ? 'Save a new one with the desktop Studio\'s <b>Online pack</b> button and upload it.</p><p><button id="gate-upload" class="primary">Upload pack</button></p>'
        : 'The team admin needs to upload a new one.</p>'}`);
      if (O.isAdmin) $('#gate-upload').onclick = () => $('#pack-file').click();
      return;
    }
    O.meta = meta; O.layout = JSON.parse(meta.layout);
    if (!O.font) {
      const [font, portraits] = await Promise.all([fb.getDoc(ref('meta', 'font')), fb.getDoc(ref('meta', 'portraits'))]);
      O.font = JSON.parse(font.data().json); O.portraits = JSON.parse(portraits.data().json);
      O.fontWidths = O.font.glyphs.map(([w]) => w);
    }
    $('#progress-note')?.remove();
    if (!O.listening) listenScript();
  });
  fb.onSnapshot(fb.collection(db, 'presence'), snap => {
    snap.docChanges().forEach(ch => ch.type === 'removed' ? delete O.presence[ch.doc.id] : (O.presence[ch.doc.id] = ch.doc.data()));
    renderPresence();
  });
  heartbeat(); setInterval(heartbeat, 60000);
  addEventListener('pagehide', leave);
}

function listenScript() {
  O.listening = true;
  let first = true;
  fb.onSnapshot(ref('meta', 'speakers'), snap => {
    O.speakers = snap.exists() ? snap.data() : {};
    if (O.started) liveSpeakers();
  });
  fb.onSnapshot(ref('meta', 'project'), snap => { O.project = snap.exists() ? snap.data() : {}; });
  // suggestions waiting for review (everyone's), and your own after review (for the inbox)
  fb.onSnapshot(fb.query(fb.collection(db, 'suggestions'), fb.where('status', '==', 'pending')), snap => {
    const touched = new Set(Object.values(O.pending || {}).map(x => x.kind + '\t' + x.id));
    O.pending = Object.fromEntries(snap.docs.map(d => [d.id, d.data()]));
    for (const x of Object.values(O.pending)) touched.add(x.kind + '\t' + x.id);
    renderCounts();
    if (O.started && O.wrapped) livePending(touched);
  });
  fb.onSnapshot(fb.query(fb.collection(db, 'suggestions'), fb.where('uid', '==', O.user.uid)), snap => {
    O.mine = snap.docs.map(d => ({ref: d.ref, ...d.data()})).filter(x => x.status !== 'pending');
    renderCounts();
  });
  fb.onSnapshot(fb.collection(db, 'files'), snap => {
    const changed = new Set();
    snap.docChanges().forEach(ch => {
      if (ch.type === 'removed') { delete O.files[ch.doc.id]; return; }
      const data = ch.doc.data(), old = O.files[ch.doc.id];
      O.files[ch.doc.id] = data;
      for (const e of data.entries) O.byId[e.id] = {e, file: ch.doc.id};
      if (old) for (const e of data.entries) if (FIELDS.some(f => (old[f] || {})[e.id] !== (data[f] || {})[e.id])) changed.add(e.id);
    });
    $('#saved').textContent = snap.metadata.hasPendingWrites ? 'Saving…' : $('#saved').textContent;
    if (first) { first = false; startStudio(); return; }
    if (O.started) liveEntries(changed);
  });
}

// the Studio's entry (project.json style) for one line, from its file document
function entryOf(id) {
  const d = O.files[O.byId[id].file], out = {};
  for (const f of FIELDS) { const v = (d[f] || {})[id]; if (v !== undefined && v !== '') out[f] = v; }
  return out;
}
// the done / mtl / edited / hidden flags the line had in the last upload (stored as their JSON, joined by commas)
function seedFlagsOf(id) {
  const s = (O.files[O.byId[id].file].seedFlags || {})[id];
  if (!s) return {};
  const [done, mtl, edited, hidden] = JSON.parse(`[${s}]`);
  return {done, mtl, edited, hidden};
}
const seedOf = (id, field = 'en') => (O.files[O.byId[id].file][field === 'en' ? 'seed' : 'seedNote'] || {})[id] || '';
const allEntries = () => Object.values(O.files).flatMap(d => d.entries).sort((a, b) => a.pos - b.pos);
// What you see: the shared script with your own suggestions still waiting for review laid over it
// (an admin's changes go straight into the script, so an admin sees just the script)
const mySuggestion = (kind, id) => (O.pending || {})[suggestionId(kind, id)];
function viewOf(id) {
  const s = mySuggestion('entry', id);
  return s ? projectSet(entryOf(id), s.change) : entryOf(id);
}
const projectMap = () => Object.fromEntries(Object.keys(O.byId).map(id => [id, viewOf(id)]).filter(([, p]) => Object.keys(p).length));
function overlay(kind, field) {
  const out = {...(O.speakers[field] || {})};
  for (const x of Object.values(O.pending || {})) if (x.uid === O.user.uid && x.kind === kind) { if (x.change.value) out[x.id] = x.change.value; else delete out[x.id]; }
  return out;
}
const speakerMap = () => overlay('speaker', 'en');
const faceMap = () => overlay('face', 'faces');
const credits = () => ({...O.layout.credits.default, ...(mySuggestion('credits', '')?.change.value || O.project.credits || {})});

// ---------- the Studio's page ----------

function startStudio() {
  hideGate();
  if (O.started) return;
  O.started = true;
  const s = document.createElement('script');
  s.src = 'studio/app.js';
  s.onload = wrapStudio;
  document.body.appendChild(s);
}

// the Studio's functions are globals of studio/app.js; a few get an online twist here
function wrapStudio() {
  const studioRenderEditor = window.renderEditor;
  window.renderEditor = function () { studioRenderEditor(); onlineEditorInfo(); };
  window.exportScript = exportScript;
  O.wrapped = true;
  const studioSave = window.save;
  // after a save, one history item for what changed
  window.save = async function (explicit, clearing) {
    const id = S.current, before = {...(S.project[id] || {})};
    const ok = await studioSave(explicit, clearing);
    if (ok && S.current === id) onlineEditorInfo();
    if (ok && O.canReview) for (const f of ['en', 'note']) if ((before[f] || '') !== ((S.project[id] || {})[f] || '')) history(id, f, before[f] || '', (S.project[id] || {})[f] || '');
    return ok;
  };
  // claims: line numbers and a tag on each claimed row, and the Claims tab
  const studioRowEl = window.rowEl;
  window.rowEl = function (e) {
    const b = studioRowEl(e), badge = claimBadge(e);
    if (badge) b.querySelector('.meta span:last-child').insertAdjacentHTML('afterbegin', badge + ' ');
    return b;
  };
  claimsTab();
  // the Studio writes "ROM: …" there once its page has loaded; say who is signed in instead
  const base = () => { $('#base').textContent = `Signed in as ${O.name} · script uploaded ${O.meta.made}${O.meta.uploaded ? ' by ' + O.meta.uploaded.n : ''}`; };
  const wait = setInterval(() => { if (S.entries.length) { clearInterval(wait); base(); numberLines(); listenClaims(); } }, 200);
  base();
  renderPresence();
}

// Someone else saved lines: show them, unless you are typing in that line (then offer theirs)
function liveEntries(changed) {
  if (!changed.size) return;
  for (const id of changed) {
    const p = viewOf(id), mine = S.project[id] || {};
    if (JSON.stringify(p) === JSON.stringify(mine)) continue;
    if (Object.keys(p).length) S.project[id] = p; else delete S.project[id];
    if (id === S.current) {
      if (!S.dirty) { renderEditor(); scheduleCheck(0); }
      else offerTheirs(id);
    }
    refreshRow(id);
  }
  renderTabsCounts();
}

function liveSpeakers() {
  const sp = speakerMap(), fc = faceMap();
  if (JSON.stringify(sp) === JSON.stringify(S.speakers) && JSON.stringify(fc) === JSON.stringify(S.faces)) return;
  S.speakers = sp; S.faces = fc;
  renderRows();
  if (S.current && !S.dirty) { renderEditor(); scheduleCheck(0); }
}

function offerTheirs(id) {
  const by = (O.files[O.byId[id].file].by || {})[id], p = S.project[id] || {};
  let box = $('#live-note');
  if (!box) { $('#editor h2').insertAdjacentHTML('afterend', '<div id="live-note" class="live"></div>'); box = $('#live-note'); }
  box.innerHTML = `${esc(by ? by.n : 'Someone')} saved this line while you were typing:<pre>${esc(p.en || '(no English)')}</pre>
    <button id="take-theirs">Use their text</button> or press <b>Save entry</b> to keep yours.`;
  $('#take-theirs').onclick = () => { S.dirty = false; renderEditor(); scheduleCheck(0); };
}

// the online lines under the editor's heading (redrawn on their own when suggestions or claims change)
function onlineEditorInfo() {
  const id = S.current;
  if (!id || !O.byId[id] || !$('#editor .sub')) return;
  document.querySelectorAll('#editor .online-info').forEach(el => el.remove());
  const by = (O.files[O.byId[id].file].by || {})[id];
  const others = Object.entries(O.presence).filter(([uid, p]) => uid !== O.user.uid && p.id === id && fresh(p)).map(([, p]) => p.n);
  const seed = seedOf(id), en = (S.project[id] || {}).en || '';
  $('#editor .sub').insertAdjacentHTML('afterend', `<div class="online-info"><div class="sub online-sub">${by ? `Last changed online by ${esc(by.n)}, ${esc(when(by.t))}` : 'Not changed online yet'}
    ${others.length ? ` · <b>Also on this line now: ${others.map(esc).join(', ')}</b>` : ''}
    ${en !== seed ? ` · <a href="#" id="show-seed">Last upload from the Studio</a>` : ''} · <a href="#" id="line-history">History</a></div>
    ${lineSuggestions(id)}${claimInfo(id)}</div>`);
  for (const b of document.querySelectorAll('[data-withdraw]')) b.onclick = () => withdraw(b.dataset.withdraw);
  $('#review-line')?.addEventListener('click', () => renderReview(id));
  $('#show-seed')?.addEventListener('click', ev => { ev.preventDefault(); showJob(`<h3>${esc(id)}: last upload from the Studio</h3><div class="merge-text">${esc(seed || '(no English)')}</div>`); });
  $('#line-history').onclick = ev => { ev.preventDefault(); lineHistory(id); };
  heartbeat();
}

// ---------- the Studio's /api requests, answered here ----------

const studioFetch = window.fetch.bind(window);
window.fetch = async (input, opts = {}) => {
  const url = new URL(typeof input === 'string' ? input : input.url, location.href);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return studioFetch(input, opts);
  let body = opts.body;
  if (typeof body === 'string' && body.startsWith('{')) body = JSON.parse(body);
  try {
    const [status, data, type] = await handle(url.pathname, url.searchParams, opts.method || 'GET', body);
    if (data instanceof Blob) return new Response(data, {status, headers: {'Content-Type': type}});
    return new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});
  } catch (err) {
    console.error(err);
    return new Response(JSON.stringify({error: err.message}), {status: 500, headers: {'Content-Type': 'application/json'}});
  }
};

// <img src="/api/..."> (portraits, the credits preview) cannot go through fetch, so they are swapped for data URLs
const images = new MutationObserver(list => {
  for (const m of list) {
    const imgs = m.type === 'attributes' ? [m.target] : [...m.addedNodes].flatMap(n => n.nodeType === 1 ? [...(n.tagName === 'IMG' ? [n] : []), ...n.querySelectorAll('img')] : []);
    for (const img of imgs) {
      const src = img.getAttribute('src') || '';
      if (src.startsWith('/api/')) img.src = imageUrl(new URL(src, location.href));
    }
  }
});
images.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['src']});

function imageUrl(url) {
  if (url.pathname === '/api/portrait') {
    const b64 = O.portraits[url.searchParams.get('face')];
    return b64 ? 'data:image/png;base64,' + b64 : '';
  }
  if (url.pathname === '/api/credits.png') {
    const cfg = credits(), [script] = creditsCompose(cfg);
    return creditsPng(creditsLines(script || O.layout.credits.base), +(url.searchParams.get('first') || 0), +(url.searchParams.get('count') || 0) || null);
  }
  return '';
}

async function handle(path, q, method, body) {
  switch (path) {
    case '/api/config':
      return [200, {application: 'fm2089-online-studio', started: 0, rom: 'online', rom_problem: null, rom_dir: '',
        groups: O.layout.groups, project: 'the shared online script', author: O.name, screen_width: O.layout.screen_width,
        stat_icons: (O.project.settings || {}).stat_icons ?? true, controls: O.layout.controls}];
    case '/api/catalog':
      return [200, {entries: allEntries(), project: projectMap(), speakers: speakerMap(), default_speakers: O.layout.default_speakers,
        faces: faceMap(), default_faces: O.layout.default_faces, portraits: Object.keys(O.portraits)}];
    case '/api/font': return [200, O.font];
    case '/api/stamp': case '/api/job': return [200, {}];
    case '/api/check': {
      const r = check(body.id, body.en || '', speakerMap());
      delete r.tokens;
      return [200, r];
    }
    case '/api/entry': return [200, await saveEntry(body)];
    case '/api/speaker': return [200, await saveSpeaker(body)];
    case '/api/credits':
      if (method === 'POST') return [200, await saveCredits(body)];
      return [200, creditsState(credits())];
    case '/api/validate': return [200, {problems: validate()}];
    case '/api/settings': {
      for (const [k, v] of Object.entries(body)) await fb.updateDoc(ref('meta', 'project'), new fb.FieldPath('settings', k), v);
      return [200, {ok: true, settings: {...(O.project.settings || {}), ...body}}];
    }
    case '/api/import/preview': case '/api/import/apply': {
      let plan;
      try { plan = importPlan(body.files); } catch (err) { return [200, {ok: false, error: err.message}]; }
      if (path.endsWith('preview')) return [200, {ok: true, ...plan}];
      const changed = await importApply(plan, body.choices || {});
      return [200, {ok: true, changed, backup: null}];
    }
    default: return [404, {error: 'not available online'}];
  }
}

// ---------- checks (studio_core.Catalog.check and msgcodec, in JavaScript) ----------

function tokens(text) {
  const toks = [], problems = [], [FIRST, LAST, WITH_ARG_LAST] = O.layout.control_range;
  text = text.replace(/\r\n?/g, '\n');
  for (let i = 0; i < text.length;) {
    const ch = text[i];
    if (ch === '\n') { toks.push(['c', 0xE8FF]); i++; continue; }
    if (ch === '«') {
      const end = text.indexOf('»', i + 1);
      if (end < 0) { problems.push('A « tag is not closed with »'); i++; continue; }
      const raw = text.slice(i + 1, end), body = raw.trim().toUpperCase();
      const hex = s => /^[0-9A-F]+$/.test(s) ? parseInt(s, 16) : NaN;
      let ok = false;
      if (body.startsWith('G:')) {
        const g = hex(body.slice(2));
        if (g > 0 && g < O.fontWidths.length) { toks.push(['g', g]); ok = true; }
      } else {
        const [code, ...rest] = body.split(':'), arg = rest.join(':'), cp = hex(code);
        if (cp >= FIRST && cp <= LAST) {
          if (cp <= WITH_ARG_LAST) { if (arg && !isNaN(hex(arg))) { toks.push(['c', cp, hex(arg)]); ok = true; } }
          else if (!arg) { toks.push(['c', cp]); ok = true; }
        }
      }
      if (!ok) problems.push(`Unknown tag «${raw}»`);
      i = end + 1; continue;
    }
    const g = O.font.lookup[ch];
    if (g === undefined) {
      const hint = '“”'.includes(ch) ? ' (use a straight " instead)' : '‘’'.includes(ch) ? " (use a straight ' instead)" : '';
      problems.push(`The game font has no "${ch}"${hint}`);
    } else toks.push(['g', g]);
    i++;
  }
  return [toks, problems];
}

function lineWidths(toks) {
  const widths = []; let w = 0;
  for (const t of toks) {
    if (t[0] === 'g') { const gw = O.fontWidths[t[1]] || 0; w += gw ? gw + O.font.spacing : 0; }
    else if (t[1] === 0xE8FF) { widths.push(w); w = 0; }
  }
  widths.push(w);
  return widths;
}

function fullText(e, text, speakers) {
  if (!e.speaker) return [text, null];
  let name = speakers[e.speaker] || O.layout.default_speakers[e.speaker], warning = null;
  if (!name) { name = e.speaker; warning = `The speaker "${e.speaker}" has no English name yet, so the Japanese name is used`; }
  return [`${name}:` + (e.speaker_own_line ? '\n' : ' ') + text, warning];
}

function check(id, text, speakers) {
  const e = O.byId[id].e, body = text, [hero, heroDefault] = O.layout.hero;
  const [full, speakerWarning] = fullText(e, text, speakers);
  const [toks, errors] = tokens(full);
  const widths = lineWidths(tokens(full.split(hero).join(heroDefault))[0]);
  const warnings = speakerWarning ? [speakerWarning] : [];
  const limit = e.limit, screen = O.layout.screen_width, dialogue = O.layout.dialogue_groups.includes(e.group);
  widths.forEach((w, n) => {
    if (w > screen) errors.push(`Line ${n + 1} is ${w} px, wider than the DS screen (${screen} px)`);
    else if (w > limit) warnings.push(dialogue ? `Line ${n + 1} is ${w} px; the text box wraps mid-word past ${limit} px`
                                               : `Line ${n + 1} is ${w} px; the widest Japanese line in this file is ${limit} px`);
  });
  if (widths.length > e.lines) warnings.push(`${widths.length} lines; the Japanese has ${e.lines}`);
  const jpCodes = [...new Set(e.body.match(/«(?!g:)[^»]+»/g) || [])].sort();
  const enCodes = new Set(body.toUpperCase().match(/«(?!g:)[^»]+»/g) || []);
  const missing = jpCodes.filter(c => !enCodes.has(c.toUpperCase()));
  if (missing.length) warnings.push('Codes from the Japanese are missing: ' + missing.join(' '));
  return {tokens: toks, errors, warnings, widths, limit, full};
}

function validate() {
  const problems = [], speakers = speakerMap();
  for (const e of allEntries()) {
    const p = S.project[e.id];
    if (!p || p.en === undefined) continue;
    const r = check(e.id, p.en, speakers);
    for (const m of r.errors) problems.push({id: e.id, level: 'error', message: m});
    if (!e.graphic) for (const m of r.warnings) problems.push({id: e.id, level: 'warning', message: m});
  }
  const [, creditProblems] = creditsCompose(credits());
  for (const [level, message] of creditProblems) problems.push({id: 'Credits', level, message});
  return problems;
}

// ---------- saving (studio_core.Project.set and the server's /api/entry and /api/speaker) ----------

function projectSet(cur, {en, note, done, mtl, edited, hidden}) {
  cur = {...cur};
  if (hidden === '') delete cur.hidden; else if (hidden !== undefined && hidden !== null) cur.hidden = !!hidden;
  if (en !== undefined && en !== null && en !== (cur.en || '')) { edited = true; mtl = false; }
  for (const [k, v] of [['mtl', mtl], ['edited', edited]]) { if (v) cur[k] = true; else if (v !== undefined && v !== null) delete cur[k]; }
  if (en !== undefined && en !== null) { if (en === '') delete cur.en; else cur.en = en; }
  if (note !== undefined && note !== null) { if (note === '') delete cur.note; else cur.note = note; }
  if (done !== undefined && done !== null) { if (done) cur.done = true; else delete cur.done; }
  return cur;
}

// the changes to write for lines whose new entry is `after`
function entryUpdates(id, after, args, who = {n: O.name, e: O.email}) {
  const before = entryOf(id);
  let changed = false;
  for (const f of FIELDS) {
    if (JSON.stringify(before[f]) === JSON.stringify(after[f])) continue;
    args.push(new fb.FieldPath(f, id), after[f] === undefined ? fb.deleteField() : after[f]);
    changed = true;
  }
  if (changed) args.push(new fb.FieldPath('by', id), {...who, t: now()});
  return changed;
}

async function saveEntry(data) {
  const id = data.id;
  if (!O.byId[id]) return {error: `unknown entry ${id}`};
  let res = {errors: [], warnings: [], widths: []};
  if (data.en) { res = check(id, data.en, speakerMap()); delete res.tokens; }
  if (res.errors.length && !data.force) return {ok: false, ...res};
  const e = O.byId[id].e;
  const hidden = !('hidden' in data) ? undefined : !!data.hidden === !!e.unused ? '' : data.hidden;
  const after = projectSet(viewOf(id), {en: data.en, note: data.note, done: data.done, mtl: data.mtl, edited: data.edited, hidden});
  if (!O.canReview) { await suggestEntry(id, after); return {ok: true, entry: after, ...res}; }
  const args = [];
  if (entryUpdates(id, after, args)) await fb.updateDoc(ref('files', O.byId[id].file), ...args);
  return {ok: true, entry: after, ...res};
}

async function saveSpeaker(data) {
  const jp = data.jp;
  if ('face' in data) {
    const face = data.face || '';
    if (face && face !== '-' && !O.portraits[face]) return {ok: false, errors: [`unknown portrait ${face}`]};
    if (!O.canReview) { await suggest('face', jp, face, (O.speakers.faces || {})[jp] || ''); return {ok: true, faces: faceMap()}; }
    const old = (O.speakers.faces || {})[jp] || '';
    await fb.updateDoc(ref('meta', 'speakers'), new fb.FieldPath('faces', jp), face || fb.deleteField());
    history(jp, 'face', old, face);
    const faces = faceMap(); if (face) faces[jp] = face; else delete faces[jp];
    return {ok: true, faces};
  }
  const en = (data.en || '').trim();
  if (en) { const [, problems] = tokens(en); if (problems.length) return {ok: false, errors: problems}; }
  if (!O.canReview) { await suggest('speaker', jp, en, (O.speakers.en || {})[jp] || ''); return {ok: true, speakers: speakerMap()}; }
  const old = (O.speakers.en || {})[jp] || '';
  await fb.updateDoc(ref('meta', 'speakers'), new fb.FieldPath('en', jp), en || fb.deleteField(),
                     new fb.FieldPath('by', jp), {n: O.name, e: O.email, t: now()});
  history(jp, 'speaker', old, en);
  const speakers = speakerMap(); if (en) speakers[jp] = en; else delete speakers[jp];
  return {ok: true, speakers};
}

function history(id, field, old, value, who = O.name) {
  if (old === value) return;
  fb.addDoc(fb.collection(db, 'history'), {id, field, old, new: value, n: who, e: O.email, t: now()}).catch(() => {});
}

// ---------- credits (credits.py in JavaScript) ----------

function creditsSettings(cfg) {
  cfg = {...O.layout.credits.default, ...cfg};
  cfg.roles = (cfg.roles || []).map(r => ({role: String(r.role ?? ''), names: String(r.names ?? '')}));
  return cfg;
}
function plain(text) {
  text = text.replace(/[’‘]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, '-').replace(/…/g, '...');
  return [...text].map(c => c.charCodeAt(0) < 128 ? c : (c.normalize('NFKD').replace(/[^\x00-\x7f]/g, '') || c)).join('');
}
const escapeCredits = t => t.replace(/</g, '\0lt\x01').replace(/>/g, '\0gt\x01').replace(/\0/g, '<').replace(/\x01/g, '>');
function teamLines(cfg) {
  const lines = [];
  if (cfg.title.trim()) lines.push([cfg.title.trim(), true]);
  if (cfg.group.trim()) lines.push([cfg.group.trim(), false]);
  const roles = cfg.roles.map(r => [r.role.trim(), r.names.split(/\r\n|\r|\n/).map(n => n.trim()).filter(Boolean)]).filter(([, n]) => n.length);
  if (!roles.length) return [];
  for (const [role, names] of roles) {
    lines.push(['', false]);
    if (role) lines.push([role, true]);
    for (const n of names) lines.push([cfg.capitals ? n.toUpperCase() : n, false]);
  }
  return lines.map(([t, h]) => [plain(t), h]);
}
const teamScript = cfg => teamLines(cfg).map(([t, h]) => (h && t ? '<color 1>' : '') + escapeCredits(t) + '<br>').join('\r\n');
function insertAt(script, cfg) {
  if (cfg.position === 'start') {
    let m = /^<color 1>Executive Producer/m.exec(script);
    if (m) return m.index;
    m = /^(?!<comment|<totaltime|<bgm|<img|<br>|\s*$).*<br>.*$/m.exec(script);
    return m ? m.index + m[0].length + 2 : 0;
  }
  for (const rx of [/^Copyright<br>/m, /^<bgm stop>/m, /^<end>/m]) { const m = rx.exec(script); if (m) return m.index; }
  return script.length;
}
function creditsLines(script) {
  const out = []; let cur = '', color = 0;
  for (const part of script.replace(/<comment\b[^>]*>/g, '').split(/(<[^<>]*>)/)) {
    if (!part.startsWith('<')) { cur += part.replace(/[\r\n]/g, ''); continue; }
    const tag = part.slice(1, -1).split(/\s+/).filter(Boolean), name = (tag[0] || '').toLowerCase();
    if (name === 'br') { out.push([cur.trim(), color]); cur = ''; color = 0; }
    else if (name === 'color' && tag.length > 1 && /^\d+$/.test(tag[1])) color = +tag[1];
    else if (name === 'lt' || name === 'gt') cur += name === 'lt' ? '<' : '>';
  }
  return out;
}
function creditsCompose(cfg) {
  const base = O.layout.credits.base, width = O.layout.credits.width;
  let script = cfg.script ? cfg.script : base;
  const team = teamScript(cfg);
  if (team) { const at = insertAt(script, cfg); script = script.slice(0, at) + team + '\r\n' + '<br>\r\n<br>\r\n' + script.slice(at); }
  if (script === base) return [null, []];
  const problems = [];
  creditsLines(script).forEach(([text], i) => {
    const bad = [...new Set([...text].filter(c => !(c.charCodeAt(0) >= 32 && c.charCodeAt(0) < 127)))].sort();
    if (bad.length) problems.push(['error', `Credits line ${i + 1} "${text}": the credits font has no ${bad.join(' ')}`]);
    if (text.length > width) problems.push(['error', `Credits line ${i + 1} "${text}" is ${text.length} characters; ${width} fit across the screen`]);
  });
  return [script, problems];
}
function creditsState(cfg) {
  cfg = creditsSettings(cfg);
  const [script, problems] = creditsCompose(cfg), base = O.layout.credits.base;
  const roll = creditsLines(script || base), team = teamLines(cfg).map(([t]) => t);
  let at = null;
  if (team.length) for (let i = 0; i < roll.length; i++) if (team.every((t, k) => roll[i + k] && roll[i + k][0] === t)) { at = i; break; }
  return {credits: cfg, positions: O.layout.credits.positions, script: cfg.script || base, edited_script: !!cfg.script,
    lines: roll.length, team_at: at, team_lines: team.length, width: O.layout.credits.width, changed: script !== null,
    problems: problems.map(([level, message]) => ({level, message}))};
}
async function saveCredits(data) {
  const cfg = creditsSettings(credits());
  for (const k of ['position', 'title', 'group', 'capitals', 'roles', 'script']) if (k in data) cfg[k] = data[k];
  if (!(cfg.position in O.layout.credits.positions)) cfg.position = O.layout.credits.default.position;
  if (cfg.script === O.layout.credits.base) cfg.script = null;
  if (!O.canReview) {
    await suggest('credits', '', cfg, O.project.credits || {});
    return {ok: true, ...creditsState(cfg)};
  }
  await fb.setDoc(ref('meta', 'project'), {credits: cfg, creditsBy: {n: O.name, e: O.email, t: now()}}, {merge: true});
  O.project = {...O.project, credits: cfg};
  history('Credits', 'credits', '', 'changed');
  return {ok: true, ...creditsState(cfg)};
}
function creditsPng(roll, first, count) {
  const c = O.layout.credits, W = c.width * 8;
  if (!O.staffTiles) O.staffTiles = Uint8Array.from(atob(c.tiles), ch => ch.charCodeAt(0));
  roll = count ? roll.slice(first, first + count) : roll.slice(first);
  const cv = document.createElement('canvas'); cv.width = W; cv.height = Math.max(1, roll.length) * 16;
  const ctx = cv.getContext('2d'), img = ctx.createImageData(cv.width, cv.height);
  for (let i = 3; i < img.data.length; i += 4) img.data[i] = 255;
  roll.forEach(([text, color], row) => {
    const pal = c.palettes[color ? 1 : 0], x0 = Math.floor((W - text.length * 8) / 2);
    [...text].forEach((ch, k) => {
      const g = ch.charCodeAt(0) - 32;
      if (g < 0 || g >= 96) return;
      for (let y = 0; y < 16; y++) for (let x = 0; x < 8; x++) {
        const tile = (Math.floor(g / 16) * 2 + (y >> 3)) * 16 + g % 16, b = O.staffTiles[tile * 32 + (y % 8) * 4 + (x >> 1)];
        const v = x & 1 ? b >> 4 : b & 15, X = x0 + k * 8 + x;
        if (!v || X < 0 || X >= W) continue;
        const o = ((row * 16 + y) * W + X) * 4;
        img.data[o] = pal[v][0]; img.data[o + 1] = pal[v][1]; img.data[o + 2] = pal[v][2];
      }
    });
  });
  ctx.putImageData(img, 0, 0);
  return cv.toDataURL('image/png');
}

// ---------- importing scripts into the shared script (scriptio.py in JavaScript) ----------

const KINDS = {en: 'English', note: 'note', done: 'done', hidden: 'hidden', speaker: 'name', face: 'portrait', credits: 'credits'};
const ENTRY_KINDS = ['en', 'note', 'done', 'hidden'];
const HEAD_SPEAKER = 'Speaker name: ', HEAD_FACE = 'Portrait: ', HEAD_CREDITS = 'Closing credits';
const BLOCK_RX = /^(Japanese|(?:Old|New) (?:English|note|done|hidden|name|portrait|credits)):\s*$/;

// flags and credits as text, the same way scriptio.py writes them: done is 'Done' or '', hidden 'Hidden', 'Shown'
// or '' (the Studio decides), credits the Credits settings as JSON with sorted keys ('' = the game's own)
const flagText = (kind, p) => kind === 'done' ? (p.done ? 'Done' : '') : p.hidden === true ? 'Hidden' : p.hidden === false ? 'Shown' : '';
const sortKeys = v => Array.isArray(v) ? v.map(sortKeys) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sortKeys(v[k])])) : v;
function creditsText(cfg) {
  if (!cfg || !Object.keys(cfg).length) return '';
  cfg = {...O.layout.credits.default, ...cfg};
  cfg.roles = (cfg.roles || []).map(r => ({role: String(r.role ?? ''), names: String(r.names ?? '')}));
  return JSON.stringify(sortKeys(cfg), null, 1);
}
const FENCE_RX = /^(~{3,}|`{3,})\s*\w*\s*$/;
const keyOf = k => k.join('\t');

function current([kind, name]) {
  if (kind === 'en' || kind === 'note') return (S.project[name] || {})[kind] || '';
  if (kind === 'done' || kind === 'hidden') return flagText(kind, S.project[name] || {});
  if (kind === 'credits') return creditsText(mySuggestion('credits', '')?.change.value || O.project.credits);
  return ((kind === 'speaker' ? S.speakers : S.faces) || {})[name] || '';
}

function parseMd(text) {
  const changes = [], lines = text.replace(/\r\n?/g, '\n').replace(/^﻿/, '').split('\n');
  let head = null, found = {};
  const flush = () => {
    if (!head) return;
    const kinds = {entry: [['English', 'en'], ['note', 'note'], ['done', 'done'], ['hidden', 'hidden']], speaker: [['name', 'speaker']],
      face: [['portrait', 'face']], credits: [['credits', 'credits']]}[head[0]];
    for (const [word, kind] of kinds) if ('New ' + word in found) changes.push([[kind, head[1]], found['Old ' + word] ?? null, found['New ' + word]]);
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('## ')) {
      flush();
      const title = line.slice(3).trim(); found = {};
      head = title.startsWith(HEAD_SPEAKER) ? ['speaker', title.slice(HEAD_SPEAKER.length)]
        : title.startsWith(HEAD_FACE) ? ['face', title.slice(HEAD_FACE.length)] : title === HEAD_CREDITS ? ['credits', ''] : ['entry', title];
      continue;
    }
    const m = BLOCK_RX.exec(line);
    if (m && head && i + 1 < lines.length && FENCE_RX.test(lines[i + 1])) {
      const f = FENCE_RX.exec(lines[i + 1])[1];
      let j = i + 2;
      while (j < lines.length && lines[j].trim() !== f) j++;
      found[m[1]] = lines.slice(i + 2, j).join('\n');
      i = j;
    }
  }
  flush();
  return changes;
}

function valuesOf(data) {
  const out = [];
  for (const [sid, p] of Object.entries(data.entries || {})) {
    for (const f of ['en', 'note']) if (p[f]) out.push([[f, sid], null, p[f]]);
    for (const f of ['done', 'hidden']) if (flagText(f, p)) out.push([[f, sid], null, flagText(f, p)]);
  }
  if (creditsText(data.credits)) out.push([['credits', ''], null, creditsText(data.credits)]);
  for (const [kind, field] of [['speaker', 'speakers'], ['face', 'faces']]) for (const [jp, v] of Object.entries(data[field] || {})) if (v) out.push([[kind, jp], null, v]);
  return out;
}

// a tab-separated file (Python's csv rules: quoted fields may hold tabs, newlines and "" for a quote)
function tsvRows(text) {
  const rows = []; let row = [], field = '', quoted = false, i = 0, start = true;
  text = text.replace(/^﻿/, '');
  while (i < text.length) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i += 2; continue; }
      if (c === '"') { quoted = false; i++; continue; }
      field += c; i++; continue;
    }
    if (c === '"' && start) { quoted = true; start = false; i++; continue; }
    if (c === '\t') { row.push(field); field = ''; start = true; i++; continue; }
    if (c === '\n' || c === '\r') { row.push(field); rows.push(row); row = []; field = ''; start = true; i += c === '\r' && text[i + 1] === '\n' ? 2 : 1; continue; }
    field += c; start = false; i++;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function tsvChanges(text) {
  const changes = [], speakers = speakerMap();
  for (const row of tsvRows(text)) {
    if (!row.length || row[0] === 'stringID') continue;
    const sid = row[0].trim();
    if (!O.byId[sid]) { changes.push([['en', sid], null, '']); continue; }
    const e = O.byId[sid].e;
    let en = row.length > 1 ? row[1] : '';
    const speakerEn = row.length > 5 && e.speaker ? row[5] : '';
    if (e.speaker) {
      for (const prefix of [e.speaker + '：', e.speaker + ':', (speakerEn || speakers[e.speaker] || '\0') + ':']) {
        if (en.startsWith(prefix)) { en = en.slice(prefix.length).replace(/^ +/, ''); if (en.startsWith('\n') && e.speaker_own_line) en = en.slice(1); break; }
      }
    }
    if (en === e.jp || en === e.body) en = '';
    const note = row.length > 3 ? row[3] : '';
    if (en) changes.push([['en', sid], null, en]);
    if (note) changes.push([['note', sid], null, note]);
    if (e.speaker && speakerEn) changes.push([['speaker', e.speaker], null, speakerEn]);
  }
  return changes;
}

function parseScript(text) {
  const body = text.replace(/^[﻿ \r\n]+/, '');
  if (body.startsWith('{')) return valuesOf(JSON.parse(body));
  if (body.startsWith('# FM2089 script changes') || body.slice(0, 5000).includes('\n## ')) return parseMd(text);
  return tsvChanges(text);
}

function importPlan(files) {
  const order = new Map(allEntries().map((e, i) => [e.id, i])), rank = {speaker: 0, face: 1, en: 2, note: 2, done: 2, hidden: 2, credits: 3};
  const sortKey = k => [rank[k[0]], ENTRY_KINDS.includes(k[0]) ? (order.get(k[1]) ?? order.size) : 0, k[1], Math.max(0, ENTRY_KINDS.indexOf(k[0]))];
  const cmp = (a, b) => { const x = sortKey(a), y = sortKey(b); for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1; return 0; };
  const offers = new Map(), unknown = new Set();
  for (const {name, text} of files) {
    let changes;
    try { changes = parseScript(text); } catch (err) { throw new Error(`${name}: ${err.message}`); }
    for (const [key, old, value] of changes) {
      if (ENTRY_KINDS.includes(key[0]) && !O.byId[key[1]]) { unknown.add(key[1]); continue; }
      if (value !== current(key)) {
        const k = keyOf(key);
        if (!offers.has(k)) offers.set(k, {key, list: []});
        offers.get(k).list.push([name, old, value]);
      }
    }
  }
  const auto = [], conflicts = [];
  for (const {key, list} of [...offers.values()].sort((a, b) => cmp(a.key, b.key))) {
    const cur = current(key), options = new Map();
    for (const [name, , value] of list) { if (!options.has(value)) options.set(value, []); options.get(value).push(name); }
    const stale = list.filter(([, old]) => old !== null && old !== cur).map(([name]) => name);
    const item = {key, kind: KINDS[key[0]], name: key[1], current: cur};
    if (ENTRY_KINDS.includes(key[0]) && O.byId[key[1]]) { const e = O.byId[key[1]].e; item.jp = e.body; item.speaker = e.speaker || ''; }
    if (options.size === 1 && !stale.length) {
      const [[value, names]] = options;
      auto.push({...item, new: value, files: names});
    } else {
      let why = options.size > 1 ? 'These files change it in different ways.' : `Someone changed this line too, after ${stale.join(', ')} was made.`;
      if (stale.length && options.size > 1) why += ` It was also changed after ${stale.join(', ')} was made.`;
      conflicts.push({...item, why, options: [...options].map(([value, names]) => ({value, files: names}))});
    }
  }
  return {auto, conflicts, unknown: [...unknown].sort()};
}

async function importApply(plan, choices) {
  const picks = [...plan.auto.map(i => [i.key, i.new])];
  for (const item of plan.conflicts) {
    const pick = choices[keyOf(item.key)];
    if (Number.isInteger(pick) && pick >= 0 && pick < item.options.length) picks.push([item.key, item.options[pick].value]);
  }
  const perFile = {}, speakerArgs = [];
  const pending = {};
  let creditsPick;
  for (const [[kind, name], value] of picks) {
    if (ENTRY_KINDS.includes(kind)) {
      const before = pending[name] || viewOf(name);
      const change = kind === 'done' ? {done: value === 'Done'} : kind === 'hidden' ? {hidden: {Hidden: true, Shown: false}[value] ?? ''} : {[kind]: value};
      pending[name] = projectSet(before, change);
    } else if (kind === 'credits') {
      creditsPick = value ? JSON.parse(value) : {};
    } else {
      speakerArgs.push(new fb.FieldPath(kind === 'speaker' ? 'en' : 'faces', name), value || fb.deleteField());
    }
  }
  if (!O.canReview) {
    for (const [id, after] of Object.entries(pending)) await suggestEntry(id, after);
    for (const [[kind, name], value] of picks) {
      if (kind === 'speaker') await suggest('speaker', name, value, (O.speakers.en || {})[name] || '');
      if (kind === 'face') await suggest('face', name, value, (O.speakers.faces || {})[name] || '');
    }
    if (creditsPick) await suggest('credits', '', creditsPick, O.project.credits || {});
    return picks.length;
  }
  for (const [id, after] of Object.entries(pending)) entryUpdates(id, after, perFile[O.byId[id].file] ||= []);
  const writes = Object.entries(perFile).filter(([, args]) => args.length);
  for (let i = 0; i < writes.length; i += 20) {
    const batch = fb.writeBatch(db);
    for (const [file, args] of writes.slice(i, i + 20)) batch.update(ref('files', file), ...args);
    await batch.commit();
  }
  if (speakerArgs.length) await fb.updateDoc(ref('meta', 'speakers'), ...speakerArgs);
  if (creditsPick) await fb.setDoc(ref('meta', 'project'), {credits: creditsPick, creditsBy: {n: O.name, e: O.email, t: now()}}, {merge: true});
  history('Import', 'import', '', `${picks.length} changes imported`);
  return picks.length;
}

// ---------- Export script: the lines changed online since the last upload, as the Studio's script .md ----------

function fence(text) { const runs = (text.match(/~{3,}/g) || []).map(r => r.length); return '~'.repeat(Math.max(2, ...runs) + 1); }
function block(label, text) { const f = fence(text); return [`${label}:`, f + 'text', ...(text ? [text] : []), f, '']; }
const stamp = () => { const d = new Date(), p = n => String(n).padStart(2, '0'); return [`${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`, `${p(d.getHours())}${p(d.getMinutes())}`, `${p(d.getHours())}:${p(d.getMinutes())}`]; };

function changesMd() {
  const out = []; let count = 0;
  const pairs = [['Speaker name: ', 'name', O.speakers.seed || {}, O.speakers.en || {}], ['Portrait: ', 'portrait', O.speakers.facesSeed || {}, O.speakers.faces || {}]];
  for (const [head, word, seed, cur] of pairs) for (const jp of Object.keys({...seed, ...cur}).sort()) {
    if ((seed[jp] || '') === (cur[jp] || '')) continue;
    out.push('---', '', `## ${head}${jp}`, '', ...block(`Old ${word}`, seed[jp] || ''), ...block(`New ${word}`, cur[jp] || ''));
    count++;
  }
  for (const e of allEntries()) {
    const parts = [], p = entryOf(e.id), seedFlags = seedFlagsOf(e.id);
    for (const [field, word] of [['en', 'English'], ['note', 'note'], ['done', 'done'], ['hidden', 'hidden']]) {
      const old = field === 'en' || field === 'note' ? seedOf(e.id, field) : flagText(field, seedFlags);
      const cur = field === 'en' || field === 'note' ? p[field] || '' : flagText(field, p);
      if (old !== cur) { parts.push(...block(`Old ${word}`, old), ...block(`New ${word}`, cur)); count++; }
    }
    if (!parts.length) continue;
    out.push('---', '', `## ${e.id}`, '');
    if (e.speaker) out.push(`Speaker: ${e.speaker} (${(O.speakers.en || {})[e.speaker] || O.layout.default_speakers[e.speaker] || 'no English name'})`, '');
    out.push(...block('Japanese', e.body || ''), ...parts);
  }
  const oldCredits = creditsText(O.project.creditsSeed), newCredits = creditsText(O.project.credits);
  if (oldCredits !== newCredits) {
    out.push('---', '', `## ${HEAD_CREDITS}`, '', ...block('Old credits', oldCredits), ...block('New credits', newCredits));
    count++;
  }
  const [day, , clock] = stamp();
  const head = ['# FM2089 script changes', '', '- From: the online script', `- Exported: ${day} ${clock}`,
    `- Changes since: the online script's last upload (${O.meta.made})`, `- Changes: ${count}`, '',
    'Load this file with **Import script** (or several at once with **Import multiple**) in the FM2089 Translation Studio.',
    'Only the "New" blocks are read in; "Old" is what the sender started from, so the Studio can tell when both of you changed a line.',
    'An empty done block means not marked done; an empty hidden block means the Studio decides whether the line is in the game.', ''];
  return [[...head, ...out].join('\n').trimEnd() + '\n', count];
}

async function exportScript() {
  if (S.dirty && !(await save(true))) return;
  const [text, count] = changesMd();
  if (!count) { showJob(`<h3>Nothing to export</h3><p>No line differs from the last upload from the Studio (${esc(O.meta.made)}).</p>`); return; }
  const [day, time] = stamp(), name = `FM2089 online script - ${day} ${time}.md`;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], {type: 'text/markdown'})); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  showJob(`<h3 class="ok">Script exported</h3><p>${fmt(count)} change${count === 1 ? '' : 's'} since the last upload from the Studio (${esc(O.meta.made)}),
    downloaded as <code>${esc(name)}</code>. In the desktop Studio, click <b>Import script</b> and pick it: lines you also changed there since that
    upload are shown so you can pick which text to keep. Then build the patch as usual.</p>`);
}

// ---------- suggestions: team members' changes wait for an admin's review ----------
// suggestions/{uid~kind~id}: one per person and line (or speaker, portrait, the credits); change = what they want,
// base = what the script had when they asked. An admin accepts it (maybe after editing it) or rejects it, with a note
// the author reads in their inbox.

const suggestionId = (kind, id, uid = O.user.uid) => `${uid}~${kind}~${encodeURIComponent(id)}`;
const ENTRY_FIELDS = ['en', 'note', 'done', 'hidden'];
const fieldValue = (f, p) => f === 'done' ? !!p.done : f === 'hidden' ? (p.hidden === undefined ? '' : p.hidden) : p[f] || '';
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

async function suggestEntry(id, after) {
  const now_ = entryOf(id), change = {}, base = {};
  for (const f of ENTRY_FIELDS) if (!same(fieldValue(f, after), fieldValue(f, now_))) { change[f] = fieldValue(f, after); base[f] = fieldValue(f, now_); }
  const sid = suggestionId('entry', id);
  if (!Object.keys(change).length) { if (O.pending[sid]) await fb.deleteDoc(ref('suggestions', sid)); return; }
  await fb.setDoc(ref('suggestions', sid), {uid: O.user.uid, e: O.email, n: O.name, kind: 'entry', id, file: O.byId[id].file, change, base, status: 'pending', t: now()});
}

async function suggest(kind, id, value, base) {
  const sid = suggestionId(kind, id);
  if (same(value || '', base || '') || (kind === 'credits' && creditsText(value) === creditsText(base))) {
    if (O.pending[sid]) await fb.deleteDoc(ref('suggestions', sid));
    return;
  }
  await fb.setDoc(ref('suggestions', sid), {uid: O.user.uid, e: O.email, n: O.name, kind, id, change: {value}, base: {value: base}, status: 'pending', t: now()});
}

async function withdraw(sid) {
  if (!confirm('Withdraw this suggestion? The line goes back to the shared script\'s text.')) return;
  await fb.deleteDoc(ref('suggestions', sid));
}

// a suggested value as words
function shown(f, v) {
  if (f === 'done') return v ? 'Marked done' : 'Not marked done';
  if (f === 'hidden') return v === true ? 'Not in game (hidden)' : v === false ? 'In game' : 'Studio decides';
  return v;
}
const FIELD_WORDS = {en: 'English', note: 'Note', done: 'Done', hidden: 'In game', value: ''};

function lineSuggestions(id) {
  const list = Object.entries(O.pending || {}).filter(([, x]) => x.kind === 'entry' && x.id === id);
  if (!list.length) return '';
  return `<div class="suggestions">${list.map(([sid, x]) => {
    const what = Object.entries(x.change).map(([f, v]) => `<div><small>${FIELD_WORDS[f]}</small>${textBox(String(shown(f, v)), 'new')}</div>`).join('');
    return x.uid === O.user.uid
      ? `<div class="suggestion mine"><b>Your suggestion is waiting for review.</b> You see it here; the rest of the team sees the shared text until an admin accepts it.
         <button data-withdraw="${esc(sid)}">Withdraw</button></div>`
      : `<div class="suggestion"><b>${esc(x.n)} suggested</b> <span class="muted">${esc(when(x.t))}</span>${what}</div>`;
  }).join('')}${O.canReview && list.some(([, x]) => x.uid !== O.user.uid) ? '<button id="review-line" class="primary">Review this line</button>' : ''}</div>`;
}

function livePending(touched) {
  let speakers = false;
  for (const key of touched) {
    const [kind, id] = key.split('\t');
    if (kind === 'speaker' || kind === 'face') { speakers = true; continue; }
    if (kind !== 'entry' || !O.byId[id]) continue;
    const p = viewOf(id);
    if (!same(p, S.project[id] || {})) { if (Object.keys(p).length) S.project[id] = p; else delete S.project[id]; refreshRow(id); }
    if (id === S.current) { if (S.dirty) onlineEditorInfo(); else { renderEditor(); scheduleCheck(0); } }
  }
  if (speakers) liveSpeakers();
  renderTabsCounts();
}

function renderCounts() {
  const waiting = Object.values(O.pending || {}), mineWaiting = waiting.filter(x => x.uid === O.user?.uid).length;
  const unseen = (O.mine || []).filter(x => !x.seen).length;
  const review = waiting.filter(x => x.uid !== O.user?.uid).length;
  $('#review').textContent = review ? `Review (${fmt(review)})` : 'Review';
  $('#review').classList.toggle('primary', !!review);
  $('#inbox').textContent = unseen ? `Inbox (${fmt(unseen)} new)` : mineWaiting ? `Inbox (${fmt(mineWaiting)} waiting)` : 'Inbox';
  $('#inbox').classList.toggle('primary', !!unseen);
}

function suggestionTitle(x) {
  if (x.kind === 'entry') return O.byId[x.id] ? `<a href="#" data-goto="${esc(x.id)}">${esc(x.id)}</a>` : esc(x.id);
  if (x.kind === 'credits') return 'Closing credits';
  return `${x.kind === 'speaker' ? 'Speaker name' : 'Portrait'}: ${esc(x.id)}`;
}
const faceImg = f => f && f !== '-' && O.portraits[f] ? `<img class="face" alt="${esc(f)}" src="data:image/png;base64,${O.portraits[f]}">` : `<span class="muted">${f === '-' ? 'No portrait' : 'Default portrait'}</span>`;
function creditsSummary(cfg) {
  if (!cfg || !Object.keys(cfg).length) return "The game's own credits";
  cfg = creditsSettings(cfg);
  return teamLines(cfg).map(([t]) => t).join('\n') || '(no team section)';
}
function currentOf(x) {
  if (x.kind === 'entry') { const p = entryOf(x.id); return Object.fromEntries(Object.keys(x.change).map(f => [f, fieldValue(f, p)])); }
  if (x.kind === 'speaker') return {value: (O.speakers.en || {})[x.id] || ''};
  if (x.kind === 'face') return {value: (O.speakers.faces || {})[x.id] || ''};
  return {value: O.project.credits || {}};
}

// ---------- the admin's review ----------

$('#review').onclick = () => renderReview();
function renderReview(onlyId) {
  const order = new Map(allEntries().map((e, i) => [e.id, i]));
  const rank = x => x.kind === 'entry' ? order.get(x.id) ?? 1e9 : x.kind === 'credits' ? 2e9 : -1;
  const items = Object.entries(O.pending || {}).filter(([, x]) => x.uid !== O.user.uid && (!onlyId || x.id === onlyId))
    .sort(([, a], [, b]) => rank(a) - rank(b) || (a.t?.toMillis?.() || 0) - (b.t?.toMillis?.() || 0));
  if (!items.length) { showJob('<h3>Review</h3><p>No suggestions are waiting for review.</p>'); return; }
  const shownItems = items.slice(0, 60);
  showJob(`<h3>Review: ${fmt(items.length)} suggestion${items.length === 1 ? '' : 's'}</h3>
    <p>Accept puts the suggestion into the shared script (edit the text first to change it). Reject leaves the script as it is.
    Either way the author sees your answer and note in their inbox.</p>
    ${onlyId ? '' : `<div class="buttons"><button id="accept-all">Accept all ${fmt(items.length)} as suggested</button></div>`}
    <div class="merge-list">${shownItems.map(([sid, x], i) => reviewItem(sid, x, i)).join('')}</div>
    ${items.length > shownItems.length ? `<p class="muted">…and ${fmt(items.length - shownItems.length)} more after you review these.</p>` : ''}`);
  wireGoto();
  shownItems.forEach(([sid, x], i) => {
    $(`#r${i}-accept`).onclick = () => decide(sid, x, i, true).then(() => renderReview(onlyId)).catch(err => alert(err.message));
    $(`#r${i}-reject`).onclick = () => decide(sid, x, i, false).then(() => renderReview(onlyId)).catch(err => alert(err.message));
  });
  $('#accept-all')?.addEventListener('click', async () => {
    if (!confirm(`Accept all ${items.length} suggestions exactly as suggested?`)) return;
    $('#accept-all').disabled = true;
    for (const [sid, x] of items) await decide(sid, x, null, true);
    renderReview();
  });
}

function reviewItem(sid, x, i) {
  const cur = currentOf(x), stale = !same(cur, x.base) && !(x.kind === 'credits' && creditsText(cur.value) === creditsText(x.base.value));
  let body = '';
  if (x.kind === 'entry') {
    const e = O.byId[x.id]?.e;
    if (e) body += `<div class="merge-jp">${e.speaker ? `<span class="speaker">${esc(e.speaker)}</span> ` : ''}${esc(e.body)}</div>`;
    for (const [f, v] of Object.entries(x.change)) {
      body += `<div class="review-field"><small>${FIELD_WORDS[f]}</small><div class="merge-pair">${textBox(String(shown(f, cur[f])))}`;
      body += f === 'en' || f === 'note' ? `<textarea id="r${i}-${f}" rows="${Math.max(2, String(v).split('\n').length + 1)}">${esc(v)}</textarea>` : textBox(String(shown(f, v)), 'new');
      body += '</div></div>';
    }
  } else if (x.kind === 'speaker') {
    body = `<div class="merge-pair">${textBox(cur.value)}<input id="r${i}-value" value="${esc(x.change.value)}"></div>`;
  } else if (x.kind === 'face') {
    body = `<div class="merge-pair"><div>${faceImg(cur.value)}</div><div>${faceImg(x.change.value)}</div></div>`;
  } else {
    body = `<div class="merge-pair">${textBox(creditsSummary(cur.value))}${textBox(creditsSummary(x.change.value), 'new')}</div>
      <p class="muted">Team section of the closing credits: now, and as suggested.</p>`;
  }
  return `<div class="merge-item review-item"><div class="merge-head"><b>${suggestionTitle(x)}</b><span>${esc(x.n)}, ${esc(when(x.t))}</span></div>
    ${stale ? '<p class="warn-text">The shared script changed after this was suggested; the left side is what it has now.</p>' : ''}
    ${body}
    <label class="review-note">Note to ${esc(x.n)} (optional)<input id="r${i}-note" placeholder="Why you accepted, changed or rejected it"></label>
    <div class="buttons"><button id="r${i}-accept" class="primary">Accept</button><button id="r${i}-reject">Reject</button></div></div>`;
}

// i = the item's place in the review window (null: accept as suggested, with no note)
async function decide(sid, x, i, accept) {
  const note = i === null ? '' : $(`#r${i}-note`).value.trim();
  const reviewed = {reviewNote: note, reviewer: {n: O.name, e: O.email}, reviewedAt: now(), seen: false};
  const batch = fb.writeBatch(db);
  if (!accept) {
    batch.update(ref('suggestions', sid), {...reviewed, status: 'rejected'});
    await batch.commit();
    return;
  }
  const final = {...x.change};
  if (i !== null) for (const f of ['en', 'note', 'value']) {
    const box = $(`#r${i}-${f}`);
    if (box && typeof final[f] === 'string') final[f] = f === 'value' ? box.value.trim() : box.value;
  }
  const modified = !same(final, x.change), who = `${x.n} (accepted by ${O.name})`;
  if (x.kind === 'entry') {
    if (final.en) {
      const errors = check(x.id, final.en, speakerMap()).errors;
      if (errors.length && !confirm(`${x.id} has problems:\n${errors.join('\n')}\n\nAccept it anyway?`)) throw new Error('Not accepted.');
    }
    const before = entryOf(x.id), after = projectSet(before, final), args = [];
    if (entryUpdates(x.id, after, args, {n: x.n, e: x.e, ok: O.name})) batch.update(ref('files', O.byId[x.id].file), ...args);
    for (const f of ['en', 'note']) if (f in final) history(x.id, f, before[f] || '', after[f] || '', who);
  } else if (x.kind === 'speaker' || x.kind === 'face') {
    if (x.kind === 'speaker' && final.value) { const [, problems] = tokens(final.value); if (problems.length) throw new Error(problems.join('\n')); }
    const field = x.kind === 'speaker' ? 'en' : 'faces';
    batch.update(ref('meta', 'speakers'), new fb.FieldPath(field, x.id), final.value || fb.deleteField(),
                 ...(x.kind === 'speaker' ? [new fb.FieldPath('by', x.id), {n: x.n, e: x.e, ok: O.name, t: now()}] : []));
    history(x.id, x.kind, (O.speakers[field] || {})[x.id] || '', final.value, who);
  } else {
    batch.set(ref('meta', 'project'), {credits: final.value, creditsBy: {n: x.n, e: x.e, ok: O.name, t: now()}}, {merge: true});
    history('Credits', 'credits', '', 'changed', who);
  }
  batch.update(ref('suggestions', sid), {...reviewed, status: modified ? 'modified' : 'accepted', final});
  await batch.commit();
}

// ---------- your inbox: what happened to your suggestions ----------

const STATUS_WORDS = {accepted: 'Accepted', modified: 'Accepted with changes', rejected: 'Rejected'};
$('#inbox').onclick = () => {
  const waiting = Object.entries(O.pending || {}).filter(([, x]) => x.uid === O.user.uid);
  const done = [...(O.mine || [])].sort((a, b) => (b.reviewedAt?.toMillis?.() || 0) - (a.reviewedAt?.toMillis?.() || 0)).slice(0, 150);
  const values = (x, change) => x.kind === 'face' ? faceImg(change.value) : x.kind === 'credits' ? textBox(creditsSummary(change.value))
    : Object.entries(change).map(([f, v]) => `${FIELD_WORDS[f] ? `<small>${FIELD_WORDS[f]}</small>` : ''}${textBox(String(shown(f, v)))}`).join('');
  showJob(`<h3>Inbox</h3>
    ${done.length ? `<div class="merge-list">${done.map(x => `<div class="merge-item${x.seen ? '' : ' unseen'}">
      <div class="merge-head"><b>${suggestionTitle(x)}</b><span><span class="badge status-${x.status}">${STATUS_WORDS[x.status] || esc(x.status)}</span>
        ${esc(x.reviewer?.n || '')}, ${esc(when(x.reviewedAt))}</span></div>
      ${x.reviewNote ? `<p class="review-said"><b>Note:</b> ${esc(x.reviewNote)}</p>` : ''}
      ${x.status === 'modified' ? `<div class="merge-pair"><div><small>You suggested</small>${values(x, x.change)}</div><div><small>Went in as</small>${values(x, x.final)}</div></div>`
        : `<div><small>You suggested</small>${values(x, x.change)}</div>`}</div>`).join('')}</div>` : '<p>Nothing has been reviewed yet.</p>'}
    ${waiting.length ? `<p class="muted">${fmt(waiting.length)} of your suggestion${waiting.length === 1 ? ' is' : 's are'} waiting for review:
      ${waiting.slice(0, 40).map(([, x]) => suggestionTitle(x)).join(', ')}${waiting.length > 40 ? '…' : ''}</p>` : ''}`);
  wireGoto();
  for (const x of done) if (!x.seen) fb.updateDoc(x.ref, {seen: true}).catch(() => {});
};

// ---------- claims: "I'm translating these" for a week, from the Claims tab ----------
// claims/{auto}: {uid, n, e, t, group, from, to}. Story claims are mission numbers; every other tab's are its
// line numbers (each line's place in that tab, shown as "line N" on its row). A claim older than a week is gone.

const WEEK = 7 * 24 * 3600 * 1000;
const claimTime = c => c?.t?.toMillis ? c.t.toMillis() : Date.now();
const live = c => claimTime(c) + WEEK > Date.now();
const until = c => new Date(claimTime(c) + WEEK).toLocaleDateString([], {month: 'short', day: 'numeric'});
const unit = group => group === 'story' ? 'Mission' : 'Line';
const rangeText = c => c.from === c.to ? `${c.from}` : `${c.from}-${c.to}`;

// line numbers of the non-story tabs: each line's place among its tab's lines, in the Studio's order
function numberLines() {
  O.lineNo = {}; O.groupSize = {};
  for (const e of S.entries) if (e.group !== 'story') O.lineNo[e.id] = O.groupSize[e.group] = (O.groupSize[e.group] || 0) + 1;
  O.missions = [...new Set(S.entries.filter(e => e.group === 'story').map(e => +e.mission))].sort((a, b) => a - b);
}
const numberOf = e => e.group === 'story' ? +e.mission : O.lineNo[e.id];
function claimOf(e) {
  const n = numberOf(e);
  return Object.values(O.claims).find(c => c.group === e.group && live(c) && n >= c.from && n <= c.to) || null;
}

function listenClaims() {
  fb.onSnapshot(fb.collection(db, 'claims'), snap => {
    O.claims = Object.fromEntries(snap.docs.map(d => [d.id, d.data()]));
    if (!O.wrapped) return;
    renderRows();
    onlineEditorInfo();
    if (O.claimsOpen) renderClaims();
  });
}

function claimBadge(e) {
  if (!O.lineNo) return '';
  const c = claimOf(e);
  const no = e.group === 'story' ? '' : `<span class="badge" title="This line's number for claims">line ${fmt(O.lineNo[e.id])}</span> `;
  if (!c) return no;
  const mine = c.uid === O.user.uid;
  return `${no}<span class="badge claim${mine ? ' mine' : ''}" title="Claimed by ${esc(c.n)} until ${until(c)}">${mine ? 'claimed by you' : 'claimed: ' + esc(c.n)}</span>`;
}

function claimInfo(id) {
  if (!O.lineNo) return '';
  const c = claimOf(S.byId[id]);
  if (!c) return '';
  const what = `${c.group === 'story' ? 'missions' : 'lines'} ${rangeText(c)}`;
  return `<div class="sub claim-sub">${c.uid === O.user.uid ? 'You claimed' : `<b>${esc(c.n)} claimed</b>`} ${what} until ${until(c)}.</div>`;
}

// "1-10, 14" -> [[1, 10], [14, 14]]
function parseRanges(text, max) {
  const out = [];
  for (const part of text.split(/[,\s]+/).filter(Boolean)) {
    const m = /^(\d+)(?:-(\d+))?$/.exec(part);
    if (!m) throw new Error(`"${part}" is not a number or a range like 1-10`);
    let [a, b] = [+m[1], +(m[2] ?? m[1])];
    if (a > b) [a, b] = [b, a];
    if (a < 1 || b > max) throw new Error(`${part} is outside 1-${max}`);
    out.push([a, b]);
  }
  if (!out.length) throw new Error('Type the numbers to claim, such as 1-10');
  return out;
}

async function claimRanges(group, text) {
  const max = group === 'story' ? Math.max(...O.missions) : O.groupSize[group];
  const ranges = parseRanges(text, max);
  const taken = [];
  for (const [a, b] of ranges) for (const c of Object.values(O.claims)) {
    if (c.group === group && live(c) && c.uid !== O.user.uid && a <= c.to && b >= c.from) taken.push(`${rangeText({from: Math.max(a, c.from), to: Math.min(b, c.to)})} (${c.n})`);
  }
  if (taken.length) throw new Error(`Already claimed by someone else: ${unit(group).toLowerCase()}s ${taken.join(', ')}. Claim around them.`);
  const batch = fb.writeBatch(db);
  for (const [from, to] of ranges) batch.set(fb.doc(fb.collection(db, 'claims')), {uid: O.user.uid, n: O.name, e: O.email, t: now(), group, from, to});
  await batch.commit();
}

// ---------- the Claims tab ----------

function claimsTab() {
  const studioRenderTabs = window.renderTabs;
  window.renderTabs = function () {
    studioRenderTabs();
    const b = document.createElement('button');
    b.id = 'claims-tab'; b.className = O.claimsOpen ? 'active' : '';
    if (O.claimsOpen) $('#tabs').querySelectorAll('button').forEach(x => x.classList.remove('active'));
    b.innerHTML = 'Claims<small id="claims-tab-count"></small>';
    b.onclick = () => { O.claimsOpen = true; renderTabs(); renderClaims(); };
    $('#tabs').appendChild(b);
    renderClaimCount();
  };
  // any other tab closes the claims page
  $('#tabs').addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (b && b.id !== 'claims-tab' && O.claimsOpen) { O.claimsOpen = false; $('#claims-page').hidden = true; $('#app').hidden = false; }
  }, true);
  $('main').insertAdjacentHTML('beforeend', '<section id="claims-page" class="claims-page" hidden></section>');
  if (S.config) renderTabs();
}

function renderClaimCount() {
  const n = Object.values(O.claims).filter(live).length;
  const el = $('#claims-tab-count');
  if (el) el.textContent = n ? `${fmt(n)} active` : 'none';
}

function claimRows(list) {
  return list.length ? `<ul class="claim-list">${list.map(([cid, c]) => `<li><b>${esc(rangeText(c))}</b> · ${esc(c.n)}, until ${until(c)}
    ${c.uid === O.user.uid ? `<button data-renew="${cid}" title="Keep it for another week from today">Renew</button>` : ''}
    ${c.uid === O.user.uid || O.canReview ? `<button data-release="${cid}">Release</button>` : ''}</li>`).join('')}</ul>` : '<p class="muted">Nothing claimed.</p>';
}

function renderClaims() {
  $('#app').hidden = true;
  const page = $('#claims-page'); page.hidden = false;
  const active = Object.entries(O.claims).filter(([, c]) => live(c)).sort(([, a], [, b]) => a.from - b.from);
  const of = g => active.filter(([, c]) => c.group === g);
  const translatedIn = list => list.filter(e => translated(e) && !(S.project[e.id] || {}).mtl).length;
  const story = S.entries.filter(e => e.group === 'story' && !isHidden(e));
  const missionRows = O.missions.map(m => {
    const lines = story.filter(e => +e.mission === m), c = claimOf({group: 'story', mission: m});
    const title = lines.find(e => e.mission_title)?.mission_title || '';
    return `<tr><td>${m}</td><td>${esc(title)}</td><td>${fmt(lines.length)}</td><td>${fmt(lines.filter(e => (S.project[e.id] || {}).mtl).length)}</td>
      <td>${c ? `<span class="badge claim${c.uid === O.user.uid ? ' mine' : ''}">${c.uid === O.user.uid ? 'you' : esc(c.n)}</span> until ${until(c)}` : ''}</td></tr>`;
  }).join('');
  const others = S.config.groups.filter(([k]) => k !== 'story');
  page.innerHTML = `<h2>Claims</h2>
    <p>Claim what you are going to translate so nobody else starts on it. A claim lasts a week (Renew keeps it another week) and shows on
      every claimed line as a purple tag. ${O.canReview ? 'As a reviewer you can release anyone\'s claim.' : ''}</p>
    <div class="claim-box"><h3>Story: by mission</h3>
      <form data-group="story" class="claim-form"><label>Missions to claim<input placeholder="for example 1-10, 14" autocomplete="off"></label>
        <button class="primary">Claim</button><span class="claim-error bad"></span></form>
      ${claimRows(of('story'))}
      <details><summary>All ${O.missions.length} missions</summary><table class="claim-table"><thead><tr><th>Mission</th><th>Title</th><th>Lines</th><th>MTL</th><th>Claimed</th></tr></thead>
        <tbody>${missionRows}</tbody></table></details></div>
    ${others.map(([k, label]) => `<div class="claim-box"><h3>${esc(label)}: by line</h3>
      <p class="muted">${fmt(O.groupSize[k] || 0)} lines. Each line's number shows on its row in the ${esc(label)} tab ("line 12"); lines not in the game keep their numbers too, so some numbers are skipped in the list.</p>
      <form data-group="${k}" class="claim-form"><label>Lines to claim<input placeholder="for example 1-100" autocomplete="off"></label>
        <button class="primary">Claim</button><span class="claim-error bad"></span></form>
      ${claimRows(of(k))}</div>`).join('')}`;
  for (const f of page.querySelectorAll('.claim-form')) f.onsubmit = async ev => {
    ev.preventDefault();
    const err = f.querySelector('.claim-error'); err.textContent = '';
    try { await claimRanges(f.dataset.group, f.querySelector('input').value); flash('Claimed'); }
    catch (e) { err.textContent = e.message; }
  };
  for (const b of page.querySelectorAll('[data-release]')) b.onclick = () => fb.deleteDoc(ref('claims', b.dataset.release)).catch(e => alert(e.message));
  for (const b of page.querySelectorAll('[data-renew]')) b.onclick = () => fb.updateDoc(ref('claims', b.dataset.renew), {t: now()}).catch(e => alert(e.message));
}

// ---------- who is online ----------

function heartbeat() {
  if (!O.user || !O.access) return;
  fb.setDoc(ref('presence', O.user.uid), {n: O.name, e: O.email, id: studioOn() ? S.current || '' : '', t: now()}).catch(() => {});
}
function leave() { return O.user ? fb.deleteDoc(ref('presence', O.user.uid)).catch(() => {}) : Promise.resolve(); }
const fresh = p => p.t?.toMillis ? Date.now() - p.t.toMillis() < 180000 : true;
function colorOf(email) { let h = 0; for (const c of email || '') h = (h * 31 + c.charCodeAt(0)) % 360; return `hsl(${h} 70% 62%)`; }
function renderPresence() {
  const people = Object.values(O.presence).filter(fresh);
  $('#online').innerHTML = people.map(p => `<span class="who" title="${esc(p.e)}${p.id ? ' · on ' + esc(p.id) : ''}"><i style="background:${colorOf(p.e)}"></i>${esc(p.n)}</span>`).join('');
}
setInterval(renderPresence, 60000);

// ---------- recent changes, line history and the team list ----------

const fieldName = f => ({en: 'English', note: 'note', speaker: 'speaker name', face: 'portrait', credits: 'credits', import: 'import'}[f] || f);

$('#recent').onclick = async () => {
  showJob('<h3>Recent changes</h3><p>Loading…</p>');
  const snap = await fb.getDocs(fb.query(fb.collection(db, 'history'), fb.orderBy('t', 'desc'), fb.limit(150)));
  const items = snap.docs.map(d => d.data());
  showJob(`<h3>Recent changes</h3>${items.length ? `<div class="merge-list">${items.map(h => `<div class="merge-item"><div class="merge-head">
    <b>${O.byId[h.id] ? `<a href="#" data-goto="${esc(h.id)}">${esc(h.id)}</a>` : esc(h.id)}</b><span>${esc(h.n)}, ${esc(when(h.t))} · ${esc(fieldName(h.field))}</span></div>
    ${h.field === 'credits' || h.field === 'import' ? `<div class="muted">${esc(h.new)}</div>` : textBox(h.new, 'new')}</div>`).join('')}</div>` : '<p>Nobody has changed anything online yet.</p>'}`);
  wireGoto();
};

async function lineHistory(id) {
  showJob(`<h3>History of ${esc(id)}</h3><p>Loading…</p>`);
  const snap = await fb.getDocs(fb.query(fb.collection(db, 'history'), fb.where('id', '==', id), fb.limit(100)));
  const items = snap.docs.map(d => d.data()).sort((a, b) => (b.t?.toMillis?.() || 0) - (a.t?.toMillis?.() || 0));
  showJob(`<h3>History of ${esc(id)}</h3>${items.length ? `<div class="merge-list">${items.map(h => `<div class="merge-item"><div class="merge-head">
    <b>${esc(fieldName(h.field))}</b><span>${esc(h.n)}, ${esc(when(h.t))}</span></div><div class="merge-pair">${textBox(h.old)}${textBox(h.new, 'new')}</div></div>`).join('')}</div>`
    : '<p>No changes online yet.</p>'}<p class="muted">Last upload from the Studio:</p>${textBox(seedOf(id))}`);
}

$('#team').onclick = () => renderTeam();
const ROLES = [['admins', 'Admin'], ['reviewers', 'Reviewer'], ['editors', 'Editor']];
function renderTeam() {
  const a = O.access, names = a.names || {};
  const row = (email, role) => `<div><span>${esc(names[email] || '')} <code>${esc(email)}</code> · ${role}</span>
    ${email === O.email ? '<span class="muted">you</span>' : `<button data-rm="${esc(email)}">Remove</button>`}</div>`;
  showJob(`<h3>Team</h3><p>Only these Google accounts can open the script.</p>
    <ul><li><b>Editors</b> suggest changes; they go into the shared script once a reviewer or admin accepts them.</li>
      <li><b>Reviewers</b> accept, change or reject suggestions, and their own edits go straight in.</li>
      <li><b>Admins</b> do the same, and also change this list and upload packs.</li></ul>
    <div class="team-list">${ROLES.map(([k, word]) => (a[k] || []).map(e => row(e, word.toLowerCase())).join('')).join('')}</div>
    <div class="team-add"><label>Google account email<input id="add-email" type="email" placeholder="name@gmail.com"></label>
      <label>Role<select id="add-role">${ROLES.slice().reverse().map(([k, word]) => `<option value="${k}">${word}</option>`).join('')}</select></label>
      <button id="add" class="primary">Add or change role</button></div>`);
  const without = email => Object.fromEntries(ROLES.map(([k]) => [k, (a[k] || []).filter(x => x !== email)]));
  $('#add').onclick = async () => {
    const email = $('#add-email').value.trim().toLowerCase(), role = $('#add-role').value;
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return alert('That does not look like an email address.');
    if (email === O.email && role !== 'admins') return alert('You can\'t take away your own admin role.');
    const next = without(email);
    next[role].push(email);
    await fb.updateDoc(ref('meta', 'access'), next); O.access = {...a, ...next}; renderTeam();
  };
  for (const b of document.querySelectorAll('[data-rm]')) b.onclick = async () => {
    if (!confirm(`Remove ${b.dataset.rm} from the team?`)) return;
    const next = without(b.dataset.rm);
    await fb.updateDoc(ref('meta', 'access'), next); O.access = {...a, ...next}; renderTeam();
  };
}

// before the Studio's page is loaded, its helpers are not there yet
const textBox = (t, cls = '') => t ? `<div class="merge-text ${cls}">${esc(t)}</div>` : '<div class="merge-text none">(empty)</div>';
// app.js's S is a global const, so it is not window.S
const studioOn = () => typeof S !== 'undefined' && O.wrapped;
function showJob(html) { if (studioOn()) window.showJob(html); else showGate(html); }
function wireGoto() { if (studioOn()) window.wireGoto(); }

// ---------- uploading a pack from the desktop Studio ----------

$('#upload').onclick = () => $('#pack-file').click();
$('#pack-file').onchange = async ev => {
  const file = ev.target.files[0];
  ev.target.value = '';
  if (!file) return;
  let pack;
  try { pack = JSON.parse(await file.text()); } catch { return alert('That file is not an Online pack (not JSON).'); }
  if (pack.format !== 'fm2089-online-script' || pack.version !== 2) {
    return alert('That file is not an Online pack from this version. Save a new one with the desktop Studio\'s Online pack button.');
  }
  showJob('<h3>Uploading the script…</h3><p id="up-status">Preparing…</p>');
  try {
    const kept = await uploadPack(pack, msg => { const s = $('#up-status'); if (s) s.textContent = msg; });
    showJob(`<h3 class="ok">Script uploaded</h3><p>${fmt(pack.entries.length)} entries from the pack made ${esc(pack.made)}.
      ${kept ? `${fmt(kept)} line${kept === 1 ? '' : 's'} changed online kept ${kept === 1 ? 'its' : 'their'} online text.` : 'No lines had online changes to keep.'}</p>`);
  } catch (err) {
    showJob(`<h3 class="bad">Upload failed</h3><p>${esc(err.message)}</p>`);
  }
};

// Lines nobody changed online take the pack's text and flags; lines changed online keep theirs. Either way the pack's
// text becomes the new "last upload" that Export script compares against.
async function uploadPack(pack, status) {
  const byFile = {};
  pack.entries.forEach((e, pos) => { (byFile[e.file] ||= []).push({...e, pos}); });
  let kept = 0;
  const flags = p => ['done', 'mtl', 'edited', 'hidden'].map(f => JSON.stringify(p[f] ?? null)).join();
  const docs = Object.entries(byFile).map(([file, entries]) => {
    const old = O.files[file] || {};
    const d = {entries, seed: {}, seedNote: {}, seedFlags: {}, by: old.by || {}};
    for (const f of FIELDS) d[f] = {};
    for (const e of entries) {
      const t = pack.text[e.id] || {}, cur = {};
      for (const f of FIELDS) if ((old[f] || {})[e.id] !== undefined) cur[f] = old[f][e.id];
      const textChanged = old.entries && ((cur.en || '') !== ((old.seed || {})[e.id] || '') || (cur.note || '') !== ((old.seedNote || {})[e.id] || ''));
      const flagsChanged = old.entries && flags(cur) !== ((old.seedFlags || {})[e.id] ?? flags({}));
      const pick = textChanged || flagsChanged ? cur : t;
      if (textChanged && (cur.en || '') !== (t.en || '')) kept++;
      for (const f of FIELDS) if (pick[f] !== undefined && pick[f] !== '') d[f][e.id] = pick[f];
      if (t.en) d.seed[e.id] = t.en;
      if (t.note) d.seedNote[e.id] = t.note;
      d.seedFlags[e.id] = flags(t);
    }
    return [file, d];
  });
  for (let i = 0; i < docs.length; i += 6) {
    status(`Saving files ${i + 1}-${Math.min(i + 6, docs.length)} of ${docs.length}…`);
    const batch = fb.writeBatch(db);
    for (const [file, d] of docs.slice(i, i + 6)) batch.set(ref('files', file), d);
    await batch.commit();
  }
  status('Saving speakers, portraits and credits…');
  const sp = O.speakers || {};
  const merge = (cur = {}, seed, fresh = {}) => {
    const out = {};
    for (const k of new Set([...Object.keys(fresh), ...Object.keys(cur)])) {
      const v = seed && (cur[k] || '') !== (seed[k] || '') ? cur[k] : fresh[k];
      if (v) out[k] = v;
    }
    return out;
  };
  await fb.setDoc(ref('meta', 'speakers'), {en: merge(sp.en, sp.seed, pack.speakers), seed: pack.speakers,
    faces: merge(sp.faces, sp.facesSeed, pack.faces), facesSeed: pack.faces, by: sp.by || {}});
  const pr = O.project || {}, same = (a, b) => JSON.stringify(a ?? {}) === JSON.stringify(b ?? {});
  await fb.setDoc(ref('meta', 'project'), {
    settings: pr.settingsSeed && !same(pr.settings, pr.settingsSeed) ? pr.settings : pack.settings, settingsSeed: pack.settings,
    credits: pr.creditsSeed && !same(pr.credits, pr.creditsSeed) ? pr.credits : pack.project_credits, creditsSeed: pack.project_credits,
    images: pack.images || {}});
  await fb.setDoc(ref('meta', 'font'), {json: JSON.stringify(pack.font)});
  await fb.setDoc(ref('meta', 'portraits'), {json: JSON.stringify(pack.portraits)});
  const layout = {groups: pack.groups, dialogue_groups: pack.dialogue_groups, screen_width: pack.screen_width, hero: pack.hero,
    controls: pack.controls, control_range: pack.control_range, default_speakers: pack.default_speakers, default_faces: pack.default_faces,
    credits: pack.credits};
  await fb.setDoc(ref('meta', 'script'), {version: 2, made: pack.made, layout: JSON.stringify(layout), uploaded: {n: O.name, e: O.email, t: now()}});
  return kept;
}
