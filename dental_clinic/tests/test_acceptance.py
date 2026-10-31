# -*- coding: utf-8 -*-
"""اختبارات القبول: تعمل على الخادم الحقيقي عبر HTTP وقاعدة SQLite حقيقية في مجلد مؤقت منفصل."""
import os, sys, json, io, time, shutil, tempfile, threading, subprocess, sqlite3, unittest, urllib.request, urllib.error, urllib.parse, socket
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server, seed_demo

PW = 'Test-pass-1234'
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Client:
    def __init__(self, port):
        self.base = 'http://127.0.0.1:%d' % port
        self.cookie = None

    def call(self, method, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode('utf-8') if body is not None else None)
        h = {'X-Requested-With': 'clinic'}
        if body is not None:
            h['Content-Type'] = 'application/json'
        if self.cookie:
            h['Cookie'] = self.cookie
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            r = e
        sc = r.headers.get('Set-Cookie')
        if sc and sc.startswith('sid='):
            self.cookie = sc.split(';')[0] if sc.split(';')[0] != 'sid=' else None
        payload = r.read()
        ctype = r.headers.get('Content-Type', '')
        parsed = json.loads(payload.decode('utf-8')) if 'json' in ctype and payload else payload
        return r.status if hasattr(r, 'status') else r.code, parsed

    def ok(self, method, path, body=None, **kw):
        s, d = self.call(method, path, body, **kw)
        assert s == 200, (method, path, s, d)
        return d

    def setup(self, username='admin'):
        return self.ok('POST', '/api/setup', {'username': username, 'password': PW, 'clinic_name': 'عيادة الاختبار'})

    def login(self, username, pw=PW):
        return self.call('POST', '/api/login', {'username': username, 'password': pw})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='clinic_test_')
        self.srv = server.make_server(self.tmp, 0)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        self.c = Client(self.srv.server_address[1])
        self.c.setup()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # أدوات مساعدة
    def patient(self, name='أحمد حسين علي', phone='07701234567', **kw):
        d = {'full_name': name, 'phone': phone}
        d.update(kw)
        return self.c.ok('POST', '/api/patients', d)['patient']

    def visit(self, pid, date, procs, **kw):
        d = {'visit_date': date, 'procedures': procs}
        d.update(kw)
        return self.c.ok('POST', '/api/patients/%d/visits' % pid, d)

    def pay(self, pid, date, amount, key=None, **kw):
        d = {'pay_date': date, 'amount': amount, 'method': 'cash', 'idem_key': key or ('k-%s-%s-%s' % (pid, date, amount))}
        d.update(kw)
        return self.c.ok('POST', '/api/patients/%d/payments' % pid, d)

    def summary(self, pid):
        return self.c.ok('GET', '/api/patients/%d' % pid)['summary']


class T01_Persistence(unittest.TestCase):
    def test_restart_keeps_data(self):
        """الاختبار 1: إنشاء مراجع، إغلاق البرنامج (عملية حقيقية) وإعادة فتحه، بقاء البيانات"""
        tmp = tempfile.mkdtemp(prefix='clinic_proc_')
        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
        def start():
            p = subprocess.Popen([sys.executable, os.path.join(APP, 'server.py'), '--port', str(port), '--data-dir', tmp],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                try:
                    socket.create_connection(('127.0.0.1', port), 0.2).close()
                    return p
                except OSError:
                    time.sleep(0.1)
            raise RuntimeError('server did not start')
        try:
            p = start()
            c = Client(port); c.setup()
            pid = c.ok('POST', '/api/patients', {'full_name': 'مراجع الاختبار الأول', 'phone': '07811112222'})['patient']['id']
            p.terminate(); p.wait(10)
            p = start()
            c2 = Client(port)
            self.assertEqual(c2.login('admin')[0], 200)
            got = c2.ok('GET', '/api/patients/%d' % pid)['patient']
            self.assertEqual(got['full_name'], 'مراجع الاختبار الأول')
            self.assertEqual(got['file_no'], 1001)
            p.terminate(); p.wait(10)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class T02_Finance(Base):
    def test_installments(self):
        """الاختبار 2: علاج 500,000 ودفعتان 150,000 و100,000 → مقبوض 250,000 ومتبقي 250,000"""
        p = self.patient()
        self.visit(p['id'], '2025-03-10', [{'name': 'زراعة سن', 'tooth_no': '36', 'status': 'in_progress', 'cost': 500000}])
        self.pay(p['id'], '2025-03-10', 150000)
        r = self.pay(p['id'], '2025-03-24', 100000)
        s = r['summary']
        self.assertEqual((s['total_cost'], s['net_paid'], s['remaining']), (500000, 250000, 250000))
        rep = self.c.ok('GET', '/api/reports/period?from=2025-03-01&to=2025-03-31')['stats']
        self.assertEqual(rep['receipts'], 250000)
        self.assertEqual(rep['agreed_value'], 500000)   # قيمة العلاج لا تُحتسب إيراداً

    def test_discount_and_formula(self):
        p = self.patient()
        self.visit(p['id'], '2025-03-10', [{'name': 'تاج', 'status': 'completed', 'cost': 400000}])
        self.c.ok('POST', '/api/patients/%d/adjustments' % p['id'], {'kind': 'discount', 'amount': 50000, 'adj_date': '2025-03-10', 'notes': 'خصم'})
        self.c.ok('POST', '/api/patients/%d/adjustments' % p['id'], {'kind': 'debit', 'amount': 10000, 'adj_date': '2025-03-11', 'notes': 'مادة إضافية'})
        self.pay(p['id'], '2025-03-12', 100000)
        s = self.summary(p['id'])
        self.assertEqual(s['remaining'], 400000 - 50000 + 10000 - 100000)

    def test_planned_not_counted_until_started(self):
        p = self.patient()
        v = self.visit(p['id'], '2025-03-10', [{'name': 'تقويم', 'status': 'planned', 'cost': 900000}])
        self.assertEqual(self.summary(p['id'])['remaining'], 0)
        self.assertEqual(self.summary(p['id'])['planned_cost'], 900000)
        self.c.ok('PUT', '/api/procedures/%d' % v['visit']['procedures'][0]['id'], {'status': 'in_progress'})
        self.assertEqual(self.summary(p['id'])['remaining'], 900000)


class T03_Months(Base):
    def test_payment_counted_in_its_own_month(self):
        """الاختبار 3: كل دفعة تُحتسب في شهر استلامها"""
        p = self.patient()
        self.visit(p['id'], '2025-03-10', [{'name': 'زراعة', 'status': 'in_progress', 'cost': 500000}])
        self.pay(p['id'], '2025-03-28', 150000)
        self.pay(p['id'], '2025-04-05', 100000)
        mar = self.c.ok('GET', '/api/reports/period?from=2025-03-01&to=2025-03-31')['stats']
        apr = self.c.ok('GET', '/api/reports/period?from=2025-04-01&to=2025-04-30')['stats']
        self.assertEqual((mar['receipts'], apr['receipts']), (150000, 100000))
        self.assertEqual((mar['agreed_value'], apr['agreed_value']), (500000, 0))
        self.assertEqual(apr['visits_count'], 0)


class T04_CashFlow(Base):
    def test_net_cash_flow(self):
        """الاختبار 4: مقبوضات 250,000 − مصروف 50,000 → صافي التدفق 200,000"""
        p = self.patient()
        self.visit(p['id'], '2025-05-02', [{'name': 'حشوة', 'status': 'completed', 'cost': 250000}])
        self.pay(p['id'], '2025-05-02', 250000)
        self.c.ok('POST', '/api/expenses', {'exp_date': '2025-05-03', 'category': 'مواد طب الأسنان', 'amount': 50000, 'method': 'cash'})
        s = self.c.ok('GET', '/api/reports/period?from=2025-05-01&to=2025-05-31')['stats']
        self.assertEqual((s['receipts'], s['expenses'], s['net_cash_flow']), (250000, 50000, 200000))
        self.assertNotIn('net_profit', s)    # لا نسمي صافي المقبوضات «صافي الربح»
        self.assertEqual(s['estimated_profit'], 250000 - 50000)
        self.c.ok('POST', '/api/patients/%d/payments' % p['id'], {'pay_date': '2025-05-20', 'amount': 20000, 'kind': 'refund', 'method': 'cash', 'idem_key': 'ref-0001-x'})
        s = self.c.ok('GET', '/api/reports/period?from=2025-05-01&to=2025-05-31')['stats']
        self.assertEqual(s['net_cash_flow'], 250000 - 50000 - 20000)
        self.assertEqual(s['receipts'], 250000)


class T05_Search(Base):
    def test_search_and_open(self):
        """الاختبار 5: بحث بجزء من الاسم، فتح الملف، ظهور الزيارات والدفعات"""
        p = self.patient('عبد الله ياسر جاسم', '0770 555 1234')
        self.patient('سارة محمد كاظم', '07801112233')
        self.visit(p['id'], '2025-06-01', [{'name': 'فحص', 'cost': 15000}])
        self.visit(p['id'], '2025-06-15', [{'name': 'حشوة', 'cost': 60000}])
        self.pay(p['id'], '2025-06-15', 30000)
        for q in ['ياسر', 'عبدالله', 'عبد الله جاسم', 'عبدالله ياسر', '5551234', '+9647705551234', str(p['file_no'])]:
            res = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote(q))['patients']
            self.assertEqual([r['id'] for r in res], [p['id']], q)
        self.assertEqual(len(self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('احمد'))['patients']), 0)
        full = self.c.ok('GET', '/api/patients/%d' % p['id'])
        self.assertEqual(len(full['visits']), 2)
        self.assertEqual(len(full['payments']), 1)
        self.assertEqual(full['visits'][0]['visit_date'], '2025-06-15')   # الأحدث أولاً

    def test_arabic_variants(self):
        a = self.patient('أحمد إبراهيم', '07700000001')
        b = self.patient('فاطمة الزهراء', '07700000002')
        for q, pid in [('احمد ابراهيم', a['id']), ('فاطمه الزهراء', b['id']), ('أحمد', a['id'])]:
            res = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote(q))['patients']
            self.assertIn(pid, [r['id'] for r in res], q)

    def test_duplicate_warning(self):
        self.patient('علي كريم', '07705550000')
        s, d = self.c.call('POST', '/api/patients', {'full_name': 'علي  كريم', 'phone': '+964 770 555 0000'})
        self.assertEqual((s, d['code']), (409, 'duplicate'))
        self.assertEqual(self.c.call('POST', '/api/patients', {'full_name': 'علي كريم', 'phone': '07705550000', 'force': True})[0], 200)


