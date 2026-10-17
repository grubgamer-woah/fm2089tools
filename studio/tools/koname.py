"""The name entry screens from the Korean/English fan patch, in English.

Kiley asked for that patch's screens after New Game: the intro that types out
"Enter Pilot Name", the romaji keyboard with English buttons, and the confirmed
screen. They are taken from the user's own copy of the patched ROM at build time
("Front Mission 2089 - Border of Madness (En+Ko).nds", next to the Japanese ROM);
nothing from it is stored in this repository.

That patch's overlay 14 picks Korean, English or Japanese tables from a language
setting its menus write to RAM. Here the reads of that setting load 2 (English)
instead, its English file names are pointed at the Japanese ROM's own files, and
those files get the English pictures. Its English default name copy is turned into
a no-op so heroname.py still sets the default name.

Its keyboard gives its keys the codes 0-80, which the Japanese game saves and
shows in dialogue as kana (the patch fixes that elsewhere). So letter keys are
remapped to the Japanese game's own letter codes (a-z 162-187, A-Z 192-217).
Digits and symbols keep their kana codes, and the build's MsgLabels_font.msg
(the character each name code shows in dialogue) gets those characters there;
the romaji keyboard has no kana keys, so nothing else uses those slots.
"""
import hashlib
import struct

import msgcodec
import portraits
import titles

KO_MD5 = '4b813a912697d890e32914f65acac3c7'
KO_SIZE = 44040192
KO_NAME = 'Front Mission 2089 - Border of Madness (En+Ko).nds'
OVERLAY = 'overlay/14'
BASE = 0x21F74C0
SIZE = 0x4FD8

# ldr rX, [rX] of the language setting -> mov rX, #2 (English), except 0x21FC244 -> #0:
# its English branch saves the patch's own default name, coded for its keyboard
LANGUAGE_READS = {0x21FB48C: (0xE5900000, 0xE3A00002), 0x21FC210: (0xE5911000, 0xE3A01002),
                  0x21FC244: (0xE5911000, 0xE3A01000), 0x21FC2D4: (0xE5922000, 0xE3A02002),
                  0x21FC304: (0xE59CC000, 0xE3A0C002), 0x21FC3C4: (0xE59CC000, 0xE3A0C002)}
# English default name copy: copy the name slot onto itself (ldr r0 = same literal as r1; nop)
NAME_COPY = {0x21FB57C: (0xE59F01C8, 0xE59F0188), 0x21FB580: (0xE08F0000, 0xE1A00000)}
# the patch's English folders -> the Japanese files they replace
FILES = {
    '/data/name/en/fon00_ncg.bin': ('/data/name/fon00_ncg.bin', 'data/name/en/fon00_ncg.bin'),
    '/data/name/en/fon01_ncg.bin': ('/data/name/fon01_ncg.bin', 'data/name/en/fon01_ncg.bin'),
    '/data/name/en/fon02_ncg.bin': ('/data/name/fon02_ncg.bin', 'data/name/en/fon02_ncg.bin'),
    '/data/name/en/check/EntryCheck_ncg.bin': ('/data/name/EntryCheck_ncg.bin', 'data/name/en/check/EntryCheck_ncg.bin'),
    '/data/name/en/env/NameEntryEnv.': ('/data/name/NameEntryEnv.', None),
}
KEYS = 0x21FBB80, 0xE6     # key -> code, u16
SPRITES = 0x21FBF02, 0xDB  # code -> name sprite, u16; sprite - 386 = MsgLabels_font string
FIRST_SPRITE = 386
KO_FONT_MSG = 'data/font/en/MsgLabels_font.msg'
NO_KEY = 218
# The patch draws a few keys with Japanese marks (、 ‥ ー 「 」 ×) that type , ' - [ ] * and _
# in dialogue; those cells of fon01 (16x16, 8 per row, index 43 = cell 0) are redrawn.
# Rows of 16: '#' = face (colour 1); the outline (colour 3) is added around it.
KEY_SHEET = '/data/name/fon01_ncg.bin'
KEY_GLYPHS = {
    8: ['', '', '', '', '', '', '', '', '', '', '.##', '.##', '..#', '.#'],              # ,
    9: ['', '.##', '.##', '..#', '.#'],                                                  # '
    10: ['', '', '', '', '', '', '', '....#######'],                                     # -
    18: ['', '.........####', '.........#', '.........#', '.........#', '.........#',
         '.........#', '.........#', '.........#', '.........#', '.........#', '.........#',
         '.........####'],                                                               # [
    19: ['', '..####', '.....#', '.....#', '.....#', '.....#', '.....#', '.....#', '.....#',
         '.....#', '.....#', '.....#', '..####'],                                        # ]
    20: ['', '', '', '.......#', '....#..#..#', '.....#.#.#', '......###', '....#######',
         '......###', '.....#.#.#', '....#..#..#', '.......#'],                           # *
    23: ['', '', '', '', '', '', '', '', '', '', '', '', '.############'],              # _
}
ENV_KINDS = ('NANR', 'NCER', 'NCGR', 'NCLR')
SAME_PATH = ['data/name/CallCheckEnd_nsc.bin']  # changed in place by the patch


