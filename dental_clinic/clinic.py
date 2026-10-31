# -*- coding: utf-8 -*-
"""حالة التطبيق: مسارات البيانات، الجلسات، النسخ الاحتياطي والاستعادة."""
import os, sqlite3, threading, time, secrets
from datetime import datetime
from core import ApiError, init_db, connect, get_settings, SCHEMA_VERSION

REQUIRED_TABLES = {'patients', 'visits', 'procedures', 'payments', 'adjustments', 'expenses',
                   'appointments', 'users', 'settings', 'audit_log', 'meta'}


class Clinic:
    def __init__(self, data_dir, demo=False):
        self.data_dir = os.path.abspath(data_dir)
        self.demo = demo
        os.makedirs(self.data_dir, exist_ok=True)
        self.db_path = os.path.join(self.data_dir, 'clinic.db')
        self.backup_dir = os.path.join(self.data_dir, 'backups')
        os.makedirs(self.backup_dir, exist_ok=True)
        self.lock = threading.RLock()
        self.sessions = {}
        self.fails = {}
        self.import_plans = {}
        self.lan = False
        init_db(self.db_path)
        try:
            self.maybe_auto_backup()
        except Exception:
            pass

    # ---- الجلسات ----
    def new_session(self, uid):
        tok = secrets.token_urlsafe(32)
        self.sessions[tok] = {'uid': uid, 'last': time.time()}
        return tok

    def drop_session(self, tok):
        self.sessions.pop(tok, None)

    def session_user(self, db, tok):
        s = self.sessions.get(tok) if tok else None
        if not s:
            return None
        try:
            mins = int(get_settings(db).get('idle_minutes') or 0)
        except ValueError:
            mins = 15
        limit = (mins * 60) if mins > 0 else 12 * 3600
        if time.time() - s['last'] > limit:
            self.sessions.pop(tok, None)
            return None
        r = db.execute('SELECT id,username,full_name,role,active,doctor FROM users WHERE id=?', (s['uid'],)).fetchone()
        if not r or not r['active']:
            self.sessions.pop(tok, None)
            return None
        s['last'] = time.time()
        return dict(r)

    # ---- النسخ الاحتياطي ----
    def make_backup(self, prefix='clinic'):
        base = '%s_%s' % (prefix, datetime.now().strftime('%Y%m%d_%H%M%S'))
        name, i = base + '.db', 1
        while os.path.exists(os.path.join(self.backup_dir, name)):
            i += 1
            name = '%s_%d.db' % (base, i)
        dest = os.path.join(self.backup_dir, name)
        src = sqlite3.connect(self.db_path)
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        chk = sqlite3.connect(dest)
        try:
            res = chk.execute('PRAGMA integrity_check').fetchone()[0]
            n = chk.execute('SELECT COUNT(*) FROM patients').fetchone()[0]
        finally:
            chk.close()
        if res != 'ok':
            os.remove(dest)
            raise ApiError('فشل التحقق من سلامة النسخة الاحتياطية، لم تُحفظ النسخة', 500, 'backup_failed')
        return {'name': name, 'path': dest, 'size': os.path.getsize(dest), 'patients': n}

    def maybe_auto_backup(self):
        autos = sorted(f for f in os.listdir(self.backup_dir) if f.startswith('auto_') and f.endswith('.db'))
        if autos and time.time() - os.path.getmtime(os.path.join(self.backup_dir, autos[-1])) < 20 * 3600:
            return None
        info = self.make_backup('auto')
        autos = sorted(f for f in os.listdir(self.backup_dir) if f.startswith('auto_') and f.endswith('.db'))
        for old in autos[:-30]:
            try:
                os.remove(os.path.join(self.backup_dir, old))
            except OSError:
                pass
        return info

    def list_backups(self):
        out = []
        for f in os.listdir(self.backup_dir):
            if f.endswith('.db'):
                p = os.path.join(self.backup_dir, f)
                out.append({'name': f, 'size': os.path.getsize(p),
                            'modified': datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M:%S')})
        out.sort(key=lambda x: x['modified'], reverse=True)
        return out

    def validate_backup_file(self, path):
        try:
            chk = sqlite3.connect('file:%s?mode=ro' % path.replace('\\', '/'), uri=True)
            try:
                if chk.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ApiError('الملف تالف (فشل فحص السلامة)')
                tables = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not REQUIRED_TABLES.issubset(tables):
                    raise ApiError('الملف ليس نسخة احتياطية صالحة لهذا البرنامج')
                v = chk.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                if not v or int(v[0]) > SCHEMA_VERSION:
                    raise ApiError('النسخة الاحتياطية من إصدار أحدث من هذا البرنامج')
            finally:
                chk.close()
        except sqlite3.DatabaseError:
            raise ApiError('الملف ليس قاعدة بيانات صالحة')

    def restore_from_file(self, path):
        self.validate_backup_file(path)
        safety = self.make_backup('pre_restore')
        src = sqlite3.connect(path)
        dst = sqlite3.connect(self.db_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        init_db(self.db_path)
        self.sessions.clear()
        return safety
