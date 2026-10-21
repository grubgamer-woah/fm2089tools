"""Font sheets: the game font's English letters as a PNG you can draw over.

A sheet is 16 x 6 cells of 16 x 16 pixels for the characters " " (0x20) to "~"
(0x7E), left to right, top to bottom; the last cell is unused. In each cell:
  rows 1-12   the letter, from the cell's left edge (12 px high, as in the game)
  row 14      the letter's width: one red pixel per pixel of width, from the left
Ink is black; the game's font also uses two greys for soft edges (dark grey and
light grey here). White or transparent is background.

Every PNG in the workspace's fonts/ folder is one more font the player can pick
in the game's Config menu (options.py), named after the file. Letters that are
left empty keep the game's own glyph.
"""
from pathlib import Path

import fontdata
import options
import portraits
import titles

COLS, ROWS, CELL = 16, 6, 16
TOP = 1
WIDTH_ROW = 14
FIRST, LAST = 0x20, 0x7E
INK = {1: (0, 0, 0), 2: (96, 96, 96), 3: (176, 176, 176)}
RED = (230, 0, 0)
FOLDER = 'fonts'
MAX_FONTS = options.MAX_FONTS - 1


def export(font, height=12):
    """The font's English letters as a sheet (PNG bytes)."""
    w, h = COLS*CELL, ROWS*CELL
    px = bytearray([255, 255, 255, 255]*(w*h))

    def put(x, y, rgb):
        px[(y*w+x)*4:(y*w+x)*4+3] = bytes(rgb)
    for c in range(FIRST, LAST+1):
        n = c - FIRST
        x0, y0 = n % COLS*CELL, n//COLS*CELL
        g = font.char_glyph(chr(c))
        if g is None:
            continue
        gw, rb, data = font.record(g)
        for y in range(height):
            for x in range(min(gw, CELL)):
                v = (data[y*rb+x//4] >> (x % 4*2)) & 3
                if v:
                    put(x0+x, y0+TOP+y, INK[v])
        for x in range(min(gw, CELL)):
            put(x0+x, y0+WIDTH_ROW, RED)
    # faint cell borders on the unused bottom row help drawing
    for n in range(COLS*ROWS):
        x0, y0 = n % COLS*CELL, n//COLS*CELL
        for x in range(CELL):
            put(x0+x, y0+CELL-1, (225, 225, 240))
    return portraits.png(w, h, bytes(px))


def _value(rgba):
    r, g, b, a = rgba
    if a < 128 or min(r, g, b) > 220:
        return 0
    if r > 150 and g < 100 and b < 100:
        return 'red'
    lum = (r*3 + g*6 + b)/10
    return min(INK, key=lambda v: abs(lum - INK[v][0]))


def load(png_bytes, height=12):
    """{char: glyph record} for the letters drawn on a sheet."""
    w, h, rgba = titles.read_png(png_bytes)
    if w < COLS*CELL or h < ROWS*CELL:
        raise ValueError(f'a font sheet is {COLS*CELL} x {ROWS*CELL} pixels; this one is {w} x {h}')

    def at(x, y):
        return _value(tuple(rgba[(y*w+x)*4:(y*w+x)*4+4]))
    letters = {}
    for c in range(FIRST, LAST+1):
        n = c - FIRST
        x0, y0 = n % COLS*CELL, n//COLS*CELL
        width = sum(1 for x in range(CELL) if at(x0+x, y0+WIDTH_ROW) == 'red')
        rows = [[at(x0+x, y0+TOP+y) for x in range(CELL)] for y in range(height)]
        rows = [[v if isinstance(v, int) else 0 for v in row] for row in rows]
        ink = any(any(row) for row in rows)
        if not ink and not width:
            continue  # left empty: the game's own letter
        if not width:
            width = max(x for row in rows for x, v in enumerate(row) if v) + 2
        letters[chr(c)] = options.pack(width, [row[:width] for row in rows])
    return letters


def find(workspace):
    """[(name, path)] of the font sheets in the workspace, at most MAX_FONTS."""
    folder = Path(workspace)/FOLDER
    if not folder.is_dir():
        return []
    return [(p.stem, p) for p in sorted(folder.glob('*.png'))][:MAX_FONTS]


def font_with(font_data, letters):
    """A fontdata.Font that draws these letters, to measure text in that font."""
    return fontdata.Font(options.replace_letters(font_data, letters))
