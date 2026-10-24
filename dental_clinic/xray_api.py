# -*- coding: utf-8 -*-
"""صور الأشعة: استقبال تلقائي من مجلد برنامج السنسر (مثل Woodpecker)، رفع يدوي، عرض وحذف.
برنامج السنسر يلتقط الصورة ويحفظها في مجلده؛ عند الضغط على «استقبال أشعة» نراقب ذلك المجلد،
وكل صورة جديدة تُنسخ (النسخ لا النقل، فيبقى أصلها في برنامج السنسر) إلى data/xrays/<رقم المراجع>/."""
import os, time, secrets, struct, zlib, threading
from core import ApiError, get_settings, now_iso, audit, v_text, v_tooth, v_date, today_iso
from api import route, Response, get_patient

IMG_EXT = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.bmp': 'image/bmp'}
MAGIC = ((b'\x89PNG', '.png'), (b'\xff\xd8\xff', '.jpg'), (b'BM', '.bmp'))
SKIP_WORDS = ('thumb', 'thumbnail', 'preview', 'small')
SESSION_MINUTES = 15
SETTLE_SECONDS = 1.0          # ننتظر حتى يكتمل حفظ الملف قبل نسخه
SHOT_GAP = 2.0                # ملفات اللقطة الواحدة تُحفظ معاً (مصغّرة + عادية + خام) خلال ثانيتين
SHOT_QUIET = 3.0              # ننتظر حتى يهدأ المجلد قبل اختيار صورة اللقطة
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


def image_info(data):
    """(العرض، الارتفاع، عمق البت) لصور PNG وBMP؛ None إن تعذّر."""
    if data.startswith(b'\x89PNG') and len(data) > 26 and data[12:16] == b'IHDR':
        w, h, bd = struct.unpack('>IIB', data[16:25])
        return w, h, bd
    if data.startswith(b'BM') and len(data) > 30:
        w, h, _, bd = struct.unpack('<iiHH', data[18:30])
        return abs(w), abs(h), bd
    return None


def png_mean(data, max_pixels=6_000_000):
    """متوسط سطوع صورة PNG بعمق 8 بت (0..255) لتمييز الصورة الخام البيضاء؛ None إن لم تُدعم."""
    try:
        w, h, bd = struct.unpack('>IIB', data[16:25])
        ct, interlace = data[25], data[28]
        ch = {0: 1, 2: 3, 4: 2, 6: 4}.get(ct)
        if bd != 8 or not ch or interlace or w * h > max_pixels:
            return None
        pos, idat = 8, []
        while pos < len(data):
            n, t = struct.unpack('>I4s', data[pos:pos + 8])
            if t == b'IDAT':
                idat.append(data[pos + 8:pos + 8 + n])
            pos += 12 + n
        raw, bpp, stride = zlib.decompress(b''.join(idat)), ch, w * ch
        prev, total = bytearray(stride), 0
        for y in range(h):
            f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
            if f == 1:
                for i in range(bpp, stride): line[i] = (line[i] + line[i - bpp]) & 255
            elif f == 2:
                line = bytearray((a + b) & 255 for a, b in zip(line, prev))
            elif f == 3:
                for i in range(stride): line[i] = (line[i] + ((line[i - bpp] if i >= bpp else 0) + prev[i]) // 2) & 255
            elif f == 4:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0; b = prev[i]; cc = prev[i - bpp] if i >= bpp else 0
                    pa, pb, pc = abs(b - cc), abs(a - cc), abs(a + b - 2 * cc)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else cc)) & 255
            total += sum(line[:w] if ch == 1 else line[0::ch])
            prev = line
        return total / float(w * h)
    except Exception:
        return None


def pick_shot_image(files):
    """من ملفات اللقطة الواحدة (مصغّرة، عادية، خام بيضاء) نختار الصورة العادية:
    نستبعد 16 بت (الخام) إن وُجد غيرها، ثم الأكبر أبعاداً (لا المصغّرة)، وعند تقارب الأبعاد الأغمق (لا البيضاء)."""
    c = [f for f in files if f['info']]
    if not c:
        return files[0] if len(files) == 1 else max(files, key=lambda f: len(f['data']))
    eight = [f for f in c if f['info'][2] <= 8]
    c = eight or c
    big = max(f['info'][0] * f['info'][1] for f in c)
    c = [f for f in c if f['info'][0] * f['info'][1] >= big * 0.8]
    if len(c) > 1:
        for f in c:
            f['mean'] = png_mean(f['data'])
        if all(f['mean'] is not None for f in c):
            return min(c, key=lambda f: f['mean'])
    return max(c, key=lambda f: f['info'][0] * f['info'][1])


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


