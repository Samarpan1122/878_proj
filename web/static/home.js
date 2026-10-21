/* GeoCrash home: 3D crash map + a few plain-language cards. The full report lives in details.html (Deep dive). */
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const num = (v, d = 0) => v == null ? '—' : Number(v).toLocaleString('en-US', {maximumFractionDigits: d, minimumFractionDigits: d});
const pct = (v, d = 0) => v == null ? '—' : num(100 * v, d) + '%';
const x2 = v => v == null ? '—' : num(v, 1) + '×';
const dur = m => m == null ? '—' : m < 90 ? num(m) + ' min' : num(m / 60, 1) + ' h';
const hour12 = h => `${(h % 12) || 12} ${h < 12 ? 'am' : 'pm'}`;
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const PRESETS = [['Omaha · 72nd & Dodge', 41.2587, -96.0266, 1], ['Chicago · The Loop', 41.8837, -87.6325, 1],
  ['Dallas · Downtown', 32.7801, -96.8003, 1], ['New York · Midtown', 40.7549, -73.984, 1], ['Houston · Downtown', 29.7604, -95.3698, 2],
  ['Los Angeles · I-10 / I-110', 34.0357, -118.2719, 1]];
const TRUCK = 'assets/truck.glb';  // Khronos glTF sample asset CesiumMilkTruck (CC-BY 4.0); Y-up, faces +X
const RADIUS_KM = 1.5;

// Resolve design tokens (OKLCH) to RGB for WebGL.
const probe = document.createElement('canvas').getContext('2d', {willReadFrequently: true});
function rgb(token) {
  probe.clearRect(0, 0, 1, 1);
  probe.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  probe.fillRect(0, 0, 1, 1);
  return [...probe.getImageData(0, 0, 1, 1).data.slice(0, 3)];
}
const C = {accent: rgb('--color-accent'), risk: rgb('--color-risk'), amber: rgb('--color-sev-3'), cool: rgb('--color-sev-2'),
  ink: rgb('--color-ink'), paper: rgb('--color-paper')};
const RAMP = [C.cool, C.accent, C.amber, C.risk];
const lerp = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
function ramp(t) { t = Math.max(0, Math.min(1, t)) * (RAMP.length - 1); const i = Math.min(Math.floor(t), RAMP.length - 2); return lerp(RAMP[i], RAMP[i + 1], t - i); }

// ---------------------------------------------------------------- deck.gl scene
const {Deck, TileLayer, BitmapLayer, ColumnLayer, HexagonLayer, ScenegraphLayer, PathLayer, TextLayer, ScatterplotLayer, FlyToInterpolator} = deck;
const esri = n => `https://server.arcgisonline.com/ArcGIS/rest/services/${n}/MapServer/tile/{z}/{y}/{x}`;
const BASES = {map: [esri('Canvas/World_Dark_Gray_Base'), 16], sat: [esri('World_Imagery'), 19]};  // [tile url, max native zoom]
let liveData = null, sim = null, replay = null, flying = false, base = 'map', view = {longitude: -96.5, latitude: 38.3, zoom: 3.7, pitch: 52, bearing: -12}, national = [], local = null, grow = 0, idle = true, t0 = performance.now();

