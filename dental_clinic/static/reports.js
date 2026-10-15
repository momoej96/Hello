'use strict';
/* ====== لوحة التحكم والتقارير والمصروفات ====== */
const statGrid = items => `<div class="stats">${items.filter(Boolean).map(i => `<div class="stat ${i.cls || ''}"><span>${i.label}</span><b>${i.value}</b>${i.note ? `<em>${i.note}</em>` : ''}</div>`).join('')}</div>`;
const intH = n => `<bdi class="num">${fmt(n)}</bdi>`;

async function pageDashboard(main) {
  const d = await api('GET', '/api/dashboard?today=' + today());
  const money = can('payments');
  const tiles = [
    ['new-patient', null, 'plus', 'إضافة مراجع جديد', 'patients'], [null, '#/patients', 'search', 'البحث عن مراجع', 'patients'],
    [null, '#/bydate', 'users', 'مراجعو يوم محدد', 'visits'], [null, '#/appointments', 'calendar', 'سجل المواعيد والزيارات', 'appointments'],
    [null, '#/reports/daily', 'wallet', 'التقرير المالي اليومي', 'reports_basic'], [null, '#/reports/monthly', 'chart', 'التقرير المالي الشهري', 'reports_full'],
    [null, '#/reports/yearly', 'chart', 'التقرير المالي السنوي', 'reports_full'], [null, '#/reports/dues', 'list', 'الإيرادات والمبالغ المستحقة', 'reports_full'],
    [null, '#/reports/debtors', 'alert', 'المراجعون المدينون', 'reports_basic'], [null, '#/settings', 'gear', 'الإعدادات والنسخ الاحتياطي', 'settings'],
  ].filter(t => can(t[4]));
  main.innerHTML = `<div class="page-head"><h1>لوحة التحكم</h1><span class="muted">${dayName(d.today)} <bdi>${d.today}</bdi></span></div>
  <section class="ledger">
    <div><span>المراجعون المسجلون</span><b>${intH(d.patients_count)}</b></div>
    <div><span>زيارات اليوم</span><b>${intH(d.visits_today)}</b></div>
    ${money ? `<div class="hl"><span>مقبوضات اليوم</span><b>${moneyH(d.receipts_today)}</b></div><div><span>مقبوضات الشهر</span><b>${moneyH(d.receipts_month)}</b></div><div><span>مقبوضات السنة</span><b>${moneyH(d.receipts_year)}</b></div>
    <div class="due"><span>إجمالي المستحق على المراجعين</span><b>${moneyH(d.total_dues)}</b><em>${intH(d.debtors_count)} مراجع</em></div>` : ''}
  </section>
  <section class="tiles">${tiles.map(t => t[0] ? `<button type="button" class="tile" data-action="${t[0]}">${icon(t[2], 26)}<span>${t[3]}</span></button>` : `<a class="tile" href="${t[1]}">${icon(t[2], 26)}<span>${t[3]}</span></a>`).join('')}</section>
  <section class="card"><h3>مواعيد اليوم <span class="cnt">${d.appointments_today.length}</span></h3>
    ${d.appointments_today.length ? `<div class="alist">${d.appointments_today.map(a => `<div class="appt a-${a.status}"><bdi class="atime">${esc(a.appt_time || '')}</bdi><div class="ainfo"><a class="pname" href="#/patient/${a.patient_id}">${esc(a.full_name)}</a><div class="muted small">${esc(a.reason || '')}</div></div>${badge(APPT_ST, a.status)}</div>`).join('')}</div>` : '<p class="muted">لا توجد مواعيد لهذا اليوم.</p>'}</section>`;
}

