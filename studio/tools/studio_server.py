"""Local web server for the FM2089 Translation Studio (listens on 127.0.0.1 only)."""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
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

    def fresh(self):
        """Reload project.json if something else changed it (Claude, an import, a text editor), so a save
        here never writes back an older copy over that change. Returns True when it reloaded."""
        with self.lock:
            if not self.project.changed_on_disk():
                return False
            self.project = core.Project(self.project.path)
            return True

    def load(self):
        path, info = core.find_rom()
        if path is None:
            self.catalog, self.rom_problem = None, info
        else:
            self.catalog, self.rom_problem = core.Catalog(path), None


STATE = None
SERVER = None
RESTART = False
STARTED = time.time()


def open_folder(path, select=None):
    """Open a folder in the file manager; on Windows select points Explorer at one file in it."""
    if os.name == 'nt' and select:
        subprocess.Popen(f'explorer /select,"{select}"')  # noqa: S602 - local desktop helper
    elif os.name == 'nt':
        os.startfile(path)  # noqa: S606 - local desktop helper
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def restart():
    """Stop serving; main() then starts a fresh copy of this server (same Python, same arguments)."""
    global RESTART
    time.sleep(.3)  # let the reply reach the page
    RESTART = True
    SERVER.shutdown()


def run_build():
    job = STATE.job
    try:
        with STATE.lock:
            project = core.Project(STATE.project.path)
        result = core.build(STATE.catalog, project, log=lambda m: job['log'].append(m))
        job.update(result=result, running=False)
    except Exception as error:  # report to the page instead of dying silently
        job.update(result={'ok': False, 'message': f'{error}', 'trace': traceback.format_exc()}, running=False)


