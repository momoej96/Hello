# -*- coding: utf-8 -*-
"""مسارات الـ API: الجلسات، المراجعون، الزيارات، الدفعات، المواعيد، المصروفات."""
import re, json, hmac, time
from core import *

ROUTES = []
ROLE_PERMS = {
    'admin': {'*'},
    'reception': {'patients', 'visits', 'payments', 'appointments', 'reports_basic'},
    'doctor': {'patients', 'visits', 'appointments'},
}


class Response:
    def __init__(self, data=None, status=200, body=None, ctype='application/json; charset=utf-8', headers=None):
        self.data, self.status, self.body, self.ctype, self.headers = data, status, body, ctype, headers or []


class Ctx:
    def __init__(self, clinic, db, user, q, body, raw):
        self.clinic, self.db, self.user, self.q, self.body, self.raw = clinic, db, user, q, body, raw

    @property
    def force(self):
        return bool(self.body.get('force')) or self.q.get('force') in ('1', 'true')


def route(method, pattern, perm=None, public=False, tx=True):
    def deco(fn):
        ROUTES.append((method, re.compile('^' + pattern + '$'), perm, public, tx, fn))
        return fn
    return deco


def can(user, perm):
    if not user:
        return False
    p = ROLE_PERMS.get(user['role'], set())
    return '*' in p or perm in p


def get_patient(db, pid, include_deleted=False):
    r = db.execute('SELECT * FROM patients WHERE id=?', (pid,)).fetchone()
    if not r or (r['deleted'] and not include_deleted):
        raise ApiError('المراجع غير موجود', 404, 'not_found')
    return r


def public_patient(r):
    d = dict(r)
    d.pop('name_norm', None)
    d.pop('phone_norm', None)
    return d


def guard_overpay(c, pid, before):
    """يمنع التعديل الذي يجعل المدفوع أكبر من المستحق إلا بتأكيد صريح (force)."""
    after = balance(c.db, pid)
    if after['remaining'] < 0 and after['remaining'] < min(before['remaining'], 0) and not c.force:
        raise ApiError('هذا الإجراء يجعل المبلغ المدفوع أكبر من المستحق على المراجع (رصيد دائن). هل تريد المتابعة؟',
                       409, 'overpaid', {'remaining': after['remaining']})


# ============ الجلسة والدخول ============
def public_settings(db):
    s = get_settings(db)
    return {k: s[k] for k in PUBLIC_SETTING_KEYS}


@route('GET', '/api/session', public=True, tx=False)
def session_info(c):
    users = c.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    perms = None
    if c.user:
        p = ROLE_PERMS[c.user['role']]
        perms = ['*'] if '*' in p else sorted(p)
    lan_urls = []
    if c.clinic.lan and c.user and c.user['role'] == 'admin':
        from netutil import lan_ips
        lan_urls = ['http://%s:%d/' % (ip, c.clinic.port) for ip in lan_ips()]
    return {'authenticated': bool(c.user), 'needs_setup': users == 0, 'user': c.user, 'perms': perms,
            'lan': c.clinic.lan, 'lan_urls': lan_urls,
            'settings': public_settings(c.db), 'demo': c.clinic.demo,
            'expense_categories': EXPENSE_CATS}


def _login_response(c, user_row):
    tok = c.clinic.new_session(user_row['id'])
    cookie = 'sid=%s; HttpOnly; SameSite=Strict; Path=/' % tok
    u = {k: user_row[k] for k in ('id', 'username', 'full_name', 'role')}
    p = ROLE_PERMS[u['role']]
    return Response({'ok': True, 'user': u, 'perms': ['*'] if '*' in p else sorted(p)}, headers=[('Set-Cookie', cookie)])


@route('POST', '/api/setup', public=True)
def setup(c):
    if c.db.execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0:
        raise ApiError('تم إعداد البرنامج مسبقاً', 403)
    b = c.body
    username = v_text(b, 'username', 'اسم المستخدم', required=True, maxlen=40)
    if len(username) < 3:
        raise ApiError('اسم المستخدم يجب ألا يقل عن 3 أحرف')
    pw = b.get('password')
    check_password_strength(pw)
    name = v_text(b, 'clinic_name', 'اسم العيادة', maxlen=120)
    h, s = hash_pw(pw)
    c.db.execute('INSERT INTO users(username,full_name,role,pw_hash,salt,active,created_at) VALUES(?,?,?,?,?,1,?)',
                 (username, v_text(b, 'full_name', 'الاسم', maxlen=100) or username, 'admin', h, s, now_iso()))
    if name:
        c.db.execute("UPDATE settings SET value=? WHERE key='clinic_name'", (name,))
    uid = c.db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()[0]
    audit(c.db, username, 'user', uid, 'setup')
    return _login_response(c, c.db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())