/* ---- التقارير ---- */
const REPORT_TABS_ALL = [['daily', 'اليومي', 'reports_basic'], ['monthly', 'الشهري', 'reports_full'], ['yearly', 'السنوي', 'reports_full'], ['period', 'فترة مخصصة', 'reports_full'], ['dues', 'الإيرادات والمستحقات', 'reports_full'], ['debtors', 'المدينون', 'reports_basic']];
async function pageReports(main, tab) {
  const REPORT_TABS = REPORT_TABS_ALL.filter(t => can(t[2]));
  tab = tab || REPORT_TABS[0][0];
  main.innerHTML = `<div class="page-head"><h1>التقارير المالية</h1></div><nav class="tabs">${REPORT_TABS.map(t => `<a href="#/reports/${t[0]}" class="${t[0] === tab ? 'on' : ''}">${t[1]}</a>`).join('')}</nav><div id="rep"></div>`;
  const host = $('#rep');
  ({ daily: repDaily, monthly: repMonthly, yearly: repYearly, period: repPeriod, dues: repDues, debtors: repDebtors }[tab] || repDaily)(host);
}
const dateNav = (id, v) => `<div class="toolbar no-print"><button type="button" class="btn sm" data-action="rep-nav" data-n="-1">‹ السابق</button><input type="date" id="${id}" value="${v}"><button type="button" class="btn sm" data-action="rep-nav" data-n="1">التالي ›</button></div>`;
const statsHTML = (s, ex = true) => statGrid([
  { label: 'إجمالي المقبوضات الفعلية', value: moneyH(s.receipts), cls: 'good', note: `${intH(s.payments_count)} دفعة` },
  { label: 'مقبوضات نقدية', value: moneyH(s.receipts_by_method.cash.total) },
  { label: 'مقبوضات بالتحويل / أخرى', value: moneyH(s.receipts_by_method.transfer.total + s.receipts_by_method.other.total) },
  { label: 'قيمة العلاجات المنفذة (مكتملة)', value: moneyH(s.executed_value) },
  { label: 'قيمة العلاجات المسجلة / المتفق عليها', value: moneyH(s.agreed_value), note: 'منفصلة عن المقبوضات' },
  { label: 'الخصومات', value: moneyH(s.discounts) },
  { label: 'المبالغ المستردة (خرجت من الصندوق)', value: moneyH(s.refunds) },
  { label: 'عدد الزيارات', value: intH(s.visits_count), note: `${intH(s.visitors_count)} مراجع` },
  { label: 'مراجعون جدد', value: intH(s.new_patients) },
  { label: 'متوسط المقبوض لكل زيارة', value: moneyH(s.avg_per_visit) },
  ex && can('expenses') ? { label: 'المصروفات', value: moneyH(s.expenses) } : null,
  ex && can('expenses') ? { label: 'صافي التدفق النقدي', value: moneyH(s.net_cash_flow), cls: s.net_cash_flow < 0 ? 'bad' : 'good', note: 'المقبوضات − المصروفات − المستردات' } : null,
  ex && can('expenses') ? { label: 'الربح التقديري (تقريبي)', value: moneyH(s.estimated_profit), note: 'العلاجات المنفذة − الخصومات − المصروفات. ليس صافي ربح محاسبياً نهائياً.' } : null,
]);
const statsPrint = s => simpleTable(['البند', 'القيمة'], [['إجمالي المقبوضات الفعلية', fmtMoney(s.receipts)], ['مقبوضات نقدية', fmtMoney(s.receipts_by_method.cash.total)], ['مقبوضات بالتحويل / أخرى', fmtMoney(s.receipts_by_method.transfer.total + s.receipts_by_method.other.total)], ['قيمة العلاجات المنفذة', fmtMoney(s.executed_value)], ['قيمة العلاجات المسجلة / المتفق عليها', fmtMoney(s.agreed_value)], ['الخصومات', fmtMoney(s.discounts)], ['المبالغ المستردة', fmtMoney(s.refunds)], ['عدد الزيارات', fmt(s.visits_count)], ['مراجعون جدد', fmt(s.new_patients)], ['متوسط المقبوض لكل زيارة', fmtMoney(s.avg_per_visit)]].concat(can('expenses') ? [['المصروفات', fmtMoney(s.expenses)], ['صافي التدفق النقدي', fmtMoney(s.net_cash_flow)], ['الربح التقديري (تقريبي)', fmtMoney(s.estimated_profit)]] : []));

