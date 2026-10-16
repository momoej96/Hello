'use strict';
/* ====== صور الأشعة: استقبال من السنسر، رفع يدوي، عرض ====== */
const xrayUrl = id => `/api/xrays/${id}/image`;
const visitLabel = v => `${v.visit_date} — ${v.procedures.map(p => p.name).join('، ') || 'زيارة'}`;
/* صور أشعة الزيارة داخل بطاقتها في السجل العلاجي */
function visitXrays(vid) {
  const xs = (PT && PT.xrays || []).filter(x => x.visit_id === vid);
  return xs.length ? `<div class="vxr"><span class="muted small">${icon('tooth', 14)} الأشعة (${xs.length}):</span>${xs.map(x => `<button type="button" class="vxr-t" data-action="xray-view" data-id="${x.id}" title="فتح الصورة"><img src="${xrayUrl(x.id)}" alt="أشعة" loading="lazy">${x.tooth_no ? `<span>${esc(teethText(x.tooth_no))}</span>` : ''}</button>`).join('')}</div>` : '';
}

function drawXrayTab(host) {
  const xs = PT.xrays || [];
  host.innerHTML = `<div class="toolbar">
      ${can('visits') ? `<button type="button" class="btn primary" data-action="xray-capture">${icon('tooth', 16)} استقبال أشعة من السنسر</button>
      <label class="btn">${icon('plus', 16)} رفع صورة من الجهاز<input type="file" id="xrayFile" accept=".png,.jpg,.jpeg,.bmp" multiple hidden></label>` : ''}
      <span class="muted small">${xs.length ? fmt(xs.length) + ' صورة' : ''}</span></div>
    ${xs.length ? `<div class="xgrid">${xs.map(x => `<button type="button" class="xcard" data-action="xray-view" data-id="${x.id}">
        <img src="${xrayUrl(x.id)}" alt="صورة أشعة ${esc(x.taken_at)}" loading="lazy">
        <span class="xmeta"><bdi class="num">${esc(x.taken_at.slice(0, 16))}</bdi>${x.tooth_no ? ' ' + teethTags(x.tooth_no) : ''}</span>
        ${(() => { const v = PT.visits.find(i => i.id === x.visit_id); return v ? `<span class="xnote">الزيارة: ${esc(visitLabel(v))}</span>` : '<span class="xnote muted">غير مرتبطة بزيارة</span>'; })()}
        ${x.notes ? `<span class="xnote">${esc(x.notes)}</span>` : ''}</button>`).join('')}</div>`
      : `<div class="empty-state">${icon('tooth', 34)}<p>لا توجد صور أشعة لهذا المراجع.</p></div>`}`;
  const f = $('#xrayFile', host);
  if (f) f.onchange = () => uploadXrays([...f.files]);
}

async function uploadXrays(files) {
  let n = 0;
  for (const file of files) {
    try { await api('POST', `/api/patients/${PT.patient.id}/xrays?` + qs({ filename: file.name }), null, { raw: await file.arrayBuffer() }); n++; }
    catch (e) { toast(file.name + ': ' + e.message, 'err'); }
  }
  if (n) { toast(`تمت إضافة ${fmt(n)} صورة`); PT_TAB = 'xray'; reloadPatient(); }
}

