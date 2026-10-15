# -*- coding: utf-8 -*-
"""اختبارات الاستيراد من Excel ووضع الشبكة (تعمل على الخادم الحقيقي)."""
import os, sys, io, datetime, sqlite3, unittest, urllib.request, urllib.error, threading, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openpyxl
from test_acceptance import Base, Client, PW
import server

D = datetime.datetime
HDR1 = ['اسم المراجع ', 'تاريخ اخر المراجعة ', 'نوع العمل ', 'رقم السن', 'المدفوع ', 'المبلغ المتبقي', 'الملاحظات', 'عمود8']
HDR2 = ['اسم المراجع ', 'تاريخ اخر المراجعة ', 'نوع العمل ', 'رقم السن', 'المدفوع ', 'الباقي', 'الملاحظات', None]


def make_xlsx(sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
        ws.cell(row=1, column=100).value = 'x'      # عمود بعيد يجب تجاهله
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


ROWS_2022 = [HDR1, HDR2,
    ['علي حسن ', '25/1', 'ج1', 'LL6', 100, 400, 'mb=20', None],              # تكلفة 500، متبقي 400
    ['علي  حسن', '26/1', 'تسديد', None, 150, None, None, None],               # دفعة فقط → متبقي 250
    ['عليّ حسن', '27/1', 'ضوئية', 'ur123', 100, 150, None, None],              # تكلفة جديدة 0 + متبقي 150 (الاسم بتشكيل)
    ['علي حسن', '27/1', 'ضوئية', 'ur123', 100, 150, None, None],              # مكرر تماماً
    ['زينب علي', '13/7', 'قلع', 'lre', 20, None, None, None],
    ['زينب علي', D(2022, 3, 7), 'ج4', 'ul3+4', 30, None, None, None],          # حقيقته 3 تموز (مقلوب)
    ['زينب علي', '15/7', 'تنظيف', None, 15, None, None, None],
    ['زينب علي', D(2022, 7, 5), 'تنظيف', 'u11', 15, None, None, None],         # 5 تموز فعلاً
    ['سالب', '5/2', 'ج1', 'ul6', -250, None, None, None],                     # مرفوض
    [None, '5/2', 'ج1', 'ul6', 25, None, None, None],                         # بدون اسم
    ['بدون تاريخ', None, 'ج1', 'ul6', 25, None, None, None],
    ['اسماء احمد', '1/2', 'فحص', 'zz9', 10, None, 'ملاحظة', 20.5],            # اسم يبدأ بـ «اسم» ليس عنواناً
]
ROWS_2023 = [['اسم المراجع', 'التاريخ', 'نوع العمل', 'رقم السن', 'المدفوع', 'المتبقي', 'عمود7', 'عمود8'],
    ['علي حسن', D(2023, 1, 2), 'ج2', 'lr6', 50, None, 'مرجع', None]]


class T20_Import(Base):
    def preview(self, data=None, mult=1000, name='x.xlsx'):
        data = data or make_xlsx({'2022': ROWS_2022, '2023': ROWS_2023})
        return self.c.ok('POST', '/api/import/preview?mult=%d&filename=%s' % (mult, name), raw=data)

    def test_preview_and_commit(self):
        pre = self.preview()
        s = pre['summary']
        self.assertEqual((s['duplicates_in_file'], s['rows_skipped'], s['patients']), (1, 3, 3))
        self.assertEqual(s['skipped_by_reason'], {'بدون اسم صالح': 1, 'مبلغ مدفوع سالب': 1, 'بدون تاريخ': 1})
        self.assertGreaterEqual(s['date_fixed'], 1)
        self.assertEqual(s['total_paid'], (100 + 150 + 100 + 20 + 30 + 15 + 15 + 10 + 50) * 1000)
        self.assertEqual(self.c.call('GET', '/api/patients')[1]['patients'], [])     # المعاينة لا تُدخل شيئاً
        r = self.c.ok('POST', '/api/import/commit', {'token': pre['token']})
        self.assertTrue(r['backup'].startswith('pre_import_'))
        res = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('علي حسن'))['patients']
        self.assertEqual(len(res), 1)                              # كل صيغ الاسم دُمجت بملف واحد
        pid = res[0]['id']
        full = self.c.ok('GET', '/api/patients/%d' % pid)
        # الرصيد: 500 تكلفة − 100 −150 دفعات ... = آخر «متبقي» مكتوب (150) ثم دفعة 50 لاحقة بلا متبقٍ = 150
        self.assertEqual(full['summary']['remaining'], 150000)
        self.assertEqual(full['summary']['paid'], (100 + 150 + 100 + 50) * 1000)
        teeth = {p['tooth_no'] for v in full['visits'] for p in v['procedures']}
        self.assertIn('46', teeth); self.assertIn('36', teeth)      # LL6 → 36 ، lr6 → 46
        multi = [p for v in full['visits'] for p in v['procedures'] if p['name'] == 'حشوة دائمية - ضوئية'][0]
        self.assertEqual(multi['tooth_no'], '11,12,13')            # عدة أسنان لنفس الإجراء
        self.assertTrue(any(p['name'] == 'حشوة جذر (عصب)' and 'mb=20' in (p['details'] or '') and 'ج1' in p['details'] for v in full['visits'] for p in v['procedures']))
        self.assertEqual(len(full['payments']), 4)                  # التسديد دفعة بدون زيارة
        self.assertEqual(sorted(v['visit_date'] for v in full['visits'])[0], '2022-01-25')
        # زينب: تاريخ مقلوب صُحّح إلى 3 تموز، وسن الأطفال lre → 85
        z = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('زينب'))['patients'][0]
        zf = self.c.ok('GET', '/api/patients/%d' % z['id'])
        self.assertIn('2022-07-03', [v['visit_date'] for v in zf['visits']])
        self.assertNotIn('2022-03-07', [v['visit_date'] for v in zf['visits']])
        self.assertIn('2022-07-05', [v['visit_date'] for v in zf['visits']])
        self.assertIn('85', {p['tooth_no'] for v in zf['visits'] for p in v['procedures']})
        self.assertIn('11,21', {p['tooth_no'] for v in zf['visits'] for p in v['procedures']})   # u11 → 11 و 21
        self.assertEqual(zf['summary']['remaining'], 0)
        # اسم يبدأ بـ «اسم» استُورد كمراجع، وسن غير مفهوم حُفظ نصاً
        a = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('اسماء'))['patients'][0]
        af = self.c.ok('GET', '/api/patients/%d' % a['id'])
        self.assertIn('zz9', af['visits'][0]['procedures'][0]['details']); self.assertIn('20.5', af['visits'][0]['procedures'][0]['details'])
        # تدقيق ودفاتر
        rep = self.c.ok('GET', '/api/reports/period?from=2022-01-01&to=2023-12-31')['stats']
        self.assertEqual(rep['receipts'], s['total_paid'])
        self.assertEqual(self.c.ok('GET', '/api/audit?entity=import')['rows'][0]['action'], 'import')

    def test_bill_rows_reduce_balance_and_upper_lower_teeth(self):
        """صفوف «bill» و«تسديد» تُطرح من حساب المراجع، وU11/L66 تُفهم كعدة أسنان"""
        rows = [HDR1,
                ['حيدر كاظم', '2/3', 'تاج', 'U11', 100, 400, None, None],     # تكلفة 500، متبقي 400
                ['حيدر كاظم', '9/3', 'bill', None, 150, None, None, None],     # يُطرح → 250
                ['حيدر كاظم', '16/3', 'Bill', None, 200, None, None, None],    # يُطرح → 50
                ['حيدر كاظم', '20/3', 'تسديد', None, 50, None, None, None],    # يُطرح → 0
                ['حيدر كاظم', '25/3', 'حشوة', 'L66', 60, 0, None, None],       # عمل جديد مدفوع بالكامل
                ['حيدر كاظم', '26/3', 'billing', None, 10, None, None, None]]   # ليس تسديداً: عمل جديد
        pre = self.preview(make_xlsx({'2024': rows}))
        s = pre['summary']
        self.assertEqual((s['payment_rows'], s['payment_rows_total']), (3, 400000))
        self.assertEqual(s['outstanding_total'], 0)
        self.c.ok('POST', '/api/import/commit', {'token': pre['token']})
        pid = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('حيدر'))['patients'][0]['id']
        full = self.c.ok('GET', '/api/patients/%d' % pid)
        self.assertEqual(full['summary']['remaining'], 0)
        self.assertEqual(full['summary']['total_cost'], (500 + 60 + 10) * 1000)    # التسديدات لم تُحسب أعمالاً
        self.assertEqual(full['summary']['paid'], (100 + 150 + 200 + 50 + 60 + 10) * 1000)
        names = sorted(p['name'] for v in full['visits'] for p in v['procedures'])
        self.assertEqual(names, ['billing', 'تاج', 'حشوة'])
        teeth = {p['name']: p['tooth_no'] for v in full['visits'] for p in v['procedures']}
        self.assertEqual((teeth['تاج'], teeth['حشوة']), ('11,21', '46,36'))

    def test_visit_with_several_teeth(self):
        """اختيار أكثر من سن لنفس الإجراء داخل الزيارة"""
        p = self.patient()
        v = self.visit(p['id'], '2025-02-01', [{'name': 'تبييض', 'tooth_no': '11, 21 ،22', 'cost': 90000},
                                               {'name': 'خلع', 'tooth_no': ['48', '38'], 'cost': 40000},
                                               {'name': 'حشوة', 'tooth_no': '١٦', 'cost': 30000}])['visit']
        self.assertEqual([x['tooth_no'] for x in v['procedures']], ['11,21,22', '48,38', '16'])
        s, d = self.c.call('POST', '/api/patients/%d/visits' % p['id'], {'visit_date': '2025-02-02', 'procedures': [{'name': 'x', 'tooth_no': '11,19'}]})
        self.assertEqual(s, 400); self.assertIn('19', d['error'])
        proc = v['procedures'][0]
        self.c.ok('PUT', '/api/procedures/%d' % proc['id'], {'tooth_no': '11'})
        self.assertEqual(self.c.ok('GET', '/api/patients/%d' % p['id'])['visits'][0]['procedures'][0]['tooth_no'], '11')

    def test_sheets_per_doctor(self):
        """كل شيت يُنسب لطبيبه: الشغل والدفعات والأرصدة معزولة لكل طبيب، والشيت المشترك يبقى «غير محدد»"""
        import json
        st = self.c.ok('GET', '/api/settings')['settings']
        self.c.ok('PUT', '/api/settings', {**st, 'doctors': ['د. مرتضى', 'د. منتظر']})
        H = ['اسم المراجع', 'التاريخ', 'نوع العمل', 'رقم السن', 'المدفوع', 'المتبقي']
        data = make_xlsx({
            '2022-2024': [H, ['علي حسن', D(2023, 1, 15), 'تاج', 'ur6', 100, 400], ['زينب علي', D(2023, 2, 20), 'تنظيف', None, 100, 0]],
            'مرتضى 2025': [H, ['علي حسن', D(2025, 1, 15), 'حشوة', 'U11', 100, 400],     # يكمل الرصيد المشترك 400 → تكلفة 100
                           ['علي حسن', D(2025, 1, 20), 'bill', None, 100, None]],        # → 300 عند مرتضى
            'منتظر 2025': [H, ['علي حسن', D(2025, 1, 18), 'تنظيف', None, 20, 30],      # دفتر منفصل → تكلفة 50
                           ['سارة كاظم', D(2025, 2, 1), 'تاج', 'll6', 200, 0]]})
        q = '/api/import/preview?mult=1000&filename=x.xlsx'
        pre = self.c.ok('POST', q, raw=data)
        docs = {s['name']: s['doctor'] for s in pre['summary']['sheets']}
        self.assertEqual(docs, {'2022-2024': '', 'مرتضى 2025': 'د. مرتضى', 'منتظر 2025': 'د. منتظر'})   # مطابقة تلقائية
        self.assertEqual(pre['summary']['outstanding_total'], (300 + 30) * 1000)
        self.assertTrue(any('انتقل إلى حساب د. مرتضى' in r['reason'] for r in pre['review']))
        # اختيار يدوي يلغي المطابقة: نجعل شيت منتظر مشتركاً ثم نعيده
        pre2 = self.c.ok('POST', q + '&doctors=' + urllib.parse.quote(json.dumps({'منتظر 2025': ''})), raw=data)
        self.assertEqual({s['name']: s['doctor'] for s in pre2['summary']['sheets']}['منتظر 2025'], '')
        self.c.ok('POST', '/api/import/commit', {'token': pre['token']})
        ali = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('علي حسن'))['patients'][0]
        full = self.c.ok('GET', '/api/patients/%d' % ali['id'])
        self.assertEqual(full['patient']['doctor'], 'د. مرتضى')
        self.assertEqual(full['summary']['remaining'], 330000)
        procs = {p['name']: (p['doctor'], p['tooth_no']) for v in full['visits'] for p in v['procedures']}
        self.assertEqual(procs['حشوة'], ('د. مرتضى', '11,21'))
        self.assertEqual(procs['تنظيف'][0], 'د. منتظر')
        sara = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('سارة'))['patients'][0]
        self.assertEqual(sara['doctor'], 'د. منتظر')
        zainab = self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('زينب'))['patients'][0]
        self.assertIsNone(zainab['doctor'])
        rows = {r['doctor']: r for r in self.c.ok('GET', '/api/reports/period?from=2025-01-01&to=2025-12-31')['by_doctor']}
        self.assertEqual((rows['د. مرتضى']['executed'], rows['د. مرتضى']['receipts']), (100000, 200000))
        self.assertEqual((rows['د. منتظر']['executed'], rows['د. منتظر']['receipts']), (250000, 220000))
        # الشيت المشترك لا يُنسب لمرتضى رغم أن علي صار مراجعه
        old = {r['doctor']: r for r in self.c.ok('GET', '/api/reports/period?from=2022-01-01&to=2024-12-31')['by_doctor']}
        self.assertEqual(set(old), {'غير محدد'})
        self.assertEqual((old['غير محدد']['executed'], old['غير محدد']['receipts']), (600000, 200000))

    def test_work_types_are_merged(self):
        """توحيد أنواع العمل المكتوبة بأشكال مختلفة تحت إجراء واحد، مع حفظ المكتوب في التفاصيل"""
        H = ['اسم المراجع', 'التاريخ', 'نوع العمل', 'رقم السن', 'المدفوع', 'المتبقي']
        works = {'X ray': 'أشعة', 'xray': 'أشعة', 'اشعه': 'أشعة', 'ج1': 'حشوة جذر (عصب)', 'ج 3': 'حشوة جذر (عصب)', 'indo': 'حشوة جذر (عصب)',
                 'اندو': 'حشوة جذر (عصب)', 'ازالة خيط': 'معالجة بعد القلع', 'رفع خيط': 'معالجة بعد القلع', 'iregation': 'معالجة بعد القلع',
                 'Dry socket': 'معالجة بعد القلع', 'plupotic': 'حشوة مؤقتة - اعتيادية', 'tf': 'حشوة مؤقتة - اعتيادية',
                 'مؤقته': 'حشوة مؤقتة - اعتيادية', 'GIC': 'حشوة مؤقتة - علاجية (GIC)', 'prep': 'جسر أسنان', 'impression': 'جسر أسنان',
                 're impression': 'جسر أسنان', 'طبعة': 'جسر أسنان', 'تحظير': 'جسر أسنان', 'fixation': 'جسر أسنان', 'تثبيت': 'جسر أسنان',
                 'amalgam': 'حشوة دائمية - معدنية', 'amlgam': 'حشوة دائمية - معدنية', 'بلاتين': 'حشوة دائمية - معدنية',
                 'ضوئية': 'حشوة دائمية - ضوئية', 'composite': 'حشوة دائمية - ضوئية', 'composet': 'حشوة دائمية - ضوئية',
                 'exo': 'قلع سن', 'قلع': 'قلع سن', 'تاج': 'تاج'}
        rows = [H] + [['مراجع %d' % i, D(2024, 1, 1 + i), w, None, 10, 0] for i, w in enumerate(works)]
        pre = self.preview(make_xlsx({'2024': rows}))
        groups = {g['name']: dict(g['variants']) for g in pre['work_merged']}
        self.assertEqual(groups['جسر أسنان'], {w: 1 for w, n in works.items() if n == 'جسر أسنان'})
        self.assertNotIn('تاج', groups)
        self.c.ok('POST', '/api/import/commit', {'token': pre['token']})
        got = {}
        ids = {p['full_name']: p['id'] for p in self.c.ok('GET', '/api/patients?limit=500')['patients']}
        for i, w in enumerate(works):
            pid = ids['مراجع %d' % i]
            pr = self.c.ok('GET', '/api/patients/%d' % pid)['visits'][0]['procedures'][0]
            got[w] = pr['name']
            if pr['name'] != w and w != 'اشعه':
                self.assertIn(w, pr['details'])                    # المكتوب الأصلي محفوظ
        self.assertEqual(got, works)
        names = {p['name'] for p in self.c.ok('GET', '/api/reports/period?from=2024-01-01&to=2024-12-31')['by_procedure']}
        self.assertEqual(names, set(works.values()))               # التقرير يجمعها تحت أسماء موحدة

    def test_reimport_is_idempotent_and_merges_with_existing(self):
        existing = self.patient('علي حسن', '07700001111')
        pre = self.preview()
        self.assertEqual(pre['summary']['patients_existing'], 1)
        self.c.ok('POST', '/api/import/commit', {'token': pre['token']})
        self.assertEqual(len(self.c.ok('GET', '/api/patients?q=' + urllib.parse.quote('علي حسن'))['patients']), 1)
        self.assertEqual(len(self.c.ok('GET', '/api/patients/%d' % existing['id'])['payments']), 4)
        again = self.preview()
        self.assertEqual((again['summary']['rows_imported'], again['summary']['duplicates_previous']), (0, 10))
        s, d = self.c.call('POST', '/api/import/commit', {'token': again['token']})
        self.assertEqual(s, 400)
        n = len(self.c.ok('GET', '/api/patients?limit=500')['patients'])
        self.assertEqual(n, 3)
        # ملف إضافي فيه صف جديد وصف قديم → يدخل الجديد فقط
        more = make_xlsx({'2022': ROWS_2022 + [['علي حسن', '30/1', 'ج3', 'ur6', 10, None, None, None]], '2023': ROWS_2023})
        p3 = self.preview(more)
        self.assertEqual(p3['summary']['rows_imported'], 1)
        self.c.ok('POST', '/api/import/commit', {'token': p3['token']})
        self.assertEqual(len(self.c.ok('GET', '/api/patients/%d' % existing['id'])['payments']), 5)

    def test_multiplier_bad_file_and_permissions(self):
        pre = self.preview(mult=1)
        self.assertEqual(pre['summary']['total_paid'], 100 + 150 + 100 + 20 + 30 + 15 + 15 + 10 + 50)
        s, d = self.c.call('POST', '/api/import/preview?mult=1000', raw=b'this is not a spreadsheet at all')
        self.assertEqual(s, 200)       # يُقرأ كـ CSV ولا يجد عناوين، فلا صفوف صالحة
        self.assertEqual(d['summary']['rows_imported'], 0)
        self.assertEqual(self.c.call('POST', '/api/import/preview?mult=7', raw=b'x')[0], 400)
        self.c.ok('POST', '/api/users', {'username': 'rec9', 'password': PW, 'role': 'reception'})
        rec = Client(self.srv.server_address[1]); rec.login('rec9')
        self.assertEqual(rec.call('POST', '/api/import/preview?mult=1000', raw=make_xlsx({'2022': ROWS_2022}))[0], 403)
        self.assertEqual(rec.call('POST', '/api/import/commit', {'token': 'x'})[0], 403)

    def test_csv_import(self):
        csv_bytes = ('اسم المراجع,التاريخ,نوع العمل,رقم السن,المدفوع,المتبقي\nسارة كريم,2024-03-05,حشوة,ur6,25,\nسارة كريم,2024-03-05,حشوة,ur6,25,\n').encode('utf-8-sig')
        pre = self.c.ok('POST', '/api/import/preview?mult=1000&filename=a.csv', raw=csv_bytes)
        self.assertEqual((pre['summary']['rows_imported'], pre['summary']['duplicates_in_file']), (1, 1))
        self.c.ok('POST', '/api/import/commit', {'token': pre['token']})
        self.assertEqual(self.c.ok('GET', '/api/reports/debtors')['total_dues'], 0)


