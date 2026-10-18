"""Japanese text drawn into graphics: screen headers, base icons, the name check and the ending.

Each label is redrawn with the game's own font (msgcmn.fnt) over the original art:
  bar     the header in the top-left corner of a screen (Start Menu, Hangar...).
          A .msur.pk (LZ10 of four u32 offsets, then NSC, NCG, NCL) or loose
          _ncg/_nsc .bin files. The bar is a 16 px high gradient; the Japanese is
          painted over with each row's gradient color and the English drawn in the
          text colors (palette entries 13-15). Tiles are never changed in place
          (other parts of the screen share them); new ones are appended.
  icon    the 64x32 room pictures on the base map (.mspr.pk: LZ10 of four u32
          offsets, then NCGR, NCER, NCLR). The Japanese band is blended out with
          the picture above and below it and the English drawn white with a dark edge.
  check   the 16 px glyph sheet of the name check screens (data/name/EntryCheck_ncg.bin,
          32 tiles wide). Each label fills a run of 16 px cells in place.
  ending  data/Ending/ed_text.msur.pk, a 256 px wide picture of the closing narration.
"""
import struct
from collections import Counter

import portraits
import titles

GROUP = 'graphics'
FILE = 'Screen graphics'


def _lz(data):
    return portraits.lz10(data) if data[:1] == b'\x10' else data


def _bins(base):
    return {'ncg': base+'_ncg.bin', 'nsc': base+'_nsc.bin'}


