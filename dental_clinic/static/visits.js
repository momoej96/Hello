'use strict';
/* ====== الزيارات والإجراءات، البحث حسب التاريخ، المواعيد ====== */
const FDI_UP = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28];
const FDI_LO = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38];
const FDI_PU = [55, 54, 53, 52, 51, 61, 62, 63, 64, 65], FDI_PL = [85, 84, 83, 82, 81, 71, 72, 73, 74, 75];
/* الأسنان: يمكن اختيار أكثر من سن لنفس الإجراء؛ تُكتب بنظام Palmer مفصولة بفواصل (UR1, UL1) */
const toothBtns = (a, sel) => a.map((n, i) => `<button type="button" class="tb ${i === a.length / 2 ? 'gap' : ''} ${sel.includes(String(n)) ? 'on' : ''}" data-action="tooth-set" data-t="${n}" aria-pressed="${sel.includes(String(n))}" title="${toPalmer(n)}">${toPalmer(n).slice(2)}</button>`).join('');
const toothPanel = sel => `<div class="tooth-panel"><div class="tp-note">اضغط على سن أو أكثر لنفس الإجراء (نظام Palmer) — الجهة العلوية للأعلى. اضغط مرة ثانية لإلغاء الاختيار.</div>
  <div class="tp-sides"><span>يمين المراجع (R)</span><span>يسار المراجع (L)</span></div>
  <div class="tp-row">${toothBtns(FDI_UP, sel)}</div><div class="tp-row">${toothBtns(FDI_LO, sel)}</div>
  <div class="tp-sub">أسنان الأطفال</div><div class="tp-row s">${toothBtns(FDI_PU, sel)}</div><div class="tp-row s">${toothBtns(FDI_PL, sel)}</div>
  <div class="tp-act"><button type="button" class="btn sm primary" data-action="tooth-done">تم</button><button type="button" class="btn sm" data-action="tooth-clear">بدون سن محدد</button></div></div>`;