class T21_LanMode(unittest.TestCase):
    def test_lan_mode_host_rules(self):
        tmp = tempfile.mkdtemp(prefix='clinic_lan_')
        srv = server.make_server(tmp, 0, lan=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        try:
            c = Client(port); c.setup()
            s = c.ok('GET', '/api/session')
            self.assertTrue(s['lan'])
            for host, code in [('192.168.1.20:%d' % port, 200), ('10.0.0.5:%d' % port, 200), ('localhost:%d' % port, 200), ('evil.example.com', 403), ('8.8.8.8', 403)]:
                req = urllib.request.Request('http://127.0.0.1:%d/api/session' % port, headers={'Host': host})
                try:
                    code_got = urllib.request.urlopen(req).status
                except urllib.error.HTTPError as e:
                    code_got = e.code
                self.assertEqual(code_got, code, host)
            # بدون وضع الشبكة: عنوان خاص مرفوض
            tmp2 = tempfile.mkdtemp(prefix='clinic_nolan_')
            srv2 = server.make_server(tmp2, 0)
            threading.Thread(target=srv2.serve_forever, daemon=True).start()
            req = urllib.request.Request('http://127.0.0.1:%d/api/session' % srv2.server_address[1], headers={'Host': '192.168.1.20'})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 403)
            self.assertEqual(srv2.server_address[0], '127.0.0.1'); self.assertEqual(srv.server_address[0], '0.0.0.0')
            srv2.shutdown(); srv2.server_close(); shutil.rmtree(tmp2, ignore_errors=True)
        finally:
            srv.shutdown(); srv.server_close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_two_laptops_share_data_concurrently(self):
        tmp = tempfile.mkdtemp(prefix='clinic_two_')
        srv = server.make_server(tmp, 0, lan=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        try:
            a, b = Client(port), Client(port); a.setup()
            a.ok('POST', '/api/users', {'username': 'lap2', 'password': PW, 'role': 'reception'})
            self.assertEqual(b.login('lap2')[0], 200)
            ids = []
            def add(cl, n):
                for i in range(15):
                    s, d = cl.call('POST', '/api/patients', {'full_name': 'مراجع %s %d' % (n, i), 'phone': '0780%07d' % (i + (1000 if n == 'ب' else 0))})
                    ids.append((s, d['patient']['file_no'] if s == 200 else d))
            ts = [threading.Thread(target=add, args=(a, 'أ')), threading.Thread(target=add, args=(b, 'ب'))]
            [t.start() for t in ts]; [t.join() for t in ts]
            self.assertTrue(all(s == 200 for s, _ in ids))
            nums = [n for _, n in ids]
            self.assertEqual(len(set(nums)), 30)                       # أرقام ملفات فريدة رغم التزامن من جهازين
            self.assertEqual(len(a.ok('GET', '/api/patients?limit=500')['patients']), 30)
            self.assertEqual(len(b.ok('GET', '/api/patients?limit=500')['patients']), 30)   # الجهازان يريان نفس البيانات
        finally:
            srv.shutdown(); srv.server_close(); shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
