'use strict';
/* ====== أدوات عامة ====== */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const S = { user: null, perms: [], settings: {}, demo: false, cats: [] };
const can = p => S.perms.includes('*') || S.perms.includes(p);
const ACTIONS = {}, CHANGES = {};
/* أسماء الأطباء من الإعدادات، وخيارات قائمة اختيار الطبيب (مع إبقاء القيمة الحالية إن لم تعد في القائمة) */
/* عرض سن أو عدة أسنان مخزنة بصيغة «11,21» */
const teethTags = s => String(s || '').split(',').filter(Boolean).map(t => `<span class="tooth-tag">${esc(t)}</span>`).join(' ');
const teethText = s => String(s || '').split(',').filter(Boolean).join('، ');
const doctorList = () => { try { return JSON.parse(S.settings.doctors || '[]'); } catch (e) { return []; } };
const doctorOptions = cur => { const l = doctorList(); if (cur && !l.includes(cur)) l.push(cur); return [{ v: '', t: '— اختر الطبيب —' }].concat(l.map(x => ({ v: x, t: x }))); };
let RPT = null; // التقرير الحالي (للطباعة والتصدير)

const PROC_ST = { planned: 'مخطط له', in_progress: 'قيد التنفيذ', completed: 'مكتمل', cancelled: 'ملغى' };
const APPT_ST = { confirmed: 'مؤكد', completed: 'مكتمل', cancelled: 'ملغى', no_show: 'لم يحضر' };
const METH = { cash: 'نقداً', transfer: 'تحويل', other: 'أخرى' };
const COMMON_PROCS = ['فحص وتشخيص', 'تنظيف الأسنان', 'حشوة تجميلية', 'حشوة عصب', 'علاج عصب', 'تاج (تلبيس)', 'خلع سن',
  'خلع جراحي', 'زراعة سن', 'تبييض الأسنان', 'تقويم أسنان', 'أشعة بانوراما', 'أشعة periapical', 'جسر أسنان', 'طقم أسنان', 'تلميع وتنظيف لثة'];

const ICONS = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><circle cx="17.5" cy="9" r="2.5"/><path d="M17 14c2.6 0 4.5 1.8 4.5 4.5"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l5 5"/>',
  chart: '<path d="M4 20V4M4 20h16"/><path d="M8 16v-5M12 16V8M16 16v-8"/>',
  wallet: '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 10h18"/><circle cx="16.5" cy="14.5" r="1"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  print: '<path d="M7 9V3h10v6"/><rect x="4" y="9" width="16" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
  download: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/>',
  trash: '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  alert: '<path d="M12 4l9 16H3L12 4z"/><path d="M12 10v4M12 17h.01"/>',
  check: '<path d="M5 13l4 4L19 7"/>',
  logout: '<path d="M10 4H5v16h5M14 8l5 4-5 4M19 12H9"/>',
  tooth: '<path d="M7 3C4.5 3 3 5 3 7.5c0 2 .8 3.4 1.5 5 .8 1.9 1 5.3 2 7.8.4 1 1.6 1 2-.1.6-1.7.8-4 1.5-5 .6-.8 3.4-.8 4 0 .7 1 .9 3.3 1.5 5 .4 1.1 1.6 1.1 2 .1 1-2.5 1.2-5.9 2-7.8.7-1.6 1.5-3 1.5-5C21 5 19.5 3 17 3c-2 0-3 1-5 1S9 3 7 3z"/>',
  wallet2: '<path d="M4 7h14a2 2 0 012 2v9a2 2 0 01-2 2H4z"/><path d="M4 7l11-3v3"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const icon = (n, size = 18) => `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ''}</svg>`;

