"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = (value, digits = 3) => value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: digits}) : "Unavailable";
  const percent = value => value == null ? "Unavailable" : `${number(value * 100, 1)}%`;
  const names = {exposure: "Traffic-exposure baseline", negative_binomial: "Negative-binomial SPF", poisson_boosting: "Poisson boosted trees", gated_mixture: "Learned expert mixture", historical_eb: "Historical empirical Bayes"};
  let benchmark, behavior;
  async function get(path) {
    const response = await fetch(path, {headers: {Accept: "application/json"}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Analysis unavailable (${response.status})`);
    return data;
  }
  function methods(target, items, report) {
    $(target).innerHTML = `<div class="method-copy"><ul>${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div><details><summary>Complete reproducible report</summary><pre class="diagnostic">${esc(JSON.stringify(report, null, 2))}</pre></details>`;
  }
  function renderBenchmark() {
    if (!benchmark) return;
    const protocol = $("benchmark-protocol").value;
    const result = benchmark[protocol];
    if (!result?.models) {$("benchmark-summary").textContent = "This evaluation is unavailable in the current report."; $("benchmark-results").replaceChildren(); return;}
    const winner = benchmark.decision?.best_development_challenger;
    $("benchmark-summary").textContent = `${number(benchmark.segments, 0)} roads · ${number(benchmark.fatal_crashes, 0)} matched fatal crashes. ${protocol === "temporal" ? `Train ${result.training_years?.join(", ")}; evaluate ${result.holdout_year}.` : `${result.folds?.length || 0} folds with disjoint geographic blocks.`} ${winner ? `${names[winner] || winner} passed the development comparison rule; independent validation is still required.` : "No challenger passed the rule for improvement on both evaluation tasks."}`;
    $("benchmark-results").innerHTML = `<div class="table-scroll" role="region" tabindex="0" aria-label="Model comparison"><table><thead><tr><th scope="col">Model</th><th scope="col">Poisson deviance ↓</th><th scope="col">Mean absolute error ↓</th><th scope="col">Predicted / observed</th><th scope="col">Crashes in top 10% of rows</th><th scope="col">Improvement vs SPF</th></tr></thead><tbody>${Object.entries(result.models).map(([name, m]) => {
      const comparison = result.comparisons?.[name]?.negative_binomial;
      const gain = comparison ? `${percent(comparison.relative_improvement)}<small>Deviance difference interval: ${number(comparison.lower, 5)} to ${number(comparison.upper, 5)}</small>` : "Reference";
      return `<tr><td>${esc(names[name] || name)}${name === "historical_eb" ? '<span class="comparison-note">Uses prior-year crashes on this road; unavailable for unseen roads.</span>' : ""}</td><td>${number(m.mean_poisson_deviance, 5)}</td><td>${number(m.mae, 5)}</td><td>${number(m.predicted_fatal_crashes, 1)} / ${number(m.observed_fatal_crashes, 0)}</td><td>${percent(m.top_decile_row_crash_capture)}</td><td>${gain}</td></tr>`;
    }).join("")}</tbody></table></div>`;
    methods("benchmark-methods", [
      `Inputs: ${(benchmark.features || []).join(", ")}. Road context uses the published network; nearby-road counts use segment midpoints, not intersections.`,
      "Positive improvement favors the challenger. An interval spanning zero is inconclusive; the intervals resample geographic blocks and adjust for the candidate comparisons.",
      benchmark.decision?.rule || "No automatic model promotion.", ...(benchmark.limitations || [])
    ], benchmark);
  }
  function renderBehavior() {
    if (!behavior) return;
    const geography = $("behavior-scope").value, year = $("behavior-year").value;
    const cohort = behavior.cohorts?.find(c => (geography === "national" ? c.scope === "national" : c.scope === "state" && Number(c.state_fips) === Number(geography)) && (year === "all" ? c.year == null : Number(c.year) === Number(year)));
    if (!cohort) {$("behavior-summary").textContent = "No cohort is available for this selection."; $("behavior-results").replaceChildren(); return;}
    $("behavior-summary").textContent = `${number(cohort.fatal_crashes, 0)} fatal crashes · ${geography === "national" ? "United States" : "Nebraska statewide"} · ${year === "all" ? behavior.years.join("–") : year}. Fractions use only crashes with a known factor finding; completeness differs by factor.`;
    const labels = {speeding: "Speeding recorded", reported_alcohol: "Alcohol involvement reported", distraction: "Distraction recorded"};
    $("behavior-results").innerHTML = `<div class="table-scroll" role="region" tabindex="0" aria-label="Recorded behavioral factors"><table><thead><tr><th scope="col">Factor</th><th scope="col">Recorded yes</th><th scope="col">Recorded no</th><th scope="col">Unknown</th><th scope="col">Not applicable</th><th scope="col">Share among known cases</th></tr></thead><tbody>${Object.entries(cohort.factors).map(([key, f]) => {
      const interval = f.known_fraction_interval95;
      return `<tr><td>${esc(labels[key] || key)}</td><td>${number(f.yes, 0)}</td><td>${number(f.no, 0)}</td><td>${number(f.unknown, 0)}</td><td>${number(f.not_applicable, 0)}</td><td>${percent(f.fraction_among_known)}${f.fraction_among_known != null ? `<meter min="0" max="1" value="${f.fraction_among_known}" aria-label="${esc(labels[key] || key)} share among known cases"></meter>` : ""}${interval ? `<small>95% interval ${percent(interval[0])}–${percent(interval[1])}</small>` : ""}</td></tr>`;
    }).join("")}</tbody></table></div>`;
    methods("behavior-methods", [...Object.entries(behavior.definitions || {}).map(([key, definition]) => `${labels[key] || key}: ${typeof definition === "string" ? definition : JSON.stringify(definition)}`), ...(behavior.limitations || [])], behavior);
  }
  $("benchmark-protocol").addEventListener("change", renderBenchmark);
  $("behavior-scope").addEventListener("change", renderBehavior);
  $("behavior-year").addEventListener("change", renderBehavior);
  Promise.allSettled([
    get("/api/safety/model-evidence").then(data => {benchmark = data; renderBenchmark();}).catch(error => {$("benchmark-summary").textContent = `${error.message}. Reload after the analysis is built.`;}),
    get("/api/safety/behavior").then(data => {behavior = data; $("behavior-year").innerHTML += (data.years || []).map(year => `<option value="${esc(year)}">${esc(year)}</option>`).join(""); renderBehavior();}).catch(error => {$("behavior-summary").textContent = `${error.message}. Reload after the analysis is built.`;})
  ]);
})();
