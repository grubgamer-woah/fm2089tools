"""The closing credits (staff roll) and the translation team's section in them.

data/Ending/ClosingCredits.txt.pk is an LZ10-packed Shift-JIS text script, already in English:
one credits line per <br>, <color 1> makes a line orange (headings), <img top|bottom ...> swaps
the pictures, <totaltime ms> is how long the whole roll takes, and a long <comment ...> at the top
lists the tags. Lines are drawn with data/Ending/SR_00, an 8x16 font of printable ASCII
(space to ~ plus a '...' glyph), so a line holds 32 characters across the 256 px screen.

The Studio keeps the team's section in project.json "credits" and adds it to the script at build
time; "script" there, when set, replaces the game's whole script (the Credits window's advanced editor).
"""
import re
import struct
import unicodedata

import portraits
import titles

PATH = 'data/Ending/ClosingCredits.txt.pk'
FONT = 'data/Ending/SR_00'
WIDTH = 32  # characters per line: 8 px glyphs on the 256 px screen
CELL_W, CELL_H = 8, 16
POSITIONS = {'start': 'After the game title, before the Square Enix staff',
             'end': 'At the end, just before the copyright'}
DEFAULT = {
    'position': 'end',
    'title': 'English Translation',
    'group': '',
    'capitals': True,  # the game's own credits write names in capitals
    'roles': [{'role': r, 'names': ''} for r in
              ('Project Lead', 'Translation', 'Editing', 'Graphics', 'Hacking & Tools', 'Testing', 'Special Thanks')],
    'script': None,
}
TOTAL = re.compile(r'<totaltime\s+(\d+)>')
COMMENT = re.compile(r'<comment\b[^>]*>', re.S)


def original(rom):
    """The game's own credits script as text."""
    return portraits.lz10(rom.read(PATH)).decode('cp932')


def settings(project):
    """The project's credits settings with every key filled in."""
    cfg = {**DEFAULT, **(project.credits or {})}
    cfg['roles'] = [{'role': str(r.get('role', '')), 'names': str(r.get('names', ''))} for r in cfg['roles'] or []]
    return cfg


def plain(text):
    """Accented letters become plain ones (é -> e); other characters the credits font lacks stay as they are."""
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    text = text.replace('–', '-').replace('—', '-').replace('…', '...')
    return ''.join(c if ord(c) < 128 else unicodedata.normalize('NFKD', c).encode('ascii', 'ignore').decode() or c
                   for c in text)


def escape(text):
    return text.replace('<', '\0lt\1').replace('>', '\0gt\1').replace('\0', '<').replace('\1', '>')


def team_lines(cfg):
    """The team's section as (text, heading) pairs; empty roles are left out."""
    lines = []
    if cfg['title'].strip():
        lines.append((cfg['title'].strip(), True))
    if cfg['group'].strip():
        lines.append((cfg['group'].strip(), False))
    roles = [(r['role'].strip(), [n.strip() for n in r['names'].splitlines() if n.strip()]) for r in cfg['roles']]
    roles = [(role, names) for role, names in roles if names]
    if not roles:
        return []
    for role, names in roles:
        lines.append(('', False))
        if role:
            lines.append((role, True))
        lines += [(n.upper() if cfg['capitals'] else n, False) for n in names]
    return [(plain(text), heading) for text, heading in lines]


def team_script(cfg):
    out = []
    for text, heading in team_lines(cfg):
        out.append(('<color 1>' if heading and text else '') + escape(text) + '<br>')
    return '\r\n'.join(out)


def _insert_at(script, cfg):
    """Where the team's section goes: before the Square Enix staff, or before the copyright."""
    if cfg['position'] == 'start':
        m = re.search(r'^<color 1>Executive Producer', script, re.M)
        if m:
            return m.start()
        m = re.search(r'^(?!<comment|<totaltime|<bgm|<img|<br>|\s*$).*<br>.*$', script, re.M)  # the first line with text
        return m.end() + 2 if m else 0
    for rx in (r'^Copyright<br>', r'^<bgm stop>', r'^<end>'):
        m = re.search(rx, script, re.M)
        if m:
            return m.start()
    return len(script)


