# -*- coding: utf-8 -*-
"""استيراد سجل العيادة من Excel/CSV: تنظيف، دمج الأسماء، إزالة التكرار، تصحيح التواريخ، حساب الأرصدة."""
import re, json, hashlib, datetime, statistics, collections
from core import norm_ar, AR_DIGITS, FDI, now_iso, audit, today_iso

HEADER_KEYS = [('name', ['اسم']), ('date', ['تاريخ']), ('work', ['عمل']), ('tooth', ['سن']),
               ('paid', ['مدفوع']), ('remaining', ['متبق', 'باقي']), ('notes', ['ملاحظ'])]
DEFAULT_POS = {'name': 0, 'date': 1, 'work': 2, 'tooth': 3, 'paid': 4, 'remaining': 5}
QUAD = {'ur': 1, 'ul': 2, 'll': 3, 'lr': 4}
PAY_WORDS = ('تسديد', 'سداد', 'قسط', 'دفعه', 'واصل')   # بعد norm_ar (ة -> ه)
PAY_LATIN = re.compile(r'(?<![a-z])(bills?|pay|paid|payment)(?![a-z])')


def is_payment_work(work):
    """صف «تسديد» أو «bill»: مبلغ مدفوع يُطرح من حساب المراجع وليس عملاً جديداً."""
    t = norm_ar(work)
    return any(w in t for w in PAY_WORDS) or bool(PAY_LATIN.search(t))
UNKNOWN_WORK = 'غير محدد'


def pkey_of(name):
    return norm_ar(name).replace(' ', '')


def clean_name(v):
    s = re.sub(r'\s+', ' ', str(v)).strip(' .،-_\t')
    return s


def to_num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).translate(AR_DIGITS).replace(',', '').replace('٬', '').strip()
    if s == '':
        return None
    try:
        return float(s)
    except ValueError:
        return 'bad'


def sheet_year(title):
    m = re.search(r'(20\d\d)', str(title))
    return int(m.group(1)) if m else None


def detect_header(vals):
    mapping, hits = {}, 0
    for i, v in enumerate(vals):
        if not isinstance(v, str) or len(v) > 40:
            continue
        t = norm_ar(v)
        for key, words in HEADER_KEYS:
            if key not in mapping and any(w in t for w in words):
                mapping[key] = i
                hits += 1
                break
    return mapping if hits >= 3 and 'name' in mapping else None


def parse_text_date(s, year):
    s = norm_ar(str(s)).strip()
    m = re.fullmatch(r'(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})', s)
    try:
        if m:
            return datetime.date(int(m[1]), int(m[2]), int(m[3])), False
        m = re.fullmatch(r'(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?:\s*[/\-.]\s*(\d{2,4}))?', s)
        if m:
            d, mo, y = int(m[1]), int(m[2]), m[3]
            if y:
                y = int(y)
                y = y + 2000 if y < 100 else y
            else:
                y = year
            if not y:
                return None, True
            return datetime.date(y, mo, d), not m[3]
    except ValueError:
        return None, False
    return None, False


PRIM_Q = {'ur': 5, 'ul': 6, 'll': 7, 'lr': 8}
_GROUP = re.compile(r'(ur|ul|ll|lr)([1-8]+|[a-e]+)')


