'use strict';
/* Procedural vehicle and roadside-object meshes for the crash simulator, with crush deformation.
   Each vehicle is a side profile extruded across its width (front faces +x, metres), coloured per vertex. No model files. */
(() => {
  const GLASS = [.1, .14, .2], TYRE = [.07, .07, .08], HUB = [.62, .64, .68], LAMP = [1, .96, .8], TAIL = [.85, .08, .06], CARGO = [.92, .93, .95];
  const STRIPS = [-1, -.6, -.2, .2, .6, 1], STEP_M = .28;
  // half-width w, ground clearance z0, profile chains as [x, z] from rear to front
  const SPECS = {
    sedan: {label: 'Car', mass: 1500, len: 4.6, w: .9, r: .33, axles: [-1.45, 1.45], lamp: .72,
      body: [[-2.3, .3], [-2.3, .78], [-2.2, .98], [-1.3, 1.02], [.7, 1.02], [1.9, .9], [2.25, .74], [2.3, .3]], cabin: [[-1.75, 1], [-1.2, 1.42], [.1, 1.45], [.95, 1.02]]},
    suv: {label: 'SUV', mass: 2100, len: 4.8, w: .95, r: .38, axles: [-1.5, 1.5], lamp: .88,
      body: [[-2.4, .36], [-2.4, .95], [-2.35, 1.18], [1.1, 1.18], [2.15, 1.08], [2.38, .85], [2.4, .36]], cabin: [[-2.3, 1.16], [-2.1, 1.76], [.3, 1.76], [1.05, 1.18]]},
    pickup: {label: 'Pickup', mass: 2300, len: 5.5, w: .98, r: .4, axles: [-1.75, 1.75], lamp: .92,
      body: [[-2.75, .4], [-2.75, 1.22], [1.5, 1.22], [2.55, 1.12], [2.73, .88], [2.75, .4]], cabin: [[-.6, 1.2], [-.5, 1.82], [.8, 1.82], [1.5, 1.22]]},
    van: {label: 'Van', mass: 2400, len: 5.1, w: .98, r: .36, axles: [-1.6, 1.6], lamp: .85,
      body: [[-2.55, .36], [-2.55, 1.25], [1.75, 1.25], [2.45, 1.08], [2.55, .8], [2.55, .36]], cabin: [[-2.5, 1.23], [-2.45, 1.98], [1.05, 1.98], [1.8, 1.25]]},
    truck: {label: 'Heavy truck', mass: 11000, len: 8.4, w: 1.25, r: .5, axles: [-3.1, -2.1, 3.2], lamp: .95,
      body: [[-4.2, .5], [-4.2, 1.15], [4.2, 1.15], [4.2, .5]], cabin: [[2.3, 1.13], [2.3, 2.75], [3.7, 2.75], [4.15, 1.9], [4.18, 1.13]],
      cargo: [[-4.15, 1.15], [-4.15, 3.4], [2.1, 3.4], [2.1, 1.15]]},
    moto: {label: 'Motorcycle', mass: 260, len: 2.1, w: .2, r: .31, axles: [-.72, .72], lamp: .95, single: true,
      body: [[-1, .4], [-.95, .85], [-.2, .95], [.3, 1], [.75, 1.15], [.95, .7], [1, .4]], rider: true}
  };
  function typeOf(body) {
    const text = String(body || '').toLowerCase();
    return /motorcycle|motor scooter|moped|cycle type|atv/.test(text) ? 'moto'
      : /truck-tractor|straight truck|medium\/heavy|heavy truck|\bbus\b|step van|motor home/.test(text) ? 'truck'
      : /pickup/.test(text) ? 'pickup' : /utility/.test(text) ? 'suv' : /\bvan\b|minivan/.test(text) ? 'van' : 'sedan';
  }

  // ---------------------------------------------------------------- mesh building
  const draft = () => ({p: [], n: [], c: [], glass: []});
  function quad(m, a, b, c, d, normal, color, glass = 0) {
    for (const v of [a, b, c, a, c, d]) { m.p.push(...v); m.n.push(...normal); m.c.push(...color); m.glass.push(glass); }
  }
  function resample(chain) {
    const out = [chain[0]];
    for (let i = 1; i < chain.length; i++) {
      const [x0, z0] = chain[i - 1], [x1, z1] = chain[i], n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, z1 - z0) / STEP_M));
      for (let k = 1; k <= n; k++) out.push([x0 + (x1 - x0) * k / n, z0 + (z1 - z0) * k / n]);
    }
    return out;
  }
  /* Extrude a rear-to-front [x, z] profile across ±halfWidth. `floor` is the underside height. */
  function extrude(m, chain, floor, halfWidth, color, glass = 0) {
    const pts = resample(chain);
    for (let i = 0; i + 1 < pts.length; i++) {
      const [px, pz] = pts[i], [qx, qz] = pts[i + 1], len = Math.hypot(qx - px, qz - pz) || 1, normal = [-(qz - pz) / len, 0, (qx - px) / len];
      for (let j = 0; j + 1 < STRIPS.length; j++) {
        const y0 = STRIPS[j] * halfWidth, y1 = STRIPS[j + 1] * halfWidth;
        quad(m, [px, y0, pz], [qx, y0, qz], [qx, y1, qz], [px, y1, pz], normal, color, glass);
      }
      if (qx - px > 1e-6) for (const side of [-1, 1]) {
        const y = side * halfWidth;
        quad(m, [px, y, floor], [qx, y, floor], [qx, y, qz], [px, y, pz], [0, side, 0], color, glass);
      }
    }
  }
  function box(m, [cx, cy, cz], [sx, sy, sz], color) {
    const x0 = cx - sx / 2, x1 = cx + sx / 2, y0 = cy - sy / 2, y1 = cy + sy / 2, z0 = cz - sz / 2, z1 = cz + sz / 2;
    quad(m, [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1], [1, 0, 0], color); quad(m, [x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [-1, 0, 0], color);
    quad(m, [x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [0, 1, 0], color); quad(m, [x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [0, -1, 0], color);
    quad(m, [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [0, 0, 1], color);
  }
  function wheel(m, x, y, radius, width) {
    const sides = 12, at = (k, r) => [x + Math.cos(k / sides * 2 * Math.PI) * r, Math.sin(k / sides * 2 * Math.PI) * r + radius];
    for (let k = 0; k < sides; k++) {
      const [ax, az] = at(k, radius), [bx, bz] = at(k + 1, radius), [hx, hz] = at(k, radius * .58), [ix, iz] = at(k + 1, radius * .58);
      const mid = (k + .5) / sides * 2 * Math.PI;
      quad(m, [ax, y - width / 2, az], [bx, y - width / 2, bz], [bx, y + width / 2, bz], [ax, y + width / 2, az], [Math.cos(mid), 0, Math.sin(mid)], TYRE);
      for (const side of [-1, 1]) {
        const face = y + side * width / 2;
        quad(m, [ax, face, az], [bx, face, bz], [ix, face, iz], [hx, face, hz], [0, side, 0], TYRE);
        quad(m, [hx, face, hz], [ix, face, iz], [x, face, radius], [x, face, radius], [0, side, 0], HUB);
      }
    }
  }
  /* Upright n-sided prism, used for trunks, canopies and poles. */
  function column(m, x, y, base, radius, height, color, sides = 8) {
    for (let k = 0; k < sides; k++) {
      const a = k / sides * 2 * Math.PI, b = (k + 1) / sides * 2 * Math.PI, mid = (a + b) / 2;
      const p = [x + Math.cos(a) * radius, y + Math.sin(a) * radius], q = [x + Math.cos(b) * radius, y + Math.sin(b) * radius];
      quad(m, [...p, base], [...q, base], [...q, base + height], [...p, base + height], [Math.cos(mid), Math.sin(mid), 0], color);
      quad(m, [...p, base + height], [...q, base + height], [x, y, base + height], [x, y, base + height], [0, 0, 1], color);
    }
  }
  const finish = m => ({attributes: {positions: {value: new Float32Array(m.p), size: 3}, normals: {value: new Float32Array(m.n), size: 3}, colors: {value: new Float32Array(m.c), size: 3}}});

  function build(type, paint) {
    const spec = SPECS[type] || SPECS.sedan, m = draft(), floor = spec.body[0][1];
    extrude(m, spec.body, floor, spec.w, paint);
    if (spec.cargo) extrude(m, spec.cargo, spec.cargo[0][1], spec.w, CARGO);
    if (spec.cabin) {
      const base = spec.cabin[0][1], mid = (spec.cabin[0][0] + spec.cabin.at(-1)[0]) / 2;
      extrude(m, spec.cabin, base, spec.w * .86, paint);
      extrude(m, spec.cabin.map(([x, z]) => [mid + (x - mid) * 1.045, Math.max(base, z - .09)]), base + .06, spec.w * .875, GLASS, 1);
    }
    if (spec.rider) { box(m, [-.15, 0, 1.3], [.36, .42, .62], [.13, .14, .17]); box(m, [-.05, 0, 1.76], [.26, .26, .26], [.85, .85, .88]); }
    for (const x of spec.axles) for (const side of spec.single ? [0] : [-1, 1]) wheel(m, x, side * (spec.w - .1), spec.r, spec.single ? .14 : .26);
    for (const side of spec.single ? [0] : [-1, 1]) {
      box(m, [spec.len / 2 - .01, side * spec.w * .66, spec.lamp], [.08, spec.w * .46, .15], LAMP);
      box(m, [-spec.len / 2 + .01, side * spec.w * .66, spec.lamp + .08], [.08, spec.w * .42, .13], TAIL);
    }
    return {type, label: spec.label, mass: spec.mass, len: spec.len, w: spec.w, belt: spec.cabin ? spec.cabin[0][1] : spec.lamp, draft: m, mesh: finish(m), crush: 0};
  }
  const hash = (x, y, z, seed) => { const v = Math.sin(x * 12.9898 + y * 78.233 + z * 37.719 + seed) * 43758.5453; return v - Math.floor(v); };
  const ease = t => t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t);
  /* Crush the vehicle around local point (hx, hy), pushed `depth` metres along the unit force direction (dx, dy). */
  function deform(vehicle, hx, hy, dx, dy, depth) {
    const {p, n, c, glass} = vehicle.draft, reach = depth * 2 + .6, lateral = Math.max(1.2, vehicle.w * 1.5);
    for (let i = 0; i < p.length; i += 3) {
      const rx = p[i] - hx, ry = p[i + 1] - hy, along = Math.max(0, rx * dx + ry * dy), side = Math.abs(ry * dx - rx * dy);
      const amount = ease(1 - along / reach) * ease(1 - side / lateral);
      if (amount <= 0) continue;
      const a = hash(p[i], p[i + 1], p[i + 2], 1), b = hash(p[i], p[i + 1], p[i + 2], 2), push = depth * amount * (.75 + .5 * a);
      p[i] += dx * push - dy * (b - .5) * push * .35; p[i + 1] += dy * push + dx * (b - .5) * push * .35; p[i + 2] = Math.max(.12, p[i + 2] - push * .3 * (a - .25));
      const dark = 1 - .55 * amount, frosted = glass[i / 3] && amount > .2;
      for (let k = 0; k < 3; k++) {
        c[i + k] = frosted ? .78 + .1 * a : c[i + k] * dark;
        n[i + k] += (hash(p[i], p[i + 1], p[i + 2], 3 + k) - .5) * amount * 1.4;
      }
      const len = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1; n[i] /= len; n[i + 1] /= len; n[i + 2] /= len;
    }
    vehicle.crush = Math.max(vehicle.crush, depth); vehicle.mesh = finish(vehicle.draft);
  }
  /* Flatten the roof toward the beltline, as in a rollover. `amount` 0–1. */
  function crushRoof(vehicle, amount) {
    const {p, c, glass} = vehicle.draft;
    for (let i = 0; i < p.length; i += 3) {
      if (p[i + 2] <= vehicle.belt) continue;
      const a = hash(p[i], p[i + 1], 0, 5);
      p[i + 2] = vehicle.belt + (p[i + 2] - vehicle.belt) * (1 - amount * (.6 + .4 * a)); p[i + 1] += (a - .5) * amount * .25;
      for (let k = 0; k < 3; k++) c[i + k] = glass[i / 3] ? .78 + .1 * a : c[i + k] * (1 - .35 * amount);
    }
    vehicle.crush = Math.max(vehicle.crush, amount * .5); vehicle.mesh = finish(vehicle.draft);
  }
  function prop(kind) {
    const m = draft();
    if (kind === 'tree') { column(m, 0, 0, 0, .24, 3, [.3, .2, .12]); column(m, 0, 0, 2.4, 1.7, 1.6, [.13, .34, .16], 9); column(m, 0, 0, 4, 1.15, 1.5, [.16, .4, .19], 9); }
    else if (kind === 'pole') { column(m, 0, 0, 0, .15, 8.5, [.42, .43, .45]); box(m, [0, 0, 8], [.12, 2.2, .12], [.42, .43, .45]); }
    else box(m, [0, 0, .45], [.55, 7, .9], [.72, .72, .7]);   // concrete barrier, long axis across the vehicle's path
    return {kind, radius: kind === 'barrier' ? .3 : kind === 'tree' ? .24 : .15, mesh: finish(m)};
  }
  window.GeoCrashVehicles = {build, typeOf, deform, crushRoof, prop, TYPES: Object.fromEntries(Object.entries(SPECS).map(([key, spec]) => [key, spec.label]))};
})();
