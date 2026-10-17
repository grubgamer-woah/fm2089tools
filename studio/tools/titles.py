"""Mission title screens: data/bg/mtittle_bg_NN_{ncg,ncl,nsc}.bin.

Each title is one 256x256 BG (the DS shows the top 256x192):
  ncg  LZ10 of "NCG\\0" + u32 tile count + 4bpp 8x8 tiles
  ncl  "NCL\\0" + u32 color count (128) + RGB555 colors; the image uses palettes 0-3,
       color 0 is transparent and color 1 is black in each; palette 3 is the same
       orange-to-white ramp in every title (the "Mission NN" bar)
  nsc  "NSC\\0" + u16 entry count + u16 0 + u8 width + u8 height (in tiles) + u16 0
       + one u16 per tile (tile | hflip<<10 | vflip<<11 | palette<<12)

`encode` turns any PNG into those three files with only the standard library, so
the Studio needs nothing installed. It is slow-ish (seconds per image); the Studio
caches the result per image.
"""
import re
import struct
import zlib

import portraits

FOLDER = 'data/bg/'
NAME_RX = re.compile(r'^mtittle_bg_(\d\d)$')
SCREEN_H = 192
FREE_PALETTES = 3  # palettes 0-2 are free per image; palette 3 stays the shared ramp
TRANSPARENT = 0x7C1E


def slots(rom):
    """Names of the mission title screens in the ROM (not the 256x192 info screens)."""
    out = []
    for path in rom.list(FOLDER):
        m = re.fullmatch(FOLDER + r'(mtittle_bg_\d\d)_nsc\.bin', path)
        if m:
            _, _, w, h = struct.unpack_from('<HHBB', rom.read(path), 4)
            if (w, h) == (32, 32):
                out.append(m.group(1))
    return out


def paths(name):
    return {k: f'{FOLDER}{name}_{k}.bin' for k in ('ncg', 'ncl', 'nsc')}


def number(file_name):
    """Title number from a file name: m10.png, mtittle_bg_01_nsc.png, Title 7.png -> 10, 1, 7."""
    m = re.search(r'(?:mtittle_bg_|^m|\D)(\d{1,2})(?!\d)', file_name.rsplit('/', 1)[-1].rsplit('\\', 1)[-1])
    return int(m.group(1)) if m else None


# ---- PNG ----

