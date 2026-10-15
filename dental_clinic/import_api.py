# -*- coding: utf-8 -*-
"""مسارات استيراد Excel: معاينة ثم اعتماد."""
import time, secrets, json
from core import ApiError, norm_ar, get_settings
from api import route
import xlsx_reader, importer


def _prune(plans):
    now = time.time()
    for k in [k for k, v in plans.items() if now - v['ts'] > 1800]:
        plans.pop(k, None)
    while len(plans) > 3:
        plans.pop(min(plans, key=lambda k: plans[k]['ts']), None)


@route('POST', '/api/import/preview', perm='import', tx=False)
def import_preview(c):
    if not c.raw:
        raise ApiError('لم يتم إرسال ملف')
    try:
        mult = int(c.q.get('mult') or 1000)
        year = int(c.q['year']) if c.q.get('year') else None
    except ValueError:
        raise ApiError('خيارات غير صحيحة')
    if mult not in (1, 10, 100, 1000):
        raise ApiError('معامل المبالغ غير مسموح')
    try:
        sheets = xlsx_reader.read_any(c.raw, c.q.get('filename', ''))
    except ValueError as e:
        raise ApiError(str(e))
    except Exception:
        raise ApiError('تعذّرت قراءة الملف. تأكد أنه Excel بصيغة xlsx (أو CSV) وغير تالف.')
    fps = {r[0] for r in c.db.execute('SELECT fingerprint FROM import_rows')}
    keys = {r['name_norm'].replace(' ', ''): r['id'] for r in c.db.execute('SELECT id,name_norm FROM patients WHERE deleted=0')}
    try:
        chosen = json.loads(c.q.get('doctors') or '{}')
        assert isinstance(chosen, dict) and all(isinstance(v, str) for v in chosen.values())
    except Exception:
        raise ApiError('اختيار الأطباء للشيتات غير صحيح')
    try:
        doctors = [d for d in json.loads(get_settings(c.db).get('doctors') or '[]') if isinstance(d, str) and d.strip()]
    except ValueError:
        doctors = []
    sheet_docs = importer.match_sheet_doctors([n for n, _ in sheets], doctors, chosen)
    plan, preview = importer.build_plan(sheets, mult, year, fps, keys, sheet_docs)
    plans = c.clinic.import_plans
    _prune(plans)
    token = secrets.token_urlsafe(12)
    plans[token] = {'plan': plan, 'ts': time.time(), 'filename': (c.q.get('filename') or '')[:120], 'user': c.user['username']}
    return {'token': token, **preview}


@route('POST', '/api/import/commit', perm='import', tx=False)
def import_commit(c):
    entry = c.clinic.import_plans.get(str(c.body.get('token') or ''))
    if not entry:
        raise ApiError('انتهت صلاحية المعاينة. أعد تحليل الملف ثم اعتمد الاستيراد.')
    if not entry['plan']['recs']:
        raise ApiError('لا توجد صفوف صالحة للاستيراد')
    backup = c.clinic.make_backup('pre_import')      # نسخة أمان قبل أي إدخال
    c.db.execute('BEGIN IMMEDIATE')
    try:
        result = importer.commit_plan(c.db, entry['plan'], c.user['username'], entry['filename'], backup['name'])
        c.db.execute('COMMIT')
    except BaseException:
        if c.db.in_transaction:
            c.db.execute('ROLLBACK')
        raise
    c.clinic.import_plans.pop(str(c.body.get('token')), None)
    return {'ok': True, 'result': result, 'backup': backup['name']}


@route('GET', '/api/import/history', perm='import', tx=False)
def import_history(c):
    return {'batches': [dict(r) for r in c.db.execute('SELECT id,ts,filename,user,rows_imported,patients_new,backup_name FROM import_batches ORDER BY id DESC LIMIT 50')]}
