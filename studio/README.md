# FM2089 Translation Studio

A local editor for translating Front Mission 2089: Border of Madness (DS) and a
one-click patch builder. It reads the text straight from the Japanese ROM, so it
does not need NitroPacker, and it writes an xdelta patch that anyone can apply
to their own copy of the game.

## Start

1. Put the clean Japanese ROM in `studio/rom/` (any file name).
   It must be *Front Mission 2089 - Border of Madness (Japan).nds*,
   MD5 `e965ed696171d327656dac3adf6c6221`.
2. Double-click **`Launch Studio.pyw`** (needs Python 3.8 or newer), or run
   `python -X utf8 studio/tools/studio_server.py`.
3. Your browser opens <http://127.0.0.1:8796>. The server only listens on this computer.
4. **Restart** (top right) stops the Studio's Python program and starts it
   again, then reloads the page; use it after updating the Studio's files.
   Double-clicking `Launch Studio.pyw` while the Studio is running restarts it too
   (unless a build is running).
   You don't need it after `workspace/project.json` is changed outside the Studio
   (by hand, by a script or by Claude): the Studio notices, reloads the file before
   its next save and refreshes the page within a few seconds, so those edits stay.

## What comes with it

* `translation/project.json`: the full English translation, and
  `translation/images/`: the English mission titles. A new workspace starts
  from them, so the first build already makes the finished patch.
* `assets/Group Localization Files/`: the localization group's own English
  graphics (title and base headers, base map rooms, opening captions, RESULTS,
  terrain panel, font icons and ×, the name screen's Delete / Back / Ok keys,
  and in `Background/` the Wanzer setup screen and the hangar and shop
  headers). Used when the group folder itself isn't next to the Studio.
* `assets/fixes/`: a map for the group's "Sell Parts" header
  (`Background/sellsetup_bg_ncg.bin`), whose tiles don't fit the game's own map.
* `assets/En+Ko name screens/`: the name entry screens of the Korean/English
  fan patch (minus its page arrow, which does nothing on its one-page keyboard).
  Used when that patch's ROM isn't next to the Japanese one.

Only the Japanese ROM is needed from you; it is never stored here.

## Editing

* Tabs split the 11,500 strings into the story, parts and items, names, and
  menus/system text. The story tab is in the order the game plays it: each
  mission's base scenes (talks, briefing, cutscenes), then its battle, with a
  heading where each one starts. The **Mission** list jumps to one part.
  Base talks you can do in any order keep the order the game stores them in.
* Pick an entry, type the English and press **Save entry** (Ctrl+Enter).
  Alt+Up / Alt+Down move between entries. Switching entries saves first.
