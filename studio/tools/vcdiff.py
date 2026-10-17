"""Minimal VCDIFF (RFC 3284) writer and reader, compatible with xdelta3.

The patched ROM keeps every unchanged byte at the same address as the clean
ROM, so each window copies from the same region of the source and adds only the
bytes that differ. No secondary compression is used; xdelta3, Delta Patcher and
Rom Patcher JS all apply these files.
"""

WINDOW = 1 << 20
BLOCK = 4096
MIN_COPY = 16  # shorter equal runs are cheaper to store as data

ADD0 = 1    # default code table: ADD, size follows
COPY0 = 19  # default code table: COPY mode 0 (VCD_SELF), size follows
VCD_SOURCE = 0x01


def varint(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def read_varint(b, p):
    n = 0
    while True:
        c = b[p]; p += 1
        n = (n << 7) | (c & 0x7F)
        if not c & 0x80:
            return n, p


def _runs(src, tgt):
    """Yield (equal, start, end) runs over tgt, comparing against src at the same offsets."""
    n = len(tgt)
    pos = 0
    while pos < n:
        # skip identical blocks quickly
        start = pos
        while pos < n and tgt[pos:pos+BLOCK] == src[pos:pos+BLOCK]:
            pos = min(pos+BLOCK, n)
        if pos > start:
            yield True, start, pos
            continue
        end = min(pos+BLOCK, n)
        p = pos
        while p < end:
            q = p
            eq = p < len(src) and tgt[p] == src[p]
            while q < end and (q < len(src) and tgt[q] == src[q]) == eq:
                q += 1
            yield eq, p, q
            p = q
        pos = end


def encode(source, target):
    out = bytearray(b'\xD6\xC3\xC4\x00\x00')
    for wpos in range(0, max(len(target), 1), WINDOW):
        tgt = target[wpos:wpos+WINDOW]
        src = source[wpos:wpos+WINDOW] if wpos < len(source) else b''
        ops = []  # (kind, start, end) merged
        for eq, s, e in _runs(src, tgt):
            kind = 'copy' if eq and e-s >= MIN_COPY else 'add'
            if ops and ops[-1][0] == kind == 'add':
                ops[-1][2] = e
            elif ops and ops[-1][0] == kind == 'copy' and ops[-1][2] == s:
                ops[-1][2] = e
            else:
                ops.append([kind, s, e])
        data, inst, addr = bytearray(), bytearray(), bytearray()
        for kind, s, e in ops:
            if kind == 'add':
                inst += bytes([ADD0]) + varint(e-s)
                data += tgt[s:e]
            else:
                inst += bytes([COPY0]) + varint(e-s)
                addr += varint(s)
        body = varint(len(tgt)) + b'\x00' + varint(len(data)) + varint(len(inst)) + varint(len(addr)) + data + inst + addr
        if src:
            out += bytes([VCD_SOURCE]) + varint(len(src)) + varint(wpos)
        else:
            out += b'\x00'
        out += varint(len(body)) + body
    return bytes(out)


def decode(source, patch):
    """Applies patches written by encode() (default code table, no compression)."""
    if patch[:4] != b'\xD6\xC3\xC4\x00' or patch[4] != 0:
        raise ValueError('not a plain VCDIFF file')
    p = 5
    out = bytearray()
    while p < len(patch):
        ind = patch[p]; p += 1
        seg = b''
        if ind & VCD_SOURCE:
            size, p = read_varint(patch, p)
            pos, p = read_varint(patch, p)
            seg = source[pos:pos+size]
        _, p = read_varint(patch, p)
        tlen, p = read_varint(patch, p)
        p += 1
        dlen, p = read_varint(patch, p)
        ilen, p = read_varint(patch, p)
        alen, p = read_varint(patch, p)
        data = patch[p:p+dlen]; inst = patch[p+dlen:p+dlen+ilen]; addr = patch[p+dlen+ilen:p+dlen+ilen+alen]
        p += dlen+ilen+alen
        win = bytearray()
        di = ii = ai = 0
        while ii < len(inst):
            code = inst[ii]; ii += 1
            size, ii = read_varint(inst, ii)
            if code == ADD0:
                win += data[di:di+size]; di += size
            elif code == COPY0:
                a, ai = read_varint(addr, ai)
                win += seg[a:a+size]
            else:
                raise ValueError(f'unsupported instruction {code}')
        if len(win) != tlen:
            raise ValueError('window size mismatch')
        out += win
    return bytes(out)