def parse_teeth(raw):
    """يحوّل كتابة الأسنان في الإكسل (UL6، lre، ul3+4، u11، ur7lr5…) إلى أرقام FDI. يعيد (قائمة, غير_مفهوم)."""
    if raw is None:
        return [], False
    s = norm_ar(str(raw)).replace(' ', '')
    if s == '':
        return [], False
    teeth, bad, last_quad = [], False, None
    for tok in [t for t in re.split(r'[,،+/\\]+', s) if t]:
        if re.fullmatch(r'((ur|ul|ll|lr)([1-8]+|[a-e]+))+', tok):
            for q, codes in _GROUP.findall(tok) and [(m.group(1), m.group(2)) for m in _GROUP.finditer(tok)]:
                last_quad = QUAD[q]
                if codes.isdigit():
                    teeth += [QUAD[q] * 10 + int(d) for d in codes]
                else:
                    teeth += [PRIM_Q[q] * 10 + (ord(ch) - 96) for ch in codes]
        elif tok.isdigit() and last_quad and all(c in '12345678' for c in tok):
            teeth += [last_quad * 10 + int(d) for d in tok]
        elif re.fullmatch(r'[ul][1-8]{2,}', tok) and len(tok) % 2 == 1:
            half = (len(tok) - 1) // 2
            right, left = tok[1:1 + half], tok[1 + half:]
            if len(set(right)) != len(right) or len(set(left)) != len(left):
                bad = True
                continue
            qr, ql = (1, 2) if tok[0] == 'u' else (4, 3)
            teeth += [qr * 10 + int(d) for d in right] + [ql * 10 + int(d) for d in left]
        elif tok.isdigit() and int(tok) in FDI:
            teeth.append(int(tok))
        else:
            bad = True
    teeth = [t for t in dict.fromkeys(teeth)]
    if any(t not in FDI for t in teeth):
        bad = True
    return teeth, bad


def fix_dates(items):
    """يصحّح التواريخ المقلوبة (يوم/شهر) التي يسببها Excel عندما يكون اليوم <= 12.
    الإدخال في الدفتر متسلسل زمنياً، فنختار التفسير الذي يقع بين آخر تاريخ محسوم وأول تاريخ محسوم لاحق."""
    amb = []
    for pos, it in enumerate(items):
        dt = it.get('raw_dt')
        if it.get('date'):
            continue
        if dt and (dt.day > 12 or dt.day == dt.month):
            it['date'] = dt.date()
        elif dt:
            amb.append(pos)
    ambset = set(amb)
    nxt, nxt_val = {}, None
    for pos in range(len(items) - 1, -1, -1):
        if pos not in ambset and items[pos].get('date'):
            nxt_val = items[pos]['date'].toordinal()
        nxt[pos] = nxt_val
    prev, fixed = None, 0
    for pos, it in enumerate(items):
        if pos not in ambset:
            if it.get('date'):
                prev = it['date'].toordinal()
            continue
        dt = it['raw_dt']
        as_is = dt.date()
        try:
            swapped = datetime.date(dt.year, dt.day, dt.month)
        except ValueError:
            it['date'] = as_is
            prev = as_is.toordinal()
            continue
        lo = prev if prev is not None else nxt[pos]
        hi = nxt[pos] if nxt[pos] is not None else lo
        if lo is None:
            it['date'] = as_is
            continue
        if hi < lo:
            hi = lo

        def score(d):
            o = d.toordinal()
            return (max(0, lo - o, o - hi), abs(o - lo))
        pick = swapped if score(swapped) < score(as_is) else as_is
        if pick == swapped:
            it['date_fixed'] = True
            fixed += 1
        it['date'] = pick
        prev = pick.toordinal()
    return fixed


# ---- توحيد أنواع العمل المكتوبة في الإكسل تحت أسماء الإجراءات في البرنامج ----
P_LIGHT, P_METAL = 'حشوة دائمية - ضوئية', 'حشوة دائمية - معدنية'
T_NORMAL, T_GIC = 'حشوة مؤقتة - اعتيادية', 'حشوة مؤقتة - علاجية (GIC)'
ROOT_CANAL, AFTER_EXT, EXTRACTION, BRIDGE, XRAY = 'حشوة جذر (عصب)', 'معالجة بعد القلع', 'قلع سن', 'جسر أسنان', 'أشعة'
SURGICAL_EXT = 'قلع جراحي'
# (الاسم الموحد، كلمات تُبحث في النص بعد حذف المسافات، كلمات لاتينية قصيرة تُطابق ككلمة كاملة). الترتيب مهم: أول قاعدة تنطبق تفوز.
WORK_RULES = [
    (AFTER_EXT, ['ازالة خيط', 'إزالة خيط', 'رفع خيط', 'بعد القلع', 'بعد الخلع', 'dry socket', 'drysocket', 'iregation', 'irrigation', 'irregation', 'irigation'], []),
    (BRIDGE, ['re impression', 'impression', 'طبعة', 'تحضير', 'تحظير', 'fixation', 'تثبيت', 'جسر'], ['prep']),
    (ROOT_CANAL, ['اندو', 'indo', 'endo', 'حشوة جذر', 'حشوة عصب'], []),
    (P_METAL, ['amalgam', 'amlgam', 'amalgum', 'بلاتين'], []),
    (P_LIGHT, ['ضوئية', 'composite', 'composet', 'composit'], []),
    (T_GIC, [], ['gic']),
    (T_NORMAL, ['plupotic', 'pulpotic', 'pulpotomy', 'مؤقتة', 'موقتة'], ['tf']),
    (XRAY, ['x ray', 'xray', 'اشعة', 'أشعة'], []),
    (EXTRACTION, ['قلع', 'خلع'], ['exo']),
]
_RC_SESSION = re.compile(r'(?:^|[^\u0600-\u06ff])ج\s*([1-4])(?![0-9])')