class T06_Reports(Base):
    def test_monthly_yearly_match_payments(self):
        """الاختبار 6: تطابق التقارير الشهرية والسنوية مع الدفعات الفعلية"""
        p1, p2 = self.patient('مريض أول', '07700000011'), self.patient('مريض ثان', '07700000012')
        data = [(p1, '2025-01-15', 100000), (p1, '2025-02-20', 50000), (p2, '2025-02-21', 75000),
                (p2, '2025-07-04', 25000), (p1, '2025-12-31', 10000), (p1, '2026-01-01', 99000)]
        for p, d, a in data:
            self.visit(p['id'], d, [{'name': 'فحص', 'cost': 500000, 'status': 'completed'}])
            self.pay(p['id'], d, a)
        y = self.c.ok('GET', '/api/reports/yearly?year=2025&compare=2026')
        self.assertEqual(sum(m['receipts'] for m in y['months']), 260000)
        self.assertEqual(y['stats']['receipts'], 260000)
        self.assertEqual(y['months'][1]['receipts'], 125000)
        self.assertEqual(y['compare']['stats']['receipts'], 99000)
        feb = self.c.ok('GET', '/api/reports/period?from=2025-02-01&to=2025-02-28')
        self.assertEqual(feb['stats']['receipts'], 125000)
        self.assertEqual(sum(d['receipts'] for d in feb['daily']), 125000)
        self.assertEqual(len(feb['daily']), 28)
        db = sqlite3.connect(os.path.join(self.tmp, 'clinic.db'))
        raw = db.execute("select sum(amount) from payments where kind='payment' and deleted=0 and pay_date between '2025-01-01' and '2025-12-31'").fetchone()[0]
        self.assertEqual(raw, y['stats']['receipts'])
        day = self.c.ok('GET', '/api/reports/daily?date=2025-02-21')
        self.assertEqual((day['stats']['receipts'], day['stats']['payments_count'], len(day['payments'])), (75000, 1, 1))

    def test_bydate_distinguishes_treatment_and_payment_dates(self):
        p = self.patient()
        self.visit(p['id'], '2025-08-01', [{'name': 'حشوة', 'cost': 80000, 'status': 'completed'}])
        self.pay(p['id'], '2025-08-09', 30000)
        r1 = self.c.ok('GET', '/api/visits_by_date?from=2025-08-01&to=2025-08-01')
        self.assertEqual((len(r1['visits']), r1['visits'][0]['visit_cost'], r1['visits'][0]['paid_that_day'], r1['visits'][0]['remaining']), (1, 80000, 0, 50000))
        r2 = self.c.ok('GET', '/api/visits_by_date?from=2025-08-09&to=2025-08-09')
        self.assertEqual((len(r2['visits']), r2['receipts_total']), (0, 30000))

    def test_debtors_and_dues(self):
        p = self.patient()
        self.visit(p['id'], '2025-09-01', [{'name': 'تاج', 'cost': 200000, 'status': 'completed'}])
        self.pay(p['id'], '2025-09-01', 50000)
        d = self.c.ok('GET', '/api/reports/debtors')
        self.assertEqual((len(d['debtors']), d['debtors'][0]['remaining'], d['total_dues']), (1, 150000, 150000))
        du = self.c.ok('GET', '/api/reports/dues?from=2025-09-01&to=2025-09-30')
        self.assertEqual((du['rows'][0]['cost_in_period'], du['rows'][0]['paid_in_period'], du['total_outstanding_now']), (200000, 50000, 150000))
        dash = self.c.ok('GET', '/api/dashboard?today=2025-09-01')
        self.assertEqual((dash['patients_count'], dash['visits_today'], dash['receipts_today'], dash['receipts_month'], dash['total_dues']), (1, 1, 50000, 50000, 150000))


