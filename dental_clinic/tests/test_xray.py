# -*- coding: utf-8 -*-
"""اختبارات صور الأشعة: الاستقبال التلقائي من مجلد برنامج السنسر، الرفع اليدوي، الصلاحيات، الدمج والحذف."""
import os, sys, time, shutil, tempfile, unittest, struct, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_acceptance import Base, Client, PW


def png(w=4, h=3, shade=100, depth=8):
    px = bytes([shade]) if depth == 8 else bytes([shade, 0])
    raw = b''.join(b'\x00' + px * w for _ in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, depth, 0, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def write(path, data, age=5):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    t = time.time() - age            # كأن برنامج السنسر أنهى الحفظ قبل ثوانٍ
    os.utime(path, (t, t))


class T30_Xray(Base):
    def setUp(self):
        super().setUp()
        self.sensor = tempfile.mkdtemp(prefix='woodpecker_')
        st = self.c.ok('GET', '/api/settings')['settings']
        self.c.ok('PUT', '/api/settings', {**st, 'xray_folder': self.sensor})

    def tearDown(self):
        shutil.rmtree(self.sensor, ignore_errors=True)
        super().tearDown()

    def test_capture_from_sensor_folder(self):
        p = self.patient()
        write(os.path.join(self.sensor, '7', 'old.png'), png(shade=10), age=100)        # صورة قديمة لمراجع آخر: لا تُضاف
        chk = self.c.ok('GET', '/api/xray_folder_check?folder=' + self.sensor)
        self.assertEqual((chk['ok'], chk['count']), (True, 1))
        st = self.c.ok('POST', '/api/patients/%d/xray_capture' % p['id'], {})
        r = self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})
        self.assertEqual((r['active'], r['new']), (True, []))
        img = png(shade=200)
        write(os.path.join(self.sensor, '12', '2026', 'IMG_0001.png'), img)                # مجلد فرعي مرقّم
        write(os.path.join(self.sensor, '12', 'IMG_0001_thumb.png'), png(shade=5))        # مصغّرة: تُتجاهل
        write(os.path.join(self.sensor, '12', 'notes.txt'), b'x')                         # ليست صورة
        write(os.path.join(self.sensor, '12', 'fresh.png'), png(shade=50), age=0)         # ما زالت تُكتب: تنتظر
        r = self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})
        self.assertEqual(len(r['new']), 1)
        self.assertEqual(r['new'][0]['source'], 'sensor')
        time.sleep(3.2)
        r = self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})
        self.assertEqual(len(r['new']), 1)                                                  # fresh.png بعد اكتمالها
        r = self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})
        self.assertEqual(r['new'], [])                                                      # لا تكرار
        self.c.ok('POST', '/api/xray_capture/%s/stop' % st['token'], {})
        self.assertFalse(self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})['active'])
        xs = self.c.ok('GET', '/api/patients/%d' % p['id'])['xrays']
        self.assertEqual(len(xs), 2)
        s, data = self.c.call('GET', '/api/xrays/%d/image' % [x for x in xs if x['source'] == 'sensor'][-1]['id'])
        self.assertEqual(s, 200)
        self.assertIn(data, (img, png(shade=50)))
        self.assertTrue(os.path.exists(os.path.join(self.sensor, '12', '2026', 'IMG_0001.png')))   # الأصل باقٍ
        # استقبال لمراجع آخر يوقف الجلسة السابقة (صورة واحدة لمراجع واحد بلا لبس)
        q = self.patient('مراجع ثاني', '07702223333')
        st1 = self.c.ok('POST', '/api/patients/%d/xray_capture' % p['id'], {})
        st2 = self.c.ok('POST', '/api/patients/%d/xray_capture' % q['id'], {})
        self.assertEqual(st2['replaced'][0]['full_name'], p['full_name'])
        self.assertFalse(self.c.ok('POST', '/api/xray_capture/%s/poll' % st1['token'], {})['active'])

    def test_one_image_per_sensor_shot(self):
        """Woodpecker يحفظ لكل لقطة 3 صور (مصغّرة، عادية، خام بيضاء 16 بت): تُضاف العادية فقط"""
        p = self.patient()
        st = self.c.ok('POST', '/api/patients/%d/xray_capture' % p['id'], {})
        normal = png(400, 300, shade=90)
        write(os.path.join(self.sensor, '20', '1001_s.png'), png(40, 30, shade=90))          # مصغّرة
        write(os.path.join(self.sensor, '20', '1001.png'), normal)                           # العادية
        write(os.path.join(self.sensor, '20', '1001_o.png'), png(400, 300, shade=250, depth=16))   # الخام
        r = self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})
        self.assertEqual((len(r['new']), r['skipped']), (1, 2))
        self.assertEqual(self.c.call('GET', '/api/xrays/%d/image' % r['new'][0]['id'])[1], normal)
        # لقطة ثانية بعد قليل في نفس المجلد: صورتان 8 بت بنفس الأبعاد، البيضاء تُستبعد
        dark = png(300, 200, shade=70)
        write(os.path.join(self.sensor, '20', '1002.png'), dark, age=4)
        write(os.path.join(self.sensor, '20', '1002_raw.png'), png(300, 200, shade=245), age=4)
        r = self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})
        self.assertEqual(len(r['new']), 1)
        self.assertEqual(self.c.call('GET', '/api/xrays/%d/image' % r['new'][0]['id'])[1], dark)
        # ملفات لقطة ما زالت تُحفظ (أحدثها قبل أقل من 3 ثوانٍ): لا يُختار منها شيء بعد
        write(os.path.join(self.sensor, '20', '1003.png'), png(300, 200, shade=60), age=1)
        self.assertEqual(self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})['new'], [])

    def test_missing_folder_upload_edit_permissions(self):
        p = self.patient()
        st = self.c.ok('GET', '/api/settings')['settings']
        self.c.ok('PUT', '/api/settings', {**st, 'xray_folder': os.path.join(self.sensor, 'nope')})
        s, d = self.c.call('POST', '/api/patients/%d/xray_capture' % p['id'], {})
        self.assertEqual(s, 400); self.assertIn('غير موجود', d['error'])
        img = png(shade=77)
        x = self.c.ok('POST', '/api/patients/%d/xrays?filename=old.png&date=2024-05-01&tooth=36' % p['id'], raw=img)['xray']
        self.assertEqual((x['source'], x['taken_at'][:10], x['tooth_no']), ('upload', '2024-05-01', '36'))
        self.assertEqual(self.c.call('POST', '/api/patients/%d/xrays?filename=a.png' % p['id'], raw=b'not an image')[0], 400)
        self.c.ok('PUT', '/api/xrays/%d' % x['id'], {'tooth_no': '11, 21', 'notes': 'قبل العلاج'})
        self.assertEqual(self.c.ok('GET', '/api/patients/%d/xrays' % p['id'])['xrays'][0]['tooth_no'], '11,21')
        # الطبيب يرى ويضيف، لكن الحذف للمدير فقط؛ والمستخدم غير المسجّل لا يرى الصورة
        self.c.ok('POST', '/api/users', {'username': 'doc1', 'password': PW, 'role': 'doctor'})
        doc = Client(self.srv.server_address[1]); doc.login('doc1')
        self.assertEqual(doc.call('GET', '/api/xrays/%d/image' % x['id'])[0], 200)
        self.assertEqual(doc.call('DELETE', '/api/xrays/%d' % x['id'], {})[0], 403)
        self.assertEqual(Client(self.srv.server_address[1]).call('GET', '/api/xrays/%d/image' % x['id'])[0], 401)
        self.c.ok('DELETE', '/api/xrays/%d' % x['id'], {})
        self.assertEqual(self.c.call('GET', '/api/xrays/%d/image' % x['id'])[0], 404)

    def test_xrays_linked_to_visits(self):
        """الصورة تُربط بالزيارة: المحددة عند الاستقبال، أو زيارة نفس اليوم، ويمكن تغيير الربط"""
        import datetime
        p = self.patient()
        q = self.patient('مراجع آخر', '07700000009')
        today = datetime.date.today().isoformat()
        old = self.visit(p['id'], '2024-01-10', [{'name': 'حشوة جذر (عصب)', 'tooth_no': '16', 'cost': 130000}])['visit']
        # استقبال من زيارة محددة (قديمة): الصورة تذهب لها رغم أن التاريخ مختلف
        st = self.c.ok('POST', '/api/patients/%d/xray_capture' % p['id'], {'visit_id': old['id']})
        write(os.path.join(self.sensor, '1', 'a.png'), png(shade=1))
        x1 = self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})['new'][0]
        self.assertEqual(x1['visit_id'], old['id'])
        # استقبال من رأس الملف: يُربط بزيارة اليوم إن وُجدت (حتى لو أُضيفت الزيارة بعد بدء الاستقبال)
        st = self.c.ok('POST', '/api/patients/%d/xray_capture' % p['id'], {})
        write(os.path.join(self.sensor, '1', 'b.png'), png(shade=2))
        self.assertIsNone(self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})['new'][0]['visit_id'])
        now_v = self.visit(p['id'], today, [{'name': 'أشعة', 'cost': 0}])['visit']
        write(os.path.join(self.sensor, '1', 'c.png'), png(shade=3))
        self.assertEqual(self.c.ok('POST', '/api/xray_capture/%s/poll' % st['token'], {})['new'][0]['visit_id'], now_v['id'])
        # زيارة مراجع آخر مرفوضة
        self.assertEqual(self.c.call('POST', '/api/patients/%d/xray_capture' % p['id'], {'visit_id': self.visit(q['id'], today, [])['visit']['id']})[0], 400)
        # الرفع اليدوي بتاريخ زيارة يُربط بها؛ وتغيير الربط من العارض
        up = self.c.ok('POST', '/api/patients/%d/xrays?filename=x.png&date=2024-01-10' % p['id'], raw=png())['xray']
        self.assertEqual(up['visit_id'], old['id'])
        self.c.ok('PUT', '/api/xrays/%d' % up['id'], {'visit_id': now_v['id']})
        self.c.ok('PUT', '/api/xrays/%d' % x1['id'], {'visit_id': ''})
        xs = {x['id']: x['visit_id'] for x in self.c.ok('GET', '/api/patients/%d' % p['id'])['xrays']}
        self.assertEqual((xs[up['id']], xs[x1['id']]), (now_v['id'], None))
        # حذف الزيارة لا يحذف صورها، بل يفك الربط فقط
        self.c.ok('DELETE', '/api/visits/%d' % now_v['id'], {})
        xs = self.c.ok('GET', '/api/patients/%d' % p['id'])['xrays']
        self.assertEqual(len(xs), 4)
        self.assertEqual([x['visit_id'] for x in xs], [None] * 4)      # كانت مرتبطة بزيارة اليوم المحذوفة أو بلا ربط

    def test_merge_and_delete_patient_carry_xrays(self):
        a = self.patient('زينب وليد', '07701112222')
        b = self.patient('زينب وليد مجيد')
        self.c.ok('POST', '/api/patients/%d/xrays?filename=b.png' % b['id'], raw=png())
        self.c.ok('POST', '/api/patients/%d/merge' % a['id'], {'other_id': b['id']})
        xs = self.c.ok('GET', '/api/patients/%d/xrays' % a['id'])['xrays']
        self.assertEqual(len(xs), 1)
        self.assertEqual(self.c.call('GET', '/api/xrays/%d/image' % xs[0]['id'])[0], 200)   # الصورة تُعرض بعد الدمج
        self.c.ok('DELETE', '/api/patients/%d' % a['id'], {})
        self.assertEqual(self.c.call('GET', '/api/xrays/%d/image' % xs[0]['id'])[0], 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
