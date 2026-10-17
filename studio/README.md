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

**Export TSV** writes every string (ID, English, Japanese, note) for a
spreadsheet. **Import TSV** reads that file back, or a `.txt` made by
`msgToTxt.py` that already has English in it.

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
* `tools/vcdiff.py` writes and checks the xdelta (VCDIFF) patch in pure Python.
* `tools/test_studio.py` checks all of this against the real ROM.

The ROM, builds and your workspace are ignored by git. Never commit the ROM.