class T07_Backup(Base):
    def test_backup_and_restore_in_separate_env(self):
        """الاختبار 7: نسخة احتياطية ثم استعادتها في بيئة منفصلة"""
        p = self.patient()
        self.visit(p['id'], '2025-03-10', [{'name': 'زراعة', 'cost': 500000, 'status': 'in_progress'}])
        self.pay(p['id'], '2025-03-10', 150000)
        info = self.c.ok('POST', '/api/backup')['backup']
        self.assertTrue(os.path.isfile(info['path']))
        s, blob = self.c.call('GET', '/api/backup/download?name=' + info['name'])
        self.assertEqual(s, 200)
        tmp2 = tempfile.mkdtemp(prefix='clinic_restore_')
        srv2 = server.make_server(tmp2, 0)
        threading.Thread(target=srv2.serve_forever, daemon=True).start()
        try:
            c2 = Client(srv2.server_address[1]); c2.setup('other')
            r = c2.ok('POST', '/api/restore', raw=blob, headers={'Content-Type': 'application/octet-stream'})
            self.assertTrue(r['relogin'])
            self.assertEqual(c2.call('GET', '/api/patients')[0], 401)           # الجلسات أُلغيت بعد الاستعادة
            self.assertEqual(c2.login('admin')[0], 200)                         # مستخدمو النسخة المستعادة
            got = c2.ok('GET', '/api/patients/%d' % p['id'])
            self.assertEqual((got['summary']['remaining'], len(got['payments']), got['patient']['full_name']), (350000, 1, p['full_name']))
            # ملف غير صالح يُرفض ولا يمس البيانات
            self.assertEqual(c2.call('POST', '/api/restore', raw=b'not a database', headers={'Content-Type': 'application/octet-stream'})[0], 400)
            self.assertEqual(c2.call('POST', '/api/restore', raw=b'not a database')[0], 400)
            self.assertEqual(c2.call('GET', '/api/patients')[0], 200)
        finally:
            srv2.shutdown(); srv2.server_close(); shutil.rmtree(tmp2, ignore_errors=True)

    def test_restore_in_place_and_safety_backup(self):
        p = self.patient()
        info = self.c.ok('POST', '/api/backup')['backup']
        self.patient('مراجع بعد النسخة', '07709990000')
        _, blob = self.c.call('GET', '/api/backup/download?name=' + info['name'])
        r = self.c.ok('POST', '/api/restore', raw=blob)
        self.assertTrue(r['safety_backup'].startswith('pre_restore_'))
        self.c.login('admin')
        self.assertEqual(len(self.c.ok('GET', '/api/patients')['patients']), 1)
        self.assertTrue(any(b['name'] == r['safety_backup'] for b in self.c.ok('GET', '/api/backups')['backups']))