def lines(script):
    """Every line of the roll as (text, color) in order: what each <br> ends."""
    out, cur, color = [], '', 0
    for part in re.split(r'(<[^<>]*>)', COMMENT.sub('', script)):
        if not part.startswith('<'):
            cur += part.replace('\r', '').replace('\n', '')
            continue
        tag = part[1:-1].split()
        name = tag[0].lower() if tag else ''
        if name == 'br':
            out.append((cur.strip(), color))
            cur, color = '', 0
        elif name == 'color' and len(tag) > 1 and tag[1].isdigit():
            color = int(tag[1])
        elif name in ('lt', 'gt'):
            cur += '<' if name == 'lt' else '>'
    return out


def compose(rom, cfg):
    """Return (script text, problems) for the project's credits, or (None, problems) when the game's stay."""
    base = original(rom)
    script = cfg['script'] if cfg.get('script') else base
    team = team_script(cfg)
    if team:
        at = _insert_at(script, cfg)
        spacer = '<br>\r\n<br>\r\n'
        script = script[:at] + team + '\r\n' + spacer + script[at:]
    if script == base:
        return None, []
    problems = []
    for i, (text, _) in enumerate(lines(script), 1):
        bad = sorted({c for c in text if not 32 <= ord(c) < 127})
        if bad:
            problems.append(('error', f'Credits line {i} "{text}": the credits font has no {" ".join(bad)}'))
        if len(text) > WIDTH:
            problems.append(('error', f'Credits line {i} "{text}" is {len(text)} characters; '
                             f'{WIDTH} fit across the screen'))
    try:
        script.encode('cp932')
    except UnicodeEncodeError as error:
        problems.append(('error', f'Credits script: {error}'))
    # keep the scrolling speed: the roll's total time grows with its number of lines,
    # unless the full script was given a total time of its own
    before, after = len(lines(base)), len(lines(script))
    m = TOTAL.search(script)
    if m and after != before and m.group(1) == TOTAL.search(base).group(1):
        script = script[:m.start(1)] + str(int(m.group(1)) * after // before) + script[m.end(1):]
    return script, problems


def build(rom, cfg):
    """({rom path: packed file}, problems) for the build."""
    script, problems = compose(rom, cfg)
    if script is None or any(level == 'error' for level, _ in problems):
        return {}, problems
    return {PATH: titles.lz10_compress(script.encode('cp932'))}, problems


class Font:
    """The staff roll's 8x16 font (printable ASCII from space), two palettes: 0 white, 1 orange."""

    def __init__(self, rom):
        ncg = portraits.lz10(rom.read(FONT + '_ncg.bin'))
        self.tiles = ncg[8:]
        ncl = rom.read(FONT + '_ncl.bin')
        ncl = portraits.lz10(ncl) if ncl[:1] == b'\x10' else ncl
        cols = struct.unpack_from('<32H', ncl, 8)
        self.palettes = [[titles.rgb555(c) for c in cols[:16]], [titles.rgb555(c) for c in cols[16:32]]]

    def pixel(self, ch, x, y):
        """Color index of glyph ch at (x, y); 16 glyphs per row of 8x16 cells, as the tiles are laid out."""
        g = ord(ch) - 32
        if not 0 <= g < 96:
            return 0
        tile = (g // 16 * 2 + y // 8) * 16 + g % 16
        b = self.tiles[tile*32 + (y % 8)*4 + x // 2]
        return b >> 4 if x & 1 else b & 15


def render(rom, roll, first=0, count=None):
    """PNG of the roll's lines, centered on a 256 px black screen as the game draws them."""
    font = Font(rom)
    roll = roll[first:first+count] if count else roll[first:]
    w, h = WIDTH*CELL_W, max(1, len(roll))*CELL_H
    px = bytearray(w*h*4)
    for i in range(0, len(px), 4):
        px[i+3] = 255
    for row, (text, color) in enumerate(roll):
        pal = font.palettes[1 if color else 0]
        x0 = (w - len(text)*CELL_W) // 2
        for k, ch in enumerate(text):
            for y in range(CELL_H):
                for x in range(CELL_W):
                    v = font.pixel(ch, x, y)
                    X = x0 + k*CELL_W + x
                    if v and 0 <= X < w:
                        o = ((row*CELL_H + y)*w + X)*4
                        px[o:o+3] = bytes(pal[v])
    return portraits.png(w, h, bytes(px))
