/* GeoCrash explorer. One location -> one report: profile, when, where, why, outliers, outlook. */
const $ = s => document.querySelector(s);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const T = {ink: css('--color-ink'), ink2: css('--color-ink-2'), muted: css('--color-muted'), rule: css('--color-rule'),
  accent: css('--color-accent'), risk: css('--color-risk'), safe: css('--color-safe'), paper: css('--color-paper'),
  sev: ['', css('--color-sev-1'), css('--color-sev-2'), css('--color-sev-3'), css('--color-sev-4')]};
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const num = (v, d = 0) => v == null || Number.isNaN(v) ? '—' : Number(v).toLocaleString('en-US', {maximumFractionDigits: d, minimumFractionDigits: d});
const pct = (v, d = 0) => v == null ? '—' : num(100 * v, d) + '%';
const x = v => v == null ? '—' : num(v, 2) + '×';
const hh = h => String(h).padStart(2, '0') + ':00';
const dur = m => m == null ? '—' : m < 90 ? num(m) + ' min' : num(m / 60, 1) + ' h';
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const PRESETS = [
  ['72nd & Dodge St, Omaha NE', 41.2587, -96.0266, 1], ['The Loop, Chicago IL', 41.8837, -87.6325, 1],
  ['Downtown Dallas TX', 32.7801, -96.8003, 1], ['Midtown Manhattan NY', 40.7549, -73.9840, 1],
  ['Downtown Houston TX', 29.7604, -95.3698, 2], ['Downtown Miami FL', 25.7743, -80.1937, 2]];

Chart.defaults.font.family = css('--font-mono').split(',')[0].replace(/"/g, '');
Chart.defaults.font.size = 10;
Chart.defaults.color = T.muted;
Chart.defaults.borderColor = T.rule;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.animation.duration = 500;

// ---------------------------------------------------------------- map
const map = L.map('map', {zoomControl: false, attributionControl: true}).setView([39.5, -97], 4);
L.control.zoom({position: 'topright'}).addTo(map);
const esri = n => `https://server.arcgisonline.com/ArcGIS/rest/services/${n}/MapServer/tile/{z}/{y}/{x}`;
let bases = {
  map: L.tileLayer(esri('Canvas/World_Light_Gray_Base'), {maxZoom: 16, attribution: 'Tiles © Esri'}),  // until Google loads
  sat: L.tileLayer(esri('World_Imagery'), {maxZoom: 19, attribution: 'Imagery © Esri'}),
  traffic: null,
};
bases.map.addTo(map);
let active = 'map', G = null, KEY = '';
// Google styled tiles can't be copied by GoogleMutant, so the muted look is a CSS filter (.muted in style.css).
function setBase(b) {
  if (!bases[b]) return;
  map.removeLayer(bases[active]); bases[b].addTo(map); active = b;
  document.querySelectorAll('#basemap button').forEach(x => x.setAttribute('aria-pressed', x.dataset.b === b));
}
document.querySelectorAll('#basemap button').forEach(b => b.onclick = () => setBase(b.dataset.b));
$('#basemap [data-b=traffic]').disabled = true;

async function initGoogle() {
  const {googleMapsKey} = await (await fetch('/api/config')).json();
  if (!googleMapsKey) return;
  KEY = googleMapsKey;
  await new Promise((ok, bad) => { window.__gm = ok; const s = document.createElement('script');
    s.src = `https://maps.googleapis.com/maps/api/js?key=${KEY}&v=weekly&libraries=places,geocoding&loading=async&callback=__gm`;
    s.onerror = bad; document.head.appendChild(s); });
  G = google.maps;
  const was = active;
  map.removeLayer(bases[active]);
  bases = {map: L.gridLayer.googleMutant({type: 'roadmap', maxZoom: 21, className: 'muted'}),
    sat: L.gridLayer.googleMutant({type: 'hybrid', maxZoom: 21}),
    traffic: L.gridLayer.googleMutant({type: 'roadmap', maxZoom: 21, className: 'muted-soft'})};
  bases.traffic.addGoogleLayer('TrafficLayer');
  bases[was].addTo(map); active = was;
  $('#basemap [data-b=traffic]').disabled = false;
}
initGoogle().catch(() => {});

const layers = L.layerGroup().addTo(map), dots = L.layerGroup().addTo(map);
let ring = null, focusMark = null;

// ---------------------------------------------------------------- search
let suggs = [], sel = -1, token = null, timer = null;
function showSugg(items) {
  suggs = items; sel = -1;
  $('#sugg').innerHTML = items.map((s, i) => `<button type="button" role="option" data-i="${i}">${esc(s.main)}<small>${esc(s.sub)}</small></button>`).join('');
  $('#sugg').style.display = items.length ? 'block' : 'none';
}
$('#q').addEventListener('input', () => {
  clearTimeout(timer);
  const q = $('#q').value.trim();
  if (!G || q.length < 3) return showSugg([]);
  timer = setTimeout(async () => {
    const {AutocompleteSuggestion, AutocompleteSessionToken} = await G.importLibrary('places');
    token ||= new AutocompleteSessionToken();
    const {suggestions} = await AutocompleteSuggestion.fetchAutocompleteSuggestions({input: q, sessionToken: token, includedRegionCodes: ['us']})
      .catch(() => ({suggestions: []}));
    showSugg(suggestions.map(s => s.placePrediction).filter(Boolean).map(p => ({p, main: p.mainText?.text ?? p.text.text, sub: p.secondaryText?.text ?? ''})));
  }, 200);
});
$('#q').addEventListener('keydown', e => {
  if (!suggs.length || !['ArrowDown', 'ArrowUp'].includes(e.key)) return;
  e.preventDefault();
  sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + suggs.length) % suggs.length;
  document.querySelectorAll('#sugg button').forEach((b, i) => b.setAttribute('aria-selected', i === sel));
});
async function pick(i) {
  const s = suggs[i]; showSugg([]);
  const place = s.p.toPlace();
  await place.fetchFields({fields: ['location', 'displayName', 'formattedAddress']});
  token = null; $('#q').value = place.displayName;
  analyze(place.location.lat(), place.location.lng(), place.formattedAddress || place.displayName);
}
$('#sugg').addEventListener('click', e => { const b = e.target.closest('[data-i]'); if (b) pick(+b.dataset.i); });
$('#search').addEventListener('submit', async e => {
  e.preventDefault();
  if (sel >= 0) return pick(sel);
  if (suggs.length) return pick(0);
  const q = $('#q').value.trim(); if (!q) return;
  const hit = await geocode(q);
  if (hit) analyze(hit.lat, hit.lng, hit.name); else $('#report').innerHTML = `<div class="intro"><p class="err">No US location found for “${esc(q)}”.</p></div>`;
});
document.addEventListener('click', e => { if (!e.target.closest('.search')) showSugg([]); });
document.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#q').focus(); $('#q').select(); } });
async function geocode(q) {
  if (G) {
    const {results} = await new G.Geocoder().geocode({address: q, componentRestrictions: {country: 'US'}}).catch(() => ({results: []}));
    if (results[0]) return {lat: results[0].geometry.location.lat(), lng: results[0].geometry.location.lng(), name: results[0].formatted_address};
  }
  const r = await (await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=us&q=${encodeURIComponent(q)}`)).json();
  return r[0] ? {lat: +r[0].lat, lng: +r[0].lon, name: r[0].display_name.split(',').slice(0, 3).join(',')} : null;
}
map.on('click', e => analyze(e.latlng.lat, e.latlng.lng, `Dropped pin`));
$('#radius').onchange = () => state && analyze(state.lat, state.lng, state.name);

// ---------------------------------------------------------------- satellite thumbnails
function satURL(lat, lng) {
  if (KEY) return `https://maps.googleapis.com/maps/api/staticmap?center=${lat},${lng}&zoom=19&size=224x144&scale=2&maptype=satellite&markers=size:tiny%7Ccolor:0x2f6bff%7C${lat},${lng}&key=${KEY}`;
  const d = 0.0008, e = d * 1.4;
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${lng - e},${lat - d},${lng + e},${lat + d}&bboxSR=4326&imageSR=3857&size=224,144&format=jpg&f=image`;
}
function focusOn(lat, lng, kind) {
  map.flyTo([lat, lng], 18, {duration: 1.1});
  if (active === 'map') setBase('sat');
  if (focusMark) map.removeLayer(focusMark);
  focusMark = L.circle([lat, lng], {radius: 55, color: kind === 'o' ? T.risk : T.accent, weight: 2, fill: false}).addTo(map);
}

// ---------------------------------------------------------------- analyze
let state = null, charts = [];
async function analyze(lat, lng, name) {
  const r = +$('#radius').value;
  state = {lat, lng, name};
  $('#progress').classList.add('on');
  map.flyTo([lat, lng], Math.round(15.3 - Math.log2(r)), {duration: 1});
  if (ring) map.removeLayer(ring);
  ring = L.circle([lat, lng], {radius: r * 1000, color: T.ink, weight: 1.5, dashArray: '4 4', fill: false}).addTo(map);
  try {
    const res = await fetch(`/api/report?lat=${lat}&lng=${lng}&r=${r}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error);
    state.report = d;
    render(d, name, lat, lng, r);
  } catch (err) {
    $('#report').innerHTML = `<div class="intro"><p class="err">Couldn't build the report: ${esc(err.message)}</p></div>`;
  } finally { $('#progress').classList.remove('on'); }
}

