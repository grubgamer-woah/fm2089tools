"""Options the patch adds to the game's Config menu: Stat Display and Font.

The Config menu (title screen and base) keeps its settings in a u16 at 0x2127c0e
(game functions 0x207dd28 get / 0x207dd48 set); the game uses bits 0x0003, 0x0010,
0x0020, 0x0100 and 0x0200, and a new game clears it. The patch adds:

* Stat Display (bit 0x8000): the parts info shows the group's stat icons
  ("Icons", bit clear) or the stat names ("Text"). The build writes the parts
  info with copies of the icon glyphs: three per stat, the icon and two empty ones,
  since the game draws at most 16 px of a glyph. Right after the 42 copies come
  42 glyphs that draw each stat's name and a space in the font's letters, and in
  Text mode the game draws those instead. Other text with the icons keeps them.
* Font (bits 0x6000): which font the game's text is drawn in. Font 0 is the
  game's own; each PNG font sheet in the workspace's fonts/ folder (see
  fontsheet.py) adds one more, up to 3. The font file gets one more glyph
  offset table per extra font, where the sheet's letters replace the game's.
  The item only appears when there is more than one font.

How the game is changed (made by dev/make_optcode.py, bytes in optcode.py):
* overlay 3 keeps a "msgcmn.fnt" name for each of its 155 message files; they all
  point at the first one now, and the code goes where the other 154 were.
* overlay 0's glyph width (0x20468a0) and glyph draw (0x20468dc) functions look
  glyphs up through that code, which applies both options.
* the Config menu calls the code right before it is finished (0x20c7284) to add
  the new items, built the same way as the game's own four.
* the items' names and help lines go in unused test messages
  (the last 8 of MsgLabels_WindowMessageForTest), edited in the Studio as
  Options_* entries.
"""
import struct

import fontdata
import optcode

SETTINGS = 0x2127c0e
TEXT_BIT = 0x8000
FONT_BITS = 0x6000
FONT_SHIFT = 13
MAX_FONTS = 4  # the game's own and 3 more
# the order of the copies and words; the same stats as staticons.ICONS
STATS = ['DEF', 'ATK', 'ACC', 'RNG', 'AMMO', 'LNG', 'MEL', 'PWR', 'HP', 'WT', 'MOV', 'EVA', 'ITEM', 'SHRT']
# the game draws at most 16 px of a glyph, so each stat gets 3 glyphs: the icon and two empty
# ones, and in Text mode the stat's name (plus a space) split over the three
PARTS = 4
MAX_GLYPH_WIDTH = 16
ICON_COUNT = PARTS*len(STATS)

OV0, OV0_RAM = 'overlay/0', 0x2045360
OV3, OV3_RAM = 'overlay/3', 0x206af60
FNT_TABLE, FNT_ROWS = 0x210576c, 155  # (file name, first message id, count, font name) per message file
FNT_NAME = 0x2121f20                   # the first "msgcmn.fnt"
CAVE, CAVE_END = 0x2121f2c, 0x21225c8  # where the other 154 names were
WIDTH_FN, WIDTH_LEN = 0x20468a0, 0x3c
DRAW_AT, DRAW_LEN = 0x20468e4, 0x28
MENU_AT = 0x20c7284
# the instructions the patch replaces, to make sure it patches the game it knows
EXPECT = {
    WIDTH_FN: 'e5902004', DRAW_AT: 'e590e004', MENU_AT: 'e5940000',
}

MSG_FILE = 'MsgLabels_WindowMessageForTest.msg'
MSG_BASE = 0x62  # its 23 messages are ids 0x62-0x78
SLOTS = {'stat_label': 15, 'stat_icons': 16, 'stat_text': 17, 'font_label': 18,
         'font_0': 19, 'font_1': 20, 'font_2': 21, 'font_3': 22}
FILE = 'Options'  # the Studio's file name for these entries
# key: (what it is, default English); {font} is the font's name
TEXTS = {
    'stat_label': ('Config menu item', 'Stat Display'),
    'stat_icons': ('Help line when it is set to Icons', 'Stat display setting\nCurrently "Icons".\nParts info shows stat icons.'),
    'stat_text': ('Help line when it is set to Text', 'Stat display setting\nCurrently "Text".\nParts info shows stat names.'),
    'font_label': ('Config menu item (only shown when there is more than one font)', 'Font'),
    'font_help': ('Help line; {font} is the font\'s name', 'Font setting\nCurrently "{font}".'),
}
DEFAULT_FONT_NAME = 'Classic'