class T08_Integrity(Base):
    def test_no_double_payment(self):
        """الاختبار 8: الضغط المتكرر لا يسجل الدفعة مرتين"""
        p = self.patient()
        self.visit(p['id'], '2025-03-10', [{'name': 'حشوة', 'cost': 100000}])
        body = {'pay_date': '2025-03-10', 'amount': 40000, 'method': 'cash', 'idem_key': 'same-click-0001'}
        r1 = self.c.ok('POST', '/api/patients/%d/payments' % p['id'], body)
        r2 = self.c.ok('POST', '/api/patients/%d/payments' % p['id'], body)
        self.assertFalse(r1['duplicate']); self.assertTrue(r2['duplicate'])
        self.assertEqual(r1['payment']['id'], r2['payment']['id'])
        self.assertEqual(self.summary(p['id'])['net_paid'], 40000)
        # ضغط متزامن من عدة خيوط
        res = []
        def hit():
            res.append(self.c.call('POST', '/api/patients/%d/payments' % p['id'], dict(body, idem_key='race-key-0002', amount=10000))[0])
        ts = [threading.Thread(target=hit) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertTrue(all(s == 200 for s in res))
        self.assertEqual(self.summary(p['id'])['net_paid'], 50000)

    def test_edits_and_refunds_do_not_corrupt_history(self):
        p = self.patient()
        v = self.visit(p['id'], '2025-03-10', [{'name': 'تاج', 'cost': 300000, 'status': 'completed'}])
        self.pay(p['id'], '2025-03-10', 100000)
        before = self.c.ok('GET', '/api/reports/period?from=2025-03-01&to=2025-03-31')['stats']
        # تعديل تكلفة الإجراء لا يغير الدفعات المسجلة
        proc = v['visit']['procedures'][0]
        self.c.ok('PUT', '/api/procedures/%d' % proc['id'], {'cost': 350000})
        self.assertEqual(self.summary(p['id'])['net_paid'], 100000)
        self.assertEqual(self.summary(p['id'])['remaining'], 250000)
        # استرداد في شهر لاحق لا يغير تقرير الشهر السابق
        self.c.ok('POST', '/api/patients/%d/payments' % p['id'], {'pay_date': '2025-04-02', 'amount': 20000, 'kind': 'refund', 'method': 'cash', 'idem_key': 'refund-key-01'})
        after = self.c.ok('GET', '/api/reports/period?from=2025-03-01&to=2025-03-31')['stats']
        self.assertEqual((before['receipts'], before['refunds']), (after['receipts'], after['refunds']))
        apr = self.c.ok('GET', '/api/reports/period?from=2025-04-01&to=2025-04-30')['stats']
        self.assertEqual((apr['receipts'], apr['refunds']), (0, 20000))
        self.assertEqual(self.summary(p['id'])['remaining'], 270000)
        # استرداد أكبر من المدفوع مرفوض
        self.assertEqual(self.c.call('POST', '/api/patients/%d/payments' % p['id'], {'pay_date': '2025-04-03', 'amount': 999999, 'kind': 'refund', 'method': 'cash', 'idem_key': 'refund-key-02'})[0], 400)

    def test_overpay_guard(self):
        p = self.patient()
        v = self.visit(p['id'], '2025-03-10', [{'name': 'حشوة', 'cost': 100000, 'status': 'completed'}])
        self.pay(p['id'], '2025-03-10', 100000)
        s, d = self.c.call('POST', '/api/patients/%d/payments' % p['id'], {'pay_date': '2025-03-11', 'amount': 5000, 'method': 'cash', 'idem_key': 'over-key-0001'})
        self.assertEqual((s, d['code']), (409, 'overpaid'))
        self.assertEqual(self.summary(p['id'])['net_paid'], 100000)         # تراجع كامل
        s, d = self.c.call('DELETE', '/api/visits/%d' % v['visit']['id'])
        self.assertEqual((s, d['code']), (409, 'overpaid'))
        self.assertEqual(len(self.c.ok('GET', '/api/patients/%d' % p['id'])['visits']), 1)
        self.c.ok('POST', '/api/patients/%d/payments' % p['id'], {'pay_date': '2025-03-11', 'amount': 5000, 'method': 'cash', 'idem_key': 'over-key-0001', 'force': True})
        self.assertEqual(self.summary(p['id'])['remaining'], -5000)

    def test_soft_delete_void_and_audit(self):
        p = self.patient()
        self.visit(p['id'], '2025-03-10', [{'name': 'حشوة', 'cost': 100000, 'status': 'completed'}])
        pay = self.pay(p['id'], '2025-03-10', 60000)['payment']
        self.assertEqual(self.c.call('DELETE', '/api/payments/%d' % pay['id'], {})[0], 400)    # السبب مطلوب
        self.c.ok('DELETE', '/api/payments/%d' % pay['id'], {'reason': 'خطأ في الإدخال'})
        self.assertEqual(self.summary(p['id'])['net_paid'], 0)
        db = sqlite3.connect(os.path.join(self.tmp, 'clinic.db'))
        row = db.execute('select deleted, void_reason, amount from payments where id=?', (pay['id'],)).fetchone()
        self.assertEqual(row, (1, 'خطأ في الإدخال', 60000))       # السجل محفوظ وليس محذوفاً نهائياً
        rows = self.c.ok('GET', '/api/audit?entity=payment&entity_id=%d' % pay['id'])['rows']
        self.assertEqual({r['action'] for r in rows}, {'create', 'void'})
        void = [r for r in rows if r['action'] == 'void'][0]
        self.assertIn('60000', void['old_json'])
        # تعديل دفعة: القيمة القديمة والجديدة في السجل
        pay2 = self.pay(p['id'], '2025-03-12', 30000)['payment']
        self.c.ok('PUT', '/api/payments/%d' % pay2['id'], {'pay_date': '2025-03-12', 'amount': 35000, 'method': 'transfer', 'notes': 'تصحيح'})
        upd = [r for r in self.c.ok('GET', '/api/audit?entity=payment&entity_id=%d' % pay2['id'])['rows'] if r['action'] == 'update'][0]
        self.assertIn('30000', upd['old_json']); self.assertIn('35000', upd['new_json'])

    def test_delete_patient_with_financial_record(self):
        """حذف المراجع يحذف زياراته ودفعاته وخصوماته ومواعيده، فيختفي من التقارير، والأثر في سجل التدقيق"""
        keep = self.patient('مراجع باقٍ', '07709999999')
        self.visit(keep['id'], '2025-05-02', [{'name': 'تنظيف', 'cost': 40000}])
        self.pay(keep['id'], '2025-05-02', 40000)
        p = self.patient()
        self.visit(p['id'], '2025-05-01', [{'name': 'تاج', 'cost': 300000}], next_appointment='2099-01-01')
        self.pay(p['id'], '2025-05-01', 100000)
        self.c.ok('POST', '/api/patients/%d/adjustments' % p['id'], {'adj_date': '2025-05-01', 'amount': 20000, 'kind': 'discount', 'notes': 'خصم'})
        info = self.c.ok('GET', '/api/patients/%d/delete_info' % p['id'])
        self.assertEqual((info['visits'], info['payments'], info['paid'], info['remaining']), (1, 1, 100000, 180000))
        r = self.c.ok('DELETE', '/api/patients/%d' % p['id'], {})          # يُحذف رغم وجود مبلغ متبقٍ
        self.assertEqual(r['deleted']['payments'], 1)
        self.assertEqual(self.c.call('GET', '/api/patients/%d' % p['id'])[0], 404)
        st = self.c.ok('GET', '/api/reports/period?from=2025-05-01&to=2025-05-31')['stats']
        self.assertEqual((st['receipts'], st['agreed_value'], st['discounts'], st['visits_count']), (40000, 40000, 0, 1))
        self.assertEqual(self.c.ok('GET', '/api/reports/debtors')['total_dues'], 0)
        self.assertEqual(self.c.ok('GET', '/api/dashboard')['total_dues'], 0)
        self.assertEqual(len(self.c.ok('GET', '/api/appointments?from=2099-01-01&to=2099-01-31')['appointments']), 0)
        self.assertEqual(self.summary(keep['id'])['remaining'], 0)           # المراجع الآخر لم يتأثر
        aud = self.c.ok('GET', '/api/audit?entity=patient&entity_id=%d' % p['id'])['rows']
        d = [x for x in aud if x['action'] == 'delete'][0]
        self.assertIn('deleted_records', d['old_json'])
        db = sqlite3.connect(os.path.join(self.tmp, 'clinic.db'))      # السجلات معلَّمة محذوفة وليست ممسوحة
        self.assertEqual(db.execute('select count(*), sum(deleted) from payments where patient_id=?', (p['id'],)).fetchone(), (1, 1))
        db.close()
        # المستخدم غير المدير لا يستطيع الحذف
        self.c.ok('POST', '/api/users', {'username': 'rec7', 'password': PW, 'role': 'reception'})
        rec = Client(self.srv.server_address[1]); rec.login('rec7')
        self.assertEqual(rec.call('DELETE', '/api/patients/%d' % keep['id'], {})[0], 403)

    def test_validation(self):
        p = self.patient()
        pid = p['id']
        bad = [
            ('/api/patients/%d/payments' % pid, {'pay_date': '2999-01-01', 'amount': 1000, 'idem_key': 'v-key-00001'}),
            ('/api/patients/%d/payments' % pid, {'pay_date': '2025-01-01', 'amount': -5, 'idem_key': 'v-key-00002'}),
            ('/api/patients/%d/payments' % pid, {'pay_date': '2025-01-01', 'amount': 'abc', 'idem_key': 'v-key-00003'}),
            ('/api/patients/%d/payments' % pid, {'pay_date': '2025-13-45', 'amount': 1000, 'idem_key': 'v-key-00004'}),
            ('/api/patients/%d/payments' % pid, {'pay_date': '2025-01-01', 'amount': 1000.5, 'idem_key': 'v-key-00005'}),
            ('/api/patients/%d/payments' % pid, {'pay_date': '2025-01-01', 'amount': 1000}),
            ('/api/patients/%d/visits' % pid, {'visit_date': '2025-01-01', 'procedures': [{'name': 'x', 'tooth_no': '19'}]}),
            ('/api/patients/%d/visits' % pid, {'visit_date': '2025-01-01', 'procedures': [{'name': 'x', 'cost': -1}]}),
            ('/api/patients/%d/visits' % pid, {'visit_date': '2099-01-01', 'procedures': []}),
            ('/api/patients', {'full_name': ''}),
            ('/api/expenses', {'exp_date': '2025-01-01', 'category': 'غير موجود', 'amount': 5}),
        ]
        for path, body in bad:
            s, d = self.c.call('POST', path, body)
            self.assertEqual(s, 400, (path, body, d))
        self.assertEqual(self.summary(pid)['net_paid'], 0)
        # أرقام عربية ومبالغ بفواصل مقبولة
        r = self.c.ok('POST', '/api/patients/%d/payments' % pid, {'pay_date': '2025-01-01', 'amount': '١٥٠,٠٠٠', 'idem_key': 'v-key-ok-001', 'force': True})
        self.assertEqual(r['payment']['amount'], 150000)
        # أرقام الأسنان FDI صحيحة
        v = self.visit(pid, '2025-01-02', [{'name': 'a', 'tooth_no': '11'}, {'name': 'b', 'tooth_no': '85'}, {'name': 'c'}])
        self.assertEqual([x['tooth_no'] for x in v['visit']['procedures']], ['11', '85', None])

    def test_multiple_procedures_edit_visit_and_next_appointment(self):
        p = self.patient()
        v = self.visit(p['id'], '2025-03-10', [{'name': 'حشوة', 'tooth_no': '16', 'cost': 60000, 'status': 'completed'},
                                                {'name': 'تنظيف', 'cost': 30000, 'status': 'completed'}],
                       next_appointment='2026-12-01', next_time='10:30', doctor='د. سامر')
        self.assertEqual(self.summary(p['id'])['total_cost'], 90000)
        ap = self.c.ok('GET', '/api/appointments?patient_id=%d' % p['id'])['appointments']
        self.assertEqual((len(ap), ap[0]['appt_date'], ap[0]['appt_time']), (1, '2026-12-01', '10:30'))
        vid, procs = v['visit']['id'], v['visit']['procedures']
        self.c.ok('PUT', '/api/visits/%d' % vid, {'visit_date': '2025-03-10', 'doctor': 'د. سامر', 'next_appointment': '2026-12-05', 'next_time': '11:00',
                  'procedures': [dict(procs[0], cost=70000), {'name': 'أشعة', 'cost': 10000}]})   # حذف التنظيف وإضافة أشعة
        self.assertEqual(self.summary(p['id'])['total_cost'], 80000)
        ap = self.c.ok('GET', '/api/appointments?patient_id=%d' % p['id'])['appointments']
        self.assertEqual((len(ap), ap[0]['appt_date']), (1, '2026-12-05'))
        self.assertEqual(len(self.c.ok('GET', '/api/patients/%d' % p['id'])['visits'][0]['procedures']), 2)


class T09_RTL(Base):
    def test_rtl_arabic_everywhere(self):
        """الاختبار 9 (الجزء الآلي): اتجاه RTL في الصفحة وملفات التصدير وبقاء النص العربي سليماً"""
        html = urllib.request.urlopen(self.c.base + '/').read().decode('utf-8')
        self.assertIn('lang="ar"', html); self.assertIn('dir="rtl"', html)
        css = urllib.request.urlopen(self.c.base + '/static/style.css').read().decode('utf-8')
        self.assertIn('direction: rtl', css)
        s, blob = self.c.call('POST', '/api/export', {'format': 'xlsx', 'title': 'تقرير', 'headers': ['الاسم', 'المبلغ'], 'rows': [['أحمد', 250000]]})
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(blob)).active
        self.assertTrue(ws.sheet_view.rightToLeft)
        self.assertEqual([c.value for c in ws[2]], ['أحمد', 250000])
        s, csvb = self.c.call('POST', '/api/export', {'format': 'csv', 'title': 't', 'headers': ['الاسم'], 'rows': [['سارة']]})
        self.assertTrue(csvb.startswith(b'\xef\xbb\xbf'))
        self.assertIn('سارة', csvb.decode('utf-8-sig'))