def check_visit(db, pid, vid):
    """زيارة محددة يجب أن تكون لنفس المراجع؛ «» أو None = بدون ربط بزيارة."""
    if vid in (None, '', 0, '0'):
        return None
    try:
        vid = int(vid)
    except (TypeError, ValueError):
        raise ApiError('زيارة غير صحيحة')
    if not db.execute('SELECT 1 FROM visits WHERE id=? AND patient_id=? AND deleted=0', (vid, pid)).fetchone():
        raise ApiError('الزيارة المحددة لا تتبع هذا المراجع')
    return vid


def same_day_visit(db, pid, day):
    """زيارة المراجع في يوم التقاط الصورة (الأحدث إن وُجد أكثر من واحدة)."""
    r = db.execute('SELECT id FROM visits WHERE patient_id=? AND visit_date=? AND deleted=0 ORDER BY id DESC LIMIT 1', (pid, day)).fetchone()
    return r['id'] if r else None


SENSORS = {1: ('xray_folder', 'جهاز الأشعة الأول'), 2: ('xray_folder2', 'جهاز الأشعة الثاني')}


def is_remote(folder):
    """مجلد على حاسبة أخرى عبر الشبكة (\\\\حاسبة\\مجلد): قراءته قد تبطئ أو تتعطل إن كانت تلك الحاسبة مطفأة."""
    return folder.startswith('\\\\') or folder.startswith('//')


def sensor_folder(c, sensor):
    key, label = SENSORS[sensor]
    f = (get_settings(c.db).get(key) or '').strip()
    if not f:
        raise ApiError('حدد مجلد صور %s أولاً من «الإعدادات ← بيانات العيادة»' % label)
    if not is_remote(f) and not os.path.isdir(f):     # مجلد الشبكة يُفحص في الخلفية حتى لا يتوقف البرنامج
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
    vid = check_visit(c.db, pid, c.q.get('visit_id')) if c.q.get('visit_id') else same_day_visit(c.db, pid, taken or today_iso())
    x = store_image(c, pid, c.raw, 'upload', (c.q.get('filename') or '')[:200] or None,
                    (taken + ' 00:00:00') if taken else None, v_tooth(c.q.get('tooth')), visit_id=vid)
    return {'xray': x}


@route('PUT', r'/api/xrays/(\d+)', perm='visits')
def xray_update(c, xid):
    old = xray_row(c.db, xid)
    tooth = v_tooth(c.body.get('tooth_no'))
    notes = v_text(c.body, 'notes', 'الملاحظات', maxlen=1000) or None
    vid = check_visit(c.db, old['patient_id'], c.body.get('visit_id')) if 'visit_id' in c.body else old['visit_id']
    c.db.execute('UPDATE xrays SET tooth_no=?, notes=?, visit_id=? WHERE id=?', (tooth, notes, vid, xid))
    audit(c.db, c.user['username'], 'xray', xid, 'update', old, {'tooth_no': tooth, 'notes': notes, 'visit_id': vid})
    return {'xray': xray_row(c.db, xid)}


@route('DELETE', r'/api/xrays/(\d+)', perm='delete')
def xray_delete(c, xid):
    old = xray_row(c.db, xid)
    c.db.execute('UPDATE xrays SET deleted=1 WHERE id=?', (xid,))   # الملف يبقى في مجلد البيانات
    audit(c.db, c.user['username'], 'xray', xid, 'delete', old, None)
    return {'ok': True}


# ---- الاستقبال التلقائي من مجلد برنامج السنسر ----
# لكل جهاز أشعة جلسة واحدة. مراقبة المجلد تجري في خيط خلفي خارج قفل البرنامج، لأن مجلد الحاسبة الثانية
# يُقرأ عبر الشبكة وقد يكون بطيئاً أو غير متاح؛ والطلب يأخذ فقط الصور الجاهزة ويحفظها.
def _sessions(clinic):
    if not hasattr(clinic, 'xray_sessions'):
        clinic.xray_sessions = {}
    return clinic.xray_sessions


