'use strict';
/* Street geometry for the crash simulator. Reads OpenStreetMap roads from OpenFreeMap vector tiles (OpenMapTiles schema),
   decodes the one layer it needs, and returns the road through a point plus the nearest crossing road, in metres. */
(() => {
  const TILEJSON = 'https://tiles.openfreemap.org/planet', ZOOM = 14, M_PER_DEG = 111320, TIMEOUT_MS = 6000;
  const DRIVABLE = new Set(['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'minor', 'service']);
  const REACH_M = 170, JOIN_M = 1.5, MAX_TURN = .6, CROSS_M = 45, SERVICE_PENALTY_M = 14;
  let template = null;
  const cache = new Map();

  // ---------------------------------------------------------------- minimal Mapbox Vector Tile reader
  function reader(buf) {
    let p = 0;
    const r = {
      more: () => p < buf.length,
      varint() { let v = 0, shift = 1, b; do { b = buf[p++]; v += (b & 127) * shift; shift *= 128; } while (b & 128); return v; },
      bytes() { const n = r.varint(), out = buf.subarray(p, p + n); p += n; return out; },
      skip(wire) { if (wire === 0) r.varint(); else if (wire === 2) r.bytes(); else if (wire === 5) p += 4; else if (wire === 1) p += 8; else throw new Error('Unsupported tile encoding'); }
    };
    return r;
  }
  const zigzag = v => (v % 2 ? -(v + 1) / 2 : v / 2);
  function fields(buf, visit) { const r = reader(buf); while (r.more()) { const key = r.varint(); visit(key >> 3, key & 7, r); } }
  function value(buf) {
    let out = null;
    fields(buf, (id, wire, r) => {
      if (id === 1) out = new TextDecoder().decode(r.bytes());
      else if (id === 4 || id === 5) out = r.varint(); else if (id === 6) out = zigzag(r.varint()); else if (id === 7) out = Boolean(r.varint());
      else r.skip(wire);
    });
    return out;
  }
  /* Returns [{props, lines: [[px, py], …][]}] for the named layer, in tile pixel units, plus its extent. */
  function layerLines(tile, name) {
    let found = null;
    fields(tile, (id, wire, r) => {
      if (id !== 3) return r.skip(wire);
      const layer = {name: '', keys: [], values: [], features: [], extent: 4096};
      fields(r.bytes(), (lid, lwire, lr) => {
        if (lid === 1) layer.name = new TextDecoder().decode(lr.bytes()); else if (lid === 2) layer.features.push(lr.bytes());
        else if (lid === 3) layer.keys.push(new TextDecoder().decode(lr.bytes())); else if (lid === 4) layer.values.push(lr.bytes());
        else if (lid === 5) layer.extent = lr.varint(); else lr.skip(lwire);
      });
      if (layer.name === name) found = layer;
    });
    if (!found) return {extent: 4096, features: []};
    const values = found.values.map(value);
    return {extent: found.extent, features: found.features.map(raw => {
      let tags = [], geometry = [], type = 0;
      fields(raw, (id, wire, r) => {
        if (id === 2) { const pr = reader(r.bytes()); while (pr.more()) tags.push(pr.varint()); }
        else if (id === 3) type = r.varint();
        else if (id === 4) { const pr = reader(r.bytes()); while (pr.more()) geometry.push(pr.varint()); }
        else r.skip(wire);
      });
      const props = {}; for (let i = 0; i + 1 < tags.length; i += 2) props[found.keys[tags[i]]] = values[tags[i + 1]];
      const lines = []; let x = 0, y = 0, i = 0;
      while (type === 2 && i < geometry.length) {
        const command = geometry[i] & 7, count = geometry[i++] >> 3;
        for (let k = 0; k < count && command !== 7; k++) {
          x += zigzag(geometry[i++]); y += zigzag(geometry[i++]);
          if (command === 1) lines.push([[x, y]]); else lines.at(-1).push([x, y]);
        }
      }
      return {props, lines};
    })};
  }

  // ---------------------------------------------------------------- geometry helpers (metres, x east, y north)
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const heading = (a, b) => Math.atan2(b[1] - a[1], b[0] - a[0]);
  const turn = (a, b) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
  function nearest(pts, p) {
    let best = {d: Infinity}, walked = 0;
    for (let i = 0; i + 1 < pts.length; i++) {
      const a = pts[i], b = pts[i + 1], dx = b[0] - a[0], dy = b[1] - a[1], len2 = dx * dx + dy * dy || 1e-9;
      const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2)), q = [a[0] + dx * t, a[1] + dy * t], d = dist(p, q);
      if (d < best.d) best = {d, point: q, s: walked + Math.sqrt(len2) * t, heading: Math.atan2(dy, dx)};
      walked += Math.sqrt(len2);
    }
    return best;
  }
  function crossing(a, b, c, d) {   // intersection of segments ab and cd, or null
    const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]], det = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(det) < 1e-9) return null;
    const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / det, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / det;
    return t < 0 || t > 1 || u < 0 || u > 1 ? null : [a[0] + r[0] * t, a[1] + r[1] * t];
  }
  const span = pts => pts.reduce((sum, p, i) => i ? sum + dist(p, pts[i - 1]) : 0, 0);
  /* Follow the road past the end of `pts` by joining lines that continue it. `flow` is +1 when travel runs with `pts`. */
  function extend(pts, lines, used, flow) {
    for (let guard = 0; guard < 14 && span(pts) < REACH_M * 2; guard++) {
      const end = pts.at(-1), going = heading(pts.at(-2), end);
      let best = null;
      for (const line of lines) {
        if (used.has(line)) continue;
        for (const reversed of [false, true]) {
          if (line.oneway && (reversed ? -1 : 1) !== flow) continue;
          const first = reversed ? line.pts.at(-1) : line.pts[0], second = reversed ? line.pts.at(-2) : line.pts[1];
          if (dist(first, end) > JOIN_M) continue;
          const bend = turn(going, heading(first, second)) + (line.cls === used.cls ? 0 : .25);
          if (bend < MAX_TURN && (!best || bend < best.bend)) best = {line, reversed, bend};
        }
      }
      if (!best) break;
      used.add(best.line);
      pts.push(...(best.reversed ? [...best.line.pts].reverse() : best.line.pts).slice(1));
    }
    return pts;
  }
  function chain(line, lines) {
    const used = new Set([line]); used.cls = line.cls;
    const forward = extend([...line.pts], lines, used, 1);
    const whole = extend(forward.reverse(), lines, used, -1).reverse();
    return {pts: whole, used, oneway: line.oneway, cls: line.cls};
  }
  function path(road, origin) {
    const pts = road.pts.map(p => [p[0] - origin[0], p[1] - origin[1]]), cum = [0];
    for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + dist(pts[i], pts[i - 1]));
    return {pts, cum, s0: nearest(pts, [0, 0]).s, oneway: road.oneway, cls: road.cls};
  }
  /* Point and unit tangent at arclength s; runs straight on past either end. */
  function sample(road, s) {
    const {pts, cum} = road, last = pts.length - 1;
    let i = 0; while (i < last - 1 && cum[i + 1] < s) i++;
    const a = pts[i], b = pts[i + 1], len = cum[i + 1] - cum[i] || 1e-9, tx = (b[0] - a[0]) / len, ty = (b[1] - a[1]) / len, along = s - cum[i];
    return {x: a[0] + tx * along, y: a[1] + ty * along, tx, ty};
  }
  const straight = angle => ({pts: [[-400 * Math.cos(angle), -400 * Math.sin(angle)], [400 * Math.cos(angle), 400 * Math.sin(angle)]], cum: [0, 800], s0: 400, oneway: false, cls: 'minor'});

  // ---------------------------------------------------------------- loading
  async function get(url, type) {
    const control = new AbortController(), timer = setTimeout(() => control.abort(), TIMEOUT_MS);
    try { const response = await fetch(url, {signal: control.signal}); if (!response.ok) throw new Error(`Road tiles returned HTTP ${response.status}`); return await response[type](); }
    finally { clearTimeout(timer); }
  }
  async function roadLines(lat, lng) {
    template ??= (await get(TILEJSON, 'json')).tiles[0];
    const n = 2 ** ZOOM, fx = (lng + 180) / 360 * n, fy = (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n;
    const near = f => { const part = f - Math.floor(f); return part < .12 ? [0, -1] : part > .88 ? [0, 1] : [0]; };
    const jobs = []; for (const dx of near(fx)) for (const dy of near(fy)) jobs.push([Math.floor(fx) + dx, Math.floor(fy) + dy]);
    const cos = Math.cos(lat * Math.PI / 180), lines = [];
    await Promise.all(jobs.map(async ([tx, ty]) => {
      const tile = new Uint8Array(await get(template.replace('{z}', ZOOM).replace('{x}', tx).replace('{y}', ty), 'arrayBuffer'));
      const {extent, features} = layerLines(tile, 'transportation');
      for (const {props, lines: shapes} of features) {
        if (!DRIVABLE.has(props.class)) continue;
        for (const shape of shapes) {
          let pts = shape.map(([px, py]) => {
            const lon = (tx + px / extent) / n * 360 - 180, la = Math.atan(Math.sinh(Math.PI * (1 - 2 * (ty + py / extent) / n))) * 180 / Math.PI;
            return [(lon - lng) * cos * M_PER_DEG, (la - lat) * M_PER_DEG];
          }).filter((p, i, all) => !i || dist(p, all[i - 1]) > .05);
          if (pts.length < 2 || !pts.some(p => Math.hypot(p[0], p[1]) < REACH_M * 2.5)) continue;
          if (props.oneway === -1) pts = pts.reverse();
          lines.push({pts, cls: props.class, oneway: props.oneway === 1 || props.oneway === -1});
        }
      }
    }));
    return lines;
  }
  /* Resolves to {mapped, plain: {origin, a}, junction: {origin, a, b} | null}. `a` is the road through the point, centred on the point
     snapped to it (plain) or on the nearest junction with a crossing road `b`. Never rejects: failures fall back to straight roads. */
  async function load(lat, lng) {
    const key = `${lat.toFixed(5)},${lng.toFixed(5)}`;
    if (cache.has(key)) return cache.get(key);
    let result;
    try {
      const lines = await roadLines(lat, lng);
      const rank = line => nearest(line.pts, [0, 0]).d + (line.cls === 'service' ? SERVICE_PENALTY_M : 0);
      const home = lines.reduce((best, line) => (!best || rank(line) < rank(best) ? line : best), null);
      if (!home || nearest(home.pts, [0, 0]).d > 80) throw new Error('No mapped road near this point');
      const main = chain(home, lines), snap = nearest(main.pts, [0, 0]);
      let cross = null;
      for (const line of lines) {
        if (main.used.has(line)) continue;
        const hits = [];
        for (let i = 0; i + 1 < line.pts.length; i++) for (let k = 0; k + 1 < main.pts.length; k++) {
          const hit = crossing(line.pts[i], line.pts[i + 1], main.pts[k], main.pts[k + 1]); if (hit) hits.push(hit);
        }
        for (const end of [line.pts[0], line.pts.at(-1)]) { const touch = nearest(main.pts, end); if (touch.d < JOIN_M * 1.5) hits.push(touch.point); }
        for (const hit of hits) {
          const angle = turn(nearest(line.pts, hit).heading, nearest(main.pts, hit).heading), score = dist(hit, snap.point) + (line.cls === 'service' ? SERVICE_PENALTY_M : 0);
          if (angle > .5 && angle < Math.PI - .5 && score < CROSS_M && (!cross || score < cross.score)) cross = {line, hit, score};
        }
      }
      const cos = Math.cos(lat * Math.PI / 180), place = point => ({lat: lat + point[1] / M_PER_DEG, lng: lng + point[0] / (M_PER_DEG * cos)});
      result = {mapped: true, plain: {origin: place(snap.point), a: path(main, snap.point)},
        junction: cross ? {origin: place(cross.hit), a: path(main, cross.hit), b: path(chain(cross.line, lines), cross.hit)} : null};
    } catch (error) {
      console.warn('GeoCrash road geometry:', error.message);
      result = {mapped: false, plain: {origin: {lat, lng}, a: straight(Math.PI / 2)}, junction: {origin: {lat, lng}, a: straight(Math.PI / 2), b: straight(0)}};
    }
    cache.set(key, result);
    return result;
  }
  window.GeoCrashRoads = {load, sample, layerLines};
})();