class T10_DemoSeparation(unittest.TestCase):
    def test_demo_data_isolated_from_real(self):
        """الاختبار 10: البيانات التجريبية في بيئة منفصلة وحذفها لا يمس بيانات العيادة"""
        real, demo = tempfile.mkdtemp(prefix='clinic_real_'), tempfile.mkdtemp(prefix='clinic_demo_')
        try:
            rs = server.make_server(real, 0)
            threading.Thread(target=rs.serve_forever, daemon=True).start()
            c = Client(rs.server_address[1]); c.setup()
            c.ok('POST', '/api/patients', {'full_name': 'مراجع حقيقي'})
            ds = server.make_server(demo, 0, demo=True)
            self.assertTrue(seed_demo.seed_if_empty(ds.clinic))
            n_demo = sqlite3.connect(os.path.join(demo, 'clinic.db')).execute('select count(*) from patients').fetchone()[0]
            self.assertGreater(n_demo, 10)
            self.assertEqual(len(c.ok('GET', '/api/patients')['patients']), 1)
            ds.server_close(); shutil.rmtree(demo)
            self.assertEqual(len(c.ok('GET', '/api/patients')['patients']), 1)
            rs.shutdown(); rs.server_close()
        finally:
            shutil.rmtree(real, ignore_errors=True); shutil.rmtree(demo, ignore_errors=True)


