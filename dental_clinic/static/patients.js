'use strict';
/* ====== المراجعون: القائمة وصفحة الملف والدفعات ====== */
let PT = null, PT_TAB = 'treat', PT_SORT_NEW = true;

const ageOf = p => { if (p.birth_date) { const b = parseISO(p.birth_date), n = new Date(); let a = n.getFullYear() - b.getFullYear(); if (n < new Date(n.getFullYear(), b.getMonth(), b.getDate())) a--; return a; } return p.age ?? ''; };
const genderAr = g => g === 'M' ? 'ذكر' : g === 'F' ? 'أنثى' : '';
async function withForce(fn) {
  try { return await fn(false); }
  catch (e) { if (e.code === 'overpaid' && await confirmBox(e.message, { ok: 'متابعة رغم ذلك', title: 'تنبيه' })) return await fn(true); throw e; }
}
function remBadge(r) {
  if (r > 0) return `<span class="rem due">مستحق ${moneyH(r)}</span>`;
  if (r < 0) return `<span class="rem credit">رصيد دائن ${moneyH(-r)}</span>`;
  return '<span class="rem paid">مسدّد</span>';
}

/* ---- قائمة المراجعين والبحث ---- */
async function pagePatients(main) {
  main.innerHTML = `<div class="page-head"><h1>المراجعون</h1><div class="actions"><button type="button" class="btn primary" data-action="new-patient">${icon('plus')} إضافة مراجع جديد</button></div></div>
  <section class="card"><div class="searchbar">${icon('search', 20)}<input id="pq" type="search" placeholder="ابحث بالاسم (كاملاً أو جزءاً منه)، أو رقم الهاتف، أو رقم الملف" autocomplete="off"></div><p id="pcount" class="muted small mt"></p><div id="plist"></div></section>`;
  const input = $('#pq'); let t, seq = 0;
  async function load() {
    const my = ++seq;
    try {
      const d = await api('GET', '/api/patients?' + qs({ q: input.value, limit: 100000 }));   // كل المراجعين
      if (my !== seq) return;
      const cols = [
        { title: 'رقم الملف', key: 'file_no', cls: 'num', render: r => `<bdi class="num">${r.file_no}</bdi>` },
        { title: 'الاسم', key: 'full_name', render: r => `<a class="pname" href="#/patient/${r.id}">${esc(r.full_name)}</a>` },
        { title: 'الهاتف', key: 'phone', render: r => `<bdi>${esc(r.phone || '')}</bdi>` },
        { title: 'العمر', val: r => ageOf(r), render: r => `<bdi>${ageOf(r)}</bdi>` },
        { title: 'الطبيب', key: 'doctor', render: r => esc(r.doctor || '') },
        { title: 'أول زيارة', key: 'first_visit_date', render: r => dateH(r.first_visit_date) },
      ];
      if (can('payments')) cols.push({ title: 'الحساب', key: 'remaining', render: r => remBadge(r.remaining), exp: r => r.remaining });
      $('#pcount').textContent = input.value ? `نتائج البحث: ${fmt(d.patients.length)} مراجع` : `عدد المراجعين: ${fmt(d.patients.length)}`;
      if (input.value.trim() && !d.patients.length) { $('#plist').innerHTML = `<div class="reslist"><div class="muted small pad">لا يوجد مراجع بهذا الاسم أو الرقم</div>${addNewItem(input.value.trim())}</div>`; return; }
      dataTable($('#plist'), { cols, rows: d.patients, href: r => '#/patient/' + r.id, search: false, empty: 'لا يوجد مراجعون بعد. أضف أول مراجع من الزر أعلاه.' });
    } catch (e) { $('#plist').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  }
  input.addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 200); });
  input.addEventListener('keydown', e => { if (e.key === 'Enter') { const a = $('#plist tbody tr[data-href]'); if (a) location.hash = a.dataset.href; } });
  await load(); input.focus();
}