function tiles([url, maxZoom], id) {
  return new TileLayer({id, data: url, minZoom: 0, maxZoom, tileSize: 256,
    renderSubLayers: p => new BitmapLayer(p, {data: null, image: p.data, bounds: [p.tile.bbox.west, p.tile.bbox.south, p.tile.bbox.east, p.tile.bbox.north]})});
}
function layers() {
  const L = [tiles(BASES[base], 'base-' + base)];
  if (!local) {
    L.push(new ColumnLayer({id: 'national', data: national, diskResolution: 6, radius: 3800, extruded: true, pickable: true,
      getPosition: c => [c[1], c[0]], getElevation: c => Math.sqrt(c[2]), elevationScale: 900 * grow,
      getFillColor: c => [...ramp((c[3] / c[2] - 0.05) / 0.45), 230], material: {ambient: 0.5, diffuse: 0.6},
      updateTriggers: {elevationScale: grow}}));
  } else {
    if (replay) return [...L, ...replayLayers()];  // close-up: just the road and the vehicles
    L.push(new HexagonLayer({id: 'local', data: local.points, radius: 45, extruded: true, pickable: true, coverage: 0.88,
      getPosition: p => [p[1], p[0]], elevationScale: 6 * grow, elevationRange: [0, 400], upperPercentile: 99,
      getColorWeight: p => (p[2] >= 3 ? 1 : 0), colorAggregation: 'MEAN', colorDomain: [0, 0.4],
      colorRange: [C.cool, C.accent, lerp(C.accent, C.amber, 0.5), C.amber, lerp(C.amber, C.risk, 0.5), C.risk],
      material: {ambient: 0.5, diffuse: 0.6}, updateTriggers: {elevationScale: grow}}));
    L.push(new PathLayer({id: 'ring', data: [{path: circle(local.lat, local.lng, local.r)}], getPath: d => d.path, getColor: [...C.paper, 200],
      getWidth: 2, widthUnits: 'pixels', getDashArray: [4, 4]}));
    L.push(new ColumnLayer({id: 'pillars', data: local.spots, diskResolution: 20, radius: 14, extruded: true, pickable: true,
      getPosition: s => [s.lng, s.lat], getElevation: 520 * grow, getFillColor: [...C.risk, 235], updateTriggers: {getElevation: grow}}));
    L.push(new TextLayer({id: 'labels', data: local.spots, getPosition: s => [s.lng, s.lat, 560 * grow], getText: (s, {index}) => String(index + 1),
      getSize: 18, getColor: [...C.paper, 255], fontFamily: 'JetBrains Mono', fontWeight: 600, background: true,
      getBackgroundColor: [...C.risk, 255], backgroundPadding: [6, 3], updateTriggers: {getPosition: grow}}));
    if (local.focus) L.push(new ColumnLayer({id: 'focus', data: [local.focus], diskResolution: 20, radius: 10, extruded: true,
      getPosition: f => [f.lng, f.lat], getElevation: 300, getFillColor: [...C.amber, 240]}));
    L.push(...simLayers(), ...replayLayers());
  }
  return L;
}
function circle(lat, lng, km) {
  return [...Array(73).keys()].map(i => { const a = (i / 72) * 2 * Math.PI;
    return [lng + (km / (111.32 * Math.cos(lat * Math.PI / 180))) * Math.cos(a), lat + (km / 110.57) * Math.sin(a)]; });
}
const deckgl = new Deck({parent: $('#deck'), initialViewState: view, controller: true, layers: [],
  onViewStateChange: ({viewState}) => { view = viewState; }, onInteractionStateChange: s => { idle = !(s.isDragging || s.isPanning || s.isRotating || s.isZooming); },
  getTooltip: ({object, layer}) => !object ? null : layer.id === 'national'
    ? {html: `<b>${num(object[2])} crashes</b><br>${pct(object[3] / object[2])} severe`, className: 'deck-tooltip'}
    : layer.id === 'local' ? {html: `<b>${object.count ?? object.points?.length} crashes</b><br>${pct(object.colorValue)} severe`, className: 'deck-tooltip'}
    : layer.id === 'pillars' ? {html: `<b>Hotspot</b><br>${num(object.n)} crashes · ${pct(object.severe_rate)} severe`, className: 'deck-tooltip'} : null});
function redraw() { deckgl.setProps({layers: layers()}); }
function animateGrow(ms = 1600) {
  const start = performance.now();
  const step = t => { grow = 1 - Math.pow(1 - Math.min((t - start) / ms, 1), 3); redraw(); if (grow < 1) requestAnimationFrame(step); };
  grow = 0; requestAnimationFrame(step);
}
// Slow orbit while idle; the truck model spins.
(function orbit() {
  if (idle && !flying && !replay && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    view = {...view, bearing: view.bearing + (local ? 0.04 : 0.025), transitionDuration: 0};
    deckgl.setProps({initialViewState: view});
    if (local) redraw();
  } else if (replay || sim) redraw();
  requestAnimationFrame(orbit);
})();
function flyTo(v, ms = 2600) {
  flying = true;
  view = {...view, ...v, transitionDuration: ms, transitionInterpolator: new FlyToInterpolator()};
  deckgl.setProps({initialViewState: view});
  setTimeout(() => { flying = false; }, ms + 50);
}
function setBase(b) { base = b; document.querySelectorAll('#basemap button').forEach(x => x.setAttribute('aria-pressed', x.dataset.b === b)); redraw(); }
document.querySelectorAll('#basemap button').forEach(b => b.onclick = () => setBase(b.dataset.b));

fetch('/api/national').then(r => r.json()).then(d => { national = d.cells; animateGrow(2200); });

