# -*- coding: utf-8 -*-
"""المستخدمون، الإعدادات، النسخ الاحتياطي والاستعادة، سجل التدقيق، التصدير."""
import os, json, tempfile
from urllib.parse import quote
from core import *
from api import route, Response, ROLE_PERMS
from xlsx_writer import build_xlsx, build_csv

ROLES = tuple(ROLE_PERMS.keys())


# ---------- المستخدمون ----------
@route('GET', '/api/users', perm='users', tx=False)
def users_list(c):
    return {'users': [dict(r) for r in c.db.execute('SELECT id,username,full_name,role,active,doctor,created_at FROM users ORDER BY id')]}


def user_doctor(b, old=None):
    """الطبيب الافتراضي للمستخدم («» = بدون)"""
    if 'doctor' not in b:
        return old
    return v_text(b, 'doctor', 'الطبيب', maxlen=100) or None


@route('POST', '/api/users', perm='users')
def user_create(c):
    b = c.body
    username = v_text(b, 'username', 'اسم المستخدم', required=True, maxlen=40)
    if len(username) < 3:
        raise ApiError('اسم المستخدم يجب ألا يقل عن 3 أحرف')
    role = v_choice(b, 'role', 'الصلاحية', ROLES)
    check_password_strength(b.get('password'))
    if c.db.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
        raise ApiError('اسم المستخدم مستخدم مسبقاً')
    h, s = hash_pw(b['password'])
    cur = c.db.execute('INSERT INTO users(username,full_name,role,pw_hash,salt,active,created_at,doctor) VALUES(?,?,?,?,?,1,?,?)',
                       (username, v_text(b, 'full_name', 'الاسم', maxlen=100) or username, role, h, s, now_iso(), user_doctor(b)))
    audit(c.db, c.user['username'], 'user', cur.lastrowid, 'create', None, {'username': username, 'role': role})
    return {'id': cur.lastrowid}


@route('PUT', r'/api/users/(\d+)', perm='users')
def user_update(c, uid):
    r = c.db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not r:
        raise ApiError('المستخدم غير موجود', 404)
    b = c.body
    role = v_choice(b, 'role', 'الصلاحية', ROLES, r['role'])
    active = 1 if b.get('active', r['active']) in (1, True, '1') else 0
    if r['role'] == 'admin' and (role != 'admin' or not active):
        others = c.db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id!=?", (uid,)).fetchone()[0]
        if others == 0:
            raise ApiError('لا يمكن تعطيل أو تخفيض صلاحية آخر مدير في النظام')
    c.db.execute('UPDATE users SET role=?, active=?, full_name=?, doctor=? WHERE id=?',
                 (role, active, v_text(b, 'full_name', 'الاسم', maxlen=100) or r['full_name'], user_doctor(b, r['doctor']), uid))
    if b.get('new_password'):
        check_password_strength(b['new_password'])
        h, s = hash_pw(b['new_password'])
        c.db.execute('UPDATE users SET pw_hash=?, salt=? WHERE id=?', (h, s, uid))
    if not active or role != r['role'] or b.get('new_password'):
        for tok in [t for t, v in c.clinic.sessions.items() if v['uid'] == uid]:
            c.clinic.drop_session(tok)
    audit(c.db, c.user['username'], 'user', uid, 'update', {'role': r['role'], 'active': r['active'], 'doctor': r['doctor']},
          {'role': role, 'active': active, 'doctor': user_doctor(b, r['doctor']), 'password_reset': bool(b.get('new_password'))})
    return {'ok': True}


# ---------- الإعدادات ----------
@route('GET', '/api/settings', tx=False)
def settings_get(c):
    return {'settings': get_settings(c.db)}