function procRowHTML(p = {}) {
  const money = can('payments');
  return `<div class="prow" data-id="${p.id || ''}" data-cost="${p.cost || 0}">
    <div class="tooth-in"><input name="name" list="dl-procs" placeholder="الإجراء أو العلاج" value="${esc(p.name || '')}" autocomplete="off"><button type="button" class="btn sm" data-action="proc-pick" title="اختيار الإجراء من القائمة">${icon('list', 15)}</button></div>
    <div class="tooth-in"><input name="tooth_no" placeholder="السن" value="${esc(teethInput(p.tooth_no))}" dir="ltr" title="سن واحد أو أكثر بنظام Palmer، مثل: UR6 أو UR1, UL1"><button type="button" class="btn sm" data-action="tooth-pick" title="اختيار السن">${icon('tooth', 15)}</button></div>
    <select name="status">${Object.entries(PROC_ST).map(([k, t]) => `<option value="${k}" ${(p.status || 'completed') === k ? 'selected' : ''}>${t}</option>`).join('')}</select>
    ${money ? `<input name="cost" data-money inputmode="decimal" placeholder="التكلفة${MONEY_UNIT()}" value="${p.cost ? moneyIn(p.cost) : ''}" autocomplete="off">` : ''}
    <input name="details" class="pdet" placeholder="تفاصيل العلاج" value="${esc(p.details || '')}">
    <button type="button" class="btn sm danger-o" data-action="rm-proc" title="حذف الإجراء">${icon('trash', 15)}</button>
    <div class="pext">
      <div class="ptype" hidden></div>
      <div class="plab" ${needsLab(p.name) ? '' : 'hidden'}><label>المختبر <input name="lab" list="dl-labs" value="${esc(p.lab || '')}" placeholder="اسم المختبر الذي عُملت عنده الحالة" autocomplete="off"></label></div>
      <div class="rc" ${isRootCanal(p.name) ? '' : 'hidden'}><b>مراحل حشوة الجذر:</b>
        ${RC_STEPS.map(([k, t]) => `<label class="chk"><input type="checkbox" name="rc_${k}" ${(p.rc_steps || '').split(',').includes(k) ? 'checked' : ''}> <bdi dir="ltr">${t}</bdi></label>`).join('')}
        <label class="rcm">القياسات <input name="rc_measure" dir="ltr" value="${esc(p.rc_measure || '')}" placeholder="مثال: MB 21mm · DB 20.5mm · P 22mm"></label></div>
      ${money && !p.id ? `<div class="ppay"><label class="chk"><input type="checkbox" name="pay_cash" checked> <b>تم الدفع نقداً</b></label>
        <label class="prem" hidden>المتبقي${MONEY_UNIT()} <input name="remain" data-money inputmode="decimal" autocomplete="off"></label><span class="pinfo muted small"></span></div>` : ''}
    </div></div>`;
}
/* إظهار مراحل حشوة الجذر حسب اسم الإجراء، وحقل «المتبقي» عند إزالة «تم الدفع نقداً» */
function syncProcRow(r) {
  const nm = $('[name=name]', r).value, par = procParent(nm), typ = procType(nm);
  $('.rc', r).hidden = !isRootCanal(nm);
  // أنواع الإجراء (زركون/سيراميك/Emax، حديد/شفاف/متحرك…) تظهر أزراراً داخل الإجراء
  const pt = $('.ptype', r); pt.hidden = !par;
  if (par && pt.dataset.for !== nm) {
    pt.dataset.for = nm;
    pt.innerHTML = `<b>النوع:</b>` + par[1].map(t => `<button type="button" class="btn sm ${t === typ ? 'primary' : ''}" data-action="proc-type" data-v="${esc(par[0] + ' - ' + t)}">${esc(t)}</button>`).join('');
  }
  $('.plab', r).hidden = !needsLab(nm);
  const pay = $('.ppay', r); if (!pay) return;
  const st = $('[name=status]', r).value, counted = st === 'in_progress' || st === 'completed';
  pay.hidden = !counted;
  const chk = $('[name=pay_cash]', r), rem = $('[name=remain]', r), cost = parseMoney($('[name=cost]', r).value) || 0;
  $('.prem', r).hidden = chk.checked;
  if (!chk.checked && rem.value === '' && !rem._touched) { rem.value = cost ? moneyIn(cost) : ''; }
  const left = chk.checked ? 0 : Math.min(cost, parseMoney(rem.value) || 0);
  $('.pinfo', r).innerHTML = cost ? (chk.checked ? `يُسجَّل مدفوعاً ${moneyH(cost)}` : `المدفوع الآن ${moneyH(cost - left)} · يبقى ديناً ${moneyH(left)}`) : '';
}
function procPaidNow(r) {
  const pay = $('.ppay', r); if (!pay || pay.hidden) return undefined;
  const cost = parseMoney($('[name=cost]', r).value) || 0;
  if ($('[name=pay_cash]', r).checked) return cost;
  const left = parseMoney($('[name=remain]', r).value) || 0;
  if (left > cost) throw new Error('المتبقي أكبر من تكلفة الإجراء: ' + $('[name=name]', r).value);
  return cost - left;
}
function procTotal(root) {
  let t = 0;
  $$('.prow', root).forEach(r => { const st = $('[name=status]', r).value; if (st === 'cancelled') return; const c = $('[name=cost]', r); t += c ? (parseMoney(c.value) || 0) : 0; });
  const el = $('.proc-total', root); if (el) el.innerHTML = moneyH(t);
}
ACTIONS['add-proc'] = b => { const root = b.closest('.dlg-body'); $('#procRows', root).insertAdjacentHTML('beforeend', procRowHTML()); attachMoneyInputs(root); const r = $$('.prow', root).pop(); syncProcRow(r); r.querySelector('input').focus(); };
ACTIONS['rm-proc'] = b => { const root = b.closest('.dlg-body'); const row = b.closest('.prow'); const nx = row.nextElementSibling; if (nx && nx.classList.contains('tooth-panel')) nx.remove(); row.remove(); procTotal(root); };
ACTIONS['tooth-pick'] = b => {
  const row = b.closest('.prow'), nx = row.nextElementSibling;
  $$('.tooth-panel').forEach(x => x.remove());
  if (nx && nx.classList.contains('tooth-panel') && !nx.classList.contains('proc-panel')) return;
  row.insertAdjacentHTML('afterend', toothPanel(teethOf($('[name=tooth_no]', row).value))); row.nextElementSibling._row = row;
};
ACTIONS['tooth-set'] = b => {
  const pn = b.closest('.tooth-panel'), inp = $('[name=tooth_no]', pn._row), t = b.dataset.t;
  const sel = teethOf(inp.value), i = sel.indexOf(t);
  if (i >= 0) sel.splice(i, 1); else sel.push(t);
  inp.value = sel.map(toPalmer).join(', ');
  b.classList.toggle('on', i < 0); b.setAttribute('aria-pressed', String(i < 0));
};
ACTIONS['tooth-done'] = b => b.closest('.tooth-panel').remove();
/* قائمة الإجراءات: الإجراء الذي له أنواع (الحشوة الدائمية والمؤقتة) يظهر مع أنواعه للاختيار */
const procPanel = cur => `<div class="tooth-panel proc-panel"><div class="tp-note">اختر الإجراء</div><div class="pp-grid">${PROC_TREE.map(([n, subs]) => subs
  ? `<div class="pp-group"><b>${esc(n)}</b><div>${subs.map(s => { const v = n + ' - ' + s; return `<button type="button" class="btn sm ${cur === v ? 'primary' : ''}" data-action="proc-set" data-v="${esc(v)}">${esc(s)}</button>`; }).join('')}</div></div>`
  : `<button type="button" class="btn sm ${cur === n ? 'primary' : ''}" data-action="proc-set" data-v="${esc(n)}">${esc(n)}</button>`).join('')}</div></div>`;