/* استقبال تلقائي: يراقب البرنامج مجلد حفظ الصور في برنامج السنسر، وكل صورة جديدة تُضاف لهذا المراجع */
ACTIONS['xray-capture'] = async b => {
  const p = PT.patient, visit = b && b.dataset.visit ? PT.visits.find(v => v.id == b.dataset.visit) : null;
  let st;
  try { st = await api('POST', `/api/patients/${p.id}/xray_capture`, { visit_id: visit ? visit.id : null }); } catch (e) { toast(e.message, 'err'); return; }
  const backTab = visit ? PT_TAB : 'xray';
  if (st.replaced && st.replaced.length) toast(`أُوقف استقبال الأشعة للمراجع «${st.replaced[0].full_name}»`, 'warn');
  let active = true, timer = null, got = 0;
  const stop = async () => {
    if (!active) return; active = false; clearTimeout(timer);
    try { await api('POST', `/api/xray_capture/${st.token}/stop`, {}); } catch (e) { }
    if (got) { PT_TAB = backTab; reloadPatient(); }
  };
  const m = modal({ title: 'استقبال أشعة — ' + p.full_name + (visit ? ' — زيارة ' + visit.visit_date : ''), wide: true, onClose: stop,
    body: `<div class="xwait"><div class="pulse"></div><div><b>بانتظار صورة الأشعة…</b><br>
      <span class="muted">صوّر الآن ببرنامج السنسر (Woodpecker) كالعادة. كل صورة يحفظها تُضاف مباشرة ${visit ? 'لزيارة ' + esc(visitLabel(visit)) : 'لملف هذا المراجع (ولزيارة اليوم إن وُجدت)'}.</span><br>
      <small class="muted">المجلد المراقَب: <bdi dir="ltr">${esc(st.folder)}</bdi> · يتوقف تلقائياً بعد <span id="xleft">${st.minutes}</span> دقيقة</small></div></div>
      <div id="xgot" class="xgrid mt"></div>`,
    footer: `<button type="button" class="btn primary" data-close>إنهاء الاستقبال</button>` });
  m.el.dataset.sticky = '1';
  async function poll() {
    if (!active) return;
    try {
      const r = await api('POST', `/api/xray_capture/${st.token}/poll`, {});
      if (!r.active) {
        active = false;
        $('.xwait', m.el).innerHTML = `<div><b>${r.reason === 'timeout' ? 'انتهت مدة الاستقبال.' : 'توقف الاستقبال.'}</b> ${r.reason === 'stopped' ? 'بدأ استقبال لمراجع آخر من جهاز آخر.' : 'اضغط «استقبال أشعة» مرة أخرى عند الحاجة.'}</div>`;
        return;
      }
      if (r.new.length) {
        got += r.new.length;
        $('#xgot', m.el).insertAdjacentHTML('beforeend', r.new.map(x => `<div class="xcard"><img src="${xrayUrl(x.id)}" alt="صورة أشعة"><span class="xmeta">وصلت ✓ <bdi class="num">${esc(x.taken_at.slice(11, 16))}</bdi></span></div>`).join(''));
        toast('وصلت صورة أشعة جديدة');
      }
      const left = $('#xleft', m.el); if (left) left.textContent = Math.ceil(r.seconds_left / 60);
    } catch (e) { toast(e.message, 'err'); }
    if (active) timer = setTimeout(poll, 2000);
  }
  poll();
};