def _compact(s):
    return re.sub(r'[\s\-_./\\]+', '', norm_ar(s))


_WORK_RULES_N = [(name, [_compact(w) for w in words], set(short)) for name, words, short in WORK_RULES]


def canonical_work(work):
    """يعيد (الاسم الموحد، ملاحظة) لنوع العمل المكتوب، أو (الاسم كما هو، None) إن لم تنطبق قاعدة."""
    t, c = norm_ar(work), _compact(work)
    tokens = set(re.findall(r'[a-z]+', t))
    m = _RC_SESSION.search(t)
    for name, words, short in _WORK_RULES_N:
        hit = any(w in c for w in words) or bool(tokens & short)
        if name == ROOT_CANAL and m:
            hit = True
        if hit:
            if name == T_NORMAL and 'علاجي' in t:
                name = T_GIC
            if name == EXTRACTION and ('جراح' in t or 'surg' in t):
                name = SURGICAL_EXT
            if _compact(name) == c:
                return name, None
            note = 'نوع العمل في الإكسل: ' + work
            if name == ROOT_CANAL and m:
                note += ' (الجلسة %s)' % m.group(1)
            return name, note
    return work, None


def doctor_core(name):
    """اسم الطبيب بدون «د.» أو «دكتور» للمطابقة مع اسم الشيت."""
    t = norm_ar(name)
    t = re.sub(r'^(الدكتور|دكتور|الطبيب|طبيب|dr\.?|د\s*\.|د\s)\s*', '', t)
    return t.strip()


def match_sheet_doctors(sheet_names, doctors, chosen=None):
    """طبيب كل شيت: اختيار المستخدم أولاً («» = مشترك/بدون طبيب)، وإلا مطابقة تلقائية إن ورد اسم طبيب واحد في اسم الشيت."""
    chosen = chosen or {}
    out = {}
    for n in sheet_names:
        if n in chosen:
            out[n] = (chosen[n] or '').strip()[:100]
            continue
        t = norm_ar(n).replace(' ', '')
        hits = [d for d in doctors if doctor_core(d) and doctor_core(d).replace(' ', '') in t]
        out[n] = hits[0] if len(hits) == 1 else ''
    return out


