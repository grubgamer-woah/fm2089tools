"""Make the download packages of the Translation Studio (nothing is published).

    python studio/dev/make_release.py [--version 1.0] [--translation PATH] [--skip-windows]

Writes to studio/dist/:
  FM2089-Translation-Studio-<version>-windows.zip  Windows, with its own Python (nothing to install)
  FM2089-Translation-Studio-<version>.zip          any system with Python 3.8 or newer
  RELEASE-NOTES-<version>.md                        text for the GitHub release page

Both hold the Studio files tracked by git, conversionTables.py and the LICENSE. The Windows one adds
the Python Software Foundation's own Windows build (the "python" NuGet package, checked by SHA-256)
in python/ and a "Start Studio.cmd" that runs it. --translation puts another project.json (such as
the latest workspace/project.json) in as translation/project.json. No ROM, build or workspace ever
goes in: only tracked files are copied, and .nds files are refused.
"""
import argparse
import datetime as dt
import hashlib
import io
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen
import zipfile

STUDIO = Path(__file__).resolve().parents[1]
REPO = STUDIO.parent
DIST = STUDIO/'dist'
CACHE = DIST/'cache'
NAME = 'FM2089 Translation Studio'

# python.org's Windows x64 build as a NuGet package (published 2026-09-30)
PYTHON_VERSION = '3.14.8'
PYTHON_URL = f'https://api.nuget.org/v3-flatcontainer/python/{PYTHON_VERSION}/python.{PYTHON_VERSION}.nupkg'
PYTHON_SHA256 = 'ce85f674d9a63029f709cbff7a3da1c6bc5bfcfaefdd9999f98fa0290470c454'
# parts of that Python the Studio never uses
PYTHON_SKIP = ('Lib/test/', 'Lib/idlelib/', 'Lib/ensurepip/', 'Lib/lib2to3/', 'Lib/turtledemo/',
               'Lib/site-packages/', 'include/', 'libs/', 'Scripts/')
# tracked files that are only for working on the Studio itself
STUDIO_SKIP = ('dev/', '.gitignore')

START_CMD = '''@echo off
rem Starts the Translation Studio with the Python in the python folder and opens it in your browser.
cd /d "%~dp0"
start "" "python\\pythonw.exe" -s "Launch Studio.pyw"
'''

READ_FIRST = '''FM2089 Translation Studio {version}
====================================

A translation editor and one-click English patch builder for
Front Mission 2089: Border of Madness (Nintendo DS).

1. Unzip this folder anywhere (not inside Program Files).
2. Put your own clean Japanese ROM in the "rom" folder (any file name):
   Front Mission 2089 - Border of Madness (Japan).nds
   MD5 e965ed696171d327656dac3adf6c6221
   The ROM is not included and never will be.
3. {start}
   Your browser opens http://127.0.0.1:8796 (only this computer can reach it).
4. "Build xdelta" writes the English patch and a patched ROM for testing into
   the "builds" folder.

The full English translation comes with it, so the first build already makes
the finished patch. Your own edits are saved in the "workspace" folder; keep it
when you update to a newer version of the Studio.

README.md explains everything else. Source: https://github.com/grubgamer-woah/fm2089tools
'''

START_WINDOWS = 'Double-click "Start Studio.cmd". Nothing else needs installing.'
START_PYTHON = ('Double-click "Launch Studio.pyw" (needs Python 3.8 or newer from python.org),\n'
                '   or run: python -X utf8 tools/studio_server.py')


def tracked_files():
    """The Studio's files as git tracks them, as (path in the package, file on disk)."""
    out = subprocess.run(['git', 'ls-files', '-z', '--', 'studio'], cwd=REPO, check=True,
                         capture_output=True).stdout.decode('utf-8')
    files = []
    for name in filter(None, out.split('\0')):
        rel = name[len('studio/'):]
        if rel.startswith(STUDIO_SKIP):
            continue
        if rel.lower().endswith('.nds'):
            raise SystemExit(f'refusing to package a ROM: {name}')
        files.append((rel, REPO/name))
    files.append(('conversionTables.py', REPO/'conversionTables.py'))  # fontdata looks next to tools/ too
    files.append(('LICENSE.txt', REPO/'LICENSE'))
    return files