class T11_Security(Base):
    def test_auth_permissions_csrf_lockout(self):
        anon = Client(self.srv.server_address[1])
        self.assertEqual(anon.call('GET', '/api/patients')[0], 401)
        self.assertEqual(anon.call('GET', '/api/reports/debtors')[0], 401)
        s, d = anon.call('GET', '/api/session'); self.assertEqual((d['authenticated'], d['needs_setup']), (False, False))
        # لا بدون ترويسة CSRF
        s, _ = anon.call('POST', '/api/login', {'username': 'admin', 'password': PW}, headers={'X-Requested-With': 'x'})
        self.assertEqual(s, 403)
        # مضيف غير محلي مرفوض
        req = urllib.request.Request(self.c.base + '/api/session', headers={'Host': 'evil.example.com'})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)
        # الصلاحيات
        self.c.ok('POST', '/api/users', {'username': 'rec1', 'password': PW, 'role': 'reception', 'full_name': 'الاستقبال'})
        self.c.ok('POST', '/api/users', {'username': 'doc1', 'password': PW, 'role': 'doctor'})
        rec, doc = Client(self.srv.server_address[1]), Client(self.srv.server_address[1])
        self.assertEqual(rec.login('rec1')[0], 200); self.assertEqual(doc.login('doc1')[0], 200)
        p = self.patient()
        for path in ['/api/expenses', '/api/users', '/api/audit', '/api/backups', '/api/reports/yearly?year=2025', '/api/reports/period?from=2025-01-01&to=2025-01-31']:
            self.assertEqual(rec.call('GET', path)[0], 403, path)
        self.assertEqual(rec.call('GET', '/api/reports/debtors')[0], 200)
        self.assertEqual(rec.call('DELETE', '/api/patients/%d' % p['id'], {})[0], 403)
        self.assertEqual(rec.call('POST', '/api/backup', {})[0], 403)
        self.assertEqual(rec.call('PUT', '/api/settings', {'clinic_name': 'x'})[0], 403)
        full = doc.ok('GET', '/api/patients/%d' % p['id'])
        self.assertNotIn('payments', full); self.assertNotIn('summary', full)
        self.assertEqual(doc.call('POST', '/api/patients/%d/payments' % p['id'], {'pay_date': '2025-01-01', 'amount': 5, 'idem_key': 'doc-key-0001'})[0], 403)
        self.assertEqual(doc.call('GET', '/api/reports/debtors')[0], 403)
        self.assertNotIn('remaining', doc.ok('GET', '/api/patients')['patients'][0])
        # قفل بعد محاولات خاطئة
        bad = Client(self.srv.server_address[1])
        for _ in range(5):
            self.assertEqual(bad.login('rec1', 'wrong-password')[0], 401)
        self.assertEqual(bad.login('rec1', PW)[0], 429)
        # تعطيل مستخدم يلغي جلسته
        uid = [u for u in self.c.ok('GET', '/api/users')['users'] if u['username'] == 'doc1'][0]['id']
        self.c.ok('PUT', '/api/users/%d' % uid, {'active': 0})
        self.assertEqual(doc.call('GET', '/api/patients')[0], 401)
        # لا يمكن تعطيل آخر مدير
        aid = [u for u in self.c.ok('GET', '/api/users')['users'] if u['username'] == 'admin'][0]['id']
        self.assertEqual(self.c.call('PUT', '/api/users/%d' % aid, {'active': 0})[0], 400)
        # كلمة مرور ضعيفة وإعادة الإعداد
        self.assertEqual(self.c.call('POST', '/api/users', {'username': 'weak', 'password': '123', 'role': 'doctor'})[0], 400)
        self.assertEqual(self.c.call('POST', '/api/setup', {'username': 'x2', 'password': PW})[0], 403)
        # كلمات المرور لا تُخزن نصاً صريحاً
        db = sqlite3.connect(os.path.join(self.tmp, 'clinic.db'))
        self.assertTrue(all(PW not in str(r) for r in db.execute('select * from users')))
        # منع اجتياز المسارات
        self.assertEqual(urllib.request.Request, urllib.request.Request)
        try:
            urllib.request.urlopen(self.c.base + '/static/..%2f..%2fcore.py')
            self.fail('path traversal should fail')
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_session_idle_timeout(self):
        self.c.ok('PUT', '/api/settings', {'clinic_name': 'x', 'currency_code': 'IQD', 'currency_label': 'دينار', 'currency_symbol': 'د.ع', 'idle_minutes': 1})
        for s in self.srv.clinic.sessions.values():
            s['last'] -= 3600
        self.assertEqual(self.c.call('GET', '/api/patients')[0], 401)