const patientFields = cur => [
  { name: 'full_name', label: 'الاسم الكامل', required: true, cls: 'full' },
  doctorList().length || cur
    ? { name: 'doctor', label: 'الطبيب المعالج', type: 'select', options: doctorOptions(cur) }
    : { name: 'doctor', label: 'الطبيب المعالج', hint: 'أضف أسماء الأطباء من الإعدادات لتظهر كقائمة اختيار' },
  { name: 'phone', label: 'رقم الهاتف', type: 'tel' },
  { name: 'gender', label: 'الجنس', type: 'select', options: [{ v: '', t: '—' }, { v: 'M', t: 'ذكر' }, { v: 'F', t: 'أنثى' }] },
  { name: 'birth_date', label: 'تاريخ الميلاد', type: 'date' },
  { name: 'age', label: 'العمر (إن لم يتوفر تاريخ الميلاد)', type: 'text' },
  { name: 'first_visit_date', label: 'تاريخ أول زيارة', type: 'date' },
  { name: 'notes', label: 'ملاحظات عامة (حساسية، أمراض مزمنة…)', type: 'textarea', cls: 'full' },
];
/* إنشاء مراجع جديد؛ إن جاء من بحث بلا نتائج يُكتب نص البحث في الاسم الكامل (أو الهاتف إن كان رقماً) */
const newPatientValues = q => { q = (q || '').trim(); const digits = toLatin(q).replace(/[\s\-+]/g, ''); return /^\d{6,}$/.test(digits) ? { phone: q } : { full_name: q }; };
const addNewItem = q => `<a class="add-new" role="button" tabindex="0" data-action="new-patient" data-q="${esc(q)}" data-pick><span class="add-ic">${icon('plus', 16)}</span><span>إضافة «<b>${esc(q)}</b>» كمراجع جديد</span></a>`;
ACTIONS['new-patient'] = b => {
  const m = formModal({
    title: 'إضافة مراجع جديد', fields: patientFields(), values: { first_visit_date: today(), ...newPatientValues(b && b.dataset && b.dataset.q) }, submit: 'حفظ وفتح الملف',
    onSubmit: async (v, force, m) => { const r = await api('POST', '/api/patients', { ...v, force }); m.close(); toast('تم إنشاء ملف رقم ' + r.patient.file_no); location.hash = '#/patient/' + r.patient.id; },
  });
  watchExisting(m);
};
/* أثناء كتابة اسم أو هاتف المراجع الجديد: إن وُجد سجل مشابه يظهر تحت الحقل مع «فتح السجل» بدل إنشاء ملف مكرر */
function watchExisting(m) {
  const name = $('[name=full_name]', m.el), phone = $('[name=phone]', m.el);
  name.closest('.fld').insertAdjacentHTML('beforeend', '<div class="exist" hidden></div>');
  const box = $('.exist', m.el);
  let t, seq = 0;
  const check = () => { clearTimeout(t); t = setTimeout(async () => {
    const q = name.value.trim().length >= 3 ? name.value.trim() : '', ph = toLatin(phone.value).replace(/\D/g, '');
    const my = ++seq;
    const found = new Map();
    try {
      for (const term of [q, ph.length >= 6 ? ph : ''].filter(Boolean))
        (await api('GET', '/api/patients?' + qs({ q: term, limit: 5 }))).patients.forEach(p => found.set(p.id, p));
    } catch (e) { return; }
    if (my !== seq) return;
    const list = [...found.values()].slice(0, 5);
    box.hidden = !list.length;
    box.innerHTML = list.length ? `<span class="muted small">يوجد سجل مشابه — افتحه بدل إنشاء ملف مكرر:</span>` + list.map(p => `<a href="#/patient/${p.id}" class="exist-it" data-close><b>${esc(p.full_name)}</b><span class="muted"> ملف <bdi>${p.file_no}</bdi>${p.phone ? ' · <bdi>' + esc(p.phone) + '</bdi>' : ''}</span><span class="open">فتح السجل ‹</span></a>`).join('') : '';
  }, 250); };
  name.addEventListener('input', check); phone.addEventListener('input', check); check();
}
ACTIONS['edit-patient'] = () => formModal({
  title: 'تعديل بيانات المراجع', fields: patientFields(PT.patient.doctor), values: PT.patient, submit: 'حفظ التعديلات',
  onSubmit: async (v, force, m) => { await api('PUT', '/api/patients/' + PT.patient.id, { ...v, force }); m.close(); toast('تم حفظ التعديلات'); reloadPatient(); },
});
ACTIONS['del-patient'] = async () => {
  const p = PT.patient;
  let i; try { i = await api('GET', `/api/patients/${p.id}/delete_info`); } catch (e) { toast(e.message, 'err'); return; }
  const msg = `سيُحذف المراجع «${p.full_name}» مع سجله كاملاً: ${fmt(i.visits)} زيارة، ${fmt(i.payments)} دفعة (مجموع المدفوع ${fmtMoney(i.paid)})، و${fmt(i.appointments)} موعد.`
    + (i.remaining ? ` المتبقي عليه ${fmtMoney(i.remaining)} سيُحذف أيضاً.` : '')
    + ' سيختفي من كل التقارير المالية، بما فيها تقارير الأيام والأشهر السابقة. هل أنت متأكد؟';
  if (!await confirmBox(msg, { danger: true, ok: 'حذف المراجع وسجله', title: 'حذف ملف المراجع' })) return;
  try { await api('DELETE', '/api/patients/' + p.id, {}); toast('تم حذف المراجع وسجله المالي'); location.hash = '#/patients'; } catch (e) { toast(e.message, 'err'); }
};

/* ---- صفحة ملف المراجع ---- */
async function pagePatient(main, id, tab) {
  PT_TAB = tab || PT_TAB || 'treat';
  const d = await api('GET', '/api/patients/' + id);
  PT = d;
  const p = d.patient, s = d.summary, money = !!s;
  const age = ageOf(p);
  main.innerHTML = `
  <section class="card pt-head">
    <div class="pt-id"><span class="fileno">ملف <bdi>${p.file_no}</bdi></span><h1>${esc(p.full_name)}</h1>
      <div class="pt-meta">${p.phone ? `<span>${icon('clock', 15)} <bdi>${esc(p.phone)}</bdi></span>` : ''}${age !== '' ? `<span>العمر: <bdi>${age}</bdi></span>` : ''}${p.gender ? `<span>${genderAr(p.gender)}</span>` : ''}${p.doctor ? `<span>الطبيب: <b>${esc(p.doctor)}</b></span>` : ''}<span>أول زيارة: ${dateH(p.first_visit_date)}</span></div>
      ${p.notes ? `<p class="pt-notes">${nl2br(p.notes)}</p>` : ''}</div>
    <div class="pt-actions">
      <button type="button" class="btn primary lg main-act" data-action="new-visit">${icon('plus', 20)} زيارة جديدة</button>
      ${money ? `<button type="button" class="btn lg" data-action="receipts">${icon('print', 18)} طباعة وصل</button><button type="button" class="btn lg" data-action="new-payment">${icon('wallet', 18)} تسجيل دفعة جديدة</button>` : ''}
      ${can('visits') ? `<button type="button" class="btn lg" data-action="xray-capture">${icon('tooth', 18)} استقبال أشعة</button>` : ''}
      <div class="more">
        <button type="button" class="btn sm" data-action="edit-patient">${icon('edit', 15)} تعديل البيانات</button>
        <button type="button" class="btn sm" data-action="print-file">${icon('print', 15)} طباعة الملف</button>
        ${careItems().length ? `<button type="button" class="btn sm" data-action="care-sheet">${icon('print', 15)} تعليمات القلع / الزراعة</button>` : ''}
        ${can('delete') ? `<button type="button" class="btn sm" data-action="merge-patient">${icon('users', 15)} دمج مع ملف مكرر</button><button type="button" class="btn sm danger-o" data-action="del-patient">${icon('trash', 15)} حذف الملف</button>` : ''}
      </div></div>
  </section>
  ${money ? summaryStrip(s) : ''}
  <nav class="tabs" role="tablist">
    <button type="button" data-action="pt-tab" data-tab="treat" class="${PT_TAB === 'treat' ? 'on' : ''}">السجل العلاجي <span class="cnt">${d.visits.length}</span></button>
    ${money ? `<button type="button" data-action="pt-tab" data-tab="fin" class="${PT_TAB === 'fin' ? 'on' : ''}">السجل المالي <span class="cnt">${d.payments.length}</span></button>` : ''}
    <button type="button" data-action="pt-tab" data-tab="appt" class="${PT_TAB === 'appt' ? 'on' : ''}">المواعيد <span class="cnt">${d.appointments.length}</span></button>
    <button type="button" data-action="pt-tab" data-tab="xray" class="${PT_TAB === 'xray' ? 'on' : ''}">الأشعة <span class="cnt">${(d.xrays || []).length}</span></button>
  </nav>
  <div id="ptab"></div>`;
  if (PT_TAB === 'fin' && !money) PT_TAB = 'treat';
  drawPatientTab();
}
const reloadPatient = () => pagePatient($('#main'), PT.patient.id, PT_TAB);
ACTIONS['pt-tab'] = b => { PT_TAB = b.dataset.tab; $$('.tabs button').forEach(x => x.classList.toggle('on', x === b)); drawPatientTab(); };

