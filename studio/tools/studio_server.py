"""Local web server for the FM2089 Translation Studio (listens on 127.0.0.1 only)."""
import argparse
import json
import os
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import studio_core as core

WEB = core.STUDIO/'web'
APP = 'fm2089-translation-studio'
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
         '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml'}


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.catalog = None
        self.rom_problem = None
        self.project = core.Project()
        self.job = None
        self.load()

    def load(self):
        path, info = core.find_rom()
        if path is None:
            self.catalog, self.rom_problem = None, info
        else:
            self.catalog, self.rom_problem = core.Catalog(path), None


STATE = None


def open_folder(path):
    if os.name == 'nt':
        os.startfile(path)  # noqa: S606 - local desktop helper
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def run_build():
    job = STATE.job
    try:
        with STATE.lock:
            project = core.Project(STATE.project.path)
        result = core.build(STATE.catalog, project, log=lambda m: job['log'].append(m))
        job.update(result=result, running=False)
    except Exception as error:  # report to the page instead of dying silently
        job.update(result={'ok': False, 'message': f'{error}', 'trace': traceback.format_exc()}, running=False)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        for k, v in {'Cache-Control': 'no-store', **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n)

    def need_rom(self):
        if STATE.catalog is None:
            self.send(409, {'error': STATE.rom_problem})
            return True
        return False

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path == '/api/config':
                cat = STATE.catalog
                return self.send(200, {
                    'application': APP, 'rom': str(cat.rom_path) if cat else None, 'rom_problem': STATE.rom_problem,
                    'rom_dir': str(core.ROM_DIR), 'groups': [[k, label] for k, label, _ in core.GROUPS],
                    'project': str(STATE.project.path), 'screen_width': core.SCREEN_WIDTH,
                    'controls': {f'{k:04X}': v for k, v in core.msgcodec.CONTROL_NAMES.items()}})
            if path == '/api/catalog':
                if self.need_rom():
                    return
                with STATE.lock:
                    return self.send(200, {'entries': STATE.catalog.entries, 'project': STATE.project.entries,
                                           'speakers': STATE.project.speakers, 'default_speakers': core.DEFAULT_SPEAKERS,
                                           'faces': STATE.project.faces, 'default_faces': core.portraits.SPEAKER_FACES,
                                           'portraits': STATE.catalog.portraits.faces})
            if path == '/api/portrait':
                if self.need_rom():
                    return
                face = parse_qs(url.query).get('face', [''])[0]
                image = STATE.catalog.portraits.image(face) if face in STATE.catalog.portraits.paths else None
                if image is None:
                    return self.send(404, {'error': 'no such portrait'})
                return self.send(200, image, 'image/png', {'Cache-Control': 'max-age=86400'})
            if path == '/api/font':
                if self.need_rom():
                    return
                return self.send(200, STATE.catalog.font.to_json())
            if path == '/api/job':
                return self.send(200, STATE.job or {})
            if path == '/api/export.tsv':
                if self.need_rom():
                    return
                with STATE.lock:
                    text = core.export_tsv(STATE.catalog, STATE.project)
                return self.send(200, text.encode('utf-8-sig'), 'text/tab-separated-values; charset=utf-8',
                                 {'Content-Disposition': 'attachment; filename="fm2089-translation.tsv"'})
            name = 'index.html' if path == '/' else path.lstrip('/')
            file = (WEB/name).resolve()
            if WEB.resolve() in file.parents and file.is_file():
                return self.send(200, file.read_bytes(), TYPES.get(file.suffix, 'application/octet-stream'))
            self.send(404, {'error': 'not found'})
        except Exception as error:
            self.send(500, {'error': str(error), 'trace': traceback.format_exc()})

    def do_POST(self):
        path = urlparse(self.path).path
        if self.headers.get('Origin') not in (None, f'http://{self.headers.get("Host")}'):
            return self.send(403, {'error': 'cross-site request refused'})
        try:
            if path == '/api/reload':
                STATE.load()
                return self.send(200, {'ok': STATE.catalog is not None, 'rom_problem': STATE.rom_problem})
            if self.need_rom():
                return
            cat = STATE.catalog
            if path == '/api/check':
                data = json.loads(self.body())
                res = cat.check(data['id'], data.get('en', ''), STATE.project.speakers)
                res.pop('tokens')
                return self.send(200, res)
            if path == '/api/entry':
                data = json.loads(self.body())
                sid = data['id']
                if sid not in cat.by_id:
                    return self.send(404, {'error': f'unknown entry {sid}'})
                res = cat.check(sid, data.get('en') or '', STATE.project.speakers) if data.get('en') else {'errors': [], 'warnings': [], 'widths': []}
                res.pop('tokens', None)
                if res['errors'] and not data.get('force'):
                    return self.send(200, {'ok': False, **res})
                with STATE.lock:
                    STATE.project.set(sid, en=data.get('en'), note=data.get('note'), done=data.get('done'))
                    STATE.project.save()
                    saved = STATE.project.entries.get(sid, {})
                return self.send(200, {'ok': True, 'entry': saved, **res})
            if path == '/api/speaker':
                data = json.loads(self.body())
                jp, en = data['jp'], (data.get('en') or '').strip()
                if 'face' in data:
                    face = data['face'] or ''
                    if face and face != '-' and face not in cat.portraits.paths:
                        return self.send(200, {'ok': False, 'errors': [f'unknown portrait {face}']})
                    with STATE.lock:
                        STATE.project.set_face(jp, face)
                        STATE.project.save()
                    return self.send(200, {'ok': True, 'faces': STATE.project.faces})
                if en:
                    _, problems = core.msgcodec.text_to_tokens(en, cat.font)
                    if problems:
                        return self.send(200, {'ok': False, 'errors': problems})
                with STATE.lock:
                    STATE.project.set_speaker(jp, en)
                    STATE.project.save()
                return self.send(200, {'ok': True, 'speakers': STATE.project.speakers})
            if path == '/api/validate':
                with STATE.lock:
                    _, problems = core.compose(cat, STATE.project)
                return self.send(200, {'problems': problems})
            if path == '/api/import':
                text = self.body().decode('utf-8', 'replace')
                with STATE.lock:
                    count, unknown = core.import_tsv(cat, STATE.project, text)
                    STATE.project.save()
                return self.send(200, {'imported': count, 'unknown': unknown[:20], 'unknown_count': len(unknown)})
            if path == '/api/build':
                if STATE.job and STATE.job.get('running'):
                    return self.send(409, {'error': 'A build is already running'})
                STATE.job = {'running': True, 'log': [], 'result': None}
                threading.Thread(target=run_build, daemon=True).start()
                return self.send(200, {'started': True})
            if path == '/api/open':
                data = json.loads(self.body())
                target = Path(data['path']).resolve()
                if core.BUILDS.resolve() not in [target, *target.parents]:
                    return self.send(403, {'error': 'only build folders can be opened'})
                open_folder(str(target))
                return self.send(200, {'ok': True})
            self.send(404, {'error': 'not found'})
        except Exception as error:
            self.send(500, {'error': str(error), 'trace': traceback.format_exc()})


def main():
    global STATE
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=8796)
    args = ap.parse_args()
    STATE = State()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'FM2089 Translation Studio: http://127.0.0.1:{args.port}')
    if STATE.rom_problem:
        print(STATE.rom_problem)
    server.serve_forever()


if __name__ == '__main__':
    main()
