"""Script exports (the changes since the last export, as a readable .md) and merging imports.

A change is (key, old, new): key is ('en', id), ('note', id), ('speaker', jp) or ('face', jp);
old is the text the exporter started from (None when the file doesn't say, as in a .tsv or a
project.json) and '' means "no text". Merging several files at once applies every change only one
file makes (or that all files agree on) and lists the rest as conflicts to pick from.
"""
import datetime as dt
import json
import re

SNAPSHOT = 'last-export.json'
KINDS = {'en': 'English', 'note': 'note', 'speaker': 'name', 'face': 'portrait'}
HEAD_SPEAKER, HEAD_FACE = 'Speaker name: ', 'Portrait: '
BLOCK_RX = re.compile(r'^(Japanese|Old English|New English|Old note|New note|Old name|New name|Old portrait|New portrait):\s*$')
FENCE_RX = re.compile(r'^(~{3,}|`{3,})\s*\w*\s*$')


def current(project, key):
    kind, name = key
    if kind in ('en', 'note'):
        return project.entries.get(name, {}).get(kind, '')
    return (project.speakers if kind == 'speaker' else project.faces).get(name, '')


def put(project, key, value):
    kind, name = key
    if kind == 'en':
        project.set(name, en=value)
    elif kind == 'note':
        project.set(name, note=value)
    elif kind == 'speaker':
        project.set_speaker(name, value)
    else:
        project.set_face(name, value)


def state(project):
    """Everything an export compares: the English, notes, speaker names and portraits."""
    return {'entries': {k: {f: v[f] for f in ('en', 'note') if v.get(f)} for k, v in project.entries.items() if v.get('en') or v.get('note')},
            'speakers': dict(project.speakers), 'faces': dict(project.faces)}


def values(data):
    out = {}
    for sid, p in data.get('entries', {}).items():
        for f in ('en', 'note'):
            if p.get(f):
                out[(f, sid)] = p[f]
    for kind, field in (('speaker', 'speakers'), ('face', 'faces')):
        for jp, v in data.get(field, {}).items():
            if v:
                out[(kind, jp)] = v
    return out


def baseline(project, bundled):
    """What the next export compares against: the last export, else the translation shipped with the Studio."""
    snap = project.path.parent/SNAPSHOT
    if snap.is_file():
        data = json.loads(snap.read_text(encoding='utf-8'))
        return data, f'the last export ({data.get("exported", "?")})'
    if bundled.is_file() and bundled.resolve() != project.path.resolve():
        return json.loads(bundled.read_text(encoding='utf-8')), 'the translation shipped with the Studio'
    return {}, 'an empty script'


def order_key(catalog):
    pos = {e['id']: i for i, e in enumerate(catalog.entries)}
    rank = {'speaker': 0, 'face': 1, 'en': 2, 'note': 2}
    return lambda key: (rank[key[0]], pos.get(key[1], len(pos)) if key[0] in ('en', 'note') else 0, key[1], key[0] == 'note')


def diff(catalog, old, new):
    a, b = values(old), values(new)
    return [(k, a.get(k, ''), b.get(k, '')) for k in sorted(set(a) | set(b), key=order_key(catalog)) if a.get(k, '') != b.get(k, '')]


def fence(text):
    ticks = max([len(m) for m in re.findall(r'~{3,}', text)] + [2]) + 1
    return '~'*ticks


def block(label, text):
    f = fence(text)
    return [f'{label}:', f + 'text', *([text] if text else []), f, '']


def to_md(catalog, project, changes, author, since):
    stamp = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
    out = ['# FM2089 script changes', '',
           f'- From: {author or "(no name)"}', f'- Exported: {stamp}', f'- Changes since: {since}', f'- Changes: {len(changes)}', '',
           'Load this file with **Import script** (or several at once with **Import multiple**) in the FM2089 Translation Studio.',
           'Only the "New" blocks are read in; "Old" is what the sender started from, so the Studio can tell when both of you changed a line.', '']
    by_head = {}
    for key, old, new in changes:
        by_head.setdefault((key[0] if key[0] in ('speaker', 'face') else 'entry', key[1]), []).append((key, old, new))
    for (kind, name), items in by_head.items():
        out += ['---', '']
        if kind == 'speaker':
            out += [f'## {HEAD_SPEAKER}{name}', '']
        elif kind == 'face':
            out += [f'## {HEAD_FACE}{name}', '']
        else:
            e = catalog.by_id[name][2] if name in catalog.by_id else None
            out += [f'## {name}', '']
            if e and e['speaker']:
                out += [f'Speaker: {e["speaker"]} ({project.speakers.get(e["speaker"]) or "no English name"})', '']
            if e:
                out += block('Japanese', e['body'])
        for key, old, new in items:
            word = KINDS[key[0]]
            out += block(f'Old {word}', old) + block(f'New {word}', new)
    return '\n'.join(out).rstrip() + '\n'