def build_plan(sheets, mult=1000, default_year=None, existing_fps=None, existing_keys=None, sheet_doctors=None):
    existing_fps = existing_fps or set()
    existing_keys = existing_keys or {}
    sheet_doctors = sheet_doctors or {}
    today = datetime.date.today()
    review, raw_rows, summary = [], [], {'sheets': []}
    for si, (sname, rows) in enumerate(sheets):
        year = sheet_year(sname) or default_year
        mapping = dict(DEFAULT_POS)
        note_cols = list(range(6, 40))
        items, n_rows, n_hdr = [], 0, 0
        for rowno, vals in rows:
            h = detect_header(vals)
            if h:
                mapping = {**DEFAULT_POS, **h} if False else h
                for k, v in DEFAULT_POS.items():
                    mapping.setdefault(k, v)
                used = set(mapping.values())
                note_cols = [i for i in range(len(vals)) if i not in used and i >= 6] + ([mapping['notes']] if 'notes' in mapping else [])
                n_hdr += 1
                continue
            g = lambda k: vals[mapping[k]] if mapping.get(k) is not None and mapping[k] < len(vals) else None
            name_v = g('name')
            name = clean_name(name_v) if name_v is not None else ''
            other = any(g(k) not in (None, '') for k in ('date', 'work', 'paid'))
            if not name or re.fullmatch(r'[\d\W_]+', name):
                if other or name:
                    review.append({'sheet': sname, 'row': rowno, 'name': name or '', 'reason': 'بدون اسم صالح', 'severity': 'skipped'})
                continue
            n_rows += 1
            it = {'sheet': sname, 'si': si, 'row': rowno, 'name': name, 'pkey': pkey_of(name), 'year': year, 'doctor': sheet_doctors.get(sname, ''),
                  'work_raw': g('work'), 'tooth_raw': g('tooth'), 'paid_raw': g('paid'), 'rem_raw': g('remaining'), 'warn': []}
            d = g('date')
            if isinstance(d, datetime.datetime):
                it['raw_dt'] = d
            elif d is not None:
                dd, assumed = parse_text_date(d, year)
                it['date'] = dd
                if dd is None:
                    it['date_err'] = 'تاريخ غير مفهوم: %s' % d if not assumed else 'تاريخ بدون سنة ولا توجد سنة في اسم الشيت'
            else:
                it['date_err'] = 'بدون تاريخ'
            notes = [str(vals[i]).strip() for i in note_cols if i < len(vals) and vals[i] not in (None, '')]
            it['notes'] = ' | '.join(notes)[:1500]
            items.append(it)
        fixed = fix_dates([x for x in items])
        summary['sheets'].append({'name': sname, 'rows': n_rows, 'date_fixed': fixed, 'doctor': sheet_doctors.get(sname, '')})
        raw_rows.extend(items)
    # ---- التحقق وتجهيز السجلات ----
    recs, seen = [], set()
    work_merged = collections.defaultdict(collections.Counter)
    dup_file, dup_prev = 0, 0
    for it in raw_rows:
        reason = None
        d = it.get('date')
        if it.get('date_err') or not d:
            reason = it.get('date_err') or 'بدون تاريخ'
        elif d > today:
            reason = 'تاريخ مستقبلي: %s' % d
        elif d.year < 2000:
            reason = 'تاريخ غير منطقي: %s' % d
        p, r = to_num(it['paid_raw']), to_num(it['rem_raw'])
        if not reason:
            if p == 'bad':
                reason = 'مبلغ مدفوع غير رقمي: %s' % it['paid_raw']
            elif r == 'bad':
                reason = 'مبلغ متبقٍ غير رقمي: %s' % it['rem_raw']
            elif (p or 0) < 0:
                reason = 'مبلغ مدفوع سالب: %s' % it['paid_raw']
            elif (r or 0) < 0:
                reason = 'مبلغ متبقٍ سالب: %s' % it['rem_raw']
        if reason:
            review.append({'sheet': it['sheet'], 'row': it['row'], 'name': it['name'], 'reason': reason, 'severity': 'skipped',
                           'paid': str(it['paid_raw'] or ''), 'remaining': str(it['rem_raw'] or ''), 'work': str(it['work_raw'] or '')})
            continue
        work = re.sub(r'\s+', ' ', str(it['work_raw'])).strip() if it['work_raw'] not in (None, '') else UNKNOWN_WORK
        teeth, bad_tooth = parse_teeth(it['tooth_raw'])
        tooth_txt = re.sub(r'\s+', ' ', str(it['tooth_raw'])).strip() if it['tooth_raw'] not in (None, '') else ''
        fp = hashlib.sha1('|'.join([it['pkey'], d.isoformat(), norm_ar(work), norm_ar(tooth_txt), str(p or 0), str(r), norm_ar(it['notes'])]).encode('utf-8')).hexdigest()
        if fp in existing_fps:
            dup_prev += 1
            review.append({'sheet': it['sheet'], 'row': it['row'], 'name': it['name'], 'reason': 'مستورد سابقاً (لن يُكرَّر)', 'severity': 'dup'})
            continue
        if fp in seen:
            dup_file += 1
            review.append({'sheet': it['sheet'], 'row': it['row'], 'name': it['name'], 'reason': 'صف مكرر تماماً داخل الملف (حُذف)', 'severity': 'dup',
                           'work': work, 'paid': str(it['paid_raw'] or '')})
            continue
        seen.add(fp)
        details = []
        raw_work = work
        if work != UNKNOWN_WORK and not is_payment_work(work):
            work, wnote = canonical_work(work)
            if wnote:
                details.append(wnote)
                work_merged[work][raw_work] += 1
        tooth_no = None
        if teeth and not bad_tooth:
            tooth_no = ','.join(str(t) for t in teeth)      # سن واحد أو عدة أسنان (U11 → 11,21)
        elif tooth_txt:
            details.append('السن (كما في الإكسل): ' + tooth_txt)
            it['warn'].append('رقم السن غير مفهوم: ' + tooth_txt)
        if work != str(it['work_raw'] or '').strip() and False:
            pass
        if it['notes']:
            details.append(it['notes'])
        recs.append({'sheet': it['sheet'], 'si': it['si'], 'row': it['row'], 'name': it['name'], 'pkey': it['pkey'], 'date': d, 'doctor': it['doctor'],
                     'work': work, 'tooth_no': tooth_no, 'details': '\n'.join(details) or None, 'p': p or 0.0, 'r': r, 'fp': fp,
                     'is_pay': is_payment_work(raw_work), 'teeth': teeth if not bad_tooth else [], 'tooth_txt': tooth_txt, 'notes_raw': it['notes'], 'date_fixed': bool(it.get('date_fixed')), 'warn': it['warn']})
        for w in it['warn']:
            review.append({'sheet': it['sheet'], 'row': it['row'], 'name': it['name'], 'reason': w, 'severity': 'warn'})
    # ---- دمج الأسماء ----
    variants = collections.defaultdict(collections.Counter)
    for x in recs:
        variants[x['pkey']][x['name']] += 1
    display = {k: v.most_common(1)[0][0] for k, v in variants.items()}
    merged = [{'names': [n for n, _ in v.most_common()], 'rows': sum(v.values())} for v in variants.values() if len(v) > 1]
    merged.sort(key=lambda m: -m['rows'])
    # ---- حساب الرصيد المتحرك لكل مراجع بترتيب الإدخال (الشيت ثم رقم الصف) ----
    # لكل طبيب دفتره: «المتبقي» في شيت طبيب يخص حسابه هو فقط، فالرصيد يُتابع لكل (مراجع، طبيب) على حدة.
    # الرصيد من الشيتات المشتركة (بدون طبيب) ينتقل مرة واحدة لأول طبيب يكمل مع المراجع، حتى لا يُحسب مرتين.
    recs.sort(key=lambda x: (x['si'], x['row']))
    state, total_paid, total_charge, total_disc = collections.defaultdict(int), 0, 0, 0
    first_date, last_date = {}, {}
    for x in recs:
        p = int(round(x['p'] * mult))
        r = None if x['r'] is None else int(round(x['r'] * mult))
        sk = (x['pkey'], x['doctor'])
        if x['doctor'] and sk not in state and state.get((x['pkey'], ''), 0):
            carried = state.pop((x['pkey'], ''))
            state[sk] = carried
            review.append({'sheet': x['sheet'], 'row': x['row'], 'name': x['name'], 'severity': 'warn',
                           'reason': 'رصيد سابق من الشيتات المشتركة (%s) انتقل إلى حساب %s' % (format(carried, ','), x['doctor'])})
        prev = state[sk]
        disc = 0
        if r is None:
            if x['is_pay']:
                off = min(p, prev)
                charge, rem = p - off, prev - off
            else:
                charge, rem = p, prev
        else:
            charge = p + r - prev
            if charge < 0:
                disc, charge = -charge, 0
                review.append({'sheet': x['sheet'], 'row': x['row'], 'name': x['name'], 'severity': 'warn',
                               'reason': 'المتبقي المكتوب أقل من المتوقع؛ سُجّلت تسوية/خصم بقيمة %s' % format(disc, ',')})
            rem = r
        state[sk] = rem
        x['rem_after'] = rem
        x.update(paid_units=p, charge=charge, discount=disc)
        x['pay_only'] = x['is_pay'] and charge == 0 and not x['tooth_no'] and not x['details']
        total_paid += p; total_charge += charge; total_disc += disc
        k = x['pkey']
        first_date[k] = min(first_date.get(k, x['date']), x['date'])
        last_date[k] = max(last_date.get(k, x['date']), x['date'])
    balances = collections.defaultdict(int)
    for (k, _doc), v in state.items():
        balances[k] += v
    new_keys = [k for k in balances if k not in existing_keys]
    debtors = sorted(((display[k], v) for k, v in balances.items() if v > 0), key=lambda t: -t[1])
    by_doc = {}
    for x in recs:
        b = by_doc.setdefault(x['doctor'], {'doctor': x['doctor'], 'rows': 0, 'patients': set(), 'paid': 0, 'charge': 0})
        b['rows'] += 1; b['patients'].add(x['pkey']); b['paid'] += x['paid_units']; b['charge'] += x['charge']
    by_doc = [{**b, 'patients': len(b['patients'])} for b in sorted(by_doc.values(), key=lambda b: (b['doctor'] == '', b['doctor']))]
    by_reason = collections.Counter(re.sub(r':.*', '', r['reason']) for r in review if r['severity'] == 'skipped')
    summary.update({
        'rows_total': sum(s['rows'] for s in summary['sheets']), 'rows_imported': len(recs),
        'duplicates_in_file': dup_file, 'duplicates_previous': dup_prev, 'rows_skipped': sum(by_reason.values()),
        'skipped_by_reason': dict(by_reason), 'warnings': sum(1 for r in review if r['severity'] == 'warn'),
        'patients': len(balances), 'patients_new': len(new_keys), 'patients_existing': len(balances) - len(new_keys), 'by_doctor': by_doc,
        'names_merged_groups': len(merged), 'date_fixed': sum(s['date_fixed'] for s in summary['sheets']),
        'total_paid': total_paid, 'total_charge': total_charge, 'total_discount': total_disc,
        'payment_rows': sum(1 for x in recs if x['is_pay']), 'payment_rows_total': sum(x['paid_units'] for x in recs if x['is_pay']),
        'outstanding_total': sum(v for _, v in debtors), 'debtors_count': len(debtors),
        'date_from': min((x['date'] for x in recs), default=None), 'date_to': max((x['date'] for x in recs), default=None),
        'multiplier': mult,
    })
    for k in ('date_from', 'date_to'):
        summary[k] = summary[k].isoformat() if summary[k] else None
    plan = {'recs': recs, 'display': display, 'first_date': first_date, 'balances': dict(balances)}
    work_groups = sorted(({'name': n, 'rows': sum(v.values()), 'variants': [[w, k] for w, k in v.most_common(30)]} for n, v in work_merged.items()), key=lambda g: -g['rows'])
    summary['work_merged_rows'] = sum(g['rows'] for g in work_groups)
    preview = {'summary': summary, 'merged_names': merged[:150], 'work_merged': work_groups, 'review': review[:5000], 'review_total': len(review),
               'top_debtors': [{'name': n, 'remaining': v} for n, v in debtors[:15]],
               'sample': [{'sheet': x['sheet'], 'row': x['row'], 'name': display[x['pkey']], 'date': x['date'].isoformat(), 'work': x['work'],
                           'tooth': x['tooth_no'] or '', 'paid': x['paid_units'], 'charge': x['charge'], 'date_fixed': x['date_fixed'], 'doctor': x['doctor']} for x in recs[:25]]}
    return plan, preview


