# -*- coding: utf-8 -*-
"""أداة مستقلة: تقرأ ملف Excel/CSV القديم وتنتج ملف Excel نظيفاً (بدون تكرار، تواريخ مصححة، أسنان FDI، أسماء موحدة).
الاستعمال:  python clean_excel.py "سجل العيادة.xlsx"  [--mult 1000] [--year 2022]
أو اسحب الملف وأفلته على clean_excel.bat"""
import os, sys, argparse
APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import xlsx_reader, importer
from xlsx_writer import build_xlsx_multi

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file'); ap.add_argument('--mult', type=int, default=1000, choices=[1, 10, 100, 1000])
    ap.add_argument('--year', type=int); ap.add_argument('--out')
    a = ap.parse_args()
    data = open(a.file, 'rb').read()
    sheets = xlsx_reader.read_any(data, a.file)
    plan, pv = importer.build_plan(sheets, a.mult, a.year)
    recs, disp, m = plan['recs'], plan['display'], a.mult
    # الشيت 1: السجل النظيف (نفس ترتيب أعمدة الملف الأصلي، قابل للاستيراد بالبرنامج مع خيار «المبالغ كاملة»)
    clean, seen = [], {}
    for x in recs:
        tooth = ','.join(str(t) for t in x['teeth']) if x['teeth'] else x['tooth_txt']
        row = [disp[x['pkey']], x['date'].isoformat(), x['work'], tooth, x['paid_units'], x['rem_after'], x['notes_raw'] or None]
        k = tuple(row)
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:      # صفوف متطابقة شرعية: نميّزها حتى لا تُحسب مكررة عند الاستيراد
            row[6] = ((row[6] + ' | ') if row[6] else '') + 'سجل مماثل رقم %d (شيت %s صف %s)' % (seen[k], x['sheet'], x['row'])
        clean.append(row)
    clean_h = ['اسم المراجع', 'تاريخ المراجعة', 'نوع العمل', 'رقم السن (FDI)', 'المدفوع', 'المتبقي بعد هذا السجل', 'الملاحظات']
    # الشيت 2: المراجعون (ملخص)
    agg = {}
    for x in recs:
        d = agg.setdefault(x['pkey'], {'n': 0, 'paid': 0, 'first': x['date'], 'last': x['date']})
        d['n'] += 1; d['paid'] += x['paid_units']; d['first'] = min(d['first'], x['date']); d['last'] = max(d['last'], x['date'])
    pats = sorted(([disp[k], v['n'], v['first'].isoformat(), v['last'].isoformat(), v['paid'], plan['balances'][k]] for k, v in agg.items()), key=lambda r: r[0])
    pats_h = ['المراجع', 'عدد السجلات', 'أول زيارة', 'آخر زيارة', 'مجموع المدفوع', 'المتبقي عليه']
    # الشيت 3: المراجعة
    sev = {'skipped': 'لم يُدخل (صحّحه يدوياً)', 'dup': 'مكرر (حُذف)', 'warn': 'تنبيه'}
    rev = [[sev[r['severity']], r['sheet'], r['row'], r['name'], r['reason']] for r in pv['review']]
    rev_h = ['النوع', 'الشيت الأصلي', 'الصف الأصلي', 'المراجع', 'السبب']
    # الشيت 4: أسماء دُمجت
    mg = [[' ، '.join(g['names']), g['rows']] for g in pv['merged_names']]
    s = pv['summary']
    summ = [['صفوف في الملف الأصلي', s['rows_total']], ['صفوف في الملف النظيف', s['rows_imported']], ['صفوف مكررة حُذفت', s['duplicates_in_file']],
            ['صفوف مُتخطّاة (انظر شيت المراجعة)', s['rows_skipped']], ['تواريخ صُحّحت (يوم/شهر مقلوب)', s['date_fixed']], ['عدد المراجعين', s['patients']],
            ['مجموع المدفوع', s['total_paid']], ['إجمالي المتبقي على المراجعين', s['outstanding_total']], ['من تاريخ', s['date_from']], ['إلى تاريخ', s['date_to']],
            ['ملاحظة', 'المبالغ في هذا الملف مكتوبة كاملة (مضروبة في %d). عند استيرادها بالبرنامج اختر «المبالغ كاملة».' % m]]
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.file)), os.path.splitext(os.path.basename(a.file))[0] + '_منظف.xlsx')
    open(out, 'wb').write(build_xlsx_multi([('السجل النظيف', clean_h, clean), ('المراجعون', pats_h, pats), ('للمراجعة', rev_h, rev), ('أسماء دُمجت', ['الصيغ المكتوبة', 'الصفوف'], mg), ('ملخص', ['البند', 'القيمة'], summ)]))
    print('تم. الملف النظيف:', out)
    for k, v in summ[:10]: print(' -', k, ':', v)

if __name__ == '__main__':
    main()
