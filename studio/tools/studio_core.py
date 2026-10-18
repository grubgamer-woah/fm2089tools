"""Catalog, project storage and patch building for the FM2089 Translation Studio.

Command line build (same as the Build button):
    python studio_core.py build [--project workspace/project.json]
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

import fontdata
import groupart
import heroname
import koname
import labels
import msgcodec
import ndsrom
import portraits
import scriptio
import titles
import staticons
import tutorials
import vcdiff

STUDIO = Path(__file__).resolve().parents[1]
# where the Japanese and En+Ko ROMs are looked for; '1. Original ROM' may sit one or two levels up
ROM_FOLDERS = [STUDIO.parent, STUDIO.parent/'1. Original ROM', STUDIO.parent.parent/'1. Original ROM']
ROM_DIR = STUDIO/'rom'
# Kiley's "5. Group Localization Files" (the group's own English graphics) sits next to the Studio folder
# the group's own graphics and the En+Ko name screens, shipped with the Studio
ASSETS = STUDIO/'assets'
GROUP_FOLDERS = [STUDIO.parent, STUDIO.parent.parent, ASSETS]
WORKSPACE = STUDIO/'workspace'
BUILDS = STUDIO/'builds'
EXPORTS = STUDIO/'exports'
PROJECT = WORKSPACE/'project.json'
# Kiley's English, shipped with the Studio: a new workspace starts from it, and Import takes it too
BUNDLED = STUDIO/'translation'/'project.json'
SETUP_PNG = 'setup_bg.png'

CLEAN_MD5 = 'e965ed696171d327656dac3adf6c6221'  # Front Mission 2089 - Border of Madness (Japan), No-Intro
MSG_DIR = 'data/font/'
FONT_PATH = 'data/font/msgcmn.fnt'
SCREEN_WIDTH = 256
# Dialogue and message boxes wrap mid-word past this width (measured in the emulator).
TEXT_BOX_WIDTH = 228
# The hero's name is a variable; widths count it as the default name.
HERO_NAME = '«E801:00»'
HERO_DEFAULT = 'Storm'
# The name entry screen's preset name follows this string's English (ストーム in the names list).
HERO_NAME_ID = 'MsgLabels_name_msg_110'
PATCH_NAME = 'FM2089 English'

GROUPS = [
    ('story', 'Story (game order)', re.compile(r'^MsgLabels_(station|tactics)_\d')),
    ('parts', 'Parts & items', re.compile(r'^MsgLabels_parts_')),
    ('names', 'Names', re.compile(r'^MsgLabels_(name|mission_name)\.')),
    (labels.GROUP, 'Screen graphics', re.compile('^' + re.escape(labels.FILE) + '$')),
    ('menus', 'Menus & system', re.compile(r'.')),
]


# Dialogue starts with the speaker's name: "レイン：\n…" (own line) or "«E801:00»：眼？" (same line).
SPEAKER_RX = re.compile(r'^((?:«E801:00»|[^\s：。、«»\n]){1,16})：( ?)(\n?)')
DIALOGUE_GROUPS = ('story',)
SCENE_RX = re.compile(r'^MsgLabels_(station|tactics)_(\d+)(?:_(\d+))?$')
DEFAULT_SPEAKERS = {'«E801:00»': '«E801:00»', '？？？': '???', '？？？？': '????'}


def split_speaker(text, group):
    """Return (speaker, own_line, body); speaker is None for lines without one."""
    m = SPEAKER_RX.match(text)
    if m and (m.group(3) or group in DIALOGUE_GROUPS):
        return m.group(1), bool(m.group(3)), text[m.end():]
    return None, False, text


def group_of(file_name):
    for key, _, rx in GROUPS:
        if rx.search(file_name):
            return key


def find_rom(folders=None):
    """Return (path, md5) of the clean Japanese ROM, or (None, reason)."""
    folders = folders or [ROM_DIR, *ROM_FOLDERS]
    seen = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob('*.nds')):
            md5 = hashlib.md5(path.read_bytes()).hexdigest()
            if md5 == CLEAN_MD5:
                return path, md5
            seen.append(f'{path.name} (MD5 {md5})')
    if seen:
        return None, 'No clean Japanese ROM found. These .nds files do not match: ' + ', '.join(seen)
    return None, f'Put the Japanese ROM (.nds) in {ROM_DIR}'


class Catalog:
    """Every string in every .msg file of the clean ROM."""

    def __init__(self, rom_path):
        self.rom_path = Path(rom_path)
        self.rom = ndsrom.Rom(self.rom_path.read_bytes())
        # The group's own graphics, when Kiley's group folder sits next to the Studio
        found = groupart.find(GROUP_FOLDERS)
        self.group, self.group_problem = None, f'"{groupart.FOLDER_SUFFIX}" not found, so the group\'s graphics are not used'
        if found:
            missing = groupart.GroupArt(found).missing()
            if missing:
                self.group_problem = f'Group graphics not used; missing from {found}: ' + ', '.join(missing)
            else:
                self.group, self.group_problem = groupart.GroupArt(found), None
        self.font_data = fontdata.tweak(self.rom.read(FONT_PATH), self.group.icons() if self.group else None)
        self.font = fontdata.Font(self.font_data)
        self.portraits = portraits.Portraits(self.rom)
        self.titles = titles.Titles(self.rom)
        # The En+Ko fan patch's name entry screens are used when that ROM sits next to the Japanese one
        ko = koname.find([ROM_DIR, *ROM_FOLDERS, self.rom_path.parent])
        self.ko_rom = ndsrom.Rom(ko.read_bytes()) if ko else None
        if not ko and (ASSETS/koname.FOLDER/koname.OVERLAY).is_file():
            self.ko_rom = koname.Folder(ASSETS/koname.FOLDER)
        self.files = {}
        self.entries = []
        self.by_id = {}
        for path in self.rom.list(MSG_DIR):
            if not path.endswith('.msg'):
                continue
            name = path[len(MSG_DIR):]
            mf = msgcodec.MsgFile(name, self.rom.read(path))
            self.files[name] = mf
            toks_all = [mf.tokens(i) for i in range(len(mf.strings))]
            widest = max((max(msgcodec.line_widths(t, self.font)) for t in toks_all), default=0)
            stem = name[:-4]
            for i, toks in enumerate(toks_all):
                widths = msgcodec.line_widths(toks, self.font)
                jp = msgcodec.tokens_to_text(toks, self.font)
                group = group_of(name)
                speaker, own_line, body = split_speaker(jp, group)
                e = {
                    'id': msgcodec.string_id(name, i), 'file': stem, 'index': i+1,
                    'group': group, 'jp': jp, 'speaker': speaker, 'speaker_own_line': own_line, 'body': body,
                    'lines': len(widths), 'jp_width': max(widths), 'file_width': widest,
                }
                self.entries.append(e)
                self.by_id[e['id']] = (name, i, e)
        # "勝利条件：…" looks like a same-line speaker; only trust names that also speak on their own line
        real = {e['speaker'] for e in self.entries if e['speaker'] and e['speaker_own_line']}
        # Japanese drawn into graphics (screen headers, base icons...): edited like text, built by labels.py
        for n, (key, (jp, _, _, _)) in enumerate(labels.LABELS.items(), 1):
            e = {
                'id': labels.entry_id(key), 'file': labels.FILE, 'index': n, 'group': labels.GROUP,
                'jp': jp, 'speaker': None, 'speaker_own_line': False, 'body': jp,
                'lines': labels.max_lines(key), 'jp_width': labels.limit(key), 'file_width': labels.limit(key),
            }
            if labels.LABELS[key][2] == 'button':
                e['art'] = ("Drawn in serif capitals like the game's own COM button (A-Z, 0-9, - . & /); "
                            "longer words are drawn narrower to fit.")
            elif self.group and self.group.uses(key):
                e['art'] = "The group's own picture is used; the English here is not drawn."
            elif self.group and key in groupart.LETTERING:
                e['art'] = "Drawn in the group's header lettering (letters: " + ''.join(sorted(self.group.letters())) + ')'

            self.entries.append(e)
            self.by_id[e['id']] = (None, None, e)
        for e in self.entries:
            if e['speaker'] and e['speaker'] not in real:
                e.update(speaker=None, speaker_own_line=False, body=e['jp'])
        self._play_order()

    def _play_order(self):
        """Put story text in the order the game plays it.

        Mission N is the base (station_N: talks, briefing, cutscenes) and then its
        battle (tactics_N). Inside a file the game's own order is kept, except:
        station_01 ends with the opening narration, which plays first; station_60
        is the closing narration after the last battle; and dialogue choices stored
        at the top of a base file go right before the reply they lead to."""
        titles = {e['index']: re.sub(r'^.*?«g:24»', '', e['jp']) for e in self.entries if e['file'] == 'MsgLabels_mission_name'}
        groups = [key for key, _, _ in GROUPS]
        by_file = {}
        for e in self.entries:
            by_file.setdefault(e['file'], []).append(e)
        keys = {}
        for n, e in enumerate(self.entries):
            keys[e['id']] = (groups.index(e['group']), 0, 0, 0, n)
        for file, es in by_file.items():
            m = SCENE_RX.match(file)
            if not m:
                continue
            kind, mission, sub = m.group(1), int(m.group(2)), int(m.group(3) or 0)
            part = 0 if kind == 'station' else 1
            if file == 'MsgLabels_station_60':
                part = 2
            pos = {e['id']: float(e['index']) for e in es}
            if file == 'MsgLabels_station_01':
                for e in es[-3:]:
                    pos[e['id']] -= 1000
            if kind == 'station':
                for e in es[:4]:
                    if e['speaker'] or not e['body'].strip() or '\n' in e['body']:
                        break
                    reply = next((r for r in es if r['speaker'] == '«E801:00»' and r['body'].startswith(e['body'])), None)
                    if reply:
                        pos[e['id']] = reply['index'] - .5
            for e in es:
                e['mission'] = mission
                e['scene'] = ('Base', 'Battle', 'Ending')[part]
                e['mission_title'] = titles.get(mission, '')
                keys[e['id']] = (groups.index(e['group']), mission, part, sub, pos[e['id']])
        self.entries.sort(key=lambda e: keys[e['id']])

    def limit(self, entry):
        """Widest line allowed before a warning.

        Story text goes in the dialogue box, which wraps mid-word past TEXT_BOX_WIDTH
        (the Japanese relies on that wrap, so its own width is no guide). Other text
        sits in fixed slots, so the widest Japanese line in the same file is the guide."""
        if entry['group'] in DIALOGUE_GROUPS:
            return TEXT_BOX_WIDTH
        return max(entry['file_width'], entry['jp_width']) or SCREEN_WIDTH

    def full_text(self, e, text, speakers):
        """The English as the game shows it: speaker name prefix plus the entry's text."""
        if not e['speaker']:
            return text, None
        name = speakers.get(e['speaker']) or DEFAULT_SPEAKERS.get(e['speaker'])
        warning = None
        if not name:
            name = e['speaker']
            warning = f'The speaker "{e["speaker"]}" has no English name yet, so the Japanese name is used'
        return f'{name}:' + ('\n' if e['speaker_own_line'] else ' ') + text, warning

    def check(self, entry_id, text, speakers=None):
        """Return dict with tokens, errors and warnings for an English string."""
        _, _, e = self.by_id[entry_id]
        body = text
        text, speaker_warning = self.full_text(e, text, speakers or {})
        toks, errors = msgcodec.text_to_tokens(text, self.font)
        widths = msgcodec.line_widths(msgcodec.text_to_tokens(text.replace(HERO_NAME, HERO_DEFAULT), self.font)[0], self.font)
        warnings = [speaker_warning] if speaker_warning else []
        limit = self.limit(e)
        for n, w in enumerate(widths, 1):
            if w > SCREEN_WIDTH:
                errors.append(f'Line {n} is {w} px, wider than the DS screen ({SCREEN_WIDTH} px)')
            elif w > limit:
                if e['group'] in DIALOGUE_GROUPS:
                    warnings.append(f'Line {n} is {w} px; the text box wraps mid-word past {limit} px')
                else:
                    warnings.append(f'Line {n} is {w} px; the widest Japanese line in this file is {limit} px')
        if len(widths) > e['lines']:
            warnings.append(f'{len(widths)} lines; the Japanese has {e["lines"]}')
        jp_codes = sorted(set(re.findall(r'«(?!g:)[^»]+»', e['body'])))
        en_codes = set(re.findall(r'«(?!g:)[^»]+»', body.upper()))
        missing = [c for c in jp_codes if c.upper() not in en_codes]
        if missing:
            warnings.append('Codes from the Japanese are missing: ' + ' '.join(missing))
        return {'tokens': toks, 'errors': errors, 'warnings': warnings, 'widths': widths, 'limit': limit, 'full': text}


