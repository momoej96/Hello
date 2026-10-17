# -*- coding: utf-8 -*-
"""التقارير المالية ولوحة التحكم والبحث حسب التاريخ. كل الأرقام تُحسب من قاعدة البيانات."""
from datetime import date, timedelta
import calendar
from core import *
from api import route, can, search_cond, balance


def _scalar(db, sql, args=()):
    return db.execute(sql, args).fetchone()[0] or 0


def period_stats(db, a, b):
    s = {'from': a, 'to': b}
    s['receipts'] = _scalar(db, "SELECT SUM(amount) FROM payments WHERE deleted=0 AND kind='payment' AND pay_date BETWEEN ? AND ?", (a, b))
    s['payments_count'] = _scalar(db, "SELECT COUNT(*) FROM payments WHERE deleted=0 AND kind='payment' AND pay_date BETWEEN ? AND ?", (a, b))
    s['refunds'] = _scalar(db, "SELECT SUM(amount) FROM payments WHERE deleted=0 AND kind='refund' AND pay_date BETWEEN ? AND ?", (a, b))
    by = {m: {'total': 0, 'count': 0} for m in PAY_METHODS}
    for r in db.execute("SELECT method, SUM(amount) t, COUNT(*) n FROM payments WHERE deleted=0 AND kind='payment' AND pay_date BETWEEN ? AND ? GROUP BY method", (a, b)):
        by[r['method']] = {'total': r['t'], 'count': r['n']}
    s['receipts_by_method'] = by
    r = db.execute("SELECT COUNT(*) n, COUNT(DISTINCT patient_id) d FROM visits WHERE deleted=0 AND visit_date BETWEEN ? AND ?", (a, b)).fetchone()
    s['visits_count'], s['visitors_count'] = r['n'], r['d']
    base = "SELECT COALESCE(SUM(p.cost),0) FROM procedures p JOIN visits v ON v.id=p.visit_id WHERE p.deleted=0 AND v.deleted=0 AND v.visit_date BETWEEN ? AND ?"
    s['executed_value'] = _scalar(db, base + " AND p.status='completed'", (a, b))
    s['agreed_value'] = _scalar(db, base + " AND p.status!='cancelled'", (a, b))
    s['discounts'] = _scalar(db, "SELECT SUM(amount) FROM adjustments WHERE deleted=0 AND kind='discount' AND adj_date BETWEEN ? AND ?", (a, b))
    s['debit_adjustments'] = _scalar(db, "SELECT SUM(amount) FROM adjustments WHERE deleted=0 AND kind='debit' AND adj_date BETWEEN ? AND ?", (a, b))
    s['new_patients'] = _scalar(db, "SELECT COUNT(*) FROM patients WHERE deleted=0 AND first_visit_date BETWEEN ? AND ?", (a, b))
    s['expenses'] = _scalar(db, "SELECT SUM(amount) FROM expenses WHERE deleted=0 AND exp_date BETWEEN ? AND ?", (a, b))
    s['expenses_by_category'] = [dict(r) for r in db.execute(
        "SELECT category, SUM(amount) total, COUNT(*) n FROM expenses WHERE deleted=0 AND exp_date BETWEEN ? AND ? GROUP BY category ORDER BY total DESC", (a, b))]
    s['avg_per_visit'] = round(s['receipts'] / s['visits_count']) if s['visits_count'] else 0
    # صافي التدفق النقدي = المقبوضات الفعلية − المصروفات الفعلية − المبالغ المستردة
    s['net_cash_flow'] = s['receipts'] - s['expenses'] - s['refunds']
    # الربح التقديري: قيمة العلاجات المنفذة − الخصومات + التعديلات المدينة − المصروفات (تقريبي)
    s['estimated_profit'] = s['executed_value'] - s['discounts'] + s['debit_adjustments'] - s['expenses']
    return s


