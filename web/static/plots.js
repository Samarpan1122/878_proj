/* Shared Chart.js helpers for the EDA and Models pages. Colours come from tokens.css. */
const $ = s => document.querySelector(s);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const fmt = (v, d = 0) => v == null ? '—' : Number(v).toLocaleString('en-US', {maximumFractionDigits: d, minimumFractionDigits: d});
const pctf = v => v == null ? '—' : (100 * v).toFixed(1) + '%';
const TK = {ink: css('--color-ink'), ink2: css('--color-ink-2'), muted: css('--color-muted'), rule: css('--color-rule'), accent: css('--color-accent'),
  risk: css('--color-risk'), safe: css('--color-safe'), amber: css('--color-sev-3'), sev: ['', css('--color-sev-1'), css('--color-sev-2'), css('--color-sev-3'), css('--color-sev-4')]};
const SERIES = [TK.muted, TK.amber, TK.ink2, TK.accent, TK.risk, TK.safe];
Chart.defaults.font.family = 'JetBrains Mono'; Chart.defaults.font.size = 10; Chart.defaults.color = TK.muted;
Chart.defaults.borderColor = TK.rule; Chart.defaults.plugins.legend.display = false; Chart.defaults.maintainAspectRatio = false;
const alpha = (c, a) => `color-mix(in oklch, ${c} ${Math.round(a * 100)}%, transparent)`;
let uid = 0;
function fig(title, note = '', tall = false) {
  const id = 'c' + (++uid);
  return {id, html: `<figure class="fig"><figcaption>${esc(title)}</figcaption><div class="chart${tall ? ' tall' : ''}"><canvas id="${id}"></canvas></div>${note ? `<p class="note">${note}</p>` : ''}</figure>`};
}
const axis = (x, y) => ({x: {title: {display: !!x, text: x}, grid: {color: TK.rule}}, y: {title: {display: !!y, text: y}, grid: {color: TK.rule}, beginAtZero: true}});
function barC(id, labels, data, o = {}) {
  return new Chart($('#' + id), {type: 'bar', data: {labels, datasets: [{data, backgroundColor: o.colors || TK.ink2, borderRadius: 2}]},
    options: {indexAxis: o.horizontal ? 'y' : 'x', scales: o.scales || axis(o.x, o.y), plugins: {legend: {display: false}}}});
}
function linesC(id, labels, sets, o = {}) {
  return new Chart($('#' + id), {type: 'line', data: {labels, datasets: sets.map((s, i) => ({label: s.label, data: s.data, borderColor: s.color || SERIES[i % SERIES.length],
      backgroundColor: s.fill || 'transparent', fill: !!s.fill, borderDash: s.dash || [], borderWidth: s.width || 1.6, pointRadius: s.points ?? 0, tension: 0.2, spanGaps: true}))},
    options: {scales: o.scales || {...axis(o.x, o.y), x: {title: {display: !!o.x, text: o.x}, ticks: {maxTicksLimit: o.ticks || 12}, grid: {display: false}}},
      plugins: {legend: {display: sets.length > 1, position: 'bottom', labels: {boxWidth: 10}}}}});
}
function scatterC(id, groups, o = {}) {
  return new Chart($('#' + id), {type: 'scatter', data: {datasets: groups.map((g, i) => ({label: g.label, data: g.data, backgroundColor: g.color || SERIES[i],
      pointRadius: g.r ?? 2, showLine: !!g.line, borderColor: g.color, borderDash: g.dash || [], borderWidth: g.line ? 1.5 : 0}))},
    options: {animation: false, scales: {x: {type: o.xlog ? 'logarithmic' : 'linear', title: {display: true, text: o.x}, grid: {color: TK.rule}, min: o.xmin, max: o.xmax},
      y: {type: o.ylog ? 'logarithmic' : 'linear', title: {display: true, text: o.y}, grid: {color: TK.rule}, min: o.ymin, max: o.ymax}},
      plugins: {legend: {display: groups.length > 1 && !o.nolegend, position: 'bottom', labels: {boxWidth: 10}}}}});
}
function bySeverity(points, xi = 0, yi = 1, si = 2, sev = [1, 2, 3, 4]) {
  return sev.map(s => ({label: 'Level ' + s, data: points.filter(p => p[si] === s && p[xi] != null && p[yi] != null).map(p => ({x: p[xi], y: p[yi]})),
    color: alpha(TK.sev[s], 0.55), r: s >= 3 ? 2.6 : 1.8}));
}
function heat(rows, cols, matrix, o = {}) {
  const flat = matrix.flat().filter(v => v != null), mx = o.max ?? Math.max(...flat.map(Math.abs)), diverging = o.diverging;
  const cell = v => { if (v == null) return 'transparent'; const a = Math.min(Math.abs(v) / (mx || 1), 1);
    return `color-mix(in oklch, ${diverging && v < 0 ? TK.safe : o.color || TK.accent} ${Math.round(a * 100)}%, var(--color-paper-2))`; };
  return `<div class="heat" style="grid-template-columns:${o.labelW || 90}px repeat(${cols.length}, minmax(0, 1fr))"><div></div>${cols.map(c => `<div class="hc">${esc(c)}</div>`).join('')}
    ${matrix.map((row, i) => `<div class="hr">${esc(rows[i])}</div>${row.map((v, j) => `<div class="hv" title="${esc(rows[i])} · ${esc(cols[j])}: ${v == null ? '—' : fmt(v, o.dec ?? 2)}"
      style="background:${cell(v)}">${o.showValues ? `<span>${v == null ? '' : fmt(v, o.dec ?? 2)}</span>` : ''}</div>`).join('')}`).join('')}</div>`;
}
function section(id, title, lead, figs) {
  return `<section id="${id}"><h2>${esc(title)}</h2>${lead ? `<p class="lead">${lead}</p>` : ''}<div class="figs">${figs.join('')}</div></section>`;
}
const histLabels = (h, f = v => fmt(v, 0)) => h.edges.slice(0, -1).map(f);