@route('PUT', '/api/settings', perm='settings')
def settings_put(c):
    b, new = c.body, {}
    new['clinic_name'] = v_text(b, 'clinic_name', 'اسم العيادة', required=True, maxlen=120)
    new['clinic_phone'] = v_text(b, 'clinic_phone', 'هاتف العيادة', maxlen=60)
    new['clinic_address'] = v_text(b, 'clinic_address', 'العنوان', maxlen=200)
    new['currency_code'] = v_text(b, 'currency_code', 'رمز العملة', required=True, maxlen=8)
    new['currency_label'] = v_text(b, 'currency_label', 'اسم العملة', required=True, maxlen=30)
    new['currency_symbol'] = v_text(b, 'currency_symbol', 'رمز العملة المعروض', required=True, maxlen=10)
    new['receipt_footer'] = v_text(b, 'receipt_footer', 'تذييل الإيصال', maxlen=200)
    try:
        m = int(b.get('idle_minutes', 15))
    except (TypeError, ValueError):
        raise ApiError('مدة القفل غير صحيحة')
    if m < 0 or m > 480:
        raise ApiError('مدة القفل يجب أن تكون بين 0 و480 دقيقة')
    new['idle_minutes'] = str(m)
    docs = b.get('doctors', [])
    if isinstance(docs, str):
        docs = [x.strip() for x in docs.split('\n')]
    if not isinstance(docs, list):
        raise ApiError('قائمة الأطباء غير صحيحة')
    new['doctors'] = json.dumps([str(x).strip()[:100] for x in docs if str(x).strip()], ensure_ascii=False)
    old = get_settings(c.db)
    if 'xray_folder' in b:
        new['xray_folder'] = v_text(b, 'xray_folder', 'مجلد صور الأشعة', maxlen=400)
    if 'xray_folder2' in b:
        new['xray_folder2'] = v_text(b, 'xray_folder2', 'مجلد جهاز الأشعة الثاني', maxlen=400)
    if 'money_thousands' in b:
        new['money_thousands'] = '1' if str(b.get('money_thousands')) in ('1', 'true', 'True') else '0'
    for k, v in new.items():
        c.db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (k, v))
    audit(c.db, c.user['username'], 'settings', None, 'update', {k: old.get(k) for k in new}, new)
    return {'ok': True, 'settings': get_settings(c.db)}


# ---------- سجل التدقيق ----------
@route('GET', '/api/audit', perm='audit', tx=False)
def audit_list(c):
    sql, args = 'SELECT * FROM audit_log WHERE 1=1', []
    if c.q.get('entity'):
        sql += ' AND entity=?'
        args.append(c.q['entity'])
    if c.q.get('entity_id'):
        sql += ' AND entity_id=?'
        args.append(int(c.q['entity_id']))
    try:
        limit = min(int(c.q.get('limit') or 200), 1000)
    except ValueError:
        limit = 200
    return {'rows': [dict(r) for r in c.db.execute(sql + ' ORDER BY id DESC LIMIT ?', args + [limit])]}


# ---------- النسخ الاحتياطي ----------
@route('POST', '/api/backup', perm='backup', tx=False)
def backup_create(c):
    info = c.clinic.make_backup('clinic')
    audit(c.db, c.user['username'], 'backup', None, 'create', None, {'name': info['name']})
    return {'ok': True, 'backup': info}


@route('GET', '/api/backups', perm='backup', tx=False)
def backup_list(c):
    return {'backups': c.clinic.list_backups(), 'dir': c.clinic.backup_dir}


@route('GET', '/api/backup/download', perm='backup', tx=False)
def backup_download(c):
    name = os.path.basename(c.q.get('name') or '')
    p = os.path.join(c.clinic.backup_dir, name)
    if not name.endswith('.db') or not os.path.isfile(p):
        raise ApiError('الملف غير موجود', 404)
    with open(p, 'rb') as f:
        data = f.read()
    return Response(body=data, ctype='application/octet-stream',
                    headers=[('Content-Disposition', "attachment; filename*=UTF-8''" + quote(name))])


@route('POST', '/api/restore', perm='backup', tx=False)
def backup_restore(c):
    if getattr(c.clinic, 'sync', None) and c.clinic.sync['cfg'].get('enabled'):
        raise ApiError('المزامنة مفعّلة: أوقفها أولاً من «الإعدادات ← المزامنة»، لأن الاستعادة في لابتوب واحد تخالف بيانات الآخر')
    if not c.raw:
        raise ApiError('لم يتم إرسال ملف')
    fd, tmp = tempfile.mkstemp(suffix='.db', dir=c.clinic.data_dir)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(c.raw)
        username = c.user['username']
        c.db.close()
        c.db = None
        safety = c.clinic.restore_from_file(tmp)
        db = connect(c.clinic.db_path)
        try:
            audit(db, username, 'backup', None, 'restore', None, {'safety_backup': safety['name']})
        finally:
            db.close()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return {'ok': True, 'safety_backup': safety['name'], 'relogin': True}


# ---------- التصدير (Excel / CSV) ----------
@route('POST', '/api/export', tx=False)
def export(c):
    b = c.body
    fmt = b.get('format')
    headers, rows = b.get('headers'), b.get('rows')
    if fmt not in ('xlsx', 'csv') or not isinstance(headers, list) or not isinstance(rows, list) or len(rows) > 50000:
        raise ApiError('بيانات التصدير غير صحيحة')
    rows = [r if isinstance(r, list) else [] for r in rows]
    title = v_text(b, 'title', 'العنوان', maxlen=60) or 'report'
    if fmt == 'xlsx':
        data, ctype = build_xlsx(title, headers, rows), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        data, ctype = build_csv(headers, rows), 'text/csv; charset=utf-8'
    return Response(body=data, ctype=ctype)
