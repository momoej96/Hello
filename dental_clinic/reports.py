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


def by_doctor(db, a, b):
    """عمل كل طبيب في الفترة: الإجراء يُنسب لطبيبه، ثم طبيب الزيارة، ثم الطبيب المعالج للمراجع.
    المقبوض يُنسب لطبيب الزيارة المرتبطة بالدفعة، وإلا للطبيب المعالج للمراجع."""
    out = {}
    def row(name):
        return out.setdefault(name or NO_DOCTOR, {'doctor': name or NO_DOCTOR, 'patients': 0, 'visits': 0, 'procedures': 0,
                                                  'executed': 0, 'agreed': 0, 'receipts': 0})
    for r in db.execute(
            "SELECT COALESCE(NULLIF(TRIM(x.doctor),''), NULLIF(TRIM(v.doctor),''), NULLIF(TRIM(pt.doctor),'')) AS doc, "
            "COUNT(DISTINCT v.patient_id) np, COUNT(DISTINCT v.id) nv, COUNT(x.id) nx, "
            "COALESCE(SUM(CASE WHEN x.status='completed' THEN x.cost END),0) executed, COALESCE(SUM(x.cost),0) agreed "
            "FROM procedures x JOIN visits v ON v.id=x.visit_id JOIN patients pt ON pt.id=v.patient_id "
            "WHERE x.deleted=0 AND v.deleted=0 AND x.status!='cancelled' AND v.visit_date BETWEEN ? AND ? GROUP BY doc", (a, b)):
        d = row(r['doc'])
        d.update(patients=r['np'], visits=r['nv'], procedures=r['nx'], executed=r['executed'], agreed=r['agreed'])
    for r in db.execute(
            "SELECT COALESCE(NULLIF(TRIM(v.doctor),''), NULLIF(TRIM(pt.doctor),'')) AS doc, SUM(y.amount) t "
            "FROM payments y JOIN patients pt ON pt.id=y.patient_id LEFT JOIN visits v ON v.id=y.visit_id AND v.deleted=0 "
            "WHERE y.deleted=0 AND y.kind='payment' AND y.pay_date BETWEEN ? AND ? GROUP BY doc", (a, b)):
        row(r['doc'])['receipts'] = r['t'] or 0
    rows = sorted(out.values(), key=lambda d: (d['doctor'] == NO_DOCTOR, -d['executed'], -d['agreed'], -d['receipts']))
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
    sql = ("SELECT v.*, p.full_name, p.file_no, p.phone FROM visits v JOIN patients p ON p.id=v.patient_id "
           "WHERE v.deleted=0 AND v.visit_date BETWEEN ? AND ?")
    args = [a, b]
    cond, ca = search_cond(q)
    if cond:
        sql += ' AND ' + cond
        args += ca
    if doctor:
        sql += ' AND v.doctor=?'
        args.append(doctor)
    sql += ' ORDER BY v.visit_date DESC, COALESCE(v.visit_time,\'\'), v.id LIMIT 2000'
    rows, seen, bal_cache = [], set(), {}
    for r in db.execute(sql, args):
        v = dict(r)
        v['procedures'] = [dict(x) for x in db.execute('SELECT name,tooth_no,status,cost FROM procedures WHERE visit_id=? AND deleted=0 ORDER BY id', (v['id'],))]
        if money:
            v['visit_cost'] = sum(p['cost'] for p in v['procedures'] if p['status'] != 'cancelled')
            key = (v['patient_id'], v['visit_date'])
            if key in seen:      # لا نكرر المقبوض إذا كان للمراجع أكثر من زيارة في اليوم نفسه
                v['paid_that_day'] = None
            else:
                seen.add(key)
                v['paid_that_day'] = _scalar(db, "SELECT SUM(amount) FROM payments WHERE deleted=0 AND kind='payment' AND patient_id=? AND pay_date=?", (v['patient_id'], v['visit_date']))
            if v['patient_id'] not in bal_cache:
                bal_cache[v['patient_id']] = balance(db, v['patient_id'])['remaining']
            v['remaining'] = bal_cache[v['patient_id']]
        rows.append(v)
    return rows


def payments_in_range(db, a, b, q=''):
    sql = ("SELECT y.id, y.pay_date, y.amount, y.kind, y.method, y.notes, y.patient_id, p.full_name, p.file_no FROM payments y "
           "JOIN patients p ON p.id=y.patient_id WHERE y.deleted=0 AND y.pay_date BETWEEN ? AND ?")
    args = [a, b]
    cond, ca = search_cond(q)
    if cond:
        sql += ' AND ' + cond
        args += ca
    return [dict(r) for r in db.execute(sql + ' ORDER BY y.pay_date DESC, y.id DESC LIMIT 3000', args)]


@route('GET', '/api/visits_by_date', perm='visits', tx=False)
def visits_by_date(c):
    a, b = _range(c)
    money = can(c.user, 'payments')
    out = {'visits': visits_in_range(c.db, a, b, c.q.get('q', ''), c.q.get('doctor', ''), money)}
    if money:
        out['payments'] = payments_in_range(c.db, a, b, c.q.get('q', ''))
        out['receipts_total'] = sum(p['amount'] for p in out['payments'] if p['kind'] == 'payment')
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
