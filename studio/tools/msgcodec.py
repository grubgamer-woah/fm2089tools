"""Reads and writes the game's .msg text files.

A .msg file is a 16 byte header, a table of (start, end) offsets and the strings.
    00 00 00 00 | 'TEXT' | 02 | count (u16) | 00 | file size (u32)
Each string is UTF-8 where every code point is a glyph number in msgcmn.fnt.
Code points U+E800..U+E8FF are control codes; U+E800..U+E8BF take one more
UTF-8 code point as their argument. A string ends at the first 00 byte (the game
pads it to 00 00); `end` points at the last byte of that padding.
"""
import re
import struct

import fontdata

LINE_BREAK = 0xE8FF
CONTROL_FIRST = 0xE800
CONTROL_LAST = 0xE8FF
CONTROL_WITH_ARG_LAST = 0xE8BF

# Short descriptions shown in the editor; the tags stay as hex so nothing is lost.
CONTROL_NAMES = {
    0xE801: 'Variable text (00 = main character name, other values = stats, names, help)',
    0xE804: 'Sound or effect (04 = buzzing noise)',
    0xE805: 'Spacing / layout code (0C = big gap)',
    0xE806: 'Unknown code with argument',
    0xE807: 'Unknown code with argument',
    0xE8F5: 'Text colour: black',
    0xE8F6: 'Text colour: red',
    0xE8F7: 'Text colour: yellow',
    0xE8F8: 'Text colour: blue',
    0xE8F9: 'Text colour: default / reset',
}

TAG = re.compile(r'«([^»]*)»')


class MsgError(ValueError):
    pass


def read_cp(b, p):
    c = b[p]
    if c < 0x80:
        return c, p+1
    if 0xC0 <= c < 0xE0:
        return ((c & 0x1F) << 6) | (b[p+1] & 0x3F), p+2
    if 0xE0 <= c < 0xF0:
        return ((c & 0x0F) << 12) | ((b[p+1] & 0x3F) << 6) | (b[p+2] & 0x3F), p+3
    raise MsgError(f'unexpected byte {c:02X} at {p:#x}')


def write_cp(cp):
    if cp < 0x80:
        return bytes([cp])
    if cp < 0x800:
        return bytes([0xC0 | cp >> 6, 0x80 | cp & 0x3F])
    return bytes([0xE0 | cp >> 12, 0x80 | (cp >> 6) & 0x3F, 0x80 | cp & 0x3F])


def tokens(b, start):
    """Yield ('g', glyph) and ('c', code, arg) tokens until the terminator."""
    out = []
    p = start
    while b[p] != 0:
        cp, p = read_cp(b, p)
        if CONTROL_FIRST <= cp <= CONTROL_LAST:
            arg = None
            if cp <= CONTROL_WITH_ARG_LAST:
                arg, p = read_cp(b, p)
            out.append(('c', cp, arg))
        else:
            out.append(('g', cp))
    return out


def tokens_to_text(toks, font):
    parts = []
    for t in toks:
        if t[0] == 'g':
            ch = font.glyph_char(t[1])
            parts.append(ch if ch is not None else f'«g:{t[1]:X}»')
        elif t[1] == LINE_BREAK:
            parts.append('\n')
        elif t[2] is None:
            parts.append(f'«{t[1]:04X}»')
        else:
            parts.append(f'«{t[1]:04X}:{t[2]:02X}»')
    return ''.join(parts)


def text_to_tokens(text, font):
    """Return (tokens, problems). Problems are human readable strings."""
    toks, problems = [], []
    i = 0
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    while i < len(text):
        ch = text[i]
        if ch == '\n':
            toks.append(('c', LINE_BREAK, None)); i += 1; continue
        if ch == '«':
            m = TAG.match(text, i)
            if not m:
                problems.append('A « tag is not closed with »'); i += 1; continue
            body = m.group(1).strip().upper()
            try:
                if body.startswith('G:'):
                    g = int(body[2:], 16)
                    if not 0 < g < font.count:
                        raise ValueError
                    toks.append(('g', g))
                else:
                    code, _, arg = body.partition(':')
                    cp = int(code, 16)
                    if not CONTROL_FIRST <= cp <= CONTROL_LAST:
                        raise ValueError
                    if cp <= CONTROL_WITH_ARG_LAST:
                        if not arg:
                            raise ValueError
                        toks.append(('c', cp, int(arg, 16)))
                    else:
                        if arg:
                            raise ValueError
                        toks.append(('c', cp, None))
            except ValueError:
                problems.append(f'Unknown tag «{m.group(1)}»')
            i = m.end(); continue
        g = font.char_glyph(ch)
        if g is None:
            hint = ' (use a straight \" instead)' if ch in '“”' else ' (use a straight \' instead)' if ch in '‘’' else ''
            problems.append(f'The game font has no "{ch}"{hint}')
        else:
            toks.append(('g', g))
        i += 1
    return toks, problems


def tokens_to_bytes(toks):
    out = bytearray()
    for t in toks:
        if t[0] == 'g':
            out += write_cp(t[1])
        else:
            out += write_cp(t[1])
            if t[2] is not None:
                out += write_cp(t[2])
    out += b'\0\0'
    return bytes(out)


def line_widths(toks, font):
    """Pixel width of each line, counting variable text as zero."""
    widths, w = [], 0
    for t in toks:
        if t[0] == 'g':
            w += font.advance(t[1])
        elif t[1] == LINE_BREAK:
            widths.append(w); w = 0
    widths.append(w)
    return widths


class MsgFile:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        if data[4:8] != b'TEXT':
            raise MsgError(f'{name}: not a TEXT file')
        count = struct.unpack_from('<H', data, 9)[0]
        ptrs = [struct.unpack_from('<II', data, 16+8*i) for i in range(count)]
        self.header = data[:16]
        self.strings = []  # (raw bytes up to the next string, end offset relative to start)
        for i, (s, e) in enumerate(ptrs):
            nxt = ptrs[i+1][0] if i+1 < count else len(data)
            self.strings.append((data[s:nxt], e-s))
        self.base = 16+8*count

    def tokens(self, i):
        return tokens(self.strings[i][0], 0)

    def build(self, replacements):
        """replacements: {index: bytes ending with 00 00}. Unchanged strings keep their exact bytes."""
        count = len(self.strings)
        table = bytearray()
        body = bytearray()
        pos = 16+8*count
        for i, (raw, rel_end) in enumerate(self.strings):
            if i in replacements:
                raw = replacements[i]; rel_end = len(raw)-1
            table += struct.pack('<II', pos, pos+rel_end)
            body += raw
            pos += len(raw)
        header = bytearray(self.header)
        struct.pack_into('<H', header, 9, count)
        struct.pack_into('<I', header, 12, pos)
        return bytes(header+table+body)


def string_id(file_name, index):
    """Same IDs as msgToTxt.py, so its .txt/.tsv files stay compatible."""
    return f"{file_name.replace('.', '_')}_{index+1:03d}"
