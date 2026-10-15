'use strict';
/* رسوم بيانية SVG بسيطة بدون مكتبات خارجية (تعمل دون إنترنت وتُطبع بشكل سليم). الزمن يسير من اليمين إلى اليسار. */
function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v))), n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}
const shortNum = n => n >= 1e6 ? (n / 1e6).toFixed(n % 1e6 ? 1 : 0).replace('.0', '') + ' م' : n >= 1e3 ? (n / 1e3).toFixed(n % 1e3 ? 1 : 0).replace('.0', '') + ' ألف' : String(n);

function barChart({ labels, series, height = 260, title = '' }) {
  const W = 920, H = height, padL = 16, padR = 70, padT = 24, padB = 46;
  const max = niceMax(Math.max(1, ...series.flatMap(s => s.values)));
  const n = labels.length, step = (W - padL - padR) / Math.max(n, 1);
  const gw = Math.min(step * 0.8, 70), bw = gw / series.length;
  const y = v => padT + (H - padT - padB) * (1 - v / max);
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const v = max * i / 4, yy = y(v);
    g += `<line x1="${padL}" x2="${W - padR}" y1="${yy}" y2="${yy}" class="ch-grid"/><text x="${W - padR + 8}" y="${yy + 4}" class="ch-ax">${shortNum(Math.round(v))}</text>`;
  }
  let bars = '';
  labels.forEach((lb, i) => {
    const cx = W - padR - (i + 0.5) * step;       // الأقدم على اليمين
    series.forEach((s, k) => {
      const v = s.values[i] || 0, h = (H - padT - padB) * v / max;
      const x = cx + gw / 2 - (k + 1) * bw;
      if (v > 0) bars += `<rect x="${x + 1}" y="${y(v)}" width="${Math.max(bw - 2, 1)}" height="${h}" rx="2" fill="${s.color}"><title>${esc(s.name)} — ${esc(lb)}: ${fmt(v)}</title></rect>`;
    });
    if (n <= 31 && (n <= 16 || i % 2 === 0) || n > 31 && i % 5 === 0) bars += `<text x="${cx}" y="${H - padB + 18}" class="ch-lb" text-anchor="middle">${esc(lb)}</text>`;
  });
  const legend = series.length > 1 || series[0].name ? `<g>${series.map((s, k) => `<rect x="${W - padR - 12 - k * 130}" y="2" width="12" height="12" rx="2" fill="${s.color}"/><text x="${W - padR - 18 - k * 130}" y="13" text-anchor="end" class="ch-ax">${esc(s.name)}</text>`).join('')}</g>` : '';
  return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}" preserveAspectRatio="xMidYMid meet">${g}${bars}${legend}<line x1="${padL}" x2="${W - padR}" y1="${H - padB}" y2="${H - padB}" class="ch-axis"/></svg></div>`;
}