# key: (Japanese, default English, kind, sources)
LABELS = {
    'title_startmenu': ('スタートメニュー', 'Start Menu', 'bar', ['data/title/startmenu.msur.pk']),
    'title_newgame': ('ニューゲーム', 'New Game', 'bar', ['data/title/newgame.msur.pk']),
    'title_nextnewgame': ('ネクストニューゲーム', 'New Game+', 'bar', ['data/title/nextnewgame.msur.pk']),
    'title_loadgame': ('ロードゲーム', 'Load Game', 'bar', ['data/title/loadgame.msur.pk']),
    'title_config': ('コンフィグ', 'Config', 'bar', ['data/title/config.msur.pk']),
    'base_commandpost': ('司令部', 'Headquarters', 'bar',
                         ['data/Base/CommandPostLowerBG.msur.pk', _bins('data/Base/CommandPostLowerBG')]),
    'base_mercenarypost': ('傭兵詰所', 'Barracks', 'bar',
                           ['data/Base/MercenaryPostLowerBG.msur.pk', _bins('data/Base/MercenaryPostLowerBG')]),
    'base_arena': ('闘技場', 'Arena', 'bar', ['data/Base/ArenaBG.msur.pk']),
    'base_saveandload': ('作戦の記録', 'Ops Records', 'bar', ['data/Base/SaveAndLoadBG.msur.pk']),
    'base_goout': ('出撃機体選択', 'Choose Sortie Units', 'bar', ['data/Base/GoOutBG.msur.pk']),
    'setup_hangar': ('格納庫', 'Hangar', 'bar', [_bins('data/setup/BackGround/hanger_bg')]),
    'setup_select': ('セットアップ', 'Wanzer Setup', 'bar', [_bins('data/setup/BackGround/setup_select')]),
    'setup_attribute': ('属性防御選択', 'Armor Type', 'bar', [_bins('data/setup/BackGround/atr-select_bg')]),
    'setup_color': ('機体色選択', 'Wanzer Color', 'bar', [_bins('data/setup/BackGround/col-select_bg')]),
    'setup_buyitem': ('アイテムの購入', 'Buy Items', 'bar', [_bins('data/setup/BackGround/buyitem_bg')]),
    'setup_buysetup': ('購入してセットアップ', 'Buy and Equip', 'bar', [_bins('data/setup/BackGround/buysetup_bg')]),
    'setup_sellitem': ('アイテムの売却', 'Sell Items', 'bar', [_bins('data/setup/BackGround/sellitem_bg')]),
    'setup_sellsetup': ('パーツの売却', 'Sell Parts', 'bar', [_bins('data/setup/BackGround/sellsetup_bg')]),
    'setup_sellparts': ('装備していないパーツの売却', 'Sell Unequipped Parts', 'bar',
                        [_bins('data/setup/BackGround/sellparts_bg_top')]),
    'setup_stocksetup': ('所持品でセットアップ', 'Equip from Stock', 'bar', [_bins('data/setup/BackGround/stocksetup_bg')]),
    'setup_tradeitem': ('アイテム交換', 'Trade Items', 'bar', [_bins('data/setup/BackGround/tradeitem_bg')]),
    'setup_collection': ('パーツコレクション', 'Parts Collection', 'bar', [_bins('data/setup/BackGround/collection_bg_top')]),
    'icon_office': ('司令部', 'HQ', 'icon', ['data/Base/Entrance/office_icon.mspr.pk']),
    'icon_station': ('傭兵詰所', 'Barracks', 'icon', ['data/Base/Entrance/station_icon.mspr.pk']),
    'icon_hangar': ('格納庫', 'Hangar', 'icon',
                    ['data/Base/Entrance/hanger_icon.mspr.pk', 'data/Base/Entrance/hanger2_icon.mspr.pk']),
    'icon_arena': ('闘技場', 'Arena', 'icon', ['data/Base/Entrance/arena_icon.mspr.pk']),
    'icon_saveload': ('作戦の記録', 'Records', 'icon', ['data/Base/Entrance/save-load_icon.mspr.pk']),
    'icon_exit': ('基地を出る', 'Exit Base', 'icon', ['data/Base/Entrance/exit_icon.mspr.pk']),
    # cells of the name check sheet: (row, first cell, cell count)
    'check_pilot': ('搭乗者名', 'Pilot Name', 'check', [(0, 0, 4)]),
    'check_confirm': ('確認', 'OK?', 'check', [(0, 4, 2)]),
    'check_callsign': ('「 コールサイン 」', '[ Callsign ]', 'check', [(0, 6, 10)]),
    'check_file': ('作戦要項ファイル オープン', 'Opening Mission File', 'check', [(1, 0, 13)]),
    'ending': ('デルタとC.I.S.U.の\n真相究明の戦いは遂に実を結び、\n2094年、O.C.U.、U.S.N.の両国が、\n'
               '第2次ハフマン紛争時の\nサカタインダストリィ事件への\n関与を認めた。\n'
               'これでPSプラン、B組織、そして\nB.D.という兵器をめぐる陰謀は\n全て解明されたかに見えた。\n\n'
               'だが、デルタが見つけた\n新たなB.D.が未来に\nどのような影を落とすのか…\n彼らはまだ知る由もない。',
               'The fight by Delta and CISU to\nuncover the truth bore fruit at last.\n'
               'In 2094, the OCU and the USN both\nadmitted their involvement in the\n'
               'Sakata Industries affair during\nthe Second Huffman Conflict.\n'
               'Every conspiracy around the PS Plan,\nOrganization B and the weapon B.D.\n'
               'seemed to have come to light.\n\n'
               'But what shadow would the new B.D.\nthat Delta found cast on the future...?\n'
               'None of them could know yet.',
               'ending', ['data/Ending/ed_text.msur.pk']),
}

ID_PREFIX = 'Graphics_'
ICON_W, ICON_H = 64, 32
ICON_BAND = (18, 29)  # rows of the Japanese on the icons (row 26 is a white rule)
ICON_RULES = (26, 29)
CHECK_CELL = 16
ENDING_TOP, ENDING_PITCH, ENDING_W = 202, 16, 256


def entry_id(key):
    return ID_PREFIX+key


def limit(key):
    """Widest English line in pixels."""
    kind = LABELS[key][2]
    if kind == 'bar':
        return 160 if key in ('setup_sellparts', 'setup_collection') else 120
    if kind == 'icon':
        return ICON_W - 4
    if kind == 'check':
        return LABELS[key][3][0][2]*CHECK_CELL - 2
    return ENDING_W - 8


def max_lines(key):
    return 14 if LABELS[key][2] == 'ending' else 1


# ---- text ----

def text_width(font, text):
    w = 0
    for ch in text:
        g = font.char_glyph(ch)
        w += font.advance(g) if g is not None else 0
    return max(w-1, 0)