def read_png(data):
    """Return (width, height, rgba bytes). 8-bit and paletted PNGs, not interlaced."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('not a PNG file')
    p, idat, plte, trns = 8, [], b'', b''
    while p < len(data):
        n, kind = struct.unpack_from('>I4s', data, p)
        body = data[p+8:p+8+n]
        p += 12 + n
        if kind == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', body)
        elif kind == b'PLTE':
            plte = body
        elif kind == b'tRNS':
            trns = body
        elif kind == b'IDAT':
            idat.append(body)
        elif kind == b'IEND':
            break
    if interlace:
        raise ValueError('interlaced PNGs are not supported; save it again without interlacing')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    if depth != 8 and not (ctype in (0, 3) and depth in (1, 2, 4)):
        raise ValueError(f'{depth}-bit PNGs are not supported; save it as 8-bit')
    bpp = max(1, channels*depth//8)
    stride = (w*channels*depth + 7)//8
    raw = zlib.decompress(b''.join(idat))
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y*(stride+1)]
        line = bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
        for i in range(stride):
            a = line[i-bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i-bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b)//2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2*c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    out = bytearray(w*h*4)
    for y, line in enumerate(rows):
        for x in range(w):
            o = (y*w + x)*4
            if depth < 8:
                v = line[x*depth//8] >> (8 - depth - x*depth % 8) & ((1 << depth) - 1)
            else:
                v = line[x*channels]
            if ctype == 3:
                out[o:o+4] = bytes((*plte[v*3:v*3+3], trns[v] if v < len(trns) else 255))
            elif ctype == 0:
                g = v*255//((1 << depth) - 1)
                out[o:o+4] = bytes((g, g, g, 255))
            elif ctype == 4:
                out[o:o+4] = bytes((v, v, v, line[x*2+1]))
            elif ctype == 2:
                out[o:o+3] = line[x*3:x*3+3]
                out[o+3] = 255
            else:
                out[o:o+4] = line[x*4:x*4+4]
    return w, h, bytes(out)


png = portraits.png


# ---- LZ10 ----

def lz10_compress(data):
    """Plain LZ10 (BIOS-compatible; never copies from the byte just written, so VRAM-safe)."""
    out = bytearray(b'\x10' + len(data).to_bytes(3, 'little'))
    i, n = 0, len(data)
    heads = {}
    while i < n:
        flag_pos = len(out)
        out.append(0)
        for bit in range(8):
            if i >= n:
                break
            best, best_d = 0, 0
            key = data[i:i+3]
            for j in reversed(heads.get(key, ())):
                d = i - j
                if d > 0x1000:
                    break
                if d < 2:
                    continue
                k = 0
                while k < 18 and i+k < n and data[j+k] == data[i+k]:
                    k += 1
                if k > best:
                    best, best_d = k, d
                    if k == 18:
                        break
            step = best if best >= 3 else 1
            if best >= 3:
                out[flag_pos] |= 0x80 >> bit
                x = (best - 3) << 12 | (best_d - 1)
                out += bytes((x >> 8, x & 255))
            else:
                out.append(data[i])
            for t in range(i, i+step):
                lst = heads.setdefault(data[t:t+3], [])
                lst.append(t)
                if len(lst) > 64:
                    del lst[:32]
            i += step
    while len(out) % 4:
        out.append(0)
    return bytes(out)


# ---- decode / render ----

def rgb555(c):
    return ((c & 31)*255//31, (c >> 5 & 31)*255//31, (c >> 10 & 31)*255//31)


def render(ncg, ncl, nsc, screen_only=True):
    """(width, height, rgba) of a title as the DS draws it; transparent shows as black."""
    tiles = portraits.lz10(ncg)[8:]
    count = struct.unpack_from('<I', ncl, 4)[0]
    pal = [rgb555(c) for c in struct.unpack_from(f'<{count}H', ncl, 8)]
    n, _, tw, th = struct.unpack_from('<HHBB', nsc, 4)
    entries = struct.unpack_from(f'<{n}H', nsc, 12)
    w, h = tw*8, min(th*8, SCREEN_H) if screen_only else th*8
    px = bytearray(w*h*4)
    for t, e in enumerate(entries):
        tx, ty = t % tw*8, t//tw*8
        if ty >= h:
            break
        base, hf, vf, p = (e & 0x3FF)*32, e >> 10 & 1, e >> 11 & 1, e >> 12
        for k in range(64):
            b = tiles[base + k//2]
            v = b & 15 if k % 2 == 0 else b >> 4
            x, y = k % 8, k//8
            o = ((ty + (7-y if vf else y))*w + tx + (7-x if hf else x))*4
            px[o:o+4] = bytes((*pal[p*16+v], 255)) if v else b'\0\0\0\xff'
    return w, h, bytes(px)


# ---- encode ----

def _dist(a, b):
    dr, dg, db = a[0]-b[0], a[1]-b[1], a[2]-b[2]
    return 2*dr*dr + 4*dg*dg + db*db


def _kmeans(colors, k, rounds=8):
    """colors: {rgb5: weight}. Returns up to k centers (rgb5 tuples)."""
    items = sorted(colors.items(), key=lambda kv: -kv[1])
    if len(items) <= k:
        return [c for c, _ in items]
    # farthest-point start, weighted toward common colors
    centers = [items[0][0]]
    dmin = {c: _dist(c, centers[0]) for c, _ in items}
    while len(centers) < k:
        c = max(items, key=lambda kv: dmin[kv[0]]*kv[1]**.5)[0]
        if dmin[c] == 0:
            break
        centers.append(c)
        for x, _ in items:
            d = _dist(x, c)
            if d < dmin[x]:
                dmin[x] = d
    fc = [tuple(map(float, c)) for c in centers]
    for _ in range(rounds):
        sums = [[0., 0., 0., 0.] for _ in fc]
        for c, wgt in items:
            j = min(range(len(fc)), key=lambda i: _dist(c, fc[i]))
            s = sums[j]
            s[0] += c[0]*wgt; s[1] += c[1]*wgt; s[2] += c[2]*wgt; s[3] += wgt
        moved = False
        for j, s in enumerate(sums):
            if s[3]:
                nc = (s[0]/s[3], s[1]/s[3], s[2]/s[3])
                moved |= nc != fc[j]
                fc[j] = nc
        if not moved:
            break
    return sorted({tuple(min(31, max(0, round(v))) for v in c) for c in fc})


def encode(width, height, rgba, original_ncl, original_nsc):
    """Return (ncg, ncl, nsc) bytes for a 256-wide picture (rows past 192 are not shown)."""
    if width != 256 or height not in (192, 256):
        raise ValueError(f'the picture is {width}x{height}; it must be 256x256 or 256x192')
    ramp = [struct.unpack_from('<H', original_ncl, 8 + 2*(48+i))[0] for i in range(16)]
    ramp5 = [(c & 31, c >> 5 & 31, c >> 10 & 31) for c in ramp]
    black = (0, 0, 0)

    def pixel(x, y):
        o = (y*width + x)*4
        r, g, b, a = rgba[o:o+4]
        if a < 128:
            return None
        r, g, b = r*a//255, g*a//255, b*a//255  # semi-transparent edges sit on black
        if r > 200 and b > 200 and g < 40:  # magenta = transparent, as in the game's own art
            return None
        return (r*31 + 127)//255, (g*31 + 127)//255, (b*31 + 127)//255

    tw, th = 32, SCREEN_H//8
    tiles = []
    for ty in range(th):
        for tx in range(tw):
            tiles.append([pixel(tx*8 + i % 8, ty*8 + i//8) for i in range(64)])

    def histogram(ts):
        h = {}
        for t in ts:
            for c in t:
                if c is not None:
                    h[c] = h.get(c, 0) + 1
        return h

    # start: split tiles into groups by their average color
    means = []
    for t in tiles:
        cs = [c for c in t if c is not None] or [black]
        means.append(tuple(sum(c[i] for c in cs)/len(cs) for i in range(3)))
    seeds = _kmeans({m: 1 for m in means}, FREE_PALETTES)
    groups = [min(range(len(seeds)), key=lambda j: _dist(m, seeds[j])) for m in means]
    palettes = []
    for _ in range(4):
        palettes = []
        for j in range(FREE_PALETTES):
            hist = histogram(t for t, g in zip(tiles, groups) if g == j)
            hist.pop(black, None)
            palettes.append([black] + _kmeans(hist, 14))
        palettes.append(ramp5[1:])  # palette 3: black + the shared ramp
        nearest = {}

        def best(c, p):
            key = (c, p)
            if key not in nearest:
                nearest[key] = min(range(len(palettes[p])), key=lambda i: _dist(c, palettes[p][i]))
            return nearest[key]

        def cost(t, p):
            return sum(_dist(c, palettes[p][best(c, p)]) for c in t if c is not None)

        new = [min(range(len(palettes)), key=lambda p: cost(t, p)) for t in tiles]
        if new == groups:
            break
        groups = new

    # palette data: color 0 transparent, then each palette's colors
    pal_words = []
    for p in range(FREE_PALETTES):
        words = [TRANSPARENT] + [c[0] | c[1] << 5 | c[2] << 10 for c in palettes[p]]
        pal_words += words + [0]*(16 - len(words))
    pal_words += ramp
    ncl = original_ncl[:8] + struct.pack('<64H', *pal_words) + b'\0'*(len(original_ncl) - 8 - 128)

    # tiles, de-duplicated with flips
    blank = bytes(32)
    tile_data, index = [blank], {blank: (0, 0, 0)}
    entries = []
    for t, p in zip(tiles, groups):
        idx = [0 if c is None else 1 + best(c, p) for c in t]
        rows = [idx[r*8:r*8+8] for r in range(8)]

        def pack(rs):
            return bytes(rs[r][x] | rs[r][x+1] << 4 for r in range(8) for x in range(0, 8, 2))
        if not any(idx):
            entries.append(p << 12)
            continue
        raw = pack(rows)
        hit = index.get(raw)
        if hit is None:
            index[raw] = (len(tile_data), 0, 0)
            index.setdefault(pack([r[::-1] for r in rows]), (len(tile_data), 1, 0))
            index.setdefault(pack(rows[::-1]), (len(tile_data), 0, 1))
            index.setdefault(pack([r[::-1] for r in rows[::-1]]), (len(tile_data), 1, 1))
            hit = index[raw]
            tile_data.append(raw)
        n, hf, vf = hit
        entries.append(n | hf << 10 | vf << 11 | p << 12)
    count, _, otw, oth = struct.unpack_from('<HHBB', original_nsc, 4)
    entries += [0]*(count - len(entries))  # rows below the screen: blank
    if len(tile_data) > 0x300:
        raise ValueError(f'{len(tile_data)} tiles; the game has room for 768')
    ncg = lz10_compress(b'NCG\0' + struct.pack('<I', len(tile_data)) + b''.join(tile_data))
    nsc = original_nsc[:12] + struct.pack(f'<{count}H', *entries)
    return ncg, ncl, nsc


class Titles:
    """Mission titles of a ROM, for the Studio and the build."""

    def __init__(self, rom):
        self.rom = rom
        self.names = slots(rom)

    def original(self, name):
        p = paths(name)
        return self.rom.read(p['ncg']), self.rom.read(p['ncl']), self.rom.read(p['nsc'])

    def original_png(self, name):
        return png(*render(*self.original(name)))

    def convert(self, name, png_bytes):
        w, h, px = read_png(png_bytes)
        _, ncl, nsc = self.original(name)
        return encode(w, h, px, ncl, nsc)