function summaryStrip(s) {
  const st = s.remaining > 0 ? 'due' : s.remaining < 0 ? 'credit' : 'paid';
  return `<section class="strip">
    <div><span>إجمالي تكلفة العلاج</span><b>${moneyH(s.total_cost)}</b>${s.planned_cost ? `<em>+ مخطط له (غير محتسب): ${moneyH(s.planned_cost)}</em>` : ''}</div>
    <div><span>الخصومات</span><b>${moneyH(s.discounts)}</b>${s.debits ? `<em>تعديلات مدينة: ${moneyH(s.debits)}</em>` : ''}</div>
    <div><span>المدفوع</span><b>${moneyH(s.net_paid)}</b>${s.refunded ? `<em>بعد استرداد ${moneyH(s.refunded)}</em>` : ''}</div>
    <div class="rem-cell ${st}"><span>${s.remaining < 0 ? 'رصيد دائن للمراجع' : 'المتبقي بذمة المراجع'}</span><b>${moneyH(Math.abs(s.remaining))}</b></div></section>`;
}

function drawPatientTab() {
  const host = $('#ptab');
  if (PT_TAB === 'treat') drawTreatTab(host);
  else if (PT_TAB === 'fin') drawFinTab(host);
  else if (PT_TAB === 'xray') drawXrayTab(host);
  else drawApptTab(host);
}

/* ---- السجل العلاجي ---- */
function visitCard(v, withActions = true) {
  const cp = v.procedures.find(x => x.status !== 'cancelled' && careKind(x.name));
  const procs = v.procedures.length ? `<div class="tbl-wrap"><table class="tbl compact"><thead><tr><th>السن</th><th>الإجراء</th><th>الحالة</th><th>التكلفة</th></tr></thead><tbody>${v.procedures.map(x => `<tr class="${x.status === 'cancelled' ? 'cancelled' : ''}">
    <td>${x.tooth_no ? teethTags(x.tooth_no) : '<span class="muted">—</span>'}</td>
    <td><b>${esc(x.name)}</b>${x.rc_steps ? `<div class="rc-done">${icon('check', 13)} <bdi dir="ltr">${esc(rcText(x))}</bdi></div>` : ''}${x.rc_measure ? `<div class="small">القياسات: <bdi dir="ltr">${esc(x.rc_measure)}</bdi></div>` : ''}${x.lab ? `<div class="small">المختبر: <b>${esc(x.lab)}</b></div>` : ''}${x.details ? `<div class="muted small">${nl2br(x.details)}</div>` : ''}</td>
    <td>${withActions && can('visits') ? `<select class="st-sel b-${x.status}" data-change="proc-status" data-id="${x.id}">${Object.entries(PROC_ST).map(([k, t]) => `<option value="${k}" ${k === x.status ? 'selected' : ''}>${t}</option>`).join('')}</select>` : badge(PROC_ST, x.status)}</td>
    <td>${can('payments') ? moneyH(x.cost) : ''}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">لا توجد إجراءات مسجلة في هذه الزيارة.</p>';
  return `<article class="visit">
    <header><div class="vh"><b><bdi>${v.visit_date}</bdi></b> <span class="muted">${dayName(v.visit_date)}${v.visit_time ? ' · ' + `<bdi>${v.visit_time}</bdi>` : ''}${v.doctor ? ' · ' + esc(v.doctor) : ''}</span></div>
    ${withActions && can('visits') ? `<div class="vact"><button type="button" class="btn sm" data-action="xray-capture" data-visit="${v.id}" title="استقبال أشعة لهذه الزيارة">${icon('tooth', 15)} أشعة</button>${cp ? `<button type="button" class="btn sm" data-action="care-sheet" data-proc="${cp.id}">${icon('print', 15)} ${careKind(cp.name) === 'implant' ? 'تعليمات الزراعة' : 'تعليمات القلع'}</button>` : ''}<button type="button" class="btn sm" data-action="edit-visit" data-id="${v.id}">${icon('edit', 15)} تعديل</button>${can('delete') ? `<button type="button" class="btn sm danger-o" data-action="del-visit" data-id="${v.id}">${icon('trash', 15)}</button>` : ''}</div>` : ''}</header>
    ${procs}
    ${v.notes ? `<p class="vnotes"><b>ملاحظات سريرية:</b> ${nl2br(v.notes)}</p>` : ''}
    ${withActions ? visitXrays(v.id) : ''}
    ${v.next_appointment ? `<p class="vnext">${icon('calendar', 15)} الموعد القادم: <bdi>${v.next_appointment}</bdi>${v.next_time ? ' <bdi>' + v.next_time + '</bdi>' : ''}</p>` : ''}
    ${can('payments') && v.procedures.length ? `<footer>إجمالي تكلفة الزيارة: ${moneyH(v.visit_total)}</footer>` : ''}</article>`;
}
function sortedVisits() { const a = PT.visits.slice(); a.sort((x, y) => (x.visit_date + (x.visit_time || '') + String(x.id).padStart(8, '0')).localeCompare(y.visit_date + (y.visit_time || '') + String(y.id).padStart(8, '0'))); return PT_SORT_NEW ? a.reverse() : a; }
function drawTreatTab(host) {
  host.innerHTML = `<div class="toolbar"><button type="button" class="btn" data-action="toggle-sort">ترتيب: ${PT_SORT_NEW ? 'الأحدث أولاً' : 'الأقدم أولاً'} ⇅</button><button type="button" class="btn" data-action="print-treat">${icon('print', 16)} طباعة السجل العلاجي</button></div>
  ${PT.visits.length ? sortedVisits().map(v => visitCard(v)).join('') : `<div class="empty-state">${icon('tooth', 34)}<p>لا توجد زيارات مسجلة لهذا المراجع.</p><button type="button" class="btn primary" data-action="new-visit">تسجيل أول زيارة</button></div>`}`;
}
ACTIONS['toggle-sort'] = () => { PT_SORT_NEW = !PT_SORT_NEW; drawPatientTab(); };
CHANGES['proc-status'] = async sel => {
  try {
    await withForce(force => api('PUT', '/api/procedures/' + sel.dataset.id, { status: sel.value, force }));
    toast('تم تحديث حالة الإجراء');
  } catch (e) { toast(e.message, 'err'); }
  reloadPatient();
};
ACTIONS['del-visit'] = async b => {
  if (!await confirmBox('سيتم حذف هذه الزيارة وإجراءاتها من الحساب (يبقى أثرها في سجل التدقيق). الدفعات المسجلة لا تتغير.', { danger: true, ok: 'حذف الزيارة' })) return;
  try { await withForce(force => api('DELETE', '/api/visits/' + b.dataset.id, { force })); toast('تم حذف الزيارة'); reloadPatient(); } catch (e) { toast(e.message, 'err'); }
};

