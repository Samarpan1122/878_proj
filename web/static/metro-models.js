/* Omaha evidence extends the established Cobalt Workbench tables. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = (value, places = 3) => Number.isFinite(value) ? value.toFixed(places) : '—';
  const count = value => Number.isFinite(value) ? value.toLocaleString('en-US') : '—';
  let evidence;
  function grid(headers, rows, caption) {
    return `<div class="wrap" tabindex="0" role="region" aria-label="${escape(caption)}"><table><caption>${escape(caption)}</caption><thead><tr>${headers.map(h => `<th scope="col">${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map((cell, i) => i ? `<td>${cell}</td>` : `<th scope="row">${cell}</th>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function classCells(m) { return [number(m?.balanced_accuracy), number(m?.macro_f1), number(m?.accuracy)]; }
  function durationCells(m) { return [number(m?.MAE_min, 2), number(m?.RMSE_min, 2), number(m?.R2_log)]; }
  function blendLabel(blend, features) {
    const names = blend.weight_b === 0 ? blend.member_a : blend.weight_b === 1 ? blend.member_b : `${blend.member_a} + ${blend.member_b}`;
    if (features === 'C_imagery' && names.includes('source')) return names.replaceAll('source', 'global').replaceAll('_', ' ') + ' · no reporting-source input';
    return names.replaceAll('_', ' ');
  }
  function perClass(label, m) {
    return grid(['Class', 'Test incidents', 'Recall', 'F1'], [1,2,3,4].map(c => {
      const row = m?.per_class?.[c]; return [`Level ${c}`, count(row?.support), number(row?.recall), number(row?.f1 ?? row?.['f1-score'])];
    }), label);
  }
  function renderAudit() {
    const a = evidence.data_audit;
    if (!a) { el('metro-audit').textContent = 'The data audit has not been generated.'; return; }
    const train = a.original_temporal_split.train, test = a.original_temporal_split.test;
    el('metro-audit').innerHTML = grid(['Observed measure', 'Original training', 'Original test'], [
      ['Incidents', count(train.rows), count(test.rows)],
      ['Level 1 incidents', count(train.severity_counts['1']), count(test.severity_counts['1'])],
      ['Level 4 incidents', count(train.severity_counts['4']), count(test.severity_counts['4'])],
      ['Median duration · minutes', number(train.duration_minutes.median, 2), number(test.duration_minutes.median, 2)],
      ['Source1 share', number(100 * train.source_fractions.Source1, 1) + '%', number(100 * test.source_fractions.Source1, 1) + '%'],
      ['Missing precipitation', number(100 * train.precipitation_missing_fraction, 1) + '%', number(100 * test.precipitation_missing_fraction, 2) + '%']
    ], 'Changes across the original time split') + `<p class="advanced-note">${number(100 * a.all.future_imagery_fraction, 1)}% of imagery has an acquisition year later than the crash year. GIS and imagery comparisons are retrospective. Corrected runs remove duplicated road geometry, exclude outcomes unavailable at training time, and rebuild neighborhood history using only training incidents. Original caches and scores remain archived.</p>`;
  }
  function render() {
    if (!evidence) return;
    const protocol = el('metro-protocol').value;
    el('metro-objective-label').hidden = protocol === 'online';
    let html = '';
    if (protocol === 'online') {
      const r = evidence.online;
      if (r?.status !== 'complete') {
        el('metro-status').textContent = 'Monthly evaluation is not complete. Refresh after the run finishes.';
        el('metro-results').replaceChildren(); return;
      }
      el('metro-status').textContent = `${count(r.test_rows)} original future incidents · ${r.periods.length} monthly origins · no imagery or observed severity as predictors.`;
      html += '<p class="advanced-note">The monthly model learns from earlier completed test-period incidents. The frozen reference uses the same learner and initial training history. This is sequential evaluation, with more information available over time.</p>';
      html += grid(['Training schedule', 'Balanced accuracy', 'Macro F1', 'Accuracy'], [
        ['Frozen at first origin', ...classCells(r.fixed)], ['Updated each month', ...classCells(r.online)]
      ], 'Four-class traffic-impact prediction');
      html += grid(['Training schedule', 'MAE · minutes', 'RMSE · minutes', 'R² · log minutes'], [
        ['Frozen at first origin', number(r.fixed.duration_mae_minutes, 2), number(r.fixed.duration_rmse_minutes, 2), number(r.fixed.duration_r2_log)],
        ['Updated each month', number(r.online.duration_mae_minutes, 2), number(r.online.duration_rmse_minutes, 2), number(r.online.duration_r2_log)],
        ['Monthly mean-log baseline', number(r.rolling_mean_log_baseline.duration_mae_minutes, 2), '—', number(r.rolling_mean_log_baseline.duration_r2_log)]
      ], 'Recorded duration · incident context, without observed severity');
      const ci = r.comparison;
      html += `<p class="advanced-note">Monthly minus frozen balanced accuracy: 95% geographic bootstrap interval ${ci.balanced_accuracy_difference95.map(x => number(x)).join(' to ')}. Duration MAE reduction: ${ci.duration_mae_reduction_minutes95.map(x => number(x, 2)).join(' to ')} minutes. Positive favors monthly updates. These exploratory intervals condition on the fitted models.</p>`;
      html += `<details><summary>Per-class performance and monthly training boundaries</summary>${perClass('Monthly model · class support and recall', r.online)}<pre>${escape(JSON.stringify(r.periods, null, 2))}</pre></details>`;
    } else {
      const r = evidence.fixed?.runs?.find(run => run.protocol === protocol && run.duration_context === 'severity_known');
      if (!r) {
        el('metro-status').textContent = 'The frozen comparison is still being built. Monthly evidence and the data audit are available as their runs finish.';
        el('metro-results').replaceChildren(); return;
      }
      const objective = el('metro-objective').value;
      el('metro-status').textContent = `${count(r.split.counts.test)} test incidents · ${count(r.split.counts.outer_train)} matured training incidents · selection uses inner validation only.`;
      html += `<p class="advanced-note">Each feature set compares a corrected legacy tree recipe with the same validation-selected recipe (${escape(r.selection.classification_recipe.replaceAll('_', ' '))}). Observed severity is available to duration models, matching the original task. Imagery postdates most incidents; these scores do not establish live prediction performance.</p>`;
      html += grid(['Features', 'Balanced accuracy', 'Macro F1', 'Accuracy'], r.ablations.map(a => [
        `${escape(a.features.replaceAll('_', ' '))}<small>Selected recipe · corrected reference below</small>`,
        ...classCells(a.classification_challenger).map((v, i) => `${v}<small>${classCells(a.classification_baseline)[i]}</small>`)
      ]), 'Four-class traffic-impact prediction');
      const tradeoffs = r.ablations.filter(a => a.classification_challenger.balanced_accuracy > a.classification_baseline.balanced_accuracy && a.classification_challenger.macro_f1 < a.classification_baseline.macro_f1).length;
      if (tradeoffs) html += `<p class="advanced-note">In ${tradeoffs} of ${r.ablations.length} feature sets, the selected recipe improves balanced accuracy but reduces macro F1. A gain in one metric does not establish an overall classification improvement.</p>`;
      html += grid(['Features', 'MAE · minutes', 'RMSE · minutes', 'R² · log minutes'], r.ablations.map(a => [
        `${escape(a.features.replaceAll('_', ' '))}<small>${escape(blendLabel(a.duration_blends[objective], a.features))}<br>Corrected tree reference below</small>`,
        ...durationCells(a.duration_blends[objective].test).map((v, i) => `${v}<small>${durationCells(a.duration_baseline)[i]}</small>`)
      ]), `Recorded duration · selected for ${objective === 'MAE_min' ? 'minute error' : 'log-minute error'}`);
      html += '<p class="advanced-note">The two duration objectives can choose different blends. Every displayed metric in a row belongs to that one selected blend. No best-on-test score is chosen.</p>';
      html += `<details><summary>Per-class results, blend members and comparison intervals</summary><p class="advanced-note">Duration intervals below always evaluate the MAE-selected blend, regardless of the duration display setting. For C imagery, source-based recipe names in the configuration use global training constants: reporting source is never an input.</p>${r.ablations.map(a => perClass(a.features.replaceAll('_',' '), a.classification_challenger)).join('')}<pre>${escape(JSON.stringify({split:r.split, selection:r.selection, comparisons:r.ablations.map(a => ({features:a.features, displayed_estimator:blendLabel(a.duration_blends[objective], a.features), displayed_blend:a.duration_blends[objective], classification_and_mae_selected_blend_intervals:a.paired_intervals_mae_blend}))}, null, 2))}</pre></details>`;
    }
    el('metro-results').innerHTML = html;
    renderAudit();
  }
  async function refresh() {
    const button = el('metro-refresh'); button.disabled = true;
    el('metro-status').textContent = 'Loading Omaha evidence…';
    try {
      const response = await fetch('/api/research/metro');
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || 'The study could not be loaded.');
      evidence = body; renderAudit(); render();
    } catch (error) {
      el('metro-status').textContent = `${error.message} Use Refresh Omaha evidence to retry.`;
      el('metro-results').replaceChildren();
    } finally { button.disabled = false; }
  }
  el('metro-protocol').addEventListener('change', render);
  el('metro-objective').addEventListener('change', render);
  el('metro-refresh').addEventListener('click', refresh);
  refresh();
})();
