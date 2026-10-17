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

Its keyboard gives letters the codes 0-51, which the Japanese game saves and
shows in dialogue as kana (the patch fixes that elsewhere). So the keyboard is
remapped to the Japanese game's own letter codes (a-z 162-187, A-Z 192-217);
keys with no Japanese code (digits, symbols) do nothing.
"""
import hashlib
import struct

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
NO_KEY = 218
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


def compose(ko_rom):
    """{rom path: bytes} for the Japanese ROM. ko_rom: ndsrom.Rom of the En+Ko ROM."""
    ov = bytearray(ko_rom.read(OVERLAY))
    if len(ov) != SIZE:
        raise ValueError('overlay 14 of the En+Ko ROM is not the expected size')
    for addr, (old, new) in {**LANGUAGE_READS, **NAME_COPY}.items():
        _word(ov, addr, old, new)
    keys = list(struct.unpack_from(f'<{KEYS[1]}H', ov, KEYS[0]-BASE))
    keys = [jp_code(c) if c < 52 else NO_KEY for c in keys]
    struct.pack_into(f'<{KEYS[1]}H', ov, KEYS[0]-BASE, *keys)
    files = {}
    for en, (jp, src) in FILES.items():
        o = ov.find(en.encode() + b'\0')
        if o < 0:
            raise ValueError(f'{en} not found in overlay 14 of the En+Ko ROM')
        ov[o:o+len(en)] = jp.encode().ljust(len(en), b'\0')
        if src:
            files[jp[1:]] = ko_rom.read(src)
    for kind in ENV_KINDS:
        files[f'data/name/NameEntryEnv.{kind}'] = ko_rom.read(f'data/name/en/env/NameEntryEnv.{kind}')
    for path in SAME_PATH:
        files[path] = ko_rom.read(path)
    files[OVERLAY] = bytes(ov)
    return files


def jp_code(c):
    """The patch's letter code (A-Z 0-25, a-z 26-51) as the Japanese game's code."""
    return 192 + c if c < 26 else 162 + c - 26
