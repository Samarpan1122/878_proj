"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const num = (value, digits = 3) => value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: digits}) : "Unavailable";
  const names = {hist_gradient_boosting: "Boosted trees", residual_mlp: "Residual neural network", soft_mixture_of_experts: "Three-expert neural network", validation_blend: "Validation-selected blend", training_prior: "Training-prior baseline"};
  let report;
  function render() {
    const run = report?.runs?.find(r => r.protocol === $("advanced-protocol").value && String(r.source_feature) === $("advanced-source").value);
    if (!run) {$("advanced-status").textContent = "This comparison is not available yet. Refresh after the experiment finishes."; $("advanced-results").replaceChildren(); return;}
    $("advanced-status").textContent = `${num(report.sample_rows, 0)} sampled incidents · train ${num(run.split.train.rows, 0)}, validation ${num(run.split.validation.rows, 0)}, test ${num(run.split.test.rows, 0)}. Selected by validation classification log loss: ${names[run.selected_on_validation_log_loss] || run.selected_on_validation_log_loss}.${report.status !== "complete" ? " Experiment still running; these are completed comparisons only." : ""}`;
    $("advanced-results").innerHTML = `<div class="wrap" tabindex="0" role="region" aria-label="Advanced research model comparison"><table><thead><tr><th scope="col">Model</th><th scope="col">ROC AUC ↑</th><th scope="col">PR AUC ↑</th><th scope="col">Brier ↓</th><th scope="col">Duration MAE ↓</th><th scope="col">Log-duration R² ↑</th><th scope="col">Brier improvement vs trees</th></tr></thead><tbody>${run.models.map(model => {
      const m = model.test, comparison = model.paired_vs_boosting?.brier_improvement;
      const interval = comparison ? `${num(comparison.estimate, 4)}<small>95% interval ${num(comparison.lower95, 4)} to ${num(comparison.upper95, 4)}</small>` : "Reference";
      return `<tr${model.model === run.selected_on_validation_log_loss ? ' class="selected-model"' : ""}><td>${esc(names[model.model] || model.model)}${model.temperature_fit_on_validation != null ? '<small>Probability calibration uses validation data.</small>' : ""}</td><td>${num(m.roc_auc)}</td><td>${num(m.pr_auc)}</td><td>${num(m.brier, 4)}</td><td>${num(m.duration_mae_minutes, 1)} min</td><td>${num(m.duration_r2_log)}</td><td>${interval}</td></tr>`;
    }).join("")}</tbody></table></div><p class="advanced-note">Positive Brier improvement favors the candidate. Intervals are exploratory comparisons across geographic test blocks, conditional on the fitted models. A negative R² means the model is worse than predicting the test-set mean for that target.</p>`;
    $("advanced-details").textContent = JSON.stringify({dataset: report.dataset, status: report.status, configuration: report.config, limitations: report.limitations, experiment: run}, null, 2);
  }
  async function load() {
    $("advanced-refresh").disabled = true;
    try {
      const response = await fetch("/api/research/advanced", {headers: {Accept: "application/json"}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Comparison unavailable");
      report = data; render();
    } catch (error) {$("advanced-status").textContent = `${error.message}. Use Refresh comparison after the research run finishes.`;}
    finally {$("advanced-refresh").disabled = false;}
  }
  $("advanced-protocol").addEventListener("change", render);
  $("advanced-source").addEventListener("change", render);
  $("advanced-refresh").addEventListener("click", load);
  load();
})();