def by_procedure(db, a, b):
    return [dict(r) for r in db.execute(
        "SELECT p.name, COUNT(*) n, SUM(CASE WHEN p.status='completed' THEN p.cost ELSE 0 END) executed, SUM(p.cost) agreed "
        "FROM procedures p JOIN visits v ON v.id=p.visit_id WHERE p.deleted=0 AND v.deleted=0 AND p.status!='cancelled' "
        "AND v.visit_date BETWEEN ? AND ? GROUP BY p.name ORDER BY executed DESC, agreed DESC", (a, b))]


NO_DOCTOR = 'غير محدد'


def settings_doctors(db):
    try:
        return [d for d in json.loads(get_settings(db).get('doctors') or '[]') if isinstance(d, str) and d.strip()]
    except ValueError:
        return []


class DoctorNames:
    """يوحّد كتابات اسم الطبيب مع أسماء الأطباء في الإعدادات («د. مرتضى» و«د مرتضى حميد عجرش» = طبيب واحد)."""
    def __init__(self, db):
        from importer import doctor_core
        self.core = lambda n: doctor_core(n).replace(' ', '')
        self.doctors = settings_doctors(db)
        self.cache = {}

    def __call__(self, name):
        name = (name or '').strip()
        if not name:
            return NO_DOCTOR
        if name not in self.cache:
            c = self.core(name)
            hit = [d for d in self.doctors if self.core(d) == c]
            if not hit and c:
                hit = [d for d in self.doctors if self.core(d) and (self.core(d) in c or c in self.core(d))]
            self.cache[name] = hit[0] if len(hit) == 1 else name
        return self.cache[name]

    def order(self, name):
        """ترتيب ثابت: أطباء الإعدادات بترتيبهم، ثم غيرهم، ثم «غير محدد»."""
        if name in self.doctors:
            return (0, self.doctors.index(name), '')
        return (2, 0, '') if name == NO_DOCTOR else (1, 0, name)


# الطبيب الفعلي: المسجل على السجل نفسه، وإلا الطبيب المعالج للمراجع. «» صريح (شيت مشترك) = غير محدد
PROC_DOC = ("CASE WHEN x.doctor IS NOT NULL THEN NULLIF(TRIM(x.doctor),'') "
            "ELSE COALESCE(NULLIF(TRIM(v.doctor),''), NULLIF(TRIM(pt.doctor),'')) END")
VISIT_DOC = "CASE WHEN v.doctor IS NOT NULL THEN NULLIF(TRIM(v.doctor),'') ELSE NULLIF(TRIM(pt.doctor),'') END"
PAY_DOC = ("CASE WHEN y.doctor IS NOT NULL THEN NULLIF(TRIM(y.doctor),'') "
           "ELSE COALESCE(NULLIF(TRIM(v.doctor),''), NULLIF(TRIM(pt.doctor),'')) END")


def receipts_by_doctor(db, a, b, names=None):
    names = names or DoctorNames(db)
    out = {}
    for r in db.execute("SELECT " + PAY_DOC + " AS doc, SUM(y.amount) t FROM payments y JOIN patients pt ON pt.id=y.patient_id "
                        "LEFT JOIN visits v ON v.id=y.visit_id AND v.deleted=0 "
                        "WHERE y.deleted=0 AND y.kind='payment' AND y.pay_date BETWEEN ? AND ? GROUP BY doc", (a, b)):
        k = names(r['doc'])
        out[k] = out.get(k, 0) + (r['t'] or 0)
    return out