/* ====== التواريخ والأرقام ====== */
const pad2 = n => String(n).padStart(2, '0');
const isoOf = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const today = () => isoOf(new Date());
const nowTime = () => { const d = new Date(); return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`; };
const parseISO = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (s, n) => { const d = parseISO(s); d.setDate(d.getDate() + n); return isoOf(d); };
const monthRange = ym => { const [y, m] = ym.split('-').map(Number); return [`${y}-${pad2(m)}-01`, `${y}-${pad2(m)}-${pad2(new Date(y, m, 0).getDate())}`]; };
const MONTHS_AR = ['كانون الثاني', 'شباط', 'آذار', 'نيسان', 'أيار', 'حزيران', 'تموز', 'آب', 'أيلول', 'تشرين الأول', 'تشرين الثاني', 'كانون الأول'];
const DAYS_AR = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
const dayName = s => DAYS_AR[parseISO(s).getDay()];
const toLatin = s => String(s ?? '').replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d)).replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d));
const fmt = n => { n = Math.round(Number(n) || 0); return (n < 0 ? '-' : '') + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ','); };
const cur = () => S.settings.currency_symbol || '';
const fmtMoney = n => `${fmt(n)} ${cur()}`.trim();
const moneyH = (n, cls = '') => `<bdi class="num ${cls}">${fmt(n)}</bdi> <small class="cur">${esc(cur())}</small>`;
const dateH = d => d ? `<bdi class="num">${esc(d)}</bdi>` : '<span class="muted">—</span>';
const parseMoney = s => { const t = toLatin(s).replace(/[^\d]/g, ''); return t === '' ? '' : Number(t); };
const uid = () => (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : 'k' + Date.now() + Math.random().toString(16).slice(2);
const normQ = s => toLatin(String(s).toLowerCase()).replace(/[\u064B-\u065F\u0670\u0640]/g, '').replace(/[أإآٱ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه');
const nl2br = s => esc(s).replace(/\n/g, '<br>');

/* ====== الاتصال بالخادم ====== */
let idleTimer = Date.now();
class ApiErr extends Error { constructor(m, status, code, data) { super(m); this.status = status; this.code = code; this.data = data || {}; } }
async function api(method, url, body, opts = {}) {
  idleTimer = Date.now();
  const o = { method, headers: { 'X-Requested-With': 'clinic' }, credentials: 'same-origin' };
  if (opts.raw) { o.body = opts.raw; o.headers['Content-Type'] = 'application/octet-stream'; }
  else if (body !== undefined && body !== null) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(body); }
  let r;
  try { r = await fetch(url, o); } catch (e) { throw new ApiErr('تعذّر الاتصال بالبرنامج. تأكد أن نافذة التشغيل السوداء ما زالت مفتوحة.', 0, 'network'); }
  if (opts.blob && r.ok) return r.blob();
  let d = {}; try { d = await r.json(); } catch (e) { }
  if (!r.ok) {
    if (r.status === 401 && d.code === 'auth' && window.onSessionLost) window.onSessionLost();
    throw new ApiErr(d.error || 'حدث خطأ غير متوقع', r.status, d.code, d);
  }
  return d;
}
const qs = o => Object.entries(o).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

/* ====== إشعارات ونوافذ ====== */
function toast(msg, kind = 'ok') {
  const t = document.createElement('div');
  t.className = 'toast ' + kind; t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.classList.add('out'), kind === 'err' ? 6000 : 3000);
  setTimeout(() => t.remove(), kind === 'err' ? 6400 : 3400);
}

function modal({ title, body, wide, footer, onClose, cls = '' }) {
  const ov = document.createElement('div');
  ov.className = 'overlay';
  ov.innerHTML = `<div class="dialog ${wide ? 'wide' : ''} ${cls}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
    <header><h3>${esc(title)}</h3><button type="button" class="x" data-close aria-label="إغلاق">×</button></header>
    <div class="dlg-body">${body}</div>${footer ? `<footer>${footer}</footer>` : ''}</div>`;
  document.body.appendChild(ov);
  const ctrl = {
    el: ov, body: $('.dlg-body', ov),
    close() { ov.remove(); document.removeEventListener('keydown', esc_); if (onClose) onClose(); },
  };
  const esc_ = e => { if (e.key === 'Escape' && ov === $$('.overlay').pop()) ctrl.close(); };
  document.addEventListener('keydown', esc_);
  ov.addEventListener('mousedown', e => { if (e.target === ov && !ov.dataset.sticky) { ov._down = true; } });
  ov.addEventListener('click', e => { if (e.target.closest('[data-close]')) ctrl.close(); });
  attachMoneyInputs(ov);
  const first = $('input:not([type=hidden]):not([readonly]), select, textarea', ov); if (first && !ov.dataset.nofocus) first.focus();
  return ctrl;
}

function confirmBox(msg, { danger = false, ok = 'تأكيد', cancel = 'إلغاء', title = 'تأكيد العملية' } = {}) {
  return new Promise(res => {
    const m = modal({ title, cls: 'small', body: `<p class="confirm-msg">${esc(msg)}</p>`,
      footer: `<button type="button" class="btn ${danger ? 'danger' : 'primary'}" data-yes>${esc(ok)}</button><button type="button" class="btn" data-close>${esc(cancel)}</button>`,
      onClose: () => res(false) });
    $('[data-yes]', m.el).onclick = () => { m.el.remove(); res(true); };
  });
}

function promptBox(title, label, { required = true, ok = 'متابعة' } = {}) {
  return new Promise(res => {
    const m = modal({ title, cls: 'small', body: `<form><label class="fld"><span>${esc(label)}</span><input name="v" autocomplete="off"></label></form>`,
      footer: `<button type="button" class="btn primary" data-yes>${esc(ok)}</button><button type="button" class="btn" data-close>إلغاء</button>`,
      onClose: () => res(null) });
    const go = () => { const v = $('input', m.el).value.trim(); if (required && !v) { $('input', m.el).focus(); return; } m.el.remove(); res(v); };
    $('[data-yes]', m.el).onclick = go;
    $('form', m.el).onsubmit = e => { e.preventDefault(); go(); };
  });
}

/* ====== النماذج ====== */
function fieldHTML(f, v) {
  const id = 'f_' + f.name, req = f.required ? ' required' : '';
  let input;
  if (f.type === 'select') input = `<select id="${id}" name="${f.name}">${f.options.map(o => `<option value="${esc(o.v)}" ${String(o.v) === String(v ?? '') ? 'selected' : ''}>${esc(o.t)}</option>`).join('')}</select>`;
  else if (f.type === 'textarea') input = `<textarea id="${id}" name="${f.name}" rows="${f.rows || 3}">${esc(v ?? '')}</textarea>`;
  else if (f.type === 'money') input = `<input id="${id}" name="${f.name}" inputmode="numeric" data-money autocomplete="off" value="${v !== '' && v != null ? fmt(v) : ''}"${req} placeholder="${f.placeholder || ''}">`;
  else input = `<input id="${id}" name="${f.name}" type="${f.type || 'text'}" ${f.list ? `list="${f.list}"` : ''} value="${esc(v ?? '')}" ${f.type === 'tel' ? 'inputmode="tel" dir="ltr"' : ''} autocomplete="off"${req}>`;
  return `<label class="fld ${f.cls || ''}"><span>${esc(f.label)}${f.required ? ' <b>*</b>' : ''}</span>${input}${f.hint ? `<em>${f.hint}</em>` : ''}</label>`;
}
function readForm(root, fields) {
  const o = {};
  fields.forEach(f => {
    const el = root.querySelector(`[name="${f.name}"]`); if (!el) return;
    o[f.name] = f.type === 'money' ? parseMoney(el.value) : (el.value || '').trim();
  });
  return o;
}
function attachMoneyInputs(root) {
  $$('[data-money]', root).forEach(el => {
    if (el._m) return; el._m = 1;
    el.addEventListener('input', () => { const n = parseMoney(el.value); el.value = n === '' ? '' : fmt(n); });
  });
}

/** نموذج منبثق عام. onSubmit(values, force) يعيد وعداً؛ عند أخطاء التأكيد (409) يُسأل المستخدم ويُعاد الإرسال مع force. */
function formModal({ title, fields, values = {}, submit = 'حفظ', onSubmit, wide, intro = '', cols = 2 }) {
  const m = modal({
    title, wide, body: `<form class="form-grid c${cols}" novalidate>${intro}${fields.map(f => fieldHTML(f, values[f.name])).join('')}<div class="form-err" role="alert"></div></form>`,
    footer: `<button type="button" class="btn primary" data-save>${esc(submit)}</button><button type="button" class="btn" data-close>إلغاء</button>`
  });
  const form = $('form', m.el), btn = $('[data-save]', m.el), err = $('.form-err', m.el);
  let busy = false;
  async function run() {
    if (busy) return;
    const v = readForm(form, fields);
    for (const f of fields) if (f.required && (v[f.name] === '' || v[f.name] == null)) { err.textContent = 'الحقل مطلوب: ' + f.label; $(`[name="${f.name}"]`, form).focus(); return; }
    busy = true; btn.disabled = true; err.textContent = '';
    try {
      try { await onSubmit(v, false, m); }
      catch (e) {
        if (e.code === 'overpaid' || e.code === 'duplicate') {
          if (await confirmBox(e.message, { ok: 'متابعة رغم ذلك', title: 'تنبيه' })) await onSubmit(v, true, m); else throw null;
        } else throw e;
      }
    } catch (e) { if (e) err.textContent = e.message; busy = false; btn.disabled = false; return; }
    busy = false;
  }
  btn.onclick = run;
  form.onsubmit = e => { e.preventDefault(); run(); };
  return m;
}

/* ====== الجداول ====== */
const badge = (map, v) => `<span class="badge b-${esc(v)}">${esc(map[v] || v)}</span>`;
function dataTable(host, o) {
  const st = { q: '', key: null, dir: 1 }, cols = o.cols;
  const val = (c, r) => c.val ? c.val(r) : r[c.key];
  host.innerHTML = (o.search !== false && o.rows.length > 6 ? `<div class="dt-tools"><input type="search" class="dt-q" placeholder="بحث داخل الجدول…"><span class="muted dt-count"></span></div>` : '') + '<div class="dt-body"></div>';
  const body = $('.dt-body', host);
  const view = () => {
    let rows = o.rows.slice();
    if (st.q) { const q = normQ(st.q); rows = rows.filter(r => cols.some(c => normQ(String(val(c, r) ?? '')).includes(q))); }
    if (st.key !== null) {
      const c = cols[st.key];
      rows.sort((a, b) => { let x = val(c, a), y = val(c, b); x = x ?? ''; y = y ?? ''; return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'ar')) * st.dir; });
    }
    return rows;
  };
  function draw() {
    const rows = view();
    const cnt = $('.dt-count', host); if (cnt) cnt.textContent = `${rows.length} من ${o.rows.length}`;
    body.innerHTML = `<div class="tbl-wrap"><table class="tbl"><thead><tr>${cols.map((c, i) => `<th data-i="${i}" class="${c.cls || ''} ${c.sortable === false ? '' : 'sortable'} ${st.key === i ? (st.dir > 0 ? 'asc' : 'desc') : ''}">${c.title}</th>`).join('')}</tr></thead><tbody>${rows.length ? rows.map(r => `<tr ${o.href ? `data-href="${esc(o.href(r))}"` : ''} class="${o.rowClass ? o.rowClass(r) : ''}">${cols.map(c => `<td class="${c.cls || ''}">${c.render ? c.render(r) : esc(val(c, r) ?? '')}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${cols.length}" class="empty">${o.empty || 'لا توجد بيانات'}</td></tr>`}</tbody>${o.footer ? `<tfoot>${o.footer(rows)}</tfoot>` : ''}</table></div>`;
  }
  host.addEventListener('click', e => { const th = e.target.closest('th.sortable'); if (!th) return; const i = +th.dataset.i; st.dir = st.key === i ? -st.dir : 1; st.key = i; draw(); });
  const q = $('.dt-q', host); if (q) q.addEventListener('input', () => { st.q = q.value; draw(); });
  draw();
  return { headers: () => cols.map(c => c.plain || c.title.replace(/<[^>]+>/g, '')), matrix: () => o.rows.map(r => cols.map(c => c.exp ? c.exp(r) : (val(c, r) ?? ''))) };
}

/** جدول ثابت (للطباعة والتقارير): headers: [string], rows: [[html]] */
function simpleTable(headers, rows, { foot = '', cls = '' } = {}) {
  return `<div class="tbl-wrap"><table class="tbl ${cls}"><thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.length ? rows.map(r => `<tr>${r.map(c => `<td>${c ?? ''}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${headers.length}" class="empty">لا توجد بيانات</td></tr>`}</tbody>${foot ? `<tfoot>${foot}</tfoot>` : ''}</table></div>`;
}

/* ====== الطباعة والتصدير ====== */
function printHeader(title, sub = '') {
  const s = S.settings;
  return `<div class="print-head"><div><h1>${esc(s.clinic_name)}</h1><div class="ph-sub">${[s.clinic_phone, s.clinic_address].filter(Boolean).map(esc).join(' &nbsp;|&nbsp; ')}</div></div><div class="ph-meta">تاريخ الطباعة: <bdi>${today()}</bdi></div></div><h2 class="print-title">${esc(title)}</h2>${sub ? `<div class="print-sub">${sub}</div>` : ''}`;
}
function printDoc(title, html, sub = '', size = '') {
  const root = $('#printRoot'), old = document.title;
  root.innerHTML = printHeader(title, sub) + html + `<div class="print-foot">${esc(S.settings.receipt_footer || '')}</div>`;
  document.title = title;
  let ps = null;
  if (size) { ps = document.createElement('style'); ps.textContent = `@page{size:${size};margin:8mm}`; document.head.appendChild(ps); document.body.classList.add('print-small'); }
  document.body.classList.add('printing');
  const done = () => { if (ps) ps.remove(); document.body.classList.remove('print-small'); document.body.classList.remove('printing'); root.innerHTML = ''; document.title = old; window.removeEventListener('afterprint', done); };
  window.addEventListener('afterprint', done);
  setTimeout(() => window.print(), 50);
}
async function exportRows(format, title, headers, rows) {
  try {
    const blob = await api('POST', '/api/export', { format, title, headers, rows }, { blob: true });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `${title}-${today()}.${format}`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast('تم تجهيز الملف (' + format.toUpperCase() + ')');
  } catch (e) { toast(e.message, 'err'); }
}
const exportBar = (extra = '') => `<div class="exp-bar no-print">${extra}<button type="button" class="btn sm" data-action="rpt-print">${icon('print', 16)} طباعة / حفظ PDF</button><button type="button" class="btn sm" data-action="rpt-xlsx">${icon('download', 16)} Excel</button><button type="button" class="btn sm" data-action="rpt-csv">${icon('download', 16)} CSV</button></div>`;
ACTIONS['rpt-print'] = () => { if (RPT) printDoc(RPT.title, RPT.html, RPT.sub || ''); };
ACTIONS['rpt-xlsx'] = () => { if (RPT) exportRows('xlsx', RPT.title, RPT.headers, RPT.rows); };
ACTIONS['rpt-csv'] = () => { if (RPT) exportRows('csv', RPT.title, RPT.headers, RPT.rows); };

/* ====== اختيار مراجع بالبحث ====== */
function patientPicker(host, { onPick } = {}) {
  host.innerHTML = `<div class="picker"><input type="search" placeholder="ابحث بالاسم أو الهاتف أو رقم الملف…" autocomplete="off"><div class="pk-res"></div><div class="pk-sel"></div></div>`;
  const inp = $('input', host), res = $('.pk-res', host), sel = $('.pk-sel', host);
  let t, picked = null;
  inp.addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      if (!inp.value.trim()) { res.innerHTML = ''; return; }
      try {
        const d = await api('GET', '/api/patients?' + qs({ q: inp.value, limit: 8 }));
        res.innerHTML = d.patients.map(p => `<button type="button" class="pk-item" data-id="${p.id}"><b>${esc(p.full_name)}</b><span class="muted"> — ملف <bdi>${p.file_no}</bdi> · <bdi>${esc(p.phone || '')}</bdi></span></button>`).join('') || '<div class="muted pad">لا توجد نتائج</div>';
        res._rows = d.patients;
      } catch (e) { res.innerHTML = `<div class="pad err">${esc(e.message)}</div>`; }
    }, 180);
  });
  res.addEventListener('click', e => {
    const b = e.target.closest('.pk-item'); if (!b) return;
    picked = res._rows.find(p => p.id == b.dataset.id);
    sel.innerHTML = `<div class="chip">${icon('user', 16)} ${esc(picked.full_name)} <span class="muted">(ملف <bdi>${picked.file_no}</bdi>)</span></div>`;
    res.innerHTML = ''; inp.value = ''; if (onPick) onPick(picked);
  });
  return { get: () => picked, set(p) { picked = p; sel.innerHTML = `<div class="chip">${icon('user', 16)} ${esc(p.full_name)}</div>`; } };
}

/* ====== أحداث عامة ====== */
document.addEventListener('click', e => {
  const a = e.target.closest('[data-action]');
  if (a) { const fn = ACTIONS[a.dataset.action]; if (fn) { e.preventDefault(); fn(a, e); } return; }
  const tr = e.target.closest('tr[data-href]');
  if (tr && !e.target.closest('a,button,select,input,label')) location.hash = tr.dataset.href;
});
document.addEventListener('change', e => { const a = e.target.closest('[data-change]'); if (a && CHANGES[a.dataset.change]) CHANGES[a.dataset.change](a, e); });
['mousemove', 'keydown', 'click', 'touchstart', 'scroll'].forEach(ev => document.addEventListener(ev, () => { idleTimer = Date.now(); }, { passive: true }));
const getIdle = () => idleTimer;
