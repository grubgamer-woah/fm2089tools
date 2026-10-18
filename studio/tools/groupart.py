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
  ICONS      12 icons the group added to unused font slots, plus their narrower ×
  NAME_KEYS  the Delete / Back / Ok keys of the name entry screen
  BACKGROUND the Wanzer setup screens (Kiley's "Background" folder, 2026-10-18): the
             header bars of the hangar menus and the setup screen with its part
             buttons. Optional: without the folder these are drawn as before

The files are read from Kiley's folder at build time when it sits next to the
Studio, otherwise from the copy of the files used in studio/assets/Group
Localization Files/. Without either, every graphic is drawn by labels.py as before.
"""
from collections import Counter
from pathlib import Path

import labels

FOLDER_SUFFIX = 'Group Localization Files'
FONT = 'font/msgcmn.fnt'
ICONS = range(0x62D, 0x639)
TIMES = 0x4F                          # the group's narrower × (Kiley, 2026-10-18)
NAME_KEYS = 'name/NameEntryEnv.NCGR'  # Delete / Back / Ok keys, put into the En+Ko keyboard
# data/setup/BackGround/ files sit in the group folder's Background/; only their _ncg.bin
# (the game's own map fits them), except the setup screen, which has its own map
SETUP_DIR, BACKGROUND = 'setup/BackGround/', 'Background/'
BACKGROUND_BARS = {'setup_hangar', 'setup_select', 'setup_attribute', 'setup_color', 'setup_buyitem',
                   'setup_buysetup', 'setup_sellitem', 'setup_sellsetup', 'setup_sellparts',
                   'setup_stocksetup', 'setup_tradeitem', 'setup_collection'}
SETUP_SCREEN = [f'setup_bg_{k}.bin' for k in ('ncg', 'nsc', 'ncl')]
# The group's sellsetup_bg_ncg.bin was saved with its tiles in a new order but no map of its
# own, so the game's map scrambles it. This map, rebuilt from the tiles, ships with the Studio
# and is used only with that exact file (sha1).
FIXES = Path(__file__).resolve().parents[1]/'assets'/'fixes'
MAP_FIXES = {'sellsetup_bg_ncg.bin': ('17c06ba422414ed502a3c731623f6fff1e230e0c', 'sellsetup_bg_nsc.bin')}

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
        return (self.folder/self._where(rel)).read_bytes()

    def has(self, rel):
        return (self.folder/self._where(rel)).is_file()

    @staticmethod
    def _where(rel):
        return BACKGROUND + rel[len(SETUP_DIR):] if rel.startswith(SETUP_DIR) else rel

    @staticmethod
    def needed():
        """Every file of the group folder the Studio uses, relative to the folder."""
        need = [FONT, NAME_KEYS, *SCREENS, *HEADERS]
        for key in ART:
            for src in labels.LABELS[key][3]:
                need += [src['ncg']] if isinstance(src, dict) else [src]
        return sorted({p[5:] if p.startswith('data/') else p for p in need})

    def missing(self):
        return [p for p in self.needed() if not self.has(p)]

    # ---- files used as they are ----

    def label_files(self, key):
        """{rom path: bytes} for a graphic in ART or BACKGROUND_BARS. Loose bars: the group's tiles fit
        the game's own map (or a map in MAP_FIXES)."""
        out = {}
        for src in labels.LABELS[key][3]:
            path = src['ncg'] if isinstance(src, dict) else src
            out[path] = self.read(path[len('data/'):])
            fix = MAP_FIXES.get(path.rsplit('/', 1)[-1])
            if fix:
                out[src['nsc']] = (FIXES/BACKGROUND/fix[1]).read_bytes()
        return out

    def uses(self, key):
        """Is the group's picture used for this graphic?"""
        if key in ART:
            return True
        if key not in BACKGROUND_BARS:
            return False
        ncg = labels.LABELS[key][3][0]['ncg']
        if not self.has(ncg[len('data/'):]):
            return False
        fix = MAP_FIXES.get(ncg.rsplit('/', 1)[-1])
        if fix:
            import hashlib
            return hashlib.sha1(self.read(ncg[len('data/'):])).hexdigest() == fix[0]
        return True

    def setup_screen(self):
        """(ncg, nsc, ncl) of the group's Wanzer setup screen, or None."""
        paths = [SETUP_DIR+f for f in SETUP_SCREEN]
        return tuple(self.read(p) for p in paths) if all(self.has(p) for p in paths) else None

    def screens(self):
        return {'data/'+p: self.read(p) for p in SCREENS}

    def icons(self):
        """{glyph: font record} of the group's icons and ×."""
        import fontdata
        font = fontdata.Font(self.read(FONT))
        return {g: bytes(font.data[font.offsets[g]:font.offsets[g]+2+font.data[font.offsets[g]+1]*font.height])
                for g in [*ICONS, TIMES] if font.offsets[g]}

    def name_keys(self):
        return self.read(NAME_KEYS)

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