class Project:
    def __init__(self, path=PROJECT):
        self.path = Path(path)
        self.entries = {}
        self.speakers = {}  # Japanese speaker name -> English name, shared by every line
        self.faces = {}  # Japanese speaker name -> portrait picked in the Studio ('-' = none); never built
        self.images = {}  # mission title name -> replacement PNG, relative to the project folder
        self.settings = {}  # build switches, such as staticons.SETTING
        source = self.path if self.path.exists() else BUNDLED if self.path == PROJECT and BUNDLED.is_file() else None
        self.stamp = self.disk_stamp()
        if source:
            data = json.loads(source.read_text(encoding='utf-8'))
            self.entries = data.get('entries', {})
            self.speakers = data.get('speakers', {})
            self.faces = data.get('faces', {})
            self.images = data.get('images', {})
            self.settings = data.get('settings', {})
        # A PNG in images/ counts even if an older Studio saved the project without it
        for png in sorted(self.image_dir.glob('mtittle_bg_??.png')):
            self.images.setdefault(png.stem, f'images/{png.name}')
        self.images = {k: v for k, v in self.images.items() if self.image_path(k, v).is_file()}

    def image_path(self, name, rel=None):
        """A title picture; the shipped project points at ../translation/images, so '..' is resolved first."""
        return Path(os.path.normpath(self.path.parent/(rel or self.images[name])))

    def setup_png(self):
        """The edited Wanzer setup screen (images/setup_bg.png, else the shipped one), or None."""
        for path in (self.image_dir/SETUP_PNG, BUNDLED.parent/'images'/SETUP_PNG):
            if path.is_file():
                return path.read_bytes()
        return None

    @property
    def image_dir(self):
        return self.path.parent/'images'

    def disk_stamp(self):
        """When and how big project.json was last written, to notice edits made outside the Studio."""
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def changed_on_disk(self):
        return self.disk_stamp() != self.stamp

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            prev = self.path.with_name(self.path.stem+'.previous.json')
            prev.write_bytes(self.path.read_bytes())
        tmp = self.path.with_suffix('.tmp')
        data = {'application': 'fm2089-translation-studio', 'version': 1, 'rom_md5': CLEAN_MD5,
                'saved': dt.datetime.now().isoformat(timespec='seconds'),
                'speakers': self.speakers, 'faces': self.faces, 'images': dict(sorted(self.images.items())),
                'settings': self.settings, 'entries': self.entries}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, self.path)
        self.stamp = self.disk_stamp()

    def set_image(self, name, png_bytes):
        """Store a replacement mission title (None removes it)."""
        path = self.image_dir/f'{name}.png'
        if png_bytes is None:
            if path.exists():
                path.unlink()
            self.images.pop(name, None)
            return
        self.image_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_bytes)
        self.images[name] = f'images/{name}.png'

    def image_bytes(self, name):
        return self.image_path(name).read_bytes()

    def set_face(self, jp, face):
        if face:
            self.faces[jp] = face
        else:
            self.faces.pop(jp, None)

    def set_speaker(self, jp, en):
        if en:
            self.speakers[jp] = en
        else:
            self.speakers.pop(jp, None)

    def set(self, entry_id, en=None, note=None, done=None):
        cur = dict(self.entries.get(entry_id, {}))
        if en is not None:
            if en == '':
                cur.pop('en', None)
            else:
                cur['en'] = en
        if note is not None:
            if note == '':
                cur.pop('note', None)
            else:
                cur['note'] = note
        if done is not None:
            if done:
                cur['done'] = True
            else:
                cur.pop('done', None)
        if cur:
            self.entries[entry_id] = cur
        else:
            self.entries.pop(entry_id, None)