* **Enter** in the English box is a line break in the game.
* Control codes from the Japanese show as tags such as `«E801:00»` (the main
  character's name) or `«E8F6»` (red text). Click a tag to insert it. Hover a tag
  to see what it does. `«g:1A3»` is a glyph with no known character.
* The preview draws the text with the game's own font. The blue line marks the
  widest Japanese line in that file and the red line the 256 px screen edge.
  Lines past the screen edge are errors; lines past the blue line are warnings.
* Untranslated entries keep their Japanese bytes exactly. **Use Japanese** removes
  an English entry again.
* Story and battle lines start with the speaker's name in the Japanese
  (`レイン：`). The Studio shows the speaker on each entry and leaves the name
  out of the text you translate, then adds it back as `Rain:` when it builds.
  Translate each name once, in the editor or under **Speakers**, and it is used
  on every line that speaker says. The **Speaker** filter lists one
  character's lines. A name with no English yet keeps its Japanese.
* Each speaker's line shows their portrait, taken from the game's own face art.
  The main cast is matched automatically. For anyone else, click the portrait
  (or the letter in its place) in the editor or under **Speakers** and pick a
  face. Portraits are only shown in the Studio; they never change the game.
* Notes and the **Done** checkbox are only for you; they never go into the game.
* Edits are saved to `studio/workspace/project.json` (the save before it is kept
  as `project.previous.json`).

## Sharing scripts

**Export script** saves the changes made since your last export (English,
notes, speaker names and portraits) as a readable `.md` file in
`studio/exports/` and opens that folder, so you can send it to others. Each
entry shows its ID, the Japanese, the old English and the new English. The
first export compares against the translation shipped in
`translation/project.json`.

**Import script** loads one of those files (or a `.tsv`, a `.txt` made by
`msgToTxt.py`, or another Studio's `project.json`). **Import multiple** loads
several at once. Either way the Studio first shows what will change:

* A line changed by only one file (or changed the same way by all of them) goes
  in automatically. If the base says `A A A`, one script says `A B A` and
  another says `A A C`, the result is `A B C`.
* A line the files change in different ways, or one you changed too since the
  sender exported, is listed with each version so you can pick which wins
  (yours is kept unless you pick another).

Nothing changes until you press **Apply**, and your `project.json` is copied to
`workspace/backups/` first.

**Export TSV** writes every string (ID, English, Japanese, note) for a
spreadsheet.

The full English translation ships with the Studio in
`translation/project.json` (every string and speaker name). The first time the
Studio starts without a `workspace/project.json`, it starts from that file, so
a fresh download already has the English. To bring a newer copy into a
workspace you already have, **Import script** `translation/project.json`: its English
replaces yours string by string, and your other strings stay as they are.

## Setup buttons

The Wanzer setup screen is the group's own (`Background/setup_bg_*` in their
folder, Kiley's "Right Shoulder / Computer / Color Select" design). It also
ships as a picture, `translation/images/setup_bg.png` (256×144). Every
build uses it for the real screen and for Yuji's tutorial picture of it. To
change it, save your own as `workspace/images/setup_bg.png`, which wins over the
shipped one. With no picture, the group's screen is used as it is, and without
that the buttons are drawn from their entries in **Screen graphics** (WEAPON,
ARM, BODY...).
`python studio/tools/studio_core.py setup-png` writes the screen there as the
Studio draws it now, to start from. Each 8×8 block of the screen has its own
16 colors, so draw with the colors already in that spot; others snap to the
nearest of them.

## Stat icons

The parts info lines use the localization group's stat icons instead of the
words, as their spreadsheet planned (ATK 5x2 ACC 78 becomes ⚙5x2 ⌖78, see
`tools/staticons.py` for which icon goes with which stat). The project text
keeps the words; the build swaps them. Untick **Stat icons** in the header to
build with the words. The icons come with the group's font, so without the
group files the words are kept.

Players can switch the icons back to the words themselves: the patch adds a
**Stat Display** option (Icons / Text) to the game's Config menu, on the title
screen and in battle. Like the game's own options it is kept in each save, and
a new game starts with Icons. Its name and help lines are the `Options_*`
entries under Menus & system.

## Fonts

The patch also adds a **Font** option to the game's Config menu, so players can
pick which font the game's text is drawn in. It only appears once there is a
second font. To make one:

1. Click **Fonts** in the header. It saves the game's own font as
   `workspace/font sheet (Classic).png` and opens `workspace/fonts/`.
2. Copy the sheet into `workspace/fonts/` and rename it; the file name is the
   font's name in the game (for example `Serif.png` shows as "Serif").
3. Draw over the letters. Each cell holds one character, from space to `~`:
   black ink (two greys for soft edges), 12 px high from the cell's second row,
   and the red line under it is the letter's width. Letters at most 16 px wide.
   A cell you clear keeps the game's own letter.
4. Build. Up to 3 extra fonts are used, in file name order.

The build warns when story lines drawn in a new font would run past the text
box. The font applies to all of the game's 12 px text (dialogue, menus, help).

## Mission titles

The mission title screens ("Mission 01 / 実戦訓練1") are pictures, not text. Click
**Mission titles** to see each Japanese screen next to its English one, exactly as
the game will draw it. **Add pictures…** takes several PNGs at once and matches them
by number (`m10.png` or `mtittle_bg_10_nsc.png` goes to title 10); each card also has
Replace and Remove. Pictures are 256×256 or 256×192 (the DS shows the top 256×192);
magenta is see-through, as in the game's own art. Title numbers are the game's file
numbers, not mission numbers (title 06 is "Mission 04", the sniper route), and 48 and
61 are info screens, not titles.

The pictures are stored in `workspace/images/` and listed under `images` in
project.json. The Studio turns each into the game's 16-color tiles once (about a
second) and keeps the result in `workspace/cache/`; every build includes them.

## Credits

The closing credits after the Epilogue are already in English (a text script,
`data/Ending/ClosingCredits.txt.pk`). Click **Credits** to add your team: a
heading ("English Translation"), an optional group name, and roles with one name
per line. Roles without names are left out, and with no names at all the game
keeps its own credits. Pick whether the section rolls right after the game title
or at the end, just before the copyright. The preview is drawn with the game's
own credits font; a line holds 32 characters of plain ASCII (accents become plain
letters, other characters are an error). Names are written in capitals like the
game's own credits unless you untick that.

The build makes the roll's total time longer by the lines it adds, so the
scrolling speed stays the same (the music is not changed). For anything else,
**Edit the game's whole credits script** opens the full script: one line per
`<br>`, `<color 1>` makes a line orange. The team's section is added on top of it.
The settings are saved under `credits` in project.json.

## Building the patch

**Build xdelta** checks every entry, then writes a new folder in `studio/builds/`:

* `FM2089 English.xdelta` — the patch to share. Apply it to the clean Japanese
  ROM with xdelta3, Delta Patcher or Rom Patcher JS.
* `FM2089 English.nds` — the patched ROM, for testing.
* `build-manifest.json`, `project.json`, `README.txt` — what went into the build.

Earlier builds are never overwritten. From a terminal the same build is
`python -X utf8 studio/tools/studio_core.py build`.

Every build also changes the font (`data/font/msgcmn.fnt`): the space becomes
3 px wide instead of 6 px, and the empty `"` glyph gets drawn, so English
spacing looks normal and straight double quotes work.

## How it works

* `tools/ndsrom.py` reads the ROM's file system and writes replacement files
  back. A file that still fits stays where it was; a bigger one moves to the
  free space after the last file. Nothing else in the ROM changes.
* `tools/msgcodec.py` reads and writes `.msg` files: UTF-8 text whose code
  points are glyph numbers, with control codes at U+E800–U+E8FF.
* `tools/fontdata.py` reads the 12 px proportional font and its ASCII table.
* `tools/portraits.py` decodes the character face graphics for the Studio.
* `tools/credits.py` adds the team to the closing credits script and draws the
  preview with the credits font (`data/Ending/SR_00`).
* `tools/groupart.py` uses the localization group's own English graphics when
  the "5. Group Localization Files" folder sits next to the Studio folder: the
  title and base headers and base map rooms they drew, the opening demo
  captions, the RESULTS screen and the terrain panel, plus 12 icons in unused
  font slots, and (from its `Background` folder) the Wanzer setup screen and
  the headers of the hangar and shop screens, which the tutorial pictures
  reuse. HQ and sortie headers get the Studio's English in the group's
  lettering. Without the folder it uses the copy in `assets/`.
* `tools/tutorials.py` redraws the menus in the tutorial screenshots (Yuji's
  hangar lesson, the battle lessons) from the entries that translate the real
  menus, so the pictures always match them. `tools/buttonfont.py` holds the
  serif capitals of the Wanzer setup buttons (made by `dev/make_buttonfont.py`).
* `tools/options.py` adds the Stat Display and Font options to the game's
  Config menu: a little ARM code (assembled by `dev/make_optcode.py` into
  `tools/optcode.py`) in overlay 3, where 154 copies of the font file's name
  were, that the game's glyph width and draw functions (overlay 0) and the
  Config menu call. `tools/fontsheet.py` reads and writes the font sheets.
* `tools/vcdiff.py` writes and checks the xdelta (VCDIFF) patch in pure Python.
* `tools/test_studio.py` checks all of this against the real ROM.

The ROM, builds and your workspace are ignored by git. Never commit the ROM itself.

## Download packages

`python studio/dev/make_release.py --version 1.0` makes the files for a GitHub
release in `studio/dist/` (ignored by git); it never publishes anything:

* `FM2089-Translation-Studio-1.0-windows.zip`: brings its own Python (the Python
  Software Foundation's Windows build, downloaded once and checked by SHA-256),
  started with `Start Studio.cmd`, so nothing needs installing.
* `FM2089-Translation-Studio-1.0.zip`: the same without Python, for macOS and Linux.
* `RELEASE-NOTES-1.0.md`: text for the release page.

Only files tracked by git go in (plus `conversionTables.py` and the LICENSE), so
no ROM, build or workspace can end up in a package. `--translation PATH` ships
another `project.json` (such as the latest `workspace/project.json`) as
`translation/project.json`.
