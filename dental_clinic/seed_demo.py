# -*- coding: utf-8 -*-
"""بيانات تجريبية وهمية. تُكتب فقط في مجلد demo_data المنفصل، ولا تلمس بيانات العيادة الحقيقية."""
import json, random
from datetime import date, timedelta
from core import connect, norm_ar, canon_phone, now_iso, audit

NAMES = ['أحمد حسين علي', 'سارة محمد كاظم', 'عبد الله ياسر جاسم', 'زينب علي حسن', 'مصطفى عدنان رشيد',
         'نور الهدى حيدر', 'حسن فاضل عباس', 'ريم أحمد صالح', 'يوسف كريم ناصر', 'مريم عماد الدين',
         'علي جبار هادي', 'فاطمة الزهراء كاظم', 'محمد باسم خليل', 'هدى سلمان داود', 'كرار حسنين عودة',
         'آية رعد منصور', 'عمر طارق سعيد', 'دعاء ماجد فرحان', 'سجاد ليث مهدي', 'رنا وليد جواد']
PROCS = [('فحص وتشخيص', 15000, None), ('تنظيف الأسنان', 35000, None), ('حشوة تجميلية', 60000, 'tooth'),
         ('حشوة عصب', 120000, 'tooth'), ('تاج (تلبيس)', 150000, 'tooth'), ('خلع سن', 40000, 'tooth'),
         ('زراعة سن', 700000, 'tooth'), ('تبييض الأسنان', 250000, None), ('تقويم أسنان', 1500000, None)]
TEETH = [11, 12, 16, 21, 24, 26, 36, 37, 46, 47]
DOCTORS = ['د. علي حسن', 'د. سارة كريم', 'د. محمد جاسم']
CATS = ['مواد طب الأسنان', 'أجور المختبر', 'الإيجار', 'الرواتب', 'الكهرباء والإنترنت', 'صيانة الأجهزة']


def seed_if_empty(clinic):
    db = connect(clinic.db_path)
    try:
        if db.execute('SELECT COUNT(*) FROM patients').fetchone()[0] > 0:
            return False
        rnd = random.Random(7)
        today = date.today()
        db.execute('BEGIN')
        now = now_iso()
        db.execute("UPDATE settings SET value=? WHERE key='doctors'", (json.dumps(DOCTORS, ensure_ascii=False),))
        for i, name in enumerate(NAMES):
            doc = DOCTORS[i % len(DOCTORS)]
            first = today - timedelta(days=rnd.randint(20, 420))
            phone = '0770%07d' % rnd.randint(1000000, 9999999)
            cur = db.execute('INSERT INTO patients(file_no,full_name,name_norm,phone,phone_norm,age,gender,first_visit_date,notes,doctor,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                             (1001 + i, name, norm_ar(name), phone, canon_phone(phone), rnd.randint(8, 70),
                              rnd.choice('MF'), first.isoformat(), 'بيانات تجريبية', doc, now, now))
            pid = cur.lastrowid
            vday = first
            for _ in range(rnd.randint(1, 4)):
                if vday > today:
                    break
                v = db.execute('INSERT INTO visits(patient_id,visit_date,visit_time,doctor,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                               (pid, vday.isoformat(), '%02d:%02d' % (rnd.randint(9, 18), rnd.choice([0, 15, 30, 45])),
                                doc, 'زيارة تجريبية', now, now)).lastrowid
                total = 0
                for _ in range(rnd.randint(1, 2)):
                    n, cost, t = rnd.choice(PROCS)
                    total += cost
                    db.execute('INSERT INTO procedures(visit_id,patient_id,name,tooth_no,status,cost,doctor,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                               (v, pid, n, str(rnd.choice(TEETH)) if t else None, rnd.choice(['completed', 'completed', 'in_progress']),
                                cost, doc, now, now))
                paid = rnd.choice([total, total, total // 2, total // 3])
                if paid > 0:
                    db.execute("INSERT INTO payments(patient_id,visit_id,pay_date,amount,kind,method,notes,created_by,created_at) VALUES(?,?,?,?, 'payment',?,?,?,?)",
                               (pid, v, vday.isoformat(), max(paid // 1000 * 1000, 1000), rnd.choice(['cash', 'cash', 'transfer']), 'دفعة تجريبية', 'demo-seed', now))
                vday += timedelta(days=rnd.randint(7, 60))
            if rnd.random() < 0.5:
                db.execute("INSERT INTO appointments(patient_id,appt_date,appt_time,reason,status,created_at,updated_at) VALUES(?,?,?,?, 'confirmed',?,?)",
                           (pid, (today + timedelta(days=rnd.randint(0, 10))).isoformat(), '%02d:00' % rnd.randint(9, 17), 'مراجعة', now, now))
        for k in range(14):
            d = today - timedelta(days=rnd.randint(0, 400))
            db.execute("INSERT INTO expenses(exp_date,category,amount,description,method,created_by,created_at) VALUES(?,?,?,?, 'cash','demo-seed',?)",
                       (d.isoformat(), rnd.choice(CATS), rnd.choice([25000, 50000, 100000, 250000, 400000]), 'مصروف تجريبي', now))
        audit(db, 'demo-seed', 'system', None, 'seed_demo')
        db.execute('COMMIT')
        return True
    finally:
        db.close()