// ---------------------------------------------------------------- search (Google Places when a key is configured)
let G = null, KEY = '', suggs = [], sel = -1, token = null, timer = null;
fetch('/api/config').then(r => r.json()).then(({googleMapsKey}) => {
  if (!googleMapsKey) return;
  KEY = googleMapsKey;
  window.__gm = () => { G = google.maps; };
  const s = document.createElement('script');
  s.src = `https://maps.googleapis.com/maps/api/js?key=${KEY}&v=weekly&libraries=places,geocoding&loading=async&callback=__gm`;
  document.head.appendChild(s);
});
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
    const {suggestions} = await AutocompleteSuggestion.fetchAutocompleteSuggestions({input: q, sessionToken: token, includedRegionCodes: ['us']}).catch(() => ({suggestions: []}));
    showSugg(suggestions.map(s => s.placePrediction).filter(Boolean).map(p => ({p, main: p.mainText?.text ?? p.text.text, sub: p.secondaryText?.text ?? ''})));
  }, 200);
});
$('#q').addEventListener('keydown', e => {
  if (!suggs.length || !['ArrowDown', 'ArrowUp'].includes(e.key)) return;
  e.preventDefault(); sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + suggs.length) % suggs.length;
  document.querySelectorAll('#sugg button').forEach((b, i) => b.setAttribute('aria-selected', i === sel));
});
async function pick(i) {
  const s = suggs[i]; showSugg([]);
  const place = s.p.toPlace();
  await place.fetchFields({fields: ['location', 'displayName', 'formattedAddress']});
  token = null; $('#q').value = place.displayName;
  check(place.location.lat(), place.location.lng(), place.formattedAddress || place.displayName);
}
$('#sugg').addEventListener('click', e => { const b = e.target.closest('[data-i]'); if (b) pick(+b.dataset.i); });
document.addEventListener('click', e => { if (!e.target.closest('.search')) showSugg([]); });
$('#search').addEventListener('submit', async e => {
  e.preventDefault();
  if (suggs.length) return pick(Math.max(sel, 0));
  const q = $('#q').value.trim(); if (!q) return;
  let hit = null;
  if (G) { const {results} = await new G.Geocoder().geocode({address: q, componentRestrictions: {country: 'US'}}).catch(() => ({results: []}));
    if (results[0]) hit = {lat: results[0].geometry.location.lat(), lng: results[0].geometry.location.lng(), name: results[0].formatted_address}; }
  if (!hit) { const r = await (await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=us&q=${encodeURIComponent(q)}`)).json();
    if (r[0]) hit = {lat: +r[0].lat, lng: +r[0].lon, name: r[0].display_name.split(',').slice(0, 3).join(',')}; }
  if (hit) check(hit.lat, hit.lng, hit.name); else { $('#q').value = ''; $('#q').placeholder = `No US match for “${q}”. Try another place.`; }
});
$('#presets').innerHTML = PRESETS.map((p, i) => `<button type="button" data-i="${i}">${p[0]}</button>`).join('');
$('#presets').onclick = e => { const b = e.target.closest('[data-i]'); if (b) { const p = PRESETS[+b.dataset.i]; check(p[1], p[2], p[0]); } };

// ---------------------------------------------------------------- check a location
let current = null;
async function check(lat, lng, name) {
  stopSim(); replay = null;
  $('#hero').hidden = true; $('#loading').hidden = false;
  flyTo({longitude: lng, latitude: lat, zoom: 14.2, pitch: 58, bearing: 25});
  try {
    const res = await fetch(`/api/report?lat=${lat}&lng=${lng}&r=${RADIUS_KM}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error);
    current = {lat, lng, name, d};
    const spots = (d.n ? (d.spots.by_risk.length ? d.spots.by_risk : d.spots.by_volume) : []).slice(0, 3);
    local = {lat, lng, r: RADIUS_KM, points: d.points || [], spots};
    animateGrow(1800);
    renderPanel(current);
  } catch (err) {
    $('#panel').hidden = false; $('#panel').innerHTML = `<div class="card"><h2>Couldn't analyze this place</h2><p>${esc(err.message)}</p></div>`;
  } finally { $('#loading').hidden = true; }
}

function grade(p) {
  const score = 0.6 * p.density_pct + 40 * Math.min(p.severe_rate / p.national.severe_rate, 2) / 2;
  return {score, letter: score < 25 ? 'A' : score < 45 ? 'B' : score < 60 ? 'C' : score < 75 ? 'D' : 'F'};
}
const card = (html, i) => `<div class="card" style="animation-delay:${i * 90}ms">${html}</div>`;

function renderPanel({name, d}) {
  $('#panel').hidden = false;
  if (!d.n) { $('#panel').innerHTML = card(`<h2>${esc(name)}</h2><p>No recorded crashes within ${RADIUS_KM} km.</p>`, 0); return; }
  const p = d.profile, g = grade(p), z = d.danger, w = d.when;
  const byHour = [...Array(24).keys()].map(h => w.grid.reduce((a, row) => a + row[h], 0));
  const peakH = byHour.indexOf(Math.max(...byHour)), top = z.top_slots[0];
  const risks = [...z.weather.flatMap(r => [{label: `${r.weather}, daytime`, v: r.day}, {label: `${r.weather}, at night`, v: r.night}]),
    ...z.features.map(f => ({label: `at a ${f.feature}`, v: f.ratio}))].filter(r => r.v > 1.05).sort((a, b) => b.v - a.v).slice(0, 3);
  const f = d.outlook, next = f.p50.reduce((a, b) => a + b, 0);
  const spots = local.spots;
  const sevVsUS = p.severe_rate / p.national.severe_rate;
  $('#panel').innerHTML = [
    card(`<h3>Risk grade · ${RADIUS_KM} km around</h3><h2>${esc(name)}</h2>
      <div class="grade"><div class="letter g-${g.letter}">${g.letter}</div>
      <p>Busier than <b>${num(p.density_pct)}%</b> of US crash locations. Severe crashes are <b>${sevVsUS > 1.1 ? num(sevVsUS, 1) + '× more common' : sevVsUS < 0.9 ? 'less common' : 'about as common'}</b> than the US average.</p></div>
      <div class="stats"><div><b data-count="${p.per_year}">0</b><span>crashes / year</span></div><div><b>${pct(p.severe_rate, 1)}</b><span>severe</span></div><div><b>${dur(p.median_duration)}</b><span>typical delay</span></div></div>`, 0),
    card(`<h3>Right now · live weather</h3><div id="live"><p>Fetching current conditions…</p></div>`, 1),
    card(`<h3>Most dangerous time</h3><p style="margin:0 0 10px">Crashes peak around <b>${hour12(peakH)}</b>. Severe ones are most likely <b>${top.dow} ${hour12(top.hour)}</b>.</p>
      <div class="clock">${byHour.map((v, h) => `<i class="${h === peakH ? 'peak' : ''}" data-h="${Math.max(4, 100 * v / Math.max(...byHour))}"></i>`).join('')}</div>
      <div class="clock-axis"><span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span></div>`, 1),
    risks.length ? card(`<h3>Watch out for</h3><div class="warn">${risks.map(r => `<div><span>${esc(r.label)}</span><em>${x2(r.v)}</em></div>`).join('')}</div>
      <p>How much more likely a crash here is to be severe, vs a typical midday crash (model).</p>`, 2) : '',
    spots.length ? card(`<h3>Hotspots · red pillars on the map</h3><div class="spots">${spots.map((s, i) => `<button type="button" data-i="${i}">
      <img alt="Satellite view of hotspot ${i + 1}" loading="lazy" src="${sat(s.lat, s.lng)}"><div><b>${i + 1}. ${num(s.n)} crashes · ${pct(s.severe_rate)} severe</b>
      <span>peak ${hour12(s.peak_hour)} · click to fly there</span></div></button>`).join('')}</div>
      <button class="btn primary replay-btn" id="replay" type="button">Replay a typical crash at hotspot 1 (3D)</button>`, 3) : '',
    outlierCard(d.outliers),
    card(`<h3>Next 12 months</h3><div class="big" data-count="${next}">0</div><p>expected recorded crashes (range ${num(f.p10.reduce((a, b) => a + b, 0))}–${num(f.p90.reduce((a, b) => a + b, 0))}), about <b>${num(f.expected_severe_12m, 1)}</b> severe.</p>
      ${spark(Object.values(f.history).slice(-36), f.p50)}`, 4),
    card(`<h3>Try it: if a crash happened here…</h3>
      <div class="opts">${seg('when', [['8', 'Morning rush'], ['13', 'Midday'], ['17', 'Evening rush'], ['23', 'Late night']], '17')}
      ${seg('wx', [['clear', 'Clear'], ['rain', 'Rain'], ['snow', 'Snow'], ['fog', 'Fog']], 'clear')}
      ${seg('day', [['2', 'Weekday'], ['5', 'Weekend']], '2')}</div>
      <div id="pred"><p>…</p></div>`, 5),
    card(`<div class="actions"><button class="btn primary" id="deep" type="button">Deep dive: full analysis</button><a class="btn" href="models.html">Model scores</a></div>`, 6),
  ].join('');
  requestAnimationFrame(() => {
    document.querySelectorAll('.clock i').forEach(i => i.style.height = i.dataset.h + '%');
    document.querySelectorAll('[data-count]').forEach(countUp);
  });
  document.querySelectorAll('.spots button').forEach(b => b.onclick = () => {
    const s = spots[+b.dataset.i]; flyTo({longitude: s.lng, latitude: s.lat, zoom: 17.3, pitch: 62}, 1800); });
  document.querySelectorAll('.opts .seg button').forEach(b => b.onclick = () => {
    b.parentElement.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b)); predict(); });
  wireOutliers();
  $('#deep').onclick = () => {
    $('#drawer-frame').src = `details.html?lat=${current.lat}&lng=${current.lng}&r=${RADIUS_KM}&name=${encodeURIComponent(current.name)}`;
    $('#drawer').hidden = false; };
  predict(); loadLive();
  $('#replay') && ($('#replay').onclick = () => startReplay(spots[0]));
}
$('#close-drawer').onclick = () => { $('#drawer').hidden = true; };
document.addEventListener('keydown', e => { if (e.key === 'Escape') $('#drawer').hidden = true; });

