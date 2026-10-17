"""Character portraits from the ROM, for showing the speaker next to each line.

Faces are NPK archives: LZ10 data holding a u32 offset table, then NCGR (4bpp tiles,
1D mapping), NCER (one cell of OAM pieces) and NCLR (palette), each LZ10 again.
"""
import re
import struct
import zlib

# Same face names the game's own table uses (overlay 3, id -> name).
FOLDERS = ('data/Character/s', 'data/Character/ss', 'data/bustup')

# Japanese speaker name -> face name. Names not here have no portrait until one is picked.
SPEAKER_FACES = {
    '«E801:00»': 'Storm', 'ストーム': 'Storm', 'スト一ム': 'Storm', 'レイン': 'Rain', 'オッドアイ': 'Oddeye',
    'チャンプ': 'Champ', 'グレイ': 'Gray', 'ファルコン': 'Falcon', 'ロイ': 'Roy', 'アイシャ': 'Aisha',
    'ヘパイスト': 'Hepaist', 'レイチェル': 'Rachel', 'ユウジ・キノシタ': 'Yuji', 'エレン': 'Ellen',
    'ライコフ': 'Lycov', 'フェイスレス': 'Faceless', 'トーネード': 'Tornado', 'バギー': 'Baggy',
    'トマス': 'Thomas', 'サーナ': 'Sirna', 'ジョンストン': 'Jonston', 'ヒュン': 'Hyun', 'ブラウン': 'Brown',
    'バッカス': 'Bacchus', 'ギルモア': 'Gilmore', '将校': 'officer',
}

# OAM sizes: [shape][size] -> (width, height)
OBJ_SIZES = [[(8, 8), (16, 16), (32, 32), (64, 64)],
             [(16, 8), (32, 8), (32, 16), (64, 32)],
             [(8, 16), (8, 32), (16, 32), (32, 64)]]


def lz10(d):
    if d[0] != 0x10:
        return d
    n = int.from_bytes(d[1:4], 'little')
    out = bytearray()
    i = 4
    while len(out) < n:
        flags = d[i]; i += 1
        for b in range(8):
            if len(out) >= n:
                break
            if flags & (0x80 >> b):
                x = d[i] << 8 | d[i+1]; i += 2
                disp = (x & 0xFFF) + 1
                for _ in range((x >> 12) + 3):
                    out.append(out[-disp])
            else:
                out.append(d[i]); i += 1
    return bytes(out)


def unpack_npk(data):
    d = lz10(data)
    count = struct.unpack_from('<I', d, 0)[0] // 4
    offs = [o for o in struct.unpack_from(f'<{count}I', d, 0) if o] + [len(d)]
    return {part[:4]: part for part in (lz10(d[a:b]) for a, b in zip(offs, offs[1:]))}


def render(data):
    """Return (width, height, rgba bytes) for the face's first cell."""
    parts = unpack_npk(data)
    tiles = parts[b'RGCN'][0x30:]
    pl = parts[b'RLCN']
    pal_off = 0x18 + struct.unpack_from('<I', pl, 0x24)[0]
    colors = []
    for k in range(16):
        c = struct.unpack_from('<H', pl, pal_off + 2*k)[0]
        colors.append(((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31, (c >> 10 & 31) * 255 // 31))
    ce = parts[b'RECN']
    ncell, attr, off, mapping = struct.unpack_from('<HHII', ce, 0x18)
    cell = 0x18 + off
    noam, _, ooff = struct.unpack_from('<HHI', ce, cell)
    oams = cell + ncell * (16 if attr == 1 else 8) + ooff
    shift = mapping if mapping < 4 else 0  # tile numbers count in units of 32 << shift bytes
    pieces = []
    for j in range(noam):
        a0, a1, a2 = struct.unpack_from('<HHH', ce, oams + 6*j)
        y = (a0 & 0xFF) - (256 if a0 & 0x80 else 0)
        x = (a1 & 0x1FF) - (512 if a1 & 0x100 else 0)
        w, h = OBJ_SIZES[a0 >> 14][a1 >> 14]
        pieces.append((x, y, w, h, (a2 & 0x3FF) << shift))
    x0 = min(p[0] for p in pieces); y0 = min(p[1] for p in pieces)
    width = max(p[0] + p[2] for p in pieces) - x0
    height = max(p[1] + p[3] for p in pieces) - y0
    px = bytearray(width * height * 4)
    for x, y, w, h, tile in pieces:
        for t in range((w // 8) * (h // 8)):
            tx, ty = (t % (w // 8)) * 8, (t // (w // 8)) * 8
            base = (tile + t) * 32
            for k in range(64):
                b = tiles[base + k // 2] if base + k // 2 < len(tiles) else 0
                v = b & 15 if k % 2 == 0 else b >> 4
                if not v:
                    continue
                o = ((y - y0 + ty + k // 8) * width + (x - x0 + tx + k % 8)) * 4
                px[o:o+4] = bytes((*colors[v], 255))
    return width, height, bytes(px)


def crop_head(width, height, rgba, size=44):
    """Cut a square around the head of a bust-up picture."""
    opaque = lambda x, y: rgba[(y*width + x)*4 + 3]
    top = next(y for y in range(height) if any(opaque(x, y) for x in range(width)))
    cols = [x for y in range(top, min(top + 12, height)) for x in range(width) if opaque(x, y)]
    cx = (min(cols) + max(cols)) // 2
    x0 = max(0, min(width - size, cx - size // 2))
    y0 = max(0, min(height - size, top))
    out = b''.join(rgba[((y0 + y)*width + x0)*4:((y0 + y)*width + x0 + size)*4] for y in range(size))
    return size, size, out


def png(width, height, rgba):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    rows = b''.join(b'\0' + rgba[y*width*4:(y+1)*width*4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


class Portraits:
    def __init__(self, rom):
        self.rom = rom
        self.cache = {}
        self.paths = {}  # face name -> the NPK used for it, small face art first
        for p in sorted(rom.paths, key=lambda p: (FOLDERS.index(p.rsplit('/', 1)[0]) if p.rsplit('/', 1)[0] in FOLDERS else 9, p)):
            folder, file = p.rsplit('/', 1)
            m = re.fullmatch(r'(.+?)(_s|_ss|_l_\d+)\.NPK', file)
            if folder in FOLDERS and m and m.group(1) != 'DUMMY':
                self.paths.setdefault(m.group(1), p)
        self.faces = sorted(self.paths, key=lambda n: (n.startswith(('Npcface', 'Vface')), len(n), n))

    def image(self, face):
        """PNG bytes of the small face for `face`, or None."""
        if face not in self.cache:
            data = None
            path = self.paths.get(face)
            if path:
                w, h, px = render(self.rom.read(path))
                if '/bustup/' in path:
                    w, h, px = crop_head(w, h, px)
                data = png(w, h, px)
            self.cache[face] = data
        return self.cache[face]