def python_package():
    """The Windows Python NuGet package, downloaded once into dist/cache and checked."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE/f'python.{PYTHON_VERSION}.nupkg'
    if not path.exists():
        print('downloading', PYTHON_URL)
        with urlopen(PYTHON_URL, timeout=120) as response:
            data = response.read()
        path.write_bytes(data)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PYTHON_SHA256:
        path.unlink()
        raise SystemExit(f'{path.name}: SHA-256 is {digest}, expected {PYTHON_SHA256}')
    return zipfile.ZipFile(io.BytesIO(data))


def add(archive, top, rel, data):
    info = zipfile.ZipInfo(f'{top}/{rel}', date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def package(path, top, files, start, python=None):
    with zipfile.ZipFile(path, 'w', compresslevel=9) as archive:
        for rel, source in files:
            add(archive, top, rel, Path(source).read_bytes() if not isinstance(source, bytes) else source)
        for folder in ('workspace', 'builds', 'exports'):
            add(archive, top, f'{folder}/.keep', b'')
        add(archive, top, 'READ ME FIRST.txt', READ_FIRST.format(version=top.rsplit(' ', 1)[-1], start=start)
            .replace('\n', '\r\n').encode('utf-8'))
        if python is not None:
            add(archive, top, 'Start Studio.cmd', START_CMD.replace('\n', '\r\n').encode('ascii'))
            for info in python.infolist():
                name = info.filename
                if not name.startswith('tools/') or name.endswith('/'):
                    continue
                rel = name[len('tools/'):]
                if rel.startswith(PYTHON_SKIP) or '__pycache__' in rel:
                    continue
                add(archive, top, f'python/{rel}', python.read(info))
    return path


NOTES = '''# FM2089 Translation Studio {version}

A translation editor and one-click English patch builder for *Front Mission 2089:
Border of Madness* (Nintendo DS). It comes with the full English translation, the
localization group's English graphics and the English name entry screens.

## Download

* **{windows}**: for Windows. Unzip it, put your ROM in `rom`, double-click
  `Start Studio.cmd`. It brings its own Python {python}, so nothing needs installing.
* **{plain}**: for macOS and Linux (or Windows with Python already installed). Needs
  Python 3.8 or newer; double-click `Launch Studio.pyw` or run
  `python -X utf8 tools/studio_server.py`.

You need your own clean Japanese ROM, *Front Mission 2089 - Border of Madness (Japan).nds*
(MD5 `e965ed696171d327656dac3adf6c6221`). No ROM is included.

## Updating

Unzip the new version next to the old one and move your old `workspace` folder into it.
To pick up a newer shipped translation, use **Import script** on `translation/project.json`.

## What's new

* (fill in)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', default=dt.date.today().isoformat())
    parser.add_argument('--translation', type=Path, help='a project.json to ship instead of translation/project.json')
    parser.add_argument('--skip-windows', action='store_true', help='only the package that needs Python installed')
    args = parser.parse_args()
    files = tracked_files()
    if args.translation:
        files = [(rel, args.translation if rel == 'translation/project.json' else source) for rel, source in files]
    DIST.mkdir(exist_ok=True)
    top = f'{NAME} {args.version}'
    base = f'FM2089-Translation-Studio-{args.version}'
    made = [package(DIST/f'{base}.zip', top, files, START_PYTHON)]
    if not args.skip_windows:
        made.append(package(DIST/f'{base}-windows.zip', top, files, START_WINDOWS, python_package()))
    notes = DIST/f'RELEASE-NOTES-{args.version}.md'
    notes.write_text(NOTES.format(version=args.version, python=PYTHON_VERSION, plain=made[0].name,
                                  windows=f'{base}-windows.zip'), encoding='utf-8')
    for path in made+[notes]:
        print(f'{path.stat().st_size/1e6:7.1f} MB  {path.relative_to(REPO)}')


if __name__ == '__main__':
    sys.exit(main())
