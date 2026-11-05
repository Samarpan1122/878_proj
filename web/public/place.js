'use strict';
// Place checks: find any US place, then pin every FARS fatal crash within a radius on satellite imagery with full details.
(() => {
  const M = window.GeoCrash;
  if (!M) return;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = value => Number(value).toLocaleString('en-US');
  const SPOTS = [['Omaha','72nd & Dodge',41.2587,-96.0266],['Chicago','The Loop',41.8837,-87.6325],['Dallas','Downtown',32.7801,-96.8003],
    ['New York','Midtown',40.7549,-73.984],['Los Angeles','I-10 / I-110',34.0357,-118.2719]];
  const RADII = [1,3,5,10,25], DEFAULT_RADIUS = 3;
  const LAT_LNG = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;
  let key = '', maps = null, current = null, result = null, selected = null, ticket = 0;
  let suggestions = [], active = -1, session = null, timer = null;

  // ---------------------------------------------------------------- formatting
  const DATE = new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', year:'numeric'});
  function when(c) {
    const date = DATE.format(new Date(c.year, c.month - 1, c.day));
    if (c.hour == null) return `${date} · time unknown`;
    const clock = `${(c.hour % 12) || 12}${c.minute == null ? '' : ':' + String(c.minute).padStart(2, '0')} ${c.hour < 12 ? 'am' : 'pm'}`;
    return `${date} · ${clock}`;
  }
  const roadOf = c => [c.road, c.road2].filter(Boolean).join(' & ') || 'Road not recorded';
  const killed = c => `${c.fatals} ${c.fatals === 1 ? 'death' : 'deaths'}`;
  const yesNo = value => value == null ? null : value ? 'Yes' : 'No';
  const minutes = value => value == null ? null : `${value} min after the crash`;
  // FARS spells the no-vehicle-collision code as a full sentence; show it the way people say it.
  const collisionOf = c => c.collision?.startsWith('The First Harmful Event was Not a Collision') ? 'Not a collision with another vehicle' : c.collision;
  const FIELDS = [
    ['Day of week', c => c.day_week], ['City', c => c.city], ['County', c => c.county], ['State', c => c.state],
    ['Road', c => c.road], ['Cross road', c => c.road2], ['Route type', c => c.route], ['Road class', c => c.func_sys], ['Area', c => c.area],
    ['First harmful event', c => c.first_event], ['Manner of collision', c => collisionOf(c)], ['Junction', c => c.junction],
    ['Intersection', c => c.intersection], ['Position on road', c => c.relation], ['Work zone', c => c.work_zone],
    ['Light', c => c.light], ['Weather', c => c.weather],
    ['Deaths', c => c.fatals], ['People involved', c => c.persons], ['Pedestrians', c => c.peds], ['Vehicles', c => c.vehicles],
    ['Speeding involved', c => yesNo(c.speeding)], ['Drinking driver', c => yesNo(c.drinking)], ['Hit and run', c => yesNo(c.hit_run)], ['Rollover', c => yesNo(c.rollover)],
    ['EMS notified', c => minutes(c.ems_notify_min)], ['EMS arrived', c => minutes(c.ems_arrive_min)],
    ['Coordinates', c => `${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`], ['Distance from search point', c => c.distance_km == null ? null : `${c.distance_km} km`]
  ];

  // ---------------------------------------------------------------- satellite thumbnails
  function satelliteUrl(lat, lng, width, height, metersTall) {
    // ponytail: thumbnails stay on free Esri imagery; Google (billed per image) is used for search only.
    const dLat = metersTall / 2 / 110574, dLng = dLat * (width / height) / Math.cos(lat * Math.PI / 180);
    return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${lng - dLng},${lat - dLat},${lng + dLng},${lat + dLat}&bboxSR=4326&imageSR=3857&size=${width * 2},${height * 2}&format=jpg&f=image`;
  }
  const satellite = (c, width, height, metersTall, alt, extra = '') =>
    `<span class="sat ${extra}"><img src="${esc(satelliteUrl(c.lat, c.lng, width, height, metersTall))}" alt="${esc(alt)}" loading="lazy"><i class="sat-pin" aria-hidden="true"></i></span>`;

  // ---------------------------------------------------------------- map layers (drawn by home.js while a place is active)
  function circle(lat, lng, km) {
    return Array.from({length: 73}, (_, i) => { const a = i / 72 * 2 * Math.PI;
      return [lng + km / (111.32 * Math.cos(lat * Math.PI / 180)) * Math.cos(a), lat + km / 110.574 * Math.sin(a)]; });
  }
  function layers() {
    if (!current) return [];
    return [
      new deck.PathLayer({id: 'place-ring', data: [circle(current.lat, current.lng, current.r)], getPath: d => d, getColor: [255, 255, 255, 245],
        getWidth: 3, widthUnits: 'pixels', getDashArray: [8, 6], dashJustified: true, extensions: [new deck.PathStyleExtension({dash: true})]}),
      new deck.ScatterplotLayer({id: 'place-crashes', data: result?.crashes || [], pickable: true, stroked: true, getPosition: c => [c.lng, c.lat],
        getRadius: c => 22 + 8 * Math.min(c.fatals, 5), radiusMinPixels: 7, radiusMaxPixels: 18,
        getFillColor: c => c.fatals > 1 ? [255, 64, 48, 235] : [255, 128, 40, 230], getLineColor: [255, 255, 255, 240], lineWidthMinPixels: 1.5,
        onClick: ({object}) => object && showDetail(object)}),
      new deck.ScatterplotLayer({id: 'place-selected', data: selected ? [selected] : [], pickable: true, stroked: true, getPosition: c => [c.lng, c.lat],
        getRadius: 60, radiusMinPixels: 12, radiusMaxPixels: 24, getFillColor: [255, 214, 10, 255], getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 2.5,
        onClick: ({object}) => object && showDetail(object)}),
      new deck.ScatterplotLayer({id: 'place-center', data: [current], pickable: true, stroked: true, getPosition: p => [p.lng, p.lat], getRadius: 7,
        radiusUnits: 'pixels', getFillColor: [255, 255, 255, 255], getLineColor: [37, 92, 242, 255], lineWidthUnits: 'pixels', getLineWidth: 3})
    ];
  }
  const clearChips = () => document.querySelectorAll('#presets button').forEach(b => b.setAttribute('aria-pressed', 'false'));
  const tooltip = object => ({text: object === current ? current.name : `${when(object)}\n${killed(object)} · ${roadOf(object)}`, className: 'deck-tooltip'});
  function zoomFor(radiusKm, lat) {
    const fit = Math.log2(156543 * Math.cos(lat * Math.PI / 180) / (4 * radiusKm)) - (innerWidth < 761 ? 1.1 : .5);
    return Math.max(8, Math.min(16.5, fit));
  }

  // ---------------------------------------------------------------- place check
  async function checkPlace(lat, lng, name, radius = current?.r || DEFAULT_RADIUS) {
    const mine = ++ticket;
    current = {lat, lng, name, r: radius}; result = null; selected = null;
    M.enterPlace({layers, tooltip, onExit: resetPlace, credit: '',
      onMapClick: (la, ln) => { clearChips(); checkPlace(la, ln, `Dropped pin · ${la.toFixed(4)}, ${ln.toFixed(4)}`); }});
    M.fly({longitude: lng, latitude: lat, zoom: zoomFor(radius, lat), pitch: 40, bearing: 0, maxZoom: 18});
    showView(`<p class="place-loading" role="status">Finding fatal crashes near ${esc(name)}…</p>`);
    $('view-status').textContent = `Checking ${name}…`;
    try {
      const data = await M.request('/api/public/crashes?' + new URLSearchParams({lat: lat.toFixed(5), lng: lng.toFixed(5), r: radius}));
      if (mine !== ticket) return;
      result = data; M.redraw(); renderList();
      $('view-status').textContent = `NHTSA FARS · ${data.years} · ${fmt(data.total)} fatal crashes within ${radius} km of ${name}`;
    } catch (error) {
      if (mine !== ticket) return;
      $('view-status').textContent = 'Crash records unavailable · choose Try again';
      showView(`${head()}<p class="place-error" role="alert">Crash records could not load. ${esc(error.message)}</p>
        <button type="button" class="place-button" data-action="retry">Try again</button>${foot()}`);
    }
  }
  function resetPlace() {
    ticket++; current = null; result = null; selected = null;
    $('place-view').hidden = true; $('place-view').replaceChildren(); $('state-view').hidden = false;
    $('panel').setAttribute('aria-label', 'Selected geography summary');
    clearChips();
    $('view-status').textContent = 'NHTSA FARS · 2021–2024 · historical data';
  }
  function showView(html) {
    $('state-view').hidden = true; $('place-view').hidden = false; $('place-view').innerHTML = html;
    $('panel').setAttribute('aria-label', 'Fatal crashes near the checked place'); $('panel').scrollTop = 0;
  }
  const head = () => `<div class="place-head"><p class="panel-kicker">FATAL CRASHES NEAR</p><h2>${esc(current.name)}</h2>
    <label class="radius">Radius <select id="place-radius">${RADII.map(r => `<option value="${r}"${r === current.r ? ' selected' : ''}>${r} km</option>`).join('')}</select></label></div>`;
  const foot = () => `<p class="panel-note">NHTSA FARS · fatal crashes only. Pins are police-reported crash coordinates; counts are not adjusted for traffic volume. Zoom in and click the map to check another spot.</p>
    <button type="button" class="place-exit" data-action="exit">Exit place view</button>`;

  function renderList() {
    const data = result, s = data.summary || {}, byYear = Object.entries(s.by_year || {});
    const max = Math.max(1, ...byYear.map(([, n]) => n)), perYear = data.total / Math.max(1, byYear.length);
    const facts = [['with_pedestrians', 'involved pedestrians'], ['speeding', 'speeding-related'], ['drinking', 'drinking driver'], ['dark', 'in the dark']];
    showView(`${head()}
      <div class="count">${fmt(data.total)}</div><p class="count-caption">fatal crashes within ${current.r} km · ${esc(data.years)}</p>
      <div class="stats"><div><strong>${fmt(s.fatalities ?? 0)}</strong><span>people killed</span></div><div><strong>${perYear.toFixed(1)}</strong><span>fatal crashes per year</span></div></div>
      <ul class="facts">${facts.map(([k, label]) => `<li><b>${fmt(s[k] ?? 0)}</b> ${label}</li>`).join('')}</ul>
      ${byYear.length ? `<div class="years" role="img" aria-label="Fatal crashes by year: ${byYear.map(([y, n]) => `${esc(y)} ${n}`).join(', ')}">${byYear.map(([y, n]) =>
        `<div><b>${fmt(n)}</b><i style="height:${Math.max(4, Math.round(100 * n / max))}%"></i><span>${esc(y)}</span></div>`).join('')}</div>` : ''}
      ${data.truncated ? `<p class="place-note">Showing the 500 nearest of ${fmt(data.total)}, newest first.</p>` : ''}
      ${data.crashes.length ? `<ol class="crash-list">${data.crashes.map(row).join('')}</ol>`
        : '<p class="place-note">No fatal crashes with recorded coordinates in this radius, 2021–2024. Try a larger radius.</p>'}
      ${foot()}`);
  }
  const row = c => `<li><button type="button" data-id="${esc(c.id)}">${satellite(c, 96, 64, 160, '')}
    <span><b>${esc(when(c))}</b><span>${esc(killed(c))} · ${esc(roadOf(c))}</span><small>${esc(collisionOf(c) || c.first_event || '')}</small></span></button></li>`;

  function showDetail(c) {
    selected = c; M.redraw();
    const facts = FIELDS.map(([label, get]) => [label, get(c)]).filter(([, value]) => value != null && value !== '');
    const place = [c.city, c.county].filter(Boolean).join(', ');
    showView(`<button type="button" class="place-back" data-action="back">← Back to list</button>
      ${satellite(c, 560, 300, 320, `Satellite view of the crash location at ${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`, 'sat-large')}
      <p class="panel-kicker">FATAL CRASH${c.state ? ' · ' + esc(c.state.toUpperCase()) : ''}</p><h2>${esc(when(c))}</h2>
      <p class="detail-lead">${esc(killed(c))} · ${esc(roadOf(c))}${place ? ' · ' + esc(place) : ''}</p>
      <button type="button" class="place-button" data-action="fly">Fly here</button>
      <dl class="crash-facts">${facts.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>
      ${vehicles(c)}
      <p class="panel-note">FARS case ${esc(c.id)}. Location as recorded by police; imagery is current, not from the crash date.</p>`);
  }
  function vehicles(c) {
    if (!c.vehicle_list?.length) return '';
    return `<h3>Vehicles</h3><ol class="vehicle-list">${c.vehicle_list.map(v => {
      const name = [v.year, v.make, v.model].filter(Boolean).join(' ') || 'Vehicle details not recorded';
      const extra = [v.body, v.speed_mph != null ? `traveling ${v.speed_mph} mph` : null].filter(Boolean).join(' · ');
      return `<li>${esc(name)}${extra ? `<span>${esc(extra)}</span>` : ''}</li>`; }).join('')}</ol>`;
  }

  $('place-view').addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.id) return showDetail(result.crashes.find(c => c.id === button.dataset.id));
    const action = button.dataset.action;
    if (action === 'exit') M.exitPlace();
    else if (action === 'retry') checkPlace(current.lat, current.lng, current.name);
    else if (action === 'fly') M.fly({longitude: selected.lng, latitude: selected.lat, zoom: 17.5, pitch: 55, maxZoom: 18});
    else if (action === 'back') { const id = selected?.id; selected = null; M.redraw(); renderList();
      $('place-view').querySelector(`[data-id="${CSS.escape(id)}"]`)?.focus(); }
  });
  $('place-view').addEventListener('change', event => {
    if (event.target.id === 'place-radius') checkPlace(current.lat, current.lng, current.name, Number(event.target.value));
  });

  // ---------------------------------------------------------------- city spots
  for (const [city, spot, lat, lng] of SPOTS) {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = city; button.title = `${spot}, ${city}`; button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => {
      $('place-q').value = ''; status('');
      checkPlace(lat, lng, `${spot} · ${city}`);
      document.querySelectorAll('#presets button').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    });
    $('presets').append(button);
  }

  // ---------------------------------------------------------------- search (Google Places when a key is configured, else Nominatim)
  M.request('/api/public/config').then(({googleMapsKey}) => {
    if (!googleMapsKey) return;
    key = googleMapsKey;
    window.__geocrashMaps = () => { maps = google.maps; };
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&libraries=places,geocoding&loading=async&callback=__geocrashMaps`;
    document.head.append(script);
  }).catch(() => {});  // ponytail: no config endpoint or key -> OpenStreetMap search still works
  const status = text => { $('place-status').textContent = text; };
  function showSuggestions(items) {
    suggestions = items; active = -1;
    $('place-suggestions').innerHTML = items.map((s, i) =>
      `<button type="button" role="option" id="place-option-${i}" aria-selected="false" data-index="${i}">${esc(s.main)}<small>${esc(s.sub)}</small></button>`).join('');
    $('place-suggestions').hidden = !items.length;
    $('place-q').setAttribute('aria-expanded', String(Boolean(items.length)));
    $('place-q').removeAttribute('aria-activedescendant');
  }
  $('place-q').addEventListener('input', () => {
    clearTimeout(timer); status(''); showSuggestions([]);
    const q = $('place-q').value.trim();
    if (!maps || q.length < 3 || LAT_LNG.test(q)) return;
    timer = setTimeout(async () => {
      const places = await maps.importLibrary('places').catch(() => null);
      if (!places) return;
      const {AutocompleteSuggestion, AutocompleteSessionToken} = places;
      session ||= new AutocompleteSessionToken();
      const {suggestions: found} = await AutocompleteSuggestion.fetchAutocompleteSuggestions({input: q, sessionToken: session, includedRegionCodes: ['us']})
        .catch(() => ({suggestions: []}));
      if (q !== $('place-q').value.trim()) return;
      showSuggestions(found.map(s => s.placePrediction).filter(Boolean)
        .map(p => ({p, main: p.mainText?.text ?? p.text.text, sub: p.secondaryText?.text ?? ''})));
    }, 200);
  });
  $('place-q').addEventListener('keydown', event => {
    if (event.key === 'Escape') return showSuggestions([]);
    if (!suggestions.length || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
    event.preventDefault();
    active = (active + (event.key === 'ArrowDown' ? 1 : -1) + suggestions.length) % suggestions.length;
    document.querySelectorAll('#place-suggestions button').forEach((b, i) => b.setAttribute('aria-selected', String(i === active)));
    $('place-q').setAttribute('aria-activedescendant', `place-option-${active}`);
  });
  async function pick(index) {
    const choice = suggestions[index]; showSuggestions([]);
    try {
      const found = choice.p.toPlace();
      await found.fetchFields({fields: ['location', 'displayName', 'formattedAddress']});
      session = null; $('place-q').value = found.displayName;
      checkPlace(found.location.lat(), found.location.lng(), found.formattedAddress || found.displayName);
    } catch (error) { status('That place could not be looked up. Try typing the full address.'); }
  }
  async function geocode(q) {
    if (maps) {
      const {results} = await new maps.Geocoder().geocode({address: q, componentRestrictions: {country: 'US'}}).catch(() => ({results: []}));
      if (results[0]) return {lat: results[0].geometry.location.lat(), lng: results[0].geometry.location.lng(), name: results[0].formatted_address};
    }
    const response = await fetch(`https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=us&addressdetails=1&q=${encodeURIComponent(q)}`);
    if (!response.ok) throw new Error(`Place search returned HTTP ${response.status}.`);
    const [hit] = await response.json();
    if (!hit) return null;
    const a = hit.address || {}, town = a.city || a.town || a.village || a.hamlet || a.county;
    const name = [hit.name || hit.display_name.split(',')[0], town, a.state].filter((part, i, all) => part && all.indexOf(part) === i).join(', ');
    return {lat: Number(hit.lat), lng: Number(hit.lon), name};
  }
  $('place-suggestions').addEventListener('click', event => { const b = event.target.closest('[data-index]'); if (b) pick(Number(b.dataset.index)); });
  document.addEventListener('click', event => { if (!event.target.closest('.place-search')) showSuggestions([]); });
  $('place-search').addEventListener('submit', async event => {
    event.preventDefault();
    if (suggestions.length) return pick(Math.max(active, 0));
    const q = $('place-q').value.trim();
    if (!q) return status('Type an address, a place name or “lat, lng”.');
    const coords = q.match(LAT_LNG);
    if (coords && Math.abs(coords[1]) <= 90 && Math.abs(coords[2]) <= 180) return checkPlace(Number(coords[1]), Number(coords[2]), `${coords[1]}, ${coords[2]}`);
    status('Searching…');
    try {
      const hit = await geocode(q);
      if (!hit) return status(`No US match for “${q}”. Try another place.`);
      status(''); clearChips();
      checkPlace(hit.lat, hit.lng, hit.name);
    } catch (error) { status(`Place search is unavailable right now. ${error.message}`); }
  });
})();