function render(d, name, lat, lng, r) {
  charts.forEach(c => c.destroy()); charts = []; layers.clearLayers(); dots.clearLayers(); stopReplay();
  $('#report').scrollTop = 0;
  if (!d.n) {
    $('#report').innerHTML = `<div class="place"><h1>${esc(name)}</h1><div class="coords">${lat.toFixed(5)}, ${lng.toFixed(5)} · ${r} km</div></div>
      <div class="intro"><p>No recorded crashes within ${r} km. Try a larger radius.</p></div>`;
    return;
  }
  const p = d.profile;
  $('#report').innerHTML = `
    <div class="place"><h1>${esc(name)}</h1>
      <div class="coords">${lat.toFixed(5)}, ${lng.toFixed(5)} · radius ${r} km · ${num(p.rows)} records${p.sampled ? ' · outside full-coverage metros counts are ×10 estimates' : ''}</div></div>
    <nav class="index" aria-label="Report sections"><a href="#s-predict">Predict</a><a href="#s-when">When</a><a href="#s-where">Where</a><a href="#s-why">Why</a><a href="#s-odd">Outliers</a><a href="#s-dur">Disruption</a><a href="#s-next">Next 12 mo</a><a href="#s-model">Models</a></nav>
    ${figures(p)}
    ${secPredict()}
    ${secWhen(d.when, d.danger)}
    ${secWhere(d.spots, d.profile)}
    ${secWhy(d.danger, d.conditions, p)}
    ${secOdd(d.outliers)}
    ${secDur(d.conditions, d.danger, p)}
    ${secNext(d.outlook)}
    ${secModels(d.diagnostics)}`;
  drawWhen(d.when); drawWhy(d.danger); drawDur(d.conditions); drawNext(d.outlook);
  wireLists(); drawModels(d.diagnostics); modelCard(); wirePredict(); drawMap(d);
}

// ---------------------------------------------------------------- sections
function cmp(v, ref) {
  if (v == null || !ref) return '';
  const k = v / ref;
  return `<span class="${k > 1.1 ? 'up' : k < 0.9 ? 'down' : ''}">${x(k)}</span>`;
}
function figures(p) {
  const st = p.state_stats || {};
  return `<div class="figs">
    <div class="fig"><b>${num(p.per_year)}</b><span>crashes per year in radius</span></div>
    <div class="fig"><b>${num(p.density_pct)}<small style="font-size:var(--text-sm)">th</small></b><span>density percentile vs all US crash cells</span></div>
    <div class="fig"><b>${pct(p.severe_rate, 1)}</b><span>severe (level 3–4) · ${cmp(p.severe_rate, st.severe_rate)} ${esc(p.state)} · ${cmp(p.severe_rate, p.national.severe_rate)} US</span></div>
    <div class="fig"><b>${dur(p.median_duration)}</b><span>median traffic impact · 1 in 10 over ${dur(p.p90_duration)}</span></div>
  </div>`;
}