def credits_state(cfg):
    """The Credits window's settings, the script it builds, problems, and where the team's lines are."""
    rom = STATE.catalog.rom
    script, problems = core.credits.compose(rom, cfg)
    base = core.credits.original(rom)
    roll = core.credits.lines(script or base)
    team = [t for t, _ in core.credits.team_lines(cfg)]
    # the first line of the team's section in the roll (to show it with a few lines around it)
    at = next((i for i in range(len(roll)) if [t for t, _ in roll[i:i+len(team)]] == team), None) if team else None
    return {'credits': cfg, 'positions': core.credits.POSITIONS, 'script': cfg['script'] or base,
            'edited_script': bool(cfg['script']), 'lines': len(roll), 'team_at': at, 'team_lines': len(team),
            'width': core.credits.WIDTH, 'changed': script is not None,
            'problems': [{'level': level, 'message': msg} for level, msg in problems]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(body, dict) and ctype.startswith('application/json'):
            # lets the page tell its own saves from changes made elsewhere (see refreshProject in app.js)
            body = {**body, '_stamp': list(STATE.project.stamp or []), '_reloaded': getattr(self, 'reloaded', False)}
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
            self.reloaded = STATE.fresh()
            if path == '/api/stamp':
                return self.send(200, {})
            if path == '/api/config':
                cat = STATE.catalog
                return self.send(200, {
                    'application': APP, 'started': STARTED, 'rom': str(cat.rom_path) if cat else None, 'rom_problem': STATE.rom_problem,
                    'rom_dir': str(core.ROM_DIR), 'groups': [[k, label] for k, label, _ in core.GROUPS],
                    'project': str(STATE.project.path), 'author': STATE.project.settings.get('author', ''), 'screen_width': core.SCREEN_WIDTH,
                    'stat_icons': STATE.project.settings.get(core.staticons.SETTING, True),
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
            if path == '/api/titles':
                if self.need_rom():
                    return
                titles = STATE.catalog.titles
                return self.send(200, {'titles': [{'name': n, 'number': int(n[-2:]), 'english': n in STATE.project.images}
                                                  for n in titles.names]})
            if path == '/api/title.png':
                if self.need_rom():
                    return
                q = parse_qs(url.query)
                name, kind = q.get('name', [''])[0], q.get('kind', ['jp'])[0]
                titles = STATE.catalog.titles
                if name not in titles.names:
                    return self.send(404, {'error': 'no such title'})
                if kind == 'en':
                    if name not in STATE.project.images:
                        return self.send(404, {'error': 'no English image'})
                    image = core.titles.png(*core.titles.render(*core.title_files(STATE.catalog, STATE.project, name)))
                else:
                    image = titles.original_png(name)
                return self.send(200, image, 'image/png')
            if path == '/api/credits':
                if self.need_rom():
                    return
                with STATE.lock:
                    cfg = core.credits.settings(STATE.project)
                return self.send(200, credits_state(cfg))
            if path == '/api/credits.png':
                if self.need_rom():
                    return
                q = parse_qs(url.query)
                with STATE.lock:
                    cfg = core.credits.settings(STATE.project)
                script = core.credits.compose(STATE.catalog.rom, cfg)[0] or core.credits.original(STATE.catalog.rom)
                roll = core.credits.lines(script)
                first, count = int(q.get('first', ['0'])[0]), int(q.get('count', ['0'])[0]) or None
                return self.send(200, core.credits.render(STATE.catalog.rom, roll, first, count), 'image/png')
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
            self.reloaded = STATE.fresh()
            if path == '/api/restart':
                threading.Thread(target=restart, daemon=True).start()
                return self.send(200, {'ok': True, 'started': STARTED})
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
                    STATE.project.set(sid, en=data.get('en'), note=data.get('note'), done=data.get('done'),
                                      mtl=data.get('mtl'), edited=data.get('edited'),
                                      # only kept when it differs from the Studio's own not-in-game list
                                      hidden=None if 'hidden' not in data else
                                      '' if bool(data['hidden']) == bool(cat.by_id[sid][2].get('unused')) else data['hidden'])
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
            if path == '/api/title':
                name = parse_qs(urlparse(self.path).query).get('name', [''])[0]
                if name not in cat.titles.names:
                    return self.send(404, {'error': f'unknown mission title {name}'})
                data = self.body()
                if not data:
                    with STATE.lock:
                        STATE.project.set_image(name, None)
                        STATE.project.save()
                    return self.send(200, {'ok': True})
                try:
                    core.title_files(cat, STATE.project, name, data)  # converts and caches; bad pictures stop here
                except Exception as error:
                    return self.send(200, {'ok': False, 'error': str(error)})
                with STATE.lock:
                    STATE.project.set_image(name, data)
                    STATE.project.save()
                return self.send(200, {'ok': True})
            if path == '/api/credits':
                data = json.loads(self.body())
                with STATE.lock:
                    cfg = core.credits.settings(STATE.project)
                    for key in ('position', 'title', 'group', 'capitals', 'roles', 'script'):
                        if key in data:
                            cfg[key] = data[key]
                    if cfg['position'] not in core.credits.POSITIONS:
                        cfg['position'] = core.credits.DEFAULT['position']
                    if cfg['script'] == core.credits.original(cat.rom):
                        cfg['script'] = None
                    STATE.project.credits = cfg
                    STATE.project.save()
                    cfg = core.credits.settings(STATE.project)
                return self.send(200, {'ok': True, **credits_state(cfg)})
            if path == '/api/validate':
                with STATE.lock:
                    _, problems = core.compose(cat, STATE.project)
                return self.send(200, {'problems': problems})
            if path == '/api/settings':
                data = json.loads(self.body())
                with STATE.lock:
                    if core.staticons.SETTING in data:
                        STATE.project.settings[core.staticons.SETTING] = bool(data[core.staticons.SETTING])
                    STATE.project.save()
                return self.send(200, {'ok': True, 'settings': STATE.project.settings})
            if path == '/api/fonts':
                # the game font as a sheet to draw over, and the folder whose sheets become the extra fonts
                folder = STATE.project.path.parent/core.fontsheet.FOLDER
                folder.mkdir(parents=True, exist_ok=True)
                sheet = STATE.project.path.parent/core.FONT_SHEET
                sheet.write_bytes(core.fontsheet.export(cat.font))
                fonts = []
                for name, file in core.fontsheet.find(STATE.project.path.parent):
                    try:
                        fonts.append({'name': name, 'letters': len(core.fontsheet.load(file.read_bytes()))})
                    except ValueError as error:
                        fonts.append({'name': name, 'error': str(error)})
                if json.loads(self.body() or b'{}').get('open', True):
                    try:
                        open_folder(str(folder))
                    except OSError:
                        pass
                return self.send(200, {'sheet': str(sheet), 'folder': str(folder), 'fonts': fonts,
                                       'max': core.fontsheet.MAX_FONTS})
            if path == '/api/export-script':
                data = json.loads(self.body() or b'{}')
                author = (data.get('author') or '').strip()
                with STATE.lock:
                    if author:
                        STATE.project.settings['author'] = author
                        STATE.project.save()
                    file, count, since = core.export_script(cat, STATE.project, author)
                core.EXPORTS.mkdir(parents=True, exist_ok=True)
                if data.get('open', True):
                    try:
                        open_folder(str(core.EXPORTS), str(file) if file else None)
                    except OSError:
                        pass  # the page still shows where the file is
                return self.send(200, {'file': str(file) if file else None, 'count': count, 'since': since, 'folder': str(core.EXPORTS)})
            if path in ('/api/import/preview', '/api/import/apply'):
                data = json.loads(self.body())
                files = [(f['name'], f['text']) for f in data['files']]
                with STATE.lock:
                    try:
                        plan = core.import_plan(cat, STATE.project, files)
                    except ValueError as error:
                        return self.send(200, {'ok': False, 'error': str(error)})
                    if path.endswith('preview'):
                        return self.send(200, {'ok': True, **plan})
                    backup = core.backup_project(STATE.project)
                    changed = core.scriptio.apply(STATE.project, plan, data.get('choices') or {})
                    STATE.project.save()
                return self.send(200, {'ok': True, 'changed': changed, 'backup': str(backup) if backup else None})
            if path == '/api/build':
                if STATE.job and STATE.job.get('running'):
                    return self.send(409, {'error': 'A build is already running'})
                STATE.job = {'running': True, 'log': [], 'result': None}
                threading.Thread(target=run_build, daemon=True).start()
                return self.send(200, {'started': True})
            if path == '/api/open':
                data = json.loads(self.body())
                target = Path(data['path']).resolve()
                fonts = (STATE.project.path.parent/core.fontsheet.FOLDER).resolve()
                if not {core.BUILDS.resolve(), core.EXPORTS.resolve(), fonts} & {target, *target.parents}:
                    return self.send(403, {'error': 'only build and export folders can be opened'})
                open_folder(str(target))
                return self.send(200, {'ok': True})
            self.send(404, {'error': 'not found'})
        except Exception as error:
            self.send(500, {'error': str(error), 'trace': traceback.format_exc()})


def main():
    global STATE, SERVER
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=8796)
    args = ap.parse_args()
    STATE = State()
    # The old copy may still be letting go of the port after a restart
    for _ in range(40):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
            break
        except OSError:
            time.sleep(.25)
    else:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    SERVER = server
    print(f'FM2089 Translation Studio: http://127.0.0.1:{args.port}')
    if STATE.rom_problem:
        print(STATE.rom_problem)
    server.serve_forever()
    server.server_close()
    if RESTART:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.Popen([sys.executable, '-u', '-X', 'utf8', *sys.argv], creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os._exit(0)  # a build thread that is still running stops here too


if __name__ == '__main__':
    main()
