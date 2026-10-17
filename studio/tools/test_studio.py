"""Checks the Studio against the real ROM: python test_studio.py [path/to/rom.nds]

Needs the clean Japanese ROM (in studio/rom/ or given on the command line).
Uses a temporary workspace, so your saved translations are never touched.
"""
import sys
import tempfile
from pathlib import Path

import msgcodec
import ndsrom
import studio_core as core
import vcdiff


def main():
    rom = Path(sys.argv[1]) if len(sys.argv) > 1 else core.find_rom()[0]
    if rom is None:
        sys.exit(core.find_rom()[1])
    cat = core.Catalog(rom)
    assert len(cat.entries) == 11500, len(cat.entries)

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
        project.save()
        tsv = core.export_tsv(cat, project)
        fresh = core.Project(Path(tmp)/'imported.json')
        count, unknown = core.import_tsv(cat, fresh, tsv)
        assert count == sum('en' in p for p in project.entries.values()) and not unknown

        result = core.build(cat, project, Path(tmp)/'builds', log=lambda m: None)
        assert result['ok'], result
        patched = Path(result['rom']).read_bytes()
        patch = Path(result['patch']).read_bytes()
        assert vcdiff.decode(cat.rom.data, patch) == patched
        check = ndsrom.Rom(patched)
        mf = msgcodec.MsgFile('x', check.read('data/font/MsgLabels_city_common.msg'))
        assert msgcodec.tokens_to_text(mf.tokens(99), cat.font).startswith('Initializing save data.')
        print(f'OK: {len(cat.entries)} strings, patch {len(patch):,} bytes, files {[f["placement"] for f in result["files"]]}')


if __name__ == '__main__':
    main()