/* عارض الصورة: تكبير، سطوع، تباين، عكس الألوان، تدوير، طباعة */
ACTIONS['xray-view'] = b => {
  const xs = PT.xrays || [], x = xs.find(i => i.id == b.dataset.id); if (!x) return;
  const v = { z: 1, br: 100, ct: 100, inv: false, rot: 0, dx: 0, dy: 0 };
  const m = modal({ title: 'صورة أشعة — ' + PT.patient.full_name, wide: true, cls: 'xviewer',
    body: `<div class="xstage"><img id="ximg" src="${xrayUrl(x.id)}" alt="صورة أشعة" draggable="false"></div>
      <div class="xctl">
        <button type="button" class="btn sm" data-z="1.25" title="تكبير">＋</button><button type="button" class="btn sm" data-z="0.8" title="تصغير">－</button>
        <button type="button" class="btn sm" data-reset>الحجم الأصلي</button><button type="button" class="btn sm" data-rot>تدوير ⟳</button>
        <button type="button" class="btn sm" data-inv>عكس الألوان</button>
        <label>السطوع <input type="range" min="40" max="220" value="100" data-k="br"></label>
        <label>التباين <input type="range" min="40" max="300" value="100" data-k="ct"></label></div>
      <div class="form-grid c3 mt"><label class="fld full"><span>الزيارة</span><select name="visit_id"><option value="">— غير مرتبطة بزيارة —</option>${PT.visits.map(v => `<option value="${v.id}" ${v.id === x.visit_id ? 'selected' : ''}>${esc(visitLabel(v))}</option>`).join('')}</select></label>
        <label class="fld"><span>السن</span><input name="tooth_no" dir="ltr" value="${esc(teethOf(x.tooth_no).join(', '))}" placeholder="مثال: 36 أو 11, 21"></label>
        <label class="fld" style="grid-column:span 2"><span>ملاحظات</span><input name="notes" value="${esc(x.notes || '')}"></label></div>
      <p class="muted small">التاريخ: <bdi class="num">${esc(x.taken_at)}</bdi> · ${x.source === 'sensor' ? 'من السنسر' : 'رفع يدوي'}</p>`,
    footer: `${can('visits') ? '<button type="button" class="btn primary" data-save>حفظ</button>' : ''}<button type="button" class="btn" data-print>${icon('print', 15)} طباعة</button>
      <a class="btn" href="${xrayUrl(x.id)}" download="xray-${PT.patient.file_no}-${x.id}">تنزيل</a>
      ${can('delete') ? '<button type="button" class="btn danger-o" data-del>حذف</button>' : ''}<button type="button" class="btn" data-close>إغلاق</button>` });
  const img = $('#ximg', m.el), stage = $('.xstage', m.el);
  const filt = () => `brightness(${v.br}%) contrast(${v.ct}%)${v.inv ? ' invert(1)' : ''}`;
  const apply = () => { img.style.transform = `translate(${v.dx}px,${v.dy}px) scale(${v.z}) rotate(${v.rot}deg)`; img.style.filter = filt(); };
  $$('[data-z]', m.el).forEach(btn => btn.onclick = () => { v.z = Math.min(8, Math.max(0.3, v.z * +btn.dataset.z)); apply(); });
  $('[data-reset]', m.el).onclick = () => { Object.assign(v, { z: 1, dx: 0, dy: 0 }); apply(); };
  $('[data-rot]', m.el).onclick = () => { v.rot = (v.rot + 90) % 360; apply(); };
  $('[data-inv]', m.el).onclick = e => { v.inv = !v.inv; e.target.classList.toggle('primary', v.inv); apply(); };
  $$('[data-k]', m.el).forEach(r => r.oninput = () => { v[r.dataset.k] = +r.value; apply(); });
  stage.addEventListener('wheel', e => { e.preventDefault(); v.z = Math.min(8, Math.max(0.3, v.z * (e.deltaY < 0 ? 1.15 : 0.87))); apply(); }, { passive: false });
  let drag = null;
  stage.addEventListener('pointerdown', e => { drag = { x: e.clientX - v.dx, y: e.clientY - v.dy }; stage.setPointerCapture(e.pointerId); });
  stage.addEventListener('pointermove', e => { if (drag) { v.dx = e.clientX - drag.x; v.dy = e.clientY - drag.y; apply(); } });
  stage.addEventListener('pointerup', () => { drag = null; });
  const save = $('[data-save]', m.el);
  if (save) save.onclick = async () => {
    try { await api('PUT', '/api/xrays/' + x.id, { tooth_no: $('[name=tooth_no]', m.el).value, notes: $('[name=notes]', m.el).value, visit_id: $('[name=visit_id]', m.el).value }); m.close(); toast('تم الحفظ'); reloadPatient(); }
    catch (e) { toast(e.message, 'err'); }
  };
  $('[data-print]', m.el).onclick = () => {
    const p = PT.patient;
    printDoc('صورة أشعة', `<table class="kv"><tr><th>المراجع</th><td>${esc(p.full_name)}</td><th>رقم الملف</th><td><bdi>${p.file_no}</bdi></td></tr>
      <tr><th>التاريخ</th><td><bdi>${esc(x.taken_at)}</bdi></td><th>السن</th><td>${esc(teethText($('[name=tooth_no]', m.el).value.replace(/[\s،]+/g, ',')) || '—')}</td></tr></table>
      <div class="xprint"><img src="${xrayUrl(x.id)}" alt="صورة أشعة" style="filter:${filt()};transform:rotate(${v.rot}deg)"></div>
      ${$('[name=notes]', m.el).value ? `<p>${esc($('[name=notes]', m.el).value)}</p>` : ''}`);
  };
  const del = $('[data-del]', m.el);
  if (del) del.onclick = async () => {
    if (!await confirmBox('حذف صورة الأشعة من ملف المراجع؟ (أصلها يبقى في برنامج السنسر)', { danger: true, ok: 'حذف' })) return;
    try { await api('DELETE', '/api/xrays/' + x.id, {}); m.close(); toast('تم الحذف'); reloadPatient(); } catch (e) { toast(e.message, 'err'); }
  };
};