def by_doctor(db, a, b):
    """عمل كل طبيب في الفترة: الإجراء يُنسب لطبيبه، ثم طبيب الزيارة، ثم الطبيب المعالج للمراجع.
    المقبوض يُنسب لطبيب الدفعة، ثم طبيب الزيارة المرتبطة بها، ثم الطبيب المعالج للمراجع.
    الطبيب الفارغ صراحةً («» من شيت مشترك عند الاستيراد) يبقى «غير محدد» ولا يُنسب لطبيب المراجع.
    كتابات اسم الطبيب المختلفة تُجمع تحت اسمه في الإعدادات."""
    names = DoctorNames(db)
    out = {}
    def row(name):
        return out.setdefault(name, {'doctor': name, 'patients': set(), 'visits': set(), 'procedures': 0, 'executed': 0, 'agreed': 0, 'receipts': 0})
    for r in db.execute(
            "SELECT " + PROC_DOC + " AS doc, v.patient_id pid, v.id vid, COUNT(x.id) nx, "
            "COALESCE(SUM(CASE WHEN x.status='completed' THEN x.cost END),0) executed, COALESCE(SUM(x.cost),0) agreed "
            "FROM procedures x JOIN visits v ON v.id=x.visit_id JOIN patients pt ON pt.id=v.patient_id "
            "WHERE x.deleted=0 AND v.deleted=0 AND x.status!='cancelled' AND v.visit_date BETWEEN ? AND ? GROUP BY doc, v.id", (a, b)):
        d = row(names(r['doc']))
        d['patients'].add(r['pid']); d['visits'].add(r['vid'])
        d['procedures'] += r['nx']; d['executed'] += r['executed']; d['agreed'] += r['agreed']
    for k, t in receipts_by_doctor(db, a, b, names).items():
        row(k)['receipts'] = t
    rows = [{**d, 'patients': len(d['patients']), 'visits': len(d['visits'])} for d in out.values()]
    rows.sort(key=lambda d: (d['doctor'] == NO_DOCTOR, -d['executed'], -d['agreed'], -d['receipts']))
    total = sum(d['executed'] for d in rows)
    for d in rows:
        d['share'] = round(100 * d['executed'] / total, 1) if total else 0
    return rows


def daily_table(db, a, b):
    d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    if (d1 - d0).days > 400:
        return []
    def grp(sql):
        return {r[0]: r for r in db.execute(sql, (a, b))}
    rec = grp("SELECT pay_date, SUM(amount), COUNT(*) FROM payments WHERE deleted=0 AND kind='payment' AND pay_date BETWEEN ? AND ? GROUP BY pay_date")
    ref = grp("SELECT pay_date, SUM(amount) FROM payments WHERE deleted=0 AND kind='refund' AND pay_date BETWEEN ? AND ? GROUP BY pay_date")
    exp = grp("SELECT exp_date, SUM(amount) FROM expenses WHERE deleted=0 AND exp_date BETWEEN ? AND ? GROUP BY exp_date")
    vis = grp("SELECT visit_date, COUNT(*) FROM visits WHERE deleted=0 AND visit_date BETWEEN ? AND ? GROUP BY visit_date")
    out, d = [], d0
    while d <= d1:
        k = d.isoformat()
        r = rec.get(k)
        e = exp.get(k)
        f = ref.get(k)
        receipts = r[1] if r else 0
        out.append({'date': k, 'receipts': receipts, 'payments_count': r[2] if r else 0,
                    'refunds': f[1] if f else 0, 'expenses': e[1] if e else 0,
                    'visits': vis[k][1] if k in vis else 0,
                    'net_cash_flow': receipts - (e[1] if e else 0) - (f[1] if f else 0)})
        d += timedelta(days=1)
    return out


def _range(c, need_both=True):
    a = v_date(c.q, 'from', 'من تاريخ')
    b = v_date(c.q, 'to', 'إلى تاريخ')
    if a > b:
        raise ApiError('تاريخ البداية بعد تاريخ النهاية')
    if (date.fromisoformat(b) - date.fromisoformat(a)).days > 3660:
        raise ApiError('الفترة المحددة طويلة جداً')
    return a, b