def commit_plan(db, plan, user, filename, backup_name=None):
    now = now_iso()
    existing = {}
    no_doctor = set()
    for r in db.execute('SELECT id, name_norm, doctor FROM patients WHERE deleted=0'):
        existing.setdefault(r['name_norm'].replace(' ', ''), r['id'])
        if not r['doctor']:
            no_doctor.add(r['id'])
    first_doc = {}
    for x in plan['recs']:
        if x.get('doctor'):
            first_doc.setdefault(x['pkey'], x['doctor'])
    max_file = db.execute('SELECT COALESCE(MAX(file_no),1000) FROM patients').fetchone()[0]
    batch = db.execute('INSERT INTO import_batches(ts,filename,user,backup_name) VALUES(?,?,?,?)', (now, filename, user, backup_name)).lastrowid
    pid_of, visit_of = {}, {}
    new_patients = n_visits = n_proc = n_pay = n_adj = 0
    for x in plan['recs']:
        k = x['pkey']
        if k not in pid_of:
            if k in existing:
                pid_of[k] = existing[k]
            else:
                max_file += 1
                nm = plan['display'][k]
                pid_of[k] = db.execute(
                    'INSERT INTO patients(file_no,full_name,name_norm,phone,phone_norm,first_visit_date,notes,doctor,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (max_file, nm, norm_ar(nm), None, None, plan['first_date'][k].isoformat(), 'مستورد من Excel', first_doc.get(k), now, now)).lastrowid
                new_patients += 1
            if pid_of[k] in no_doctor and first_doc.get(k):   # مراجع موجود بلا طبيب: نعطيه طبيب الشيت
                db.execute('UPDATE patients SET doctor=?, updated_at=? WHERE id=?', (first_doc[k], now, pid_of[k]))
                no_doctor.discard(pid_of[k])
        pid = pid_of[k]
        iso = x['date'].isoformat()
        doc = x.get('doctor') or ''   # «» صريح = شيت مشترك: يبقى «غير محدد» في التقارير ولا يُنسب لطبيب المراجع
        vid = None
        if not x['pay_only']:
            vid = visit_of.get((pid, iso, doc))
            if vid is None:
                vid = db.execute('INSERT INTO visits(patient_id,visit_date,doctor,created_at,updated_at) VALUES(?,?,?,?,?)', (pid, iso, doc, now, now)).lastrowid
                visit_of[(pid, iso, doc)] = vid
                n_visits += 1
            db.execute('INSERT INTO procedures(visit_id,patient_id,name,tooth_no,details,status,cost,doctor,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (vid, pid, x['work'][:200], x['tooth_no'], x['details'], 'completed', x['charge'], doc, now, now))
            n_proc += 1
        if x['paid_units'] > 0:
            db.execute("INSERT INTO payments(patient_id,visit_id,pay_date,amount,kind,method,notes,idem_key,created_by,created_at,doctor) VALUES(?,?,?,?, 'payment','cash',?,?,?,?,?)",
                       (pid, vid, iso, x['paid_units'], 'مستورد من Excel (شيت %s، صف %s)' % (x['sheet'], x['row']), 'imp:' + x['fp'], user, now, doc))
            n_pay += 1
        if x['discount'] > 0:
            db.execute("INSERT INTO adjustments(patient_id,adj_date,amount,kind,notes,created_by,created_at) VALUES(?,?,?, 'discount',?,?,?)",
                       (pid, iso, x['discount'], 'تسوية عند الاستيراد (فرق الرصيد المتبقي في الشيت %s صف %s)' % (x['sheet'], x['row']), user, now))
            n_adj += 1
        db.execute('INSERT INTO import_rows(fingerprint,batch_id) VALUES(?,?)', (x['fp'], batch))
    result = {'batch': batch, 'patients_new': new_patients, 'patients_total': len(pid_of), 'visits': n_visits, 'procedures': n_proc, 'payments': n_pay, 'adjustments': n_adj}
    db.execute('UPDATE import_batches SET rows_imported=?, patients_new=?, summary_json=? WHERE id=?',
               (len(plan['recs']), new_patients, json.dumps(result, ensure_ascii=False), batch))
    audit(db, user, 'import', batch, 'import', None, {**result, 'filename': filename}, backup_name)
    return result
