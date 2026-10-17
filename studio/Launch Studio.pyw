"""Double-click to start the FM2089 Translation Studio; --no-open checks without opening a browser."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
PORT = 8796
URL = f'http://127.0.0.1:{PORT}'


def existing():
    try:
        with urlopen(URL+'/api/config', timeout=2) as response:
            value = json.load(response)
    except (URLError, OSError):
        return False
    if value.get('application') != 'fm2089-translation-studio':
        raise RuntimeError(f'Port {PORT} is used by a different application.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    if not existing():
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        python = sys.executable
        if python.lower().endswith('pythonw.exe'):
            python = python[:-len('pythonw.exe')]+'python.exe'
        subprocess.Popen([python, '-u', '-X', 'utf8', str(ROOT/'tools'/'studio_server.py'), '--port', str(PORT)],
                         cwd=ROOT, creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            if existing():
                break
            time.sleep(.25)
        else:
            raise RuntimeError('The Studio did not start. Run tools/studio_server.py in a terminal to see the error.')
    if args.no_open:
        print(URL)
    else:
        webbrowser.open(URL)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if sys.stdout is not None:
            raise
        from tkinter.messagebox import showerror
        showerror('FM2089 Translation Studio', str(error))
