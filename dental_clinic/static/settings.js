'use strict';
/* ====== الإعدادات، المستخدمون، النسخ الاحتياطي، سجل التدقيق ====== */
const ROLE_AR = { admin: 'مدير', reception: 'استقبال / محاسبة', doctor: 'طبيب' };
const fmtBytes = n => n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';

async function pageSettings(main, tab) {
  tab = tab || 'clinic';
  const tabs = [['clinic', 'بيانات العيادة'], ['account', 'حسابي'], ['users', 'المستخدمون'], ['import', 'استيراد من Excel'], ['network', 'لابتوبات وموبايل'], ['backup', 'النسخ الاحتياطي'], ['audit', 'سجل التدقيق']];
  main.innerHTML = `<div class="page-head"><h1>الإعدادات والنسخ الاحتياطي</h1></div><nav class="tabs">${tabs.map(t => `<a href="#/settings/${t[0]}" class="${t[0] === tab ? 'on' : ''}">${t[1]}</a>`).join('')}</nav><div id="st"></div>`;
  ({ clinic: stClinic, account: stAccount, users: stUsers, import: stImport, network: stNetwork, backup: stBackup, audit: stAudit }[tab] || stClinic)($('#st'));
}

async function stClinic(host) {
  const { settings: s } = await api('GET', '/api/settings');
  let docs = []; try { docs = JSON.parse(s.doctors || '[]'); } catch (e) { }
  host.innerHTML = `<section class="card"><form id="cf" class="form-grid c2" novalidate>
    ${['clinic_name|اسم العيادة (يظهر في رأس التقارير)|full', 'clinic_phone|هاتف العيادة|', 'clinic_address|العنوان|', 'currency_label|اسم العملة|', 'currency_symbol|رمز العملة المعروض|', 'currency_code|رمز العملة (ISO)|', 'receipt_footer|عبارة أسفل الإيصالات والتقارير|full'].map(x => { const [n, l, c] = x.split('|'); return `<label class="fld ${c}"><span>${l}</span><input name="${n}" value="${esc(s[n])}" autocomplete="off"></label>`; }).join('')}
    <label class="fld"><span>القفل التلقائي بعد (دقائق من عدم الاستخدام، 0 = معطّل)</span><input name="idle_minutes" inputmode="numeric" value="${esc(s.idle_minutes)}"></label>
    <label class="fld full"><span>أسماء الأطباء (اسم في كل سطر — تظهر كقائمة اختيار عند إضافة مراجع أو زيارة، وفي تقرير عمل الأطباء)</span><textarea name="doctors" rows="3">${esc(docs.join('\n'))}</textarea></label>
    <div class="form-err" role="alert"></div><div class="full"><button type="submit" class="btn primary">حفظ الإعدادات</button></div></form></section>`;
  $('#cf').onsubmit = async e => {
    e.preventDefault();
    const f = e.target, body = {}; $$('input,textarea', f).forEach(i => body[i.name] = i.value.trim());
    body.doctors = body.doctors.split('\n'); body.idle_minutes = parseInt(toLatin(body.idle_minutes), 10);
    try { const r = await api('PUT', '/api/settings', body); Object.assign(S.settings, r.settings); renderSide(); toast('تم حفظ الإعدادات'); } catch (er) { $('.form-err', f).textContent = er.message; }
  };
}

function stAccount(host) {
  host.innerHTML = `<section class="card narrow"><h3>تغيير كلمة المرور</h3><p class="muted">المستخدم الحالي: <b>${esc(S.user.username)}</b> (${ROLE_AR[S.user.role]})</p><form id="pf" class="form-grid c1" novalidate>
    <label class="fld"><span>كلمة المرور الحالية</span><input type="password" name="old_password" autocomplete="current-password"></label>
    <label class="fld"><span>كلمة المرور الجديدة (8 أحرف على الأقل)</span><input type="password" name="new_password" autocomplete="new-password"></label>
    <label class="fld"><span>تأكيد كلمة المرور الجديدة</span><input type="password" name="c" autocomplete="new-password"></label>
    <div class="form-err" role="alert"></div><div><button type="submit" class="btn primary">تغيير كلمة المرور</button></div></form></section>`;
  $('#pf').onsubmit = async e => {
    e.preventDefault(); const f = e.target, v = n => $(`[name=${n}]`, f).value;
    if (v('new_password') !== v('c')) { $('.form-err', f).textContent = 'تأكيد كلمة المرور غير مطابق'; return; }
    try { await api('POST', '/api/change_password', { old_password: v('old_password'), new_password: v('new_password') }); f.reset(); $('.form-err', f).textContent = ''; toast('تم تغيير كلمة المرور'); } catch (er) { $('.form-err', f).textContent = er.message; }
  };
}