ACTIONS['proc-pick'] = b => {
  const row = b.closest('.prow'), nx = row.nextElementSibling, open = nx && nx.classList.contains('proc-panel');
  $$('.tooth-panel').forEach(x => x.remove());
  if (open) return;
  row.insertAdjacentHTML('afterend', procPanel($('[name=name]', row).value)); row.nextElementSibling._row = row;
};
ACTIONS['proc-set'] = b => { const pn = b.closest('.proc-panel'), row = pn._row; $('[name=name]', row).value = b.dataset.v; pn.remove(); syncProcRow(row); const c = $('[name=cost]', row); (c || $('[name=details]', row)).focus(); };
ACTIONS['proc-type'] = b => { const r = b.closest('.prow'); $('[name=name]', r).value = b.dataset.v; syncProcRow(r); const lab = $('[name=lab]', r); if (!lab.closest('.plab').hidden) lab.focus(); };
ACTIONS['tooth-clear'] = b => { const pn = b.closest('.tooth-panel'); $('[name=tooth_no]', pn._row).value = ''; pn.remove(); };

/* دفعات الزيارة (المرتبطة بها أو بنفس تاريخها) قابلة للتعديل من نافذة تعديل الزيارة */
const visitPays = v => (PT.payments || []).filter(y => y.kind === 'payment' && (y.visit_id === v.id || y.pay_date === v.visit_date));
const visitPaysHTML = v => { const ps = visitPays(v); return ps.length ? `<div class="vpays"><b>دفعات هذه الزيارة</b>
  ${ps.map(y => `<label class="vpay">وصل <bdi class="num">${y.id}</bdi> · <bdi>${y.pay_date}</bdi> · ${METH[y.method]} <span>المبلغ${MONEY_UNIT()}</span><input name="pay_${y.id}" data-pay="${y.id}" data-money inputmode="decimal" value="${moneyIn(y.amount)}" autocomplete="off"></label>`).join('')}
  <span class="muted small">تعديل المبلغ هنا يعدّل الدفعة نفسها (صفر = إلغاؤها). وإذا غيّرت تاريخ الزيارة تنتقل دفعاتها لنفس التاريخ. التغييرات تُحفظ في سجل التدقيق.</span></div>` : ''; };