/* عمل كل طبيب: الإجراءات المنفذة والمتفق عليها والمقبوض المنسوب له */
const DOC_HEAD = ['الطبيب', 'المراجعون', 'الزيارات', 'الإجراءات', 'قيمة العمل المنفذ (مكتمل)', 'النسبة من المنفذ', 'العلاجات المسجلة / المتفق عليها', 'المقبوض المنسوب'];
const DOC_NOTE = '<p class="muted small">يُنسب الإجراء لطبيب الزيارة (أو الطبيب المعالج للمراجع إن لم يُحدد). يُنسب المقبوض لطبيب شيت الاستيراد أو الزيارة المرتبطة بالدفعة، وإلا للطبيب المعالج للمراجع. الشغل المستورد من شيت مشترك يبقى «غير محدد».</p>';
function doctorTable(rows, money = moneyH, int = intH) {
  if (!rows || !rows.length) return '<p class="muted">لا يوجد عمل مسجل للأطباء في هذه الفترة.</p>';
  const sum = k => rows.reduce((a, r) => a + r[k], 0);
  return simpleTable(DOC_HEAD, rows.map(r => [esc(r.doctor), int(r.patients), int(r.visits), int(r.procedures), `<b>${money(r.executed)}</b>`, `<bdi>${r.share}%</bdi>`, money(r.agreed), money(r.receipts)]),
    { foot: `<tr class="tot"><td>المجموع</td><td></td><td>${int(sum('visits'))}</td><td>${int(sum('procedures'))}</td><td>${money(sum('executed'))}</td><td></td><td>${money(sum('agreed'))}</td><td>${money(sum('receipts'))}</td></tr>` });
}
const doctorCard = rows => {
  const chart = rows && rows.length > 1 ? barChart({ labels: rows.map(r => r.doctor), series: [{ name: '', color: '#0e7c7b', values: rows.map(r => r.executed) }], title: 'العمل المنفذ لكل طبيب' }) : '';
  return `<section class="card"><h3>عمل الأطباء</h3>${chart}${doctorTable(rows)}${DOC_NOTE}</section>`;
};
const doctorPrint = rows => '<h3>عمل الأطباء</h3>' + doctorTable(rows, fmtMoney, fmt);

