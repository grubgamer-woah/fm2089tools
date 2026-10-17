"""Read files from a .nds ROM and write replacements back without NitroPacker.

Replaced files that still fit their original slot stay in place; bigger ones move
to free space after the last file. Everything else in the ROM is left untouched,
so the xdelta between the clean and patched ROM stays small.
"""
import struct

ALIGN = 0x200
FILL = 0xFF


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def align(n):
    return (n+ALIGN-1)//ALIGN*ALIGN


class Rom:
    def __init__(self, data):
        self.data = data
        self.title = data[0:12].rstrip(b'\0').decode('ascii', 'replace')
        self.code = data[12:16].decode('ascii', 'replace')
        self.fnt_off, _, self.fat_off, fat_size = struct.unpack_from('<IIII', data, 0x40)
        self.fat = [struct.unpack_from('<II', data, self.fat_off+8*i) for i in range(fat_size//8)]
        self.used = struct.unpack_from('<I', data, 0x80)[0]
        self.paths = {}
        self._walk(0xF000, '')
        # ARM9 overlays have no name in the file table; they are read and replaced as "overlay/N"
        ovt, ovt_size = struct.unpack_from('<II', data, 0x50)
        for i in range(ovt_size//32):
            ov_id, = struct.unpack_from('<I', data, ovt+32*i)
            self.paths[f'overlay/{ov_id}'], = struct.unpack_from('<I', data, ovt+32*i+24)

    def _walk(self, dir_id, prefix):
        d = self.data
        sub, file_id, _ = struct.unpack_from('<IHH', d, self.fnt_off+(dir_id & 0xFFF)*8)
        p = self.fnt_off+sub
        while d[p]:
            n = d[p] & 0x7F
            name = d[p+1:p+1+n].decode('shift_jis', 'replace')
            is_dir = d[p] & 0x80
            p += 1+n
            if is_dir:
                self._walk(struct.unpack_from('<H', d, p)[0], prefix+name+'/')
                p += 2
            else:
                self.paths[prefix+name] = file_id
                file_id += 1

    def read(self, path):
        s, e = self.fat[self.paths[path]]
        return self.data[s:e]

    def list(self, folder):
        return sorted(p for p in self.paths if p.startswith(folder))

    def _resize_overlay(self, out, ov_id, size):
        """A bigger (uncompressed) overlay loads more bytes; its zeroed area shrinks to match."""
        ovt, ovt_size = struct.unpack_from('<II', self.data, 0x50)
        for i in range(ovt_size//32):
            o = ovt+32*i
            oid, _, ram, bss = struct.unpack_from('<4I', self.data, o)
            if oid == ov_id and size > ram:
                if struct.unpack_from('<I', self.data, o+28)[0] & 0x01000000:
                    raise ValueError(f'overlay {ov_id} is compressed')
                struct.pack_into('<II', out, o+8, size, max(0, ram+bss-size))

    def rebuild(self, replacements):
        """replacements: {path: bytes}. Returns (new rom bytes, report list)."""
        out = bytearray(self.data)
        # anything that may sit right after a file: other files, code, tables, banner
        header_starts = [struct.unpack_from('<I', self.data, o)[0] for o in (0x20, 0x30, 0x40, 0x48, 0x50, 0x58, 0x68)]
        starts = sorted({s for s, e in self.fat if e > s} | {x for x in header_starts if x})
        end_of_files = max(e for s, e in self.fat)
        # leave room for the download-play signature that follows the used area
        free = align(max(self.used, end_of_files)+0x88)
        report = []
        for path, new in sorted(replacements.items()):
            fid = self.paths[path]
            s, e = self.fat[fid]
            later = [x for x in starts if x > s]
            slot_end = later[0] if later else align(e)
            if s+len(new) <= slot_end:
                out[s:s+len(new)] = new
                if s+len(new) < e:
                    out[s+len(new):e] = bytes([FILL])*(e-s-len(new))
                where = 'in place'
            else:
                s = free
                if s+len(new) > len(out):
                    raise ValueError(f'{path} does not fit in the ROM ({len(new)} bytes)')
                out[s:s+len(new)] = new
                free = align(s+len(new))
                where = f'moved to {s:#x}'
            struct.pack_into('<II', out, self.fat_off+8*fid, s, s+len(new))
            if path.startswith('overlay/'):
                self._resize_overlay(out, int(path[8:]), len(new))
            report.append({'path': path, 'old_size': e-self.fat[fid][0], 'new_size': len(new), 'placement': where})
        new_used = max(self.used, max(struct.unpack_from('<I', out, self.fat_off+8*i+4)[0] for i in range(len(self.fat))))
        struct.pack_into('<I', out, 0x80, new_used)
        struct.pack_into('<H', out, 0x15E, crc16(out[:0x15E]))
        return bytes(out), report
