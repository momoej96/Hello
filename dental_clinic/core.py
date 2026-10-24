# -*- coding: utf-8 -*-
"""نواة النظام: قاعدة البيانات، التحقق من المدخلات، الحسابات المالية، التدقيق."""
import os, re, json, sqlite3, hashlib, secrets
from datetime import datetime, date

SCHEMA_VERSION = 1


class ApiError(Exception):
    def __init__(self, message, status=400, code='error', extra=None):
        super().__init__(message)
        self.message, self.status, self.code, self.extra = message, status, code, extra or {}


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT,
  role TEXT NOT NULL CHECK(role IN ('admin','reception','doctor')),
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS patients(
  id INTEGER PRIMARY KEY, file_no INTEGER UNIQUE NOT NULL,
  full_name TEXT NOT NULL, name_norm TEXT NOT NULL, phone TEXT, phone_norm TEXT,
  birth_date TEXT, age INTEGER, gender TEXT CHECK(gender IN ('M','F') OR gender IS NULL),
  first_visit_date TEXT, notes TEXT, deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS visits(
  id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id),
  visit_date TEXT NOT NULL, visit_time TEXT, doctor TEXT, notes TEXT,
  next_appointment TEXT, next_time TEXT, deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS procedures(
  id INTEGER PRIMARY KEY, visit_id INTEGER NOT NULL REFERENCES visits(id),
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  name TEXT NOT NULL, tooth_no TEXT, details TEXT,
  status TEXT NOT NULL CHECK(status IN ('planned','in_progress','completed','cancelled')),
  cost INTEGER NOT NULL DEFAULT 0 CHECK(cost>=0), doctor TEXT,
  deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id),
  visit_id INTEGER REFERENCES visits(id), pay_date TEXT NOT NULL,
  amount INTEGER NOT NULL CHECK(amount>0),
  kind TEXT NOT NULL CHECK(kind IN ('payment','refund')),
  method TEXT NOT NULL CHECK(method IN ('cash','transfer','other')),
  notes TEXT, idem_key TEXT UNIQUE, deleted INTEGER NOT NULL DEFAULT 0,
  void_reason TEXT, created_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS adjustments(
  id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id),
  adj_date TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
  kind TEXT NOT NULL CHECK(kind IN ('discount','debit')), notes TEXT,
  deleted INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS expenses(
  id INTEGER PRIMARY KEY, exp_date TEXT NOT NULL, category TEXT NOT NULL,
  amount INTEGER NOT NULL CHECK(amount>0), description TEXT,
  method TEXT NOT NULL CHECK(method IN ('cash','transfer','other')), notes TEXT,
  deleted INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS appointments(
  id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id),
  appt_date TEXT NOT NULL, appt_time TEXT, reason TEXT,
  status TEXT NOT NULL CHECK(status IN ('confirmed','completed','cancelled','no_show')),
  notes TEXT, source_visit_id INTEGER, deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user TEXT, entity TEXT, entity_id INTEGER,
  action TEXT, old_json TEXT, new_json TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS import_batches(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, filename TEXT, user TEXT, rows_imported INTEGER DEFAULT 0,
  patients_new INTEGER DEFAULT 0, summary_json TEXT, backup_name TEXT);
CREATE TABLE IF NOT EXISTS import_rows(fingerprint TEXT PRIMARY KEY, batch_id INTEGER);
CREATE INDEX IF NOT EXISTS ix_pat_name ON patients(name_norm);
CREATE INDEX IF NOT EXISTS ix_pat_phone ON patients(phone_norm);
CREATE INDEX IF NOT EXISTS ix_vis_pat ON visits(patient_id, visit_date);
CREATE INDEX IF NOT EXISTS ix_vis_date ON visits(visit_date);
CREATE INDEX IF NOT EXISTS ix_proc_visit ON procedures(visit_id);
CREATE INDEX IF NOT EXISTS ix_proc_pat ON procedures(patient_id);
CREATE INDEX IF NOT EXISTS ix_pay_pat ON payments(patient_id);
CREATE INDEX IF NOT EXISTS ix_pay_date ON payments(pay_date);
CREATE INDEX IF NOT EXISTS ix_exp_date ON expenses(exp_date);
CREATE INDEX IF NOT EXISTS ix_app_date ON appointments(appt_date);
CREATE INDEX IF NOT EXISTS ix_aud_ent ON audit_log(entity, entity_id);
DROP VIEW IF EXISTS v_balances;
CREATE VIEW v_balances AS
SELECT p.id AS patient_id,
 COALESCE((SELECT SUM(cost) FROM procedures x WHERE x.patient_id=p.id AND x.deleted=0 AND x.status IN ('in_progress','completed')),0) AS total_cost,
 COALESCE((SELECT SUM(cost) FROM procedures x WHERE x.patient_id=p.id AND x.deleted=0 AND x.status='planned'),0) AS planned_cost,
 COALESCE((SELECT SUM(amount) FROM adjustments a WHERE a.patient_id=p.id AND a.deleted=0 AND a.kind='discount'),0) AS discounts,
 COALESCE((SELECT SUM(amount) FROM adjustments a WHERE a.patient_id=p.id AND a.deleted=0 AND a.kind='debit'),0) AS debits,
 COALESCE((SELECT SUM(amount) FROM payments y WHERE y.patient_id=p.id AND y.deleted=0 AND y.kind='payment'),0) AS paid,
 COALESCE((SELECT SUM(amount) FROM payments y WHERE y.patient_id=p.id AND y.deleted=0 AND y.kind='refund'),0) AS refunded
FROM patients p;
"""

DEFAULT_SETTINGS = {
    'clinic_name': 'عيادة الأسنان', 'clinic_phone': '', 'clinic_address': '',
    'currency_code': 'IQD', 'currency_label': 'دينار عراقي', 'currency_symbol': 'د.ع',
    'idle_minutes': '15', 'doctors': '[]', 'receipt_footer': 'شكراً لزيارتكم',
    'money_thousands': '1',
    'xray_folder': r'C:\ai-dental-images\patients',   # مجلد حفظ الصور في برنامج السنسر (Image Path في Woodpecker)   # إدخال المبالغ بالألف في الواجهة: 25 تعني 25,000 (التخزين دائماً بالمبلغ الكامل)
}
PUBLIC_SETTING_KEYS = list(DEFAULT_SETTINGS.keys())

PROC_STATUS = ('planned', 'in_progress', 'completed', 'cancelled')
RC_STEPS = ('access', 'obturation', 'buildup')   # Access / Instrumentation + Obturation / Build up
APPT_STATUS = ('confirmed', 'completed', 'cancelled', 'no_show')
PAY_METHODS = ('cash', 'transfer', 'other')
EXPENSE_CATS = ['مواد طب الأسنان', 'أجور المختبر', 'الإيجار', 'الرواتب',
                'الكهرباء والإنترنت', 'صيانة الأجهزة', 'مصروفات أخرى']
FDI = {q * 10 + t for q in (1, 2, 3, 4) for t in range(1, 9)} | \
      {q * 10 + t for q in (5, 6, 7, 8) for t in range(1, 6)}


def connect(path):
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    return db


def init_db(path):
    db = connect(path)
    try:
        db.executescript(SCHEMA)
        migrate(db)
        db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        for k, v in DEFAULT_SETTINGS.items():
            db.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, v))
    finally:
        db.close()


def migrate(db):
    """ترقية قواعد البيانات القديمة بإضافة الأعمدة الجديدة دون المساس بالبيانات."""
    cols = {r['name'] for r in db.execute('PRAGMA table_info(patients)')}
    if 'doctor' not in cols:   # الطبيب المعالج للمراجع
        db.execute('ALTER TABLE patients ADD COLUMN doctor TEXT')
    db.execute('''CREATE TABLE IF NOT EXISTS xrays(
        id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id), visit_id INTEGER REFERENCES visits(id),
        taken_at TEXT NOT NULL, file_name TEXT NOT NULL, source TEXT, original_path TEXT, tooth_no TEXT, notes TEXT,
        size INTEGER, deleted INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS ix_xray_pat ON xrays(patient_id, taken_at)')
    # أسماء قديمة لمراجعين دُمجت ملفاتهم، حتى يتعرف عليها الاستيراد من Excel لاحقاً
    db.execute('CREATE TABLE IF NOT EXISTS patient_aliases(name_key TEXT PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id))')
    cols = {r['name'] for r in db.execute('PRAGMA table_info(procedures)')}
    if 'lab' not in cols:        # المختبر الذي عُمل عنده التاج/الجسر/التقويم
        db.execute('ALTER TABLE procedures ADD COLUMN lab TEXT')
    if 'rc_steps' not in cols:   # مراحل حشوة الجذر (access,obturation,buildup) وقياسات الجذور
        db.execute('ALTER TABLE procedures ADD COLUMN rc_steps TEXT')
        db.execute('ALTER TABLE procedures ADD COLUMN rc_measure TEXT')
    cols = {r['name'] for r in db.execute('PRAGMA table_info(payments)')}
    if 'doctor' not in cols:   # الطبيب الذي تُنسب له الدفعة (من شيت الطبيب عند الاستيراد)
        db.execute('ALTER TABLE payments ADD COLUMN doctor TEXT')


def get_settings(db):
    d = dict(DEFAULT_SETTINGS)
    for r in db.execute('SELECT key,value FROM settings'):
        d[r['key']] = r['value']
    return d


# ---------- أدوات النصوص العربية ----------
AR_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def norm_ar(s):
    s = (s or '').translate(AR_DIGITS)
    s = re.sub('[\u064B-\u065F\u0670\u0640]', '', s)
    s = re.sub('[أإآٱ]', 'ا', s)
    s = s.replace('ى', 'ي').replace('ة', 'ه').replace('ؤ', 'و').replace('ئ', 'ي')
    return re.sub(r'\s+', ' ', s).strip().lower()


def canon_phone(s):
    d = re.sub(r'\D', '', (s or '').translate(AR_DIGITS))
    if d.startswith('00'):
        d = d[2:]
    if d.startswith('964'):
        d = d[3:]
    return d.lstrip('0')


def esc_like(s):
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def now_iso():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def today_iso():
    return date.today().isoformat()


# ---------- التحقق من المدخلات ----------
def v_text(b, key, label, required=False, maxlen=300):
    v = b.get(key)
    if v is None:
        v = ''
    if not isinstance(v, (str, int, float)) or isinstance(v, bool):
        raise ApiError('قيمة غير صحيحة: ' + label)
    v = str(v).strip()
    if required and not v:
        raise ApiError('الحقل مطلوب: ' + label)
    if len(v) > maxlen:
        raise ApiError('النص طويل جداً: ' + label)
    return v


def v_date(b, key, label, required=True, allow_future=True):
    v = b.get(key)
    v = v.strip() if isinstance(v, str) else v
    if not v:
        if required:
            raise ApiError('الحقل مطلوب: ' + label)
        return None
    try:
        d = datetime.strptime(str(v), '%Y-%m-%d').date()
    except ValueError:
        raise ApiError('تاريخ غير صحيح: ' + label)
    if d.year < 2000 or d.year > 2100:
        raise ApiError('تاريخ خارج النطاق المسموح: ' + label)
    if not allow_future and d > date.today():
        raise ApiError('لا يمكن أن يكون التاريخ في المستقبل: ' + label)
    return d.isoformat()


def v_time(b, key, label, required=False):
    v = b.get(key)
    v = v.strip() if isinstance(v, str) else v
    if not v:
        if required:
            raise ApiError('الحقل مطلوب: ' + label)
        return None
    if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', str(v)):
        raise ApiError('وقت غير صحيح: ' + label)
    return str(v)


def v_money(b, key, label, required=True, allow_zero=False):
    v = b.get(key)
    if isinstance(v, str):
        v = v.translate(AR_DIGITS).replace(',', '').replace('٬', '').replace(' ', '').strip()
    if v is None or v == '':
        if required:
            raise ApiError('الحقل مطلوب: ' + label)
        return None
    if isinstance(v, bool):
        raise ApiError('مبلغ غير صحيح: ' + label)
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ApiError('مبلغ غير صحيح: ' + label)
    if f != int(f):
        raise ApiError('يجب أن يكون المبلغ رقماً صحيحاً بدون كسور: ' + label)
    n = int(f)
    if n < 0 or (n == 0 and not allow_zero):
        raise ApiError('يجب أن يكون المبلغ أكبر من صفر: ' + label)
    if n > 10 ** 12:
        raise ApiError('المبلغ كبير جداً: ' + label)
    return n


def v_choice(b, key, label, choices, default=None):
    v = b.get(key)
    if v in (None, ''):
        if default is not None:
            return default
        raise ApiError('الحقل مطلوب: ' + label)
    if v not in choices:
        raise ApiError('قيمة غير مسموحة: ' + label)
    return v


def v_tooth(v):
    """سن واحد أو عدة أسنان لنفس الإجراء (مثل «11، 21» أو قائمة). تُحفظ مفصولة بفواصل: «11,21»."""
    if v in (None, '') or v == []:
        return None
    if not isinstance(v, list) and re.search(r'[a-zA-Z]', str(v)):
        from importer import parse_teeth          # نظام Palmer: UR6، ul1، LLE، u11 …
        parts, bad = parse_teeth(str(v))
        if bad or not parts:
            raise ApiError('رقم السن غير مفهوم (اكتب بنظام Palmer مثل UR6 أو LL7): ' + str(v))
        v = [str(t) for t in parts]
    parts = v if isinstance(v, list) else re.split(r'[\s,،؛;+/\-]+', str(v).translate(AR_DIGITS))
    teeth = []
    for t in parts:
        t = str(t).translate(AR_DIGITS).strip()
        if not t:
            continue
        if not t.isdigit() or int(t) not in FDI:
            raise ApiError('رقم السن غير صحيح (نظام FDI): ' + t)
        if t not in teeth:
            teeth.append(t)
    if len(teeth) > 32:
        raise ApiError('عدد الأسنان كبير جداً لإجراء واحد')
    return ','.join(teeth) or None


# ---------- الحسابات المالية ----------
def balance(db, pid):
    r = db.execute('SELECT * FROM v_balances WHERE patient_id=?', (pid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d['net_paid'] = d['paid'] - d['refunded']
    # المتبقي = التكاليف − الخصومات + التعديلات المدينة − (الدفعات − المبالغ المستردة)
    d['remaining'] = d['total_cost'] - d['discounts'] + d['debits'] - d['net_paid']
    return d


def audit(db, user, entity, eid, action, old=None, new=None, note=None):
    j = lambda x: None if x is None else json.dumps(x, ensure_ascii=False, default=str)
    db.execute('INSERT INTO audit_log(ts,user,entity,entity_id,action,old_json,new_json,note) VALUES(?,?,?,?,?,?,?,?)',
               (now_iso(), user, entity, eid, action, j(old), j(new), note))


# ---------- كلمات المرور ----------
def hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 200_000).hex()
    return h, salt


def check_password_strength(pw):
    if not isinstance(pw, str) or len(pw) < 8:
        raise ApiError('كلمة المرور يجب ألا تقل عن 8 أحرف')