def parse_md(text):
    """The changes in an exported .md (old text included)."""
    changes, head, found = [], None, {}
    lines = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿').split('\n')

    def flush():
        if head is None:
            return
        kinds = {'entry': (('English', 'en'), ('note', 'note')), 'speaker': (('name', 'speaker'),), 'face': (('portrait', 'face'),)}
        for word, kind in kinds[head[0]]:
            if 'New ' + word in found:
                changes.append(((kind, head[1]), found.get('Old ' + word), found['New ' + word]))

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('## '):
            flush()
            title, found = line[3:].strip(), {}
            if title.startswith(HEAD_SPEAKER):
                head = ('speaker', title[len(HEAD_SPEAKER):])
            elif title.startswith(HEAD_FACE):
                head = ('face', title[len(HEAD_FACE):])
            else:
                head = ('entry', title)
        else:
            m = BLOCK_RX.match(line)
            if m and head and i + 1 < len(lines) and FENCE_RX.match(lines[i+1]):
                f = FENCE_RX.match(lines[i+1]).group(1)
                j = i + 2
                while j < len(lines) and lines[j].strip() != f:
                    j += 1
                found[m.group(1)] = '\n'.join(lines[i+2:j])
                i = j
        i += 1
    flush()
    return changes


def parse_project(text):
    """Another Studio's project.json: every value it has, with no "old" to compare."""
    data = json.loads(text.lstrip('﻿'))
    return [(k, None, v) for k, v in values(data).items()]


def parse(catalog, project, text, tsv_rows):
    """Changes from an exported .md, a project.json, or a .tsv/.txt (tsv_rows turns those into (id, en, note, speaker_en))."""
    body = text.lstrip('﻿ \r\n')
    if body.startswith('{'):
        return parse_project(text)
    if body.startswith('# FM2089 script changes') or '\n## ' in body[:5000]:
        return parse_md(text)
    changes = []
    for sid, en, note, speaker_en in tsv_rows(catalog, project, text):
        if en:
            changes.append((('en', sid), None, en))
        if note:
            changes.append((('note', sid), None, note))
        sp = catalog.by_id[sid][2]['speaker'] if sid in catalog.by_id else ''
        if sp and speaker_en:
            changes.append((('speaker', sp), None, speaker_en))
    return changes


def known(catalog, key):
    return key[0] not in ('en', 'note') or key[1] in catalog.by_id


def plan(catalog, project, sources):
    """sources = [(file name, changes)]. Returns what an import would do, applying nothing.

    A change counts only where it differs from the current text. If exactly one new text is offered
    and every file that offers it started from the current text (or doesn't say), it is applied;
    otherwise the line is a conflict: two files disagree, or the sender changed a line you changed too."""
    offers, unknown = {}, []
    for name, changes in sources:
        for key, old, new in changes:
            if not known(catalog, key):
                unknown.append(key[1]); continue
            if new != current(project, key):
                offers.setdefault(key, []).append((name, old, new))
    auto, conflicts = [], []
    for key in sorted(offers, key=order_key(catalog)):
        cur = current(project, key)
        options = {}
        for name, old, new in offers[key]:
            options.setdefault(new, []).append(name)
        stale = [name for name, old, new in offers[key] if old is not None and old != cur]
        item = {'key': list(key), 'kind': KINDS[key[0]], 'name': key[1], 'current': cur}
        e = catalog.by_id[key[1]][2] if key[0] in ('en', 'note') and key[1] in catalog.by_id else None
        if e:
            item.update(jp=e['body'], speaker=e['speaker'] or '')
        if len(options) == 1 and not stale:
            (new, files), = options.items()
            auto.append({**item, 'new': new, 'files': files})
        else:
            if len(options) > 1:
                why = 'These files change it in different ways.'
            else:
                why = f'You changed this line too, after {", ".join(stale)} was made.'
            if stale and len(options) > 1:
                why += f' You also changed it after {", ".join(stale)} was made.'
            conflicts.append({**item, 'why': why, 'options': [{'value': v, 'files': f} for v, f in options.items()]})
    return {'auto': auto, 'conflicts': conflicts, 'unknown': sorted(set(unknown))}


def apply(project, the_plan, choices):
    """Apply the plan's automatic changes, plus each conflict's chosen option (choices: 'kind\\tname' -> option
    index; missing or -1 keeps the current text). Returns how many values changed."""
    n = 0
    for item in the_plan['auto']:
        put(project, tuple(item['key']), item['new']); n += 1
    for item in the_plan['conflicts']:
        pick = choices.get('\t'.join(item['key']), -1)
        if isinstance(pick, int) and 0 <= pick < len(item['options']):
            put(project, tuple(item['key']), item['options'][pick]['value']); n += 1
    return n


def write_snapshot(project):
    data = {'exported': dt.datetime.now().strftime('%Y-%m-%d %H:%M'), **state(project)}
    project.path.parent.mkdir(parents=True, exist_ok=True)
    (project.path.parent/SNAPSHOT).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
