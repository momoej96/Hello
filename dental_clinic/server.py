# -*- coding: utf-8 -*-
"""خادم HTTP محلي (127.0.0.1 فقط) لبرنامج إدارة عيادة الأسنان."""
import os, re, sys, json, argparse, traceback, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from http.cookies import SimpleCookie

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
from core import ApiError, connect
from clinic import Clinic
import api, reports, admin_api, import_api, xray_api   # تسجيل المسارات
import ipaddress
from netutil import lan_ips, host_allowed
from api import ROUTES, Ctx, Response, can

STATIC_DIR = os.path.join(APP_DIR, 'static')
MAX_JSON = 5 * 1024 * 1024
MAX_UPLOAD = 300 * 1024 * 1024
UPLOAD_PATHS = ('/api/restore', '/api/import/preview')


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class Handler(BaseHTTPRequestHandler):
    server_version = 'DentalClinic'

    def log_message(self, fmt, *args):
        pass

    # ---- إرسال ----
    def _send(self, status, body, ctype, headers=()):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', CSP)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, data, headers=()):
        self._send(status, json.dumps(data, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8', headers)

    def _static(self, rel):
        rel = 'index.html' if rel in ('', '/') else rel.lstrip('/')
        if rel.startswith('static/'):
            rel = rel[len('static/'):]
        full = os.path.realpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(os.path.realpath(STATIC_DIR) + os.sep) or not os.path.isfile(full):
            return self._json(404, {'error': 'غير موجود'})
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
            ctype += '; charset=utf-8'
        with open(full, 'rb') as f:
            self._send(200, f.read(), ctype)

    # ---- المعالجة ----
    def _handle(self, method):
        clinic = self.server.clinic
        lan = getattr(self.server, 'lan', False)
        if not host_allowed(self.headers.get('Host'), lan):
            return self._json(403, {'error': 'مرفوض'})
        if lan:
            try:
                cip = ipaddress.ip_address(self.client_address[0])
                if not (cip.is_private or cip.is_loopback):
                    return self._json(403, {'error': 'مرفوض: الاتصال مسموح من داخل شبكة العيادة فقط'})
            except ValueError:
                return self._json(403, {'error': 'مرفوض'})
        u = urlparse(self.path)
        path = u.path
        if not path.startswith('/api/'):
            if method != 'GET':
                return self._json(405, {'error': 'غير مسموح'})
            return self._static(path)
        if method != 'GET' and self.headers.get('X-Requested-With') != 'clinic':
            return self._json(403, {'error': 'طلب غير مصرّح به'})
        q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        length = int(self.headers.get('Content-Length') or 0)
        is_upload = path in UPLOAD_PATHS or bool(re.fullmatch(r'/api/patients/\d+/xrays', path)) and method == 'POST'
        if length > (MAX_UPLOAD if is_upload else MAX_JSON):
            return self._json(413, {'error': 'حجم الطلب كبير جداً'})
        raw = self.rfile.read(length) if length else b''
        body = {}
        if raw and not is_upload:
            try:
                body = json.loads(raw.decode('utf-8'))
                if not isinstance(body, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {'error': 'بيانات الطلب غير صحيحة'})
        found = None
        for m, rx, perm, public, tx, fn in ROUTES:
            if m == method:
                mt = rx.match(path)
                if mt:
                    found = (perm, public, tx, fn, mt.groups())
                    break
        if not found:
            return self._json(404, {'error': 'مسار غير موجود'})
        perm, public, tx, fn, groups = found
        cookie = SimpleCookie(self.headers.get('Cookie') or '')
        tok = cookie['sid'].value if 'sid' in cookie else None
        db = None
        with clinic.lock:
            try:
                db = connect(clinic.db_path)
                user = clinic.session_user(db, tok)
                if not public and not user:
                    raise ApiError('انتهت الجلسة، سجّل الدخول من جديد', 401, 'auth')
                if perm and not can(user, perm):
                    raise ApiError('ليست لديك صلاحية لهذه العملية', 403, 'forbidden')
                ctx = Ctx(clinic, db, user, q, body, raw)
                ctx.raw_cookie = tok
                use_tx = tx and method != 'GET'
                if use_tx:
                    db.execute('BEGIN IMMEDIATE')
                try:
                    res = fn(ctx, *[int(g) if g.isdigit() else g for g in groups])
                    if use_tx:
                        db.execute('COMMIT')
                except BaseException:
                    if use_tx and db.in_transaction:
                        db.execute('ROLLBACK')
                    raise
                if ctx.db is None:
                    db = None
            except ApiError as e:
                payload = {'error': e.message, 'code': e.code}
                payload.update(e.extra)
                return self._json(e.status, payload)
            except Exception:
                try:
                    with open(os.path.join(clinic.data_dir, 'error.log'), 'a', encoding='utf-8') as f:
                        f.write(traceback.format_exc() + '\n')
                except OSError:
                    pass
                return self._json(500, {'error': 'حدث خطأ داخلي في البرنامج. لم تُحفظ العملية.', 'code': 'internal'})
            finally:
                if db is not None:
                    try:
                        db.close()
                    except Exception:
                        pass
        if isinstance(res, Response):
            if res.body is not None:
                return self._send(res.status, res.body, res.ctype, res.headers)
            return self._json(res.status, res.data, res.headers)
        return self._json(200, res)

    def do_GET(self): self._handle('GET')
    def do_POST(self): self._handle('POST')
    def do_PUT(self): self._handle('PUT')
    def do_DELETE(self): self._handle('DELETE')


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        pass


def make_server(data_dir, port=0, demo=False, lan=False):
    srv = QuietServer(('0.0.0.0' if lan else '127.0.0.1', port), Handler)
    srv.lan = lan
    srv.clinic = Clinic(data_dir, demo=demo)
    srv.clinic.lan = lan
    srv.clinic.port = srv.server_address[1]
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--data-dir', default=os.environ.get('CLINIC_DATA_DIR') or os.path.join(APP_DIR, 'data'))
    ap.add_argument('--lan', action='store_true', help='السماح بالدخول من أجهزة داخل شبكة العيادة')
    ap.add_argument('--demo', action='store_true', help='وضع تجريبي ببيانات وهمية في مجلد منفصل')
    a = ap.parse_args()
    data_dir = a.data_dir
    if a.demo and a.data_dir == (os.environ.get('CLINIC_DATA_DIR') or os.path.join(APP_DIR, 'data')):
        data_dir = os.path.join(APP_DIR, 'demo_data')
    srv = make_server(data_dir, a.port, a.demo, a.lan)
    if a.demo:
        import seed_demo
        seed_demo.seed_if_empty(srv.clinic)
    print('Dental clinic server running at http://127.0.0.1:%d  (data: %s)' % (srv.server_address[1], srv.clinic.data_dir), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
