"""Assembles the game code behind the Config menu options (tools/optcode.py).

Needs keystone-engine (pip install keystone-engine); the Studio itself only uses
the bytes this writes, so it runs without it. See tools/options.py for what the
code does and where it goes.

    python studio/dev/make_optcode.py
"""
import re
import struct
import sys
from pathlib import Path

import keystone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import options  # noqa: E402

# Game functions (overlay 3 unless noted)
GET_SETTINGS = 0x207dd28   # returns the u16 option bits
SET_SETTINGS = 0x207dd48
SHOW_HELP = 0x20bbd10      # shows message id r0 in the help box
REFRESH = 0x2068a84        # menu, 0: redraws the menu
LABEL = 0x2064608          # out, message id: menu label text
LABEL_FREE = 0x207dcc8
ZERO = 0x20c77b0
ZERO_FREE = 0x20c7c58
NEW_ITEM = 0x205f968       # out, menu, label, zero, [sp]=0: adds an item to the menu
SHARED_ASSIGN = 0x20b9180
SHARED_FREE = 0x20751d0
HELP_FUNCTOR = 0x20c73d4
SET_HELP = 0x2067e98
HELP_FREE = 0x20c7c18
BIND = 0x20c72e4
CALLBACK = 0x20c7324
SET_CALLBACK = 0x2068f10
PMF_TAG = 0x2124d24        # two bytes every Config item passes along with its callback


def item(n, label, help_fn, pmf):
    """One Config item, built the way the game builds its own four (0x20c6ffc-0x20c7128).
    r4 = the menu owner, r5 = the caller's frame (its item pointer at +0x38, +0x3c)."""
    return f'''
    add r0, sp, #0x10
    ldr r1, {label}
    bl #{LABEL:#x}
    add r0, sp, #0x20
    bl #{ZERO:#x}
    mov r0, #0
    str r0, [sp]
    ldr r1, [r4]
    add r0, sp, #0x08
    add r2, sp, #0x10
    add r3, sp, #0x20
    bl #{NEW_ITEM:#x}
    ldr r1, [sp, #0x08]
    str r1, [r5, #0x38]
    add r0, r5, #0x3c
    add r1, sp, #0x0c
    bl #{SHARED_ASSIGN:#x}
    add r0, sp, #0x0c
    bl #{SHARED_FREE:#x}
    add r0, sp, #0x20
    bl #{ZERO_FREE:#x}
    add r0, sp, #0x10
    bl #{LABEL_FREE:#x}
    ldr r1, {help_fn}_p
    add r0, sp, #0x30
    mov r2, #0
    bl #{HELP_FUNCTOR:#x}
    ldr r0, [r5, #0x38]
    add r1, sp, #0x30
    bl #{SET_HELP:#x}
    add r0, sp, #0x30
    bl #{HELP_FREE:#x}
    ldr r1, pmf_tag
    ldr r2, {pmf}_p
    ldrb ip, [r1]
    add r0, sp, #0x40
    mov r3, r4
    strb ip, [sp]
    ldrb r1, [r1, #1]
    strb r1, [sp, #4]
    ldm r2, {{r1, r2}}
    bl #{BIND:#x}
    mov r0, #0
    str r0, [sp]
    add r1, sp, #0x40
    add r0, sp, #0x50
    ldm r1, {{r1, r2, r3}}
    bl #{CALLBACK:#x}
    ldr r0, [r5, #0x38]
    add r1, sp, #0x50
    add r0, r0, #0x38
    bl #{SET_CALLBACK:#x}
    add r0, sp, #0x50
    bl #{ZERO_FREE:#x}
'''