@route('POST', '/api/login', public=True)
def login(c):
    username = str(c.body.get('username') or '').strip()
    pw = c.body.get('password')
    key = username.lower()
    f = c.clinic.fails.get(key)
    if f and f[0] >= 5 and time.time() - f[1] < 60:
        raise ApiError('محاولات دخول كثيرة خاطئة. انتظر دقيقة ثم حاول مرة أخرى', 429, 'locked')
    r = c.db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    ok = False
    if isinstance(pw, str) and pw:
        h, _ = hash_pw(pw, r['salt'] if r else '00' * 16)
        ok = bool(r) and r['active'] and hmac.compare_digest(h, r['pw_hash'])
    if not ok:
        cnt = (f[0] if f and time.time() - f[1] < 60 else 0) + 1
        c.clinic.fails[key] = (cnt, time.time())
        raise ApiError('اسم المستخدم أو كلمة المرور غير صحيحة', 401, 'bad_login')
    c.clinic.fails.pop(key, None)
    audit(c.db, username, 'user', r['id'], 'login')
    try:
        c.clinic.maybe_auto_backup()
    except Exception:
        pass
    return _login_response(c, r)


@route('POST', '/api/logout', public=True, tx=False)
def logout(c):
    tok = c.raw_cookie if hasattr(c, 'raw_cookie') else None
    if tok:
        c.clinic.drop_session(tok)
    return Response({'ok': True}, headers=[('Set-Cookie', 'sid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')])


@route('POST', '/api/change_password')
def change_password(c):
    r = c.db.execute('SELECT * FROM users WHERE id=?', (c.user['id'],)).fetchone()
    h, _ = hash_pw(str(c.body.get('old_password') or ''), r['salt'])
    if not hmac.compare_digest(h, r['pw_hash']):
        raise ApiError('كلمة المرور الحالية غير صحيحة')
    check_password_strength(c.body.get('new_password'))
    nh, ns = hash_pw(c.body['new_password'])
    c.db.execute('UPDATE users SET pw_hash=?, salt=? WHERE id=?', (nh, ns, r['id']))
    audit(c.db, c.user['username'], 'user', r['id'], 'change_password')
    return {'ok': True}


# ============ المراجعون ============
def search_cond(q, alias='p'):
    q = (q or '').strip()
    if not q:
        return '', []
    nq = norm_ar(q)
    conds, args = [], []
    toks = [t for t in nq.split(' ') if t]
    if toks:
        conds.append('(' + ' AND '.join(["%s.name_norm LIKE ? ESCAPE '\\'" % alias for _ in toks]) + ')')
        args += ['%' + esc_like(t) + '%' for t in toks]
        conds.append("replace(%s.name_norm,' ','') LIKE ? ESCAPE '\\'" % alias)
        args.append('%' + esc_like(nq.replace(' ', '')) + '%')
    digits = re.sub(r'\D', '', nq)
    if digits:
        conds.append("CAST(%s.file_no AS TEXT) LIKE ?" % alias)
        args.append(digits + '%')
        cp = canon_phone(digits)
        if len(cp) >= 3:
            conds.append("%s.phone_norm LIKE ?" % alias)
            args.append('%' + cp + '%')
    return '(' + ' OR '.join(conds) + ')', args


@route('GET', '/api/patients', perm='patients', tx=False)
def patients_list(c):
    q = (c.q.get('q') or '').strip()
    try:
        limit = max(1, min(int(c.q.get('limit') or 100), 500))
    except ValueError:
        limit = 100
    sql = ("SELECT p.*, (b.total_cost - b.discounts + b.debits - (b.paid - b.refunded)) AS remaining "
           "FROM patients p JOIN v_balances b ON b.patient_id=p.id WHERE p.deleted=0")
    args = []
    cond, a = search_cond(q)
    if cond:
        sql += ' AND ' + cond
        args += a
    digits = re.sub(r'\D', '', norm_ar(q))
    if q:
        sql += ' ORDER BY (p.file_no = ?) DESC, p.name_norm LIMIT ?'
        args += [int(digits) if digits and len(digits) < 12 else -1, limit]
    else:
        sql += ' ORDER BY p.id DESC LIMIT ?'
        args.append(limit)
    rows = []
    money = can(c.user, 'payments')
    for r in c.db.execute(sql, args):
        d = public_patient(r)
        if not money:
            d.pop('remaining', None)
        rows.append(d)
    return {'patients': rows}


