"""The localization group's own English graphics, from Kiley's "5. Group Localization Files".

The group drew English into copies of the game's own files, saved at their ROM
paths (title/startmenu.msur.pk is data/title/startmenu.msur.pk). Kiley picked,
graphic by graphic, which of them the patch uses (2026-10-18):

  ART        screen graphics used exactly as the group drew them; the Studio's
             English for these entries is not drawn
  LETTERING  the Studio's English drawn in the group's header lettering. The
             letters are cut out of the group's own headers, so only letters
             that appear there (plus q, h and U, built from p, n+k and O) exist
  SCREENS    screens the Studio has no text entry for, used as they are
  ICONS      12 icons the group added to unused font slots; in the font, not used
             by any text yet

The files are read from Kiley's folder at build time; nothing from them is stored
in this repository. Without the folder every graphic is drawn by labels.py as before.
"""
from collections import Counter
from pathlib import Path

import labels

FOLDER_SUFFIX = 'Group Localization Files'
FONT = 'font/msgcmn.fnt'
ICONS = range(0x62D, 0x639)

ART = {'title_startmenu', 'title_newgame', 'title_nextnewgame', 'title_loadgame', 'title_config',
       'base_mercenarypost', 'base_arena', 'base_saveandload',
       'icon_office', 'icon_station', 'icon_hangar', 'icon_arena', 'icon_saveload', 'icon_exit'}
LETTERING = {'base_commandpost', 'base_goout'}
SCREENS = [f'AdDemo/Text0{n}_{k}.bin' for n in range(1, 8) for k in ('ncg', 'nsc')] + [
    'result/ResultBG_ncg.bin', 'result/ResultBG_ncl.bin', 'result/ResultBG_nsc.bin',
    'slg/ge/GeInfoMsg.NCGR']
# what each group header says: the source of the lettering
HEADERS = {
    'title/startmenu.msur.pk': 'Start menu', 'title/newgame.msur.pk': 'New Game',
    'title/nextnewgame.msur.pk': 'New Game+', 'title/loadgame.msur.pk': 'Load game',
    'title/config.msur.pk': 'Config', 'Base/CommandPostLowerBG.msur.pk': 'HQ',
    'Base/MercenaryPostLowerBG.msur.pk': 'Barracks', 'Base/ArenaBG.msur.pk': 'Arena',
    'Base/SaveAndLoadBG.msur.pk': 'Ops Records', 'Base/GoOutBG.msur.pk': 'Move Out',
}
TOP, BOTTOM = 3, 13      # rows of the header bar the lettering may use
X0 = 3                   # where the group's lettering starts
BAR_RIGHT = 126          # last column it may reach (the header bars are 128 px wide)
GAP, SPACE = 0, 3        # columns between letters (their blended edges touch) / for a space
ASCENDER = 6             # first row of lowercase letters without an ascender


def find(folders):
    """The group folder in any of the folders (or the folder itself), or None."""
    for folder in folders:
        for f in [folder, *(sorted(folder.glob('*')) if folder.is_dir() else [])]:
            if f.is_dir() and f.name.endswith(FOLDER_SUFFIX) and (f/'title'/'startmenu.msur.pk').is_file():
                return f
    return None


def _rows(data):
    """Palette indices of a header bar (rows 0-15) and the background index of each row."""
    d, offs = labels._msur_split(data)
    screen = labels.Screen(d[offs[2]:offs[3]], d[offs[0]:offs[2]])
    w = 0
    while screen.tile_px(w, 0)[0][0] == 0xB and w < screen.tw:
        w += 1
    rows, _ = screen.get(0, 0, w*8, 16)
    base = [Counter(r[1:-1]).most_common(1)[0][0] for r in rows]
    return rows, base


# Letters cut out of the group's headers: header, first and last column. The
# group's letters touch (their edges are blended), so these were picked by eye.
# These headers sit one row higher than the rest; their letters move down to match.
RAISED = {'Load game', 'Ops Records'}
CUTS = {
    'S': ('Start menu', 3, 7), 'a': ('Start menu', 12, 16), 'm': ('Start menu', 27, 33),
    'e': ('Start menu', 34, 39), 'n': ('Config', 15, 19), 'H': ('HQ', 3, 9), 'Q': ('HQ', 10, 17),
    'B': ('Barracks', 3, 8), 'r': ('Barracks', 15, 18), 'c': ('Barracks', 29, 32),
    'k': ('Barracks', 34, 38), 's': ('Barracks', 39, 42), 'L': ('Load game', 3, 7),
    'o': ('Load game', 8, 12), 'd': ('Load game', 20, 24), 'C': ('Config', 3, 8),
    'i': ('Config', 23, 24), 'g': ('Config', 26, 30), 'O': ('Ops Records', 3, 9),
    'p': ('Ops Records', 10, 13), 'u': ('Move Out', 39, 43), 't': ('Move Out', 44, 47),
}


