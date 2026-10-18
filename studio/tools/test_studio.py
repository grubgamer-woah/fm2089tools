"""Checks the Studio against the real ROM: python test_studio.py [path/to/rom.nds]

Needs the clean Japanese ROM (in studio/rom/ or given on the command line).
Uses a temporary workspace, so your saved translations are never touched.
"""
import struct
import sys
import tempfile
from pathlib import Path

import groupart
import heroname
import koname
import labels
import msgcodec
import ndsrom
import portraits
import scriptio
import tutorials
import studio_core as core
import vcdiff


def main():
    rom = Path(sys.argv[1]) if len(sys.argv) > 1 else core.find_rom()[0]
    if rom is None:
        sys.exit(core.find_rom()[1])
    cat = core.Catalog(rom)
    assert len(cat.entries) == 11500 + len(labels.LABELS), len(cat.entries)

    for name, mf in cat.files.items():
        assert mf.build({}) == mf.data, f'{name} does not rebuild byte for byte'
    assert cat.rom.rebuild({})[0] == cat.rom.data, 'empty ROM rebuild changed the ROM'

    for e in cat.entries:
        toks, problems = msgcodec.text_to_tokens(e['jp'], cat.font)
        assert not problems, (e['id'], problems)

    with tempfile.TemporaryDirectory() as tmp:
        project = core.Project(Path(tmp)/'project.json')
        project.set('MsgLabels_city_common_msg_100', en='Initializing save data.\nPress the A Button or\ntouch the "Touch Screen".')
        for e in cat.entries:
            if e['file'] == 'MsgLabels_station_01' and e['jp']:
                project.set(e['id'], en=f'«E801:00» says line {e["index"]} in English.')
        project.set(labels.entry_id('title_startmenu'), en='Main Menu')
        project.save()
        tsv = core.export_tsv(cat, project)
        fresh = core.Project(Path(tmp)/'imported.json')
        count, unknown = core.import_tsv(cat, fresh, tsv)
        assert count == sum('en' in p for p in project.entries.values()) and not unknown
        if core.BUNDLED.is_file():
            shipped = core.Project(Path(tmp)/'shipped.json')
            count, unknown = core.import_text(cat, shipped, core.BUNDLED.read_text(encoding='utf-8'))
            assert count > 9000 and not unknown, (count, unknown[:5])

        # Script exports merge: base A A A, one script makes it A B A, another A A C -> A B C;
        # a line both scripts change differently waits for a choice
        a, b, c, d = (e['id'] for e in cat.entries[:4])
        scripts = []
        for who, sid in (('B', b), ('C', c)):
            other = core.Project(Path(tmp)/who/'project.json')
            for i in (a, b, c, d):
                other.set(i, en='A')
            scriptio.write_snapshot(other)
            other.set(sid, en=who)
            other.set(d, en=f'{who} says so')
            path, n, _ = core.export_script(cat, other, who, Path(tmp)/'exports')
            assert n == 2 and core.export_script(cat, other, who, Path(tmp)/'exports')[0] is None
            scripts.append((path.name, path.read_text(encoding='utf-8')))
        base = core.Project(Path(tmp)/'base.json')
        for i in (a, b, c, d):
            base.set(i, en='A')
        plan = core.import_plan(cat, base, scripts)
        assert len(plan['auto']) == 2 and len(plan['conflicts']) == 1, plan
        scriptio.apply(base, plan, {'\t'.join(plan['conflicts'][0]['key']): 1})
        assert [base.entries[i]['en'] for i in (a, b, c, d)] == ['A', 'B', 'C', 'C says so']
        everything = scriptio.diff(cat, {}, scriptio.state(project))
        assert scriptio.parse_md(scriptio.to_md(cat, project, everything, '', '')) == everything

        result = core.build(cat, project, Path(tmp)/'builds', log=lambda m: None)
        assert result['ok'], result
        patched = Path(result['rom']).read_bytes()
        patch = Path(result['patch']).read_bytes()
        assert vcdiff.decode(cat.rom.data, patch) == patched
        check = ndsrom.Rom(patched)
        mf = msgcodec.MsgFile('x', check.read('data/font/MsgLabels_city_common.msg'))
        assert msgcodec.tokens_to_text(mf.tokens(99), cat.font).startswith('Initializing save data.')
        assert heroname.decode(check.read('overlay/14')) == 'Storm'
        for key, (_, _, kind, sources) in labels.LABELS.items():
            if cat.group and cat.group.uses(key):
                for path, data in cat.group.label_files(key).items():
                    assert check.read(path) == data, path
                continue  # the group's picture replaces only the files it drew
            for src in sources:
                for path in (src.values() if isinstance(src, dict) else [] if kind in ('check', 'button') else [src]):
                    assert check.read(path) != cat.rom.read(path), path
        assert check.read('data/name/EntryCheck_ncg.bin') != cat.rom.read('data/name/EntryCheck_ncg.bin')
        for part in ('ncg', 'nsc'):
            assert check.read(labels.SETUP_BG+part+'.bin') != cat.rom.read(labels.SETUP_BG+part+'.bin'), part
        if cat.group and cat.group.setup_screen():
            for path, data in zip(('ncg', 'nsc'), cat.group.setup_screen()):   # the shipped png changes nothing
                assert labels._lz(check.read(labels.SETUP_BG+path+'.bin')) == labels._lz(data), path
        for name in tutorials.PICTURES:
            path = f'data/bg/{name}_ncg.bin'
            assert check.read(path) != cat.rom.read(path), path
        if cat.ko_rom:
            assert check.read('data/name/fon00_ncg.bin') == cat.ko_rom.read('data/name/en/fon00_ncg.bin')
            ovt = struct.unpack_from('<I', patched, 0x50)[0]
            assert any(struct.unpack_from('<3I', patched, ovt+32*i)[::2] == (14, koname.SIZE) for i in range(64))
        st = msgcodec.MsgFile('x', check.read('data/font/MsgLabels_station_01.msg'))
        assert msgcodec.tokens_to_text(st.tokens(1), cat.font) == '«E801:00»:\n«E801:00» says line 2 in English.'

        speakers = sum(1 for e in cat.entries if e['speaker'])
        assert speakers > 5800, speakers
        project.set_speaker('レイン', 'Rain')
        e = next(e for e in cat.entries if e['speaker'] == 'レイン')
        assert cat.check(e['id'], 'Hi.', project.speakers)['full'] == 'Rain:\nHi.'
        faces = cat.portraits
        assert all(f in faces.paths for f in portraits.SPEAKER_FACES.values())
        for face in ('Rain', 'Falcon', 'Brown'):  # small face art and a bust-up crop
            assert faces.image(face).startswith(b'\x89PNG'), face
        print(f'OK: {len(cat.entries)} strings, patch {len(patch):,} bytes, files {[f["placement"] for f in result["files"]]}')


if __name__ == '__main__':
    main()