def visits_in_range(db, a, b, q='', doctor='', money=True):
    """كل زيارات الفترة (بلا حد أقصى). الإجراءات والمقبوض والأرصدة تُقرأ بثلاث استعلامات مجمّعة لا استعلام لكل زيارة."""
    names = DoctorNames(db)
    where = "v.deleted=0 AND v.visit_date BETWEEN ? AND ?"
    args = [a, b]
    cond, ca = search_cond(q)
    if cond:
        where += ' AND ' + cond
        args += ca
    rows = []
    for r in db.execute("SELECT v.*, p.full_name, p.file_no, p.phone, " + VISIT_DOC.replace('pt.', 'p.') + " AS doc FROM visits v "
                        "JOIN patients p ON p.id=v.patient_id WHERE " + where + " ORDER BY v.visit_date DESC, COALESCE(v.visit_time,''), v.id", args):
        v = dict(r)
        v['doctor_eff'] = names(v.pop('doc'))       # الطبيب الفعلي للزيارة (بالاسم الموحد)
        if doctor and v['doctor_eff'] != doctor:
            continue
        v['procedures'] = []
        rows.append(v)
    if not rows:
        return rows
    by_id = {v['id']: v for v in rows}
    for x in db.execute("SELECT x.visit_id, x.name, x.tooth_no, x.status, x.cost FROM procedures x JOIN visits v ON v.id=x.visit_id "
                        "JOIN patients p ON p.id=v.patient_id WHERE x.deleted=0 AND " + where + " ORDER BY x.id", args):
        if x['visit_id'] in by_id:
            by_id[x['visit_id']]['procedures'].append({k: x[k] for k in ('name', 'tooth_no', 'status', 'cost')})
    if money:
        paid = {(r[0], r[1]): r[2] for r in db.execute(
            "SELECT patient_id, pay_date, SUM(amount) FROM payments WHERE deleted=0 AND kind='payment' AND pay_date BETWEEN ? AND ? GROUP BY patient_id, pay_date", (a, b))}
        pids = {v['patient_id'] for v in rows}
        rem = {r[0]: r[1] for r in db.execute("SELECT patient_id, total_cost-discounts+debits-(paid-refunded) FROM v_balances")
               if r[0] in pids} if len(pids) > 200 else {pid: balance(db, pid)['remaining'] for pid in pids}
        seen = set()
        for v in rows:
            v['visit_cost'] = sum(p['cost'] for p in v['procedures'] if p['status'] != 'cancelled')
            key = (v['patient_id'], v['visit_date'])
            v['paid_that_day'] = None if key in seen else paid.get(key, 0)   # لا نكرر المقبوض لزيارتين في نفس اليوم
            seen.add(key)
            v['remaining'] = rem.get(v['patient_id'], 0)
    return rows


def payments_in_range(db, a, b, q='', names=None):
    names = names or DoctorNames(db)
    sql = ("SELECT y.id, y.pay_date, y.amount, y.kind, y.method, y.notes, y.patient_id, p.full_name, p.file_no, "
           + PAY_DOC.replace('pt.', 'p.') + " AS doc FROM payments y "
           "JOIN patients p ON p.id=y.patient_id LEFT JOIN visits v ON v.id=y.visit_id AND v.deleted=0 WHERE y.deleted=0 AND y.pay_date BETWEEN ? AND ?")
    args = [a, b]
    cond, ca = search_cond(q)
    if cond:
        sql += ' AND ' + cond
        args += ca
    out = []
    for r in db.execute(sql + ' ORDER BY y.pay_date DESC, y.id DESC LIMIT 5000', args):
        d = dict(r)
        d['doctor_eff'] = names(d.pop('doc'))
        out.append(d)
    return out