function secWhen(w, z) {
  const t = z.top_slots[0];
  const night = w.grid.map(r => r.filter((_, h) => h < 6 || h >= 20).reduce((a, b) => a + b, 0)).reduce((a, b) => a + b, 0);
  return `<section class="sec" id="s-when"><h2>When crashes happen</h2>
    <p class="finding">Busiest slot: <b>${w.peak.dow} ${hh(w.peak.hour)}</b>. Highest expected severe crashes: <b>${t.dow} ${hh(t.hour)}</b>
      (${num(t.crashes_per_year, 1)} crashes/yr, each ${x(t.p_rel)} as likely to be severe as a typical midday crash here).</p>
    <div class="row"><div class="seg" id="hm-mode" role="group" aria-label="Heatmap measure">
      <button type="button" data-m="all" aria-pressed="true">All crashes</button><button type="button" data-m="sev" aria-pressed="false">Severe</button><button type="button" data-m="model" aria-pressed="false">Model: expected severe</button></div></div>
    <div class="hm" id="hm"></div>
    <div class="scale" id="hm-scale"></div>
    <div class="grid2" style="margin-top:var(--space-lg)">
      <div><h3>Seasonality</h3><div class="chart"><canvas id="c-month"></canvas></div></div>
      <div><h3>Recorded per year</h3><div class="chart"><canvas id="c-year"></canvas></div></div>
    </div>
    <p class="note">Yearly totals track the dataset's reporting coverage, which dropped after 2019 in many areas; compare within a year, not across years.</p>
  </section>`;
}
function drawWhen(w) {
  const paint = mode => {
    const g = mode === 'all' ? w.grid : mode === 'sev' ? w.severe_grid : state.report.danger.expected_severe_grid;
    const max = Math.max(...g.flat(), 1e-9);
    let h = '<div></div>' + [...Array(24).keys()].map(i => `<div class="hr">${i % 3 ? '' : i}</div>`).join('');
    g.forEach((row, k) => {
      h += `<div class="lab">${DOW[k]}</div>` + row.map((v, i) => {
        const a = Math.round(100 * Math.sqrt(v / max));
        const label = mode === 'model' ? `${num(v * 52, 2)} severe/yr` : `${num(v, 1)} crashes`;
        return `<div class="c" title="${DOW[k]} ${hh(i)} · ${label}" style="background:color-mix(in oklch, var(--color-${mode === 'all' ? 'accent' : 'risk'}) ${a}%, var(--color-paper-2))"></div>`;
      }).join('');
    });
    $('#hm').innerHTML = h;
    $('#hm-scale').innerHTML = `0 <i style="background:linear-gradient(90deg, var(--color-paper-2), var(--color-${mode === 'all' ? 'accent' : 'risk'}))"></i> ${mode === 'model' ? num(max * 52, 2) + ' severe/yr' : num(max, 0) + (mode === 'sev' ? ' severe' : ' crashes')} · square-root scale`;
  };
  paint('all');
  document.querySelectorAll('#hm-mode button').forEach(b => b.onclick = () => {
    document.querySelectorAll('#hm-mode button').forEach(x => x.setAttribute('aria-pressed', x === b)); paint(b.dataset.m); });
  charts.push(new Chart($('#c-month'), {type: 'bar', data: {labels: MON, datasets: [{data: MON.map((_, i) => w.by_month[i + 1] || 0), backgroundColor: T.ink2, borderRadius: 2}]},
    options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, grid: {color: T.rule}}, x: {grid: {display: false}}}}}));
  const ys = Object.keys(w.by_year);
  charts.push(new Chart($('#c-year'), {type: 'bar', data: {labels: ys, datasets: [{data: ys.map(y => w.by_year[y]), backgroundColor: T.muted, borderRadius: 2}]},
    options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, grid: {color: T.rule}}, x: {grid: {display: false}}}}}));
}

function spotRow(s, i, by) {
  const hot = s.z >= 2;
  return `<li tabindex="0" data-lat="${s.lat}" data-lng="${s.lng}" data-k="s">
    <span class="no">${i + 1}</span><img class="sat" loading="lazy" alt="Satellite view of spot ${i + 1}" src="${satURL(s.lat, s.lng)}">
    <div><div class="t1">${num(s.n)} crashes · ${pct(s.severe_rate)} severe ${hot ? '<span class="up">· unusually severe</span>' : ''}</div>
      <div class="t2">${s.lat.toFixed(4)}, ${s.lng.toFixed(4)} · peak ${hh(s.peak_hour)} · ${pct(s.night_share)} at night</div>
      <div class="t3">${num(s.severe)} severe vs ${num(s.expected, 1)} expected (z ${num(s.z, 1)}) · median impact ${dur(s.median_duration)}</div></div></li>`;
}
function secWhere(sp, p) {
  const top = sp.by_risk[0], vol = sp.by_volume[0];
  const finding = top && top.z >= 2
    ? `The spot at <b>${top.lat.toFixed(4)}, ${top.lng.toFixed(4)}</b> has ${num(top.severe)} severe crashes where ${num(top.expected, 1)} were expected given its roads, weather and timing (z ${num(top.z, 1)}).`
    : `No spot is unusually severe for its conditions (all z < 2). The busiest is <b>${vol ? vol.lat.toFixed(4) + ', ' + vol.lng.toFixed(4) : '—'}</b> with ${vol ? num(vol.n) : '—'} crashes.`;
  return `<section class="sec" id="s-where"><h2>Where exactly</h2>
    <p class="finding">${finding}</p>
    <div class="row"><div class="seg" id="spot-mode" role="group" aria-label="Rank spots by"><button type="button" data-m="risk" aria-pressed="true">Worse than expected</button><button type="button" data-m="volume" aria-pressed="false">Most crashes</button></div></div>
    <ul class="ranked" id="spots">${sp.by_risk.map((s, i) => spotRow(s, i)).join('') || '<li>No spot has a severe crash.</li>'}</ul>
    <p class="note">${num(sp.cells)} ~110 m cells with ≥5 crashes. Expected severe counts come from an out-of-fold model (it never saw this area's labels). Click a row to inspect it on satellite imagery.</p>
  </section>`;
}

