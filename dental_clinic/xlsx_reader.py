# -*- coding: utf-8 -*-
"""قارئ ملفات Excel (xlsx) وCSV بدون مكتبات خارجية. يتجاهل الأعمدة الفارغة الكثيرة ويحوّل التواريخ."""
import io, re, csv, zipfile, datetime
import xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RNS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
BUILTIN_DATE_FMTS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))


def _col_index(ref):
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n - 1


def _is_date_format(code):
    c = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', code or '').lower()
    return bool(re.search(r'[ymd]', c)) and not re.search(r'0\.0|#', c)


def _serial_to_dt(v, date1904=False):
    base = datetime.datetime(1904, 1, 1) if date1904 else datetime.datetime(1899, 12, 30)
    try:
        return base + datetime.timedelta(days=float(v))
    except (OverflowError, ValueError):
        return None


def list_sheets(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    wb = ET.fromstring(z.read('xl/workbook.xml'))
    rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    target = {r.get('Id'): r.get('Target') for r in rels}
    out = []
    for s in wb.find(NS + 'sheets'):
        t = target.get(s.get(RNS + 'id'), '')
        t = t.lstrip('/')
        out.append((s.get('name'), t if t.startswith('xl/') else 'xl/' + t, s.get('state', 'visible')))
    return z, out, (wb.find(NS + 'workbookPr') is not None and wb.find(NS + 'workbookPr').get('date1904') in ('1', 'true'))


def read_xlsx(data, max_cols=40):
    """يعيد قائمة (اسم الشيت، [صفوف]) كل صف قائمة قيم (None للفارغ) برقم الصف الأصلي: (row_no, [values])."""
    z, sheets, d1904 = list_sheets(data)
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for _, el in ET.iterparse(io.BytesIO(z.read('xl/sharedStrings.xml'))):
            if el.tag == NS + 'si':
                shared.append(''.join(t.text or '' for t in el.iter(NS + 't')))
                el.clear()
    date_styles = set()
    if 'xl/styles.xml' in z.namelist():
        st = ET.fromstring(z.read('xl/styles.xml'))
        custom = {int(n.get('numFmtId')): n.get('formatCode') for n in st.iter(NS + 'numFmt')}
        xfs = st.find(NS + 'cellXfs')
        if xfs is not None:
            for i, xf in enumerate(xfs):
                fid = int(xf.get('numFmtId', 0))
                if fid in BUILTIN_DATE_FMTS or (fid in custom and _is_date_format(custom[fid])):
                    date_styles.add(i)
    result = []
    for name, path, state in sheets:
        if state != 'visible' or path not in z.namelist():
            continue
        rows = []
        for _, row in ET.iterparse(io.BytesIO(z.read(path))):
            if row.tag != NS + 'row':
                continue
            vals = [None] * max_cols
            has = False
            for c in row.iter(NS + 'c'):
                ci = _col_index(c.get('r', 'A1'))
                if ci >= max_cols or ci < 0:
                    continue
                t, s = c.get('t'), c.get('s')
                v = c.find(NS + 'v')
                val = None
                if t == 's' and v is not None and v.text is not None:
                    val = shared[int(v.text)]
                elif t == 'inlineStr':
                    val = ''.join(x.text or '' for x in c.iter(NS + 't'))
                elif t in ('str', 'e') and v is not None:
                    val = v.text
                elif t == 'b' and v is not None:
                    val = v.text == '1'
                elif v is not None and v.text not in (None, ''):
                    try:
                        f = float(v.text)
                        if s is not None and int(s) in date_styles:
                            val = _serial_to_dt(f, d1904)
                        else:
                            val = int(f) if f == int(f) else f
                    except ValueError:
                        val = v.text
                if isinstance(val, str) and val.strip() == '':
                    val = None
                if val is not None:
                    vals[ci] = val
                    has = True
            if has:
                rows.append((int(row.get('r', len(rows) + 1)), vals))
            row.clear()
        result.append((name, rows))
    return result


def read_csv(data, max_cols=40):
    for enc in ('utf-8-sig', 'cp1256', 'latin-1'):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = []
    for i, r in enumerate(csv.reader(io.StringIO(text)), 1):
        vals = [(c.strip() or None) for c in r[:max_cols]] + [None] * max(0, max_cols - len(r))
        if any(v is not None for v in vals):
            out = []
            for v in vals:
                if isinstance(v, str) and re.fullmatch(r'-?\d+(\.\d+)?', v):
                    f = float(v)
                    v = int(f) if f == int(f) else f
                out.append(v)
            rows.append((i, out))
    return [('csv', rows)]


def read_any(data, filename=''):
    if data[:2] == b'PK':
        return read_xlsx(data)
    if filename.lower().endswith('.xls') and data[:4] == b'\xd0\xcf\x11\xe0':
        raise ValueError('صيغة xls القديمة غير مدعومة. افتح الملف في Excel واحفظه بصيغة xlsx ثم أعد المحاولة.')
    return read_csv(data)