/* ---- السجل المالي ---- */
function costRows() {
  const out = [];
  PT.visits.forEach(v => v.procedures.forEach(x => out.push({ date: v.visit_date, ...x })));
  return out.sort((a, b) => a.date.localeCompare(b.date));
}
function drawFinTab(host) {
  const { payments, adjustments } = PT;
  host.innerHTML = `<div class="toolbar">
    <button type="button" class="btn primary" data-action="new-payment">${icon('wallet', 16)} تسجيل دفعة جديدة</button>
    <button type="button" class="btn" data-action="new-refund">مبلغ مسترد</button>
    <button type="button" class="btn" data-action="new-adj">خصم / تعديل مالي</button>
    <button type="button" class="btn" data-action="print-statement">${icon('print', 16)} طباعة كشف حساب المراجع</button></div>
  <section class="card"><h3>الدفعات</h3><div id="payTbl"></div></section>
  <section class="card"><h3>الخصومات والتعديلات المالية</h3>${simpleTable(['التاريخ', 'النوع', 'المبلغ', 'السبب', ''], adjustments.map(a => [dateH(a.adj_date), a.kind === 'discount' ? 'خصم' : 'تعديل مدين (زيادة)', moneyH(a.amount), esc(a.notes), can('finance_edit') ? `<button type="button" class="btn sm danger-o" data-action="del-adj" data-id="${a.id}">${icon('trash', 14)}</button>` : '']))}</section>
  <section class="card"><h3>تفصيل التكاليف</h3>${simpleTable(['التاريخ', 'السن', 'الإجراء', 'الحالة', 'التكلفة', 'محتسبة؟'], costRows().map(x => [dateH(x.date), x.tooth_no ? teethTags(x.tooth_no) : '—', esc(x.name), badge(PROC_ST, x.status), moneyH(x.cost), x.status === 'planned' ? '<span class="muted">لا (مخطط له)</span>' : x.status === 'cancelled' ? '<span class="muted">لا (ملغى)</span>' : 'نعم']))}</section>`;
  dataTable($('#payTbl', host), {
    search: false, empty: 'لا توجد دفعات مسجلة بعد.',
    cols: [
      { title: 'رقم الإيصال', key: 'id', render: r => `<bdi class="num">${r.id}</bdi>` },
      { title: 'التاريخ', key: 'pay_date', render: r => dateH(r.pay_date) },
      { title: 'النوع', val: r => r.kind === 'refund' ? 'مسترد' : 'دفعة', render: r => r.kind === 'refund' ? '<span class="badge b-cancelled">مبلغ مسترد</span>' : '<span class="badge b-completed">دفعة</span>' },
      { title: 'المبلغ', key: 'amount', render: r => moneyH(r.kind === 'refund' ? -r.amount : r.amount, r.kind === 'refund' ? 'neg' : ''), exp: r => r.kind === 'refund' ? -r.amount : r.amount },
      { title: 'الطريقة', val: r => METH[r.method], },
      { title: 'ملاحظات', key: 'notes', render: r => esc(r.notes || '') },
      { title: '', sortable: false, render: r => `<div class="row-act"><button type="button" class="btn sm" data-action="print-receipt" data-id="${r.id}" title="طباعة إيصال">${icon('print', 14)}</button>${can('finance_edit') ? `<button type="button" class="btn sm" data-action="edit-payment" data-id="${r.id}" title="تعديل">${icon('edit', 14)}</button><button type="button" class="btn sm danger-o" data-action="void-payment" data-id="${r.id}" title="إلغاء">${icon('trash', 14)}</button>` : ''}</div>` },
    ], rows: payments,
  });
}

