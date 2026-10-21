"""Double-click to start the FM2089 Translation Studio; --no-open checks without opening a browser."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
PORT = 8796
URL = f'http://127.0.0.1:{PORT}'


def existing():
    """The running Studio's start time, or None when nothing is running."""
    try:
        with urlopen(URL+'/api/config', timeout=2) as response:
            value = json.load(response)
    except (URLError, OSError, ValueError):
        return None
    if value.get('application') != 'fm2089-translation-studio':
        raise RuntimeError(f'Port {PORT} is used by a different application.')
    return value.get('started', 0)


def restart(started):
    """Ask a Studio that is already running to restart, so it runs the current files."""
    try:
        with urlopen(URL+'/api/job', timeout=2) as response:
            if json.load(response).get('running'):
                return  # never stop a build that is still running
        urlopen(Request(URL+'/api/restart', data=b'{}', headers={'Content-Type': 'application/json'}), timeout=5).close()
    except (URLError, OSError):
        return  # an older Studio without the restart command keeps running as it is
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        time.sleep(.25)
        now = existing()
        if now is not None and now != started:
            return
    raise RuntimeError('The Studio did not restart. Close python.exe in Task Manager and try again.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    started = existing()
    if started is not None:
        restart(started)
    else:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        python = sys.executable
        if python.lower().endswith('pythonw.exe'):
            python = python[:-len('pythonw.exe')]+'python.exe'
        subprocess.Popen([python, '-u', '-X', 'utf8', str(ROOT/'tools'/'studio_server.py'), '--port', str(PORT)],
                         cwd=ROOT, creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            if existing() is not None:
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
        if os.name == 'nt':  # the Python that comes with the Windows download has no tkinter
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), 'FM2089 Translation Studio', 0x10)
        else:
            from tkinter.messagebox import showerror
            showerror('FM2089 Translation Studio', str(error))