def find_shots(s, now):
    """صور اللقطات الجديدة المكتملة في مجلد الجلسة (صورة واحدة لكل لقطة)."""
    seen, found = s['seen'], []
    pending = []
    for p, (m, z) in scan(s['folder']).items():
        if s['known'].get(p) == (m, z) or z <= 0:
            continue
        if seen.get(p, (None,))[0] != (m, z):
            seen[p] = ((m, z), now)          # متى لاحظنا هذا الملف بحالته الحالية (بساعة هذا الجهاز)
        pending.append((p, m, z))
    # تجميع ملفات كل لقطة: نفس المجلد وأوقات حفظ متقاربة
    shots = []
    for p, m, z in sorted(pending, key=lambda t: (os.path.dirname(t[0]), t[1])):
        last = shots[-1] if shots else None
        if last and last['dir'] == os.path.dirname(p) and m - last['end'] <= SHOT_GAP:
            last['files'].append((p, m, z)); last['end'] = m
        else:
            shots.append({'dir': os.path.dirname(p), 'end': m, 'files': [(p, m, z)]})
    quiet = max(SHOT_QUIET, SETTLE_SECONDS)
    for shot in sorted(shots, key=lambda sh: sh['end']):
        # برنامج السنسر ما زال يحفظ ملفات هذه اللقطة؟ (ساعة الحاسبة الثانية قد تختلف، فنعتمد أيضاً وقت ملاحظتنا للملف)
        if now - shot['end'] < quiet and now - max(seen[p][1] for p, _, _ in shot['files']) < quiet:
            continue
        files = []
        for p, m, z in shot['files']:
            try:
                with open(p, 'rb') as f:
                    data = f.read()
            except OSError:
                files = None
                break
            if sniff(data):
                files.append({'path': p, 'mtime': m, 'data': data, 'info': image_info(data)})
        if files is None:
            continue                                   # ملف ما زال مقفلاً: نحاول في المرة القادمة
        for p, m, z in shot['files']:
            s['known'][p] = (m, z)
        if files:
            found.append((pick_shot_image(files), len(files) - 1))
    return found


def _watch(s):
    cv = s['cv']
    try:
        if 'known' not in s:
            if not os.path.isdir(s['folder']):
                raise OSError
            s['known'] = scan(s['folder'])
        s['ready'] = True
        while not s['stopped'] and time.time() < s['until']:
            with cv:
                s['scanning'] = True
            shots = find_shots(s, time.time())
            with cv:
                s['queue'].extend(shots); s['gen'] += 1; s['scanning'] = False; cv.notify_all()
                if not s['kick']:
                    cv.wait(1.5)
                s['kick'] = False
    except OSError:
        s['error'] = 'تعذّر الوصول لمجلد %s: %s — تأكد أن تلك الحاسبة شغالة وأن المجلد مشارك على الشبكة' % (s['label'], s['folder'])
    except Exception as e:                              # لا نترك الجلسة معلّقة بصمت
        s['error'] = 'خطأ في مراقبة مجلد الأشعة: %s' % e
    with cv:
        s['gen'] += 1; cv.notify_all()


@route('POST', r'/api/patients/(\d+)/xray_capture', perm='visits', tx=False)
def capture_start(c, pid):
    p = get_patient(c.db, pid)
    vid = check_visit(c.db, pid, c.body.get('visit_id'))
    sensor = 2 if str(c.body.get('sensor') or '1') == '2' else 1
    folder = sensor_folder(c, sensor)
    sessions = _sessions(c.clinic)
    with c.clinic.lock:
        # جلسة واحدة لكل جهاز أشعة: صورة جديدة يجب أن تذهب لمراجع واحد بلا لبس
        replaced = []
        for k, s in list(sessions.items()):
            if s['sensor'] == sensor or time.time() > s['until']:
                if s['sensor'] == sensor and time.time() < s['until']:
                    replaced.append(dict(full_name=s['patient_name'], user=s['user']))
                s['stopped'] = True
                with s['cv']:
                    s['cv'].notify_all()
                sessions.pop(k)
        tok = secrets.token_urlsafe(12)
        s = {'patient_id': pid, 'patient_name': p['full_name'], 'visit_id': vid, 'user': c.user['username'], 'folder': folder,
             'sensor': sensor, 'label': SENSORS[sensor][1], 'remote': is_remote(folder),
             'since': time.time(), 'until': time.time() + SESSION_MINUTES * 60, 'seen': {}, 'imported': [],
             'queue': [], 'gen': 0, 'kick': False, 'scanning': False, 'stopped': False, 'ready': False, 'error': None, 'cv': threading.Condition()}
        if not s['remote']:
            s['known'] = scan(folder)          # المجلد المحلي سريع: نبدأ فوراً
        sessions[tok] = s
    threading.Thread(target=_watch, args=(s,), daemon=True, name='xray-watch').start()
    return {'token': tok, 'folder': folder, 'sensor': sensor, 'label': s['label'], 'minutes': SESSION_MINUTES, 'replaced': replaced, 'visit_id': vid}


