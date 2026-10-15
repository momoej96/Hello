# -*- coding: utf-8 -*-
"""اختبار واجهة حقيقي بمتصفح Chromium: يمر على الشاشات الرئيسية ويلتقط صوراً ويجمع أخطاء JavaScript."""
import os, sys, tempfile, threading, shutil, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server, seed_demo
from playwright.sync_api import sync_playwright

PW = 'Test-pass-1234'; SH = os.environ.get('SHOTS', '/tmp/shots')
tmp = tempfile.mkdtemp(prefix='clinic_ui_')
srv = server.make_server(tmp, 0, demo=True); seed_demo.seed_if_empty(srv.clinic)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:%d/' % srv.server_address[1]
errors = []
def shot(p, n): p.screenshot(path=f'{SH}/{n}.png', full_page=False)
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={'width': 1366, 'height': 850}, accept_downloads=True); p = ctx.new_page()
    p.on('pageerror', lambda e: errors.append('pageerror: %s' % e))
    p.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    p.goto(base); p.wait_for_selector('#lf')
    assert 'الإعداد الأول' in p.inner_text('#lf'); shot(p, '01_setup')
    p.fill('[name=clinic_name]', 'عيادة النور لطب الأسنان'); p.fill('[name=username]', 'admin'); p.fill('[name=password]', PW); p.fill('[name=c]', PW)
    p.click('#lf button[type=submit]'); p.wait_for_selector('.ledger')
    assert p.evaluate("document.documentElement.dir") == 'rtl'
    shot(p, '02_dashboard')
    # بحث
    p.click('a[href="#/patients"]'); p.wait_for_selector('#plist table'); p.fill('#pq', 'عبدالله'); p.wait_for_timeout(600)
    assert 'عبد الله ياسر' in p.inner_text('#plist'), p.inner_text('#plist'); shot(p, '03_patients_search')
    p.click('#plist a.pname'); p.wait_for_selector('.pt-head'); shot(p, '04_patient')
    # مراجع جديد
    p.click('.topbar [data-action=new-patient]'); p.wait_for_selector('.dialog')
    p.fill('[name=full_name]', 'خالد إبراهيم الجبوري'); p.fill('[name=phone]', '07901234567'); shot(p, '05_new_patient_modal'); p.click('[data-save]')
    p.wait_for_selector('.pt-head h1:has-text("خالد إبراهيم")')  # ننتظر صفحة المراجع الجديد لا الصفحة السابقة
    # زيارة بإجراءين
    p.click('.pt-actions [data-action=new-visit]'); p.wait_for_selector('.vform')
    rows = p.locator('.prow'); rows.nth(0).locator('[name=name]').fill('زراعة سن'); rows.nth(0).locator('[data-action=tooth-pick]').click(); p.wait_for_selector('.tooth-panel'); shot(p, '06_visit_modal_tooth')
    p.click('.tooth-panel [data-t="36"]'); assert rows.nth(0).locator('[name=tooth_no]').input_value() == '36'
    rows.nth(0).locator('[name=status]').select_option('in_progress'); rows.nth(0).locator('[name=cost]').fill('500000'); assert rows.nth(0).locator('[name=cost]').input_value() == '500,000'
    p.click('[data-action=add-proc]'); rows.nth(1).locator('[name=name]').fill('فحص وتشخيص'); rows.nth(1).locator('[name=cost]').fill('١٥٠٠٠')
    p.fill('[name=notes]', 'ملاحظة سريرية تجريبية'); p.wait_for_timeout(100); assert '515,000' in p.inner_text('.proc-total'), p.inner_text('.proc-total')
    p.click('[data-save]'); p.wait_for_selector('.visit'); assert '515,000' in p.inner_text('.strip'), p.inner_text('.strip')
    # دفعتان
    for amt in ('150000', '100000'):
        p.click('.pt-actions [data-action=new-payment]'); p.wait_for_selector('[name=amount]'); p.fill('[name=amount]', amt); p.click('[data-save]')
        p.wait_for_selector('.ok-msg'); 
        if amt == '150000': shot(p, '07_payment_done')
        p.click('.dialog [data-close]:not(.x)')
    s = p.inner_text('.strip'); assert '250,000' in s and '265,000' in s, s; shot(p, '08_patient_after_payments')
    p.click('[data-tab=fin]'); p.wait_for_selector('#payTbl table'); shot(p, '09_financial_tab')
    # طباعة كشف الحساب (التحقق من محتوى منطقة الطباعة)
    p.evaluate("window.print = () => {}"); p.click('[data-action=print-statement]'); p.wait_for_timeout(200)
    t = p.inner_text('#printRoot'); assert 'كشف حساب المراجع' in t and 'عيادة النور' in t and '265,000' in t, t[:300]
    p.emulate_media(media='print'); p.pdf(path=f'{SH}/statement.pdf', format='A4'); p.emulate_media(media='screen'); p.evaluate("window.dispatchEvent(new Event('afterprint'))")
    p.click('[data-action=print-receipt] >> nth=0'); p.wait_for_timeout(200); assert 'إيصال قبض' in p.inner_text('#printRoot'); p.evaluate("window.dispatchEvent(new Event('afterprint'))")
    # تعليمات القلع/الزراعة
    p.click('.pt-actions [data-action=care-sheet]'); p.wait_for_selector('.dialog [name=k]'); assert p.input_value('.dialog [name=k]') == 'implant'
    p.fill('.dialog [name=x]', 'تجنب الجهة اليمنى'); p.click('.dialog [data-print]'); p.wait_for_timeout(200)
    t = p.inner_text('#printRoot'); assert 'تعليمات ما بعد الزراعة' in t and 'خالد إبراهيم' in t and '36' in t and 'تجنب الجهة اليمنى' in t and 'عيادة النور' in t, t[:300]
    p.emulate_media(media='print'); p.pdf(path=f'{SH}/care.pdf', prefer_css_page_size=True); p.emulate_media(media='screen'); p.evaluate("window.dispatchEvent(new Event('afterprint'))")
    p.click('[data-tab=treat]'); p.click('.visit [data-action=care-sheet]'); p.wait_for_selector('.dialog [name=k]'); p.select_option('.dialog [name=k]', 'extract'); p.click('.dialog [data-print]'); p.wait_for_timeout(200)
    assert 'تعليمات ما بعد القلع' in p.inner_text('#printRoot'); p.evaluate("window.dispatchEvent(new Event('afterprint'))")
    # تصدير Excel من التقرير
    p.goto(base + '#/reports/daily'); p.wait_for_selector('.stats'); assert p.locator('.tabs a').count() == 6; shot(p, '10_report_daily')
    p.goto(base + '#/reports/monthly'); p.wait_for_selector('.chart'); shot(p, '11_report_monthly')
    with p.expect_download() as dl: p.click('[data-action=rpt-xlsx]')
    path = f'{SH}/dl.xlsx'; dl.value.save_as(path)
    import openpyxl; ws = openpyxl.load_workbook(path).active; assert ws.max_row > 5 and ws.sheet_view.rightToLeft
    p.goto(base + '#/reports/yearly'); p.wait_for_selector('.chart'); shot(p, '12_report_yearly')
    p.goto(base + '#/reports/dues'); p.wait_for_selector('.stats'); p.goto(base + '#/reports/debtors'); p.wait_for_selector('#dtb table'); shot(p, '13_debtors')
    # مصروف
    p.goto(base + '#/expenses'); p.wait_for_selector('#eb .stats'); p.click('[data-action=new-exp]'); p.fill('[name=amount]', '50000'); p.fill('[name=description]', 'مواد'); p.click('[data-save]'); p.wait_for_selector('#etb table'); p.wait_for_timeout(300)
    assert '50,000' in p.inner_text('#eb'); shot(p, '14_expenses')
    # مواعيد + بحث حسب التاريخ
    p.goto(base + '#/appointments'); p.wait_for_selector('#apl'); p.click('[data-action=appt-mode][data-m=week]'); p.wait_for_selector('.card.day'); shot(p, '15_appointments_week')
    p.goto(base + '#/appointments/log'); p.wait_for_selector('#vtbl table'); shot(p, '16_visit_log')
    p.goto(base + '#/bydate'); p.wait_for_selector('#vtbl'); p.click('[data-p=month]'); p.wait_for_timeout(500); shot(p, '17_bydate')
    # إعدادات + نسخ احتياطي
    p.goto(base + '#/settings/backup'); p.wait_for_selector('[data-action=make-backup]'); p.click('[data-action=make-backup]'); p.wait_for_selector('.toast:has-text("النسخة الاحتياطية")'); assert 'بنجاح' in p.inner_text('#toasts'); shot(p, '18_backup')
    p.goto(base + '#/settings/audit'); p.wait_for_selector('#atb table'); p.goto(base + '#/settings/users'); p.wait_for_selector('.card')
    # قفل
    p.click('[data-action=lock]'); p.wait_for_selector('#lf'); assert 'تم قفل' in p.inner_text('#lf'); shot(p, '19_locked')
    # شاشة صغيرة
    p.set_viewport_size({'width': 390, 'height': 800}); p.fill('[name=username]', 'admin'); p.fill('[name=password]', PW); p.click('#lf button[type=submit]'); p.wait_for_selector('#main .page-head'); p.goto(base + '#/dashboard'); p.wait_for_selector('.ledger'); shot(p, '20_mobile'); p.goto(base + '#/patients'); p.wait_for_selector('#plist table'); shot(p, '21_mobile_patients')
    b.close()
srv.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
print('UI errors:', errors if errors else 'none'); print('UI SMOKE OK' if not errors else 'UI SMOKE WITH ERRORS')