const METHOD_OPTS = Object.entries(METH).map(([v, t]) => ({ v, t }));
function paymentFields() {
  return [
    { name: 'amount', label: 'المبلغ', type: 'money', required: true },
    { name: 'pay_date', label: 'تاريخ الدفعة', type: 'date', required: true },
    { name: 'method', label: 'طريقة الدفع', type: 'select', options: METHOD_OPTS },
    { name: 'visit_id', label: 'ربط بزيارة (اختياري)', type: 'select', options: [{ v: '', t: '— بدون ربط —' }].concat(PT.visits.map(v => ({ v: v.id, t: v.visit_date + ' — ' + (v.procedures.map(x => x.name).join('، ') || 'زيارة') }))) },
    { name: 'notes', label: 'ملاحظات', type: 'textarea', rows: 2, cls: 'full' },
  ];
}
function openPaymentModal(kind) {
  const s = PT.summary, key = uid(), isRef = kind === 'refund';
  const intro = `<div class="pay-intro full">المتبقي حالياً على المراجع: <b>${moneyH(s.remaining)}</b>${!isRef && s.remaining > 0 ? ` <button type="button" class="link" data-action="fill-remaining" data-v="${s.remaining}">تعبئة المبلغ المتبقي كاملاً</button>` : ''}${isRef ? `<br><small class="muted">أقصى مبلغ يمكن استرداده: ${moneyH(s.net_paid)}</small>` : ''}</div>`;
  formModal({
    title: isRef ? 'تسجيل مبلغ مسترد للمراجع' : 'تسجيل دفعة جديدة', fields: paymentFields(), values: { pay_date: today(), method: 'cash' }, intro, submit: isRef ? 'تسجيل الاسترداد' : 'تسجيل الدفعة',
    onSubmit: async (v, force, m) => {
      const r = await api('POST', '/api/patients/' + PT.patient.id + '/payments', { ...v, kind, idem_key: key, force });
      m.close();
      if (r.duplicate) toast('هذه الدفعة سُجّلت سابقاً ولم تُكرَّر', 'warn'); else toast(isRef ? 'تم تسجيل المبلغ المسترد' : 'تم تسجيل الدفعة');
      await reloadPatient();
    },
  });
  setTimeout(() => { const a = $('.overlay [name=amount]'); if (a) a.focus(); }, 30);
}
ACTIONS['new-payment'] = () => openPaymentModal('payment');
ACTIONS['new-refund'] = () => openPaymentModal('refund');
ACTIONS['fill-remaining'] = b => { const i = $('.overlay [name=amount]'); i.value = moneyIn(+b.dataset.v); i.dispatchEvent(new Event('input')); i.focus(); };
/* دمج ملف مكرر (مثل «زينب وليد» و«زينب وليد مجيد»): بحث عن الملف المكرر ثم نقل كل سجله إلى هذا الملف */
ACTIONS['merge-patient'] = () => {
  const p = PT.patient, money = can('payments');
  const m = modal({ title: 'دمج ملف مكرر مع «' + p.full_name + '»', wide: true,
    body: `<p class="muted small">ابحث عن الملف المكرر لنفس المراجع. عند الدمج تنتقل كل زياراته وإجراءاته ودفعاته وخصوماته ومواعيده إلى هذا الملف، ويُعتمد الاسم الأطول، ثم يُحذف الملف المكرر.</p>
      <div class="searchbar">${icon('search', 20)}<input id="mq" type="search" value="${esc(p.full_name.split(' ').slice(0, 2).join(' '))}" autocomplete="off" placeholder="اسم أو هاتف أو رقم ملف"></div><div id="mres" class="mt"></div>`,
    footer: '<button type="button" class="btn" data-close>إغلاق</button>' });
  const inp = $('#mq', m.el); let t, seq = 0;
  async function load() {
    const my = ++seq;
    try {
      const rows = (await api('GET', '/api/patients?' + qs({ q: inp.value, limit: 30 }))).patients.filter(r => r.id !== p.id);
      if (my !== seq) return;
      $('#mres', m.el).innerHTML = rows.length ? simpleTable(['رقم الملف', 'الاسم', 'الهاتف', 'الطبيب', 'أول زيارة'].concat(money ? ['الحساب'] : []).concat(['']), rows.map(r => [`<bdi class="num">${r.file_no}</bdi>`, esc(r.full_name), `<bdi>${esc(r.phone || '')}</bdi>`, esc(r.doctor || ''), dateH(r.first_visit_date)]
        .concat(money ? [remBadge(r.remaining)] : []).concat([`<button type="button" class="btn sm primary" data-action="merge-do" data-id="${r.id}" data-name="${esc(r.full_name)}" data-file="${r.file_no}">دمج</button>`])))
        : '<p class="muted">لا يوجد ملف مطابق. جرّب جزءاً من الاسم.</p>';
    } catch (e) { $('#mres', m.el).innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  }
  inp.addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 200); });
  load(); inp.select();
};
ACTIONS['merge-do'] = async b => {
  const p = PT.patient, other = b.dataset.name;
  const words = n => normQ(n).split(' ').filter(Boolean);
  const longer = words(other).length > words(p.full_name).length || (words(other).length === words(p.full_name).length && normQ(other).length > normQ(p.full_name).length) ? other : p.full_name;
  if (!await confirmBox(`سيُنقل كل سجل «${other}» (ملف ${b.dataset.file}) إلى ملف «${p.full_name}» (ملف ${p.file_no})، ويصير الاسم «${longer}»، ثم يُحذف الملف المكرر. متابعة؟`, { ok: 'دمج الملفين', title: 'تأكيد الدمج' })) return;
  try {
    const r = await api('POST', `/api/patients/${p.id}/merge`, { other_id: +b.dataset.id }), mv = r.moved;
    b.closest('.overlay').remove();
    toast(`تم الدمج: ${fmt(mv.visits)} زيارة و${fmt(mv.payments)} دفعة انتقلت إلى هذا الملف`);
    reloadPatient();
  } catch (e) { toast(e.message, 'err'); }
};
/* طباعة وصل: قائمة بكل دفعات المراجع، ويختار المستخدم الدفعة التي يريد طباعة وصلها */
ACTIONS['receipts'] = () => {
  const pays = (PT.payments || []).slice().sort((a, b) => b.pay_date.localeCompare(a.pay_date) || b.id - a.id);
  const body = pays.length ? `<p class="muted small">اختر الدفعة التي تريد طباعة وصلها.</p>` + simpleTable(['رقم الوصل', 'التاريخ', 'النوع', 'المبلغ', 'الطريقة', ''],
    pays.map(r => [`<bdi class="num">${r.id}</bdi>`, dateH(r.pay_date), r.kind === 'refund' ? 'مسترد' : 'دفعة', moneyH(r.amount), METH[r.method],
      `<button type="button" class="btn sm primary" data-action="receipt-print" data-id="${r.id}">${icon('print', 14)} طباعة</button>`]))
    : '<p class="muted">لا توجد دفعات مسجلة لهذا المراجع.</p>';
  modal({ title: 'طباعة وصل — ' + PT.patient.full_name, body, wide: true, footer: '<button type="button" class="btn" data-close>إغلاق</button>' });
};
ACTIONS['receipt-print'] = b => { b.closest('.overlay').remove(); printReceipt(b.dataset.id); };
ACTIONS['edit-payment'] = b => {
  const pay = PT.payments.find(x => x.id == b.dataset.id);
  formModal({ title: 'تعديل الدفعة رقم ' + pay.id, fields: [
    { name: 'amount', label: 'المبلغ', type: 'money', required: true }, { name: 'pay_date', label: 'التاريخ', type: 'date', required: true },
    { name: 'method', label: 'الطريقة', type: 'select', options: METHOD_OPTS }, { name: 'notes', label: 'ملاحظات', type: 'textarea', rows: 2, cls: 'full' },
    { name: 'reason', label: 'سبب التعديل (يُحفظ في سجل التدقيق)', cls: 'full' }], values: pay,
  intro: '<div class="alert warn full">تعديل الدفعة يغيّر التقارير الخاصة بتاريخها. يُحفظ المبلغ القديم والجديد في سجل التدقيق.</div>',
  onSubmit: async (v, force, m) => { await api('PUT', '/api/payments/' + pay.id, { ...v, force }); m.close(); toast('تم تعديل الدفعة'); reloadPatient(); } });
};
ACTIONS['void-payment'] = async b => {
  const reason = await promptBox('إلغاء الدفعة', 'سبب الإلغاء (مطلوب)', { ok: 'إلغاء الدفعة' }); if (!reason) return;
  try { await withForce(force => api('DELETE', '/api/payments/' + b.dataset.id, { reason, force })); toast('تم إلغاء الدفعة (السجل محفوظ في التدقيق)'); reloadPatient(); } catch (e) { toast(e.message, 'err'); }
};
ACTIONS['new-adj'] = () => formModal({
  title: 'خصم أو تعديل مالي', fields: [
    { name: 'kind', label: 'النوع', type: 'select', options: [{ v: 'discount', t: 'خصم للمراجع' }, { v: 'debit', t: 'تعديل مدين (زيادة على المراجع)' }] },
    { name: 'amount', label: 'المبلغ', type: 'money', required: true }, { name: 'adj_date', label: 'التاريخ', type: 'date', required: true },
    { name: 'notes', label: 'السبب', required: true, cls: 'full' }], values: { kind: 'discount', adj_date: today() },
  onSubmit: async (v, force, m) => { await api('POST', '/api/patients/' + PT.patient.id + '/adjustments', { ...v, force }); m.close(); toast('تم تسجيل التعديل'); reloadPatient(); },
});
ACTIONS['del-adj'] = async b => {
  if (!await confirmBox('حذف هذا التعديل المالي؟ (يُحفظ أثره في سجل التدقيق)', { danger: true, ok: 'حذف' })) return;
  try { await withForce(force => api('DELETE', '/api/adjustments/' + b.dataset.id, { force })); toast('تم الحذف'); reloadPatient(); } catch (e) { toast(e.message, 'err'); }
};

