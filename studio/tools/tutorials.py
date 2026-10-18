"""Japanese menus in the tutorial screenshots, redrawn with the English of the real menus.

Yuji's hangar lesson and the battle lessons show pictures of the game's own
screens (data/bg/image0001-0015, data/bg/tutorial_bg_04/06/07). They are plain
pictures, so the text strings that translate the real menus don't reach them.
Each Japanese piece is painted out and drawn again from the entry that
translates the real thing, so the pictures follow those entries:

  bar      the header in the top-left corner (a Graphics_setup_* entry)
  row      a menu line: the white Japanese is painted out, blending the row's
           background from just above and below it, and the English drawn white
  buttons  the part buttons of the setup screen (all Graphics_button_* entries)
"""
from collections import Counter

import labels

ROW_H = 12          # rows of a menu line's lettering
ROW_RIGHT = 222     # menu lines end before the OK marker
BAR_W = 128


def _rows(x, *ids, top=26, right=ROW_RIGHT):
    """Menu lines 16 px apart, the first one's lettering at row top. None skips a line."""
    return [('row', (x, top+16*n, right), i) for n, i in enumerate(ids) if i]


STOCK = [('bar', None, 'Graphics_setup_stocksetup')]
PICTURES = {
    'image0001': _rows(10, 'MsgLabels_hanger_msg_001', 'MsgLabels_hanger_msg_002', 'MsgLabels_hanger_msg_003'),
    'image0002': [('bar', None, 'Graphics_setup_select'),
                  *_rows(138, 'MsgLabels_name_msg_110', 'MsgLabels_name_msg_111')],
    'image0003': [('buttons', None, None)],
    'image0004': STOCK, 'image0005': STOCK,
    'image0006': [('bar', None, 'Graphics_setup_buysetup')],
    'image0007': [('bar', None, 'Graphics_setup_buysetup')],
    'image0008': [('bar', None, 'Graphics_setup_sellsetup')],
    'image0009': STOCK + _rows(138, *['MsgLabels_hanger_msg_012']*4),
    'image0010': STOCK + _rows(138, None, *['MsgLabels_hanger_msg_012']*3),
    'image0011': STOCK + _rows(138, 'MsgLabels_hanger_msg_011'),
    'image0012': STOCK, 'image0013': STOCK, 'image0014': STOCK, 'image0015': STOCK,
    'tutorial_bg_04': _rows(138, 'MsgLabels_tactics_command_msg_001', 'MsgLabels_tactics_command_msg_005'),
    'tutorial_bg_06': _rows(138, 'MsgLabels_tactics_command_msg_003', 'MsgLabels_tactics_command_msg_009',
                            'MsgLabels_tactics_command_msg_005', 'MsgLabels_tactics_command_msg_007'),
    'tutorial_bg_07': _rows(138, 'MsgLabels_tactics_command_msg_003', 'MsgLabels_tactics_command_msg_009',
                            'MsgLabels_tactics_command_msg_005', 'MsgLabels_tactics_command_msg_007'),
}


def _bright(c):
    return sum(c)


def _bar(pic, font, text):
    """Like labels._bar on a picture: each row's own color over the lettering, then the English."""
    img = pic.img
    ink = None
    for y in range(3, 15):
        base = Counter(img[y][1:BAR_W-1]).most_common(1)[0][0]
        for x in range(1, BAR_W-1):
            if _bright(img[y][x]) > _bright(base) + 90:
                ink = max(ink or img[y][x], img[y][x], key=_bright)   # the Japanese's own color
                pic.set(x, y, base)
    ink = ink or (255, 255, 255)
    for x, y in labels._ink(font, text, 4, 3):
        if 1 <= x < BAR_W-1 and 3 <= y < 15:
            pic.set(x, y, ink)


def _row(pic, font, box, text):
    """Paint the Japanese out with each row's own background (the most common color to its right), then the English."""
    x0, top, right = box
    img = pic.img
    y0, y1 = top-1, top+ROW_H
    lit = [x for x in range(x0-2, right) for y in range(y0, y1) if min(img[y][x]) >= 0xA0]
    end = max(lit) + 2 if lit else x0
    for y in range(y0, y1):
        rest = [c for c in img[y][end:right] if min(c) < 0xA0] or [c for c in img[y][x0-2:end] if min(c) < 0x60]
        base = Counter(rest).most_common(1)[0][0]
        for x in range(x0-2, end):
            pic.set(x, y, base)
    for x, y in labels._ink(font, text, x0, y0):
        if x < right:
            pic.set(x, y, (255, 255, 255))


def compose(rom, font, english):
    """english(entry id) -> the project's English or None. Returns ({rom path: bytes}, problems)."""
    files, problems = {}, []
    buttons = []
    for key, (_, default, kind, sources) in labels.LABELS.items():
        if kind == 'button':
            text = english(labels.entry_id(key)) or default
            buttons += [(src, text if labels.button_word(text) else default) for src in sources]
    for name, parts in PICTURES.items():
        base = f'data/bg/{name}_'
        pic = labels.Picture(rom.read(base+'ncg.bin'), rom.read(base+'nsc.bin'), rom.read(base+'ncl.bin'))
        for kind, box, eid in parts:
            if kind == 'buttons':
                labels.draw_buttons(pic, buttons)
                continue
            text = english(eid)
            if not text or '\n' in text or labels.missing_chars(font, text):
                problems.append({'id': eid, 'level': 'warning',
                                 'message': f'The tutorial picture {name} keeps its Japanese here: '
                                            'this entry has no one-line English yet'})
                continue
            limit = BAR_W-6 if kind == 'bar' else box[2]-box[0]
            if labels.text_width(font, text) > limit:
                problems.append({'id': eid, 'level': 'warning',
                                 'message': f'Cut short in the tutorial picture {name}: wider than {limit} px'})
            if kind == 'bar':
                _bar(pic, font, text)
            else:
                _row(pic, font, box, text)
        files[base+'ncg.bin'], files[base+'nsc.bin'] = pic.save()
    return files, problems
