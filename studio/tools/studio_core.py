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
import msgcodec
import ndsrom
import vcdiff

STUDIO = Path(__file__).resolve().parents[1]
ROM_DIR = STUDIO/'rom'
WORKSPACE = STUDIO/'workspace'
BUILDS = STUDIO/'builds'
PROJECT = WORKSPACE/'project.json'

CLEAN_MD5 = 'e965ed696171d327656dac3adf6c6221'  # Front Mission 2089 - Border of Madness (Japan), No-Intro
MSG_DIR = 'data/font/'
FONT_PATH = 'data/font/msgcmn.fnt'
SCREEN_WIDTH = 256
PATCH_NAME = 'FM2089 English'

GROUPS = [
    ('story', 'Story scenes', re.compile(r'^MsgLabels_station_')),
    ('battle', 'Battle dialogue', re.compile(r'^MsgLabels_tactics_\d')),
    ('parts', 'Parts & items', re.compile(r'^MsgLabels_parts_')),
    ('names', 'Names', re.compile(r'^MsgLabels_(name|mission_name)\.')),
    ('menus', 'Menus & system', re.compile(r'.')),
]


def group_of(file_name):
    for key, _, rx in GROUPS:
        if rx.search(file_name):
            return key


def find_rom(folders=None):
    """Return (path, md5) of the clean Japanese ROM, or (None, reason)."""
    folders = folders or [ROM_DIR, STUDIO.parent, STUDIO.parent.parent/'1. Original ROM']
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
        self.font_data = fontdata.tweak(self.rom.read(FONT_PATH))
        self.font = fontdata.Font(self.font_data)
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
                e = {
                    'id': msgcodec.string_id(name, i), 'file': stem, 'index': i+1,
                    'group': group_of(name), 'jp': msgcodec.tokens_to_text(toks, self.font),
                    'lines': len(widths), 'jp_width': max(widths), 'file_width': widest,
                }
                self.entries.append(e)
                self.by_id[e['id']] = (name, i, e)

    def limit(self, entry):
        """Widest line allowed before a warning: the widest Japanese line in the same file."""
        return max(entry['file_width'], entry['jp_width']) or SCREEN_WIDTH

    def check(self, entry_id, text):
        """Return dict with tokens, errors and warnings for an English string."""
        _, _, e = self.by_id[entry_id]
        toks, errors = msgcodec.text_to_tokens(text, self.font)
        widths = msgcodec.line_widths(toks, self.font)
        warnings = []
        limit = self.limit(e)
        for n, w in enumerate(widths, 1):
            if w > SCREEN_WIDTH:
                errors.append(f'Line {n} is {w} px, wider than the DS screen ({SCREEN_WIDTH} px)')
            elif w > limit:
                warnings.append(f'Line {n} is {w} px; the widest Japanese line in this file is {limit} px')
        if len(widths) > e['lines']:
            warnings.append(f'{len(widths)} lines; the Japanese has {e["lines"]}')
        jp_codes = sorted(set(re.findall(r'«(?!g:)[^»]+»', e['jp'])))
        en_codes = set(re.findall(r'«(?!g:)[^»]+»', text.upper()))
        missing = [c for c in jp_codes if c.upper() not in en_codes]
        if missing:
            warnings.append('Codes from the Japanese are missing: ' + ' '.join(missing))
        return {'tokens': toks, 'errors': errors, 'warnings': warnings, 'widths': widths, 'limit': limit}


class Project:
    def __init__(self, path=PROJECT):
        self.path = Path(path)
        self.entries = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.entries = data.get('entries', {})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            prev = self.path.with_name(self.path.stem+'.previous.json')
            prev.write_bytes(self.path.read_bytes())
        tmp = self.path.with_suffix('.tmp')
        data = {'application': 'fm2089-translation-studio', 'version': 1, 'rom_md5': CLEAN_MD5,
                'saved': dt.datetime.now().isoformat(timespec='seconds'), 'entries': self.entries}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(tmp, self.path)

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
    """Same layout as msgToTxt.py plus Japanese, so it pastes into a spreadsheet."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter='\t', lineterminator='\n')
    w.writerow(['stringID', 'text', 'japanese', 'note'])
    for e in catalog.entries:
        p = project.entries.get(e['id'], {})
        w.writerow([e['id'], p.get('en', ''), e['jp'], p.get('note', '')])
    return buf.getvalue()


def import_tsv(catalog, project, text):
    """Accepts this Studio's export or msgToTxt.py .txt files (stringID<TAB>"text")."""
    count, unknown = 0, []
    rows = csv.reader(io.StringIO(text.lstrip('﻿')), delimiter='\t')
    for row in rows:
        if not row or row[0] == 'stringID':
            continue
        sid = row[0].strip()
        if sid not in catalog.by_id:
            unknown.append(sid); continue
        en = row[1] if len(row) > 1 else ''
        if en and en != catalog.by_id[sid][2]['jp']:
            project.set(sid, en=en); count += 1
        if len(row) > 3 and row[3]:
            project.set(sid, note=row[3])
    return count, unknown


def compose(catalog, project):
    """Return ({rom path: new .msg bytes}, problems)."""
    per_file, problems = {}, []
    for sid, p in project.entries.items():
        if 'en' not in p or sid not in catalog.by_id:
            continue
        name, i, e = catalog.by_id[sid]
        res = catalog.check(sid, p['en'])
        for msg in res['errors']:
            problems.append({'id': sid, 'level': 'error', 'message': msg})
        for msg in res['warnings']:
            problems.append({'id': sid, 'level': 'warning', 'message': msg})
        if not res['errors']:
            per_file.setdefault(name, {})[i] = msgcodec.tokens_to_bytes(res['tokens'])
    files = {MSG_DIR+name: catalog.files[name].build(repl) for name, repl in per_file.items()}
    files[FONT_PATH] = catalog.font_data
    return files, problems


def build(catalog, project, out_root=BUILDS, log=print):
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    files, problems = compose(catalog, project)
    errors = [p for p in problems if p['level'] == 'error']
    if errors:
        return {'ok': False, 'problems': problems, 'message': f'{len(errors)} entries have errors; fix them first.'}
    log(f'Writing {len(files)} text files into the ROM…')
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
        'files': report, 'warnings': [p for p in problems if p['level'] == 'warning'],
    }
    (out/'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    (out/'project.json').write_text(json.dumps({'entries': project.entries}, ensure_ascii=False, indent=1), encoding='utf-8')
    (out/'README.txt').write_text(
        f'{PATCH_NAME} patch for Front Mission 2089: Border of Madness (Japan)\n\n'
        f'Apply "{patch_out.name}" with xdelta3, Delta Patcher or https://www.marcrobledo.com/RomPatcher.js/\n'
        f'to the clean Japanese ROM (MD5 {CLEAN_MD5}).\n'
        f'Patched ROM MD5: {manifest["patched_rom_md5"]}\n'
        f'Translated {translated} of {len(catalog.entries)} strings.\n', encoding='utf-8')
    log('Done.')
    return {'ok': True, 'folder': str(out), 'rom': str(rom_out), 'patch': str(patch_out),
            'patch_size': len(patch), 'problems': problems, 'files': report, 'translated': translated}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['build', 'export'])
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
    result = build(catalog, project, args.out)
    for p in result['problems']:
        print(f"{p['level']}: {p['id']}: {p['message']}")
    if not result['ok']:
        sys.exit(result['message'])
    print(result['patch'])


if __name__ == '__main__':
    main()