function openVisitModal(v) {
  const isNew = !v, p = PT.patient, money = can('payments');
  const docs = doctorList();
  v = v || { visit_date: today(), visit_time: nowTime(), doctor: p.doctor || '', procedures: [{}] };
  const docField = docs.length || v.doctor
    ? `<label class="fld"><span>الطبيب</span><select name="doctor">${doctorOptions(v.doctor).map(o => `<option value="${esc(o.v)}" ${o.v === (v.doctor || '') ? 'selected' : ''}>${esc(o.t)}</option>`).join('')}</select></label>`
    : null;
  const f = (n, l, val, type = 'text', extra = '') => `<label class="fld ${extra}"><span>${l}</span><input name="${n}" type="${type}" value="${esc(val || '')}" autocomplete="off" ${n === 'doctor' ? 'list="dl-docs"' : ''}></label>`;
  const m = modal({
    title: isNew ? 'زيارة جديدة — ' + p.full_name : 'تعديل الزيارة', wide: true,
    body: `<form class="vform" novalidate>
      <datalist id="dl-procs">${COMMON_PROCS.map(x => `<option value="${esc(x)}">`).join('')}</datalist><datalist id="dl-labs"></datalist><datalist id="dl-docs">${docs.map(x => `<option value="${esc(x)}">`).join('')}</datalist>
      <div class="form-grid c3">${f('visit_date', 'تاريخ الزيارة *', v.visit_date, 'date')}${f('visit_time', 'الوقت', v.visit_time, 'time')}${docField || f('doctor', 'الطبيب', v.doctor)}</div>
      <h4 class="sec">الإجراءات العلاجية</h4>
      <div class="phead"><span>الإجراء</span><span>السن</span><span>الحالة</span>${money ? `<span>التكلفة${MONEY_UNIT()}</span>` : ''}<span>تفاصيل</span><span></span></div>
      <div id="procRows">${(v.procedures.length ? v.procedures : [{}]).map(procRowHTML).join('')}</div>
      <div class="padd"><button type="button" class="btn sm" data-action="add-proc">${icon('plus', 15)} إضافة إجراء آخر لنفس الزيارة</button>${money ? `<span class="ptot">إجمالي الزيارة (بدون الملغى): <b class="proc-total"></b></span>` : ''}</div>
      ${!isNew && can('finance_edit') ? visitPaysHTML(v) : ''}
      ${money ? '<p class="muted small">«تم الدفع نقداً» لكل إجراء جديد: يُسجَّل المبلغ دفعة مباشرة. إذا لم يدفع كاملاً أزل العلامة واكتب «المتبقي»، فيُضاف إلى المبلغ المطلوب منه.</p>' : ''}
      ${money ? '<p class="muted small">الإجراء «مخطط له» لا يدخل في المبلغ المستحق على المراجع حتى تغيّر حالته إلى «قيد التنفيذ» أو «مكتمل».</p>' : ''}
      <label class="fld full"><span>ملاحظات سريرية</span><textarea name="notes" rows="3">${esc(v.notes || '')}</textarea></label>
      <div class="form-grid c3">${f('next_appointment', 'موعد الزيارة القادمة', v.next_appointment, 'date')}${f('next_time', 'وقت الموعد القادم', v.next_time, 'time')}</div>
      <div class="form-err" role="alert"></div></form>`,
    footer: `<button type="button" class="btn primary" data-save>حفظ الزيارة</button><button type="button" class="btn" data-close>إلغاء</button>`,
  });
  const root = m.body, form = $('form', root);
  api('GET', '/api/labs').then(d => { $('#dl-labs', root).innerHTML = d.labs.map(l => `<option value="${esc(l)}">`).join(''); }).catch(() => { });
  const onEdit = e => { const r = e && e.target.closest && e.target.closest('.prow'); if (r) { if (e.target.name === 'remain') e.target._touched = true; syncProcRow(r); } procTotal(root); };
  root.addEventListener('input', onEdit); root.addEventListener('change', onEdit); $$('.prow', root).forEach(syncProcRow); procTotal(root);
  let busy = false;
  async function save() {
    if (busy) return;
    const err = $('.form-err', root); err.textContent = '';
    const procs = [];
    try {
      $$('.prow', root).forEach(r => {
        const g = n => { const e = $(`[name=${n}]`, r); return e ? e.value.trim() : ''; };
        if (!g('name') && !g('tooth_no') && !g('details') && !(parseMoney(g('cost')) > 0) && !r.dataset.id) return;
        const costEl = $('[name=cost]', r), rc = isRootCanal(g('name'));
        const pr = { id: r.dataset.id ? +r.dataset.id : undefined, name: g('name'), tooth_no: g('tooth_no'), status: g('status'), details: g('details'), cost: costEl ? (parseMoney(costEl.value) || 0) : +r.dataset.cost,
          rc_steps: rc ? RC_STEPS.filter(([k]) => $(`[name=rc_${k}]`, r).checked).map(([k]) => k) : [], rc_measure: rc ? g('rc_measure') : '', lab: needsLab(g('name')) ? g('lab') : '' };
        const paid = procPaidNow(r); if (paid !== undefined) pr.paid_now = paid;
        procs.push(pr);
      });
    } catch (e2) { err.textContent = e2.message; return; }
    const body = { visit_date: $('[name=visit_date]', root).value, visit_time: $('[name=visit_time]', root).value, doctor: $('[name=doctor]', root).value.trim(), notes: $('[name=notes]', root).value.trim(),
      next_appointment: $('[name=next_appointment]', root).value, next_time: $('[name=next_time]', root).value, procedures: procs };
    const payEls = $$('[data-pay]', root);
    if (payEls.length) body.payments = payEls.map(e => ({ id: +e.dataset.pay, amount: parseMoney(e.value) === '' ? 0 : parseMoney(e.value) }));
    if (!body.visit_date) { err.textContent = 'تاريخ الزيارة مطلوب'; return; }
    busy = true; $('[data-save]', m.el).disabled = true;
    try {
      let r;
      if (isNew) r = await api('POST', `/api/patients/${p.id}/visits`, body);
      else r = await withForce(force => api('PUT', '/api/visits/' + v.id, { ...body, force }));
      m.close(); toast(r && r.payment ? `تم حفظ الزيارة وتسجيل دفعة نقدية ${fmtMoney(r.payment.amount)}` : 'تم حفظ الزيارة'); reloadPatient();
    } catch (e) { if (e) err.textContent = e.message; busy = false; $('[data-save]', m.el).disabled = false; }
  }
  $('[data-save]', m.el).onclick = save;
  form.onsubmit = e => { e.preventDefault(); save(); };
}
ACTIONS['new-visit'] = () => openVisitModal(null);
ACTIONS['edit-visit'] = b => openVisitModal(PT.visits.find(x => x.id == b.dataset.id));

