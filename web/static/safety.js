"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const state = {rows: [], selected: null, catalog: [], sort: "excess_annual", desc: true, load: 0, calculation: 0, synthetic: false};
  const areas = {omaha: {lat: 41.2565, lng: -95.9345, radius_km: 30}, lincoln: {lat: 40.8136, lng: -96.7026, radius_km: 30}, nebraska: {}};
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const num = (value, digits = 2) => value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: digits}) : "Not available";
  const money = value => value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {style: "currency", currency: "USD", maximumFractionDigits: 0}) : "Not available";
  const text = value => typeof value === "object" ? JSON.stringify(value) : String(value ?? "Not reported");
  const link = (url, label) => {try {const u = new URL(url); return ["https:", "http:"].includes(u.protocol) ? `<a href="${escape(u.href)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>` : escape(label);} catch {return escape(label);}};
  async function request(path, options) {
    const response = await fetch(path, {...options, headers: {"Accept": "application/json", ...(options?.headers || {})}});
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data?.detail;
      throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(x => `${x.loc?.slice(1).join(".")}: ${x.msg}`).join("; ") : `Request failed (${response.status}). Try loading again.`);
    }
    return data;
  }
  function renderRows() {
    const rows = [...state.rows].sort((a, b) => {
      const x = a[state.sort], y = b[state.sort];
      if (x == null) return y == null ? 0 : 1;
      if (y == null) return -1;
      const d = typeof x === "string" ? x.localeCompare(String(y)) : x - y;
      return state.desc ? -d : d;
    });
    $("segments").innerHTML = rows.length ? rows.map(r => `<tr${r.segment_id === state.selected?.segment_id ? ' class="selected"' : ""}><td><button type="button" class="road-button" data-segment="${escape(r.segment_id)}" aria-pressed="${r.segment_id === state.selected?.segment_id}">${escape(r.route || r.segment_id)}</button><small>${num(r.length_miles)} mi · AADT ${escape(r.aadt_year ?? "year unavailable")}</small></td><td>${num(r.aadt, 0)}</td><td>${num(r.observed, 0)}</td><td>${num(r.rate_per_100m_vmt)}</td><td>${num(r.excess_annual, 3)}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">No road segments found in this area. Try another study area.</td></tr>';
    document.querySelectorAll("[data-sort]").forEach(b => b.parentElement.setAttribute("aria-sort", b.dataset.sort === state.sort ? (state.desc ? "descending" : "ascending") : "none"));
    $("export").disabled = !rows.length;
  }
  function selectSegment(id) {
    state.selected = state.rows.find(r => String(r.segment_id) === id) || null;
    const r = state.selected;
    const synthetic = r?.data_mode === "synthetic";
    $("cost-result").replaceChildren();
    $("applicability").checked = false;
    $("fatal-transfer").checked = false;
    state.calculation++;
    renderRows();
    if (!r) {$("segment-detail").innerHTML = '<p class="muted">Select a road from the table to review its exposure, uncertainty and treatment scenario.</p>'; updateCalculator(); return;}
    const values = [["Fatal crashes observed", num(r.observed, 0)], ["Observation duration", Array.isArray(r.years) ? `${r.years.length} years` : `${num(r.years, 2)} years`], ["Segment length", `${num(r.length_miles)} miles`], ["Daily traffic (AADT)", num(r.aadt, 0)], ["Traffic count year", escape(r.aadt_year ?? "Unavailable")], ["Exposure", `${num(r.exposure_vmt, 0)} VMT`], ["Fatal crashes / 100M VMT", num(r.rate_per_100m_vmt)], ["EB expected / year", num(r.expected_annual, 3)], ["Excess / year", num(r.excess_annual, 3)]];
    const lo = r.lower_annual, hi = r.upper_annual, mid = r.expected_annual;
    let chart = "";
    if ([lo, hi, mid].every(x => x != null && Number.isFinite(Number(x))) && hi >= lo) {
      const max = Math.max(hi * 1.15, mid * 1.15, .01), x = n => 16 + Math.max(0, n) / max * 248;
      chart = `<h3>Expected annual fatal crashes</h3><svg class="uncertainty" viewBox="0 0 280 82" role="img" aria-label="Expected annual fatal crashes ${escape(num(mid, 3))}, model interval ${escape(num(lo, 3))} to ${escape(num(hi, 3))}"><line x1="16" x2="264" y1="34" y2="34" stroke="var(--color-rule-strong)"/><line x1="${x(lo)}" x2="${x(hi)}" y1="34" y2="34" stroke="var(--color-accent)" stroke-width="5"/><circle cx="${x(mid)}" cy="34" r="6" fill="var(--color-accent)"/><text x="16" y="65">0</text><text x="264" y="65" text-anchor="end">${num(max, 3)} / year</text></svg><p class="table-note">Model interval: ${num(lo, 3)}–${num(hi, 3)} per year. Model uncertainty does not include every source of exposure or matching error.</p>`;
    }
    if (synthetic) chart = chart.replaceAll("Expected annual fatal crashes", "Illustrative annual count").replaceAll("Model interval", "Invented example interval").replaceAll("model interval", "invented example interval").replace("Model uncertainty does not include every source of exposure or matching error.", "These bounds were constructed for the demo; they are not estimated uncertainty.");
    $("segment-detail").innerHTML = `<h3 class="segment-name">${escape(r.route || "Road segment")}</h3><span class="segment-id">${escape(r.segment_id)}</span>${synthetic ? '<p class="inline-note"><strong>Invented example.</strong> Every value below is simulated, including the screening estimate.</p>' : ""}<dl>${values.map(([k,v]) => `<div><dt>${synthetic && k === "EB expected / year" ? "Illustrative expected / year" : k}</dt><dd>${v}</dd></div>`).join("")}</dl><p class="inline-note"><strong>Exposure status:</strong> ${escape(r.exposure_status === "aadt_vintage_proxy" ? "Traffic volume from a different year; proxy exposure" : (r.exposure_status || "Review data vintage before use")).replace(/_/g, " ")}</p>${chart}`;
    updateCalculator();
  }
  function updateCalculator() {
    $("calculate").disabled = !(state.selected && $("countermeasure").value && $("applicability").checked && $("fatal-transfer").checked);
    $("scenario-selection").textContent = state.selected ? `Scenario for ${state.selected.route || state.selected.segment_id}. Values are analyst assumptions.` : "Select a road segment first.";
  }
  function treatmentChanged() {
    const c = state.catalog.find(c => String(c.id) === $("countermeasure").value);
    $("applicability").checked = false;
    $("fatal-transfer").checked = false;
    state.calculation++;
    $("cost-result").replaceChildren();
    $("treatment-note").innerHTML = c ? `CMF: ${escape(num(c.cmf, 3))}. ${escape(text(c.applicability || c.conditions || c.description || "Review the source study for applicable roads and crash types."))} ${c.source_url ? link(c.source_url, "Read source study") : ""}${c.requires_transfer_assumption ? " Transferring this CMF to fatal crashes requires an explicit engineering assumption." : ""} Fatalities per fatal crash is a scenario assumption; the default of 1 is not a measured segment average.` : "Select a catalog entry to read its applicability and evidence.";
    updateCalculator();
  }
  async function loadSegments() {
    const seq = ++state.load;
    const query = new URLSearchParams({...areas[$("area").value], limit: $("limit").value});
    $("load").disabled = true;
    $("load-state").classList.remove("error");
    $("load-state").textContent = "Loading the selected area…";
    $("segments").innerHTML = '<tr><td colspan="5" class="empty">Loading road segments…</td></tr>';
    state.rows = []; selectSegment(""); $("export").disabled = true;
    try {
      const data = await request(`/api/safety/segments?${query}`);
      if (seq !== state.load) return;
      state.rows = data.segments || [];
      state.synthetic = data.data_mode === "synthetic";
      renderRows();
      $("segment-summary").textContent = `${num(state.rows.length, 0)} of ${num(data.total ?? state.rows.length, 0)} segments shown · fatal-crash outcome`;
      $("load-state").textContent = state.rows.length ? "Screening loaded. Select a road to inspect its evidence." : "No results. Change the area and load again.";
    } catch (error) {
      if (seq !== state.load) return;
      $("load-state").classList.add("error");
      $("load-state").textContent = `${error.message} Use Load screening to retry.`;
      $("segment-summary").textContent = "Screening unavailable.";
      $("segments").innerHTML = '<tr><td colspan="5" class="empty">Data could not be loaded. Source readiness is shown below.</td></tr>';
    } finally {if (seq === state.load) $("load").disabled = false;}
  }
  async function loadStatus() {
    try {
      const s = await request("/api/safety/status");
      state.synthetic = s.data_mode === "synthetic";
      const years = Array.isArray(s.years) ? [...new Set(s.years.map(Number).filter(Number.isFinite))].sort((a,b) => a-b) : [];
      const window = years.length > 1 && years.at(-1) - years[0] === years.length - 1 ? `${years[0]}–${years.at(-1)}` : years.join(", ");
      $("crash-window").textContent = window ? `FARS fatal-crash observation window: ${window}.` : "FARS observation years are unavailable; check the source snapshot.";
      const q = s.quality || {};
      if (Number.isFinite(q.total_crashes) && q.total_crashes > 0 && Number.isFinite(q.matched)) {
        const excluded = q.total_crashes - q.matched;
        $("linkage-summary").innerHTML = `<strong>Statewide linkage coverage: ${num(q.matched, 0)} / ${num(q.total_crashes, 0)} fatal crashes (${num(q.matched / q.total_crashes * 100, 1)}%) matched to supplied roads.</strong> This covers the full Nebraska dataset${window ? ` for ${escape(window)}` : ""}, not just the selected area. ${num(excluded, 0)} crashes are excluded from segment screening: ${num(q.ambiguous, 0)} ambiguous matches, ${num(q.outside_tolerance, 0)} beyond ${num(q.max_distance_m, 0)} m, and ${num(q.unlocated, 0)} without usable locations.`;
      } else $("linkage-summary").textContent = "Statewide crash-to-road linkage coverage is unavailable. Review the source snapshot before interpreting the segment rankings.";
      const sources = Array.isArray(s.sources) ? s.sources : Object.values(s.sources || {});
      const limitations = s.limitations || [];
      $("readiness").innerHTML = `<div class="evidence-grid"><div><h3>${s.ready ? "Snapshot available" : "Snapshot not built"}<span class="status-tag">${s.commercial_ready ? "Review reuse terms" : "Commercial readiness unconfirmed"}</span></h3><p class="muted">${s.built_at ? `Built ${escape(new Date(s.built_at).toLocaleString())}.` : "The data pipeline must finish before screening can run."} ${escape(text(s.scope || "Nebraska fatal-crash research screening"))}${Array.isArray(s.years) ? `. Crash years: ${escape(s.years.join(", "))}.` : ""}</p>${limitations.length ? `<ul>${limitations.map(x => `<li>${escape(text(x))}</li>`).join("")}</ul>` : ""}<details><summary>Quality, model and feed diagnostics</summary><pre class="diagnostic">${escape(JSON.stringify({quality: s.quality, metrics: s.metrics, model: s.model, feeds: s.feeds, monitoring: s.monitoring}, null, 2))}</pre></details></div><div><h3>Source register</h3>${sources.map(source => `<div class="source"><strong>${source.url ? link(source.url, source.name || source.id || "Source") : escape(source.name || source.id || "Source")}</strong><p>${escape(text(source.rights || source.license || "Review original terms"))}</p><p>Commercial use: ${source.commercial_use === true ? "permitted per source register" : "not cleared for this engine"}. ${escape(text(source.scope || ""))}</p></div>`).join("") || '<p class="muted">No sources reported.</p>'}</div></div>`;
      if (!s.legacy_explorer_url) document.querySelectorAll('a[href="/"],a[href="models.html"]').forEach(a => {if (a.classList.contains("wordmark")) a.href = "safety.html"; else a.hidden = true;});
      else document.querySelectorAll('a[href="/"],a[href="models.html"]').forEach(a => {a.href = a.getAttribute("href") === "models.html" ? new URL("models.html", new URL(s.legacy_explorer_url, location.origin)).href : s.legacy_explorer_url;});
      if (s.public_portal_url === "/") {
        document.querySelector(".wordmark").href = "/";
        const home = document.querySelector("nav a");
        home.hidden = false; home.href = "/"; home.textContent = "3D map";
      }
      if (state.synthetic) {
        document.title = "Synthetic workflow demo · GeoCrash";
        document.querySelector("h1").textContent = "Road safety workflow demo";
        document.querySelector(".area-note").textContent = "Synthetic examples · no real road risk";
        $("dataset-notice").replaceChildren();
        const label = document.createElement("strong"); label.textContent = "Synthetic demonstration. ";
        $("dataset-notice").append(label, "All roads, crash counts, exposure, predictions and intervals are invented. Use this workspace to explore the workflow; these are not measured results or engineering recommendations.");
        $("linkage-summary").textContent = "24 fictional corridors near Omaha and Lincoln. No real road or person is represented; no model was trained for this demonstration.";
        document.querySelectorAll('#model-evidence, #behavior, a[href="#model-evidence"], a[href="#behavior"]').forEach(el => {el.hidden = true;});
        document.querySelector("footer").textContent = "Synthetic workflow demonstration. Model benchmarks and official recorded-factor evidence are available only in the separate research evaluation.";
      }
    } catch (error) {$("readiness").textContent = `Source status unavailable: ${error.message}`; if ($("crash-window")) $("crash-window").textContent = "FARS observation years could not be verified."; $("linkage-summary").textContent = "Linkage coverage could not be loaded. Reload the page to verify the crash-to-road matching scope before interpreting results.";}
  }
  async function loadCatalog() {
    try {
      const data = await request("/api/safety/countermeasures");
      state.catalog = Array.isArray(data) ? data : data.countermeasures || [];
      $("countermeasure").innerHTML = '<option value="">Select a treatment to evaluate</option>' + state.catalog.map(c => `<option value="${escape(c.id)}">${escape(c.name)}</option>`).join("");
      $("countermeasure").disabled = !state.catalog.length;
      if (!state.catalog.length) $("treatment-note").textContent = "No countermeasures are available in the source catalog.";
    } catch (error) {$("countermeasure").innerHTML = '<option value="">Catalog unavailable</option>'; $("treatment-note").textContent = `Catalog could not load: ${error.message} Reload the page to retry.`;}
  }
  $("area-form").addEventListener("submit", e => {e.preventDefault(); loadSegments();});
  $("segments").addEventListener("click", e => {const b = e.target.closest("[data-segment]"); if (b) selectSegment(b.dataset.segment);});
  document.querySelectorAll("[data-sort]").forEach(b => b.addEventListener("click", () => {state.desc = state.sort === b.dataset.sort ? !state.desc : b.dataset.sort !== "route"; state.sort = b.dataset.sort; renderRows();}));
  $("countermeasure").addEventListener("change", treatmentChanged);
  $("applicability").addEventListener("change", updateCalculator);
  $("fatal-transfer").addEventListener("change", updateCalculator);
  $("cost-form").addEventListener("input", () => {state.calculation++; $("cost-result").replaceChildren();});
  $("cost-form").addEventListener("submit", async e => {
    e.preventDefault();
    if (!state.selected || !$("applicability").checked || !$("fatal-transfer").checked) return;
    const calc = ++state.calculation;
    const segmentId = state.selected.segment_id;
    $("calculate").disabled = true; $("cost-result").textContent = "Calculating scenario…";
    try {
      const r = await request("/api/safety/benefit-cost", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({segment_id: segmentId, countermeasure_id: $("countermeasure").value, implementation_cost: Number($("implementation-cost").value), annual_maintenance_cost: Number($("maintenance-cost").value), service_life_years: Number($("service-life").value), discount_rate: Number($("discount-rate").value) / 100, fatalities_per_crash: Number($("fatalities-per-crash").value), eligible_fraction: Number($("eligible-fraction").value) / 100, applicability_confirmed: true, fatal_transfer_assumption_confirmed: true})});
      if (state.selected?.segment_id !== segmentId || calc !== state.calculation) return;
      const values = [["Benefit–cost ratio", num(r.benefit_cost_ratio)], ["Net present value", money(r.net_present_value)], ["Present value of benefits", money(r.present_value_benefits)], ["Fatal crashes avoided / year", num(r.annual_fatal_crashes_prevented ?? r.annual_crashes_prevented, 3)]];
      $("cost-result").innerHTML = `<div class="result-grid">${values.map(([label,value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("")}</div><p class="table-note">Scenario output only. Present value of costs: ${money(r.present_value_costs)}. ${(r.limitations || []).map(x => escape(text(x))).join(" ")}</p><details><summary>Full scenario assumptions and calculation</summary><pre class="diagnostic">${escape(JSON.stringify(r, null, 2))}</pre></details>`;
    } catch (error) {if (calc === state.calculation) $("cost-result").innerHTML = `<p class="result-error">${escape(error.message)} Check the assumptions and try again.</p>`;} finally {updateCalculator();}
  });
  $("export").addEventListener("click", () => {
    const fields = ["data_mode", "segment_id", "route", "lat", "lng", "length_miles", "aadt", "aadt_year", "observed", "years", "exposure_vmt", "rate_per_100m_vmt", "expected_annual", "excess_annual", "lower_annual", "upper_annual", "exposure_status"];
    const csv = value => '"' + String(value ?? "").replace(/^[=+@-]/, "'$&").replace(/"/g, '""') + '"';
    const rows = [fields, ...state.rows.map(row => fields.map(key => Array.isArray(row[key]) ? row[key].join(";") : row[key]))];
    const url = URL.createObjectURL(new Blob([rows.map(row => row.map(csv).join(",")).join("\r\n")], {type: "text/csv;charset=utf-8"}));
    const a = document.createElement("a"); a.href = url; a.download = `geocrash-${$("area").value}-${state.synthetic ? "SYNTHETIC-demo" : "research-screening"}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  Promise.allSettled([loadSegments(), loadStatus(), loadCatalog()]);
})();