def missing_chars(font, text):
    return sorted({ch for ch in text if ch != '\n' and font.char_glyph(ch) is None})


def draw_text(font, text, put, x0, y0):
    """Call put(x, y) for every ink pixel of one line."""
    x = x0
    for ch in text:
        g = font.char_glyph(ch)
        if g is None:
            continue
        w, rb, rows = font.record(g)
        for y in range(font.height):
            for gx in range(w):
                if rows[y*rb + gx//4] >> (gx % 4*2) & 3:
                    put(x+gx, y0+y)
        x += font.advance(g)


def _ink(font, text, x0, y0):
    pts = set()
    draw_text(font, text, lambda x, y: pts.add((x, y)), x0, y0)
    return pts


def _edge(pts):
    return {(x+dx, y+dy) for x, y in pts for dx in (-1, 0, 1) for dy in (-1, 0, 1)} - pts


# ---- tiles ----

def _unpack(tiles, i):
    t = tiles[i*32:i*32+32]
    return [t[k//2] >> (k % 2*4) & 15 for k in range(64)]


def _pack(px):
    return bytes(px[k] | px[k+1] << 4 for k in range(0, 64, 2))


def _flipped(px, hf, vf):
    return [px[(7-y if vf else y)*8 + (7-x if hf else x)] for y in range(8) for x in range(8)]


class Screen:
    """An NSC map plus its 4bpp tiles, editable as a picture of palette indices."""

    def __init__(self, ncg, nsc):
        self.ncg_head = ncg[:8]
        self.tiles = bytearray(ncg[8:8+struct.unpack_from('<I', ncg, 4)[0]*32])
        self.nsc_head = nsc[:12]
        n, _, self.tw, self.th = struct.unpack_from('<HHBB', nsc, 4)
        self.map = list(struct.unpack_from(f'<{n}H', nsc, 12))
        self.nsc_tail = nsc[12+2*n:]
        self.known = {}

    def tile_px(self, tx, ty):
        e = self.map[ty*self.tw+tx]
        return _flipped(_unpack(self.tiles, e & 0x3FF), e >> 10 & 1, e >> 11 & 1), e >> 12

    def get(self, x0, y0, w, h):
        """Rows of palette indices for a tile-aligned area, plus the palette of its first tile."""
        out = [[0]*w for _ in range(h)]
        pal = None
        for ty in range(y0//8, (y0+h)//8):
            for tx in range(x0//8, (x0+w)//8):
                px, p = self.tile_px(tx, ty)
                pal = p if pal is None else pal
                for k in range(64):
                    out[ty*8+k//8-y0][tx*8+k % 8-x0] = px[k]
        return out, pal

    def put(self, x0, y0, rows, pal):
        """Write a tile-aligned area back, reusing identical tiles and appending new ones."""
        if not self.known:
            for i in range(len(self.tiles)//32):
                self.known.setdefault(bytes(self.tiles[i*32:i*32+32]), i)
        h, w = len(rows), len(rows[0])
        for ty in range(h//8):
            for tx in range(w//8):
                px = [rows[ty*8+k//8][tx*8+k % 8] for k in range(64)]
                key = _pack(px)
                if key not in self.known:
                    self.known[key] = len(self.tiles)//32
                    self.tiles += key
                self.map[(y0//8+ty)*self.tw + x0//8+tx] = self.known[key] | pal << 12

    def ncg(self):
        count = len(self.tiles)//32
        if count > 1024:
            raise ValueError(f'{count} tiles; a screen holds at most 1024')
        return self.ncg_head[:4] + struct.pack('<I', count) + bytes(self.tiles)

    def nsc(self):
        return self.nsc_head + struct.pack(f'<{len(self.map)}H', *self.map) + self.nsc_tail


def _msur_split(data):
    d = _lz(data)
    a, b, c, e = struct.unpack_from('<4I', d, 0)
    return d, (a, b, c, e)


def _msur_join(d, offs, nsc, ncg):
    a, b, c, e = offs
    ncl = d[e:]
    head = struct.pack('<4I', 0x10, 0x10, 0x10+len(nsc), 0x10+len(nsc)+len(ncg))
    return titles.lz10_compress(head + nsc + ncg + ncl)


# ---- kinds ----

def _bar(screen, font, text, key, draw=None):
    w = 0
    while screen.tile_px(w, 0)[0][0] == 0xB and w < screen.tw:
        w += 1
    width = w*8
    rows, pal = screen.get(0, 0, width, 16)
    for y in range(3, 15):
        base = Counter(v for v in rows[y][1:width-1] if v < 0xC).most_common(1)[0][0]
        for x in range(1, width-1):
            if rows[y][x] >= 0xC:
                rows[y][x] = base
    if draw:
        draw(rows)
    else:
        for x, y in _ink(font, text, 4, 3):
            if 1 <= x < width-1 and 3 <= y < 15:
                rows[y][x] = 0xF
    screen.put(0, 0, rows, pal)


def bar_file(data, font, text, key, loose=None, draw=None):
    """New file(s) for a header bar: a .msur.pk, or (ncg, nsc) bins when loose=(ncg, nsc).
    draw(rows) paints the text instead of the game's font (groupart.py's lettering)."""
    if loose:
        ncg_raw, nsc_raw = loose
        screen = Screen(_lz(ncg_raw), _lz(nsc_raw))
        _bar(screen, font, text, key, draw)
        ncg = titles.lz10_compress(screen.ncg()) if ncg_raw[:1] == b'\x10' else screen.ncg()
        nsc = titles.lz10_compress(screen.nsc()) if nsc_raw[:1] == b'\x10' else screen.nsc()
        return ncg, nsc
    d, offs = _msur_split(data)
    a, b, c, e = offs
    screen = Screen(d[c:e], d[a:c])
    _bar(screen, font, text, key, draw)
    return _msur_join(d, offs, screen.nsc(), screen.ncg())


def _rgb(c):
    return titles.rgb555(c)


def icon_file(data, font, text):
    d = _lz(data)
    offs = list(struct.unpack_from('<4I', d, 0))
    ncgr = bytearray(d[offs[0]:offs[1]])
    nclr = d[offs[2]:offs[3]]
    count = struct.unpack_from('<I', nclr, 0x20)[0]//2
    pal = [_rgb(c) for c in struct.unpack_from(f'<{count}H', nclr, 0x28)][:16]
    tiles = ncgr[0x30:0x30+ICON_W*ICON_H//2]

    def get(x, y):
        b = tiles[(y//8*8 + x//8)*32 + y % 8*4 + x % 8//2]
        return b >> (x % 2*4) & 15

    def put(x, y, v):
        o = (y//8*8 + x//8)*32 + y % 8*4 + x % 8//2
        tiles[o] = tiles[o] & (0xF0 if x % 2 == 0 else 0x0F) | v << (x % 2*4)

    def nearest(rgb):
        return min(range(1, 16), key=lambda i: sum((a-b)**2 for a, b in zip(pal[i], rgb)))

    top, bottom = ICON_BAND
    rule = get(ICON_W-1, ICON_RULES[0])
    for x in range(ICON_W):
        a, b = pal[get(x, top-1)], pal[get(x, bottom+1)]
        for y in range(top, bottom+1):
            if y in ICON_RULES:
                put(x, y, rule)
                continue
            t = (y-top+1)/(bottom-top+2)
            put(x, y, nearest(tuple(round(p*(1-t)+q*t) for p, q in zip(a, b))))
    dark = min(range(1, 16), key=lambda i: sum(pal[i]))
    white = max(range(1, 16), key=lambda i: sum(pal[i]))
    ink = _ink(font, text, 2, bottom-11)
    for x, y in _edge(ink):
        if 0 <= x < ICON_W and 0 <= y < ICON_H:
            put(x, y, dark)
    for x, y in ink:
        if 0 <= x < ICON_W and 0 <= y < ICON_H:
            put(x, y, white)
    ncgr[0x30:0x30+len(tiles)] = tiles
    return titles.lz10_compress(d[:offs[0]] + bytes(ncgr) + d[offs[1]:])


def check_file(ncg_data, font, labels):
    """labels: [((row, cell, cells), text)]. Returns the new EntryCheck_ncg.bin."""
    d = bytearray(_lz(ncg_data))
    tiles = memoryview(d)[8:]

    def put(x, y, v):
        o = (y//8*32 + x//8)*32 + y % 8*4 + x % 8//2
        tiles[o] = tiles[o] & (0xF0 if x % 2 == 0 else 0x0F) | v << (x % 2*4)

    for (row, cell, cells), text in labels:
        x0, y0 = cell*CHECK_CELL, row*CHECK_CELL
        for y in range(y0, y0+CHECK_CELL):
            for x in range(x0, x0+cells*CHECK_CELL):
                put(x, y, 0)
        ink = _ink(font, text, x0+1, y0+2)
        for x, y in ink:
            put(x+1, y+1, 1)
        for x, y in ink:
            put(x, y, 3)
    return titles.lz10_compress(bytes(d)) if ncg_data[:1] == b'\x10' else bytes(d)


def ending_file(data, font, text):
    d, offs = _msur_split(data)
    a, b, c, e = offs
    screen = Screen(d[c:e], d[a:c])
    h = screen.th*8
    rows = [[0]*ENDING_W for _ in range(h)]
    ink, y = set(), ENDING_TOP
    for line in text.split('\n'):
        if line:
            ink |= _ink(font, line, (ENDING_W - text_width(font, line))//2, y+2)
        y += ENDING_PITCH
    for x, yy in _edge(ink):
        if 0 <= x < ENDING_W and 0 <= yy < h:
            rows[yy][x] = 2
    for x, yy in ink:
        if 0 <= yy < h:
            rows[yy][x] = 1
    screen.tiles = bytearray(32)
    screen.known = {}
    screen.put(0, 0, rows, 0)
    return _msur_join(d, offs, screen.nsc(), screen.ncg())


def ending_lines(text):
    return len(text.split('\n'))


# ---- build ----

def compose(rom, font, texts, group=None):
    """texts: {key: English}; group: a groupart.GroupArt, or None. Returns ({rom path: bytes}, problems)."""
    import groupart
    files, problems = {}, []
    checks = []
    for key, (jp, default, kind, sources) in LABELS.items():
        if group and key in groupart.ART:
            files.update(group.label_files(key))
            continue
        text = texts.get(key) or default
        draw = None
        if group and key in groupart.LETTERING:
            bad = group.missing_letters(text)
            wide = groupart.X0 + group.text_width(text)
            if bad or wide > groupart.BAR_RIGHT or '\n' in text:
                why = f'the group lettering has no {" ".join(bad)}' if bad else 'it is too wide for the bar'
                problems.append({'id': entry_id(key), 'level': 'warning',
                                 'message': f'Drawn in the game font instead of the group lettering: {why}'})
            else:
                draw = group.draw(text)
        bad = [] if draw else missing_chars(font, text)
        lines = text.split('\n')
        wide = max(text_width(font, line) for line in lines)
        if draw:
            wide = 0
        if bad or wide > limit(key) or len(lines) > max_lines(key):
            why = (f'the font has no {" ".join(bad)}' if bad else
                   f'{len(lines)} lines (max {max_lines(key)})' if len(lines) > max_lines(key) else
                   f'{wide} px wide (max {limit(key)})')
            problems.append({'id': entry_id(key), 'level': 'warning',
                             'message': f'Graphic keeps the default English "{default}": {why}'})
            text = default
        if kind == 'check':
            checks += [(s, text) for s in sources]
            continue
        for src in sources:
            if kind == 'bar' and isinstance(src, dict):
                ncg, nsc = bar_file(None, font, text, key, (rom.read(src['ncg']), rom.read(src['nsc'])), draw)
                files[src['ncg']], files[src['nsc']] = ncg, nsc
            elif kind == 'bar':
                files[src] = bar_file(rom.read(src), font, text, key, draw=draw)
            elif kind == 'icon':
                files[src] = icon_file(rom.read(src), font, text)
            elif kind == 'ending':
                files[src] = ending_file(rom.read(src), font, text)
    path = 'data/name/EntryCheck_ncg.bin'
    files[path] = check_file(rom.read(path), font, checks)
    return files, problems