def export_tsv(catalog, project):
    """Same first columns as msgToTxt.py, so it pastes into a spreadsheet.

    text and japanese leave out the speaker prefix; the speaker columns carry it."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter='\t', lineterminator='\n')
    w.writerow(['stringID', 'text', 'japanese', 'note', 'speaker', 'speaker_english'])
    for e in catalog.entries:
        p = project.entries.get(e['id'], {})
        sp = e['speaker'] or ''
        w.writerow([e['id'], p.get('en', ''), e['body'], p.get('note', ''), sp,
                    project.speakers.get(sp, '') if sp else ''])
    return buf.getvalue()


def tsv_rows(catalog, project, text, unknown=None):
    """(id, english, note, speaker_english) for each row of this Studio's export or a msgToTxt.py .txt
    (stringID<TAB>"text"); English that is just the Japanese comes back empty."""
    rows = csv.reader(io.StringIO(text.lstrip('\ufeff')), delimiter='\t')
    for row in rows:
        if not row or row[0] == 'stringID':
            continue
        sid = row[0].strip()
        if sid not in catalog.by_id:
            if unknown is not None:
                unknown.append(sid)
            continue
        e = catalog.by_id[sid][2]
        en = row[1] if len(row) > 1 else ''
        speaker_en = row[5] if len(row) > 5 and e['speaker'] else ''
        if e['speaker']:
            # msgToTxt-style rows still carry the "Name:" prefix; the Studio adds it itself
            for prefix in (e['speaker']+'：', e['speaker']+':', (speaker_en or project.speakers.get(e['speaker']) or '\0')+':'):
                if en.startswith(prefix):
                    en = en[len(prefix):].lstrip(' ')
                    en = en[1:] if en.startswith('\n') and e['speaker_own_line'] else en
                    break
        yield sid, en if en not in (e['jp'], e['body']) else '', row[3] if len(row) > 3 else '', speaker_en


def import_tsv(catalog, project, text):
    """Accepts this Studio's export or msgToTxt.py .txt files (stringID<TAB>"text")."""
    count, unknown = 0, []
    for sid, en, note, speaker_en in tsv_rows(catalog, project, text, unknown):
        if speaker_en:
            project.set_speaker(catalog.by_id[sid][2]['speaker'], speaker_en)
        if en:
            project.set(sid, en=en); count += 1
        if note:
            project.set(sid, note=note)
    return count, unknown