function secWhy(z, c, p) {
  const wx = [...z.weather].sort((a, b) => b.night - a.night)[0];
  const feats = z.features.filter(f => Math.abs(f.ratio - 1) > 0.08).sort((a, b) => b.ratio - a.ratio);
  const obs = c.weather.filter(r => r.share > 0.02);
  return `<section class="sec" id="s-why"><h2>What makes a crash here worse</h2>
    <p class="finding">Against a typical midday crash here in clear weather, <b>${wx.weather} at night</b> makes a severe outcome <b>${x(wx.night)}</b> as likely.
      ${feats.length ? `Road features matter: ${feats.slice(0, 2).map(f => `${f.feature} ${x(f.ratio)}`).join(', ')}.` : ''}</p>
    <h3>Model · relative severity risk by weather and light</h3>
    <table><thead><tr><th>Weather</th><th class="num">Day</th><th class="num">Night</th></tr></thead><tbody>
      ${z.weather.map(r => `<tr><td>${r.weather}</td><td class="num">${liftCell(r.day)}</td><td class="num">${liftCell(r.night)}</td></tr>`).join('')}</tbody></table>
    <div class="grid2" style="margin-top:var(--space-md)">
      <div><h3>Model · visibility (mi)</h3><div class="chart"><canvas id="c-vis"></canvas></div></div>
      <div><h3>Model · temperature (°F)</h3><div class="chart"><canvas id="c-temp"></canvas></div></div>
    </div>
    <h3>Model · road feature effect at this location</h3>
    <table><tbody>${z.features.map(f => `<tr><td>${f.feature}${f.present_here ? ' <span class="t2">(typical here)</span>' : ''}</td><td class="num">${liftCell(f.ratio)}</td></tr>`).join('')}</tbody></table>
    <h3>Observed · crashes here by weather</h3>
    <table><thead><tr><th>Weather</th><th class="num">Share</th><th class="num">Severe</th><th class="num">vs local</th></tr></thead><tbody>
      ${obs.map(r => `<tr><td>${r.key}</td><td class="num">${pct(r.share)}</td><td class="num">${pct(r.severe_rate)}</td><td class="num">${liftCell(r.lift)}</td></tr>`).join('')}</tbody></table>
    <h3>Observed · road features present</h3>
    <table><thead><tr><th>Feature</th><th class="num">Share</th><th class="num">Severe with</th><th class="num">without</th></tr></thead><tbody>
      ${c.roads.map(r => `<tr><td>${r.key}</td><td class="num">${pct(r.share)}</td><td class="num">${pct(r.severe_rate)}</td><td class="num">${pct(r.severe_rate_without)}</td></tr>`).join('') || '<tr><td colspan="4">None flagged</td></tr>'}</tbody></table>
    <p class="note">Model rows are partial-dependence estimates from the national gradient-boosting severity model, evaluated at this location with everything else held at the local typical value. They describe association in historical records, not causation.</p>
  </section>`;
}
const liftCell = v => v == null ? '—' : `<span class="lift ${v > 1.1 ? 'up' : v < 0.9 ? 'down' : ''}">${x(v)}</span>`;
function curve(id, c, label) {
  charts.push(new Chart($(id), {type: 'line', data: {labels: c.x, datasets: [
      {data: c.y, borderColor: T.ink, borderWidth: 1.5, pointRadius: 2, pointBackgroundColor: T.ink, tension: 0.25},
      {data: c.x.map(() => 1), borderColor: T.muted, borderDash: [3, 3], borderWidth: 1, pointRadius: 0}]},
    options: {maintainAspectRatio: false, scales: {y: {grid: {color: T.rule}, ticks: {callback: v => v.toFixed(2) + '×'}}, x: {grid: {display: false}}},
      plugins: {tooltip: {callbacks: {label: i => `${x(i.raw)} vs typical`, title: i => `${i[0].label} ${label}`}}}}}));
}
function drawWhy(z) { curve('#c-vis', z.visibility, 'mi'); curve('#c-temp', z.temperature, '°F'); }

function crashRow(o, i) {
  return `<li tabindex="0" data-lat="${o.lat}" data-lng="${o.lng}" data-k="o">
    <span class="no">${i + 1}</span><img class="sat" loading="lazy" alt="Satellite view of crash ${i + 1}" src="${satURL(o.lat, o.lng)}">
    <div><div class="t1">Severity ${o.severity} · ${dur(o.duration_min)} · ${esc(o.weather)}</div>
      <div class="t2">${o.time} · ${esc(o.city)}</div><div class="t3">${esc(o.why)}</div></div></li>`;
}
function secOdd(o) {
  const s = o.surprising_severe[0];
  return `<section class="sec band" id="s-odd"><h2>Outliers</h2>
    <p class="finding">${s ? `The most surprising severe crash (${s.time}) had a <b>${pct(s.p_severe)}</b> modelled chance of being severe.` : 'No severe crashes in this radius.'}
      The longest disruption lasted <b>${dur(o.extreme_duration[0]?.duration_min)}</b>; 1 in 100 crashes here exceeds ${dur(o.duration_p99)}.</p>
    <div class="row"><div class="seg" id="odd-mode" role="group" aria-label="Outlier type">
      <button type="button" data-m="surprising_severe" aria-pressed="true">Unexpectedly severe</button><button type="button" data-m="extreme_duration" aria-pressed="false">Longest impact</button><button type="button" data-m="multivariate" aria-pressed="false">Unusual combination</button></div></div>
    <ul class="ranked" id="odd">${o.surprising_severe.map(crashRow).join('')}</ul>
    <p class="note">“Unusual combination” is an Isolation Forest over hour, weekday, severity, duration, temperature, visibility, precipitation and light; the reason lists the two most atypical values.</p>
  </section>`;
}