def clean_patient(b):
    name = v_text(b, 'full_name', 'الاسم الكامل', required=True, maxlen=120)
    if len(norm_ar(name)) < 2:
        raise ApiError('الاسم قصير جداً')
    phone = v_text(b, 'phone', 'رقم الهاتف', maxlen=30)
    if phone and len(canon_phone(phone)) < 6:
        raise ApiError('رقم الهاتف غير صحيح')
    age = None
    if b.get('age') not in (None, ''):
        try:
            age = int(str(b['age']).translate(AR_DIGITS))
        except ValueError:
            raise ApiError('العمر غير صحيح')
        if age < 0 or age > 120:
            raise ApiError('العمر غير صحيح')
    gender = b.get('gender') or None
    if gender not in (None, 'M', 'F'):
        raise ApiError('قيمة الجنس غير صحيحة')
    return {
        'full_name': re.sub(r'\s+', ' ', name), 'name_norm': norm_ar(name),
        'phone': phone or None, 'phone_norm': canon_phone(phone) or None,
        'birth_date': v_date(b, 'birth_date', 'تاريخ الميلاد', required=False, allow_future=False),
        'age': age, 'gender': gender,
        'first_visit_date': v_date(b, 'first_visit_date', 'تاريخ أول زيارة', required=False, allow_future=False),
        'notes': v_text(b, 'notes', 'الملاحظات', maxlen=3000) or None,
    }


def check_duplicate(c, f, exclude_id=None):
    if f['phone_norm'] and not c.force:
        r = c.db.execute('SELECT id,file_no,full_name FROM patients WHERE deleted=0 AND name_norm=? AND phone_norm=? AND id IS NOT ?',
                         (f['name_norm'], f['phone_norm'], exclude_id)).fetchone()
        if r:
            raise ApiError('يوجد مراجع بنفس الاسم ورقم الهاتف (ملف رقم %d). هل تريد إضافته مرة أخرى؟' % r['file_no'],
                           409, 'duplicate', {'existing': dict(r)})


@route('POST', '/api/patients', perm='patients')
def patient_create(c):
    f = clean_patient(c.body)
    check_duplicate(c, f)
    now = now_iso()
    file_no = c.db.execute('SELECT COALESCE(MAX(file_no),1000)+1 FROM patients').fetchone()[0]
    cur = c.db.execute(
        'INSERT INTO patients(file_no,full_name,name_norm,phone,phone_norm,birth_date,age,gender,first_visit_date,notes,created_at,updated_at) '
        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
        (file_no, f['full_name'], f['name_norm'], f['phone'], f['phone_norm'], f['birth_date'], f['age'], f['gender'],
         f['first_visit_date'] or today_iso(), f['notes'], now, now))
    pid = cur.lastrowid
    audit(c.db, c.user['username'], 'patient', pid, 'create', None, {'file_no': file_no, 'full_name': f['full_name']})
    return {'patient': public_patient(get_patient(c.db, pid))}


@route('PUT', r'/api/patients/(\d+)', perm='patients')
def patient_update(c, pid):
    old = get_patient(c.db, pid)
    f = clean_patient(c.body)
    check_duplicate(c, f, exclude_id=pid)
    c.db.execute('UPDATE patients SET full_name=?,name_norm=?,phone=?,phone_norm=?,birth_date=?,age=?,gender=?,first_visit_date=?,notes=?,updated_at=? WHERE id=?',
                 (f['full_name'], f['name_norm'], f['phone'], f['phone_norm'], f['birth_date'], f['age'], f['gender'],
                  f['first_visit_date'] or old['first_visit_date'], f['notes'], now_iso(), pid))
    audit(c.db, c.user['username'], 'patient', pid, 'update', public_patient(old), public_patient(get_patient(c.db, pid)))
    return {'patient': public_patient(get_patient(c.db, pid))}


@route('DELETE', r'/api/patients/(\d+)', perm='delete')
def patient_delete(c, pid):
    old = get_patient(c.db, pid)
    bal = balance(c.db, pid)
    if bal['remaining'] != 0:
        raise ApiError('لا يمكن حذف مراجع لديه رصيد غير مسدد أو رصيد دائن. سوِّ حسابه أولاً')
    c.db.execute('UPDATE patients SET deleted=1, updated_at=? WHERE id=?', (now_iso(), pid))
    audit(c.db, c.user['username'], 'patient', pid, 'delete', public_patient(old), None, c.body.get('reason'))
    return {'ok': True}