async function stUsers(host) {
  const d = await api('GET', '/api/users'); window._users = d.users;
  host.innerHTML = `<div class="toolbar"><button type="button" class="btn primary" data-action="new-user">${icon('plus', 16)} مستخدم جديد</button></div><section class="card">${simpleTable(['المستخدم', 'الاسم', 'الصلاحية', 'الحالة', ''], d.users.map(u => [`<bdi>${esc(u.username)}</bdi>`, esc(u.full_name || ''), ROLE_AR[u.role], u.active ? '<span class="badge b-completed">مفعّل</span>' : '<span class="badge b-cancelled">معطّل</span>', `<button type="button" class="btn sm" data-action="edit-user" data-id="${u.id}">${icon('edit', 14)} تعديل</button>`]))}
    <p class="muted small">الصلاحيات: <b>المدير</b> كل شيء. <b>الاستقبال/المحاسبة</b> المراجعون والزيارات والدفعات والمواعيد والتقرير اليومي والمدينون. <b>الطبيب</b> السجل العلاجي والمواعيد فقط دون أي معلومات مالية.</p></section>`;
}
const roleOpts = Object.entries(ROLE_AR).map(([v, t]) => ({ v, t }));
ACTIONS['new-user'] = () => formModal({ title: 'مستخدم جديد', fields: [{ name: 'username', label: 'اسم المستخدم', required: true }, { name: 'full_name', label: 'الاسم' }, { name: 'role', label: 'الصلاحية', type: 'select', options: roleOpts }, { name: 'password', label: 'كلمة المرور (8 أحرف على الأقل)', type: 'password', required: true }], values: { role: 'reception' },
  onSubmit: async (v, f, m) => { await api('POST', '/api/users', v); m.close(); toast('تمت إضافة المستخدم'); pageSettings($('#main'), 'users'); } });
ACTIONS['edit-user'] = b => { const u = window._users.find(x => x.id == b.dataset.id); formModal({ title: 'تعديل المستخدم: ' + u.username, fields: [{ name: 'full_name', label: 'الاسم' }, { name: 'role', label: 'الصلاحية', type: 'select', options: roleOpts }, { name: 'active', label: 'الحالة', type: 'select', options: [{ v: 1, t: 'مفعّل' }, { v: 0, t: 'معطّل' }] }, { name: 'new_password', label: 'كلمة مرور جديدة (اتركه فارغاً بدون تغيير)', type: 'password' }], values: u,
  onSubmit: async (v, f, m) => { if (!v.new_password) delete v.new_password; v.active = +v.active; await api('PUT', '/api/users/' + u.id, v); m.close(); toast('تم الحفظ'); pageSettings($('#main'), 'users'); } }); };