function secDur(c, z, p) {
  const m = z.duration.minor, s = z.duration.severe;
  return `<section class="sec" id="s-dur"><h2>How long traffic is disrupted</h2>
    <p class="finding">Half of crashes here clear within <b>${dur(p.median_duration)}</b>; 10% run past <b>${dur(p.p90_duration)}</b>.
      For a new crash under typical conditions the model expects <b>${dur(m['0.5'])}</b> (80% range ${dur(m['0.1'])}–${dur(m['0.9'])}).</p>
    <div class="chart tall"><canvas id="c-dur"></canvas></div>
    <table style="margin-top:var(--space-md)"><thead><tr><th>Model prediction</th><th class="num">Median</th><th class="num">80% range</th></tr></thead><tbody>
      <tr><td>Level-2 crash</td><td class="num">${dur(m['0.5'])}</td><td class="num">${dur(m['0.1'])} – ${dur(m['0.9'])}</td></tr>
      <tr><td>Level-3 crash</td><td class="num">${dur(s['0.5'])}</td><td class="num">${dur(s['0.1'])} – ${dur(s['0.9'])}</td></tr></tbody></table>
    <p class="note">Duration = time from report to cleared traffic impact, as recorded by the source feeds. Quantile gradient-boosting models give the range.</p>
  </section>`;
}
function drawDur(c) {
  const e = c.duration_hist.edges, lab = e.slice(0, -1).map((v, i) => `${dur(v)}–${dur(e[i + 1])}`.replace(/ min/g, '').replace('–10080', '+'));
  charts.push(new Chart($('#c-dur'), {type: 'bar', data: {labels: e.slice(0, -1).map(v => v < 60 ? v + 'm' : v / 60 + 'h'),
    datasets: [{data: c.duration_hist.counts, backgroundColor: T.ink2, borderRadius: 2}]},
    options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, grid: {color: T.rule}}, x: {grid: {display: false}, title: {display: true, text: 'impact duration (bin start)'}}},
      plugins: {tooltip: {callbacks: {title: i => lab[i[0].dataIndex]}}}}}));
}

function secNext(f) {
  const total = f.p50.reduce((a, b) => a + b, 0), lo = f.p10.reduce((a, b) => a + b, 0), hi = f.p90.reduce((a, b) => a + b, 0);
  const b = f.backtest, wins = b.mae_model < b.mae_seasonal_naive;
  return `<section class="sec" id="s-next"><h2>Next 12 months</h2>
    <p class="finding">Expect about <b>${num(total)}</b> recorded crashes (80% range ${num(lo)}–${num(hi)}), of which roughly <b>${num(f.expected_severe_12m, 1)}</b> severe.
      Backtest on the last 12 months: model error ${num(b.mae_model, 2)} vs ${num(b.mae_seasonal_naive, 2)} for “same month last year”,
      so ${wins ? '<b>the model beats the naive baseline here</b>' : '<b>the naive baseline is as good or better at this scale</b>; treat the forecast as indicative'}.</p>
    <div class="chart tall"><canvas id="c-fc"></canvas></div>
    <p class="note">Global gradient-boosting forecaster on lagged and seasonal features (0.25° US grid panel), applied recursively from Mar 2023; band = 10–90% quantile models. Forecasts inherit the dataset's reporting coverage.</p>
  </section>`;
}
function drawNext(f) {
  const hk = Object.keys(f.history), n = hk.length, last = f.history[hk[n - 1]], pad = Array(n - 1).fill(null);
  charts.push(new Chart($('#c-fc'), {type: 'line', data: {labels: [...hk, ...f.months], datasets: [
      {data: hk.map(k => f.history[k]), borderColor: T.ink2, borderWidth: 1.2, pointRadius: 0, tension: 0.2},
      {data: [...pad, last, ...f.p90], borderColor: 'transparent', backgroundColor: 'color-mix(in oklch, ' + T.accent + ' 16%, transparent)', fill: '+1', pointRadius: 0},
      {data: [...pad, last, ...f.p10], borderColor: 'transparent', pointRadius: 0},
      {data: [...pad, last, ...f.p50], borderColor: T.accent, borderWidth: 2, pointRadius: 0, tension: 0.2}]},
    options: {maintainAspectRatio: false, scales: {x: {ticks: {maxTicksLimit: 8}, grid: {display: false}}, y: {beginAtZero: true, grid: {color: T.rule}}}}}));
}

// ---------------------------------------------------------------- predict (interactive scenario)
const SCEN_PRESETS = [
  ['Weekday rush, clear', {hour: 17, dow: 1, weather: 'clear', vis: 10, temp: 60}],
  ['Friday rush, rain', {hour: 17, dow: 4, weather: 'rain', vis: 4, temp: 50}],
  ['Saturday 2 am, fog', {hour: 2, dow: 5, weather: 'fog', vis: 0.5, temp: 45}],
  ['Winter morning, snow', {hour: 8, dow: 2, weather: 'snow', vis: 1.5, temp: 25}]];