def import_project(catalog, project, text):
    """Takes another Studio's project.json (such as translation/project.json): its English,
    notes, speaker names and faces replace this project's where it has them."""
    data = json.loads(text.lstrip('\ufeff'))
    count, unknown = 0, []
    for sid, p in data.get('entries', {}).items():
        if sid not in catalog.by_id:
            unknown.append(sid); continue
        project.set(sid, en=p.get('en'), note=p.get('note'), done=p.get('done'))
        count += 'en' in p
    for jp, en in data.get('speakers', {}).items():
        project.set_speaker(jp, en)
    for jp, face in data.get('faces', {}).items():
        project.set_face(jp, face)
    return count, unknown


def import_text(catalog, project, text):
    """A project.json or a .tsv/.txt, whichever the text is."""
    if text.lstrip('\ufeff \r\n').startswith('{'):
        return import_project(catalog, project, text)
    return import_tsv(catalog, project, text)


def export_script(catalog, project, author='', folder=EXPORTS):
    """Write the changes since the last export (or since the shipped translation) as a .md in folder.
    Returns (path or None when nothing changed, number of changes, what it compared against)."""
    base, since = scriptio.baseline(project, BUNDLED)
    changes = scriptio.diff(catalog, base, scriptio.state(project))
    if not changes:
        return None, 0, since
    folder.mkdir(parents=True, exist_ok=True)
    who = re.sub(r'[^\w .-]+', '', author).strip()
    path = folder/f'FM2089 script{" - " + who if who else ""} - {dt.datetime.now():%Y-%m-%d %H%M%S}.md'
    path.write_text(scriptio.to_md(catalog, project, changes, author, since), encoding='utf-8')
    scriptio.write_snapshot(project)
    return path, len(changes), since