class T12_Doctors(Base):
    def test_patient_doctor_and_visit_default(self):
        """اختيار الطبيب عند إضافة المراجع، والزيارة الجديدة تأخذ طبيبه افتراضياً"""
        p = self.patient(doctor='د. علي')
        self.assertEqual(p['doctor'], 'د. علي')
        self.visit(p['id'], '2025-03-01', [{'name': 'حشوة', 'cost': 50000}])
        v = self.c.ok('GET', '/api/patients/%d' % p['id'])['visits'][0]
        self.assertEqual(v['doctor'], 'د. علي')
        self.assertEqual(v['procedures'][0]['doctor'], 'د. علي')
        # طبيب مختلف لزيارة معينة يبقى كما اختير
        self.visit(p['id'], '2025-03-02', [{'name': 'تنظيف', 'cost': 20000}], doctor='د. سارة')
        docs = sorted(v['doctor'] for v in self.c.ok('GET', '/api/patients/%d' % p['id'])['visits'])
        self.assertEqual(docs, ['د. سارة', 'د. علي'])
        # تغيير الطبيب المعالج وإزالته
        upd = self.c.ok('PUT', '/api/patients/%d' % p['id'], {'full_name': p['full_name'], 'phone': p['phone'], 'doctor': 'د. سارة'})['patient']
        self.assertEqual(upd['doctor'], 'د. سارة')
        upd = self.c.ok('PUT', '/api/patients/%d' % p['id'], {'full_name': p['full_name'], 'phone': p['phone'], 'doctor': ''})['patient']
        self.assertIsNone(upd['doctor'])
        lst = self.c.ok('GET', '/api/patients')['patients']
        self.assertIn('doctor', lst[0])

    def test_user_default_doctor(self):
        """كل مستخدم يُربط بطبيب افتراضي من الإعدادات؛ يظهر مع بيانات الدخول ويمكن تغييره أو إزالته"""
        self.c.ok('POST', '/api/users', {'username': 'reca', 'password': PW, 'role': 'reception', 'doctor': 'د. منتظر'})
        u = [x for x in self.c.ok('GET', '/api/users')['users'] if x['username'] == 'reca'][0]
        self.assertEqual(u['doctor'], 'د. منتظر')
        a = Client(self.srv.server_address[1]); s, d = a.login('reca')
        self.assertEqual((s, d['user']['doctor']), (200, 'د. منتظر'))
        self.assertEqual(a.ok('GET', '/api/session')['user']['doctor'], 'د. منتظر')
        self.c.ok('PUT', '/api/users/%d' % u['id'], {'role': 'reception', 'full_name': 'استقبال', 'active': 1})   # بدون الحقل: يبقى
        self.assertEqual(a.ok('GET', '/api/session')['user']['doctor'], 'د. منتظر')
        self.c.ok('PUT', '/api/users/%d' % u['id'], {'role': 'reception', 'active': 1, 'doctor': 'د. مرتضى'})
        self.assertEqual(a.ok('GET', '/api/session')['user']['doctor'], 'د. مرتضى')
        self.c.ok('PUT', '/api/users/%d' % u['id'], {'role': 'reception', 'active': 1, 'doctor': ''})
        self.assertIsNone(a.ok('GET', '/api/session')['user']['doctor'])

    def test_report_by_doctor(self):
        """تقرير عمل كل طبيب يطابق مجاميع التقرير العام"""
        a = self.patient('مراجع أول', '07701111111', doctor='د. علي')
        b = self.patient('مراجع ثاني', '07702222222', doctor='د. سارة')
        self.visit(a['id'], '2025-04-02', [{'name': 'تاج', 'cost': 100000, 'status': 'completed'},
                                          {'name': 'زراعة', 'cost': 50000, 'status': 'planned'},
                                          {'name': 'ملغى', 'cost': 99000, 'status': 'cancelled'}])
        vb1 = self.visit(b['id'], '2025-04-03', [{'name': 'حشوة', 'cost': 30000}], doctor='د. علي')['visit']
        self.visit(b['id'], '2025-04-10', [{'name': 'عصب', 'cost': 200000}])
        self.visit(b['id'], '2025-05-10', [{'name': 'خارج الفترة', 'cost': 70000}])
        self.pay(a['id'], '2025-04-02', 60000)
        self.pay(b['id'], '2025-04-03', 30000, visit_id=vb1['id'])
        self.pay(b['id'], '2025-04-10', 100000)
        d = self.c.ok('GET', '/api/reports/period?from=2025-04-01&to=2025-04-30')
        rows = {r['doctor']: r for r in d['by_doctor']}
        self.assertEqual(set(rows), {'د. علي', 'د. سارة'})
        ali, sara = rows['د. علي'], rows['د. سارة']
        self.assertEqual((ali['executed'], ali['agreed'], ali['receipts']), (130000, 180000, 90000))
        self.assertEqual((ali['patients'], ali['visits'], ali['procedures']), (2, 2, 3))
        self.assertEqual((sara['executed'], sara['agreed'], sara['receipts']), (200000, 200000, 100000))
        self.assertEqual(d['by_doctor'][0]['doctor'], 'د. سارة')   # الأعلى عملاً أولاً
        self.assertAlmostEqual(ali['share'] + sara['share'], 100, delta=0.2)
        self.assertEqual(sum(r['executed'] for r in d['by_doctor']), d['stats']['executed_value'])
        self.assertEqual(sum(r['agreed'] for r in d['by_doctor']), d['stats']['agreed_value'])
        self.assertEqual(sum(r['receipts'] for r in d['by_doctor']), d['stats']['receipts'])
        y = self.c.ok('GET', '/api/reports/yearly?year=2025')
        self.assertEqual(sum(r['executed'] for r in y['by_doctor']), 400000)
        day = self.c.ok('GET', '/api/reports/daily?date=2025-04-03')
        self.assertEqual([(r['doctor'], r['executed'], r['receipts']) for r in day['by_doctor']], [('د. علي', 30000, 30000)])
        # مراجع بلا طبيب: يظهر تحت «غير محدد»
        c = self.patient('مراجع ثالث', '07703333333')
        self.visit(c['id'], '2025-04-20', [{'name': 'فحص', 'cost': 10000}])
        d = self.c.ok('GET', '/api/reports/period?from=2025-04-01&to=2025-04-30')
        self.assertEqual(d['by_doctor'][-1]['doctor'], 'غير محدد')
        self.assertEqual(d['by_doctor'][-1]['executed'], 10000)

    def test_bydate_grouped_by_doctor(self):
        """مراجعو يوم/فترة: مجموعة لكل طبيب بترتيب الإعدادات ومجموع المدفوع له، والفلترة تُظهر كل مراجعيه"""
        st = self.c.ok('GET', '/api/settings')['settings']
        self.c.ok('PUT', '/api/settings', {**st, 'doctors': ['د مرتضى حميد عجرش', 'د منتظر']})
        a = self.patient('مراجع مرتضى', '07701000001', doctor='د مرتضى حميد عجرش')
        b = self.patient('مراجع منتظر', '07701000002', doctor='د منتظر')
        c = self.patient('مراجع قديم', '07701000003', doctor='د مرتضى حميد عجرش')
        self.visit(a['id'], '2025-07-01', [{'name': 'حشوة', 'cost': 50000}], paid_cash=True)
        self.visit(b['id'], '2025-07-01', [{'name': 'قلع سن', 'cost': 30000}], paid_cash=True)
        self.visit(b['id'], '2025-07-03', [{'name': 'تنظيف', 'cost': 20000}], doctor='د. مرتضى')     # كتابة مختلفة لنفس الطبيب
        db = sqlite3.connect(os.path.join(self.tmp, 'clinic.db'))     # زيارة قديمة بلا طبيب على الزيارة نفسها (مثل المستورد)
        vid = db.execute("INSERT INTO visits(patient_id,visit_date,doctor,created_at,updated_at) VALUES(?, '2025-07-02', NULL, 'x', 'x')", (c['id'],)).lastrowid
        db.execute("INSERT INTO procedures(visit_id,patient_id,name,status,cost,created_at,updated_at) VALUES(?,?, 'فحص', 'completed', 15000, 'x', 'x')", (vid, c['id']))
        db.commit(); db.close()
        self.pay(c['id'], '2025-07-02', 15000)
        d = self.c.ok('GET', '/api/visits_by_date?from=2025-07-01&to=2025-07-31')
        self.assertEqual([g['doctor'] for g in d['groups']], ['د مرتضى حميد عجرش', 'د منتظر'])
        mo, mu = d['groups']
        self.assertEqual((mo['visits'], mo['patients'], mo['cost'], mo['receipts']), (3, 3, 85000, 65000))
        self.assertEqual((mu['visits'], mu['patients'], mu['cost'], mu['receipts']), (1, 1, 30000, 30000))
        # الفلترة بالطبيب: كل زياراته (بما فيها القديمة بلا طبيب والكتابة المختلفة)، والدفعات أيضاً
        f = self.c.ok('GET', '/api/visits_by_date?from=2025-07-01&to=2025-07-31&doctor=' + urllib.parse.quote('د مرتضى حميد عجرش'))
        self.assertEqual(len(f['visits']), 3)
        self.assertEqual(f['receipts_total'], 65000)
        self.assertEqual({v['doctor_eff'] for v in f['visits']}, {'د مرتضى حميد عجرش'})
        # تقرير الأطباء يستعمل نفس التوحيد
        rows = {r['doctor']: r for r in self.c.ok('GET', '/api/reports/period?from=2025-07-01&to=2025-07-31')['by_doctor']}
        self.assertEqual(set(rows), {'د مرتضى حميد عجرش', 'د منتظر'})
        self.assertEqual(rows['د مرتضى حميد عجرش']['receipts'], 65000)

    def test_patients_list_shows_all(self):
        """قائمة المراجعين تعرض الكل (آلاف المراجعين) لا أول 200 فقط"""
        db = sqlite3.connect(os.path.join(self.tmp, 'clinic.db'))
        db.executemany("INSERT INTO patients(file_no,full_name,name_norm,created_at,updated_at) VALUES(?,?,?,'x','x')",
                       [(2000 + i, 'مراجع %d' % i, 'مراجع %d' % i) for i in range(1200)])
        db.commit(); db.close()
        self.assertEqual(len(self.c.ok('GET', '/api/patients?limit=100000')['patients']), 1200)

    def test_root_canal_stages_and_partial_payment(self):
        """حشوة الجذر: مراحل وقياسات تُحفظ؛ الدفع لكل إجراء: المدفوع = التكلفة − المتبقي، والمتبقي يُضاف للمطلوب"""
        p = self.patient()
        r = self.visit(p['id'], '2025-08-01', [
            {'name': 'حشوة جذر (عصب)', 'tooth_no': '16', 'cost': 100000, 'rc_steps': ['obturation', 'access'], 'rc_measure': 'MB 21mm, DB 20.5mm', 'paid_now': 60000},
            {'name': 'فحص وتشخيص', 'cost': 10000, 'paid_now': 10000},
            {'name': 'تاج', 'cost': 300000, 'status': 'planned', 'paid_now': 300000}])        # المخطط له لا يُدفع الآن
        self.assertEqual(r['payment']['amount'], 70000)
        rc = r['visit']['procedures'][0]
        self.assertEqual((rc['rc_steps'], rc['rc_measure']), ('access,obturation', 'MB 21mm, DB 20.5mm'))
        self.assertEqual(self.summary(p['id'])['remaining'], 40000)
        # تجاوز التكلفة أو مرحلة غير معروفة مرفوضان
        bad = lambda pr: self.c.call('POST', '/api/patients/%d/visits' % p['id'], {'visit_date': '2025-08-02', 'procedures': [pr]})[0]
        self.assertEqual(bad({'name': 'حشوة', 'cost': 10000, 'paid_now': 20000}), 400)
        self.assertEqual(bad({'name': 'حشوة جذر', 'cost': 0, 'rc_steps': ['x']}), 400)
        # تعديل الزيارة: إكمال المراحل، وإجراء جديد يُضاف مع دفعته
        v = r['visit']
        procs = [{'id': x['id'], 'name': x['name'], 'tooth_no': x['tooth_no'], 'status': x['status'], 'cost': x['cost'], 'rc_steps': x['rc_steps'], 'rc_measure': x['rc_measure']} for x in v['procedures']]
        procs[0]['rc_steps'] = ['access', 'obturation', 'buildup']
        procs.append({'name': 'أشعة', 'cost': 15000, 'paid_now': 15000})
        u = self.c.ok('PUT', '/api/visits/%d' % v['id'], {'visit_date': '2025-08-01', 'procedures': procs})
        self.assertEqual(u['payment']['amount'], 15000)
        self.assertEqual(u['visit']['procedures'][0]['rc_steps'], 'access,obturation,buildup')
        self.assertEqual(self.summary(p['id'])['remaining'], 40000)
        self.assertEqual(len(self.c.ok('GET', '/api/patients/%d' % p['id'])['payments']), 2)

    def test_lab_and_visit_payments_follow_visit_edit(self):
        """المختبر يُحفظ للتاج/الجسر/التقويم؛ وتعديل الزيارة يعدّل دفعاتها (التاريخ والمبلغ، وصفر = إلغاء)"""
        p = self.patient()
        r = self.visit(p['id'], '2025-09-01', [{'name': 'تاج (تلبيس) - زركون', 'tooth_no': 'UR6', 'cost': 200000, 'lab': 'مختبر النور', 'paid_now': 150000}])
        v, pay = r['visit'], r['payment']
        self.assertEqual(v['procedures'][0]['lab'], 'مختبر النور')
        self.pay(p['id'], '2025-09-01', 20000)                                           # دفعة أخرى بنفس تاريخ الزيارة
        self.pay(p['id'], '2025-09-05', 10000)                                           # يوم آخر: لا تتأثر
        self.assertEqual(self.c.ok('GET', '/api/labs')['labs'], ['مختبر النور'])
        procs = [{'id': x['id'], 'name': x['name'], 'tooth_no': x['tooth_no'], 'status': x['status'], 'cost': x['cost'], 'lab': x['lab']} for x in v['procedures']]
        same_day = [y for y in self.c.ok('GET', '/api/patients/%d' % p['id'])['payments'] if y['pay_date'] == '2025-09-01' and y['id'] != pay['id']][0]
        self.c.ok('PUT', '/api/visits/%d' % v['id'], {'visit_date': '2025-09-03', 'procedures': procs,
                                                     'payments': [{'id': pay['id'], 'amount': 170000}, {'id': same_day['id'], 'amount': 0}]})
        pays = {y['id']: y for y in self.c.ok('GET', '/api/patients/%d' % p['id'])['payments']}
        self.assertEqual((pays[pay['id']]['amount'], pays[pay['id']]['pay_date']), (170000, '2025-09-03'))
        self.assertNotIn(same_day['id'], pays)                                            # صفر = أُلغيت
        self.assertEqual(sorted(y['pay_date'] for y in pays.values()), ['2025-09-03', '2025-09-05'])
        self.assertEqual(self.summary(p['id'])['remaining'], 200000 - 170000 - 10000)
        # دفعة لا تتبع الزيارة مرفوضة؛ والاستقبال لا يعدّل الدفعات من الزيارة
        other = [y for y in pays.values() if y['pay_date'] == '2025-09-05'][0]
        self.assertEqual(self.c.call('PUT', '/api/visits/%d' % v['id'], {'visit_date': '2025-09-03', 'payments': [{'id': other['id'], 'amount': 1}]})[0], 400)
        self.c.ok('POST', '/api/users', {'username': 'rec5', 'password': PW, 'role': 'reception'})
        rec = Client(self.srv.server_address[1]); rec.login('rec5')
        self.assertEqual(rec.call('PUT', '/api/visits/%d' % v['id'], {'visit_date': '2025-09-04', 'payments': [{'id': pay['id'], 'amount': 1}]})[0], 200)
        self.assertEqual({y['id']: y for y in self.c.ok('GET', '/api/patients/%d' % p['id'])['payments']}[pay['id']]['amount'], 170000)

    def test_old_database_is_upgraded(self):
        """قاعدة بيانات من الإصدار السابق (بدون عمود الطبيب) تُرقّى تلقائياً دون فقدان البيانات"""
        import core
        tmp = tempfile.mkdtemp(prefix='clinic_old_')
        try:
            path = os.path.join(tmp, 'clinic.db')
            db = sqlite3.connect(path)
            db.executescript(core.SCHEMA)   # الجداول الأساسية كما في الإصدار السابق (العمود يُضاف بالترقية فقط)
            self.assertNotIn('doctor', [r[1] for r in db.execute('PRAGMA table_info(patients)')])
            db.execute("INSERT INTO patients(file_no,full_name,name_norm,created_at,updated_at) VALUES(1001,'قديم','قديم','x','x')")
            db.commit(); db.close()
            core.init_db(path)
            core.init_db(path)   # تشغيل ثانٍ لا يسبب خطأ
            db = sqlite3.connect(path)
            self.assertIn('doctor', [r[1] for r in db.execute('PRAGMA table_info(patients)')])
            self.assertEqual(db.execute('SELECT full_name FROM patients').fetchone()[0], 'قديم')
            db.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    import urllib.parse
    unittest.main(verbosity=2)
