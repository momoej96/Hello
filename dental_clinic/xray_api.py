# -*- coding: utf-8 -*-
"""صور الأشعة: استقبال تلقائي من مجلد برنامج السنسر (مثل Woodpecker)، رفع يدوي، عرض وحذف.
برنامج السنسر يلتقط الصورة ويحفظها في مجلده؛ عند الضغط على «استقبال أشعة» نراقب ذلك المجلد،
وكل صورة جديدة تُنسخ (النسخ لا النقل، فيبقى أصلها في برنامج السنسر) إلى data/xrays/<رقم المراجع>/."""
import os, time, secrets
from core import ApiError, get_settings, now_iso, audit, v_text, v_tooth, v_date, today_iso
from api import route, Response, get_patient

IMG_EXT = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.bmp': 'image/bmp'}
MAGIC = ((b'\x89PNG', '.png'), (b'\xff\xd8\xff', '.jpg'), (b'BM', '.bmp'))
SKIP_WORDS = ('thumb', 'thumbnail', 'preview', 'small')
SESSION_MINUTES = 15
SETTLE_SECONDS = 1.0          # ننتظر حتى يكتمل حفظ الملف قبل نسخه
MAX_IMAGE = 60 * 1024 * 1024


def xray_dir(clinic, pid=None):
    d = os.path.join(clinic.data_dir, 'xrays')
    return os.path.join(d, str(int(pid))) if pid is not None else d


def scan(folder):
    """كل صور المجلد ومجلداته الفرعية: {المسار: (وقت التعديل، الحجم)}."""
    out, stack = {}, [folder]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif os.path.splitext(e.name)[1].lower() in IMG_EXT and not any(w in e.name.lower() for w in SKIP_WORDS):
                        st = e.stat()
                        out[e.path] = (st.st_mtime, st.st_size)
                except OSError:
                    continue
    return out


def sniff(data):
    for sig, ext in MAGIC:
        if data.startswith(sig):
            return ext
    return None


def store_image(c, pid, data, source, original_path=None, taken_at=None, tooth=None, notes=None, visit_id=None):
    ext = sniff(data)
    if not ext:
        raise ApiError('الملف ليس صورة مدعومة (PNG أو JPG أو BMP)')
    if len(data) > MAX_IMAGE:
        raise ApiError('الصورة كبيرة جداً')
    now = now_iso()
    cur = c.db.execute('INSERT INTO xrays(patient_id,visit_id,taken_at,file_name,source,original_path,tooth_no,notes,size,created_by,created_at) '
                       'VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (pid, visit_id, taken_at or now, '', source, original_path, tooth, notes, len(data), c.user['username'], now))
    xid = cur.lastrowid
    d = xray_dir(c.clinic, pid)
    os.makedirs(d, exist_ok=True)
    name = '%d%s' % (xid, ext)
    tmp = os.path.join(d, name + '.part')
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, os.path.join(d, name))
    # المسار يُحفظ نسبةً لمجلد xrays (رقم المراجع وقت الحفظ)، فيبقى صحيحاً حتى لو دُمج الملف مع مراجع آخر
    c.db.execute('UPDATE xrays SET file_name=? WHERE id=?', ('%d/%s' % (pid, name), xid))
    audit(c.db, c.user['username'], 'xray', xid, 'create', None, {'patient_id': pid, 'source': source, 'original_path': original_path})
    return xray_row(c.db, xid)


def xray_row(db, xid):
    r = db.execute('SELECT id,patient_id,visit_id,taken_at,source,original_path,tooth_no,notes,size,created_by,created_at FROM xrays WHERE id=? AND deleted=0', (xid,)).fetchone()
    if not r:
        raise ApiError('الصورة غير موجودة', 404, 'not_found')
    return dict(r)


def folder_setting(c):
    f = (get_settings(c.db).get('xray_folder') or '').strip()
    if not f:
        raise ApiError('حدد مجلد صور الأشعة أولاً من «الإعدادات ← بيانات العيادة ← مجلد صور الأشعة»')
    if not os.path.isdir(f):
        raise ApiError('مجلد صور الأشعة غير موجود على الجهاز الرئيسي: %s' % f)
    return f


# ============ المسارات ============
@route('GET', r'/api/patients/(\d+)/xrays', perm='patients', tx=False)
def xrays_list(c, pid):
    get_patient(c.db, pid)
    return {'xrays': [dict(r) for r in c.db.execute(
        'SELECT id,patient_id,visit_id,taken_at,source,tooth_no,notes,size,created_by FROM xrays WHERE patient_id=? AND deleted=0 ORDER BY taken_at DESC, id DESC', (pid,))]}


@route('GET', r'/api/xrays/(\d+)/image', perm='patients', tx=False)
def xray_image(c, xid):
    r = c.db.execute('SELECT patient_id, file_name FROM xrays WHERE id=? AND deleted=0', (xid,)).fetchone()
    if not r or not r['file_name']:
        raise ApiError('الصورة غير موجودة', 404, 'not_found')
    root = os.path.realpath(xray_dir(c.clinic))
    path = os.path.realpath(os.path.join(root, r['file_name']))
    if not path.startswith(root + os.sep):
        raise ApiError('الصورة غير موجودة', 404, 'not_found')
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        raise ApiError('ملف الصورة مفقود من مجلد البيانات', 404, 'not_found')
    return Response(body=data, ctype=IMG_EXT.get(os.path.splitext(path)[1].lower(), 'application/octet-stream'))


