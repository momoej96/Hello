# -*- coding: utf-8 -*-
"""كاتب ملفات Excel (xlsx) بدون مكتبات خارجية، مع اتجاه الورقة من اليمين لليسار."""
import io, zipfile
from xml.sax.saxutils import escape


def _col(n):
    s = ''
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _clean(s):
    return ''.join(ch for ch in str(s) if ch == '\t' or ch == '\n' or ord(ch) >= 32)


def build_xlsx(title, headers, rows):
    ncols = len(headers)
    widths = [max(10, min(45, len(_clean(h)) + 4)) for h in headers]
    for r in rows:
        for i, v in enumerate(r[:ncols]):
            widths[i] = max(widths[i], min(45, len(_clean(v)) + 3))
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews><cols>']
    for i, w in enumerate(widths):
        out.append('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, w))
    out.append('</cols><sheetData>')

    def cell(ref, v, style=0):
        if isinstance(v, bool):
            v = str(v)
        if isinstance(v, (int, float)):
            return '<c r="%s" s="2"><v>%s</v></c>' % (ref, v)
        return '<c r="%s" t="inlineStr" s="%d"><is><t xml:space="preserve">%s</t></is></c>' % (
            ref, style, escape(_clean(v)))

    out.append('<row r="1">' + ''.join(cell(_col(i) + '1', h, 1) for i, h in enumerate(headers)) + '</row>')
    for ri, r in enumerate(rows, start=2):
        out.append('<row r="%d">' % ri + ''.join(
            cell(_col(i) + str(ri), v) for i, v in enumerate(r[:ncols]) if v is not None) + '</row>')
    out.append('</sheetData></worksheet>')
    sheet = ''.join(out)
    name = escape(_clean(title)[:28].replace('/', '-').replace('\\', '-').replace('?', '').replace('*', '')
                  .replace('[', '').replace(']', '').replace(':', '')) or 'Sheet1'
    files = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>' % name,
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        'xl/worksheets/sheet1.xml': sheet,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, c in files.items():
            z.writestr(n, c)
    return buf.getvalue()


def build_csv(headers, rows):
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(['' if v is None else v for v in r])
    return ('\ufeff' + buf.getvalue()).encode('utf-8')


def build_xlsx_multi(sheets):
    """sheets: قائمة (اسم, عناوين, صفوف). ينتج ملف xlsx بعدة شيتات من اليمين لليسار."""
    from xml.sax.saxutils import escape as esc
    used, names = set(), []
    for t, _, _ in sheets:
        n = _clean(t)[:28]
        for ch in '/\\?*[]:':
            n = n.replace(ch, '-')
        n = n or 'Sheet'
        base, i = n, 2
        while n in used:
            n = '%s%d' % (base[:26], i); i += 1
        used.add(n); names.append(n)
    def sheet_xml(headers, rows):
        ncols = len(headers)
        widths = [max(10, min(45, len(_clean(h)) + 4)) for h in headers]
        for r in rows[:2000]:
            for i, v in enumerate(r[:ncols]):
                widths[i] = max(widths[i], min(45, len(_clean(v)) + 3))
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView rightToLeft="1" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>']
        out += ['<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, w) for i, w in enumerate(widths)]
        out.append('</cols><sheetData>')
        def cell(ref, v, style=0):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return '<c r="%s" s="2"><v>%s</v></c>' % (ref, v)
            return '<c r="%s" t="inlineStr" s="%d"><is><t xml:space="preserve">%s</t></is></c>' % (ref, style, esc(_clean(v)))
        out.append('<row r="1">' + ''.join(cell(_col(i) + '1', h, 1) for i, h in enumerate(headers)) + '</row>')
        for ri, r in enumerate(rows, start=2):
            out.append('<row r="%d">' % ri + ''.join(cell(_col(i) + str(ri), v) for i, v in enumerate(r[:ncols]) if v is not None and v != '') + '</row>')
        out.append('</sheetData></worksheet>')
        return ''.join(out)
    n = len(sheets)
    ct = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1) for i in range(n)) + '</Types>'
    wb = '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (esc(nm), i + 1, i + 1) for i, nm in enumerate(names)) + '</sheets></workbook>'
    rels = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(n)) + '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>' % (n + 1)
    styles = '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', wb); z.writestr('xl/_rels/workbook.xml.rels', rels); z.writestr('xl/styles.xml', styles)
        for i, (_, h, r) in enumerate(sheets):
            z.writestr('xl/worksheets/sheet%d.xml' % (i + 1), sheet_xml(h, r))
    return buf.getvalue()