def import_plan(catalog, project, files):
    """files = [(name, text)]: what importing them together would change, and where they conflict."""
    sources = []
    for name, text in files:
        try:
            sources.append((name, scriptio.parse(catalog, project, text, tsv_rows)))
        except ValueError as error:
            raise ValueError(f'{name}: {error}') from error
    return scriptio.plan(catalog, project, sources)


def backup_project(project):
    """Copy project.json to workspace/backups before an import changes it; returns the copy's path."""
    if not project.path.exists():
        return None
    folder = project.path.parent/'backups'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/f'project-before-import-{dt.datetime.now():%Y%m%d-%H%M%S}.json'
    path.write_bytes(project.path.read_bytes())
    return path


def title_files(catalog, project, name, png_bytes=None):
    """(ncg, ncl, nsc) for a replacement mission title, converted once and cached by PNG hash."""
    data = png_bytes if png_bytes is not None else project.image_bytes(name)
    cache = project.path.parent/'cache'/f'{name}-{hashlib.sha1(data).hexdigest()[:16]}.bin'
    if cache.is_file():
        blob = cache.read_bytes()
        parts, p = [], 0
        while p < len(blob):
            n = int.from_bytes(blob[p:p+4], 'little')
            parts.append(blob[p+4:p+4+n]); p += 4+n
        return tuple(parts)
    parts = catalog.titles.convert(name, data)
    cache.parent.mkdir(parents=True, exist_ok=True)
    for old in cache.parent.glob(f'{name}-*.bin'):
        old.unlink()
    cache.write_bytes(b''.join(len(x).to_bytes(4, 'little')+x for x in parts))
    return parts