@route('POST', r'/api/xray_capture/([\w\-]+)/poll', perm='visits', tx=False)
def capture_poll(c, tok):
    tok = str(tok)
    s = _sessions(c.clinic).get(tok)
    if not s:
        return {'active': False, 'reason': 'stopped', 'xrays': []}
    if time.time() > s['until']:
        _sessions(c.clinic).pop(tok, None)
        s['stopped'] = True
        return {'active': False, 'reason': 'timeout', 'xrays': s['imported']}
    cv = s['cv']
    with cv:
        # المجلد المحلي: نطلب فحصاً فورياً وننتظره قليلاً؛ مجلد الشبكة: لا ننتظر حتى لا يتوقف البرنامج
        need = s['gen'] + (2 if s['scanning'] else 1)     # فحص يبدأ بعد هذا الطلب
        s['kick'] = True; cv.notify_all()
        if not s['remote']:
            cv.wait_for(lambda: s['gen'] >= need or s['error'] or s['stopped'], timeout=1.5)
        shots, s['queue'] = s['queue'], []
    new, now = [], time.time()
    for best, skipped in shots:
        s['skipped'] = s.get('skipped', 0) + skipped
        c.db.execute('BEGIN IMMEDIATE')
        try:
            taken = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min(best['mtime'], now)))
            vid = s['visit_id']
            if vid and not c.db.execute('SELECT 1 FROM visits WHERE id=? AND deleted=0', (vid,)).fetchone():
                vid = None                                        # حُذفت الزيارة أثناء الاستقبال
            vid = vid or same_day_visit(c.db, s['patient_id'], taken[:10])   # وإلا: زيارة نفس اليوم
            x = store_image(c, s['patient_id'], best['data'], 'sensor', best['path'], taken, visit_id=vid)
            c.db.execute('COMMIT')
        except BaseException:
            c.db.execute('ROLLBACK')
            raise
        s['imported'].append(x)
        new.append(x)
    return {'active': True, 'new': new, 'xrays': s['imported'], 'skipped': s.get('skipped', 0), 'seconds_left': int(s['until'] - now),
            'ready': s['ready'], 'error': s['error'], 'label': s['label']}


@route('POST', r'/api/xray_capture/([\w\-]+)/stop', perm='visits', tx=False)
def capture_stop(c, tok):
    s = _sessions(c.clinic).pop(str(tok), None)
    if s:
        s['stopped'] = True
        with s['cv']:
            s['cv'].notify_all()
    return {'ok': True, 'xrays': s['imported'] if s else []}


@route('GET', '/api/xray_folder_check', perm='settings', tx=False)
def folder_check(c):
    f = (c.q.get('folder') or '').strip()
    if not f:
        raise ApiError('اكتب مسار المجلد')
    res = {}

    def run():
        res['ok'] = os.path.isdir(f)
        if res['ok']:
            res['imgs'] = scan(f)
    t = threading.Thread(target=run, daemon=True)
    t.start(); t.join(15)                    # مجلد شبكة لحاسبة مطفأة قد لا يرد
    if t.is_alive():
        return {'ok': False, 'message': 'لا يوجد رد من الحاسبة: تأكد أنها شغالة وأن المجلد مشارك على الشبكة'}
    if not res.get('ok'):
        return {'ok': False, 'message': 'المجلد غير متاح: تأكد أن المسار صحيح وأن الحاسبة شغالة' if is_remote(f) else 'المجلد غير موجود على الجهاز الرئيسي'}
    imgs = res['imgs']
    last = max((m for m, _ in imgs.values()), default=None)
    return {'ok': True, 'count': len(imgs), 'last': time.strftime('%Y-%m-%d %H:%M', time.localtime(last)) if last else None}