@route('GET', '/api/visits_by_date', perm='visits', tx=False)
def visits_by_date(c):
    a, b = _range(c)
    money = can(c.user, 'payments')
    names = DoctorNames(c.db)
    doctor = (c.q.get('doctor') or '').strip()
    out = {'visits': visits_in_range(c.db, a, b, c.q.get('q', ''), doctor, money), 'doctors': names.doctors + [NO_DOCTOR]}
    # مراجعو كل طبيب في مجموعة منفصلة، بترتيب ثابت (أطباء الإعدادات بترتيبهم)، وتحت كل مجموعة ما قُبض له
    groups = {}
    def grp(k):
        return groups.setdefault(k, {'doctor': k, 'visits': 0, 'patients': set(), 'cost': 0, 'receipts': 0})
    for v in out['visits']:
        g = grp(v['doctor_eff'])
        g['visits'] += 1; g['patients'].add(v['patient_id']); g['cost'] += v.get('visit_cost') or 0
    if money:
        pays = payments_in_range(c.db, a, b, c.q.get('q', ''), names)
        if doctor:
            pays = [p for p in pays if p['doctor_eff'] == doctor]
        out['payments'] = pays
        out['receipts_total'] = sum(p['amount'] for p in pays if p['kind'] == 'payment')
        for p in pays:
            if p['kind'] == 'payment':
                grp(p['doctor_eff'])['receipts'] += p['amount']
    out['groups'] = [{**g, 'patients': len(g['patients'])} for g in sorted(groups.values(), key=lambda g: names.order(g['doctor']))]
    if not money:
        for g in out['groups']:
            g.pop('cost'); g.pop('receipts')
    return out


@route('GET', '/api/dashboard', perm='patients', tx=False)
def dashboard(c):
    today = v_date(c.q, 'today', 'اليوم', required=False) or today_iso()
    y, m = today[:4], today[:7]
    db = c.db
    out = {'today': today, 'patients_count': _scalar(db, 'SELECT COUNT(*) FROM patients WHERE deleted=0'),
           'visits_today': _scalar(db, 'SELECT COUNT(*) FROM visits WHERE deleted=0 AND visit_date=?', (today,))}
    if can(c.user, 'payments'):
        rc = lambda a, b: _scalar(db, "SELECT SUM(amount) FROM payments WHERE deleted=0 AND kind='payment' AND pay_date BETWEEN ? AND ?", (a, b))
        last = calendar.monthrange(int(y), int(today[5:7]))[1]
        out['receipts_today'] = rc(today, today)
        out['receipts_month'] = rc(m + '-01', '%s-%02d' % (m, last))
        out['receipts_year'] = rc(y + '-01-01', y + '-12-31')
        rem = db.execute("SELECT COALESCE(SUM(MAX(rem,0)),0), SUM(CASE WHEN rem>0 THEN 1 ELSE 0 END) FROM "
                         "(SELECT b.total_cost-b.discounts+b.debits-(b.paid-b.refunded) AS rem FROM v_balances b JOIN patients p ON p.id=b.patient_id WHERE p.deleted=0)").fetchone()
        out['total_dues'] = rem[0] or 0
        out['debtors_count'] = rem[1] or 0
    out['appointments_today'] = [dict(r) for r in db.execute(
        "SELECT a.*, p.full_name, p.file_no FROM appointments a JOIN patients p ON p.id=a.patient_id "
        "WHERE a.deleted=0 AND a.appt_date=? ORDER BY a.appt_time", (today,))]
    return out


@route('GET', '/api/reports/daily', perm='reports_basic', tx=False)
def report_daily(c):
    d = v_date(c.q, 'date', 'التاريخ')
    s = period_stats(c.db, d, d)
    return {'stats': s, 'payments': payments_in_range(c.db, d, d),
            'visits': visits_in_range(c.db, d, d), 'by_doctor': by_doctor(c.db, d, d),
            'expenses': [dict(r) for r in c.db.execute('SELECT * FROM expenses WHERE deleted=0 AND exp_date=? ORDER BY id', (d,))] if can(c.user, 'expenses') else []}


@route('GET', '/api/reports/period', perm='reports_full', tx=False)
def report_period(c):
    a, b = _range(c)
    return {'stats': period_stats(c.db, a, b), 'daily': daily_table(c.db, a, b), 'by_procedure': by_procedure(c.db, a, b),
            'by_doctor': by_doctor(c.db, a, b)}