def compose_images(catalog, project, log=print):
    """Return ({rom path: bytes}, problems) for the replacement mission titles."""
    files, problems = {}, []
    names = [n for n in sorted(project.images) if n in catalog.titles.names]
    if names:
        log(f'Converting {len(names)} mission title images…')
    for name in names:
        try:
            parts = title_files(catalog, project, name)
        except Exception as error:  # a broken PNG stops the build with its name
            problems.append({'id': name, 'level': 'error', 'message': f'Mission title image: {error}'})
            continue
        for kind, data in zip(('ncg', 'ncl', 'nsc'), parts):
            files[titles.paths(name)[kind]] = data
    return files, problems


def compose(catalog, project):
    """Return ({rom path: new .msg bytes}, problems)."""
    per_file, problems = {}, []
    # the group's stat icons replace the stat names of the parts info (they come with the group's font)
    icons = project.settings.get(staticons.SETTING, True) and catalog.group is not None
    for sid, p in project.entries.items():
        if 'en' not in p or sid not in catalog.by_id:
            continue
        name, i, e = catalog.by_id[sid]
        en = staticons.with_icons(p['en']) if icons and staticons.applies(sid) else p['en']
        res = catalog.check(sid, en, project.speakers)
        if name is None:  # a graphic; labels.compose draws it
            problems += [{'id': sid, 'level': 'error', 'message': msg} for msg in res['errors']]
            continue
        for msg in res['errors']:
            problems.append({'id': sid, 'level': 'error', 'message': msg})
        for msg in res['warnings']:
            problems.append({'id': sid, 'level': 'warning', 'message': msg})
        if not res['errors']:
            per_file.setdefault(name, {})[i] = msgcodec.tokens_to_bytes(res['tokens'])
    ko_files = {}
    if catalog.ko_rom:
        # digit and symbol keys of the patch's keyboard show these in dialogue
        ko_files, name_chars = koname.compose(catalog.ko_rom, catalog.font,
                                              catalog.group.name_keys() if catalog.group else None)
        for i, ch in name_chars.items():
            per_file.setdefault('MsgLabels_font.msg', {})[i] = msgcodec.tokens_to_bytes([('g', catalog.font.char_glyph(ch))])
    files = {MSG_DIR+name: catalog.files[name].build(repl) for name, repl in per_file.items()}
    files[FONT_PATH] = catalog.font_data
    texts = {key: project.entries.get(labels.entry_id(key), {}).get('en') for key in labels.LABELS}
    # an edited picture of the Wanzer setup buttons, if there is one (see README, "Setup buttons")
    setup = project.setup_png()
    graphics, graphic_problems = labels.compose(catalog.rom, catalog.font, texts, catalog.group, setup)
    files.update(graphics)
    if catalog.group:
        files.update(catalog.group.screens())
    else:
        problems.append({'id': labels.entry_id('title_startmenu'), 'level': 'warning', 'message': catalog.group_problem})
    problems += graphic_problems

    def english(sid):
        key = sid[len(labels.ID_PREFIX):]
        if sid.startswith(labels.ID_PREFIX) and key in labels.LABELS:
            return texts[key] or labels.LABELS[key][1]
        return project.entries.get(sid, {}).get('en')
    # tutorial screenshots of the menus: redrawn from the same entries, or with the group's own headers
    screen = catalog.group and catalog.group.setup_screen()
    pictures, picture_problems = tutorials.compose(
        catalog.rom, catalog.font, english, setup or (screen and labels.Picture(*screen).png()),
        tutorials.group_bars(catalog.rom, graphics, catalog.group))
    files.update(pictures)
    problems += picture_problems
    overlay = f'overlay/{heroname.OVERLAY}'
    files[overlay] = catalog.rom.read(overlay)
    if catalog.ko_rom:
        files.update(ko_files)
    else:
        problems.append({'id': labels.entry_id('check_pilot'), 'level': 'warning',
                         'message': f'"{koname.KO_NAME}" not found, so the name entry screens stay Japanese'})
    name = project.entries.get(HERO_NAME_ID, {}).get('en', HERO_DEFAULT)
    try:
        heroname.encode(name)
    except ValueError as error:
        problems.append({'id': HERO_NAME_ID, 'level': 'warning',
                         'message': f'Name entry screen keeps "{HERO_DEFAULT}": {error}'})
        name = HERO_DEFAULT
    files[overlay] = heroname.patch(files[overlay], name)
    return files, problems