class GroupArt:
    def __init__(self, folder):
        self.folder = Path(folder)
        self._letters = None

    def read(self, rel):
        return (self.folder/rel).read_bytes()

    def has(self, rel):
        return (self.folder/rel).is_file()

    def missing(self):
        need = [FONT, *SCREENS, *HEADERS]
        for key in ART:
            for src in labels.LABELS[key][3]:
                need += [src['ncg']] if isinstance(src, dict) else [src]
        return sorted({p[5:] if p.startswith('data/') else p for p in need if not self.has(p[5:] if p.startswith('data/') else p)})

    # ---- files used as they are ----

    def label_files(self, key):
        """{rom path: bytes} for a graphic in ART. Loose bars: the group's tiles fit the game's own map."""
        out = {}
        for src in labels.LABELS[key][3]:
            path = src['ncg'] if isinstance(src, dict) else src
            out[path] = self.read(path[len('data/'):])
        return out

    def screens(self):
        return {'data/'+p: self.read(p) for p in SCREENS}

    def icons(self):
        """{glyph: font record} of the group's icons."""
        import fontdata
        font = fontdata.Font(self.read(FONT))
        return {g: bytes(font.data[font.offsets[g]:font.offsets[g]+2+font.data[font.offsets[g]+1]*font.height])
                for g in ICONS if font.offsets[g]}

    # ---- lettering ----

    def letters(self):
        """{character: columns}; a column is {row: palette index} of the letter's ink."""
        if self._letters is None:
            found = {}
            by_text = {text: path for path, text in HEADERS.items()}
            headers = {}
            for ch, (text, x0, x1) in CUTS.items():
                if text not in headers:
                    headers[text] = _rows(self.read(by_text[text]))
                rows, base = headers[text]
                down = 1 if text in RAISED else 0
                found[ch] = [{y+down: rows[y][x] for y in range(TOP, BOTTOM) if rows[y][x] != base[y]}
                             for x in range(x0, x1+1)]
            self._derive(found)
            self._letters = found
        return self._letters

    @staticmethod
    def _derive(found):
        """q, h and U, which none of the group's headers spell."""
        if 'p' in found and 'q' not in found:
            found['q'] = found['p'][::-1]
        if 'n' in found and 'k' in found and 'h' not in found:
            # n with the ascender of k's stem on its own stem
            found['h'] = [{**{y: v for y, v in k.items() if y < ASCENDER}, **n}
                          for k, n in zip(found['k'][:2], found['n'][:2])] + found['n'][2:]
        if 'O' in found and 'U' not in found:
            o = found['O']
            mid = (TOP + BOTTOM)//2
            u = []
            for x, col in enumerate(o):
                c = {y: v for y, v in col.items() if y >= mid}
                if x in (0, 1, len(o)-2, len(o)-1):
                    for y in range(TOP, mid):
                        v = col.get(mid) or col.get(mid-1)
                        if v is not None:
                            c[y] = v
                u.append(c)
            found['U'] = u
        return found

    def missing_letters(self, text):
        have = self.letters()
        return sorted({ch for ch in text if ch != ' ' and ch not in have})

    def text_width(self, text):
        have = self.letters()
        w = 0
        for ch in text:
            w += SPACE if ch == ' ' else len(have.get(ch, ())) + GAP
        return max(w - GAP, 0)

    def draw(self, text):
        """draw(rows) for labels.bar_file: paints the text over a blanked header bar."""
        have = self.letters()

        def paint(rows):
            x = X0
            for ch in text:
                if ch == ' ':
                    x += SPACE
                    continue
                for col in have[ch]:
                    for y, v in col.items():
                        if x < len(rows[0]) - 1:
                            rows[y][x] = v
                    x += 1
                x += GAP
        return paint