const seg = (id, opts, on) => `<div class="seg" data-k="${id}" role="group">${opts.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${v === on}">${l}</button>`).join('')}</div>`;
const val = k => document.querySelector(`.seg[data-k=${k}] [aria-pressed=true]`).dataset.v;
async function predict() {
  const wx = val('wx'), vis = {clear: 10, rain: 4, snow: 1.5, fog: 0.5}[wx];
  const q = new URLSearchParams({lat: current.lat, lng: current.lng, r: RADIUS_KM, hour: val('when'), dow: val('day'), weather: wx, vis});
  const s = await (await fetch('/api/scenario?' + q)).json();
  if (s.error) { $('#pred').innerHTML = `<p>${esc(s.error)}</p>`; return; }
  const rel = s.p_severe / s.base_p_severe;
  $('#pred').innerHTML = `<div class="result"><span class="big">${pct(s.p_severe, 0)}</span><span>chance it's severe ·
    <b class="${rel > 1.1 ? 'up' : rel < 0.9 ? 'down' : ''}">${x2(rel)}</b> vs a typical crash here</span></div>
    <div class="meter"><i style="width:0"></i></div><p>Expected traffic delay about <b>${dur(s.expected_minutes)}</b>.</p>`;
  requestAnimationFrame(() => { $('#pred .meter i').style.width = Math.min(100, 100 * s.p_severe) + '%'; });
}

function countUp(el) {
  const target = +el.dataset.count, t = performance.now();
  const step = n => { const k = Math.min((n - t) / 1000, 1); el.textContent = num(target * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
function spark(hist, fc) {
  const all = [...hist, ...fc], max = Math.max(...all, 1), W = 340, H = 56, n = all.length;
  const pt = (v, i) => `${(i / (n - 1)) * W},${H - 4 - (v / max) * (H - 8)}`;
  const h = hist.map(pt).join(' '), f = [hist.at(-1), ...fc].map((v, i) => pt(v, i + hist.length - 1)).join(' ');
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <polyline points="${h}" fill="none" stroke="var(--color-muted)" stroke-width="1.5"/>
    <polyline points="${f}" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-dasharray="4 3"/></svg>`;
}
function sat(lat, lng) {
  if (KEY) return `https://maps.googleapis.com/maps/api/staticmap?center=${lat},${lng}&zoom=19&size=192x128&scale=2&maptype=satellite&key=${KEY}`;
  const d = 0.0008, e = d * 1.5;
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${lng - e},${lat - d},${lng + e},${lat + d}&bboxSR=4326&imageSR=3857&size=192,128&format=jpg&f=image`;
}


// ---------------------------------------------------------------- live: real weather now -> predictions + simulation
async function loadLive() {
  try {
    const res = await fetch(`/api/live?lat=${current.lat}&lng=${current.lng}&r=${RADIUS_KM}`);
    liveData = await res.json(); if (!res.ok) throw new Error(liveData.error);
  } catch (e) { $('#live').innerHTML = `<p>Live conditions unavailable: ${esc(e.message)}</p>`; return; }
  const n = liveData.now, rel = n.p_severe / liveData.base_p_severe, t = new Date(n.time);
  const maxE = Math.max(...liveData.next24.map(h => h.expected), 1e-9);
  $('#live').innerHTML = `<p style="margin:0">${t.toLocaleString('en-US', {weekday: 'short', hour: 'numeric', minute: '2-digit'})} local ·
      <b>${esc(n.weather)}</b>${n.temp != null ? ` · ${num(n.temp)}°F` : ''}${n.vis_mi != null ? ` · ${num(n.vis_mi, 1)} mi visibility` : ''}</p>
    <div class="result" style="margin-top:8px"><span class="big">${pct(n.p_severe)}</span><span>chance a crash right now is severe ·
      <b class="${rel > 1.1 ? 'up' : rel < 0.9 ? 'down' : ''}">${x2(rel)}</b> vs typical</span></div>
    <p>Expected crashes in this ${RADIUS_KM} km circle: <b>${num(n.expected, 2)}</b> this hour, <b>${num(liveData.expected_24h, 1)}</b> in the next 24 h.</p>
    <div class="risk24">${liveData.next24.map(h => `<i title="${hour12(h.hour)} · ${h.weather} · ${num(h.expected, 2)} expected · ${pct(h.p_severe)} severe"
      style="height:${Math.max(6, 100 * h.expected / maxE)}%;background:rgb(${ramp((h.p_severe - 0.05) / 0.4).join(',')})"></i>`).join('')}</div>
    <div class="clock-axis"><span>now</span><span>+6h</span><span>+12h</span><span>+18h</span><span>+24h</span></div>
    <button class="btn primary" id="sim-btn" type="button" style="width:100%;margin-top:10px">Run live simulation</button>
    <div id="sim-feed" class="feed"></div>
    <p class="fine">Weather: ${esc(liveData.source)}. Crash counts use this spot's historical weekday-hour pattern × its recent volume trend. The simulation draws random crashes from those rates; they are not real incidents.</p>`;
  $('#sim-btn').onclick = () => sim ? stopSim() : startSim();
}