async function stBackup(host) {
  const d = await api('GET', '/api/backups');
  host.innerHTML = `<section class="card"><h3>إنشاء نسخة احتياطية</h3>
    <div class="alert warn">النسخة الاحتياطية على نفس القرص لا تحميك من تعطّل القرص أو سرقة الجهاز. انسخ الملف بانتظام إلى <b>مكان منفصل وآمن</b> (فلاشة أو قرص خارجي مشفّر أو جهاز آخر)، فالملف يحوي بيانات المراجعين كاملة.</div>
    <div class="toolbar"><button type="button" class="btn primary" data-action="make-backup">${icon('download', 16)} إنشاء نسخة احتياطية الآن</button></div>
    <p class="muted small">مجلد النسخ على هذا الجهاز: <bdi dir="ltr">${esc(d.dir)}</bdi><br>يُنشئ البرنامج نسخة تلقائية مرة كل يوم عند التشغيل أو تسجيل الدخول ويحتفظ بآخر 30 نسخة تلقائية.</p></section>
  <section class="card"><h3>النسخ المتوفرة</h3>${simpleTable(['الملف', 'التاريخ', 'الحجم', ''], d.backups.map(b => [`<bdi dir="ltr">${esc(b.name)}</bdi>`, dateH(b.modified), fmtBytes(b.size), `<a class="btn sm" href="/api/backup/download?name=${encodeURIComponent(b.name)}">${icon('download', 14)} تنزيل نسخة إلى جهازي</a>`]))}</section>
  <section class="card"><h3>استعادة نسخة احتياطية</h3><div class="alert err">الاستعادة <b>تستبدل كل البيانات الحالية</b> ببيانات النسخة المختارة. يُحفظ تلقائياً نسخة من الوضع الحالي قبل الاستبدال، وسيُطلب منك تسجيل الدخول من جديد.</div>
    <input type="file" id="rf" accept=".db"><div class="mt"><button type="button" class="btn danger" data-action="do-restore">استعادة من الملف المختار</button></div></section>`;
}
ACTIONS['make-backup'] = async () => { try { const r = await api('POST', '/api/backup'); toast(`تم إنشاء النسخة الاحتياطية بنجاح (${r.backup.patients} مراجع، ${fmtBytes(r.backup.size)})`); pageSettings($('#main'), 'backup'); } catch (e) { toast('فشل النسخ الاحتياطي: ' + e.message, 'err'); } };
ACTIONS['do-restore'] = async () => {
  const f = $('#rf').files[0]; if (!f) { toast('اختر ملف النسخة الاحتياطية أولاً', 'err'); return; }
  if (!await confirmBox(`سيتم استبدال كل بيانات العيادة الحالية بمحتوى الملف «${f.name}». هل أنت متأكد؟`, { danger: true, ok: 'نعم، استعد البيانات', title: 'تحذير: استبدال البيانات' })) return;
  try { const r = await api('POST', '/api/restore', null, { raw: await f.arrayBuffer() }); toast('تمت الاستعادة بنجاح. حُفظت نسخة من الوضع السابق باسم ' + r.safety_backup); setTimeout(() => { S.user = null; location.hash = '#/'; location.reload(); }, 1800); }
  catch (e) { toast('فشلت الاستعادة، لم تتغير البيانات: ' + e.message, 'err'); }
};

const AUD_ENT = { patient: 'مراجع', visit: 'زيارة', procedure: 'إجراء', payment: 'دفعة', adjustment: 'تعديل مالي', expense: 'مصروف', appointment: 'موعد', user: 'مستخدم', settings: 'إعدادات', backup: 'نسخ احتياطي', system: 'نظام' };
const AUD_ACT = { create: 'إنشاء', update: 'تعديل', delete: 'حذف', void: 'إلغاء', login: 'دخول', setup: 'إعداد أولي', restore: 'استعادة', change_password: 'تغيير كلمة مرور', seed_demo: 'بيانات تجريبية' };
async function stAudit(host) {
  const d = await api('GET', '/api/audit?limit=500'); window._aud = d.rows;
  host.innerHTML = `<section class="card"><p class="muted">آخر 500 عملية. يُحفظ فيها ما تغيّر ومتى ومن غيّره (القيم القديمة والجديدة).</p><div id="atb"></div></section>`;
  dataTable($('#atb'), { rows: d.rows, empty: 'لا توجد سجلات.', cols: [
    { title: 'الوقت', key: 'ts', render: r => `<bdi class="num">${esc(r.ts)}</bdi>` }, { title: 'المستخدم', key: 'user', render: r => `<bdi>${esc(r.user || '')}</bdi>` },
    { title: 'العملية', val: r => (AUD_ACT[r.action] || r.action) + ' ' + (AUD_ENT[r.entity] || r.entity) }, { title: 'المعرّف', key: 'entity_id', render: r => `<bdi>${r.entity_id ?? ''}</bdi>` },
    { title: 'التفاصيل', sortable: false, render: r => `${r.note ? `<div>السبب: ${esc(r.note)}</div>` : ''}${r.old_json || r.new_json ? `<button type="button" class="btn sm" data-action="aud-detail" data-id="${r.id}">عرض التغيير</button>` : ''}` }] });
}
ACTIONS['aud-detail'] = b => {
  const r = window._aud.find(x => x.id == b.dataset.id), pj = s => { try { return JSON.stringify(JSON.parse(s), null, 2); } catch (e) { return s || '—'; } };
  modal({ title: 'تفاصيل التغيير', wide: true, body: `<div class="form-grid c2"><div><h4>قبل</h4><pre class="json" dir="ltr">${esc(pj(r.old_json))}</pre></div><div><h4>بعد</h4><pre class="json" dir="ltr">${esc(pj(r.new_json))}</pre></div></div>` });
};