CAVE = f'''
copy_base:  .word 0
font_count: .word 1
show_stat:  .word 0
font_tables: .word 0x10c, 0x10c, 0x10c
settings:   .word {options.SETTINGS:#x}
pmf_tag:    .word {PMF_TAG:#x}
id_stat:    .word {options.msg_id('stat_label'):#x}
id_icons:   .word {options.msg_id('stat_icons'):#x}
id_text:    .word {options.msg_id('stat_text'):#x}
id_font:    .word {options.msg_id('font_label'):#x}
id_font0:   .word {options.msg_id('font_0'):#x}
pmf_stat:   .word toggle_stat, 0
pmf_font:   .word toggle_font, 0
font_tables_p: .word font_tables - 4
help_stat_p: .word help_stat
help_font_p: .word help_font
pmf_stat_p: .word pmf_stat
pmf_font_p: .word pmf_font

@ r0 = font data, r1 = glyph -> r0 = glyph record or 0. Uses r1-r3, ip.
glyph_record:
    ldr r2, settings
    ldrh r2, [r2]
    tst r2, #{options.TEXT_BIT:#x}
    beq gr_lookup
    ldr r3, copy_base
    sub r3, r1, r3
    cmp r3, #{options.ICON_COUNT - 1}
    addls r1, r1, #{options.ICON_COUNT}
gr_lookup:
    ldrh r3, [r0, #0xa]
    cmp r1, r3
    movhs r0, #0
    bxhs lr
    ands r2, r2, #{options.FONT_BITS:#x}
    moveq r3, #0x10c
    ldrne ip, font_tables_p
    ldrne r3, [ip, r2, lsr #{options.FONT_SHIFT - 2}]
    add r3, r3, r1, lsl #2
    ldr r3, [r0, r3]
    add r0, r0, r3
    bx lr

help_stat:
    push {{r3, lr}}
    bl #{GET_SETTINGS:#x}
    tst r0, #{options.TEXT_BIT:#x}
    ldrne r0, id_text
    ldreq r0, id_icons
    bl #{SHOW_HELP:#x}
    pop {{r3, pc}}

toggle_stat:
    push {{r4, lr}}
    mov r4, r0
    bl #{GET_SETTINGS:#x}
    eor r0, r0, #{options.TEXT_BIT:#x}
    bl #{SET_SETTINGS:#x}
    mov r0, #0
    mov r1, r0
    bl help_stat
    ldr r0, [r4]
    mov r1, #0
    bl #{REFRESH:#x}
    pop {{r4, pc}}

help_font:
    push {{r3, lr}}
    bl #{GET_SETTINGS:#x}
    and r0, r0, #{options.FONT_BITS:#x}
    ldr r1, id_font0
    add r0, r1, r0, lsr #{options.FONT_SHIFT}
    bl #{SHOW_HELP:#x}
    pop {{r3, pc}}

toggle_font:
    push {{r4, lr}}
    mov r4, r0
    bl #{GET_SETTINGS:#x}
    and r1, r0, #{options.FONT_BITS:#x}
    bic r0, r0, #{options.FONT_BITS:#x}
    add r1, r1, #{1 << options.FONT_SHIFT:#x}
    ldr r2, font_count
    cmp r1, r2, lsl #{options.FONT_SHIFT}
    movhs r1, #0
    orr r0, r0, r1
    bl #{SET_SETTINGS:#x}
    mov r0, #0
    mov r1, r0
    bl help_font
    ldr r0, [r4]
    mov r1, #0
    bl #{REFRESH:#x}
    pop {{r4, pc}}

@ called in place of the Config menu's "ldr r0, [r4]" right before it is finished
add_items:
    push {{r4, r5, lr}}
    sub sp, sp, #0x64
    add r5, sp, #0x70
    ldr r0, show_stat
    cmp r0, #0
    beq no_stat
{item(1, 'id_stat', 'help_stat', 'pmf_stat')}
no_stat:
    ldr r0, font_count
    cmp r0, #1
    bls no_font
{item(2, 'id_font', 'help_font', 'pmf_font')}
no_font:
    ldr r0, [r4]
    add sp, sp, #0x64
    pop {{r4, r5, pc}}
'''

# overlay 0: the font's width and draw functions look glyphs up through glyph_record
WIDTH = '''
    push {{lr}}
    ldr r0, [r0, #4]
    cmp r0, #0
    popeq {{pc}}
    bl #{glyph_record:#x}
    cmp r0, #0
    ldrbne r0, [r0]
    pop {{pc}}
'''
DRAW = '''
    push {{r0, r1, r2, r3}}
    ldr r0, [r0, #4]
    mov r1, r3
    cmp r0, #0
    blne #{glyph_record:#x}
    mov r4, r0
    pop {{r0, r1, r2, r3}}
    ldr lr, [r0, #4]
    b #0x2046910
'''
MENU = 'bl #{add_items:#x}'


def asm(src, addr):
    ks = keystone.Ks(keystone.KS_ARCH_ARM, keystone.KS_MODE_ARM)
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def symbols(src, addr):
    """Address of each label: assemble once more with a table of all of them at the end."""
    names = [l.strip().split(':')[0] for l in src.splitlines()
             if re.match(r'\s*[a-z_][a-z0-9_]*:', l)]
    code = asm(src, addr)
    tail = asm(src + '\n' + '\n'.join(f'.word {n}' for n in names), addr)[len(code):]
    return dict(zip(names, struct.unpack(f'<{len(names)}I', tail)))


def main():
    cave = asm(CAVE, options.CAVE)
    syms = symbols(CAVE, options.CAVE)
    assert options.CAVE + len(cave) <= options.CAVE_END, f'cave too big: {len(cave)} bytes'
    width = asm(WIDTH.format(**syms), options.WIDTH_FN)
    draw = asm(DRAW.format(**syms), options.DRAW_AT)
    menu = asm(MENU.format(**syms), options.MENU_AT)
    assert len(width) <= options.WIDTH_LEN and len(draw) <= options.DRAW_LEN
    data = {name: syms[name] - options.CAVE for name in ('copy_base', 'font_count', 'show_stat', 'font_tables')}
    out = Path(__file__).resolve().parents[1]/'tools'/'optcode.py'
    out.write_text(
        '"""Machine code for tools/options.py, made by dev/make_optcode.py; do not edit."""\n'
        f'CAVE = bytes.fromhex(\n    {_wrap(cave.hex())})\n'
        f'WIDTH = bytes.fromhex({width.hex()!r})\n'
        f'DRAW = bytes.fromhex({draw.hex()!r})\n'
        f'MENU = bytes.fromhex({menu.hex()!r})\n'
        f'DATA = {data!r}  # offsets in CAVE of the words the build fills in\n', encoding='utf-8')
    print(f'{out}: cave {len(cave)} of {options.CAVE_END - options.CAVE} bytes', {k: hex(v) for k, v in syms.items()})


def _wrap(h, n=96):
    return '\n    '.join(repr(h[i:i+n]) for i in range(0, len(h), n))


if __name__ == '__main__':
    main()
