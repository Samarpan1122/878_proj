'use strict';
/* GeoCrash homepage motion: column intro, idle orbit, hotspot beacons, year time-lapse and the 3D crash simulator.
   Everything here is presentation. The crash simulator is an illustrative physics sketch: FARS records where, when and
   how vehicles collided, never their paths, and the HUD says so. Loaded after home.js, place.js, roads.js and vehicles.js. */
(() => {
  const M = window.GeoCrash, V = window.GeoCrashVehicles, Roads = window.GeoCrashRoads;
  if (!M || !V || !Roads || !window.deck) return;
  const $ = id => document.getElementById(id);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const MPH = 0.44704, M_PER_DEG = 111320, G = 9.81;
  const DRAW_SCALE = 1.15;         // vehicles drawn slightly large so they read from the orbit camera
  const APPROACH_S = 2.6, FRICTION = 6.5, IDLE_MS = 7000, GROW_MS = 2600, LANE_M = 1.75, SMOKE_S = 2.2;
  const LAB_SPOT = {lat: 41.25953, lng: -96.02383, name: '72nd & Dodge, Omaha'};
  const PAINT = [[.2, .45, .95], [1, .4, .22], [.16, .72, .52], [.66, .42, .96], [.95, .78, .18]], SWATCH = ['#3373f2', '#ff6638', '#29b885', '#a86bf5', '#f2c72e'];
  const TAGS = 'ABCDE', MAX_VEHICLES = PAINT.length, FOLLOW_GAP_M = 14, REACTION_S = .35, OTHER_CONTACT = [.85, .08];
  const KINDS = {angle: 'Side impact (T-bone)', headon: 'Head-on', rear: 'Rear-end', sideswipe: 'Sideswipe, opposite directions', merge: 'Sideswipe, same direction',
    parked: 'Parked vehicle struck', fixed: 'Fixed object struck', rollover: 'Rollover', runoff: 'Run off road', brake: 'Emergency stop'};
  const CONTACT = {angle: [.9, .16], headon: [1, .05], rear: [.85, .03], parked: [.85, .06], sideswipe: [.25, .1], merge: [.2, .06]};   // momentum share, spin per m/s
  const SEVERITY = [[8, 'Minor'], [18, 'Moderate'], [30, 'Severe'], [Infinity, 'Extreme']];   // by speed change, mph
  const fx = window.GeoCrashFx = {grow: 1, replaying: false};
  let sim = null, saved = null, ticket = 0, growStart = 0, last = performance.now(), lastInput = last;
  for (const type of ['pointerdown', 'wheel', 'keydown', 'touchstart'])
    addEventListener(type, () => { lastInput = performance.now(); }, {passive: true, capture: true});
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const ease = t => t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t);
  const offset = (o, x, y) => [o.lng + x / (M_PER_DEG * Math.cos(o.lat * Math.PI / 180)), o.lat + y / M_PER_DEG];

  // ---------------------------------------------------------------- crash simulator: scenario from a FARS record
  function scenarioFor(c) {
    const collision = String(c.collision || '').toLowerCase(), event = String(c.first_event || '').toLowerCase();
    if (/front-to-rear|rear-to/.test(collision)) return {kind: 'rear'};
    if (/front-to-front/.test(collision)) return {kind: 'headon'};
    if (/sideswipe/.test(collision)) return {kind: /same/.test(collision) ? 'merge' : 'sideswipe'};
    if (/angle/.test(collision)) return {kind: 'angle'};
    if (/parked/.test(event)) return {kind: 'parked'};
    if (c.rollover || /rollover|overturn/.test(event)) return {kind: 'rollover'};
    if (c.peds > 0 || /pedestrian|cyclist|non-motorist|conveyance/.test(event)) return {kind: 'brake'};
    if (/tree|shrub/.test(event)) return {kind: 'fixed', prop: 'tree'};
    if (/pole|support|sign|post|hydrant/.test(event)) return {kind: 'fixed', prop: 'pole'};
    if (/barrier|guardrail|wall|attenuator|bridge|fence|building|fixed|culvert/.test(event)) return {kind: 'fixed', prop: 'barrier'};
    return {kind: 'runoff'};
  }
  /* Put a road-following vehicle at its current distance `u` from the scenario origin (negative = still approaching). */
  function follow(c) {
    const at = Roads.sample(c.road, c.road.s0 + c.dir * c.u), tx = at.tx * c.dir, ty = at.ty * c.dir, side = c.off(c.u), drift = c.off(c.u + .5) - c.off(c.u - .5);
    c.x = at.x + ty * side; c.y = at.y - tx * side; c.yaw = Math.atan2(ty, tx) - Math.atan(drift);
    c.vx = Math.cos(c.yaw) * c.speed; c.vy = Math.sin(c.yaw) * c.speed;
  }
  function build(o, network) {
    const roads = o.kind === 'angle' && network.junction ? network.junction : network.plain;
    const a = o.vA * MPH, b = o.vB * MPH, T = APPROACH_S, A = roads.a, lane = road => road.oneway ? 0 : LANE_M, la = A.oneway ? 1 : LANE_M;
    const drift = (from, to, start, len) => u => from + (to - from) * ease((u - start) / len), leave = u => la + (u > -16 ? (u + 16) ** 2 * .028 : 0);
    const cars = [], notes = [];
    const add = (type, road, dir, speed, u, off) => {
      const i = cars.length, veh = V.build(type, PAINT[i]);
      cars.push({veh, name: o.names?.[i] || veh.label, road, dir, speed, u, off, free: false, x: 0, y: 0, yaw: 0, vx: 0, vy: 0, spin: 0, roll: 0, rollRate: 0, skid: [[], []], dv: 0, v0: speed});
      return cars[i];
    };
    const k = o.kind;
    if (k === 'angle') {
      add(o.typeA, A, 1, a, -a * T, () => lane(A));
      if (roads.b) add(o.typeB, roads.b, 1, b, -b * T, () => lane(roads.b));
      else { add(o.typeB, A, -1, b, -b * T, drift(la, -la - .6, -16, 15)); notes.push('No cross street is mapped at this point, so vehicle B turns across the path.'); }
    } else if (k === 'headon') { add(o.typeA, A, 1, a, -a * T, drift(la, -.9, -26, 22)); add(o.typeB, A, -1, b, -b * T, () => la); }
    else if (k === 'sideswipe') { add(o.typeA, A, 1, a, -a * T, drift(la, .1, -26, 22)); add(o.typeB, A, -1, b, -b * T, () => la); }
    else if (k === 'merge') {
      const first = add(o.typeA, A, 1, a, -a * T, () => 0), slow = Math.min(b, a * .8), second = add(o.typeB, A, 1, slow, -slow * T, () => la);
      first.off = drift(-la, la - first.veh.w - second.veh.w, -18, 14);
    } else if (k === 'rear') {
      const first = add(o.typeA, A, 1, a, -a * T, () => la), slow = Math.min(b, a * .6), second = add(o.typeB, A, 1, slow, 0, () => la);
      second.u = -slow * T + (first.veh.len + second.veh.len) / 2 + .3;
    } else if (k === 'parked') { add(o.typeA, A, 1, a, -a * T, drift(la, la + 1.1, -20, 15)); add(o.typeB, A, 1, 0, 0, () => la + 2.2); }
    else if (k === 'brake') add(o.typeA, A, 1, a, -a * T, () => la);
    else add(o.typeA, A, 1, a, -a * T, leave);
    let prop = null;
    if (k === 'fixed') {
      const c = cars[0], was = c.u; c.u = 0; follow(c); c.u = was;
      prop = V.prop(o.prop || 'tree'); const ahead = c.veh.len / 2 + prop.radius;
      Object.assign(prop, {x: c.x + Math.cos(c.yaw) * ahead, y: c.y + Math.sin(c.yaw) * ahead, yaw: c.yaw});
    }
    const lead = cars.slice(0, 2).map(c => { const was = c.u; c.u = 0; follow(c); c.u = was; return [c.veh.mass * c.vx, c.veh.mass * c.vy, c.veh.mass]; });
    const px = lead.reduce((sum, m) => sum + m[0], 0), py = lead.reduce((sum, m) => sum + m[1], 0), drift0 = Math.hypot(px, py) / lead.reduce((sum, m) => sum + m[2], 0);
    const home = Roads.sample(A, A.s0), wx = drift0 > .5 ? px / Math.hypot(px, py) : home.tx, wy = drift0 > .5 ? py / Math.hypot(px, py) : home.ty;
    (o.extras || []).slice(0, MAX_VEHICLES - cars.length).forEach((extra, n) => {
      const first = cars[0];
      if (extra.mode === 'stopped') {   // standing where the struck vehicles are expected to slide
        const c = add(extra.type, A, 1, 0, 0, () => 0), ahead = clamp(.55 * drift0 * drift0 / (2 * FRICTION), 4.5, 10) + n * 5.5;
        Object.assign(c, {free: true, x: wx * ahead - wy * 1.2, y: wy * ahead + wx * 1.2, yaw: Math.atan2(home.ty, home.tx) + Math.PI});
      } else {                          // travelling behind vehicle A, braking once the crash happens
        const base = first.off(-999), c = add(extra.type, first.road, first.dir, (extra.speed ?? o.vA) * MPH, first.u - FOLLOW_GAP_M * (n + 1) - first.veh.len, () => base);
        c.follower = true;
      }
    });
    for (const c of cars) if (!c.free) follow(c);
    if (!network.mapped) notes.push('Street geometry was unavailable, so straight roads are assumed.');
    const road = Roads.sample(A, A.s0);
    return {...o, opts: o, lat: roads.origin.lat, lng: roads.origin.lng, mapped: network.mapped, heading: Math.atan2(road.ty, road.tx), cars, prop, notes,
      debris: [], smoke: [], pairs: [], struck: new Set(), t: 0, impactT: null, ring: null, result: null, done: false, slowUntil: 0, startAt: performance.now() + 1400};
  }

  // ---------------------------------------------------------------- crash simulator: physics
  function burst(s, x, y, n, speed) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * 6.283, v = speed * (.2 + Math.random());
      s.debris.push({x, y, z: .6, vx: Math.cos(a) * v, vy: Math.sin(a) * v, vz: 2 + Math.random() * 6, hot: Math.random() < .4});
    }
    s.ring = {x, y, t: s.t}; s.slowUntil = s.t + (s.impactT == null ? .45 : .2); s.impactT ??= s.t;
    if (!reduced.matches) for (const id of ['deck', 'fx-flash']) { const el = $(id); el.classList.remove('fx-hit'); void el.offsetWidth; el.classList.add('fx-hit'); }
  }
  /* Crush vehicle `c` where the contact point (world mx, my) meets it, by the velocity change it just took. */
  function damage(c, mx, my, dvx, dvy) {
    const change = Math.hypot(dvx, dvy), cos = Math.cos(-c.yaw), sin = Math.sin(-c.yaw);
    c.dv = Math.max(c.dv, change / MPH);
    if (change < .5) return;
    const hx = clamp(cos * (mx - c.x) - sin * (my - c.y), -c.veh.len / 2, c.veh.len / 2), hy = clamp(sin * (mx - c.x) + cos * (my - c.y), -c.veh.w, c.veh.w);
    V.deform(c.veh, hx, hy, (cos * dvx - sin * dvy) / change, (sin * dvx + cos * dvy) / change, clamp(change * .05, .05, Math.min(1.4, c.veh.len * .3)));
    c.hit = [hx, hy]; c.smokeUntil = c.veh.crush > .3 ? Infinity : 0;
  }
  const energy = c => .5 * c.veh.mass * (c.vx * c.vx + c.vy * c.vy);
  /* Any two vehicles that touch exchange momentum and crush each other. The first pair follows the scenario's contact model. */
  function collide(s) {
    const scripted = s.kind in CONTACT;
    for (let i = 0; i < s.cars.length; i++) for (let j = i + 1; j < s.cars.length; j++) {
      const A = s.cars[i], B = s.cars[j], primary = scripted && i === 0 && j === 1;
      if (s.struck.has(i * 8 + j) || (!primary && s.impactT == null)) continue;
      const reach = !primary ? (A.veh.len + B.veh.len) / 4 + (A.veh.w + B.veh.w) / 2 + .2 : s.kind === 'angle' ? A.veh.len / 2 + B.veh.w + .3
        : s.kind === 'sideswipe' || s.kind === 'merge' ? A.veh.w + B.veh.w + .3 : (A.veh.len + B.veh.len) / 2 * .96;
      if (Math.hypot(A.x - B.x, A.y - B.y) > reach) continue;
      s.struck.add(i * 8 + j); s.pairs.push([A, B, reach]);
      const [share, spin] = primary ? CONTACT[s.kind] : OTHER_CONTACT, total = A.veh.mass + B.veh.mass;
      const cx = (A.veh.mass * A.vx + B.veh.mass * B.vx) / total, cy = (A.veh.mass * A.vy + B.veh.mass * B.vy) / total;
      const closing = Math.hypot(A.vx - B.vx, A.vy - B.vy), before = energy(A) + energy(B), mx = (A.x + B.x) / 2, my = (A.y + B.y) / 2;
      for (const c of [A, B]) {
        const was = [c.vx, c.vy];
        c.free = true; c.vx += share * (cx - c.vx); c.vy += share * (cy - c.vy);
        damage(c, mx, my, c.vx - was[0], c.vy - was[1]);
      }
      A.spin += spin * closing * B.veh.mass / total * 2; B.spin -= spin * closing * A.veh.mass / total * 2;
      const shed = (before - energy(A) - energy(B)) / 1000;
      if (s.result) s.result.kJ += shed; else s.result = {closing: closing / MPH, kJ: shed};
      if (closing > 1) burst(s, mx, my, primary ? 80 : 40, 3 + closing * .28);
    }
  }
  function solo(s) {
    const c = s.cars[0], before = energy(c), nose = [c.x + Math.cos(c.yaw) * c.veh.len / 2, c.y + Math.sin(c.yaw) * c.veh.len / 2];
    if (s.kind === 'brake') { if (c.u > -(c.speed * c.speed) / (2 * FRICTION) - 2.5) c.braking = true; return; }
    if (c.u < (s.kind === 'fixed' ? 0 : s.kind === 'rollover' ? -4 : -2)) return;
    c.free = true;
    if (s.kind === 'fixed') { const was = [c.vx, c.vy]; c.vx *= .08; c.vy *= .08; c.spin = .5; damage(c, ...nose, c.vx - was[0], c.vy - was[1]); }
    else if (s.kind === 'rollover') { c.spin = -1.2; c.rollRate = 9; c.dv = c.speed * .6 / MPH; V.crushRoof(c.veh, clamp(c.speed / 30, .25, .75)); c.hit = [0, 0]; c.smokeUntil = Infinity; }
    else { c.spin = -1.4; damage(c, ...nose, -c.vx * .35, -c.vy * .35); }
    s.result = {closing: c.speed / MPH, kJ: (s.kind === 'fixed' ? before - energy(c) : before) / 1000};
    burst(s, ...nose, s.kind === 'fixed' ? 70 : 35, 2 + c.speed * .18);
  }
  function mark(s, c) {   // tyre marks: one track per side
    const half = (c.veh.w - .15) * DRAW_SCALE, nx = -Math.sin(c.yaw) * half, ny = Math.cos(c.yaw) * half;
    c.skid[0].push(offset(s, c.x + nx, c.y + ny)); c.skid[1].push(offset(s, c.x - nx, c.y - ny));
  }
  function separate(s) {   // keep struck vehicles from passing through each other
    for (const [A, B, reach] of s.pairs) {
      const dx = B.x - A.x, dy = B.y - A.y, gap = Math.hypot(dx, dy) || 1e-6, overlap = reach * .95 - gap;
      if (overlap <= 0) continue;
      const total = A.veh.mass + B.veh.mass, ux = dx / gap, uy = dy / gap;
      A.x -= ux * overlap * B.veh.mass / total; A.y -= uy * overlap * B.veh.mass / total; B.x += ux * overlap * A.veh.mass / total; B.y += uy * overlap * A.veh.mass / total;
    }
  }
  function step(dt) {
    const s = sim, two = s.kind in CONTACT;
    dt *= s.slow ? .3 : 1; if (s.impactT != null && s.t < s.slowUntil && !reduced.matches) dt *= .22;   // brief slow motion at impact
    s.t += dt;
    if (!s.done) { if (!two && s.impactT == null) solo(s); collide(s); }
    for (const c of s.cars) {
      const speed = Math.hypot(c.vx, c.vy);
      if (!c.free) {
        if (c.follower && s.impactT != null && s.t > s.impactT + REACTION_S) c.braking = true;
        if (c.braking) c.speed = Math.max(0, c.speed - FRICTION * dt);
        c.u += c.speed * dt; follow(c);
        if (c.braking && c.speed > 1) mark(s, c);
        continue;
      }
      if (speed > 0) { const next = Math.max(0, speed - FRICTION * dt) / speed; c.vx *= next; c.vy *= next; }
      c.x += c.vx * dt; c.y += c.vy * dt; c.yaw += c.spin * dt; c.spin *= Math.exp(-1.3 * dt);
      c.roll += c.rollRate * dt; c.rollRate *= Math.exp(-(speed < 2 ? 6 : .9) * dt);
      if (speed > 1 && !(c.rollRate > 1)) mark(s, c);
      if (c.hit && s.t - s.impactT < c.smokeUntil && Math.random() < dt * 12) {
        const cos = Math.cos(c.yaw), sin = Math.sin(c.yaw), [hx, hy] = c.hit;
        s.smoke.push({x: c.x + (cos * hx - sin * hy) * DRAW_SCALE, y: c.y + (sin * hx + cos * hy) * DRAW_SCALE, z: 1, age: 0, drift: Math.random() - .5});
      }
    }
    separate(s);
    for (const d of s.debris) {
      d.vz -= G * dt; d.x += d.vx * dt; d.y += d.vy * dt; d.z += d.vz * dt;
      if (d.z < 0) { d.z = 0; d.vz *= -.35; d.vx *= .6; d.vy *= .6; }
    }
    for (const puff of s.smoke) { puff.age += dt; puff.z += 1.3 * dt; puff.x += puff.drift * dt; }
    s.smoke = s.smoke.filter(puff => puff.age < SMOKE_S);
    const moving = s.cars.some(c => Math.hypot(c.vx, c.vy) > .3 || Math.abs(c.rollRate) > .3);
    if (!s.done && two && s.impactT == null && s.t > APPROACH_S + 2) s.done = s.missed = true;
    if (!s.done && !moving && (s.impactT != null || s.kind === 'brake')) {
      s.done = true;
      for (const c of s.cars) { c.roll = Math.round(c.roll / Math.PI) * Math.PI; c.smokeUntil = Math.min(c.smokeUntil ?? 0, s.t - s.impactT + 6); }
    }
    hud();
  }
  function simLayers() {
    const s = sim;
    if (!s) return [];
    const t = s.t, at = c => offset(s, c.x, c.y), ringAge = s.ring ? (t - s.ring.t) / .7 : 2, smoking = s.impactT == null ? 0 : t - s.impactT;
    const lift = c => (Math.abs(Math.sin(c.roll)) * c.veh.w + (1 - Math.cos(c.roll)) / 2 * (c.veh.belt + .45)) * DRAW_SCALE;
    return [
      new deck.PathLayer({id: 'fx-skids', data: s.cars.flatMap(c => c.skid).filter(track => track.length > 1), getPath: track => track, getWidth: .26 * DRAW_SCALE, getColor: [10, 10, 12, 170],
        capRounded: true, jointRounded: true, updateTriggers: {getPath: t}}),
      new deck.ScatterplotLayer({id: 'fx-fluid', data: s.cars.filter(c => c.hit && c.veh.crush > .45), getPosition: at, getRadius: Math.min(1.5, smoking * .3),
        getFillColor: [18, 22, 20, 150], updateTriggers: {getPosition: t, getRadius: t}}),
      new deck.ScatterplotLayer({id: 'fx-ring', data: ringAge < 1 ? [s.ring] : [], getPosition: r => [...offset(s, r.x, r.y), .3], stroked: true, filled: false,
        getRadius: 2 + 22 * ringAge, getLineColor: [255, 236, 190, Math.round(255 * (1 - ringAge))], getLineWidth: .6, updateTriggers: {getRadius: t, getLineColor: t}}),
      ...(s.prop ? [new deck.SimpleMeshLayer({id: 'fx-prop', data: [s.prop], mesh: s.prop.mesh, getPosition: p => offset(s, p.x, p.y), getColor: [255, 255, 255],
        getOrientation: p => [0, p.yaw * 180 / Math.PI, 0], sizeScale: DRAW_SCALE})] : []),
      ...s.cars.map((c, i) => new deck.SimpleMeshLayer({id: `fx-car-${i}`, data: [c], mesh: c.veh.mesh, getPosition: at, getColor: [255, 255, 255], sizeScale: DRAW_SCALE,
        getOrientation: [0, c.yaw * 180 / Math.PI, c.roll * 180 / Math.PI], getTranslation: [0, 0, lift(c)], material: {ambient: .5, diffuse: .7, shininess: 70},
        updateTriggers: {getPosition: t, getOrientation: t, getTranslation: t}})),
      new deck.ScatterplotLayer({id: 'fx-debris', data: s.debris, billboard: true, getPosition: d => [...offset(s, d.x, d.y), d.z * DRAW_SCALE], getRadius: .12,
        radiusMinPixels: 1.5, getFillColor: d => d.hot ? [255, 190, 80, 255] : [225, 235, 245, 235], updateTriggers: {getPosition: t}}),
      new deck.ScatterplotLayer({id: 'fx-smoke', data: s.smoke, billboard: true, getPosition: p => [...offset(s, p.x, p.y), p.z * DRAW_SCALE], getRadius: p => .35 + p.age * .8,
        getFillColor: p => [70, 72, 76, Math.round(130 * (1 - p.age / SMOKE_S))], updateTriggers: {getPosition: t, getRadius: t, getFillColor: t}}),
      new deck.TextLayer({id: 'fx-labels', data: s.cars, getPosition: c => [...at(c), (c.veh.belt + 2.2) * DRAW_SCALE], getText: (c, {index}) => `${TAGS[index]}  ${c.name}`,
        getSize: 12, getColor: [255, 255, 255], background: true, getBackgroundColor: (c, {index}) => [...PAINT[index].map(v => Math.round(v * 150)), 225], backgroundPadding: [7, 4],
        fontFamily: 'Inter, -apple-system, sans-serif', fontWeight: 600, characterSet: 'auto', getPixelOffset: (c, {index}) => [0, -24 * index], parameters: {depthCompare: 'always'}, updateTriggers: {getPosition: t}})
    ];
  }

  // ---------------------------------------------------------------- crash simulator: HUD and control
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const options = (map, chosen) => Object.entries(map).map(([key, label]) => `<option value="${key}"${key === chosen ? ' selected' : ''}>${esc(label)}</option>`).join('');
  function mountHud(o, loading = false) {
    $('fx-hud')?.remove();
    const two = o.kind in CONTACT, speedOf = (id, label, value, min) => `<label>${label} <output>${value} mph</output><input id="${id}" type="range" min="${min}" max="90" step="5" value="${value}"></label>`;
    document.body.insertAdjacentHTML('beforeend', `<section class="fx-hud" id="fx-hud" aria-label="Crash simulation">
      <p class="fx-tag">Illustrative simulation · not a record of vehicle paths</p>
      <h2>${esc(o.title)}</h2><p class="fx-desc">${esc(o.desc)}</p>
      <div class="fx-gauges"><div><b id="fx-va">—</b><span><i style="background:${SWATCH[0]}"></i>Vehicle A · mph</span></div>
        <div${two ? '' : ' hidden'}><b id="fx-vb">—</b><span><i style="background:${SWATCH[1]}"></i>Vehicle B · mph</span></div>
        <div><b id="fx-ke">—</b><span>Energy shed · kJ</span></div>
        <div class="fx-severity"><b id="fx-sev">—</b><span class="fx-meter" id="fx-meter" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span>Impact severity</span></div></div>
      <ul class="fx-cars" id="fx-cars"></ul>
      ${o.lab ? `<div class="fx-controls">
        <label class="wide">Scenario<select id="fx-kind">${options(KINDS, o.kind)}</select></label>
        ${speedOf('fx-sa', 'Vehicle A', o.vA, 10)}<label>Vehicle A type<select id="fx-ta">${options(V.TYPES, o.typeA)}</select></label>
        ${two ? `${speedOf('fx-sb', 'Vehicle B', o.vB, 0)}<label>Vehicle B type<select id="fx-tb">${options(V.TYPES, o.typeB)}</select></label>` : ''}
        <label>Third vehicle<select id="fx-third">${options({none: 'None', stopped: 'Stopped nearby', follow: 'Following vehicle A'}, o.third || 'none')}</select></label>
        <label>Third vehicle type<select id="fx-tc">${options(V.TYPES, o.typeC || 'van')}</select></label></div>` : ''}
      <div class="fx-actions"><button type="button" data-fx="again">Replay</button><button type="button" data-fx="slow" aria-pressed="${Boolean(o.slow)}">Slow motion</button><button type="button" data-fx="close">Close</button></div>
      <p class="fx-status" id="fx-status" role="status">${loading ? 'Loading street geometry…' : ''}</p>
      <p class="fx-credit">${loading ? '' : o.mapped ? 'Street geometry © OpenStreetMap contributors · OpenFreeMap' : ''}</p></section>`);
    const el = $('fx-hud');
    el.addEventListener('click', event => {
      const action = event.target.closest('button')?.dataset.fx;
      if (action === 'close') fx.stop();
      else if (!sim) return;
      else if (action === 'again') start({...sim.opts, slow: sim.slow});
      else if (action === 'slow') { sim.slow = !sim.slow; event.target.setAttribute('aria-pressed', String(sim.slow)); }
    });
    el.addEventListener('input', event => { if (event.target.type === 'range') event.target.previousElementSibling.textContent = `${event.target.value} mph`; });
    el.addEventListener('change', () => {
      if (!sim?.lab) return;
      start({...sim.opts, slow: sim.slow, kind: $('fx-kind').value, vA: Number($('fx-sa').value), typeA: $('fx-ta').value,
        vB: Number($('fx-sb')?.value ?? sim.opts.vB), typeB: $('fx-tb')?.value ?? sim.opts.typeB, third: $('fx-third').value, typeC: $('fx-tc').value,
        extras: $('fx-third').value === 'none' ? [] : [{mode: $('fx-third').value, type: $('fx-tc').value}]});
    });
  }
  function hud() {
    const s = sim, mph = c => Math.round(Math.hypot(c.vx, c.vy) / MPH), hit = s.impactT != null;
    $('fx-va').textContent = mph(s.cars[0]); if (s.cars[1]) $('fx-vb').textContent = mph(s.cars[1]);
    $('fx-ke').textContent = s.result ? Math.round(s.result.kJ).toLocaleString('en-US') : '—';
    const worst = Math.max(...s.cars.map(c => c.dv)), level = hit ? SEVERITY.findIndex(([limit]) => worst < limit) : -1;
    $('fx-sev').textContent = hit ? SEVERITY[level][1] : '—'; $('fx-meter').dataset.level = level + 1;
    $('fx-cars').innerHTML = s.cars.map((c, i) => `<li><i style="background:${SWATCH[i]}"></i><b>${TAGS[i]} · ${esc(c.name)}</b>
      <span>${hit ? `${esc(c.veh.label)} · speed change ${Math.round(c.dv)} mph${c.veh.crush > .05 ? ` · crush about ${Math.round(c.veh.crush * 39.4)} in` : ''}` : `${esc(c.veh.label)} · ${Math.round(c.v0 / MPH)} mph`}</span></li>`).join('');
    $('fx-status').textContent = s.missed ? 'The vehicles did not make contact in this run.' : s.done ? (s.result ? `Vehicles at rest. Closing speed at contact ${Math.round(s.result.closing)} mph. ${s.notes.join(' ')}` : `Vehicle stopped. ${s.notes.join(' ')}`)
      : hit ? 'Impact' : performance.now() < s.startAt ? 'Ready' : 'Approach';
    $('fx-hud').classList.toggle('fx-impact', hit && !s.done);
  }
  async function start(o) {
    const mine = ++ticket, fresh = !sim || sim.opts.srcLat !== o.srcLat || sim.opts.srcLng !== o.srcLng;
    saved ??= {satellite: M.isSatellite(), view: {...M.getView()}};
    fx.replaying = true; document.body.classList.add('replay');
    if (!M.isSatellite()) M.setSatellite(true);
    if (fresh) { sim = null; mountHud(o, true); M.fly({longitude: o.srcLng, latitude: o.srcLat, zoom: 17.6, pitch: 50, maxZoom: 20}); }
    const roads = await Roads.load(o.srcLat, o.srcLng);
    if (mine !== ticket) return;
    sim = build({typeA: 'sedan', typeB: 'sedan', vB: 0, ...o}, roads);
    if (fresh) M.fly({longitude: sim.lng, latitude: sim.lat, zoom: innerWidth < 761 ? 18.6 : 19.3, pitch: 60, bearing: 90 - sim.heading * 180 / Math.PI + 32, maxZoom: 20});
    else sim.startAt = performance.now() + 300;
    mountHud(sim); hud(); M.redraw();
  }
  fx.stop = () => {
    if (!fx.replaying) return;
    ticket++; sim = null; fx.replaying = false; document.body.classList.remove('replay'); $('fx-hud')?.remove();
    const back = saved; saved = null;
    if (M.hasPlace()) M.fly({zoom: 16.5, pitch: 45, bearing: 0, maxZoom: 18});
    else { if (!back.satellite) M.setSatellite(false); M.fly({...back.view, maxZoom: 9, zoom: Math.min(back.view.zoom, 9)}); }
    M.redraw();
  };
  /* Replay a FARS record: collision type, vehicle bodies and any recorded speeds come from the record; the motion is assumed. */
  fx.replay = c => {
    const {kind, prop} = scenarioFor(c), list = c.vehicle_list || [], speeds = list.map(v => v.speed_mph).filter(v => v > 0 && v < 150);
    const assumed = /interstate|freeway|expressway/i.test(c.func_sys || '') ? 65 : /arterial/i.test(c.func_sys || '') ? 45 : 35;
    const names = list.map(v => [v.year, v.make, v.model].filter(part => part && !/unknown/i.test(part)).join(' '));
    const what = c.collision && !/not a collision/i.test(c.collision) ? c.collision : c.first_event || 'crash';
    const leads = kind in CONTACT ? 2 : 1, extras = list.slice(leads).map(v => ({type: V.typeOf(v.body), mode: v.speed_mph === 0 ? 'stopped' : 'follow', speed: v.speed_mph > 0 && v.speed_mph < 150 ? v.speed_mph : undefined}));
    const shown = Math.min(MAX_VEHICLES, Math.max(list.length, leads)), count = c.vehicles ?? list.length;
    start({srcLat: c.lat, srcLng: c.lng, kind, prop, fromPlace: true, names, extras, typeA: V.typeOf(list[0]?.body), typeB: V.typeOf(list[1]?.body),
      vA: speeds[0] ?? assumed, vB: kind === 'rear' ? speeds[1] ?? 5 : speeds[1] ?? speeds[0] ?? assumed,
      title: `${KINDS[kind]} · reconstruction`,
      desc: `FARS case ${c.id}: ${what}. ${count > shown ? `${shown} of ${count} vehicles are shown` : count > 1 ? `All ${count} vehicles are shown` : 'The vehicle is shown'} with the body types on record. `
        + `${speeds.length ? 'Recorded travel speeds are used where available.' : `No speeds were recorded, so ${assumed} mph is assumed from the road class.`}${c.peds > 0 ? ' People on foot are not depicted.' : ''}`});
  };
  $('crash-lab')?.addEventListener('click', () => {
    const view = M.getView(), here = view.zoom >= 15 ? {lat: view.latitude, lng: view.longitude, name: 'the current map view'} : LAB_SPOT;
    start({srcLat: here.lat, srcLng: here.lng, kind: 'angle', prop: 'tree', vA: 45, vB: 35, typeA: 'sedan', typeB: 'suv', lab: true, title: 'Crash lab',
      desc: `A physics sandbox on the real streets at ${here.name}: momentum exchange, crush damage, sliding friction and debris.`});
  });

  // ---------------------------------------------------------------- ambient motion on the national map
  let ranked = null, rankedFrom = null;
  function beacons() {
    if (reduced.matches || M.hasPlace()) return [];
    const cells = M.cells();
    if (cells !== rankedFrom) { rankedFrom = cells; ranked = [...cells].sort((a, b) => b.properties.fatal_crashes - a.properties.fatal_crashes).slice(0, 14); }
    const t = performance.now() / 1000, phase = i => (t * .4 + i * .37) % 1, rgb = M.isSatellite() ? [255, 214, 120] : [170, 200, 255];
    return [new deck.ScatterplotLayer({id: 'fx-beacons', data: ranked, stroked: true, filled: false, radiusUnits: 'pixels', lineWidthUnits: 'pixels', getLineWidth: 1.5,
      getPosition: f => f.geometry.coordinates, getRadius: (f, {index}) => 5 + 38 * phase(index), getLineColor: (f, {index}) => [...rgb, Math.round(210 * (1 - phase(index)))],
      updateTriggers: {getRadius: t, getLineColor: t}})];
  }
  fx.layers = () => fx.replaying ? simLayers() : beacons();
  fx.onData = () => { if (!reduced.matches) { growStart = performance.now(); fx.grow = 0; } };
  /* Height factor for a column while the map loads: columns rise in a wave moving out from the view centre. */
  fx.rise = ([lng, lat], view) => fx.grow >= 1 ? 1 : ease(fx.grow * 2.2 - Math.min(1.2, Math.hypot(lng - view.longitude, (lat - view.latitude) * 1.3) / 28));
  addEventListener('pointermove', event => { document.body.style.setProperty('--mx', `${event.clientX}px`); document.body.style.setProperty('--my', `${event.clientY}px`); }, {passive: true});

  let playing = false;
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  $('timelapse')?.addEventListener('click', async () => {
    if (playing) { playing = false; return; }
    if (M.hasPlace()) M.exitPlace();   // the time-lapse is a national view
    playing = true; $('timelapse').setAttribute('aria-pressed', 'true'); $('timelapse').textContent = '■ Stop';
    for (const year of ['2021', '2022', '2023', '2024', '']) {
      if (!playing) break;
      $('fx-year').textContent = year || '2021–2024'; $('fx-year').hidden = false;
      await M.setYear(year); await wait(1700);
    }
    if (!playing) await M.setYear('');
    playing = false; $('fx-year').hidden = true; $('timelapse').setAttribute('aria-pressed', 'false'); $('timelapse').textContent = '▶ Years';
  });

  function frame(now) {
    const dt = Math.min(.05, (now - last) / 1000); last = now;
    if (!document.hidden && M.isMapReady()) {
      if (fx.replaying && sim?.fromPlace && !M.hasPlace()) fx.stop();
      if (fx.grow < 1) fx.grow = 1 - Math.pow(1 - Math.min(1, (now - growStart) / GROW_MS), 3);
      const settled = now > M.busyUntil();
      if (sim) {
        if (now > sim.startAt) step(dt);
        if (settled && !reduced.matches) M.jump({bearing: M.getView().bearing + 5 * dt});
      } else if (!reduced.matches && settled && now - lastInput > IDLE_MS && !M.hasPlace()) M.jump({bearing: M.getView().bearing + 1.4 * dt});
      if (fx.replaying || !reduced.matches) M.redraw();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
