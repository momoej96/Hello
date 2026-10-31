# -*- coding: utf-8 -*-
"""اختبارات المزامنة: لابتوبان (خادمان حقيقيان بمجلدي بيانات منفصلين) يعمل كل منهما وحده ويتبادلان التغييرات."""
import os, sys, time, shutil, tempfile, threading, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['CLINIC_SYNC_INTERVAL'] = '0.2'
import server
from test_acceptance import Client, PW
from test_xray import png


class Laptop:
    def __init__(self, data_dir, port=0):
        self.dir = data_dir
        self.srv = server.make_server(data_dir, port, lan=True)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.c = Client(self.port)

    def stop(self):
        self.srv.clinic.sync['stop'].set()
        self.srv.shutdown()
        self.srv.server_close()


def wait(fn, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except AssertionError:
            pass
        time.sleep(0.1)
    return fn()


class T40_Sync(unittest.TestCase):
    def setUp(self):
        self.da, self.db = tempfile.mkdtemp(prefix='lapA_'), tempfile.mkdtemp(prefix='lapB_')
        self.A = Laptop(self.da)
        self.A.c.setup()
        self.B = None

    def tearDown(self):
        for l in (self.A, self.B):
            if l:
                l.stop()
        shutil.rmtree(self.da, True); shutil.rmtree(self.db, True)

    def pair(self):
        a, A = self.A.c, self.A
        st = a.ok('POST', '/api/sync/enable', {})
        self.assertTrue(st['enabled']); self.assertRegex(st['key'], r'^[A-Z0-9]{4}-[A-Z0-9]{4}$')
        self.B = Laptop(self.db)
        self.B.c.setup('temp')                                           # تنصيب جديد في اللابتوب الثاني
        s, d = self.B.c.call('POST', '/api/sync/join', {'host': '127.0.0.1:%d' % A.port, 'key': st['key'].lower()})
        self.assertEqual(s, 200, d); self.assertTrue(d['relogin'])
        self.assertEqual(self.B.c.login('admin')[0], 200)                # مستخدمو اللابتوب الأول
        return st

    def test_pair_and_two_way_sync(self):
        a = self.A.c
        st = a.ok('GET', '/api/settings')['settings']
        a.ok('PUT', '/api/settings', {**st, 'doctors': ['د مرتضى', 'د منتظر'], 'xray_folder': '/sensorA'})
        p = a.ok('POST', '/api/patients', {'full_name': 'مراجع قديم', 'phone': '07700000001', 'doctor': 'د منتظر'})['patient']
        v = a.ok('POST', '/api/patients/%d/visits' % p['id'], {'visit_date': '2026-10-01', 'procedures': [{'name': 'حشوة', 'cost': 50000, 'status': 'completed', 'paid_now': 20000}]})
        img = png(shade=90)
        x = a.ok('POST', '/api/patients/%d/xrays?filename=a.png' % p['id'], raw=img)['xray']
        self.pair()
        b = self.B.c
        # النسخة الأولى: كل البيانات وصورة الأشعة
        bp = b.ok('GET', '/api/patients/%d' % p['id'])
        self.assertEqual((bp['patient']['full_name'], bp['summary']['remaining']), ('مراجع قديم', 30000))
        self.assertTrue(wait(lambda: b.call('GET', '/api/xrays/%d/image' % x['id']) == (200, img)))
        self.assertNotEqual(b.ok('GET', '/api/settings')['settings']['xray_folder'], '/sensorA')       # مجلد أشعته يبقى
        # جديد في اللابتوب الثاني: أرقام من مجاله، ويصل للأول
        q = b.ok('POST', '/api/patients', {'full_name': 'مراجع من اللابتوب الثاني', 'phone': '07700000002', 'doctor': 'د مرتضى'})['patient']
        self.assertGreater(q['id'], 5_000_000); self.assertGreater(q['file_no'], 90_000)
        bv = b.ok('POST', '/api/patients/%d/visits' % q['id'], {'visit_date': '2026-10-02', 'procedures': [{'name': 'قلع سن', 'cost': 25000, 'status': 'completed', 'paid_now': 25000}]})
        self.assertTrue(wait(lambda: a.call('GET', '/api/patients/%d' % q['id'])[0] == 200))
        aq = wait(lambda: (lambda d: d if d['summary']['net_paid'] == 25000 else None)(a.ok('GET', '/api/patients/%d' % q['id'])))
        self.assertEqual((len(aq['visits']), aq['visits'][0]['procedures'][0]['name']), (1, 'قلع سن'))
        # جديد في الأول بنفس الوقت: لا يتكرر الرقم
        r = a.ok('POST', '/api/patients', {'full_name': 'مراجع جديد في الأول', 'phone': '07700000003'})['patient']
        self.assertLess(r['id'], 5_000_000); self.assertLess(r['file_no'], 90_000)
        self.assertTrue(wait(lambda: b.call('GET', '/api/patients/%d' % r['id'])[0] == 200))
        # تعديل وحذف ودفعة على سجل قديم من الثاني
        b.ok('PUT', '/api/patients/%d' % p['id'], {'full_name': 'مراجع قديم معدّل', 'phone': '07700000001', 'doctor': 'د منتظر'})
        b.ok('POST', '/api/patients/%d/payments' % p['id'], {'pay_date': '2026-10-05', 'amount': 30000, 'method': 'cash', 'idem_key': 'k1'})
        self.assertTrue(wait(lambda: a.ok('GET', '/api/patients/%d' % p['id'])['summary']['remaining'] == 0))
        self.assertEqual(a.ok('GET', '/api/patients/%d' % p['id'])['patient']['full_name'], 'مراجع قديم معدّل')
        # الإعدادات تتزامن، أما مجلد الأشعة فلكل لابتوب
        stb = b.ok('GET', '/api/settings')['settings']
        b.ok('PUT', '/api/settings', {**stb, 'clinic_name': 'عيادة الأسنان التخصصية', 'xray_folder': '/sensorB'})
        self.assertTrue(wait(lambda: a.ok('GET', '/api/settings')['settings']['clinic_name'] == 'عيادة الأسنان التخصصية'))
        self.assertEqual(a.ok('GET', '/api/settings')['settings']['xray_folder'], '/sensorA')
        # الحالة
        s = wait(lambda: (lambda d: d if d['connected'] else None)(a.ok('GET', '/api/sync/status')))
        self.assertEqual((s['enabled'], s['device'], s['error']), (True, 0, None))
        self.assertEqual(b.ok('GET', '/api/sync/status')['device'], 1)
        # الاستعادة من نسخة احتياطية ممنوعة أثناء المزامنة
        self.assertEqual(a.call('POST', '/api/restore', raw=b'x')[0], 400)

    def test_offline_then_catch_up_and_last_edit_wins(self):
        a = self.A.c
        p = a.ok('POST', '/api/patients', {'full_name': 'مراجع مشترك', 'phone': '07711111111'})['patient']
        self.pair()
        b = self.B.c
        self.assertEqual(b.ok('GET', '/api/patients/%d' % p['id'])['patient']['full_name'], 'مراجع مشترك')
        # اللابتوب الثاني يُغلق؛ الأول يكمل شغله
        portB = self.B.port
        self.B.stop(); self.B = None
        for i in range(3):
            a.ok('POST', '/api/patients', {'full_name': 'مراجع أثناء الانقطاع %d' % i, 'phone': '0772222222%d' % i})
        self.assertTrue(wait(lambda: a.ok('GET', '/api/sync/status')['error'], 3))         # «غير متصل»
        a.ok('PUT', '/api/patients/%d' % p['id'], {'full_name': 'تعديل الأول', 'phone': '07711111111'})
        time.sleep(0.05)
        # الثاني يرجع (نفس البيانات) وكان قد عدّل نفس السجل قبل الإغلاق؟ نعدّله الآن بعد الأول: الأحدث يفوز
        self.B = Laptop(self.db, portB)
        b = self.B.c; self.assertEqual(b.login('admin')[0], 200)
        b.ok('PUT', '/api/patients/%d' % p['id'], {'full_name': 'تعديل الثاني الأحدث', 'phone': '07711111111'})
        names = lambda c: sorted(x['full_name'] for x in c.ok('GET', '/api/patients?limit=100')['patients'])
        self.assertTrue(wait(lambda: names(a) == names(b) and len(names(b)) == 4))
        self.assertTrue(wait(lambda: a.ok('GET', '/api/patients/%d' % p['id'])['patient']['full_name'] == 'تعديل الثاني الأحدث'))
        time.sleep(0.6)
        self.assertEqual(b.ok('GET', '/api/patients/%d' % p['id'])['patient']['full_name'], 'تعديل الثاني الأحدث')

    def test_conflict_while_disconnected_and_big_batch(self):
        """الجهازان يعدّلان نفس السجلين وهما منفصلان: كل سجل يأخذ آخر تعديل في الجهازين؛ ودفعة كبيرة (مثل الاستيراد) تصل كاملة"""
        a = self.A.c
        p = a.ok('POST', '/api/patients', {'full_name': 'سجل 1', 'phone': '07740000001'})['patient']
        q = a.ok('POST', '/api/patients', {'full_name': 'سجل 2', 'phone': '07740000002'})['patient']
        self.pair()
        b = self.B.c
        for L in (self.A, self.B):                                          # قطع المزامنة
            L.srv.clinic.sync['stop'].set()
        time.sleep(0.4)
        a.ok('PUT', '/api/patients/%d' % p['id'], {'full_name': 'سجل 1 من الأول', 'phone': '07740000001'})
        b.ok('PUT', '/api/patients/%d' % q['id'], {'full_name': 'سجل 2 من الثاني', 'phone': '07740000002'})
        time.sleep(0.05)
        b.ok('PUT', '/api/patients/%d' % p['id'], {'full_name': 'سجل 1 من الثاني (الأحدث)', 'phone': '07740000001'})
        a.ok('PUT', '/api/patients/%d' % q['id'], {'full_name': 'سجل 2 من الأول (الأحدث)', 'phone': '07740000002'})
        import core, sync
        db = core.connect(self.A.srv.clinic.db_path)                       # 1200 سجل دفعة واحدة في الأول
        for i in range(1200):
            db.execute('INSERT INTO patients(file_no,full_name,name_norm,phone,phone_norm,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                       (core.next_file_no(db), 'مستورد %d' % i, 'مستورد %d' % i, None, None, 'x', 'x'))
        db.close()
        for L in (self.A, self.B):                                          # رجوع الاتصال
            sync.activate(L.srv.clinic)
        name = lambda c, x: c.ok('GET', '/api/patients/%d' % x['id'])['patient']['full_name']
        self.assertTrue(wait(lambda: name(a, p) == name(b, p) == 'سجل 1 من الثاني (الأحدث)'))
        self.assertTrue(wait(lambda: name(a, q) == name(b, q) == 'سجل 2 من الأول (الأحدث)'))
        self.assertTrue(wait(lambda: len(b.ok('GET', '/api/patients?limit=5000')['patients']) == 1202, 20))

    def test_wrong_key_and_disable(self):
        self.A.c.ok('POST', '/api/sync/enable', {})
        self.B = Laptop(self.db); self.B.c.setup('temp')
        s, d = self.B.c.call('POST', '/api/sync/join', {'host': '127.0.0.1:%d' % self.A.port, 'key': 'AAAA-BBBB'})
        self.assertEqual(s, 400); self.assertIn('رمز الربط غير صحيح', d['error'])
        self.assertEqual(self.B.c.ok('GET', '/api/session')['user']['username'], 'temp')          # بياناته لم تتغير
        self.A.c.ok('POST', '/api/sync/disable', {})
        self.assertFalse(self.A.c.ok('GET', '/api/sync/status')['enabled'])
        p = self.A.c.ok('POST', '/api/patients', {'full_name': 'بعد الإيقاف', 'phone': '07733333333'})['patient']
        self.assertLess(p['id'], 100)                                       # الترقيم عاد كما كان


if __name__ == '__main__':
    unittest.main()