/* ---- المواعيد داخل الملف ---- */
function drawApptTab(host) {
  host.innerHTML = `<div class="toolbar"><button type="button" class="btn primary" data-action="new-appt-pt">${icon('plus', 16)} موعد جديد</button></div>
  ${simpleTable(['التاريخ', 'اليوم', 'الوقت', 'السبب', 'الحالة'], PT.appointments.map(a => [dateH(a.appt_date), dayName(a.appt_date), `<bdi>${a.appt_time || ''}</bdi>`, esc(a.reason || ''), apptStatusSel(a)]))}`;
}
ACTIONS['new-appt-pt'] = () => apptModal(null, PT.patient);

/* ---- الطباعة ---- */
function patientInfoHTML() {
  const p = PT.patient;
  return `<table class="kv"><tr><th>رقم الملف</th><td><bdi>${p.file_no}</bdi></td><th>الاسم</th><td>${esc(p.full_name)}</td></tr>
  <tr><th>الهاتف</th><td><bdi>${esc(p.phone || '')}</bdi></td><th>العمر / الجنس</th><td>${ageOf(p) !== '' ? '<bdi>' + ageOf(p) + '</bdi>' : ''} ${genderAr(p.gender)}</td></tr>
  ${p.doctor ? `<tr><th>الطبيب المعالج</th><td colspan="3">${esc(p.doctor)}</td></tr>` : ''}
  <tr><th>أول زيارة</th><td><bdi>${p.first_visit_date || ''}</bdi></td><th>ملاحظات</th><td>${nl2br(p.notes || '')}</td></tr></table>`;
}
function treatPrintHTML(withMoney) {
  return sortedVisits().slice().sort((a, b) => a.visit_date.localeCompare(b.visit_date)).map(v => `<div class="pv"><h4>زيارة <bdi>${v.visit_date}</bdi> ${v.visit_time ? '<bdi>' + v.visit_time + '</bdi>' : ''} ${v.doctor ? '— ' + esc(v.doctor) : ''}</h4>
    ${simpleTable(['السن', 'الإجراء', 'الحالة'].concat(withMoney ? ['التكلفة'] : []), v.procedures.map(x => [teethText(x.tooth_no) || '—', esc(x.name) + (x.details ? '<br><small>' + esc(x.details) + '</small>' : ''), PROC_ST[x.status]].concat(withMoney ? [fmtMoney(x.cost)] : [])))}
    ${v.notes ? `<p><b>ملاحظات:</b> ${nl2br(v.notes)}</p>` : ''}${v.next_appointment ? `<p><b>الموعد القادم:</b> <bdi>${v.next_appointment}</bdi></p>` : ''}</div>`).join('') || '<p>لا توجد زيارات.</p>';
}
ACTIONS['print-treat'] = () => printDoc('السجل العلاجي', patientInfoHTML() + treatPrintHTML(can('payments')));
ACTIONS['print-file'] = () => {
  const s = PT.summary;
  printDoc('ملف المراجع', patientInfoHTML() + (s ? `<table class="kv"><tr><th>إجمالي التكلفة</th><td>${fmtMoney(s.total_cost)}</td><th>الخصومات</th><td>${fmtMoney(s.discounts)}</td></tr><tr><th>المدفوع</th><td>${fmtMoney(s.net_paid)}</td><th>المتبقي</th><td><b>${fmtMoney(s.remaining)}</b></td></tr></table>` : '') + '<h3>السجل العلاجي</h3>' + treatPrintHTML(!!s));
};
ACTIONS['print-statement'] = () => {
  const { summary: s, payments, adjustments } = PT;
  const rows = costRows().filter(x => x.status !== 'cancelled');
  const html = patientInfoHTML() + '<h3>التكاليف</h3>' + simpleTable(['التاريخ', 'السن', 'الإجراء', 'الحالة', 'التكلفة', 'محتسبة'], rows.map(x => [`<bdi>${x.date}</bdi>`, teethText(x.tooth_no) || '—', esc(x.name), PROC_ST[x.status], fmtMoney(x.cost), x.status === 'planned' ? 'لا (مخطط)' : 'نعم']))
    + '<h3>الخصومات والتعديلات</h3>' + simpleTable(['التاريخ', 'النوع', 'المبلغ', 'السبب'], adjustments.map(a => [`<bdi>${a.adj_date}</bdi>`, a.kind === 'discount' ? 'خصم' : 'تعديل مدين', fmtMoney(a.amount), esc(a.notes)]))
    + '<h3>الدفعات</h3>' + simpleTable(['إيصال', 'التاريخ', 'النوع', 'المبلغ', 'الطريقة', 'ملاحظات'], payments.slice().reverse().map(r => [`<bdi>${r.id}</bdi>`, `<bdi>${r.pay_date}</bdi>`, r.kind === 'refund' ? 'مسترد' : 'دفعة', fmtMoney(r.kind === 'refund' ? -r.amount : r.amount), METH[r.method], esc(r.notes || '')]))
    + `<table class="kv total"><tr><th>إجمالي التكاليف المحتسبة</th><td>${fmtMoney(s.total_cost)}</td></tr><tr><th>الخصومات</th><td>${fmtMoney(-s.discounts)}</td></tr>${s.debits ? `<tr><th>التعديلات المدينة</th><td>${fmtMoney(s.debits)}</td></tr>` : ''}<tr><th>إجمالي المدفوع (بعد المسترد)</th><td>${fmtMoney(s.net_paid)}</td></tr><tr class="grand"><th>${s.remaining < 0 ? 'رصيد دائن للمراجع' : 'المبلغ المتبقي'}</th><td>${fmtMoney(Math.abs(s.remaining))}</td></tr></table>`;
  printDoc('كشف حساب المراجع', html);
};
function printReceipt(id) {
  const pay = PT.payments.find(x => x.id == id) || null; if (!pay) return;
  const p = PT.patient, s = PT.summary, ref = pay.kind === 'refund';
  printDoc(ref ? 'إيصال صرف (مبلغ مسترد)' : 'إيصال قبض', `<div class="receipt"><table class="kv"><tr><th>رقم الإيصال</th><td><bdi>${pay.id}</bdi></td><th>التاريخ</th><td><bdi>${pay.pay_date}</bdi></td></tr>
    <tr><th>${ref ? 'صُرف للمراجع' : 'استُلم من'}</th><td>${esc(p.full_name)}</td><th>رقم الملف</th><td><bdi>${p.file_no}</bdi></td></tr>
    <tr><th>المبلغ</th><td class="big">${fmtMoney(pay.amount)}</td><th>طريقة الدفع</th><td>${METH[pay.method]}</td></tr>
    ${pay.notes ? `<tr><th>ملاحظات</th><td colspan="3">${esc(pay.notes)}</td></tr>` : ''}
    <tr><th>المتبقي بذمة المراجع (حالياً)</th><td colspan="3">${fmtMoney(Math.max(s.remaining, 0))}</td></tr></table>
    <div class="sign"><span>توقيع المستلم: ____________</span><span>توقيع المراجع: ____________</span></div></div>`);
}
ACTIONS['print-receipt'] = b => printReceipt(b.dataset.id);


