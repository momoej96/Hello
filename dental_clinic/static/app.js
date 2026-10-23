'use strict';
/* ====== الهيكل العام، الدخول، التوجيه، القفل التلقائي ====== */
const NAV = [['#/dashboard', 'home', 'لوحة التحكم', 'patients'], ['#/patients', 'users', 'المراجعون', 'patients'], ['#/bydate', 'search', 'زيارات يوم / فترة', 'visits'],
  ['#/appointments', 'calendar', 'المواعيد والسجل', 'appointments'], ['#/reports', 'chart', 'التقارير المالية', 'reports_basic'], ['#/expenses', 'wallet', 'المصروفات', 'expenses'], ['#/settings', 'gear', 'الإعدادات والنسخ', 'settings']];
let routeSeq = 0, lockMsg = '';

window.onSessionLost = () => { if (S.user) { S.user = null; lockMsg = 'انتهت الجلسة. سجّل الدخول من جديد.'; showLogin(); } };
window.refreshPage = () => route();

function renderSide() {
  const side = $('#side'); if (!side) return;
  const h = location.hash || '#/dashboard';
  side.innerHTML = `<div class="brand">${icon('tooth', 30)}<div><b>${esc(S.settings.clinic_name)}</b><small>نظام إدارة العيادة</small></div></div>
  <nav>${NAV.filter(n => can(n[3])).map(n => `<a href="${n[0]}" class="${h.startsWith(n[0]) ? 'on' : ''}">${icon(n[1], 19)}<span>${n[2]}</span></a>`).join('')}</nav>
  <div class="side-foot"><div class="who">${icon('user', 16)} <span>${esc(S.user.full_name || S.user.username)}<small>${ROLE_AR[S.user.role]}</small></span></div>
  <button type="button" class="btn sm block" data-action="lock">${icon('lock', 15)} قفل البرنامج</button><button type="button" class="btn sm block" data-action="logout">${icon('logout', 15)} تسجيل الخروج</button></div>`;
}
ACTIONS.logout = async () => { try { await api('POST', '/api/logout', {}); } catch (e) { } S.user = null; lockMsg = ''; showLogin(); };
ACTIONS.lock = async () => { try { await api('POST', '/api/logout', {}); } catch (e) { } S.user = null; lockMsg = 'تم قفل البرنامج. أدخل كلمة المرور للمتابعة.'; showLogin(); };
ACTIONS['toggle-menu'] = () => document.body.classList.toggle('menu-open');

function showLogin(setup) {
  $$('.overlay').forEach(o => o.remove());
  $('#root').innerHTML = `<div class="login-wrap"><form class="login card" id="lf" novalidate>
    <div class="login-logo">${icon('tooth', 44)}</div><h1>${esc(S.settings.clinic_name || 'عيادة الأسنان')}</h1>
    <p class="muted">${setup ? 'الإعداد الأول: أنشئ حساب المدير' : 'تسجيل الدخول'}</p>
    ${S.demo ? '<div class="alert warn">وضع تجريبي: البيانات وهمية ومنفصلة عن بيانات العيادة الحقيقية.</div>' : ''}
    ${lockMsg ? `<div class="alert info">${esc(lockMsg)}</div>` : ''}
    ${setup ? '<label class="fld"><span>اسم العيادة</span><input name="clinic_name" autocomplete="off"></label>' : ''}
    <label class="fld"><span>اسم المستخدم</span><input name="username" autocomplete="username" required></label>
    <label class="fld"><span>كلمة المرور${setup ? ' (8 أحرف على الأقل)' : ''}</span><input type="password" name="password" autocomplete="${setup ? 'new-password' : 'current-password'}" required></label>
    ${setup ? '<label class="fld"><span>تأكيد كلمة المرور</span><input type="password" name="c" autocomplete="new-password"></label>' : ''}
    <div class="form-err" role="alert"></div><button type="submit" class="btn primary lg block">${setup ? 'إنشاء الحساب والدخول' : 'دخول'}</button></form></div>`;
  const f = $('#lf'); $('[name=username]', f).focus();
  f.onsubmit = async e => {
    e.preventDefault(); const g = n => { const x = $(`[name=${n}]`, f); return x ? x.value : ''; };
    if (setup && g('password') !== g('c')) { $('.form-err', f).textContent = 'تأكيد كلمة المرور غير مطابق'; return; }
    try {
      const r = await api('POST', setup ? '/api/setup' : '/api/login', { username: g('username').trim(), password: g('password'), clinic_name: g('clinic_name') });
      lockMsg = ''; await boot();
    } catch (er) { $('.form-err', f).textContent = er.message; }
  };
}