def is_ko_rom(data):
    return hashlib.md5(data).hexdigest() == KO_MD5


def find(folders):
    """Path of the patched ROM in any of the folders, or None."""
    for folder in folders:
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob('*.nds'), key=lambda p: p.name != KO_NAME):
            if p.stat().st_size == KO_SIZE and is_ko_rom(p.read_bytes()):
                return p
    return None


def _word(buf, addr, old, new):
    o = addr - BASE
    if struct.unpack_from('<I', buf, o)[0] != old:
        raise ValueError(f'overlay 14 of the En+Ko ROM is not the expected version (at {addr:#x})')
    struct.pack_into('<I', buf, o, new)


def key_chars(ko_rom, font):
    """The character each of the patch's key codes types, read from its English name font table."""
    ov = ko_rom.read(OVERLAY)
    sprites = struct.unpack_from(f'<{SPRITES[1]}H', ov, SPRITES[0]-BASE)
    msg = msgcodec.MsgFile('MsgLabels_font.msg', ko_rom.read(KO_FONT_MSG))
    ascii_of = {g: chr(0x20+i) for i, g in enumerate(font.ascii)}
    chars = {}
    for code in range(NO_KEY):
        toks = msg.tokens(sprites[code]-FIRST_SPRITE)
        if len(toks) == 1 and toks[0][0] == 'g' and toks[0][1] in ascii_of:
            chars[code] = ascii_of[toks[0][1]]
    return chars, sprites


def redraw_keys(data):
    """fon01 of the patch with KEY_GLYPHS drawn in."""
    d = bytearray(portraits.lz10(data) if data[:1] == b'\x10' else data)
    tiles = memoryview(d)[8:]

    def put(x, y, v):
        o = (y//8*16 + x//8)*32 + y % 8*4 + x % 8//2
        tiles[o] = tiles[o] & (0xF0 if x % 2 == 0 else 0x0F) | v << (x % 2*4)

    for cell, rows in KEY_GLYPHS.items():
        x0, y0 = cell % 8*16, cell//8*16
        face = {(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == '#'}
        edge = {(x+dx, y+dy) for x, y in face for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))} - face
        for y in range(16):
            for x in range(16):
                put(x0+x, y0+y, 1 if (x, y) in face else 3 if (x, y) in edge else 0)
    return titles.lz10_compress(bytes(d))


def compose(ko_rom, font):
    """({rom path: bytes}, {MsgLabels_font index: character}) for the Japanese ROM.
    ko_rom: ndsrom.Rom of the En+Ko ROM; font: fontdata.Font of the build."""
    ov = bytearray(ko_rom.read(OVERLAY))
    if len(ov) != SIZE:
        raise ValueError('overlay 14 of the En+Ko ROM is not the expected size')
    for addr, (old, new) in {**LANGUAGE_READS, **NAME_COPY}.items():
        _word(ov, addr, old, new)
    keys = list(struct.unpack_from(f'<{KEYS[1]}H', ov, KEYS[0]-BASE))
    chars, sprites = key_chars(ko_rom, font)
    name_chars = {}
    new_keys = []
    for c in keys:
        ch = chars.get(c)
        if ch is None:
            new_keys.append(NO_KEY)
        elif ch.isascii() and ch.isalpha():
            new_keys.append(jp_code(ch))
        else:
            new_keys.append(c)
            name_chars[sprites[c]-FIRST_SPRITE] = ch
    keys = new_keys
    struct.pack_into(f'<{KEYS[1]}H', ov, KEYS[0]-BASE, *keys)
    files = {}
    for en, (jp, src) in FILES.items():
        o = ov.find(en.encode() + b'\0')
        if o < 0:
            raise ValueError(f'{en} not found in overlay 14 of the En+Ko ROM')
        ov[o:o+len(en)] = jp.encode().ljust(len(en), b'\0')
        if src:
            files[jp[1:]] = redraw_keys(ko_rom.read(src)) if jp == KEY_SHEET else ko_rom.read(src)
    for kind in ENV_KINDS:
        files[f'data/name/NameEntryEnv.{kind}'] = ko_rom.read(f'data/name/en/env/NameEntryEnv.{kind}')
    for path in SAME_PATH:
        files[path] = ko_rom.read(path)
    files[OVERLAY] = bytes(ov)
    return files, name_chars


def jp_code(ch):
    """The Japanese game's name code for an English letter."""
    return 192 + ord(ch) - ord('A') if ch.isupper() else 162 + ord(ch) - ord('a')