/* ====== تعليمات ما بعد القلع / الزراعة ====== */
function careKind(name) {
  const t = normQ(name || '');
  if (/زراع|implant/.test(t)) return 'implant';
  if (/قلع|خلع|exo|extract/.test(t)) return 'extract';
  return null;
}
function careItems() {
  if (!PT) return [];
  const out = [];
  PT.visits.forEach(v => v.procedures.forEach(x => {
    const k = careKind(x.name);
    if (k && x.status !== 'cancelled') out.push({ id: x.id, kind: k, date: v.visit_date, name: x.name, tooth: x.tooth_no, doctor: x.doctor || v.doctor || '' });
  }));
  return out.sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
}
const CARE = {
  extract: {
    title: 'تعليمات ما بعد القلع',
    sections: [
      ['أول 24 ساعة', [
        'عضّ على الشاش 30 دقيقة.',
        'لا مضمضة ولا بصق ولا قشة ولا تدخين.',
        'الأكل سوائل باردة فقط، على الجهة المقابلة للقلع.',
        'كمادات باردة على الخد من الخارج.',
        'لا تلمس مكان القلع، وتجنّب المجهود.']],
      ['بعد 24 ساعة', [
        'مضمضة بماء دافئ مع قليل من الملح كل ساعتين.',
        'أكل لين وامضغ من الجهة الثانية.',
        'الأدوية حسب وصف الطبيب فقط.']],
    ],
    warn: ['نزف لا يتوقف بعد ساعة.', 'ألم أو تورم يزداد بعد 3 أيام، أو حرارة.']
  },
  implant: {
    title: 'تعليمات ما بعد الزراعة',
    sections: [
      ['أول 24 ساعة', [
        'عضّ على الشاش 30 دقيقة.',
        'لا مضمضة ولا بصق ولا قشة ولا تدخين.',
        'الأكل سوائل باردة فقط، على الجهة المقابلة للزراعة.',
        'كمادات باردة على الخد من الخارج.',
        'لا تلمس المكان بلسانك أو أصابعك.']],
      ['بعد 24 ساعة', [
        'مضمضة بماء دافئ مع قليل من الملح كل ساعتين.',
        'أكل لين لعدة أيام، وتجنّب القاسي والمقرمش.',
        'التدخين يضعف نجاح الزراعة، فتجنّبه.',
        'الأدوية والمواعيد حسب الطبيب.']],
    ],
    warn: ['نزف لا يتوقف بعد ساعة.', 'ألم أو تورم يزداد بعد 3 أيام، أو حرارة.', 'إحساس بحركة في الغرسة.']
  },
};
function printCare(item, kind, extra) {
  const c = CARE[kind], p = PT.patient;
  const html = `<table class="kv"><tr><th>المراجع</th><td>${esc(p.full_name)}</td><th>رقم الملف</th><td><bdi>${p.file_no}</bdi></td></tr>
    <tr><th>السن</th><td>${item.tooth ? `<bdi>${esc(teethText(item.tooth))}</bdi>` : '—'}</td><th>التاريخ</th><td><bdi>${esc(item.date)}</bdi></td></tr></table>
    <div class="care">${c.sections.map(([h, li]) => `<h3>${esc(h)}</h3><ul>${li.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`).join('')}
    ${extra ? `<div class="care-extra"><b>ملاحظات الطبيب:</b> ${nl2br(extra)}</div>` : ''}
    <div class="care-warn"><b>راجع العيادة فوراً إذا:</b><ul>${c.warn.map(x => `<li>${esc(x)}</li>`).join('')}</ul>${S.settings.clinic_phone ? `<div>هاتف العيادة: <bdi dir="ltr"><b>${esc(S.settings.clinic_phone)}</b></bdi></div>` : ''}</div></div>`;
  printDoc(c.title, html, '', 'A5');
}
function openCareSheet(item) {
  const items = careItems();
  if (!items.length) { toast('لا يوجد إجراء قلع أو زراعة لهذا المراجع', 'err'); return; }
  item = item || items[0];
  const m = modal({ title: 'طباعة تعليمات القلع / الزراعة', cls: 'small', body: `<form class="form-grid c1" novalidate>
    <label class="fld"><span>الإجراء</span><select name="i">${items.map((x, i) => `<option value="${i}" ${x.id === item.id ? 'selected' : ''}>${esc(x.date)} — ${esc(x.name)}${x.tooth ? ' (سن ' + esc(teethText(x.tooth)) + ')' : ''}</option>`).join('')}</select></label>
    <label class="fld"><span>نوع التعليمات</span><select name="k"><option value="extract">بعد القلع</option><option value="implant">بعد الزراعة</option></select></label>
    <label class="fld"><span>ملاحظات إضافية من الطبيب (اختياري)</span><textarea name="x" rows="3"></textarea></label></form>`,
    footer: `<button type="button" class="btn primary" data-print>${icon('print', 16)} طباعة</button><button type="button" class="btn" data-close>إلغاء</button>` });
  const iSel = $('[name=i]', m.el), kSel = $('[name=k]', m.el);
  kSel.value = item.kind;
  iSel.onchange = () => { kSel.value = items[+iSel.value].kind; };
  $('[data-print]', m.el).onclick = () => { const it = items[+iSel.value], k = kSel.value, x = $('[name=x]', m.el).value.trim(); m.close(); printCare(it, k, x); };
}
ACTIONS['care-sheet'] = b => openCareSheet(b.dataset.proc ? careItems().find(x => x.id == b.dataset.proc) : null);