@route('GET', '/api/reports/yearly', perm='reports_full', tx=False)
def report_yearly(c):
    def year_block(y):
        months = []
        for m in range(1, 13):
            a = '%04d-%02d-01' % (y, m)
            b = '%04d-%02d-%02d' % (y, m, calendar.monthrange(y, m)[1])
            s = period_stats(c.db, a, b)
            months.append({'month': m, 'receipts': s['receipts'], 'executed_value': s['executed_value'],
                           'agreed_value': s['agreed_value'], 'visits_count': s['visits_count'],
                           'new_patients': s['new_patients'], 'discounts': s['discounts'], 'refunds': s['refunds'],
                           'expenses': s['expenses'], 'net_cash_flow': s['net_cash_flow']})
        return {'year': y, 'stats': period_stats(c.db, '%04d-01-01' % y, '%04d-12-31' % y), 'months': months,
                'by_procedure': by_procedure(c.db, '%04d-01-01' % y, '%04d-12-31' % y),
                'by_doctor': by_doctor(c.db, '%04d-01-01' % y, '%04d-12-31' % y)}
    try:
        y = int(c.q.get('year'))
        cy = int(c.q['compare']) if c.q.get('compare') else None
    except (TypeError, ValueError):
        raise ApiError('سنة غير صحيحة')
    if not (2000 <= y <= 2100) or (cy and not 2000 <= cy <= 2100):
        raise ApiError('سنة خارج النطاق')
    out = year_block(y)
    out['compare'] = year_block(cy) if cy else None
    return out


def _balances_sql(extra_where=''):
    return ("SELECT p.id, p.file_no, p.full_name, p.phone, b.total_cost, b.planned_cost, b.discounts, b.debits, b.paid, b.refunded, "
            "(b.total_cost-b.discounts+b.debits-(b.paid-b.refunded)) AS remaining, "
            "(SELECT MAX(pay_date) FROM payments y WHERE y.patient_id=p.id AND y.deleted=0 AND y.kind='payment') AS last_payment, "
            "(SELECT MAX(visit_date) FROM visits v WHERE v.patient_id=p.id AND v.deleted=0) AS last_visit "
            "FROM patients p JOIN v_balances b ON b.patient_id=p.id WHERE p.deleted=0 " + extra_where)


@route('GET', '/api/reports/debtors', perm='reports_basic', tx=False)
def report_debtors(c):
    rows = [dict(r) for r in c.db.execute(_balances_sql() + ' ORDER BY remaining DESC')]
    debtors = [r for r in rows if r['remaining'] > 0]
    credits = [r for r in rows if r['remaining'] < 0]
    return {'debtors': debtors, 'credits': credits, 'total_dues': sum(r['remaining'] for r in debtors),
            'total_credits': -sum(r['remaining'] for r in credits)}


@route('GET', '/api/reports/dues', perm='reports_full', tx=False)
def report_dues(c):
    a, b = _range(c)
    s = period_stats(c.db, a, b)
    rows = []
    for r in c.db.execute(
            "SELECT p.id, p.file_no, p.full_name, "
            "(SELECT COALESCE(SUM(x.cost),0) FROM procedures x JOIN visits v ON v.id=x.visit_id WHERE x.patient_id=p.id AND x.deleted=0 AND v.deleted=0 AND x.status!='cancelled' AND v.visit_date BETWEEN :a AND :b) AS cost_in_period, "
            "(SELECT COALESCE(SUM(amount),0) FROM payments y WHERE y.patient_id=p.id AND y.deleted=0 AND y.kind='payment' AND y.pay_date BETWEEN :a AND :b) AS paid_in_period "
            "FROM patients p WHERE p.deleted=0", {'a': a, 'b': b}):
        if r['cost_in_period'] or r['paid_in_period']:
            d = dict(r)
            d['remaining'] = balance(c.db, r['id'])['remaining']
            rows.append(d)
    rows.sort(key=lambda x: -x['remaining'])
    dues = c.db.execute("SELECT COALESCE(SUM(MAX(rem,0)),0) FROM (SELECT b.total_cost-b.discounts+b.debits-(b.paid-b.refunded) AS rem FROM v_balances b JOIN patients p ON p.id=b.patient_id WHERE p.deleted=0)").fetchone()[0]
    return {'stats': s, 'rows': rows, 'total_outstanding_now': dues}