def msg_id(key):
    return MSG_BASE + SLOTS[key]


def entry_id(key):
    return f'{FILE}_{key}'


def copy_glyphs(base, stat):
    """The glyphs that stand for one stat's icon in the parts info."""
    first = base + PARTS*STATS.index(stat)
    return list(range(first, first+PARTS))


def _records(data):
    count = struct.unpack_from('<H', data, 0x0A)[0]
    offsets = struct.unpack_from(f'<{count}I', data, 0x10C)
    height = data[8]
    recs = []
    for g, o in enumerate(offsets):
        if g == 0 or not o:
            recs.append(b'')
            continue
        rb = data[o+1]
        recs.append(data[o:o+2+rb*height])
    return recs


def _rows(rec, height=12):
    """A glyph record as rows of 2-bit pixels."""
    if not rec:
        return 0, [[] for _ in range(height)]
    w, rb = rec[0], rec[1]
    px = rec[2:]
    return w, [[(px[y*rb+x//4] >> (x % 4*2)) & 3 for x in range(w)] for y in range(height)]


def pack(width, rows):
    rb = (width*2+7)//8
    out = bytearray(rb*len(rows))
    for y, row in enumerate(rows):
        for x, v in enumerate(row[:width]):
            out[y*rb+x//4] |= (v & 3) << (x % 4*2)
    return bytes([width, rb]) + bytes(out)


def word_records(font_recs, ascii_glyphs, word, height=12):
    """The word and a space as PARTS glyphs of at most MAX_GLYPH_WIDTH px each.

    The word is drawn as text would be (letters, the game's letter spacing, a space),
    then cut at blank columns; the game's letter spacing after each glyph stands in
    for the blank column at each cut."""
    gap = fontdata.LETTER_SPACING
    strip = [[] for _ in range(height)]
    for c in word + ' ':
        w, r = _rows(font_recs[ascii_glyphs[ord(c)-0x20]], height)
        for y in range(height):
            strip[y] += r[y] + [0]*gap
    width = len(strip[0]) - gap  # the last glyph's spacing comes from the game

    def blank(x):
        return not any(strip[y][x] for y in range(height))
    pieces, start = [], 0
    while start < width:
        end = min(width, start + MAX_GLYPH_WIDTH)
        if end < width:
            cuts = [x for x in range(end, start, -1) if x < width and blank(x)]
            if not cuts:
                raise ValueError(f'"{word}" has no gap to split it at')
            end = cuts[0]
        pieces.append([row[start:end] for row in strip])
        start = end + gap
    if len(pieces) > PARTS:
        raise ValueError(f'"{word}" does not fit in {PARTS} glyphs')
    pieces += [[[] for _ in range(height)]]*(PARTS-len(pieces))
    return [pack(len(rows[0]), rows) for rows in pieces]


def serialize(data, recs, alt_tables=()):
    """The font file with these records; alt_tables: lists of glyph -> record index overrides
    ({glyph: record bytes}), each written as one more full offset table. Returns (bytes, table offsets)."""
    count = len(recs)
    head = bytearray(data[:0x10C])
    struct.pack_into('<H', head, 0x0A, count)
    body = bytearray()
    pos = 0x10C + 4*count
    offsets = []
    for rec in recs:
        offsets.append(pos + len(body) if rec else 0)
        body += rec
    tables = []
    extra = bytearray()
    for over in alt_tables:
        own = list(offsets)
        recs_at = pos + len(body) + len(extra)
        blob = bytearray()
        for g, rec in sorted(over.items()):
            own[g] = recs_at + len(blob)
            blob += rec
        extra += blob
        while (pos + len(body) + len(extra)) % 4:
            extra += b'\0'
        tables.append(pos + len(body) + len(extra))
        extra += struct.pack(f'<{count}I', *own)
    return bytes(head + struct.pack(f'<{count}I', *offsets) + body + extra), tables


def add_stat_glyphs(data, icons):
    """The font with a copy of each stat icon and, right after them, each stat's name as one glyph.
    icons: {stat: glyph}. Returns (font bytes, first copy glyph)."""
    recs = _records(data)
    base = len(recs)
    ascii_glyphs = struct.unpack_from('<95H', data, 0x4C)
    empty = pack(0, [[] for _ in range(data[8])])
    recs += [rec for s in STATS for rec in (recs[icons[s]], *[empty]*(PARTS-1))]
    recs += [rec for s in STATS for rec in word_records(recs, ascii_glyphs, s, data[8])]
    return serialize(data, recs)[0], base


def with_fonts(data, fonts, copy_base=None):
    """The font with one more offset table per extra font. fonts: [{char: record}]; the words
    of the stat names are drawn again in each font's letters. Returns (bytes, table offsets)."""
    recs = _records(data)
    ascii_glyphs = struct.unpack_from('<95H', data, 0x4C)
    overs = []
    for letters in fonts:
        over = {ascii_glyphs[ord(c)-0x20]: rec for c, rec in letters.items()}
        if copy_base is not None:
            mixed = list(recs)
            for g, rec in over.items():
                mixed[g] = rec
            for n, s in enumerate(STATS):
                for k, rec in enumerate(word_records(mixed, ascii_glyphs, s, data[8])):
                    over[copy_base + ICON_COUNT + PARTS*n + k] = rec
        overs.append(over)
    return serialize(data, recs, overs)


def replace_letters(data, letters):
    """The font with these letters ({char: record}) in place of its own."""
    recs = _records(data)
    ascii_glyphs = struct.unpack_from('<95H', data, 0x4C)
    for c, rec in letters.items():
        recs[ascii_glyphs[ord(c)-0x20]] = rec
    return serialize(data, recs)[0]


def _check(code, addr, ram, expect):
    o = addr - ram
    got = struct.unpack_from('<I', code, o)[0]
    if f'{got:08x}' != expect:
        raise ValueError(f'unexpected game code at {addr:#x} ({got:08x}); is this the Japanese ROM?')


def patch_code(ov0, ov3, copy_base, show_stat, font_tables):
    """Overlays 0 and 3 with the options' code. font_tables: offsets of the extra fonts' tables."""
    ov0, ov3 = bytearray(ov0), bytearray(ov3)
    _check(ov0, WIDTH_FN, OV0_RAM, EXPECT[WIDTH_FN])
    _check(ov0, DRAW_AT, OV0_RAM, EXPECT[DRAW_AT])
    _check(ov3, MENU_AT, OV3_RAM, EXPECT[MENU_AT])
    if ov3[FNT_NAME-OV3_RAM:FNT_NAME-OV3_RAM+11] != b'msgcmn.fnt\0':
        raise ValueError('font names not where expected in overlay 3')
    for i in range(FNT_ROWS):
        o = FNT_TABLE - OV3_RAM + 16*i + 12
        name = struct.unpack_from('<I', ov3, o)[0]
        if not FNT_NAME <= name < CAVE_END or ov3[name-OV3_RAM:name-OV3_RAM+11] != b'msgcmn.fnt\0':
            raise ValueError(f'message file {i} does not use msgcmn.fnt')
        struct.pack_into('<I', ov3, o, FNT_NAME)
    cave = bytearray(optcode.CAVE)
    tables = list(font_tables)[:MAX_FONTS-1]
    struct.pack_into('<I', cave, optcode.DATA['copy_base'], copy_base if copy_base is not None else 0xFFFF)
    struct.pack_into('<I', cave, optcode.DATA['font_count'], 1 + len(tables))
    struct.pack_into('<I', cave, optcode.DATA['show_stat'], int(bool(show_stat and copy_base is not None)))
    struct.pack_into('<3I', cave, optcode.DATA['font_tables'], *(tables + [0x10C]*(3-len(tables))))
    c = CAVE - OV3_RAM
    ov3[c:c+len(cave)] = cave
    ov3[c+len(cave):CAVE_END-OV3_RAM] = bytes(CAVE_END-CAVE-len(cave))
    for addr, code in ((WIDTH_FN, optcode.WIDTH), (DRAW_AT, optcode.DRAW)):
        o = addr - OV0_RAM
        size = WIDTH_LEN if addr == WIDTH_FN else DRAW_LEN
        ov0[o:o+size] = code + bytes.fromhex('00f020e3')*((size-len(code))//4)   # nop
    o = MENU_AT - OV3_RAM
    ov3[o:o+4] = optcode.MENU
    return bytes(ov0), bytes(ov3)


def texts(project_entries, font_names):
    """{slot: English} for the options' messages."""
    def en(key):
        return project_entries.get(entry_id(key), {}).get('en') or TEXTS[key][1]
    out = {SLOTS[k]: en(k) for k in ('stat_label', 'stat_icons', 'stat_text', 'font_label')}
    for n, name in enumerate(font_names[:MAX_FONTS]):
        out[SLOTS[f'font_{n}']] = en('font_help').replace('{font}', name)
    return out