const FEATS = [['Junction', 'Junction'], ['Traffic_Signal', 'Traffic signal'], ['Crossing', 'Crossing'], ['Stop', 'Stop sign'], ['Railway', 'Railway']];
function secPredict() {
  return `<section class="sec" id="s-predict"><h2>Predict a crash here</h2>
    <p class="finding">Set the conditions. The severity and duration models (trained on 7.7M US crashes) predict what a crash at this spot would look like, and show which of your choices moved the risk.</p>
    <div class="row" id="sc-presets">${SCEN_PRESETS.map((p, i) => `<button type="button" class="btn" data-i="${i}">${p[0]}</button>`).join('')}</div>
    <div class="controls">
      <label>Time <output id="o-hour">17:00</output><input type="range" id="sc-hour" min="0" max="23" value="17"></label>
      <label>Day <select id="sc-dow">${DOW.map((d, i) => `<option value="${i}" ${i === 4 ? 'selected' : ''}>${d}</option>`).join('')}</select></label>
      <label>Month <select id="sc-month">${MON.map((m, i) => `<option value="${i + 1}" ${i === 10 ? 'selected' : ''}>${m}</option>`).join('')}</select></label>
      <label>Visibility <output id="o-vis">10 mi</output><input type="range" id="sc-vis" min="0.25" max="10" step="0.25" value="10"></label>
      <label>Temperature <output id="o-temp">60°F</output><input type="range" id="sc-temp" min="-10" max="100" step="5" value="60"></label>
    </div>
    <div class="row"><div class="seg" id="sc-weather" role="group" aria-label="Weather">${['clear', 'cloudy', 'rain', 'snow', 'fog', 'thunder'].map((w, i) =>
      `<button type="button" data-v="${w}" aria-pressed="${i === 0}">${w}</button>`).join('')}</div></div>
    <div class="row" id="sc-feats">${FEATS.map(([k, l]) => `<label class="chk"><input type="checkbox" data-k="${k}"> ${l}</label>`).join('')}</div>
    <div id="sc-out" class="scout"><p class="note">Computing…</p></div>
  </section>`;
}
let scTimer = null;
function scParams() {
  const q = {hour: +$('#sc-hour').value, dow: +$('#sc-dow').value, month: +$('#sc-month').value, vis: +$('#sc-vis').value, temp: +$('#sc-temp').value,
    weather: document.querySelector('#sc-weather [aria-pressed=true]').dataset.v};
  document.querySelectorAll('#sc-feats input').forEach(i => q[i.dataset.k] = i.checked ? 1 : 0);
  return q;
}
function wirePredict() {
  const upd = () => { $('#o-hour').textContent = hh($('#sc-hour').value); $('#o-vis').textContent = $('#sc-vis').value + ' mi';
    $('#o-temp').textContent = $('#sc-temp').value + '°F'; clearTimeout(scTimer); scTimer = setTimeout(runScenario, 180); };
  document.querySelectorAll('#s-predict input, #s-predict select').forEach(el => el.addEventListener('input', upd));
  document.querySelectorAll('#sc-weather button').forEach(b => b.onclick = () => {
    document.querySelectorAll('#sc-weather button').forEach(x => x.setAttribute('aria-pressed', x === b)); upd(); });
  document.querySelectorAll('#sc-presets button').forEach(b => b.onclick = () => {
    const p = SCEN_PRESETS[+b.dataset.i][1];
    $('#sc-hour').value = p.hour; $('#sc-dow').value = p.dow; $('#sc-vis').value = p.vis; $('#sc-temp').value = p.temp;
    document.querySelectorAll('#sc-weather button').forEach(x => x.setAttribute('aria-pressed', x.dataset.v === p.weather)); upd(); });
  runScenario(true);
}
async function runScenario(first) {
  const params = scParams();
  if (first) FEATS.forEach(([k]) => delete params[k]);  // start from this spot's own road features
  const r = $('#radius').value, q = new URLSearchParams({lat: state.lat, lng: state.lng, r, ...params});
  let s;
  try { const res = await fetch('/api/scenario?' + q); s = await res.json(); if (!res.ok) throw new Error(s.error); }
  catch (e) { $('#sc-out').innerHTML = `<p class="err">Prediction failed: ${esc(e.message)}</p>`; return; }
  if (first) FEATS.forEach(([k]) => { const i = document.querySelector(`#sc-feats [data-k=${k}]`); i.checked = !!s.baseline[k]; });
  s.contributions = s.contributions.filter(c => Math.abs(c.pts) >= 0.05);
  const rel = s.p_severe / s.base_p_severe, maxPts = Math.max(...s.contributions.map(c => Math.abs(c.pts)), 1);
  const m2 = s.duration[2], m3 = s.duration[3];
  $('#sc-out').innerHTML = `
    <div class="figs inset">
      <div class="fig"><b>${pct(s.p_severe, 1)}</b><span>chance a crash here is severe (level 3–4)</span></div>
      <div class="fig"><b class="${rel > 1.1 ? 'up' : rel < 0.9 ? 'down' : ''}">${x(rel)}</b><span>vs this spot's typical crash (${pct(s.base_p_severe, 1)})</span></div>
      <div class="fig"><b>${x(s.p_severe / s.us_severe_rate)}</b><span>vs US average severe rate (${pct(s.us_severe_rate, 1)})</span></div>
      <div class="fig"><b>${dur(s.expected_minutes)}</b><span>expected traffic impact · level-3 crash ${dur(m3['0.1'])}–${dur(m3['0.9'])}</span></div>
    </div>
    <div class="grid2">
      <div><h3>Severity distribution</h3><div class="chart"><canvas id="c-sc"></canvas></div></div>
      <div><h3>What moved the risk (points of P(severe))</h3>
        ${s.contributions.length ? `<div class="contrib">${s.contributions.map(c => `<div class="cr"><span>${c.label}</span>
          <div class="cbar"><i class="${c.pts > 0 ? 'pos' : 'neg'}" style="width:${50 * Math.abs(c.pts) / maxPts}%"></i></div>
          <em class="${c.pts > 0 ? 'up' : 'down'}">${c.pts > 0 ? '+' : ''}${num(c.pts, 1)}</em></div>`).join('')}</div>`
          : '<p class="note">Nothing changed from this spot\'s typical crash (weekday midday, clear).</p>'}
      </div>
    </div>
    <p class="note">Baseline = this spot's typical crash: Wednesday 12:00, clear, local median temperature and visibility, local typical road features. Contributions average “add this change to the baseline” and “remove it from your scenario”, so they are attribution estimates, not exact decompositions. Severity labels drift across data sources; compare scenarios with each other rather than reading the absolute percentage as a forecast.</p>`;
  const old = charts.find(c => c.canvas.id === 'c-sc'); if (old) { old.destroy(); charts = charts.filter(c => c !== old); }
  charts.push(new Chart($('#c-sc'), {type: 'bar', data: {labels: ['Level 1', 'Level 2', 'Level 3', 'Level 4'], datasets: [
      {label: 'typical here', data: s.base_proba, backgroundColor: T.rule, borderRadius: 2},
      {label: 'your scenario', data: s.proba, backgroundColor: [1, 2, 3, 4].map(k => T.sev[k]), borderRadius: 2}]},
    options: {maintainAspectRatio: false, plugins: {legend: {display: true, position: 'bottom', labels: {boxWidth: 10}}},
      scales: {y: {beginAtZero: true, max: 1, grid: {color: T.rule}, ticks: {callback: v => Math.round(v * 100) + '%'}}, x: {grid: {display: false}}}}}));
}