/* ====== المواعيد ====== */
const apptStatusSel = a => `<select class="st-sel a-${a.status}" data-change="appt-status" data-id="${a.id}">${Object.entries(APPT_ST).map(([k, t]) => `<option value="${k}" ${k === a.status ? 'selected' : ''}>${t}</option>`).join('')}</select>`;
CHANGES['appt-status'] = async sel => {
  try { await api('PUT', '/api/appointments/' + sel.dataset.id, { status: sel.value }); toast('تم تحديث حالة الموعد'); } catch (e) { toast(e.message, 'err'); }
  window.refreshPage();
};
function apptModal(a, patient) {
  const isNew = !a;
  a = a || { appt_date: today(), appt_time: '10:00', status: 'confirmed' };
  const m = modal({ title: isNew ? 'موعد جديد' : 'تعديل الموعد', body: `<form class="form-grid c2" novalidate>
    <div class="full"><span class="lbl">المراجع *</span><div id="apk"></div></div>
    <label class="fld"><span>التاريخ *</span><input name="appt_date" type="date" value="${esc(a.appt_date)}"></label>
    <label class="fld"><span>الوقت *</span><input name="appt_time" type="time" value="${esc(a.appt_time || '')}"></label>
    <label class="fld full"><span>سبب الموعد</span><input name="reason" value="${esc(a.reason || '')}" autocomplete="off"></label>
    <label class="fld"><span>الحالة</span><select name="status">${Object.entries(APPT_ST).map(([k, t]) => `<option value="${k}" ${a.status === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    <label class="fld full"><span>ملاحظات</span><textarea name="notes" rows="2">${esc(a.notes || '')}</textarea></label><div class="form-err" role="alert"></div></form>`,
    footer: '<button type="button" class="btn primary" data-save>حفظ الموعد</button><button type="button" class="btn" data-close>إلغاء</button>' });
  const pk = patientPicker($('#apk', m.el));
  if (patient) pk.set(patient); else if (a.patient_id) pk.set({ id: a.patient_id, full_name: a.full_name });
  $('[data-save]', m.el).onclick = async () => {
    const err = $('.form-err', m.el), g = n => $(`[name=${n}]`, m.el).value.trim();
    const pt = pk.get() || patient || (a.patient_id ? { id: a.patient_id } : null);
    if (!pt) { err.textContent = 'اختر المراجع أولاً'; return; }
    const body = { patient_id: pt.id, appt_date: g('appt_date'), appt_time: g('appt_time'), reason: g('reason'), status: g('status'), notes: g('notes') };
    try { if (isNew) await api('POST', '/api/appointments', body); else await api('PUT', '/api/appointments/' + a.id, body); m.close(); toast('تم حفظ الموعد'); window.refreshPage(); }
    catch (e) { err.textContent = e.message; }
  };
}
let APPT = { mode: 'day', date: today() };
const weekStart = d => addDays(d, -((parseISO(d).getDay() + 1) % 7));   // الأسبوع يبدأ السبت
async function drawAppointments(host) {
  const [from, to] = APPT.mode === 'day' ? [APPT.date, APPT.date] : [weekStart(APPT.date), addDays(weekStart(APPT.date), 6)];
  host.innerHTML = `<div class="toolbar"><div class="seg"><button type="button" data-action="appt-mode" data-m="day" class="${APPT.mode === 'day' ? 'on' : ''}">اليوم</button><button type="button" data-action="appt-mode" data-m="week" class="${APPT.mode === 'week' ? 'on' : ''}">الأسبوع</button></div>
    <button type="button" class="btn sm" data-action="appt-nav" data-n="-1">‹ السابق</button><input type="date" id="apd" value="${APPT.date}"><button type="button" class="btn sm" data-action="appt-nav" data-n="1">التالي ›</button><button type="button" class="btn sm" data-action="appt-today">اليوم</button>
    <span class="grow"></span><button type="button" class="btn primary" data-action="new-appt">${icon('plus', 16)} موعد جديد</button></div><div id="apl"><div class="muted pad">جارٍ التحميل…</div></div>`;
  $('#apd', host).onchange = e => { if (e.target.value) { APPT.date = e.target.value; drawAppointments(host); } };
  try {
    const d = await api('GET', '/api/appointments?' + qs({ from, to }));
    const days = {}; for (let i = 0; i <= (APPT.mode === 'day' ? 0 : 6); i++) days[addDays(from, i)] = [];
    d.appointments.forEach(a => (days[a.appt_date] = days[a.appt_date] || []).push(a));
    $('#apl').innerHTML = Object.entries(days).map(([day, list]) => `<section class="card day ${day === today() ? 'is-today' : ''}"><h3>${dayName(day)} <bdi class="num">${day}</bdi> ${day === today() ? '<span class="badge b-confirmed">اليوم</span>' : ''}<span class="cnt">${list.length}</span></h3>
      ${list.length ? `<div class="alist">${list.map(a => `<div class="appt a-${a.status}"><bdi class="atime">${esc(a.appt_time || '')}</bdi><div class="ainfo"><a class="pname" href="#/patient/${a.patient_id}">${esc(a.full_name)}</a> <span class="muted">ملف <bdi>${a.file_no}</bdi> · <bdi>${esc(a.phone || '')}</bdi></span><div class="muted small">${esc(a.reason || '')}${a.notes ? ' — ' + esc(a.notes) : ''}</div></div>${apptStatusSel(a)}<button type="button" class="btn sm" data-action="edit-appt" data-id="${a.id}">${icon('edit', 14)}</button><button type="button" class="btn sm danger-o" data-action="del-appt" data-id="${a.id}">${icon('trash', 14)}</button></div>`).join('')}</div>` : '<p class="muted">لا توجد مواعيد.</p>'}</section>`).join('');
    host._appts = d.appointments;
  } catch (e) { $('#apl').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
}
ACTIONS['appt-mode'] = b => { APPT.mode = b.dataset.m; drawAppointments($('#subpage')); };
ACTIONS['appt-nav'] = b => { APPT.date = addDays(APPT.date, +b.dataset.n * (APPT.mode === 'week' ? 7 : 1)); drawAppointments($('#subpage')); };
ACTIONS['appt-today'] = () => { APPT.date = today(); drawAppointments($('#subpage')); };
ACTIONS['new-appt'] = () => apptModal(null, null);
ACTIONS['edit-appt'] = b => apptModal($('#subpage')._appts.find(x => x.id == b.dataset.id), null);
ACTIONS['del-appt'] = async b => {
  if (!await confirmBox('حذف هذا الموعد؟', { danger: true, ok: 'حذف' })) return;
  try { await api('DELETE', '/api/appointments/' + b.dataset.id, {}); toast('تم حذف الموعد'); window.refreshPage(); } catch (e) { toast(e.message, 'err'); }
};

/* ====== الزيارات حسب التاريخ / الفترة ====== */
async function renderVisitsView(host, def) {
  const money = can('payments');
  host.innerHTML = `<section class="card filters"><div class="form-grid c4">
    <label class="fld"><span>من تاريخ</span><input type="date" id="vf" value="${def.from}"></label><label class="fld"><span>إلى تاريخ</span><input type="date" id="vt" value="${def.to}"></label>
    <label class="fld"><span>اسم / هاتف / رقم ملف</span><input type="search" id="vq" autocomplete="off"></label><label class="fld"><span>الطبيب</span><select id="vd"><option value="">كل الأطباء</option>${doctorList().concat(['غير محدد']).map(x => `<option value="${esc(x)}">${esc(x)}</option>`).join('')}</select></label></div>
    <div class="presets"><button type="button" class="btn sm" data-p="prev" title="الرجوع يوماً واحداً">‹ السابق</button><button type="button" class="btn sm" data-p="next" title="التقدّم يوماً واحداً">التالي ›</button><button type="button" class="btn sm" data-p="today">اليوم</button><button type="button" class="btn sm" data-p="yest">أمس</button><button type="button" class="btn sm" data-p="week">هذا الأسبوع</button><button type="button" class="btn sm" data-p="month">هذا الشهر</button><button type="button" class="btn sm" data-p="30">آخر 30 يوماً</button></div></section>
    <div id="vres"></div>`;
  const val = id => $('#' + id, host).value;
  let seq = 0, t;
  async function load() {
    const my = ++seq, from = val('vf'), to = val('vt');
    if (!from || !to) return;
    try {
      const d = await api('GET', '/api/visits_by_date?' + qs({ from, to, q: val('vq'), doctor: val('vd') }));
      if (my !== seq) return;
      const cols = [
        { title: 'التاريخ', key: 'visit_date', render: r => dateH(r.visit_date) },
        { title: 'الوقت', key: 'visit_time', render: r => `<bdi>${esc(r.visit_time || '')}</bdi>` },
        { title: 'المراجع', key: 'full_name', render: r => `<a class="pname" href="#/patient/${r.patient_id}">${esc(r.full_name)}</a>` },
        { title: 'الهاتف', key: 'phone', render: r => `<bdi>${esc(r.phone || '')}</bdi>` },
        { title: 'الإجراءات', val: r => r.procedures.map(p => p.name).join('، '), render: r => r.procedures.map(p => `${teethTags(p.tooth_no)}${p.tooth_no ? ' ' : ''}${esc(p.name)}`).join('<br>') || '<span class="muted">—</span>' },
      ];
      if (money) cols.push({ title: 'تكلفة العلاج', key: 'visit_cost', render: r => moneyH(r.visit_cost) }, { title: 'المقبوض في ذلك اليوم', key: 'paid_that_day', render: r => r.paid_that_day == null ? '<span class="muted">—</span>' : moneyH(r.paid_that_day) }, { title: 'المتبقي على المراجع', key: 'remaining', render: r => remBadge(r.remaining) });
      /* مجموعة لكل طبيب بترتيب ثابت، وتحتها مجموع ما قُبض له في الفترة */
      const box = $('#vtbl', host);
      box.innerHTML = d.groups.length ? d.groups.map((g, i) => `<section class="card dgroup"><h3>${esc(g.doctor)} <span class="cnt">${fmt(g.visits)} زيارة · ${fmt(g.patients)} مراجع</span></h3><div id="dg${i}"></div>
          ${money ? `<div class="dsum"><span>تكلفة العلاج: <b>${moneyH(g.cost)}</b></span><span class="hl">المبلغ المدفوع لهذا الطبيب: <b>${moneyH(g.receipts)}</b></span></div>` : ''}</section>`).join('')
        + (money && d.groups.length > 1 ? `<section class="card dsum total"><span>المجموع لكل الأطباء: ${fmt(d.visits.length)} زيارة</span><span>تكلفة العلاج: <b>${moneyH(d.visits.reduce((s, r) => s + r.visit_cost, 0))}</b></span><span class="hl">إجمالي المدفوع: <b>${moneyH(d.receipts_total)}</b></span></section>` : '')
        : '<section class="card"><p class="muted">لا توجد زيارات مسجلة في هذه الفترة.</p></section>';
      d.groups.forEach((g, i) => dataTable($('#dg' + i, box), { cols, rows: d.visits.filter(v => v.doctor_eff === g.doctor), search: false, empty: 'لا توجد زيارات لهذا الطبيب في الفترة (توجد دفعات فقط).' }));
      if (money) {
        $('#vpay', host).innerHTML = `<h3>الدفعات المقبوضة في هذه الفترة <small class="muted">(حسب تاريخ استلام المبلغ، وقد تختلف عن تاريخ العلاج)</small></h3><div id="vpayt"></div>`;
        dataTable($('#vpayt', host), { rows: d.payments, search: false, empty: 'لا توجد دفعات في هذه الفترة.', cols: [
          { title: 'التاريخ', key: 'pay_date', render: p => dateH(p.pay_date) }, { title: 'المراجع', key: 'full_name', render: p => `<a class="pname" href="#/patient/${p.patient_id}">${esc(p.full_name)}</a>` },
          { title: 'الطبيب', key: 'doctor_eff' }, { title: 'النوع', val: p => p.kind === 'refund' ? 'مسترد' : 'دفعة' },
          { title: 'المبلغ', val: p => p.kind === 'refund' ? -p.amount : p.amount, render: p => moneyH(p.kind === 'refund' ? -p.amount : p.amount) }, { title: 'الطريقة', val: p => METH[p.method] }],
          footer: () => `<tr class="tot"><td colspan="4">إجمالي المقبوضات (بدون المسترد)</td><td colspan="2">${moneyH(d.receipts_total)}</td></tr>` });
      }
      const head = ['الطبيب', 'التاريخ', 'الوقت', 'المراجع', 'الهاتف', 'الإجراءات'].concat(money ? ['تكلفة العلاج', 'المقبوض في ذلك اليوم', 'المتبقي على المراجع'] : []);
      const ordered = d.groups.flatMap(g => d.visits.filter(v => v.doctor_eff === g.doctor));
      const rows = ordered.map(v => [v.doctor_eff, v.visit_date, v.visit_time || '', v.full_name, v.phone || '', v.procedures.map(p => p.name).join('، ')].concat(money ? [v.visit_cost, v.paid_that_day ?? '', v.remaining] : []));
      const sums = money ? '<h3>المجاميع حسب الطبيب</h3>' + simpleTable(['الطبيب', 'الزيارات', 'المراجعون', 'تكلفة العلاج', 'المبلغ المدفوع'], d.groups.map(g => [esc(g.doctor), fmt(g.visits), fmt(g.patients), fmtMoney(g.cost), fmtMoney(g.receipts)])) : '';
      RPT = { title: `الزيارات من ${from} إلى ${to}`, headers: head, rows, html: sums + simpleTable(head, rows.map(r => r.map(c => esc(typeof c === 'number' ? fmt(c) : c)))) };
    } catch (e) { $('#vtbl', host).innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  }
  $('#vres', host).innerHTML = `${exportBar()}<div id="vtbl"></div>${money ? '<section class="card" id="vpay"></section>' : ''}`;
  ['vf', 'vt', 'vd'].forEach(i => $('#' + i, host).addEventListener('change', load));
  $('#vq', host).addEventListener('input', () => { clearTimeout(t); t = setTimeout(load, 250); });
  host.addEventListener('click', e => {
    const b = e.target.closest('[data-p]'); if (!b) return;
    const td = today(); let f = td, to = td;
    if (b.dataset.p === 'prev' || b.dataset.p === 'next') {      // يوم واحد للخلف أو للأمام (للفترة كلها)
      const n = b.dataset.p === 'prev' ? -1 : 1;
      f = addDays($('#vf', host).value || td, n); to = addDays($('#vt', host).value || td, n);
    }
    else if (b.dataset.p === 'yest') f = to = addDays(td, -1);
    else if (b.dataset.p === 'week') { f = weekStart(td); to = addDays(f, 6); }
    else if (b.dataset.p === 'month') [f, to] = monthRange(td.slice(0, 7));
    else if (b.dataset.p === '30') f = addDays(td, -29);
    $('#vf', host).value = f; $('#vt', host).value = to; load();
  });
  load();
}
async function pageByDate(main) {
  main.innerHTML = `<div class="page-head"><h1>مراجعو يوم أو فترة محددة</h1></div><div id="subpage"></div>`;
  renderVisitsView($('#subpage'), { from: today(), to: today() });
}
async function pageAppointments(main, tab) {
  tab = tab || 'appts';
  main.innerHTML = `<div class="page-head"><h1>المواعيد وسجل الزيارات</h1></div><nav class="tabs"><a href="#/appointments" class="${tab === 'appts' ? 'on' : ''}">المواعيد القادمة</a><a href="#/appointments/log" class="${tab === 'log' ? 'on' : ''}">سجل الزيارات</a></nav><div id="subpage"></div>`;
  if (tab === 'log') renderVisitsView($('#subpage'), { from: addDays(today(), -29), to: today() }); else drawAppointments($('#subpage'));
}
