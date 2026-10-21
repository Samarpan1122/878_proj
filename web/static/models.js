/* Models page: leaderboard (outputs/tables/leaderboard.json) + diagnostic plots (model_plots.json). */
const LOWER_BETTER = /MAE|RMSE|AE \(|Log loss|WAPE|Davies/;
const OURS = /feed \+ (location )?history|Gradient boosting \(lags/;
const SEV = ['Level 1', 'Level 2', 'Level 3', 'Level 4'];
let board = null, plots = null, proto = 'future', charts = [];

function table(rows) {
  const cols = [...new Set(rows.flatMap(r => Object.keys(r)))].filter(c => c !== 'model');
  const best = Object.fromEntries(cols.map(c => { const v = rows.map(r => r[c]).filter(v => v != null);
    return [c, LOWER_BETTER.test(c) ? Math.min(...v) : Math.max(...v)]; }));
  return `<div class="wrap"><table><thead><tr><th>Model</th>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>
    ${rows.map(r => `<tr class="${OURS.test(r.model) ? 'ours' : ''}"><td>${esc(r.model)}${OURS.test(r.model) ? '<span class="pill">used on site</span>' : ''}</td>
      ${cols.map(c => `<td class="${r[c] === best[c] ? 'best' : ''}">${r[c] == null ? '—' : (+r[c]).toFixed(Math.abs(r[c]) >= 100 ? 1 : 3)}</td>`).join('')}</tr>`).join('')}
  </tbody></table></div>`;
}
const pctAxis = {ticks: {callback: v => Math.round(v * 100) + '%'}};
const block = (html) => `<figure class="fig wide">${html}</figure>`;

function render() {
  charts.forEach(c => c.destroy()); charts = [];
  const t = board?.tasks || {}, p = plots || {}, F = {}, f = (k, ...a) => (F[k] = fig(...a)).html;
  const c = p.classification, r = p.regression, ts = p.timeseries, cl = p.clustering;
  const names = c ? Object.keys(c.roc) : [];
  let h = '';
  if (t.severity) h += section('m-cls', 'Classification · crash severity',
    `Predict severity 1–4 from time, weather, road features, location, and (best model) the reporting feed plus the area's crash history. Most crashes are level 2, so look at ROC-AUC, PR-AUC and macro F1 rather than accuracy. ${proto === 'future' ? 'Future test: train on the earliest 80%, test on the latest 20%.' : 'Random 80/20 split.'}`,
    [block(table(t.severity[proto])),
     ...(c ? [f('roc', 'ROC curves · severe vs not (future test)'), f('pr', 'Precision–recall curves · severe vs not'),
       f('cal', 'Calibration · predicted vs observed severe rate', 'On the diagonal = well calibrated.'), f('pcl', 'Per-class F1 by model'),
       ...names.slice(-2).map(n => `<figure class="fig"><figcaption>Confusion matrix · ${esc(n)} (row-normalised)</figcaption>${heat(SEV, SEV, c.confusion[n], {max: 1, showValues: true, labelW: 60})}</figure>`),
       f('imp', 'Feature importance · drop in ROC-AUC when shuffled', 'Year ranks high because severity labelling drifted across reporting feeds.', true)] : [])]);
  if (t.duration) h += section('m-reg', 'Regression · traffic delay',
    'Predict how long traffic is disrupted (minutes, modelled on a log scale). R² = share of variation explained (1 perfect, 0 = predicting the average).',
    [block(table(t.duration[proto])),
     ...(r ? [f('rsc', 'Predicted vs actual delay · best model (log–log)', 'Points on the dashed line are perfect predictions.'), f('rres', 'Residuals vs prediction · best model (log scale)'),
       f('rhist', 'Residual distribution by model (log minutes)'), f('rsev', 'Mean absolute error by severity (minutes)'),
       block(`<p class="lead" style="margin:0">80% prediction interval (quantile gradient boosting) covers <b>${pctf(r.interval_coverage)}</b> of real delays (target 80%); median interval width ${fmt(r.interval_width_median_min)} min.</p>`)] : [])]);
  if (t.forecast) h += section('m-ts', 'Time series · monthly crash forecasting',
    `One-step-ahead forecasts of monthly crashes for ${fmt(t.forecast.cells)} grid cells (~25 km), tested on the final 12 months (Mar 2022 – Feb 2023). Gradient boosting on lags (1, 2, 3, 6, 12 months), rolling means and seasonality vs naive baselines.`,
    [block(table(t.forecast.future)),
     ...(ts ? [f('tsn', 'National total · actual vs forecast', 'Grey = history, dots = test months.', true), ...ts.series.map((s, i) => f('ts' + i, 'Grid cell ' + s.cell)),
       f('tserr', 'Forecast error distribution (crashes per cell-month)'), f('tssc', 'Predicted vs actual (cell-months)')] : [])]);
  if (t.clustering) h += section('m-clu', 'Clustering · crash types',
    `Unsupervised grouping of crashes by time of day, light, weather, road features, severity and delay. ${cl ? `KMeans with k = ${cl.k} (chosen by silhouette between 4 and 8).` : ''}`,
    [block(table(t.clustering)),
     ...(cl ? [f('elbow', 'Elbow · inertia by k'), f('sil', 'Silhouette by k'), f('pca', `Clusters in 2D (PCA, ${pctf(cl.pca_var[0] + cl.pca_var[1])} of variance)`, '', true),
       f('csize', 'Cluster size and severe rate', '', true),
       block(`<figcaption>Cluster profiles · standardised feature means (blue high, green low)</figcaption>${heat(cl.profile.centers.map((_, i) => 'Cluster ' + i),
         cl.profile.features.map(x => x.replace(/\(.*\)/, '').replace('wx_', '')), cl.profile.centers, {diverging: true, showValues: true, labelW: 70, dec: 1})}`)] : [])]);
  if (t.metro_ablation) {
    const m = t.metro_ablation.filter(x => x.task === 'severity' && x.protocol === (proto === 'future' ? 'temporal' : 'spatial_cv'));
    const d = t.metro_ablation.filter(x => x.task === 'duration' && x.protocol === (proto === 'future' ? 'temporal' : 'spatial_cv'));
    h += section('m-omaha-archive', 'Omaha study · archived original scores',
      `Original 26,480-incident experiment, retained for comparison. ${proto === 'future' ? 'Time-ordered 80/20 test.' : 'All-time spatial cross-validation (held-out 2 km blocks).'} These runs use duplicated road-density geometry and retrospective imagery. E includes earlier test outcomes in temporal evaluation and held-out outcomes in spatial training features. The corrected comparison above rebuilds those features within each training partition.`,
      [block(table(m.map(x => ({model: x.features.replace(/_/g, ' '), 'Balanced accuracy': x.balanced_accuracy, 'Macro F1': x.macro_f1, 'Accuracy': x.accuracy})))),
       block(table(d.map(x => ({model: x.features.replace(/_/g, ' '), 'MAE (min)': x.MAE_min, 'RMSE (min)': x.RMSE_min, 'R² (log minutes)': x.R2_log}))))]);
  }
  $('#main').innerHTML = h || '<p class="note">Nothing generated yet.</p>';
  draw(F, c, r, ts, cl);
}

function draw(F, c, r, ts, cl) {
  const push = x => charts.push(x);
  if (c && F.roc) {
    const names = Object.keys(c.roc);
    push(scatterC(F.roc.id, [...names.map((n, i) => ({label: n, data: c.roc[n].map(([x, y]) => ({x, y})), line: true, r: 0, color: SERIES[i]})),
      {label: 'chance', data: [{x: 0, y: 0}, {x: 1, y: 1}], line: true, r: 0, color: TK.rule, dash: [4, 4]}], {x: 'false positive rate', y: 'true positive rate', xmin: 0, xmax: 1, ymin: 0, ymax: 1}));
    push(scatterC(F.pr.id, names.map((n, i) => ({label: n, data: c.pr[n].map(([x, y]) => ({x, y})), line: true, r: 0, color: SERIES[i]})), {x: 'recall', y: 'precision', xmin: 0, xmax: 1, ymin: 0, ymax: 1}));
    const mx = Math.max(...names.flatMap(n => c.calibration[n].flat())) * 1.05;
    push(scatterC(F.cal.id, [...names.map((n, i) => ({label: n, data: c.calibration[n].map(([x, y]) => ({x, y})), line: true, r: 3, color: SERIES[i]})),
      {label: 'perfect', data: [{x: 0, y: 0}, {x: mx, y: mx}], line: true, r: 0, color: TK.rule, dash: [4, 4]}], {x: 'predicted P(severe)', y: 'observed severe rate', xmin: 0, xmax: mx, ymin: 0, ymax: mx}));
    push(new Chart($('#' + F.pcl.id), {type: 'bar', data: {labels: SEV, datasets: names.map((n, i) => ({label: n, data: c.per_class[n].f1, backgroundColor: SERIES[i], borderRadius: 2}))},
      options: {scales: {y: {max: 1, title: {display: true, text: 'F1'}}}, plugins: {legend: {display: true, position: 'bottom', labels: {boxWidth: 10}}}}}));
    fetch('/api/models').then(x => x.json()).then(m => { const imp = m.importance.slice(0, 14);
      push(barC(F.imp.id, imp.map(i => i.feature), imp.map(i => i.auc_drop), {horizontal: true, scales: {x: {title: {display: true, text: 'ROC-AUC drop'}}, y: {grid: {display: false}, ticks: {autoSkip: false}}}})); });
  }
  if (r && F.rsc) {
    const best = Object.keys(r.scatter).at(-1);
    push(scatterC(F.rsc.id, [...bySeverity(r.scatter[best].map(p => [Math.max(p[0], 1), Math.max(p[1], 1), p[2]])),
      {label: 'perfect', data: [{x: 1, y: 1}, {x: 10000, y: 10000}], line: true, r: 0, color: TK.ink, dash: [4, 4]}], {x: 'predicted minutes', y: 'actual minutes', xlog: true, ylog: true, xmin: 5, xmax: 3000, ymin: 1, ymax: 10000}));
    push(scatterC(F.rres.id, [{label: 'residual', data: r.residual_vs_pred.map(([x, y]) => ({x, y})), color: alpha(TK.accent, 0.4), r: 1.6},
      {label: 'zero', data: [{x: 2, y: 0}, {x: 8, y: 0}], line: true, r: 0, color: TK.ink, dash: [4, 4]}], {x: 'predicted log(1+min)', y: 'actual − predicted', nolegend: true}));
    const ns = Object.keys(r.residual_hist), h0 = r.residual_hist[ns[0]];
    push(linesC(F.rhist.id, histLabels(h0, x => fmt(x, 1)), ns.map((n, i) => ({label: n, data: r.residual_hist[n].counts, color: SERIES[i]})), {x: 'residual (log minutes)', ticks: 9}));
    push(new Chart($('#' + F.rsev.id), {type: 'bar', data: {labels: SEV, datasets: ns.map((n, i) => ({label: n, data: [1, 2, 3, 4].map(s => r.mae_by_severity[n][s]), backgroundColor: SERIES[i], borderRadius: 2}))},
      options: {scales: {y: {title: {display: true, text: 'MAE (min)'}}}, plugins: {legend: {display: true, position: 'bottom', labels: {boxWidth: 10}}}}}));
  }
  if (ts && F.tsn) {
    const n = ts.national, pad = n.months.map(m => n.test_months.includes(m) ? undefined : null), at = (arr) => n.months.map(m => { const i = n.test_months.indexOf(m); return i < 0 ? null : arr[i]; });
    push(linesC(F.tsn.id, n.months, [{label: 'actual', data: n.actual, color: TK.muted}, {label: 'gradient boosting', data: at(n.gbm), color: TK.accent, points: 3, width: 2},
      {label: 'seasonal naive', data: at(n.naive), color: TK.amber, points: 3, dash: [4, 3]}], {ticks: 14}));
    ts.series.forEach((s, i) => { const at2 = arr => s.months.map(m => { const j = s.test_months.indexOf(m); return j < 0 ? null : arr[j]; });
      push(linesC(F['ts' + i].id, s.months, [{label: 'actual', data: s.actual, color: TK.muted}, {label: 'gradient boosting', data: at2(s.gbm), color: TK.accent, points: 2, width: 2},
        {label: 'seasonal naive', data: at2(s.naive), color: TK.amber, points: 2, dash: [4, 3]}], {ticks: 8})); });
    push(linesC(F.tserr.id, histLabels(ts.error_hist.gbm), [{label: 'gradient boosting', data: ts.error_hist.gbm.counts, color: TK.accent}, {label: 'seasonal naive', data: ts.error_hist.naive.counts, color: TK.amber}], {x: 'forecast − actual'}));
    const mx = Math.max(...ts.scatter.flat());
    push(scatterC(F.tssc.id, [{label: 'cell-month', data: ts.scatter.map(([x, y]) => ({x: x + 1, y: y + 1})), color: alpha(TK.accent, 0.4), r: 1.8},
      {label: 'perfect', data: [{x: 1, y: 1}, {x: mx, y: mx}], line: true, r: 0, color: TK.ink, dash: [4, 4]}], {x: 'predicted + 1', y: 'actual + 1', xlog: true, ylog: true, nolegend: true}));
  }
  if (cl && F.elbow) {
    push(linesC(F.elbow.id, cl.elbow.map(e => e.k), [{data: cl.elbow.map(e => e.inertia), color: TK.ink2, points: 3}], {x: 'k'}));
    push(linesC(F.sil.id, cl.elbow.map(e => e.k), [{data: cl.elbow.map(e => e.silhouette), color: TK.accent, points: 4}], {x: 'k'}));
    const K = cl.sizes.length, pal = k => `oklch(62% 0.15 ${(k * 360 / K + 250) % 360})`;
    push(scatterC(F.pca.id, [...Array(K).keys()].map(k => ({label: 'Cluster ' + k, data: cl.pca_scatter.filter(p => p[2] === k).map(p => ({x: p[0], y: p[1]})), color: pal(k), r: 1.6})), {x: 'PC 1', y: 'PC 2'}));
    push(new Chart($('#' + F.csize.id), {type: 'bar', data: {labels: cl.sizes.map((_, i) => 'Cluster ' + i), datasets: [
      {label: 'share of crashes', data: cl.sizes, backgroundColor: cl.sizes.map((_, i) => pal(i)), borderRadius: 2},
      {label: 'severe rate', data: cl.severe_rate, backgroundColor: TK.risk, borderRadius: 2}]},
      options: {scales: {y: pctAxis}, plugins: {legend: {display: true, position: 'bottom', labels: {boxWidth: 10}}}}}));
  }
}

document.querySelectorAll('#proto button').forEach(b => b.onclick = () => {
  proto = b.dataset.p; document.querySelectorAll('#proto button').forEach(x => x.setAttribute('aria-pressed', x === b)); render(); });
Promise.all([fetch('/api/leaderboard').then(x => x.json()), fetch('/api/model-plots').then(x => x.json())])
  .then(([b, p]) => { board = b; plots = p.missing ? null : p; render(); })
  .catch(err => { $('#main').innerHTML = `<p class="note">Could not load: ${esc(err.message)}</p>`; });