// ---------------------------------------------------------------- models (diagnostics)
function secModels(g) {
  const cal = g.calibration || [], mean = a => a.reduce((s, v) => s + v, 0) / (a.length || 1);
  const predMean = mean(cal.map(c => c.pred)), over = predMean > g.base_rate * 1.3, under = predMean < g.base_rate * 0.7;
  const d = g.duration;
  return `<section class="sec" id="s-model"><h2>How the models do here</h2>
    <p class="finding">On the ${num(g.n)} crashes in this radius, the severity model ranks severe vs non-severe with <b>AUC ${g.auc == null ? '—' : num(g.auc, 2)}</b>
      (0.5 = chance) and ${over ? '<b>over-predicts</b> severity here' : under ? '<b>under-predicts</b> severity here' : 'is <b>roughly calibrated</b> here'}
      (${pct(g.base_rate, 1)} observed severe). The duration model's error is <b>${dur(d.mae_model)}</b> vs ${dur(d.mae_median)} for always guessing the local median.</p>
    <div class="grid2">
      <div><h3>Severity · predicted vs observed</h3><div class="chart"><canvas id="c-cal"></canvas></div>
        <p class="note">Crashes binned by out-of-fold predicted P(severe). On the diagonal = calibrated.</p></div>
      <div><h3>Duration · predicted vs actual (median per bin)</h3><div class="chart"><canvas id="c-dfit"></canvas></div>
        <p class="note">In-sample for the national model; these crashes were part of training.</p></div>
    </div>
    <h3>Crash types here vs US (KMeans regimes)</h3>
    <table><thead><tr><th>Regime</th><th class="num">Here</th><th class="num">US</th><th class="num">Severe here</th></tr></thead><tbody>
      ${g.regimes.map(r => `<tr><td>${esc(r.name)}</td><td class="num">${pct(r.share)}</td><td class="num">${pct(r.us)}</td><td class="num">${pct(r.severe_rate)}</td></tr>`).join('')}</tbody></table>
    <h3>What the severity model relies on (permutation importance)</h3><div class="chart tall"><canvas id="c-imp"></canvas></div>
    <p class="note">Drop in national severe-vs-not AUC when a feature is shuffled. <b>Year</b> ranks first because the dataset's severity labelling changed across its reporting sources, which is the main limit on absolute predictions.</p>
    <div id="model-card"></div>
  </section>`;
}
function drawModels(g) {
  const cal = g.calibration || [], top = Math.max(...cal.map(c => Math.max(c.pred, c.obs)), 0.05) * 1.1;
  charts.push(new Chart($('#c-cal'), {type: 'scatter', data: {datasets: [
      {data: cal.map(c => ({x: c.pred, y: c.obs})), backgroundColor: T.accent, pointRadius: cal.map(c => 3 + Math.sqrt(c.n) / 3)},
      {type: 'line', data: [{x: 0, y: 0}, {x: top, y: top}], borderColor: T.muted, borderDash: [3, 3], borderWidth: 1, pointRadius: 0}]},
    options: {maintainAspectRatio: false, scales: {x: {min: 0, max: top, title: {display: true, text: 'predicted'}, ticks: {callback: v => Math.round(v * 100) + '%'}},
      y: {min: 0, max: top, title: {display: true, text: 'observed'}, ticks: {callback: v => Math.round(v * 100) + '%'}}}}}));
  const b = g.duration.bins, dmax = Math.max(...b.map(v => Math.max(v.pred, v.obs))) * 1.1;
  charts.push(new Chart($('#c-dfit'), {type: 'scatter', data: {datasets: [
      {data: b.map(v => ({x: v.pred, y: v.obs})), backgroundColor: T.ink, pointRadius: 4},
      {type: 'line', data: [{x: 0, y: 0}, {x: dmax, y: dmax}], borderColor: T.muted, borderDash: [3, 3], borderWidth: 1, pointRadius: 0}]},
    options: {maintainAspectRatio: false, scales: {x: {min: 0, max: dmax, title: {display: true, text: 'predicted min'}}, y: {min: 0, max: dmax, title: {display: true, text: 'actual min'}}}}}));
}
async function modelCard() {
  try {
    const m = await (await fetch('/api/models')).json();
    const [s, d, f] = m.metrics, imp = m.importance.slice(0, 12);
    charts.push(new Chart($('#c-imp'), {type: 'bar', data: {labels: imp.map(i => i.feature), datasets: [{data: imp.map(i => i.auc_drop), backgroundColor: T.ink2, borderRadius: 2}]},
      options: {indexAxis: 'y', maintainAspectRatio: false, scales: {x: {grid: {color: T.rule}, title: {display: true, text: 'AUC drop'}}, y: {grid: {display: false}, ticks: {autoSkip: false}}}}}));
    $('#model-card').innerHTML = `<h3>National scorecard (future-time holdout)</h3><table><tbody>
      <tr><td>Severity classifier · gradient boosting</td><td class="num">AUC ${num(s.auc_severe, 3)}</td></tr>
      <tr><td>Duration regressor · gradient boosting + quantiles</td><td class="num">MAE ${num(d.MAE_min, 1)} min · baseline ${num(d.baseline_MAE_min, 1)}</td></tr>
      <tr><td>Monthly forecaster · 3,183 grid cells</td><td class="num">MAE ${num(f.MAE_gbm, 1)} · seasonal naive ${num(f.MAE_seasonal_naive, 1)}</td></tr>
      <tr><td>Crash regimes · KMeans, k by silhouette</td><td class="num">k = ${m.regimes.length}</td></tr></tbody></table>
      <p class="note">Trained on the earliest 80% of crashes, tested on the latest 20%. Data: US Accidents 2016–2023 (Moosavi et al.), 7.7M records; a 10% national sample plus complete coverage for Omaha, Lincoln, Chicago and Dallas.</p>`;
  } catch { $('#model-card').innerHTML = '<p class="note">Model card unavailable.</p>'; }
}