const SIM_TARGET_CRASHES = 15, SIM_MAX_DAYS = 365, SIM_MIN_DAYS = 7, SIM_TOTAL_MS = 30000;
let SIM_DAYS = 30, SIM_MS_PER_DAY = 1000;
function startSim() {
  const pts = local.points, perDay = liveData.next24.reduce((a, h) => a + h.expected, 0);
  SIM_DAYS = Math.min(SIM_MAX_DAYS, Math.max(SIM_MIN_DAYS, Math.ceil(SIM_TARGET_CRASHES / Math.max(perDay, 1e-6))));
  SIM_MS_PER_DAY = SIM_TOTAL_MS / SIM_DAYS;
  sim = {start: performance.now(), events: [], perHour: liveData.next24, pts, last: 0, t0: new Date(liveData.now.time), perDay};
  lastEvents = []; $('#sim-feed').innerHTML = '';
  $('#sim-btn').textContent = 'Stop simulation';
  flyTo({zoom: 14.4, pitch: 55}, 1200);
  tickSim();
}
function stopSim() { if (!sim) return; cancelAnimationFrame(sim.raf); sim = null; $('#sim-btn') && ($('#sim-btn').textContent = 'Run live simulation'); redraw(); }
function tickSim() {
  if (!sim) return;
  const simHours = Math.min(((performance.now() - sim.start) / SIM_MS_PER_DAY) * 24, SIM_DAYS * 24);
  for (let h = sim.last; h < Math.floor(simHours); h++) {
    const slot = sim.perHour[h % 24];
    let k = poisson(slot.expected);
    while (k-- > 0 && sim.pts.length) {
      const p = sim.pts[Math.floor(Math.random() * sim.pts.length)];
      const severe = Math.random() < slot.p_severe;
      const when = new Date(sim.t0.getTime() + h * 3600e3);
      sim.events.push({lat: p[0] + (Math.random() - 0.5) * 0.0004, lng: p[1] + (Math.random() - 0.5) * 0.0004, severe, born: performance.now(), when, weather: slot.weather});
      $('#sim-feed').insertAdjacentHTML('afterbegin', `<div class="${severe ? 'sev' : ''}">${when.toLocaleString('en-US', {month: 'short', day: 'numeric', hour: 'numeric'})}
        · ${severe ? 'severe crash' : 'crash'} · ${esc(slot.weather)}</div>`);
    }
  }
  sim.last = Math.floor(simHours);
  const day = Math.floor(simHours / 24) + 1, sev = sim.events.filter(e => e.severe).length;
  $('#sim-btn').textContent = simHours >= SIM_DAYS * 24 ? `Done · ${sim.events.length} simulated crashes (${sev} severe) · run again`
    : `Day ${day} of ${SIM_DAYS} · ${sim.events.length} crashes (${sev} severe) · stop`;
  if (simHours >= SIM_DAYS * 24) { const s = sim; sim = null; setTimeout(() => { $('#sim-btn').onclick = () => startSim(); }, 0); redrawEvents(s); return; }
  sim.raf = requestAnimationFrame(tickSim);
}
let lastEvents = [];
function redrawEvents(s) { lastEvents = s.events; redraw(); }
function poisson(l) { let k = 0, p = Math.exp(-l), s = p, u = Math.random(); while (u > s && k < 50) { k++; p *= l / k; s += p; } return k; }
function simLayers() {
  const ev = sim ? sim.events : lastEvents, now = performance.now();
  if (!ev.length) return [];
  return [
    new ScatterplotLayer({id: 'sim-pulse', data: ev.filter(e => now - e.born < 1500), getPosition: e => [e.lng, e.lat],
      getRadius: e => 10 + 120 * ((now - e.born) / 1500), getFillColor: e => [...(e.severe ? C.risk : C.amber), Math.round(160 * (1 - (now - e.born) / 1500))],
      updateTriggers: {getRadius: now, getFillColor: now}}),
    new ColumnLayer({id: 'sim-cols', data: ev, radius: 9, diskResolution: 12, extruded: true, getPosition: e => [e.lng, e.lat],
      getElevation: e => (e.severe ? 260 : 120) * Math.min((now - e.born) / 600, 1), getFillColor: e => [...(e.severe ? C.risk : C.amber), 230],
      updateTriggers: {getElevation: now}}),
  ];
}