function showApp() {
  $('#root').innerHTML = `<div id="app"><aside id="side"></aside><div class="content"><header class="topbar no-print"><button type="button" class="btn icon-btn menu-btn" data-action="toggle-menu" aria-label="القائمة">${icon('menu', 22)}</button>
    <div class="tsearch">${icon('search', 18)}<input id="tq" type="search" placeholder="بحث سريع عن مراجع: اسم أو هاتف أو رقم ملف" autocomplete="off"><div id="tres" class="tres"></div></div>
    ${S.demo ? '<span class="demo-badge">وضع تجريبي</span>' : ''}${can('patients') ? `<button type="button" class="btn primary" data-action="new-patient">${icon('plus', 16)} مراجع جديد</button>` : ''}</header><main id="main"></main></div></div>`;
  renderSide();
  const tq = $('#tq'), tres = $('#tres'); let t, seq = 0;
  tq.addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const q = tq.value.trim(); if (!q) { tres.innerHTML = ''; return; }
      const my = ++seq;
      try {
        const d = await api('GET', '/api/patients?' + qs({ q, limit: 7 })); if (my !== seq) return;
        tres.innerHTML = d.patients.map(p => `<a href="#/patient/${p.id}" data-pick><b>${esc(p.full_name)}</b><span class="muted"> ملف <bdi>${p.file_no}</bdi> · <bdi>${esc(p.phone || '')}</bdi></span></a>`).join('') + (can('patients') ? addNewItem(q) : '');   // مثل جهات الاتصال: آخر سطر «إضافة … كمراجع جديد»
      } catch (e) { }
    }, 180);
  });
  tq.addEventListener('keydown', e => { if (e.key === 'Enter') { const a = $('a[href]', tres); if (a) { location.hash = a.getAttribute('href'); tq.value = ''; tres.innerHTML = ''; } else { const n = $('.add-new', tres); if (n) n.click(); } } if (e.key === 'Escape') { tres.innerHTML = ''; } });
  document.addEventListener('click', e => { if (e.target.closest('[data-pick]')) { tq.value = ''; tres.innerHTML = ''; } else if (!e.target.closest('.tsearch')) tres.innerHTML = ''; });
}

async function route() {
  if (!S.user) return;
  const my = ++routeSeq, main = $('#main'); if (!main) return;
  document.body.classList.remove('menu-open');
  const parts = (location.hash || '#/dashboard').replace(/^#\//, '').split('/');
  const [page, a, b] = parts;
  renderSide();
  const guard = p => { if (!can(p)) { main.innerHTML = '<div class="alert err">ليست لديك صلاحية لفتح هذه الصفحة.</div>'; return false; } return true; };
  try {
    main.innerHTML = '<div class="muted pad">جارٍ التحميل…</div>';
    const draw = document.createElement('div'); draw.id = 'main-tmp';
    switch (page) {
      case 'patients': if (guard('patients')) await pagePatients(main); break;
      case 'patient': if (guard('patients')) await pagePatient(main, +a, b); break;
      case 'bydate': if (guard('visits')) await pageByDate(main); break;
      case 'appointments': if (guard('appointments')) await pageAppointments(main, a); break;
      case 'reports': if (guard('reports_basic')) await pageReports(main, a); break;
      case 'expenses': if (guard('expenses')) await pageExpenses(main); break;
      case 'settings': if (guard('settings')) await pageSettings(main, a); break;
      default: if (guard('patients')) await pageDashboard(main);
    }
  } catch (e) { if (my === routeSeq) $('#main').innerHTML = `<div class="alert err">${esc(e.message)}</div>`; }
  window.scrollTo(0, 0);
}
window.addEventListener('hashchange', route);

async function boot() {
  let s;
  try { s = await api('GET', '/api/session'); } catch (e) { $('#root').innerHTML = `<div class="login-wrap"><div class="card login"><div class="alert err">${esc(e.message)}</div></div></div>`; return; }
  S.settings = s.settings; S.demo = s.demo; S.cats = s.expense_categories || []; S.lan_urls = s.lan_urls || [];
  if (!s.authenticated) { S.user = null; showLogin(s.needs_setup); return; }
  S.user = s.user; S.perms = s.perms || [];
  showApp(); route();
}
// القفل التلقائي عند عدم الاستخدام
setInterval(async () => {
  const mins = parseInt(S.settings.idle_minutes || '0', 10);
  if (S.user && mins > 0 && Date.now() - getIdle() > mins * 60000) {
    try { await api('POST', '/api/logout', {}); } catch (e) { }
    S.user = null; lockMsg = 'تم قفل البرنامج لعدم الاستخدام. أدخل كلمة المرور للمتابعة.'; showLogin();
  }
}, 15000);
boot();
