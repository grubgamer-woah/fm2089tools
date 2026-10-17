"""The game's proportional font, data/font/msgcmn.fnt.

    0x08 glyph height (12), 0x09 bits per pixel (2), 0x0A glyph count (u16)
    0x4C  95 x u16  glyph used for each ASCII character 0x20..0x7E
    0x10C count x u32  offset of each glyph record
    record: width, bytes per row, then 12 rows of 2bpp pixels (low bits first)
"""
import base64
import struct
import sys
from pathlib import Path

# conversionTables.py sits in the repo root, or next to tools/ when the studio folder's contents are moved up
for _root in Path(__file__).resolve().parents[2:0:-1]:
    sys.path.insert(0, str(_root))
import conversionTables  # noqa: E402

LETTER_SPACING = 1  # matches the gap seen in DeSmuME

# Font changes every build applies (the original font has no " and a 6 px space).
SPACE_GLYPH = 1
SPACE_WIDTH = 3
QUOTE_GLYPH = 0x62B  # ASCII " already points here, but the glyph is empty
QUOTE_ROWS = ['1.1', '1.1', '1.1']  # rows 1-3 of a 3 px wide glyph


def _pack(rows, width, height=12):
    rb = (width*2+7)//8
    out = bytearray(rb*height)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != '.':
                out[y*rb+x//4] |= int(c) << ((x % 4)*2)
    return bytes([width, rb]) + bytes(out)


def tweak(data):
    """Return msgcmn.fnt with a narrower space and a straight double quote."""
    count = struct.unpack_from('<H', data, 0x0A)[0]
    offsets = struct.unpack_from(f'<{count}I', data, 0x10C)
    records = []
    for g, o in enumerate(offsets):
        if g == 0:
            records.append(b''); continue
        w, rb = data[o], data[o+1]
        records.append(data[o:o+2+rb*data[8]])
    records[SPACE_GLYPH] = _pack([], SPACE_WIDTH)
    records[QUOTE_GLYPH] = _pack(['...'] + QUOTE_ROWS, 3)
    head = bytearray(data[:0x10C])
    table = bytearray()
    body = bytearray()
    pos = 0x10C + 4*count
    for g, rec in enumerate(records):
        table += struct.pack('<I', pos if rec else 0)
        body += rec
        pos += len(rec)
    return bytes(head+table+body)


def table_glyph(key):
    """conversionTables keys are the .msg bytes with the UTF-8 marker bits cleared."""
    if len(key) == 1:
        return key[0]
    return ((key[0] & 0x1F) << 6) | (key[1] & 0x3F)


class Font:
    def __init__(self, data):
        self.data = data
        self.height = data[8]
        self.count = struct.unpack_from('<H', data, 0x0A)[0]
        self.ascii = struct.unpack_from('<95H', data, 0x4C)
        self.offsets = struct.unpack_from(f'<{self.count}I', data, 0x10C)
        self.widths = [data[o] if i else 0 for i, o in enumerate(self.offsets)]

        self.chars = {}
        for key, ch in conversionTables.fontTable.items():
            if len(ch) == 1:
                self.chars[table_glyph(key)] = ch
        self.lookup = {}
        for g in sorted(self.chars):
            self.lookup.setdefault(self.chars[g], g)
        # English letters use the game's own ASCII glyphs; skip ones with no pixels.
        for i, g in enumerate(self.ascii):
            if self.widths[g] > 0:
                self.lookup[chr(0x20+i)] = g
            elif self.lookup.get(chr(0x20+i)) == g:
                del self.lookup[chr(0x20+i)]

    def glyph_char(self, g):
        return self.chars.get(g)

    def char_glyph(self, ch):
        return self.lookup.get(ch)

    def advance(self, g):
        w = self.widths[g] if 0 <= g < self.count else 0
        return w+LETTER_SPACING if w else 0

    def record(self, g):
        o = self.offsets[g]
        w, rb = self.data[o], self.data[o+1]
        return w, rb, self.data[o+2:o+2+rb*self.height]

    def to_json(self):
        glyphs = []
        for g in range(self.count):
            if g == 0:
                glyphs.append([0, 0, '']); continue
            w, rb, px = self.record(g)
            glyphs.append([w, rb, base64.b64encode(px).decode()])
        return {'height': self.height, 'spacing': LETTER_SPACING, 'glyphs': glyphs,
                'lookup': self.lookup, 'chars': {str(k): v for k, v in self.chars.items()}}