// ---------------------------------------------------------------- list interactions
function wireLists() {
  const bindRows = sel => document.querySelectorAll(sel + ' li[data-lat]').forEach(li => {
    const go = () => focusOn(+li.dataset.lat, +li.dataset.lng, li.dataset.k);
    li.onclick = go; li.onkeydown = e => { if (e.key === 'Enter') go(); };
  });
  const seg = (id, fn) => document.querySelectorAll(`#${id} button`).forEach(b => b.onclick = () => {
    document.querySelectorAll(`#${id} button`).forEach(x => x.setAttribute('aria-pressed', x === b)); fn(b.dataset.m); });
  seg('spot-mode', m => { const s = state.report.spots[m === 'risk' ? 'by_risk' : 'by_volume'];
    $('#spots').innerHTML = s.map((r, i) => spotRow(r, i)).join(''); bindRows('#spots'); drawPins(); });
  seg('odd-mode', m => { $('#odd').innerHTML = (state.report.outliers[m] || []).map(crashRow).join('') || '<li>None.</li>'; bindRows('#odd'); drawPins(); });
  bindRows('#spots'); bindRows('#odd');
}

// ---------------------------------------------------------------- map layers
let pins = L.layerGroup().addTo(map);
function drawPins() {
  pins.clearLayers();
  document.querySelectorAll('#spots li[data-lat]').forEach((li, i) => L.marker([+li.dataset.lat, +li.dataset.lng],
    {icon: L.divIcon({className: '', html: `<div class="pin">${i + 1}</div>`, iconSize: [22, 22]})}).addTo(pins));
  document.querySelectorAll('#odd li[data-lat]').forEach((li, i) => L.marker([+li.dataset.lat, +li.dataset.lng],
    {icon: L.divIcon({className: '', html: `<div class="pin o">${i + 1}</div>`, iconSize: [22, 22]})}).addTo(pins));
}
function drawMap(d) {
  L.heatLayer(d.points.map(p => [p[0], p[1], 0.35 + 0.15 * p[2]]), {radius: 12, blur: 16, minOpacity: 0.2,
    gradient: {0.2: T.sev[1], 0.5: T.accent, 0.8: T.sev[3], 1: T.risk}}).addTo(layers);
  drawPins(); setupReplay(d.points);
  $('#legend').hidden = false;
}

// ---------------------------------------------------------------- replay (month by month)
let months = [], byMonth = {}, rtimer = null;
function setupReplay(points) {
  byMonth = {}; points.forEach(p => (byMonth[p[3]] ||= []).push(p));
  months = Object.keys(byMonth).sort();
  $('#replay').hidden = !months.length; $('#scrub').max = months.length - 1; $('#scrub').value = 0; $('#month').textContent = months[0] || '—';
}
function showMonth(i) {
  $('#month').textContent = months[i]; $('#scrub').value = i;
  (byMonth[months[i]] || []).forEach(p => {
    const m = L.circleMarker([p[0], p[1]], {radius: 2 + p[2], color: T.sev[p[2]], weight: 0, fillOpacity: 0.95}).addTo(dots);
    setTimeout(() => m.setStyle({fillOpacity: 0.25}), 700);
  });
}
function stopReplay() { clearInterval(rtimer); rtimer = null; $('#play').textContent = 'Replay'; }
$('#play').onclick = () => {
  if (rtimer) return stopReplay();
  dots.clearLayers(); let i = +$('#scrub').value >= months.length - 1 ? 0 : +$('#scrub').value;
  $('#play').textContent = 'Pause';
  rtimer = setInterval(() => { showMonth(i++); if (i >= months.length) stopReplay(); }, 160);
};
$('#scrub').oninput = e => { dots.clearLayers(); showMonth(+e.target.value); };

// ---------------------------------------------------------------- empty state
$('#report').innerHTML = `<div class="intro">
  <h1>What happens on this road, and when.</h1>
  <p>Search any US address or click the map. You get the hours when crashes are most likely to be severe, the exact spots that are worse than their conditions explain, the crashes that don't fit the pattern, and what the next year looks like. Built on 7.7 million recorded crashes, 2016–2023.</p>
  <div class="presets">${PRESETS.map((p, i) => `<button type="button" data-i="${i}"><span>${p[0]}</span><span>${p[1].toFixed(3)}, ${p[2].toFixed(3)}</span></button>`).join('')}</div>
</div>`;
document.querySelectorAll('.presets button').forEach(b => b.onclick = () => {
  const p = PRESETS[+b.dataset.i]; $('#radius').value = String(p[3]); analyze(p[1], p[2], p[0]); });

// Deep-dive entry: details.html?lat=..&lng=..&r=..&name=.. opens straight into the report.
{
  const u = new URLSearchParams(location.search);
  if (u.has('lat') && u.has('lng')) {
    if (u.has('r')) $('#radius').value = u.get('r');
    analyze(+u.get('lat'), +u.get('lng'), u.get('name') || 'Selected location');
  }
}
