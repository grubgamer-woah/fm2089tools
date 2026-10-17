"""The default hero name the name entry screen starts with (ストーム).

It is not in the .msg text: overlay 14 (the name entry screen) keeps it at 0x3898
as u16 keyboard codes ending in FFFF, and copies it into the 7-slot name buffer.
Keyboard codes: hiragana 0-80, katakana 81-161, a-z 162-187, A-Z 192-217.
The slot has room for 5 codes plus the end mark (the next word is a pointer).
"""
import struct

OVERLAY = 14
OFFSET = 0x3898
SLOT = 6  # u16s, end mark included
END = 0xFFFF
ORIGINAL = (93, 100, 50, 113, END)  # ス ト ー ム


def code(ch):
    if 'a' <= ch <= 'z':
        return 162 + ord(ch) - ord('a')
    if 'A' <= ch <= 'Z':
        return 192 + ord(ch) - ord('A')
    raise ValueError(f'"{ch}" is not on the name entry keyboard (use A-Z and a-z)')


def encode(name):
    if not 1 <= len(name) <= SLOT - 1:
        raise ValueError(f'the default name must be 1 to {SLOT - 1} letters long')
    return struct.pack(f'<{len(name)+1}H', *map(code, name), END)


def decode(overlay):
    """The default name in an overlay 14 patched with Latin letters."""
    out, p = '', OFFSET
    while (c := struct.unpack_from('<H', overlay, p)[0]) != END:
        out += chr(c - 162 + ord('a')) if 162 <= c <= 187 else chr(c - 192 + ord('A')) if 192 <= c <= 217 else '?'
        p += 2
    return out


def patch(overlay, name):
    """Return overlay 14 with `name` as the default hero name."""
    if struct.unpack_from('<5H', overlay, OFFSET) != ORIGINAL:
        raise ValueError('overlay 14 does not hold the default name where expected')
    new = encode(name)
    return overlay[:OFFSET] + new + overlay[OFFSET+len(new):]
