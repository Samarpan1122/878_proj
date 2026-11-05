"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const state = {rows: [], selected: null, catalog: [], candidates: [], sort: "excess_annual", load: 0, projection: 0, portfolio: 0, synthetic: false};
  const areas = {omaha: {lat: 41.2565, lng: -95.9345, radius_km: 30}, lincoln: {lat: 40.8136, lng: -96.7026, radius_km: 30}, nebraska: {}};
  const sortLabels = {observed: "fatal crashes", rate_per_100m_vmt: "rate per 100M VMT", excess_annual: "excess per year"};
  const MAX_CANDIDATES = 30;
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const isNum = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  const num = (value, digits = 2) => isNum(value) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: digits}) : "Not available";
  const money = value => isNum(value) ? Number(value).toLocaleString(undefined, {style: "currency", currency: "USD", maximumFractionDigits: 0}) : "Not available";
  const text = value => typeof value === "object" && value !== null ? JSON.stringify(value) : String(value ?? "");
  const yearSpan = years => {const ys = [...new Set((years || []).map(Number).filter(Number.isFinite))].sort((a, b) => a - b); return ys.length > 1 ? `${ys[0]}–${ys.at(-1)}` : ys.length ? String(ys[0]) : "";};
  const list = items => items.map(x => `<li>${escape(text(x))}</li>`).join("");
  const link = (url, label) => {try {const u = new URL(url); return ["https:", "http:"].includes(u.protocol) ? `<a href="${escape(u.href)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>` : escape(label);} catch {return escape(label);}};
  const fieldValue = id => Number($(id).value);

  async function request(path, body) {
    const options = body === undefined ? {headers: {Accept: "application/json"}} : {method: "POST", headers: {Accept: "application/json", "Content-Type": "application/json"}, body: JSON.stringify(body)};
    const response = await fetch(path, options).catch(() => {throw new Error("Could not reach the server. Check your connection.");});
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data?.detail;
      const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(x => `${(x.loc || []).slice(1).join(".") || "request"}: ${x.msg}`).join("; ") : `Request failed (${response.status}).`;
      throw new Error(/[.!?]$/.test(message) ? message : `${message}.`);
    }
    if (data === null) throw new Error("The server returned an unreadable response.");
    return data;
  }

  function renderRows() {
    const id = state.selected?.segment_id;
    $("segments").innerHTML = state.rows.length ? state.rows.map(r => `<tr${r.segment_id === id ? ' class="selected"' : ""}><td><button type="button" class="road-button" data-segment="${escape(r.segment_id)}" aria-pressed="${r.segment_id === id}">${escape(r.route || r.segment_id)}</button><small>${num(r.length_miles)} mi · AADT ${escape(r.aadt_year ?? "year unavailable")}</small></td><td>${num(r.aadt, 0)}</td><td>${num(r.observed, 0)}</td><td>${num(r.rate_per_100m_vmt)}</td><td>${num(r.excess_annual, 3)}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">No road segments found in this area. Try another study area.</td></tr>';
    $("export").disabled = !state.rows.length;
  }

  function renderDetail() {
    const r = state.selected;
    $("segment-tools").hidden = !r;
    if (!r) {$("segment-detail").innerHTML = '<p class="muted">Select a road from the table to review its exposure and uncertainty.</p>'; return;}
    const duration = Array.isArray(r.years) ? yearSpan(r.years) : `${num(r.years)} years`;
    const values = [["Fatal crashes observed", num(r.observed, 0)], ["Observation period", escape(duration)], ["Segment length", `${num(r.length_miles)} miles`], ["Daily traffic (AADT)", num(r.aadt, 0)], ["Traffic count year", escape(r.aadt_year ?? "Unavailable")], ["Exposure", `${num(r.exposure_vmt, 0)} VMT`], ["Fatal crashes / 100M VMT", num(r.rate_per_100m_vmt)], ["EB expected / year", num(r.expected_annual, 3)], ["Excess / year", num(r.excess_annual, 3)]];
    const lo = Number(r.lower_annual), hi = Number(r.upper_annual), mid = Number(r.expected_annual);
    let chart = "";
    if ([r.lower_annual, r.upper_annual, r.expected_annual].every(isNum) && hi >= lo) {
      const max = Math.max(hi * 1.15, mid * 1.15, .01), x = n => 16 + Math.max(0, n) / max * 248;
      chart = `<h3>Expected annual fatal crashes</h3><svg class="uncertainty" viewBox="0 0 280 82" role="img" aria-label="Expected annual fatal crashes ${num(mid, 3)}, model interval ${num(lo, 3)} to ${num(hi, 3)}"><line x1="16" x2="264" y1="34" y2="34" stroke="var(--color-rule-strong)"/><line x1="${x(lo)}" x2="${x(hi)}" y1="34" y2="34" stroke="var(--color-accent)" stroke-width="5"/><circle cx="${x(mid)}" cy="34" r="6" fill="var(--color-accent)"/><text x="16" y="65">0</text><text x="264" y="65" text-anchor="end">${num(max, 3)} / year</text></svg><p class="table-note">Model interval: ${num(lo, 3)}–${num(hi, 3)} per year. It excludes traffic-volume, road-matching and parameter uncertainty.</p>`;
    }
    const exposure = r.exposure_status === "aadt_vintage_proxy" ? "Traffic volume from a different year than the crashes; proxy exposure" : String(r.exposure_status || "Review data vintage before use").replace(/_/g, " ");
    $("segment-detail").innerHTML = `<h3 class="segment-name">${escape(r.route || "Road segment")}</h3><span class="segment-id">${escape(r.segment_id)}</span>${state.synthetic || r.data_mode === "synthetic" ? '<p class="inline-note"><strong>Invented example.</strong> Every value below is simulated.</p>' : ""}<dl>${values.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl><p class="inline-note"><strong>Exposure:</strong> ${escape(exposure)}</p>${chart}`;
  }

  function selectSegment(id) {
    state.selected = state.rows.find(r => String(r.segment_id) === id) || null;
    state.projection++;
    renderRows();
    renderDetail();
    $("projection-result").replaceChildren();
    $("candidate-status").textContent = "";
    $("applicability").checked = false;
    $("transfer").checked = false;
    if (!state.selected) return;
    $("projection-year").value = Math.min(2035, Math.max(2025, new Date().getFullYear() + 1));
    $("projection-aadt").value = isNum(state.selected.aadt) ? Math.round(state.selected.aadt) : "";
    if (matchMedia("(max-width: 740px)").matches) $("detail-title").scrollIntoView({block: "start"});
  }

  async function loadSegments() {
    const seq = ++state.load;
    const query = new URLSearchParams({...areas[$("area").value], limit: $("limit").value, sort: state.sort});
    document.querySelectorAll("[data-sort]").forEach(b => b.parentElement.setAttribute("aria-sort", b.dataset.sort === state.sort ? "descending" : "none"));
    $("load").disabled = true;
    $("load-state").classList.remove("error");
    $("load-state").textContent = "Loading the selected area…";
    try {
      const data = await request(`/api/safety/segments?${query}`);
      if (seq !== state.load) return;
      state.rows = Array.isArray(data.segments) ? data.segments : [];
      if (data.data_mode === "synthetic") state.synthetic = true;
      const keep = state.rows.find(r => r.segment_id === state.selected?.segment_id);
      if (keep) {state.selected = keep; renderRows();} else selectSegment("");
      $("segment-summary").textContent = `${num(state.rows.length, 0)} of ${num(data.total ?? state.rows.length, 0)} segments · highest ${sortLabels[state.sort]} first`;
      $("load-state").textContent = state.rows.length ? "Screening loaded. Select a road to inspect it." : "No results. Change the area and load again.";
    } catch (error) {
      if (seq !== state.load) return;
      state.rows = []; selectSegment("");
      $("load-state").classList.add("error");
      $("load-state").textContent = `${error.message} Use Load screening to retry.`;
      $("segment-summary").textContent = "Screening unavailable.";
      $("segments").innerHTML = '<tr><td colspan="5" class="empty">Road segments could not be loaded.</td></tr>';
    } finally {if (seq === state.load) $("load").disabled = false;}
  }

  function retryButton(onClick) {
    const b = document.createElement("button"); b.type = "button"; b.className = "retry"; b.textContent = "Retry";
    b.addEventListener("click", onClick, {once: true});
    return b;
  }

  async function loadStatus() {
    $("notice-text").innerHTML = "<strong>Experimental screening, not an agency-validated ranking.</strong> Loading crash years and road-matching coverage…";
    try {
      const s = await request("/api/safety/status");
      if (s.public_portal_url !== "/") document.querySelectorAll(".app-header nav a").forEach(a => {if (a.hasAttribute("aria-current")) a.href = location.pathname; else a.hidden = true;});
      state.synthetic = s.data_mode === "synthetic";
      const years = yearSpan(s.years);
      const q = s.quality || {};
      const linked = Number.isFinite(q.total_crashes) && q.total_crashes > 0 && Number.isFinite(q.matched);
      const coverage = linked ? `${num(q.matched, 0)} of ${num(q.total_crashes, 0)} Nebraska fatal crashes (${num(q.matched / q.total_crashes * 100, 1)}%) are matched to a road; the rest are excluded.` : "Road-matching coverage is unavailable.";
      const caveats = [...(linked ? [`Excluded from screening statewide: ${num(q.ambiguous, 0)} ambiguous matches, ${num(q.outside_tolerance, 0)} crashes more than ${num(q.max_distance_m, 0)} m from a road, ${num(q.unlocated, 0)} without a usable location.`] : []), ...(Array.isArray(s.limitations) ? s.limitations : [])];
      $("caveats").innerHTML = caveats.length ? list(caveats) : "<li>No further caveats reported.</li>";
      if (state.synthetic) {
        document.title = "Synthetic workflow demo · GeoCrash";
        document.querySelector("h1").textContent = "Road safety workflow demo";
        $("notice-text").innerHTML = "<strong>Synthetic demonstration.</strong> All roads, crash counts, exposure, predictions and intervals are invented. These are not measured results or engineering recommendations.";
      } else {
        $("notice-text").innerHTML = `<strong>Experimental screening, not an agency-validated ranking.</strong> FARS fatal crashes${years ? ` ${escape(years)}` : ""} are paired with current NDOT traffic counts, a proxy for earlier years. ${coverage}`;
      }
      if (state.selected) renderDetail();
    } catch (error) {
      $("notice-text").innerHTML = `<strong>Experimental screening, not an agency-validated ranking.</strong> Crash years and road-matching coverage could not be loaded: ${escape(error.message)} `;
      $("notice-text").append(retryButton(loadStatus));
      $("caveats").innerHTML = "<li>Caveats are unavailable until the data status loads.</li>";
    }
  }

  async function loadCatalog() {
    $("catalog-state").textContent = "";
    try {
      const data = await request("/api/safety/countermeasures");
      state.catalog = Array.isArray(data) ? data : data.countermeasures || [];
      $("countermeasure").innerHTML = state.catalog.map(c => `<option value="${escape(c.id)}">${escape(c.name)} (CMF ${escape(c.id)})</option>`).join("") || '<option value="">No countermeasures available</option>';
      $("countermeasure").disabled = $("add-candidate").disabled = !state.catalog.length;
      treatmentChanged();
    } catch (error) {
      $("countermeasure").innerHTML = '<option value="">Catalog unavailable</option>';
      $("catalog-state").innerHTML = `<span class="error">Countermeasures could not load: ${escape(error.message)}</span> `;
      $("catalog-state").append(retryButton(loadCatalog));
    }
  }

  function treatmentChanged() {
    const c = state.catalog.find(c => String(c.id) === $("countermeasure").value);
    $("applicability").checked = false;
    $("transfer").checked = false;
    $("catalog-state").innerHTML = c ? `CMF ${escape(num(c.cmf, 3))}. ${escape(text(c.conditions || c.applicability || c.description || "Review the source study for applicable roads and crash types."))} ${c.source_url ? link(c.source_url, "Read the source study") : ""}` : "";
  }

  function invalidatePortfolio() {
    state.portfolio++;
    $("portfolio-result").replaceChildren();
  }

  function renderCandidates() {
    const n = state.candidates.length;
    $("candidate-count").textContent = `${n} road${n === 1 ? "" : "s"}`;
    $("run-portfolio").disabled = !n;
    $("candidate-list").innerHTML = n ? state.candidates.map(c => `<li><div><strong>${escape(c.route)}</strong> <span class="segment-id">${escape(c.segment_id)}</span><span class="small">${money(c.implementation_cost)} installation · ${money(c.annual_maintenance_cost)}/yr maintenance · ${num(c.eligible_fraction * 100)}% eligible · ${num(c.fatalities_per_crash)} fatalities / fatal crash</span></div><button type="button" data-remove="${escape(c.candidate_id)}" aria-label="Remove ${escape(c.route)} from the budget">Remove</button></li>`).join("") : '<li class="muted">No roads yet. Select a road and use Add to budget.</li>';
  }

  $("candidate-form").addEventListener("submit", e => {
    e.preventDefault();
    const r = state.selected;
    if (!r || !$("applicability").checked || !$("transfer").checked) return;
    const others = state.candidates.filter(c => c.segment_id !== r.segment_id);
    if (others.length >= MAX_CANDIDATES) {$("candidate-status").textContent = `A budget comparison supports up to ${MAX_CANDIDATES} roads. Remove one first.`; return;}
    const candidate = {route: r.route || r.segment_id, candidate_id: `road-${r.segment_id}`, segment_id: r.segment_id, countermeasure_id: $("countermeasure").value, implementation_cost: fieldValue("install"), annual_maintenance_cost: fieldValue("maintenance"), fatalities_per_crash: fieldValue("fatalities"), eligible_fraction: fieldValue("eligible") / 100, applicability_confirmed: true, fatal_transfer_assumption_confirmed: true};
    const replaced = others.length !== state.candidates.length;
    state.candidates = [...others, candidate];
    invalidatePortfolio();
    renderCandidates();
    $("applicability").checked = false;
    $("transfer").checked = false;
    $("candidate-status").textContent = `${replaced ? "Updated" : "Added"} ${candidate.route} in the treatment budget below.`;
  });
  $("candidate-list").addEventListener("click", e => {
    const b = e.target.closest("[data-remove]");
    if (!b) return;
    state.candidates = state.candidates.filter(c => c.candidate_id !== b.dataset.remove);
    invalidatePortfolio();
    renderCandidates();
    $("budget-title").focus();
  });

  $("projection-form").addEventListener("input", () => {state.projection++; $("projection-result").replaceChildren();});
  $("projection-form").addEventListener("submit", async e => {
    e.preventDefault();
    const r = state.selected;
    if (!r) return;
    const seq = ++state.projection;
    const button = e.submitter || $("projection-form").querySelector("button");
    button.disabled = true;
    $("projection-result").innerHTML = '<p class="small">Projecting…</p>';
    try {
      const d = await request("/api/safety/projection", {segment_id: r.segment_id, target_year: fieldValue("projection-year"), aadt: fieldValue("projection-aadt"), scenario_note: $("projection-note").value});
      if (seq !== state.projection || state.selected?.segment_id !== r.segment_id) return;
      const mean = d.conditional_mean_interval95 || {}, count = d.predictive_count_interval95 || {};
      $("projection-result").innerHTML = `<p class="projection"><span>Expected fatal crashes / year in ${escape(d.target_year)}</span><strong>${num(d.mean_annual_fatal_crashes, 3)}</strong><span>95% interval ${num(mean.lower, 3)}–${num(mean.upper, 3)} · ${num(d.baseline_aadt_mean_annual_fatal_crashes, 3)} at current AADT</span></p><p class="small">Actual count that year: ${num(count.lower, 0)}–${num(count.upper, 0)} crashes (95%). A conditional scenario from the fitted model, not a validated forecast: it assumes the road's historical risk persists and only traffic changes.</p>${Array.isArray(d.limitations) && d.limitations.length ? `<details><summary>Projection assumptions</summary><ul>${list(d.limitations)}</ul></details>` : ""}`;
    } catch (error) {
      if (seq === state.projection) $("projection-result").innerHTML = `<p class="error">${escape(error.message)} Check the inputs and try again.</p>`;
    } finally {button.disabled = false;}
  });

  function renderPortfolio(d) {
    const t = d.totals || {}, selected = new Set(d.selected_candidate_ids || []), cands = Array.isArray(d.candidates) ? d.candidates : [];
    const s = d.cmf_sensitivity || {};
    const grid = [["Installation cost", money(t.implementation_cost)], ["Benefit–cost ratio", num(t.benefit_cost_ratio)], ["Societal net present value", money(t.net_present_value)], ["Fatal crashes prevented / year", num(t.annual_fatal_crashes_prevented, 3)]];
    const rows = cands.map(c => {const a = c.appraisal || {}; return `<tr${selected.has(c.candidate_id) ? ' class="selected"' : ""}><td>${escape(c.route || c.segment_id)}<small>${escape(c.segment_id)}</small></td><td>${selected.has(c.candidate_id) ? "Selected" : "Not selected"}</td><td>${money(a.implementation_cost)}</td><td>${num(a.benefit_cost_ratio)}</td><td>${money(a.net_present_value)}</td><td>${num(a.annual_fatal_crashes_prevented, 3)}</td></tr>`;}).join("");
    $("portfolio-result").innerHTML = `<p class="result-lead">${selected.size ? `${selected.size} of ${cands.length} road${cands.length === 1 ? "" : "s"} selected within ${money(d.budget)}; ${money(t.unallocated_implementation_budget)} unallocated.` : "No road is selected: none fits the budget with a positive net value."}</p>${selected.size ? `<div class="result-grid">${grid.map(([k, v]) => `<div><span>${k}</span><strong>${v}</strong></div>`).join("")}</div>` : ""}<div class="table-scroll" tabindex="0" role="region" aria-label="Budget comparison by road"><table><thead><tr><th scope="col">Road</th><th scope="col">Result</th><th scope="col">Installation</th><th scope="col">Benefit–cost</th><th scope="col">Net present value</th><th scope="col">Crashes prevented / yr</th></tr></thead><tbody>${rows}</tbody></table></div><p class="table-note">Benefits are USDOT value-of-statistical-life estimates for society, not agency cash savings. ${selected.size && isNum(s.societal_npv_lower) && isNum(s.societal_npv_upper) ? `With the CMF at its published uncertainty bounds, societal net value ranges ${money(s.societal_npv_lower)}–${money(s.societal_npv_upper)}.` : ""} Present value of benefits ${money(t.societal_safety_benefits_present_value)}; of costs ${money(t.present_value_costs)}.</p>${Array.isArray(d.interpretation) ? `<details><summary>How to read this result</summary><ul>${list(d.interpretation)}</ul></details>` : ""}`;
  }

  $("portfolio-form").addEventListener("input", invalidatePortfolio);
  $("portfolio-form").addEventListener("submit", async e => {
    e.preventDefault();
    if (!state.candidates.length) return;
    const seq = ++state.portfolio;
    const body = {budget: fieldValue("budget"), candidates: state.candidates.map(({route, ...c}) => ({...c, service_life_years: fieldValue("life"), discount_rate: fieldValue("discount") / 100}))};
    $("run-portfolio").disabled = true;
    $("portfolio-result").innerHTML = '<p class="small">Comparing…</p>';
    try {
      const d = await request("/api/safety/planning/portfolio", body);
      if (seq === state.portfolio) renderPortfolio(d);
    } catch (error) {
      if (seq === state.portfolio) $("portfolio-result").innerHTML = `<p class="error">${escape(error.message)} Check the assumptions and try again.</p>`;
    } finally {$("run-portfolio").disabled = !state.candidates.length;}
  });

  $("area-form").addEventListener("submit", e => {e.preventDefault(); loadSegments();});
  $("segments").addEventListener("click", e => {const b = e.target.closest("[data-segment]"); if (b) selectSegment(b.dataset.segment);});
  document.querySelectorAll("[data-sort]").forEach(b => b.addEventListener("click", () => {state.sort = b.dataset.sort; loadSegments();}));
  $("countermeasure").addEventListener("change", treatmentChanged);
  $("export").addEventListener("click", () => {
    const fields = ["segment_id", "route", "lat", "lng", "length_miles", "aadt", "aadt_year", "observed", "years", "exposure_vmt", "rate_per_100m_vmt", "expected_annual", "excess_annual", "lower_annual", "upper_annual", "exposure_status"];
    const csv = value => '"' + (typeof value === "string" ? value.replace(/^[=+@-]/, "'$&") : String(value ?? "")).replace(/"/g, '""') + '"';
    const rows = [fields, ...state.rows.map(row => fields.map(key => Array.isArray(row[key]) ? row[key].join(";") : row[key]))];
    const url = URL.createObjectURL(new Blob([rows.map(row => row.map(csv).join(",")).join("\r\n")], {type: "text/csv;charset=utf-8"}));
    const a = document.createElement("a"); a.href = url; a.download = `geocrash-${$("area").value}-${state.synthetic ? "SYNTHETIC-demo" : "screening"}-by-${state.sort}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  renderCandidates();
  Promise.allSettled([loadSegments(), loadStatus(), loadCatalog()]);
})();