@route('POST', r'/api/patients/(\d+)/xrays', perm='visits')
def xray_upload(c, pid):
    """رفع يدوي لصورة أشعة (صورة قديمة أو من جهاز آخر)."""
    get_patient(c.db, pid)
    if not c.raw:
        raise ApiError('لم يتم إرسال صورة')
    taken = v_date(c.q, 'date', 'تاريخ الصورة', required=False, allow_future=False)
    x = store_image(c, pid, c.raw, 'upload', (c.q.get('filename') or '')[:200] or None,
                    (taken + ' 00:00:00') if taken else None, v_tooth(c.q.get('tooth')))
    return {'xray': x}


@route('PUT', r'/api/xrays/(\d+)', perm='visits')
def xray_update(c, xid):
    old = xray_row(c.db, xid)
    tooth = v_tooth(c.body.get('tooth_no'))
    notes = v_text(c.body, 'notes', 'الملاحظات', maxlen=1000) or None
    c.db.execute('UPDATE xrays SET tooth_no=?, notes=? WHERE id=?', (tooth, notes, xid))
    audit(c.db, c.user['username'], 'xray', xid, 'update', old, {'tooth_no': tooth, 'notes': notes})
    return {'xray': xray_row(c.db, xid)}


@route('DELETE', r'/api/xrays/(\d+)', perm='delete')
def xray_delete(c, xid):
    old = xray_row(c.db, xid)
    c.db.execute('UPDATE xrays SET deleted=1 WHERE id=?', (xid,))   # الملف يبقى في مجلد البيانات
    audit(c.db, c.user['username'], 'xray', xid, 'delete', old, None)
    return {'ok': True}


# ---- الاستقبال التلقائي من مجلد برنامج السنسر ----
def _sessions(clinic):
    if not hasattr(clinic, 'xray_sessions'):
        clinic.xray_sessions = {}
    return clinic.xray_sessions


@route('POST', r'/api/patients/(\d+)/xray_capture', perm='visits', tx=False)
def capture_start(c, pid):
    p = get_patient(c.db, pid)
    folder = folder_setting(c)
    sessions = _sessions(c.clinic)
    with c.clinic.lock:
        # جلسة واحدة فقط: صورة جديدة يجب أن تذهب لمراجع واحد بلا لبس
        replaced = [dict(full_name=s['patient_name'], user=s['user']) for s in sessions.values() if time.time() < s['until']]
        sessions.clear()
        tok = secrets.token_urlsafe(12)
        sessions[tok] = {'patient_id': pid, 'patient_name': p['full_name'], 'user': c.user['username'], 'folder': folder,
                         'since': time.time(), 'until': time.time() + SESSION_MINUTES * 60, 'known': scan(folder), 'imported': []}
    return {'token': tok, 'folder': folder, 'minutes': SESSION_MINUTES, 'replaced': replaced}


@route('POST', r'/api/xray_capture/([\w\-]+)/poll', perm='visits', tx=False)
def capture_poll(c, tok):
    tok = str(tok)
    s = _sessions(c.clinic).get(tok)
    if not s:
        return {'active': False, 'reason': 'stopped', 'xrays': []}
    if time.time() > s['until']:
        _sessions(c.clinic).pop(tok, None)
        return {'active': False, 'reason': 'timeout', 'xrays': s['imported']}
    now, new = time.time(), []
    with c.clinic.lock:
        for path, (mtime, size) in sorted(scan(s['folder']).items(), key=lambda kv: kv[1][0]):
            if s['known'].get(path) == (mtime, size) or now - mtime < SETTLE_SECONDS or size == 0:
                continue
            try:
                with open(path, 'rb') as f:
                    data = f.read()
            except OSError:
                continue                       # ما زال برنامج السنسر يكتب الملف: نحاول في المرة القادمة
            s['known'][path] = (mtime, size)
            if not sniff(data):
                continue
            c.db.execute('BEGIN IMMEDIATE')
            try:
                x = store_image(c, s['patient_id'], data, 'sensor', path, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime)))
                c.db.execute('COMMIT')
            except BaseException:
                c.db.execute('ROLLBACK')
                raise
            s['imported'].append(x)
            new.append(x)
    return {'active': True, 'new': new, 'xrays': s['imported'], 'seconds_left': int(s['until'] - now)}


@route('POST', r'/api/xray_capture/([\w\-]+)/stop', perm='visits', tx=False)
def capture_stop(c, tok):
    s = _sessions(c.clinic).pop(str(tok), None)
    return {'ok': True, 'xrays': s['imported'] if s else []}


@route('GET', '/api/xray_folder_check', perm='settings', tx=False)
def folder_check(c):
    f = (c.q.get('folder') or '').strip()
    if not f:
        raise ApiError('اكتب مسار المجلد')
    if not os.path.isdir(f):
        return {'ok': False, 'message': 'المجلد غير موجود على الجهاز الرئيسي'}
    imgs = scan(f)
    last = max((m for m, _ in imgs.values()), default=None)
    return {'ok': True, 'count': len(imgs), 'last': time.strftime('%Y-%m-%d %H:%M', time.localtime(last)) if last else None}