def visit_with_procs(db, vrow):
    v = dict(vrow)
    v['procedures'] = [dict(r) for r in db.execute(
        'SELECT * FROM procedures WHERE visit_id=? AND deleted=0 ORDER BY id', (v['id'],))]
    v['visit_total'] = sum(p['cost'] for p in v['procedures'] if p['status'] != 'cancelled')
    return v


@route('GET', r'/api/patients/(\d+)', perm='patients', tx=False)
def patient_get(c, pid):
    p = get_patient(c.db, pid)
    out = {'patient': public_patient(p)}
    out['visits'] = [visit_with_procs(c.db, r) for r in c.db.execute(
        'SELECT * FROM visits WHERE patient_id=? AND deleted=0 ORDER BY visit_date DESC, id DESC', (pid,))]
    out['appointments'] = [dict(r) for r in c.db.execute(
        'SELECT * FROM appointments WHERE patient_id=? AND deleted=0 ORDER BY appt_date DESC, appt_time DESC', (pid,))]
    if can(c.user, 'payments'):
        out['payments'] = [dict(r) for r in c.db.execute(
            'SELECT * FROM payments WHERE patient_id=? AND deleted=0 ORDER BY pay_date DESC, id DESC', (pid,))]
        out['adjustments'] = [dict(r) for r in c.db.execute(
            'SELECT * FROM adjustments WHERE patient_id=? AND deleted=0 ORDER BY adj_date DESC, id DESC', (pid,))]
        out['summary'] = balance(c.db, pid)
    return out


# ============ الزيارات والإجراءات ============
def clean_procs(lst, default_doctor):
    if not isinstance(lst, list):
        raise ApiError('قائمة الإجراءات غير صحيحة')
    out = []
    for i, p in enumerate(lst, 1):
        if not isinstance(p, dict):
            raise ApiError('إجراء غير صحيح')
        out.append({
            'id': p.get('id'),
            'name': v_text(p, 'name', 'اسم الإجراء رقم %d' % i, required=True, maxlen=200),
            'tooth_no': v_tooth(p.get('tooth_no')),
            'details': v_text(p, 'details', 'تفاصيل الإجراء', maxlen=2000) or None,
            'status': v_choice(p, 'status', 'حالة الإجراء', PROC_STATUS, 'completed'),
            'cost': v_money(p, 'cost', 'تكلفة الإجراء رقم %d' % i, required=False, allow_zero=True) or 0,
            'doctor': v_text(p, 'doctor', 'الطبيب', maxlen=100) or default_doctor or None,
        })
    return out


def sync_next_appt(c, visit_id, pid, next_date, next_time):
    ex = c.db.execute('SELECT * FROM appointments WHERE source_visit_id=? AND deleted=0', (visit_id,)).fetchone()
    now = now_iso()
    if not next_date:
        if ex and ex['status'] == 'confirmed':
            c.db.execute('UPDATE appointments SET deleted=1, updated_at=? WHERE id=?', (now, ex['id']))
        return
    if ex:
        if ex['status'] == 'confirmed':
            c.db.execute('UPDATE appointments SET appt_date=?, appt_time=?, updated_at=? WHERE id=?',
                         (next_date, next_time, now, ex['id']))
    else:
        c.db.execute("INSERT INTO appointments(patient_id,appt_date,appt_time,reason,status,source_visit_id,created_at,updated_at) "
                     "VALUES(?,?,?,?, 'confirmed', ?,?,?)", (pid, next_date, next_time, 'موعد مراجعة قادمة', visit_id, now, now))


def clean_visit(b):
    doctor = v_text(b, 'doctor', 'الطبيب', maxlen=100) or None
    return {
        'visit_date': v_date(b, 'visit_date', 'تاريخ الزيارة', allow_future=False),
        'visit_time': v_time(b, 'visit_time', 'وقت الزيارة'),
        'doctor': doctor,
        'notes': v_text(b, 'notes', 'الملاحظات السريرية', maxlen=4000) or None,
        'next_appointment': v_date(b, 'next_appointment', 'موعد الزيارة القادمة', required=False),
        'next_time': v_time(b, 'next_time', 'وقت الموعد القادم'),
    }