// ---------------------------------------------------------------- 3D crash replay (illustrative reconstruction)
const REPLAY_MS = 5200, IMPACT_AT = 0.55, M_PER_DEG = 111320;
const VEHICLE_SCALE = 2;  // drawn at 2x so they read from the orbit camera
function startReplay(spot) {
  stopSim();
  const dz = current.d.danger.features, typical = f => dz.find(x => x.feature === f)?.present_here;
  const kind = typical('junction') || typical('traffic signal') || typical('stop') || typical('crossing') ? 'side' : 'rear';
  replay = {spot, kind, start: performance.now() + 1600};
  setBase('sat');
  flyTo({longitude: spot.lng, latitude: spot.lat, zoom: 19.2, pitch: 64, bearing: 35}, 1600);
  const o = current.d.outliers.surprising_severe[0];
  $('#replay-card')?.remove();
  document.body.insertAdjacentHTML('beforeend', `<div class="replay-card" id="replay-card"><h3>Crash replay · illustrative</h3>
    <p><b>${kind === 'side' ? 'Side impact at an intersection' : 'Rear-end collision'}</b> at hotspot 1 · ${num(spot.n)} recorded crashes, ${pct(spot.severe_rate)} severe,
    peak ${hour12(spot.peak_hour)}, typical delay ${dur(spot.median_duration)}.</p>
    ${o ? `<p>Most surprising severe crash nearby: ${esc(o.time)}, ${esc(o.weather)}, level ${o.severity}, ${dur(o.duration_min)} delay (model gave it ${pct(o.p_severe)}).</p>` : ''}
    <p class="fine">Vehicles drawn at 2× scale. The dataset records where, when, conditions and severity, not vehicle paths. The motion is a reconstruction of the most common crash type for this spot's road layout.</p>
    <div class="actions"><button class="btn" type="button" id="replay-again">Replay</button><button class="btn" type="button" id="replay-close">Close</button></div></div>`);
  $('#replay-again').onclick = () => startReplay(spot);
  $('#replay-close').onclick = () => { replay = null; $('#replay-card').remove(); flyTo({zoom: 14.2, pitch: 58}, 1400); };
}
function offset(lat, lng, east, north) { return [lng + east / (M_PER_DEG * Math.cos(lat * Math.PI / 180)), lat + north / M_PER_DEG]; }
const ease = t => 1 - Math.pow(1 - t, 2);
function replayLayers() {
  if (!replay || !window.loaders?.GLTFLoader) return [];
  const {spot: s, kind} = replay, t = Math.max(0, Math.min((performance.now() - replay.start) / REPLAY_MS, 1));
  const pre = Math.min(t / IMPACT_AT, 1), post = Math.max((t - IMPACT_AT) / (1 - IMPACT_AT), 0);
  // Car drives north into the point; truck comes from the west (side) or from behind (rear-end). After impact both slide and yaw.
  const car = kind === 'side'
    ? {pos: offset(s.lat, s.lng, 4 * ease(post), -45 * (1 - pre) + 6 * ease(post)), yaw: 0 + 55 * ease(post)}
    : {pos: offset(s.lat, s.lng, 1.5 * ease(post), -2 + 10 * ease(post)), yaw: 0 + 18 * ease(post)};
  const truck = kind === 'side'
    ? {pos: offset(s.lat, s.lng, -55 * (1 - pre) - 6 + 5 * ease(post), 0), yaw: 90 - 20 * ease(post)}
    : {pos: offset(s.lat, s.lng, 0, -70 * (1 - pre) - 9 + 4 * ease(post)), yaw: 0 - 12 * ease(post)};
  const flash = t > IMPACT_AT && t < IMPACT_AT + 0.18 ? (t - IMPACT_AT) / 0.18 : null;
  const L = [
    new ScenegraphLayer({id: 'replay-car', data: [car], scenegraph: TRUCK, loaders: [loaders.GLTFLoader], getPosition: d => d.pos,
      getOrientation: d => [0, d.yaw + 90, 90], getColor: [...C.risk, 255], sizeScale: VEHICLE_SCALE, _lighting: 'pbr', updateTriggers: {getPosition: t, getOrientation: t}}),
    new ScenegraphLayer({id: 'replay-truck', data: [truck], scenegraph: TRUCK, loaders: [loaders.GLTFLoader], getPosition: d => d.pos,
      getOrientation: d => [0, d.yaw, 90], sizeScale: VEHICLE_SCALE, _lighting: 'pbr', updateTriggers: {getPosition: t, getOrientation: t}}),
  ];
  if (flash != null) L.push(new ScatterplotLayer({id: 'impact', data: [0], getPosition: () => [s.lng, s.lat, 1], getRadius: 2 + 25 * flash,
    getFillColor: [...C.risk, Math.round(220 * (1 - flash))], updateTriggers: {getRadius: t, getFillColor: t}}));
  if (t >= 1) replay.done = true;
  return L;
}