let REP_DATE = today();
ACTIONS['rep-nav'] = b => { const i = $('#rd'); if (!i) return; i.value = addDays(i.value, +b.dataset.n); i.dispatchEvent(new Event('change')); };
async function repDaily(host) {
  host.innerHTML = dateNav('rd', REP_DATE) + '<div id="rb"></div>';
  async function load() {
    REP_DATE = $('#rd').value || today();
    try {
      const d = await api('GET', '/api/reports/daily?date=' + REP_DATE), s = d.stats;
      const payRows = d.payments.map(p => [dateH(p.pay_date), `<a class="pname" href="#/patient/${p.patient_id}">${esc(p.full_name)}</a>`, p.kind === 'refund' ? 'مسترد' : 'دفعة', moneyH(p.kind === 'refund' ? -p.amount : p.amount), METH[p.method], esc(p.notes || '')]);
      const body = `${statsHTML(s)}${doctorCard(d.by_doctor)}<section class="card"><h3>تفاصيل الدفعات</h3>${simpleTable(['التاريخ', 'المراجع', 'النوع', 'المبلغ', 'الطريقة', 'ملاحظات'], payRows)}</section>
        <section class="card"><h3>زيارات اليوم</h3>${simpleTable(['الوقت', 'المراجع', 'الإجراءات', 'تكلفة العلاج'], d.visits.map(v => [`<bdi>${esc(v.visit_time || '')}</bdi>`, `<a class="pname" href="#/patient/${v.patient_id}">${esc(v.full_name)}</a>`, esc(v.procedures.map(p => p.name).join('، ')), moneyH(v.visit_cost)]))}</section>`;
      $('#rb').innerHTML = exportBar() + body;
      RPT = { title: 'التقرير المالي اليومي', sub: `التاريخ: <bdi>${REP_DATE}</bdi> (${dayName(REP_DATE)})`, html: statsPrint(s) + doctorPrint(d.by_doctor) + '<h3>تفاصيل الدفعات</h3>' + simpleTable(['التاريخ', 'المراجع', 'النوع', 'المبلغ', 'الطريقة'], d.payments.map(p => [`<bdi>${p.pay_date}</bdi>`, esc(p.full_name), p.kind === 'refund' ? 'مسترد' : 'دفعة', fmtMoney(p.kind === 'refund' ? -p.amount : p.amount), METH[p.method]])),
        headers: ['التاريخ', 'المراجع', 'رقم الملف', 'النوع', 'المبلغ', 'الطريقة', 'ملاحظات'], rows: d.payments.map(p => [p.pay_date, p.full_name, p.file_no, p.kind === 'refund' ? 'مسترد' : 'دفعة', p.kind === 'refund' ? -p.amount : p.amount, METH[p.method], p.notes || '']) };
    } catch (e) { $('#rb').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  }
  $('#rd').onchange = load; load();
}

function periodBody(d, dues) {
  const s = d.stats, days = d.daily;
  const chart = days.length ? barChart({ labels: days.map(x => x.date.slice(8)), series: [{ name: 'المقبوضات', color: '#0e7c7b', values: days.map(x => x.receipts) }], title: 'المقبوضات اليومية' }) : '';
  const tot = k => days.reduce((a, x) => a + x[k], 0);
  const dayTbl = simpleTable(['التاريخ', 'اليوم', 'المقبوضات', 'عدد الدفعات', 'الزيارات', 'المستردات', 'المصروفات', 'صافي التدفق'], days.map(x => [dateH(x.date), dayName(x.date), moneyH(x.receipts), intH(x.payments_count), intH(x.visits), moneyH(x.refunds), moneyH(x.expenses), moneyH(x.net_cash_flow)]),
    { foot: `<tr class="tot"><td colspan="2">المجموع</td><td>${moneyH(tot('receipts'))}</td><td>${intH(tot('payments_count'))}</td><td>${intH(tot('visits'))}</td><td>${moneyH(tot('refunds'))}</td><td>${moneyH(tot('expenses'))}</td><td>${moneyH(tot('net_cash_flow'))}</td></tr>` });
  const procTbl = simpleTable(['الإجراء', 'العدد', 'المنفذ (مكتمل)', 'المتفق عليه (مسجل)'], d.by_procedure.map(p => [esc(p.name), intH(p.n), moneyH(p.executed), moneyH(p.agreed)]));
  const catTbl = s.expenses_by_category.length ? simpleTable(['تصنيف المصروف', 'العدد', 'المبلغ'], s.expenses_by_category.map(c => [esc(c.category), intH(c.n), moneyH(c.total)])) : '';
  return { html: `${statGrid([{ label: 'إجمالي المبالغ المستحقة على المراجعين (حالياً)', value: moneyH(dues), cls: 'due' }])}${statsHTML(s)}${doctorCard(d.by_doctor)}${chart ? `<section class="card"><h3>تغيّر المقبوضات خلال الفترة</h3>${chart}</section>` : ''}
    <section class="card"><h3>الجدول اليومي</h3>${dayTbl}</section><section class="card"><h3>تفصيل الإيرادات حسب نوع الإجراء</h3>${procTbl}</section>${catTbl ? `<section class="card"><h3>المصروفات حسب التصنيف</h3>${catTbl}</section>` : ''}`,
    print: statsPrint(s) + `<p>المبالغ المستحقة على المراجعين (حالياً): <b>${fmtMoney(dues)}</b></p>` + doctorPrint(d.by_doctor) + chart + '<h3>الجدول اليومي</h3>' + dayTbl + '<h3>حسب نوع الإجراء</h3>' + procTbl + (catTbl ? '<h3>المصروفات حسب التصنيف</h3>' + catTbl : ''),
    headers: ['التاريخ', 'المقبوضات', 'عدد الدفعات', 'الزيارات', 'المستردات', 'المصروفات', 'صافي التدفق'], rows: days.map(x => [x.date, x.receipts, x.payments_count, x.visits, x.refunds, x.expenses, x.net_cash_flow]) };
}
async function loadPeriod(box, from, to, title) {
  try {
    const [d, db] = await Promise.all([api('GET', '/api/reports/period?' + qs({ from, to })), api('GET', '/api/reports/debtors')]);
    const b = periodBody(d, db.total_dues);
    box.innerHTML = exportBar() + b.html;
    RPT = { title, sub: `الفترة: من <bdi>${from}</bdi> إلى <bdi>${to}</bdi>`, html: b.print, headers: b.headers, rows: b.rows };
  } catch (e) { box.innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
}
let REP_MONTH = today().slice(0, 7);
async function repMonthly(host) {
  host.innerHTML = `<div class="toolbar no-print"><button type="button" class="btn sm" data-action="mon-nav" data-n="-1">‹ الشهر السابق</button><input type="month" id="rm" value="${REP_MONTH}"><button type="button" class="btn sm" data-action="mon-nav" data-n="1">الشهر التالي ›</button></div><div id="rb"></div>`;
  const load = () => { REP_MONTH = $('#rm').value || today().slice(0, 7); const [a, b] = monthRange(REP_MONTH); loadPeriod($('#rb'), a, b, 'التقرير المالي الشهري — ' + MONTHS_AR[+REP_MONTH.slice(5) - 1] + ' ' + REP_MONTH.slice(0, 4)); };
  $('#rm').onchange = load; load();
}
ACTIONS['mon-nav'] = b => { const [y, m] = $('#rm').value.split('-').map(Number), d = new Date(y, m - 1 + +b.dataset.n, 1); $('#rm').value = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`; $('#rm').dispatchEvent(new Event('change')); };
async function repPeriod(host) {
  host.innerHTML = `<div class="toolbar no-print"><label>من <input type="date" id="pf" value="${today().slice(0, 8)}01"></label><label>إلى <input type="date" id="pt" value="${today()}"></label></div><div id="rb"></div>`;
  const load = () => { if ($('#pf').value && $('#pt').value) loadPeriod($('#rb'), $('#pf').value, $('#pt').value, 'تقرير مالي لفترة محددة'); };
  $('#pf').onchange = load; $('#pt').onchange = load; load();
}

async function repYearly(host) {
  const y0 = new Date().getFullYear();
  const yopt = (sel, none) => (none ? '<option value="">— بدون مقارنة —</option>' : '') + Array.from({ length: 12 }, (_, i) => y0 + 1 - i).map(y => `<option value="${y}" ${y == sel ? 'selected' : ''}>${y}</option>`).join('');
  host.innerHTML = `<div class="toolbar no-print"><label>السنة <select id="ry">${yopt(y0)}</select></label><label>مقارنة مع سنة <select id="rc">${yopt(y0 - 1, true)}</select></label></div><div id="rb"></div>`;
  async function load() {
    const y = $('#ry').value, c = $('#rc').value;
    try {
      const [d, db] = await Promise.all([api('GET', '/api/reports/yearly?' + qs({ year: y, compare: c })), api('GET', '/api/reports/debtors')]);
      const cm = d.compare, M = i => MONTHS_AR[i];
      const head = ['الشهر', 'إجمالي المقبوضات', 'قيمة العلاجات المنفذة', 'عدد الزيارات', 'مراجعون جدد', 'الخصومات والمستردات', 'المصروفات', 'صافي التدفق'].concat(cm ? [`مقبوضات ${c}`, `منفذ ${c}`] : []);
      const rows = d.months.map((m, i) => [M(i), moneyH(m.receipts), moneyH(m.executed_value), intH(m.visits_count), intH(m.new_patients), moneyH(m.discounts + m.refunds), moneyH(m.expenses), moneyH(m.net_cash_flow)].concat(cm ? [moneyH(cm.months[i].receipts), moneyH(cm.months[i].executed_value)] : []));
      const sum = k => d.months.reduce((a, m) => a + m[k], 0), csum = k => cm ? cm.months.reduce((a, m) => a + m[k], 0) : 0;
      const foot = `<tr class="tot"><td>المجموع</td><td>${moneyH(sum('receipts'))}</td><td>${moneyH(sum('executed_value'))}</td><td>${intH(sum('visits_count'))}</td><td>${intH(sum('new_patients'))}</td><td>${moneyH(sum('discounts') + sum('refunds'))}</td><td>${moneyH(sum('expenses'))}</td><td>${moneyH(sum('net_cash_flow'))}</td>${cm ? `<td>${moneyH(csum('receipts'))}</td><td>${moneyH(csum('executed_value'))}</td>` : ''}</tr>`;
      const tbl = simpleTable(head, rows, { foot });
      const series = [{ name: 'مقبوضات ' + y, color: '#0e7c7b', values: d.months.map(m => m.receipts) }].concat(cm ? [{ name: 'مقبوضات ' + c, color: '#c9a227', values: cm.months.map(m => m.receipts) }] : []);
      const chart = barChart({ labels: MONTHS_AR.map(m => m.split(' ')[0]), series, title: 'المقارنة الشهرية' });
      $('#rb').innerHTML = exportBar() + statGrid([{ label: 'إجمالي المبالغ المستحقة على المراجعين (حالياً)', value: moneyH(db.total_dues), cls: 'due' }]) + statsHTML(d.stats) + doctorCard(d.by_doctor) + `<section class="card"><h3>المقارنة بين الأشهر</h3>${chart}</section><section class="card"><h3>الجدول الشهري</h3>${tbl}</section><section class="card"><h3>الإيرادات حسب نوع الإجراء</h3>${simpleTable(['الإجراء', 'العدد', 'المنفذ', 'المتفق عليه'], d.by_procedure.map(p => [esc(p.name), intH(p.n), moneyH(p.executed), moneyH(p.agreed)]))}</section>`;
      RPT = { title: 'التقرير المالي السنوي ' + y, sub: cm ? 'مقارنة مع سنة ' + c : '', html: statsPrint(d.stats) + doctorPrint(d.by_doctor) + chart + '<h3>الجدول الشهري</h3>' + tbl,
        headers: head.map(h => h), rows: d.months.map((m, i) => [M(i), m.receipts, m.executed_value, m.visits_count, m.new_patients, m.discounts + m.refunds, m.expenses, m.net_cash_flow].concat(cm ? [cm.months[i].receipts, cm.months[i].executed_value] : [])) };
    } catch (e) { $('#rb').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  }
  $('#ry').onchange = load; $('#rc').onchange = load; load();
}

async function repDues(host) {
  host.innerHTML = `<div class="toolbar no-print"><label>من <input type="date" id="pf" value="${today().slice(0, 8)}01"></label><label>إلى <input type="date" id="pt" value="${today()}"></label></div><div id="rb"></div>`;
  async function load() {
    try {
      const d = await api('GET', '/api/reports/dues?' + qs({ from: $('#pf').value, to: $('#pt').value })), s = d.stats;
      const head = ['الملف', 'المراجع', 'تكلفة العلاج في الفترة', 'المقبوض في الفترة', 'المتبقي حالياً'];
      const tbl = simpleTable(head, d.rows.map(r => [`<bdi>${r.file_no}</bdi>`, `<a class="pname" href="#/patient/${r.id}">${esc(r.full_name)}</a>`, moneyH(r.cost_in_period), moneyH(r.paid_in_period), remBadge(r.remaining)]));
      $('#rb').innerHTML = exportBar() + statGrid([{ label: 'المقبوضات الفعلية في الفترة', value: moneyH(s.receipts), cls: 'good' }, { label: 'قيمة العلاجات المتفق عليها في الفترة', value: moneyH(s.agreed_value) }, { label: 'إجمالي المستحق على المراجعين (حالياً)', value: moneyH(d.total_outstanding_now), cls: 'due' }]) + `<section class="card"><h3>المراجعون في الفترة: التكلفة مقابل المقبوض والمتبقي</h3>${tbl}</section>`;
      RPT = { title: 'تقرير الإيرادات والمبالغ المستحقة', sub: `الفترة: من <bdi>${$('#pf').value}</bdi> إلى <bdi>${$('#pt').value}</bdi>`, html: `<p>المقبوضات في الفترة: <b>${fmtMoney(s.receipts)}</b> — قيمة العلاجات المتفق عليها: <b>${fmtMoney(s.agreed_value)}</b> — المستحق حالياً: <b>${fmtMoney(d.total_outstanding_now)}</b></p>` + simpleTable(head, d.rows.map(r => [r.file_no, esc(r.full_name), fmtMoney(r.cost_in_period), fmtMoney(r.paid_in_period), fmtMoney(r.remaining)])),
        headers: head, rows: d.rows.map(r => [r.file_no, r.full_name, r.cost_in_period, r.paid_in_period, r.remaining]) };
    } catch (e) { $('#rb').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  }
  $('#pf').onchange = load; $('#pt').onchange = load; load();
}

async function repDebtors(host) {
  host.innerHTML = '<div id="rb"></div>';
  try {
    const d = await api('GET', '/api/reports/debtors');
    const cols = [{ title: 'الملف', key: 'file_no', render: r => `<bdi>${r.file_no}</bdi>` }, { title: 'المراجع', key: 'full_name', render: r => `<a class="pname" href="#/patient/${r.id}">${esc(r.full_name)}</a>` }, { title: 'الهاتف', key: 'phone', render: r => `<bdi>${esc(r.phone || '')}</bdi>` },
      { title: 'إجمالي التكلفة', key: 'total_cost', render: r => moneyH(r.total_cost) }, { title: 'المدفوع', val: r => r.paid - r.refunded, render: r => moneyH(r.paid - r.refunded) }, { title: 'المتبقي', key: 'remaining', render: r => `<b class="due-t">${moneyH(r.remaining)}</b>` },
      { title: 'آخر دفعة', key: 'last_payment', render: r => dateH(r.last_payment) }, { title: 'آخر زيارة', key: 'last_visit', render: r => dateH(r.last_visit) }];
    $('#rb').innerHTML = exportBar() + statGrid([{ label: 'إجمالي المبالغ المستحقة', value: moneyH(d.total_dues), cls: 'due', note: `${intH(d.debtors.length)} مراجع` }]) + '<section class="card"><div id="dtb"></div></section>' + (d.credits.length ? `<section class="card"><h3>أرصدة دائنة للمراجعين (دفعوا أكثر من المستحق)</h3>${simpleTable(['الملف', 'المراجع', 'الرصيد الدائن'], d.credits.map(r => [`<bdi>${r.file_no}</bdi>`, `<a class="pname" href="#/patient/${r.id}">${esc(r.full_name)}</a>`, moneyH(-r.remaining)]))}</section>` : '');
    const dt = dataTable($('#dtb'), { cols, rows: d.debtors, href: r => '#/patient/' + r.id, empty: 'لا يوجد مراجعون عليهم مبالغ متبقية.', footer: () => `<tr class="tot"><td colspan="5">المجموع</td><td>${moneyH(d.total_dues)}</td><td colspan="2"></td></tr>` });
    RPT = { title: 'المراجعون المدينون', html: simpleTable(['الملف', 'المراجع', 'الهاتف', 'التكلفة', 'المدفوع', 'المتبقي', 'آخر دفعة'], d.debtors.map(r => [r.file_no, esc(r.full_name), `<bdi>${esc(r.phone || '')}</bdi>`, fmtMoney(r.total_cost), fmtMoney(r.paid - r.refunded), fmtMoney(r.remaining), r.last_payment || ''])) + `<p>الإجمالي: <b>${fmtMoney(d.total_dues)}</b></p>`, headers: dt.headers(), rows: dt.matrix() };
  } catch (e) { $('#rb').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
}

/* ====== المصروفات ====== */
let EXP_MONTH = today().slice(0, 7);
async function pageExpenses(main) {
  main.innerHTML = `<div class="page-head"><h1>المصروفات</h1><div class="actions"><button type="button" class="btn primary" data-action="new-exp">${icon('plus')} تسجيل مصروف</button></div></div>
  <div class="toolbar"><input type="month" id="em" value="${EXP_MONTH}"><select id="ec"><option value="">كل التصنيفات</option>${S.cats.map(c => `<option>${esc(c)}</option>`).join('')}</select></div><div id="eb"></div>`;
  async function load() {
    EXP_MONTH = $('#em').value || today().slice(0, 7); const [a, b] = monthRange(EXP_MONTH);
    try {
      const [d, p] = await Promise.all([api('GET', '/api/expenses?' + qs({ from: a, to: b, category: $('#ec').value })), api('GET', '/api/reports/period?' + qs({ from: a, to: b }))]);
      const s = p.stats; window._exps = d.expenses;
      $('#eb').innerHTML = exportBar() + statGrid([{ label: 'مقبوضات الشهر الفعلية', value: moneyH(s.receipts), cls: 'good' }, { label: 'مصروفات الشهر', value: moneyH(s.expenses), cls: 'due' }, { label: 'صافي التدفق النقدي', value: moneyH(s.net_cash_flow), cls: s.net_cash_flow < 0 ? 'bad' : 'good', note: 'المقبوضات − المصروفات − المستردات' }]) + '<section class="card"><div id="etb"></div></section>' +
        (s.expenses_by_category.length ? `<section class="card"><h3>حسب التصنيف</h3>${simpleTable(['التصنيف', 'العدد', 'المبلغ'], s.expenses_by_category.map(c => [esc(c.category), intH(c.n), moneyH(c.total)]))}</section>` : '');
      const dt = dataTable($('#etb'), { rows: d.expenses, empty: 'لا توجد مصروفات في هذا الشهر.', cols: [
        { title: 'التاريخ', key: 'exp_date', render: r => dateH(r.exp_date) }, { title: 'التصنيف', key: 'category' }, { title: 'الوصف', key: 'description', render: r => esc(r.description || '') },
        { title: 'المبلغ', key: 'amount', render: r => moneyH(r.amount) }, { title: 'الطريقة', val: r => METH[r.method] }, { title: 'ملاحظات', key: 'notes', render: r => esc(r.notes || '') },
        { title: '', sortable: false, render: r => `<div class="row-act"><button type="button" class="btn sm" data-action="edit-exp" data-id="${r.id}">${icon('edit', 14)}</button><button type="button" class="btn sm danger-o" data-action="del-exp" data-id="${r.id}">${icon('trash', 14)}</button></div>`, exp: () => '' }],
        footer: () => `<tr class="tot"><td colspan="3">الإجمالي</td><td colspan="4">${moneyH(d.total)}</td></tr>` });
      RPT = { title: 'المصروفات — ' + EXP_MONTH, html: simpleTable(['التاريخ', 'التصنيف', 'الوصف', 'المبلغ', 'الطريقة'], d.expenses.map(r => [`<bdi>${r.exp_date}</bdi>`, esc(r.category), esc(r.description || ''), fmtMoney(r.amount), METH[r.method]])) + `<p>الإجمالي: <b>${fmtMoney(d.total)}</b> — صافي التدفق النقدي للشهر: <b>${fmtMoney(s.net_cash_flow)}</b></p>`, headers: dt.headers().slice(0, 6), rows: dt.matrix().map(r => r.slice(0, 6)) };
    } catch (e) { $('#eb').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  }
  $('#em').onchange = load; $('#ec').onchange = load; window._expLoad = load; load();
}
const expFields = () => [{ name: 'exp_date', label: 'التاريخ', type: 'date', required: true }, { name: 'category', label: 'التصنيف', type: 'select', options: S.cats.map(c => ({ v: c, t: c })) },
  { name: 'amount', label: 'المبلغ', type: 'money', required: true }, { name: 'method', label: 'طريقة الدفع', type: 'select', options: Object.entries(METH).map(([v, t]) => ({ v, t })) },
  { name: 'description', label: 'الوصف', cls: 'full' }, { name: 'notes', label: 'ملاحظات', type: 'textarea', rows: 2, cls: 'full' }];
ACTIONS['new-exp'] = () => formModal({ title: 'تسجيل مصروف', fields: expFields(), values: { exp_date: today(), method: 'cash' }, onSubmit: async (v, f, m) => { await api('POST', '/api/expenses', v); m.close(); toast('تم تسجيل المصروف'); window._expLoad(); } });
ACTIONS['edit-exp'] = b => { const e = window._exps.find(x => x.id == b.dataset.id); formModal({ title: 'تعديل المصروف', fields: expFields(), values: e, onSubmit: async (v, f, m) => { await api('PUT', '/api/expenses/' + e.id, v); m.close(); toast('تم التعديل'); window._expLoad(); } }); };
ACTIONS['del-exp'] = async b => { if (!await confirmBox('حذف هذا المصروف؟ (يُحفظ أثره في سجل التدقيق)', { danger: true, ok: 'حذف' })) return; try { await api('DELETE', '/api/expenses/' + b.dataset.id, {}); toast('تم الحذف'); window._expLoad(); } catch (e) { toast(e.message, 'err'); } };