def insert_proc(c, vid, pid, p, now):
    c.db.execute('INSERT INTO procedures(visit_id,patient_id,name,tooth_no,details,status,cost,doctor,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                 (vid, pid, p['name'], p['tooth_no'], p['details'], p['status'], p['cost'], p['doctor'], now, now))


@route('POST', r'/api/patients/(\d+)/visits', perm='visits')
def visit_create(c, pid):
    get_patient(c.db, pid)
    f = clean_visit(c.body)
    procs = clean_procs(c.body.get('procedures') or [], f['doctor'])
    now = now_iso()
    cur = c.db.execute('INSERT INTO visits(patient_id,visit_date,visit_time,doctor,notes,next_appointment,next_time,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                       (pid, f['visit_date'], f['visit_time'], f['doctor'], f['notes'], f['next_appointment'], f['next_time'], now, now))
    vid = cur.lastrowid
    for p in procs:
        insert_proc(c, vid, pid, p, now)
    sync_next_appt(c, vid, pid, f['next_appointment'], f['next_time'])
    audit(c.db, c.user['username'], 'visit', vid, 'create', None, {'visit': f, 'procedures': procs})
    out = {'visit': visit_with_procs(c.db, c.db.execute('SELECT * FROM visits WHERE id=?', (vid,)).fetchone())}
    if can(c.user, 'payments'):
        out['summary'] = balance(c.db, pid)
    return out


def get_visit(db, vid):
    r = db.execute('SELECT * FROM visits WHERE id=?', (vid,)).fetchone()
    if not r or r['deleted']:
        raise ApiError('الزيارة غير موجودة', 404, 'not_found')
    return r


@route('PUT', r'/api/visits/(\d+)', perm='visits')
def visit_update(c, vid):
    old = get_visit(c.db, vid)
    pid = old['patient_id']
    before = balance(c.db, pid)
    old_full = visit_with_procs(c.db, old)
    f = clean_visit(c.body)
    now = now_iso()
    c.db.execute('UPDATE visits SET visit_date=?,visit_time=?,doctor=?,notes=?,next_appointment=?,next_time=?,updated_at=? WHERE id=?',
                 (f['visit_date'], f['visit_time'], f['doctor'], f['notes'], f['next_appointment'], f['next_time'], now, vid))
    if 'procedures' in c.body:
        procs = clean_procs(c.body['procedures'], f['doctor'])
        existing = {r['id'] for r in c.db.execute('SELECT id FROM procedures WHERE visit_id=? AND deleted=0', (vid,))}
        keep = set()
        for p in procs:
            if p['id'] is not None:
                try:
                    pid_ = int(p['id'])
                except (TypeError, ValueError):
                    raise ApiError('معرّف إجراء غير صحيح')
                if pid_ not in existing:
                    raise ApiError('إجراء لا يتبع هذه الزيارة')
                keep.add(pid_)
                c.db.execute('UPDATE procedures SET name=?,tooth_no=?,details=?,status=?,cost=?,doctor=?,updated_at=? WHERE id=?',
                             (p['name'], p['tooth_no'], p['details'], p['status'], p['cost'], p['doctor'], now, pid_))
            else:
                insert_proc(c, vid, pid, p, now)
        for gone in existing - keep:
            c.db.execute('UPDATE procedures SET deleted=1, updated_at=? WHERE id=?', (now, gone))
    sync_next_appt(c, vid, pid, f['next_appointment'], f['next_time'])
    guard_overpay(c, pid, before)
    new_full = visit_with_procs(c.db, get_visit(c.db, vid))
    audit(c.db, c.user['username'], 'visit', vid, 'update', old_full, new_full)
    out = {'visit': new_full}
    if can(c.user, 'payments'):
        out['summary'] = balance(c.db, pid)
    return out


@route('DELETE', r'/api/visits/(\d+)', perm='delete')
def visit_delete(c, vid):
    old = get_visit(c.db, vid)
    pid = old['patient_id']
    before = balance(c.db, pid)
    old_full = visit_with_procs(c.db, old)
    now = now_iso()
    c.db.execute('UPDATE visits SET deleted=1, updated_at=? WHERE id=?', (now, vid))
    c.db.execute('UPDATE procedures SET deleted=1, updated_at=? WHERE visit_id=?', (now, vid))
    c.db.execute("UPDATE appointments SET deleted=1, updated_at=? WHERE source_visit_id=? AND status='confirmed'", (now, vid))
    guard_overpay(c, pid, before)
    audit(c.db, c.user['username'], 'visit', vid, 'delete', old_full, None, c.body.get('reason'))
    return {'ok': True, 'summary': balance(c.db, pid)}


@route('PUT', r'/api/procedures/(\d+)', perm='visits')
def proc_update(c, procid):
    r = c.db.execute('SELECT * FROM procedures WHERE id=? AND deleted=0', (procid,)).fetchone()
    if not r:
        raise ApiError('الإجراء غير موجود', 404, 'not_found')
    before = balance(c.db, r['patient_id'])
    b = dict(r)
    b.update({k: v for k, v in c.body.items() if k in ('name', 'tooth_no', 'details', 'status', 'cost', 'doctor')})
    p = clean_procs([b], None)[0]
    c.db.execute('UPDATE procedures SET name=?,tooth_no=?,details=?,status=?,cost=?,doctor=?,updated_at=? WHERE id=?',
                 (p['name'], p['tooth_no'], p['details'], p['status'], p['cost'], p['doctor'], now_iso(), procid))
    guard_overpay(c, r['patient_id'], before)
    audit(c.db, c.user['username'], 'procedure', procid, 'update', dict(r),
          dict(c.db.execute('SELECT * FROM procedures WHERE id=?', (procid,)).fetchone()))
    return {'ok': True, 'summary': balance(c.db, r['patient_id']) if can(c.user, 'payments') else None}


# ============ الدفعات والتعديلات المالية ============
def get_payment(db, payid):
    r = db.execute('SELECT * FROM payments WHERE id=?', (payid,)).fetchone()
    if not r or r['deleted']:
        raise ApiError('الدفعة غير موجودة', 404, 'not_found')
    return r


@route('POST', r'/api/patients/(\d+)/payments', perm='payments')
def payment_create(c, pid):
    p = get_patient(c.db, pid)
    b = c.body
    idem = v_text(b, 'idem_key', 'مفتاح منع التكرار', required=True, maxlen=80)
    ex = c.db.execute('SELECT * FROM payments WHERE idem_key=?', (idem,)).fetchone()
    if ex:   # نفس الطلب أُرسل سابقاً (ضغط مزدوج): نعيد السجل نفسه دون إنشاء دفعة جديدة
        return {'payment': dict(ex), 'summary': balance(c.db, pid), 'duplicate': True}
    amount = v_money(b, 'amount', 'المبلغ')
    kind = v_choice(b, 'kind', 'نوع العملية', ('payment', 'refund'), 'payment')
    method = v_choice(b, 'method', 'طريقة الدفع', PAY_METHODS, 'cash')
    pay_date = v_date(b, 'pay_date', 'تاريخ الدفعة', allow_future=False)
    notes = v_text(b, 'notes', 'الملاحظات', maxlen=1000) or None
    visit_id = b.get('visit_id') or None
    if visit_id:
        v = c.db.execute('SELECT patient_id FROM visits WHERE id=? AND deleted=0', (visit_id,)).fetchone()
        if not v or v['patient_id'] != pid:
            raise ApiError('الزيارة المحددة لا تتبع هذا المراجع')
    before = balance(c.db, pid)
    if kind == 'refund' and amount > before['net_paid']:
        raise ApiError('مبلغ الاسترداد أكبر من صافي ما دفعه المراجع (%s)' % format(before['net_paid'], ','))
    cur = c.db.execute('INSERT INTO payments(patient_id,visit_id,pay_date,amount,kind,method,notes,idem_key,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (pid, visit_id, pay_date, amount, kind, method, notes, idem, c.user['username'], now_iso()))
    if kind == 'payment':
        guard_overpay(c, pid, before)
    payid = cur.lastrowid
    row = dict(c.db.execute('SELECT * FROM payments WHERE id=?', (payid,)).fetchone())
    audit(c.db, c.user['username'], 'payment', payid, 'create', None, row)
    return {'payment': row, 'summary': balance(c.db, pid), 'duplicate': False, 'patient': public_patient(p)}


@route('PUT', r'/api/payments/(\d+)', perm='finance_edit')
def payment_update(c, payid):
    old = get_payment(c.db, payid)
    pid = old['patient_id']
    before = balance(c.db, pid)
    b = c.body
    amount = v_money(b, 'amount', 'المبلغ')
    method = v_choice(b, 'method', 'طريقة الدفع', PAY_METHODS)
    pay_date = v_date(b, 'pay_date', 'تاريخ الدفعة', allow_future=False)
    notes = v_text(b, 'notes', 'الملاحظات', maxlen=1000) or None
    c.db.execute('UPDATE payments SET amount=?, method=?, pay_date=?, notes=? WHERE id=?', (amount, method, pay_date, notes, payid))
    after = balance(c.db, pid)
    if after['net_paid'] < 0:
        raise ApiError('التعديل يجعل صافي المدفوعات سالباً')
    guard_overpay(c, pid, before)
    audit(c.db, c.user['username'], 'payment', payid, 'update', dict(old), dict(get_payment(c.db, payid)), b.get('reason'))
    return {'payment': dict(get_payment(c.db, payid)), 'summary': after}


@route('DELETE', r'/api/payments/(\d+)', perm='finance_edit')
def payment_void(c, payid):
    old = get_payment(c.db, payid)
    reason = v_text(c.body, 'reason', 'سبب الإلغاء', required=True, maxlen=300)
    pid = old['patient_id']
    before = balance(c.db, pid)
    c.db.execute('UPDATE payments SET deleted=1, void_reason=? WHERE id=?', (reason, payid))
    guard_overpay(c, pid, before)
    audit(c.db, c.user['username'], 'payment', payid, 'void', dict(old), None, reason)
    return {'ok': True, 'summary': balance(c.db, pid)}


@route('POST', r'/api/patients/(\d+)/adjustments', perm='payments')
def adjustment_create(c, pid):
    get_patient(c.db, pid)
    b = c.body
    kind = v_choice(b, 'kind', 'نوع التعديل', ('discount', 'debit'))
    amount = v_money(b, 'amount', 'المبلغ')
    d = v_date(b, 'adj_date', 'التاريخ', allow_future=False)
    notes = v_text(b, 'notes', 'سبب التعديل', required=True, maxlen=500)
    before = balance(c.db, pid)
    cur = c.db.execute('INSERT INTO adjustments(patient_id,adj_date,amount,kind,notes,created_by,created_at) VALUES(?,?,?,?,?,?,?)',
                       (pid, d, amount, kind, notes, c.user['username'], now_iso()))
    guard_overpay(c, pid, before)
    audit(c.db, c.user['username'], 'adjustment', cur.lastrowid, 'create', None,
          {'kind': kind, 'amount': amount, 'date': d, 'notes': notes})
    return {'summary': balance(c.db, pid), 'id': cur.lastrowid}


@route('DELETE', r'/api/adjustments/(\d+)', perm='finance_edit')
def adjustment_delete(c, aid):
    r = c.db.execute('SELECT * FROM adjustments WHERE id=? AND deleted=0', (aid,)).fetchone()
    if not r:
        raise ApiError('التعديل غير موجود', 404, 'not_found')
    before = balance(c.db, r['patient_id'])
    c.db.execute('UPDATE adjustments SET deleted=1 WHERE id=?', (aid,))
    guard_overpay(c, r['patient_id'], before)
    audit(c.db, c.user['username'], 'adjustment', aid, 'delete', dict(r), None, c.body.get('reason'))
    return {'summary': balance(c.db, r['patient_id'])}


# ============ المواعيد ============
def clean_appt(c, b):
    pid = b.get('patient_id')
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        raise ApiError('اختر المراجع')
    get_patient(c.db, pid)
    return {
        'patient_id': pid,
        'appt_date': v_date(b, 'appt_date', 'تاريخ الموعد'),
        'appt_time': v_time(b, 'appt_time', 'وقت الموعد', required=True),
        'reason': v_text(b, 'reason', 'سبب الموعد', maxlen=300) or None,
        'status': v_choice(b, 'status', 'حالة الموعد', APPT_STATUS, 'confirmed'),
        'notes': v_text(b, 'notes', 'الملاحظات', maxlen=1000) or None,
    }


@route('GET', '/api/appointments', perm='appointments', tx=False)
def appts_list(c):
    a = v_date(c.q, 'from', 'من تاريخ', required=False)
    b = v_date(c.q, 'to', 'إلى تاريخ', required=False)
    sql = ("SELECT a.*, p.full_name, p.file_no, p.phone FROM appointments a JOIN patients p ON p.id=a.patient_id "
           "WHERE a.deleted=0")
    args = []
    if a:
        sql += ' AND a.appt_date>=?'
        args.append(a)
    if b:
        sql += ' AND a.appt_date<=?'
        args.append(b)
    if c.q.get('status'):
        sql += ' AND a.status=?'
        args.append(c.q['status'])
    if c.q.get('patient_id'):
        sql += ' AND a.patient_id=?'
        args.append(int(c.q['patient_id']))
    sql += ' ORDER BY a.appt_date, a.appt_time LIMIT 1000'
    return {'appointments': [dict(r) for r in c.db.execute(sql, args)]}


@route('POST', '/api/appointments', perm='appointments')
def appt_create(c):
    f = clean_appt(c, c.body)
    now = now_iso()
    cur = c.db.execute('INSERT INTO appointments(patient_id,appt_date,appt_time,reason,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                       (f['patient_id'], f['appt_date'], f['appt_time'], f['reason'], f['status'], f['notes'], now, now))
    audit(c.db, c.user['username'], 'appointment', cur.lastrowid, 'create', None, f)
    return {'id': cur.lastrowid}


@route('PUT', r'/api/appointments/(\d+)', perm='appointments')
def appt_update(c, aid):
    old = c.db.execute('SELECT * FROM appointments WHERE id=? AND deleted=0', (aid,)).fetchone()
    if not old:
        raise ApiError('الموعد غير موجود', 404, 'not_found')
    b = dict(old)
    b.update(c.body)
    f = clean_appt(c, b)
    c.db.execute('UPDATE appointments SET patient_id=?,appt_date=?,appt_time=?,reason=?,status=?,notes=?,updated_at=? WHERE id=?',
                 (f['patient_id'], f['appt_date'], f['appt_time'], f['reason'], f['status'], f['notes'], now_iso(), aid))
    audit(c.db, c.user['username'], 'appointment', aid, 'update', dict(old), f)
    return {'ok': True}


@route('DELETE', r'/api/appointments/(\d+)', perm='appointments')
def appt_delete(c, aid):
    r = c.db.execute('SELECT * FROM appointments WHERE id=? AND deleted=0', (aid,)).fetchone()
    if not r:
        raise ApiError('الموعد غير موجود', 404, 'not_found')
    c.db.execute('UPDATE appointments SET deleted=1, updated_at=? WHERE id=?', (now_iso(), aid))
    audit(c.db, c.user['username'], 'appointment', aid, 'delete', dict(r))
    return {'ok': True}


# ============ المصروفات ============
def clean_expense(b):
    return {
        'exp_date': v_date(b, 'exp_date', 'تاريخ المصروف', allow_future=False),
        'category': v_choice(b, 'category', 'التصنيف', EXPENSE_CATS),
        'amount': v_money(b, 'amount', 'المبلغ'),
        'description': v_text(b, 'description', 'الوصف', maxlen=300) or None,
        'method': v_choice(b, 'method', 'طريقة الدفع', PAY_METHODS, 'cash'),
        'notes': v_text(b, 'notes', 'الملاحظات', maxlen=1000) or None,
    }


@route('GET', '/api/expenses', perm='expenses', tx=False)
def expenses_list(c):
    a = v_date(c.q, 'from', 'من تاريخ', required=False)
    b = v_date(c.q, 'to', 'إلى تاريخ', required=False)
    sql, args = 'SELECT * FROM expenses WHERE deleted=0', []
    if a:
        sql += ' AND exp_date>=?'
        args.append(a)
    if b:
        sql += ' AND exp_date<=?'
        args.append(b)
    if c.q.get('category'):
        sql += ' AND category=?'
        args.append(c.q['category'])
    rows = [dict(r) for r in c.db.execute(sql + ' ORDER BY exp_date DESC, id DESC LIMIT 2000', args)]
    return {'expenses': rows, 'total': sum(r['amount'] for r in rows)}


@route('POST', '/api/expenses', perm='expenses')
def expense_create(c):
    f = clean_expense(c.body)
    cur = c.db.execute('INSERT INTO expenses(exp_date,category,amount,description,method,notes,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',
                       (f['exp_date'], f['category'], f['amount'], f['description'], f['method'], f['notes'], c.user['username'], now_iso()))
    audit(c.db, c.user['username'], 'expense', cur.lastrowid, 'create', None, f)
    return {'id': cur.lastrowid}


@route('PUT', r'/api/expenses/(\d+)', perm='expenses')
def expense_update(c, eid):
    old = c.db.execute('SELECT * FROM expenses WHERE id=? AND deleted=0', (eid,)).fetchone()
    if not old:
        raise ApiError('المصروف غير موجود', 404, 'not_found')
    f = clean_expense(c.body)
    c.db.execute('UPDATE expenses SET exp_date=?,category=?,amount=?,description=?,method=?,notes=? WHERE id=?',
                 (f['exp_date'], f['category'], f['amount'], f['description'], f['method'], f['notes'], eid))
    audit(c.db, c.user['username'], 'expense', eid, 'update', dict(old), f)
    return {'ok': True}


@route('DELETE', r'/api/expenses/(\d+)', perm='expenses')
def expense_delete(c, eid):
    old = c.db.execute('SELECT * FROM expenses WHERE id=? AND deleted=0', (eid,)).fetchone()
    if not old:
        raise ApiError('المصروف غير موجود', 404, 'not_found')
    c.db.execute('UPDATE expenses SET deleted=1 WHERE id=?', (eid,))
    audit(c.db, c.user['username'], 'expense', eid, 'delete', dict(old), None, c.body.get('reason'))
    return {'ok': True}