def build(catalog, project, out_root=BUILDS, log=print):
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    files, problems = compose(catalog, project)
    images, image_problems = compose_images(catalog, project, log)
    files.update(images)
    problems += image_problems
    errors = [p for p in problems if p['level'] == 'error']
    if errors:
        return {'ok': False, 'problems': problems, 'message': f'{len(errors)} entries have errors; fix them first.'}
    log(f'Writing {len(files) - len(images)} files ({len(images)//3} mission titles) into the ROM…')
    clean = catalog.rom.data
    patched, report = catalog.rom.rebuild(files)
    out = Path(out_root)/f'build-{stamp}'
    out.mkdir(parents=True, exist_ok=False)
    log('Creating the xdelta patch…')
    patch = vcdiff.encode(clean, patched)
    log('Checking the patch against the clean ROM…')
    if vcdiff.decode(clean, patch) != patched:
        raise RuntimeError('Patch verification failed')
    check = ndsrom.Rom(patched)
    for path, data in files.items():
        if check.read(path) != data:
            raise RuntimeError(f'{path} did not round-trip')
    rom_out = out/f'{PATCH_NAME}.nds'
    patch_out = out/f'{PATCH_NAME}.xdelta'
    rom_out.write_bytes(patched)
    patch_out.write_bytes(patch)
    translated = sum(1 for p in project.entries.values() if 'en' in p)
    manifest = {
        'built': dt.datetime.now().isoformat(timespec='seconds'),
        'source_rom_md5': CLEAN_MD5,
        'patched_rom_md5': hashlib.md5(patched).hexdigest(),
        'patch_md5': hashlib.md5(patch).hexdigest(),
        'translated_entries': translated, 'total_entries': len(catalog.entries),
        'hero_default_name': heroname.decode(check.read(f'overlay/{heroname.OVERLAY}')),
        'name_entry_screens': 'En+Ko patch' if catalog.ko_rom else 'Japanese',
        'group_art': str(catalog.group.folder) if catalog.group else None,
        'mission_titles': sorted({p.split('/')[-1][:13] for p in images}),
        'files': report, 'warnings': [p for p in problems if p['level'] == 'warning'],
    }
    (out/'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    (out/'project.json').write_text(json.dumps({'entries': project.entries}, ensure_ascii=False, indent=1), encoding='utf-8')
    (out/'README.txt').write_text(
        f'{PATCH_NAME} patch for Front Mission 2089: Border of Madness (Japan)\n\n'
        f'Apply "{patch_out.name}" with xdelta3, Delta Patcher or https://www.marcrobledo.com/RomPatcher.js/\n'
        f'to the clean Japanese ROM (MD5 {CLEAN_MD5}).\n'
        f'Patched ROM MD5: {manifest["patched_rom_md5"]}\n'
        f'Translated {translated} of {len(catalog.entries)} strings and {len(images)//3} mission title screens.\n', encoding='utf-8')
    log('Done.')
    return {'ok': True, 'folder': str(out), 'rom': str(rom_out), 'patch': str(patch_out),
            'patch_size': len(patch), 'problems': problems, 'files': report, 'translated': translated,
            'titles': len(images)//3}


def setup_png(catalog, project):
    """The Wanzer setup screen with the project's button words, as a PNG."""
    texts = {key: project.entries.get(labels.entry_id(key), {}).get('en') for key in labels.LABELS}
    buttons = []
    for key, (_, default, kind, sources) in labels.LABELS.items():
        if kind == 'button':
            text = texts[key] or default
            buttons += [(src, text if labels.button_word(text) else default) for src in sources]
    return labels.setup_png(catalog.rom, buttons, catalog.group)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['build', 'export', 'setup-png'])
    ap.add_argument('--project', default=str(PROJECT))
    ap.add_argument('--rom')
    ap.add_argument('--out', default=str(BUILDS))
    args = ap.parse_args()
    rom = Path(args.rom) if args.rom else find_rom()[0]
    if rom is None:
        sys.exit(find_rom()[1])
    catalog = Catalog(rom)
    project = Project(args.project)
    if args.command == 'export':
        sys.stdout.write(export_tsv(catalog, project))
        return
    if args.command == 'setup-png':
        # the Wanzer setup screen as this project draws it, to edit (see README, "Setup buttons")
        out = Path(args.out) if args.out != str(BUILDS) else project.image_dir/SETUP_PNG
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(setup_png(catalog, project))
        print(out)
        return
    result = build(catalog, project, args.out)
    for p in result['problems']:
        print(f"{p['level']}: {p['id']}: {p['message']}")
    if not result['ok']:
        sys.exit(result['message'])
    print(result['patch'])


if __name__ == '__main__':
    main()