/* ====== استيراد من Excel ====== */
let IMP = { file: null, data: null, docs: null };
async function stImport(host) {
  let hist = []; try { hist = (await api('GET', '/api/import/history')).batches; } catch (e) { }
  host.innerHTML = `<section class="card"><h3>استيراد سجل العيادة من Excel</h3>
    <p class="muted">يقرأ البرنامج الملف (xlsx أو csv)، يدمج أسماء المراجع المتشابهة، يحذف الصفوف المكررة، يصحّح التواريخ المقلوبة (يوم/شهر)، ويحوّل رموز الأسنان (مثل UL6) إلى نظام FDI. <b>ستشاهد معاينة كاملة قبل أي إدخال</b>، ولا يُدخل شيء إلا بعد اعتمادك. وتُحفظ نسخة احتياطية تلقائياً قبل الإدخال.</p>
    <div class="form-grid c3"><label class="fld full"><span>ملف Excel</span><input type="file" id="impf" accept=".xlsx,.csv"></label>
    <label class="fld"><span>المبالغ في الملف</span><select id="impm"><option value="1000">بالألف (25 = 25,000)</option><option value="1">كاملة (25000 = 25,000)</option></select></label>
    <label class="fld"><span>سنة افتراضية للتواريخ بدون سنة (اختياري)</span><input id="impy" inputmode="numeric" placeholder="مثال 2022"></label>
    <div class="fld"><span>&nbsp;</span><button type="button" class="btn primary" data-action="imp-preview">تحليل الملف ومعاينة النتيجة</button></div></div>
    <div class="alert info">قاعدة الحساب: التكلفة تُستنتج من «المدفوع + المتبقي» لكل صف مع مراعاة الرصيد السابق للمراجع، حتى يطابق رصيد كل مراجع آخر «متبقي» مكتوب في الملف. صفوف «تسديد» تُسجَّل كدفعات بدون تكلفة جديدة.</div></section>
    <div id="impres"></div>
    ${hist.length ? `<section class="card"><h3>عمليات الاستيراد السابقة</h3>${simpleTable(['#', 'التاريخ', 'الملف', 'المستخدم', 'الصفوف', 'مراجعون جدد', 'نسخة الأمان'], hist.map(b => [b.id, dateH(b.ts), esc(b.filename || ''), esc(b.user || ''), intH(b.rows_imported), intH(b.patients_new), `<bdi dir="ltr">${esc(b.backup_name || '')}</bdi>`]))}</section>` : ''}`;
}
async function runImportPreview() {
  const f = $('#impf').files[0]; if (!f) { toast('اختر ملف Excel أولاً', 'err'); return; }
  const btn = $('[data-action=imp-preview]'); btn.disabled = true; $('#impres').innerHTML = '<div class="card muted">جارٍ تحليل الملف… قد يستغرق بضع ثوانٍ للملفات الكبيرة.</div>';
  try {
    const q = { mult: $('#impm').value, year: toLatin($('#impy').value.trim()), filename: f.name };
    if (IMP.docs) q.doctors = JSON.stringify(IMP.docs);
    IMP.data = await api('POST', '/api/import/preview?' + qs(q), null, { raw: await f.arrayBuffer() });
    IMP.docs = Object.fromEntries(IMP.data.summary.sheets.map(s => [s.name, s.doctor || '']));
    drawImportPreview();
  } catch (e) { $('#impres').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  btn.disabled = false;
}
/* ملف جديد أو تحليل من جديد: نبدأ بالمطابقة التلقائية لأسماء الشيتات مع الأطباء */
ACTIONS['imp-preview'] = () => { IMP.docs = null; runImportPreview(); };
CHANGES['imp-doc'] = el => { IMP.docs[el.dataset.sheet] = el.value; runImportPreview(); };
function importSheetsCard(s) {
  const docs = doctorList();
  const sel = sh => `<select data-change="imp-doc" data-sheet="${esc(sh.name)}" aria-label="طبيب الشيت ${esc(sh.name)}"><option value="">— مشترك / بدون طبيب —</option>${docs.concat(sh.doctor && !docs.includes(sh.doctor) ? [sh.doctor] : []).map(d => `<option value="${esc(d)}" ${d === sh.doctor ? 'selected' : ''}>${esc(d)}</option>`).join('')}</select>`;
  const byDoc = (s.by_doctor || []).map(b => [b.doctor ? esc(b.doctor) : '<span class="muted">مشترك / بدون طبيب</span>', intH(b.rows), intH(b.patients), moneyH(b.charge), moneyH(b.paid)]);
  return `<section class="card"><h3>الشيتات والأطباء</h3>
    <p class="muted small">اختر الطبيب الذي اشتغل كل شيت. كل زيارات ودفعات الشيت تُسجَّل باسمه، فتظهر في تقرير «عمل الأطباء» لأي فترة. الشيت المشترك (فيه شغل أكثر من طبيب) اتركه «مشترك». الشيت الذي فيه اسم الطبيب يُختار له تلقائياً.</p>
    ${docs.length ? '' : '<div class="alert warn">لا توجد أسماء أطباء بعد. أضفها من «بيانات العيادة ← أسماء الأطباء» ثم أعد التحليل.</div>'}
    ${simpleTable(['الشيت', 'الصفوف', 'الطبيب'], s.sheets.map(sh => [esc(sh.name), intH(sh.rows), sel(sh)]))}
    ${byDoc.length > 1 || (byDoc.length && s.by_doctor[0].doctor) ? '<h4>ملخص حسب الطبيب</h4>' + simpleTable(['الطبيب', 'الصفوف', 'المراجعون', 'قيمة العمل', 'المدفوع'], byDoc) : ''}
    <p class="muted small">حساب «المتبقي» يُتابع لكل طبيب على حدة، لأن شيت كل طبيب يسجّل حسابه فقط. الرصيد من الشيتات المشتركة ينتقل لأول طبيب يكمل مع المراجع.</p>
    ${s.duplicates_previous ? `<div class="alert warn">${fmt(s.duplicates_previous)} صف مستورد سابقاً لن يُعاد إدخاله، ولن يتغير طبيبه.</div>` : ''}</section>`;
}
function drawImportPreview() {
  const d = IMP.data, s = d.summary, host = $('#impres');
  const sevAr = { skipped: 'تم تخطيه', dup: 'مكرر', warn: 'تنبيه' };
  host.innerHTML = importSheetsCard(s) + `<section class="card"><h3>نتيجة التحليل</h3>${statGrid([
    { label: 'صفوف في الملف', value: intH(s.rows_total) }, { label: 'صفوف ستُستورد', value: intH(s.rows_imported), cls: 'good' },
    { label: 'مراجعون (جدد / موجودون)', value: `${intH(s.patients_new)} / ${intH(s.patients_existing)}` },
    { label: 'صفوف مكررة مُزالة', value: intH(s.duplicates_in_file + s.duplicates_previous), note: `داخل الملف ${s.duplicates_in_file} · مستوردة سابقاً ${s.duplicates_previous}` },
    { label: 'صفوف مُتخطّاة (للمراجعة)', value: intH(s.rows_skipped), cls: s.rows_skipped ? 'due' : '' },
    { label: 'تواريخ صُحّحت تلقائياً', value: intH(s.date_fixed), note: 'يوم/شهر مقلوب' },
    { label: 'مجموع المدفوع المستورد', value: moneyH(s.total_paid) }, { label: 'مجموع التكاليف المحسوبة', value: moneyH(s.total_charge) },
    { label: 'صفوف تسديد / bill', value: intH(s.payment_rows || 0), note: `${fmtMoney(s.payment_rows_total || 0)} — تُطرح من حساب المراجع ولا تُحسب عملاً جديداً` },
    { label: 'إجمالي المتبقي على المراجعين بعد الاستيراد', value: moneyH(s.outstanding_total), cls: 'due', note: `${intH(s.debtors_count)} مراجع` },
    { label: 'الفترة', value: `<bdi class="num">${esc(s.date_from || '')}</bdi><br><bdi class="num">${esc(s.date_to || '')}</bdi>` }])}
    <p class="muted small">قارن مجموع المدفوع مع حساباتك. إن كان الفرق كبيراً فغالباً معامل المبالغ (بالألف/كاملة) غير مناسب؛ غيّره وأعد التحليل.</p>
    <div class="toolbar"><button type="button" class="btn primary lg" data-action="imp-commit">اعتماد الاستيراد (${fmt(s.rows_imported)} صف)</button></div></section>
  <section class="card"><h3>صفوف تحتاج مراجعتك <span class="cnt">${d.review_total}</span></h3>
    <p class="muted small">«تم تخطيه»: لم يُستورد (غالباً مبلغ سالب أو بدون تاريخ أو اسم) فصحّحه في الإكسل وأعد الاستيراد لاحقاً؛ التكرار لا يحدث. «تنبيه»: استُورد لكن فيه ملاحظة. «مكرر»: حُذف.</p>
    ${exportBar().replace(/data-action="rpt-/g, 'data-action="imp-rpt-')}<div id="impreview"></div></section>
  ${d.work_merged && d.work_merged.length ? `<section class="card"><h3>أنواع عمل وُحّدت <span class="cnt">${fmt(s.work_merged_rows)}</span></h3><p class="muted small">الكتابات المختلفة لنفس العمل تُسجَّل تحت اسم إجراء واحد، فتُجمع في التقارير. المكتوب الأصلي يُحفظ في تفاصيل الإجراء.</p>
    ${simpleTable(['الإجراء في البرنامج', 'الكتابات في الإكسل (عدد الصفوف)', 'الصفوف'], d.work_merged.map(g => [`<b>${esc(g.name)}</b>`, g.variants.map(([w, n]) => `<bdi>${esc(w)}</bdi> (${fmt(n)})`).join('، '), intH(g.rows)]))}</section>` : ''}
  <section class="card"><h3>أسماء دُمجت لأنها متشابهة <span class="cnt">${s.names_merged_groups}</span></h3><p class="muted small">راجعها: إن كان اسمان لشخصين مختلفين فعلاً فاعلم أنهما سيُدمجان بملف واحد.</p>
    ${simpleTable(['الصيغ المكتوبة', 'الصفوف'], d.merged_names.map(m => [m.names.map(esc).join(' ، '), intH(m.rows)]))}</section>
  <section class="card"><h3>أكبر المبالغ المتبقية</h3>${simpleTable(['المراجع', 'المتبقي'], d.top_debtors.map(t => [esc(t.name), moneyH(t.remaining)]))}</section>
  <section class="card"><h3>عيّنة من الصفوف التي ستُستورد</h3>${simpleTable(['الشيت', 'صف', 'المراجع', 'الطبيب', 'التاريخ', 'العمل', 'السن', 'المدفوع', 'التكلفة'], d.sample.map(x => [esc(x.sheet), x.row, esc(x.name), esc(x.doctor || '—'), dateH(x.date) + (x.date_fixed ? ' <span class="badge b-no_show">صُحّح</span>' : ''), esc(x.work), teethTags(x.tooth), moneyH(x.paid), moneyH(x.charge)]))}</section>`;
  dataTable($('#impreview'), { rows: d.review, empty: 'لا توجد صفوف تحتاج مراجعة.', cols: [
    { title: 'النوع', val: r => sevAr[r.severity], render: r => `<span class="badge ${r.severity === 'skipped' ? 'b-no_show' : r.severity === 'dup' ? 'b-cancelled' : 'b-planned'}">${sevAr[r.severity]}</span>` },
    { title: 'الشيت', key: 'sheet' }, { title: 'الصف', key: 'row' }, { title: 'المراجع', key: 'name' }, { title: 'السبب', key: 'reason' }] });
  RPT = { title: 'مراجعة الاستيراد', headers: ['النوع', 'الشيت', 'الصف', 'المراجع', 'السبب'], rows: d.review.map(r => [sevAr[r.severity], r.sheet, r.row, r.name, r.reason]), html: simpleTable(['النوع', 'الشيت', 'الصف', 'المراجع', 'السبب'], d.review.map(r => [sevAr[r.severity], esc(r.sheet), r.row, esc(r.name), esc(r.reason)])) };
}
ACTIONS['imp-rpt-print'] = ACTIONS['rpt-print']; ACTIONS['imp-rpt-xlsx'] = ACTIONS['rpt-xlsx']; ACTIONS['imp-rpt-csv'] = ACTIONS['rpt-csv'];
ACTIONS['imp-commit'] = async () => {
  const s = IMP.data.summary;
  if (!await confirmBox(`سيتم إدخال ${fmt(s.rows_imported)} صف و${fmt(s.patients_new)} مراجع جديد إلى البرنامج. تُحفظ نسخة احتياطية تلقائياً قبل الإدخال. متابعة؟`, { ok: 'اعتماد الاستيراد', title: 'تأكيد الاستيراد' })) return;
  const btn = $('[data-action=imp-commit]'); btn.disabled = true; btn.textContent = 'جارٍ الإدخال…';
  try {
    const r = await api('POST', '/api/import/commit', { token: IMP.data.token }), x = r.result;
    $('#impres').innerHTML = `<section class="card"><div class="alert info"><b>تم الاستيراد بنجاح.</b> أُضيف ${fmt(x.patients_new)} مراجع جديد (من ${fmt(x.patients_total)} مراجع في الملف)، ${fmt(x.visits)} زيارة، ${fmt(x.procedures)} إجراء، ${fmt(x.payments)} دفعة${x.adjustments ? '، و' + fmt(x.adjustments) + ' تسوية' : ''}.<br>نسخة الأمان قبل الاستيراد: <bdi dir="ltr">${esc(r.backup)}</bdi> (يمكن استعادتها من النسخ الاحتياطي إن أردت التراجع).</div>
      <div class="toolbar"><a class="btn primary" href="#/patients">فتح قائمة المراجعين</a><a class="btn" href="#/reports/debtors">المراجعون المدينون</a></div></section>`;
    toast('تم الاستيراد بنجاح');
  } catch (e) { toast(e.message, 'err'); btn.disabled = false; btn.textContent = 'اعتماد الاستيراد'; }
};

/* ====== لابتوبات وموبايل داخل العيادة ====== */
function stNetwork(host) {
  const urls = S.lan_urls || [];
  host.innerHTML = urls.length ? `<section class="card"><h3>وضع الشبكة شغّال</h3><p>افتح أحد هذه العناوين من أي لابتوب أو موبايل متصل بنفس شبكة العيادة (نفس الواي فاي أو الراوتر)، ثم سجّل الدخول بحسابك:</p>
    ${urls.map(u => `<p class="addr"><bdi dir="ltr"><b>${esc(u)}</b></bdi></p>`).join('')}
    <div class="alert warn">يجب أن يبقى هذا الجهاز (الرئيسي) شغّالاً وبرنامجه مفتوحاً. استخدم واي فاي العيادة المحمي بكلمة سر. الاتصال داخل الشبكة غير مشفّر، ولا تفتحه من خارج العيادة.</div></section>` :
    `<section class="card"><h3>العمل من عدة لابتوبات / موبايل</h3><p>شغّل البرنامج على اللابتوب الرئيسي بالملف <b>run_network.bat</b> بدل run.bat. سيظهر في النافذة السوداء (وهنا في هذه الصفحة) عنوان مثل <bdi dir="ltr">http://192.168.1.10:8765/</bdi>، وتفتحه من باقي اللابتوبات والموبايلات بالمتصفح، ولا تحتاج تثبيت أي شيء عليها.</p>
    <p class="muted">إذا سألك Windows عن الجدار الناري (Firewall) اختر السماح على الشبكات الخاصة (Private).</p></section>`;
}