// ---------------------------------------------------------------- outliers card
const ODD = [['surprising_severe', 'Unexpectedly severe'], ['extreme_duration', 'Longest delay'], ['multivariate', 'Unusual combination']];
function outlierCard(o) {
  if (!o) return '';
  return card(`<h3>Outliers · crashes that don't fit the pattern</h3>
    <div class="seg odd-tabs" role="group" aria-label="Outlier type">${ODD.map(([k, l], i) => `<button type="button" data-k="${k}" aria-pressed="${i === 0}">${l}</button>`).join('')}</div>
    <div class="spots" id="odd-list">${oddRows(o.surprising_severe)}</div>
    <p class="fine">Unexpectedly severe = severe crashes the model rated unlikely. Unusual combination = Isolation Forest over time, weather, severity and delay.</p>`, 4);
}
function oddRows(list) {
  return (list || []).slice(0, 4).map((o, i) => `<button type="button" data-lat="${o.lat}" data-lng="${o.lng}">
    <img alt="Satellite view of outlier ${i + 1}" loading="lazy" src="${sat(o.lat, o.lng)}"><div><b>Level ${o.severity} · ${dur(o.duration_min)} · ${esc(o.weather)}</b>
    <span>${esc(o.time)} · ${esc(o.why)}</span></div></button>`).join('') || '<p>None in this radius.</p>';
}
function wireOutliers() {
  const bind = () => document.querySelectorAll('#odd-list button').forEach(b => b.onclick = () => {
    const lat = +b.dataset.lat, lng = +b.dataset.lng;
    local.focus = {lat, lng};
    flyTo({longitude: lng, latitude: lat, zoom: 17.5, pitch: 60}, 1800); redraw(); });
  document.querySelectorAll('.odd-tabs button').forEach(b => b.onclick = () => {
    document.querySelectorAll('.odd-tabs button').forEach(x => x.setAttribute('aria-pressed', x === b));
    $('#odd-list').innerHTML = oddRows(current.d.outliers[b.dataset.k]); bind(); });
  bind();
}
