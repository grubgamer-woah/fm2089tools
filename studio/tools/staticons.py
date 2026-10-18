"""Stat icons in the parts info lines, as the localization group planned them.

The group added 12 icons to unused font slots (groupart.ICONS) and their
spreadsheet writes the parts info with them in place of the stat names, for
example "{98 2D}5X2 {98 2E}78 {98 2F}1 {98 30}∞" for "ATK 5x2 ACC 78 RNG 1 AMMO ∞".
The project keeps the English words; when the project's "stat_icons" setting is
on (the default), the build swaps each stat name on the lines below the first of
a parts info entry for its icon. Turn it off in the Studio to keep the words.

The icon for each stat comes from the spreadsheet (hanger sort labels and the
parts_help sheets). SHRT uses the Japanese font's own short-range gun icon.
"""
import re

SETTING = 'stat_icons'
FILE_PREFIX = 'MsgLabels_parts_help_'
ICONS = {
    'DEF': 0x62C, 'ATK': 0x62D, 'ACC': 0x62E, 'RNG': 0x62F, 'AMMO': 0x630, 'LNG': 0x631,
    'MEL': 0x632, 'PWR': 0x633, 'HP': 0x634, 'WT': 0x635, 'MOV': 0x636, 'EVA': 0x637,
    'ITEM': 0x638, 'SHRT': 0x4DB,
}
STAT = re.compile(r'(?<![^\s])(' + '|'.join(sorted(ICONS, key=len, reverse=True)) + r') +(?=[\d∞~?-])')


def applies(sid):
    return sid.startswith(FILE_PREFIX)


def with_icons(text):
    """The text with the stat names after its first line turned into icons."""
    first, sep, rest = text.partition('\n')
    rest = STAT.sub(lambda m: f'«g:{ICONS[m.group(1)]:X}»', rest)
    return first + sep + re.sub(r' {2,}(?=«g:)', ' ', rest)   # icons need less room than the words
