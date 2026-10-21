/* Explore-data page: renders outputs/tables/eda.json. */
const DOWN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], MONN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const SECTIONS = [['overview', 'Dataset'], ['target', 'Severity & delay'], ['time', 'When'], ['weather', 'Weather'], ['scatter', 'Scatter plots'],
  ['roads', 'Road features'], ['geo', 'Where'], ['corr', 'Correlations'], ['outliers', 'Outliers']];

fetch('/api/eda').then(r => r.json()).then(e => {
  if (e.missing) { $('#main').innerHTML = '<p class="note">EDA not generated yet. Run <code>python -m src.analysis</code>.</p>'; return; }
  $('#toc').innerHTML = SECTIONS.map(([id, t]) => `<a href="#${id}">${t}</a>`).join('');
  const F = {}, f = (k, ...a) => (F[k] = fig(...a)).html;
  const o = e.overview, miss = Object.entries(o.missing).slice(0, 14);
  const sevTotal = Object.values(e.severity).reduce((a, b) => a + b, 0);
  $('#main').innerHTML = [
    section('overview', 'The dataset', `<b>${fmt(o.rows_represented)}</b> crashes from ${o.start} to ${o.end} across ${o.states} states and ${fmt(o.cities)} cities.
      Each row is one crash with its location, start and end time, weather at the nearest station, and 12 road-feature flags. ${o.columns.length} columns after dropping free text.`,
      [f('miss', 'Missing values by column (%)', 'Wind chill and precipitation are often not reported; the models treat missing values natively.', true)]),
    section('target', 'Severity and traffic delay', `Severity is 1–4 by traffic impact. Level 2 dominates (${pctf((e.severity['2'] || 0) / sevTotal)}), so accuracy alone is misleading; that's why the models are judged on ROC-AUC, PR-AUC and macro F1.`,
      [f('sev', 'Crashes by severity'), f('sevsrc', 'Severity mix by reporting feed', 'Feeds label severity differently. This is why the feed is a model feature.'),
       f('dur', 'Traffic delay distribution (log scale)', 'Heavy right tail: most clear within an hour, a few last days.'), f('durq', 'Delay by severity (10th, 25th, median, 75th, 90th percentile, minutes)')]),
    section('time', 'When crashes happen', 'Recorded volume jumps after 2019 as feeds were added; weekday rush hours dominate, while the severe share peaks at night.',
      [f('year', 'Crashes per year'), f('sevyear', 'Severe share per year'), f('month', 'Crashes by month'), f('dow', 'Crashes by weekday'),
       f('hour', 'Crashes by hour of day'), f('sevhour', 'Severe share by hour'), `<figure class="fig wide"><figcaption>Hour × weekday (crashes)</figcaption>${heat(DOWN,
        [...Array(24).keys()].map(h => h % 3 ? '' : h), e.hour_dow, {labelW: 40})}</figure>`]),
    section('weather', 'Weather and visibility', `At night ${pctf(e.day_night.severe_night)} of crashes are severe vs ${pctf(e.day_night.severe_day)} by day.`,
      [f('wx', 'Crashes by weather'), f('sevwx', 'Severe share by weather'), f('temp', 'Temperature (°F)'), f('vis', 'Visibility (mi)'),
       f('hum', 'Humidity (%)'), f('wind', 'Wind speed (mph)'), f('sevtemp', 'Severe share by temperature band'), f('sevvis', 'Severe share by visibility band')]),
    section('scatter', 'Scatter plots', '2,500 random crashes, coloured by severity (red = level 4).',
      [f('sc1', 'Temperature vs humidity'), f('sc2', 'Visibility vs delay (log)'), f('sc3', 'Wind speed vs delay (log)'), f('sc4', 'Hour of day vs delay (log)')]),
    section('roads', 'Road features', 'Share of crashes near each feature, and the severe share with vs without it.',
      [f('rshare', 'Crashes near feature (share)'), f('rsev', 'Severe share: with vs without feature')]),
    section('geo', 'Where', 'Each dot is a crash (8,000 sampled); the dataset covers the contiguous US.',
      [f('map', 'Crash locations (longitude vs latitude)', '', true), f('states', 'Top 20 states by crashes', '', true), f('sevstate', 'Severe share, top 20 states', '', true), f('cities', 'Top 15 cities', '', true)]),
    section('corr', 'Correlations', 'Spearman rank correlation between numeric weather, time and the two targets. Weather variables are only weakly related to severity or delay; context (feed, location history) matters more.',
      [`<figure class="fig wide"><figcaption>Correlation matrix</figcaption>${heat(e.corr.cols.map(c => c.replace(/\(.*\)/, '')), e.corr.cols.map(c => c.replace(/\(.*\)/, '').slice(0, 10)),
        e.corr.matrix, {diverging: true, max: 1, showValues: true, labelW: 110})}</figure>`]),
    section('outliers', 'Outliers', 'Two views. <b>Per-variable</b>: values outside 1.5 × IQR. <b>Multivariate</b>: an Isolation Forest flags the 1% of crashes whose combination of time, weather, delay and severity is most unusual.',
      [`<figure class="fig wide"><figcaption>Per-variable outliers (IQR rule)</figcaption><div class="wrap"><table><thead><tr><th>Variable</th><th>Low outliers</th><th>High outliers</th><th>Min</th><th>1%</th><th>Median</th><th>99%</th><th>Max</th></tr></thead><tbody>
        ${Object.entries(e.outliers_iqr).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${fmt(v.low)} (${pctf(v.low / v.n)})</td><td>${fmt(v.high)} (${pctf(v.high / v.n)})</td><td>${fmt(v.min, 1)}</td><td>${fmt(v.p1, 1)}</td><td>${fmt(v.median, 1)}</td><td>${fmt(v.p99, 1)}</td><td>${fmt(v.max, 1)}</td></tr>`).join('')}</tbody></table></div></figure>`,
       f('iso', 'Isolation Forest: temperature vs log delay (red = flagged outlier)'),
       `<figure class="fig"><figcaption>Most anomalous crashes</figcaption><div class="wrap"><table><thead><tr>${e.isolation.features.concat('score').map(c => `<th>${esc(c.replace(/\(.*\)/, ''))}</th>`).join('')}</tr></thead><tbody>
        ${e.isolation.top.map(row => `<tr>${e.isolation.features.concat('score').map(c => `<td>${fmt(row[c], 2)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></figure>`]),
  ].join('');

  barC(F.miss.id, miss.map(m => m[0]), miss.map(m => m[1]), {horizontal: true, scales: {x: {title: {display: true, text: '% missing'}}, y: {grid: {display: false}}}});
  barC(F.sev.id, ['1', '2', '3', '4'], ['1', '2', '3', '4'].map(k => e.severity[k] || 0), {colors: TK.sev.slice(1), x: 'severity', y: 'crashes'});
  const srcs = Object.keys(e.severity_by_source);
  new Chart($('#' + F.sevsrc.id), {type: 'bar', data: {labels: srcs, datasets: [1, 2, 3, 4].map(k => ({label: 'Level ' + k, backgroundColor: TK.sev[k],
    data: srcs.map(s => { const t = Object.values(e.severity_by_source[s]).reduce((a, b) => a + b, 0); return (e.severity_by_source[s][k] || 0) / t; })}))},
    options: {scales: {x: {stacked: true}, y: {stacked: true, max: 1, ticks: {callback: v => v * 100 + '%'}}}, plugins: {legend: {display: true, position: 'bottom', labels: {boxWidth: 10}}}}});
  barC(F.dur.id, histLabels(e.duration_hist, v => { const m = 10 ** v; return m < 60 ? Math.round(m) + 'm' : m < 1440 ? (m / 60).toFixed(0) + 'h' : (m / 1440).toFixed(0) + 'd'; }),
    e.duration_hist.counts, {x: 'delay', y: 'crashes'});
  const dq = e.duration_by_severity, sevs = Object.keys(dq);
  new Chart($('#' + F.durq.id), {type: 'bar', data: {labels: sevs.map(s => 'Level ' + s), datasets: [
    {label: '10–90%', data: sevs.map(s => [dq[s][0], dq[s][4]]), backgroundColor: alpha(TK.accent, 0.2), borderRadius: 2, barPercentage: 0.5},
    {label: '25–75%', data: sevs.map(s => [dq[s][1], dq[s][3]]), backgroundColor: alpha(TK.accent, 0.55), borderRadius: 2, barPercentage: 0.5, grouped: false},
    {type: 'line', label: 'median', data: sevs.map(s => dq[s][2]), borderColor: TK.ink, pointRadius: 5, showLine: false}]},
    options: {scales: {y: {type: 'logarithmic', title: {display: true, text: 'minutes'}}}, plugins: {legend: {display: true, position: 'bottom', labels: {boxWidth: 10}}}}});
  const k = o => Object.keys(o), v = o => Object.values(o);
  barC(F.year.id, k(e.by_year), v(e.by_year));
  linesC(F.sevyear.id, k(e.severe_by_year), [{data: v(e.severe_by_year), color: TK.risk, points: 3}], {scales: {y: {ticks: {callback: x => Math.round(x * 100) + '%'}, beginAtZero: true}}});
  barC(F.month.id, MONN, MONN.map((_, i) => e.by_month[i + 1] || 0));
  barC(F.dow.id, DOWN, DOWN.map((_, i) => e.by_dow[i] || 0));
  barC(F.hour.id, [...Array(24).keys()], [...Array(24).keys()].map(h => e.by_hour[h] || 0), {colors: [...Array(24).keys()].map(h => (h >= 7 && h <= 9) || (h >= 16 && h <= 18) ? TK.accent : TK.ink2)});
  linesC(F.sevhour.id, [...Array(24).keys()], [{data: [...Array(24).keys()].map(h => e.severe_by_hour[h]), color: TK.risk, points: 2}], {scales: {y: {ticks: {callback: x => Math.round(x * 100) + '%'}}}});
  const wx = Object.entries(e.weather).sort((a, b) => b[1] - a[1]);
  barC(F.wx.id, wx.map(w => w[0]), wx.map(w => w[1]));
  const sw = Object.entries(e.severe_by_weather).sort((a, b) => b[1] - a[1]);
  barC(F.sevwx.id, sw.map(w => w[0]), sw.map(w => w[1]), {colors: TK.risk, scales: {y: {ticks: {callback: x => Math.round(x * 100) + '%'}}}});
  barC(F.temp.id, histLabels(e.temp_hist), e.temp_hist.counts, {x: '°F'});
  barC(F.vis.id, histLabels(e.vis_hist, x => fmt(x, 1)), e.vis_hist.counts, {x: 'miles'});
  barC(F.hum.id, histLabels(e.humidity_hist), e.humidity_hist.counts, {x: '%'});
  barC(F.wind.id, histLabels(e.wind_hist), e.wind_hist.counts, {x: 'mph'});
  barC(F.sevtemp.id, k(e.severe_by_temp), v(e.severe_by_temp), {colors: TK.risk, scales: {y: {ticks: {callback: x => Math.round(x * 100) + '%'}}}});
  barC(F.sevvis.id, k(e.severe_by_vis), v(e.severe_by_vis), {colors: TK.risk, scales: {y: {ticks: {callback: x => Math.round(x * 100) + '%'}}}});
  scatterC(F.sc1.id, bySeverity(e.scatter_temp_humidity), {x: 'temperature °F', y: 'humidity %'});
  scatterC(F.sc2.id, bySeverity(e.scatter_vis_duration), {x: 'visibility mi', y: 'delay min', ylog: true});
  scatterC(F.sc3.id, bySeverity(e.scatter_wind_duration), {x: 'wind mph', y: 'delay min', ylog: true, xmax: 50});
  scatterC(F.sc4.id, bySeverity(e.scatter_hour_duration), {x: 'hour', y: 'delay min', ylog: true});
  const rd = [...e.roads].sort((a, b) => b.share - a.share);
  barC(F.rshare.id, rd.map(r => r.flag), rd.map(r => r.share), {horizontal: true, scales: {x: {ticks: {callback: x => Math.round(x * 100) + '%'}}, y: {grid: {display: false}}}});
  const rs = rd.filter(r => r.severe_with != null);
  new Chart($('#' + F.rsev.id), {type: 'bar', data: {labels: rs.map(r => r.flag), datasets: [
    {label: 'with', data: rs.map(r => r.severe_with), backgroundColor: TK.risk, borderRadius: 2}, {label: 'without', data: rs.map(r => r.severe_without), backgroundColor: TK.muted, borderRadius: 2}]},
    options: {indexAxis: 'y', scales: {x: {ticks: {callback: x => Math.round(x * 100) + '%'}}, y: {grid: {display: false}}}, plugins: {legend: {display: true, position: 'bottom', labels: {boxWidth: 10}}}}});
  scatterC(F.map.id, bySeverity(e.geo_points, 1, 0, 2).map(g => ({...g, r: 1.2})), {x: 'longitude', y: 'latitude', xmin: -125, xmax: -66, ymin: 24, ymax: 50});
  barC(F.states.id, e.states.map(s => s.state), e.states.map(s => s.n), {horizontal: true, scales: {y: {grid: {display: false}}}});
  barC(F.sevstate.id, e.states.map(s => s.state), e.states.map(s => s.severe), {horizontal: true, colors: TK.risk, scales: {x: {ticks: {callback: x => Math.round(x * 100) + '%'}}, y: {grid: {display: false}}}});
  barC(F.cities.id, e.cities.map(c => c.city), e.cities.map(c => c.n), {horizontal: true, scales: {y: {grid: {display: false}}}});
  const iso = e.isolation.scatter;
  scatterC(F.iso.id, [{label: 'normal', data: iso.filter(p => !p[2]).map(p => ({x: p[0], y: p[1]})), color: alpha(TK.muted, 0.5), r: 1.6},
    {label: 'outlier', data: iso.filter(p => p[2]).map(p => ({x: p[0], y: p[1]})), color: TK.risk, r: 3.5}], {x: 'temperature °F', y: 'log(1 + delay min)'});
}).catch(err => { $('#main').innerHTML = `<p class="note">Could not load: ${esc(err.message)}</p>`; });
