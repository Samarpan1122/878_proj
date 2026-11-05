'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const fmt = (x, digits = 0) => Number.isFinite(Number(x)) && x !== null ? Number(x).toLocaleString('en-US', {maximumFractionDigits:digits, minimumFractionDigits:digits}) : '—';
  const pct = x => x === null || x === undefined ? '—' : `${fmt(Number(x)*100,1)}%`;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const items = values => (values||[]).map(x=>`<li>${escape(x)}</li>`).join('');
  const params = obj => new URLSearchParams(Object.entries(obj).filter(([,v])=>v)).toString();
  const state = {states:[], generation:0, hasModel:false};
  async function request(path) {
    const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),25000);
    try { const response=await fetch(path,{signal:controller.signal,headers:{Accept:'application/json'}}); if(!response.ok)throw new Error(`The service returned HTTP ${response.status}.`); return await response.json(); }
    catch(error) { if(error.name==='AbortError')throw new Error('The request timed out. Please try again.'); throw error; }
    finally {clearTimeout(timeout);}
  }
  const stateName = id => state.states.find(s=>String(s.state_fips)===String(id))?.state_name;
  function busy(value) {$('explore-results').setAttribute('aria-busy',String(value));}
  function showError(message) {$('global-error').hidden=false;$('global-error-detail').textContent=message;}
  function renderMeta(meta) {
    $('dataset-status').textContent=`${fmt(meta.total_crashes)} fatal crashes · ${fmt(meta.states_count)} jurisdictions`;
    $('snapshot').textContent=`Snapshot built ${meta.built_at?new Date(meta.built_at).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}):'(date not supplied)'} · observations through ${meta.data_as_of||'2024-12-31'}.`;
    if(meta.limitations?.length)$('limitations').innerHTML=items(meta.limitations);
  }
  function populateStates(states) {
    state.states=states.slice().sort((a,b)=>a.state_name.localeCompare(b.state_name));
    $('state').insertAdjacentHTML('beforeend',state.states.map(s=>`<option value="${Number(s.state_fips)}">${escape(s.state_name)}</option>`).join(''));$('state').disabled=false;
    const search=new URLSearchParams(location.search);
    if(stateName(search.get('state')))$('state').value=search.get('state');
    if([...$('year').options].some(o=>o.value&&o.value===search.get('year')))$('year').value=search.get('year');
  }
  async function updateView() {
    const generation=++state.generation; const id=$('state').value, year=$('year').value;
    const scope=`${stateName(id)||'United States'} · ${year||'2021–2024'}`;
    busy(true);$('view-status').textContent=`Loading ${scope}…`;$('global-error').hidden=true;
    try {
      const areaQuery=params({state:id}), rankQuery=params({year}), area=request(`/api/public/summary?${areaQuery}`);
      const [areaData,ranking,behavior,projection]=await Promise.all([area,rankQuery===areaQuery?area:request(`/api/public/summary?${rankQuery}`),request(`/api/public/behaviors?${params({state:id,year})}`),id?request(`/api/public/forecast?${params({state:id})}`).catch(error=>({error})):null]);
      if(generation!==state.generation)return;
      renderSummary(areaData,id,year,scope); renderProjection(projection); renderRanking(ranking,id,year); renderBehavior(behavior,scope);
      $('view-status').textContent=`Showing ${scope}`;
      const filters=params({state:id,year}); history.replaceState(null,'',`${location.pathname}${filters?'?'+filters:''}${location.hash}`);
    } catch(error) {
      if(generation!==state.generation)return;
      $('view-status').textContent='Update failed. The previous results have not changed.';
      showError(`${error.message} Choose Retry to reload the selected state and year.`);
    } finally {if(generation===state.generation)busy(false);}
  }
  function renderSummary(data,id,year,scope) {
    const annual=(data.years||[]).slice().sort((a,b)=>a.year-b.year);
    const totals=year?annual.find(r=>String(r.year)===year)||{fatal_crashes:0,fatalities:0}:data;
    $('crashes').textContent=fmt(totals.fatal_crashes);$('fatalities').textContent=fmt(totals.fatalities);
    $('scope-description').textContent=`${scope}. Observed counts, not adjusted for traffic volume.`;
    $('trend-title').textContent=`Fatal crashes by year · ${stateName(id)||'United States'}`;
    const max=Math.max(...annual.map(r=>r.fatal_crashes),1);
    $('annual-chart').innerHTML=annual.map(r=>`<div class="annual-bar${String(r.year)===year?' selected':''}"><span>${fmt(r.fatal_crashes)}</span><div class="bar" style="height:${Math.max(r.fatal_crashes/max*120,2)}px"></div><span>${escape(r.year)}</span></div>`).join('')||'<p class="small">No annual records match this selection.</p>';
    $('annual-chart').setAttribute('aria-label',`Fatal crashes by year, ${stateName(id)||'United States'}: ${annual.map(r=>`${r.year}: ${fmt(r.fatal_crashes)}`).join('; ')}`);
  }
  function renderProjection(data) {
    $('projection').hidden=$('projection-note').hidden=!data; if(!data)return;
    if(data.error){$('projection-value').textContent='—';$('projection-note').textContent=`Projection unavailable: ${data.error.message}`;return;}
    // ponytail: the API reports no prediction interval today ("no calibrated prediction interval"); a range shows only if one is added.
    const range=Array.isArray(data.prediction_interval)?data.prediction_interval:null;
    $('projection-label').textContent=`${data.year||2025} projection`;$('projection-value').textContent=fmt(data.expected_fatal_crashes);
    $('projection-note').textContent=`${range?`Range ${fmt(range[0])}–${fmt(range[1])}. `:''}Model estimate from the 2021–2024 trend, not a live forecast or per-mile risk. ${fmt(data.last_observed_crashes)} observed in ${data.last_observed_year||2024}.`;
  }
  function renderRanking(data,id,year) {
    const list=$('state-ranking'), refocus=list.contains(document.activeElement);
    const ranked=(data.states||[]).slice().sort((a,b)=>b.fatal_crashes-a.fatal_crashes);
    $('states-title').textContent=`States · ${year||'2021–2024'}`;
    list.innerHTML=ranked.map((r,i)=>`<button type="button" class="rank-button" data-state="${Number(r.state_fips)}" aria-pressed="${String(r.state_fips)===id}"><span class="rank-number">${i+1}</span><span>${escape(r.state_name)}</span><span class="rank-value">${fmt(r.fatal_crashes)}</span></button>`).join('')||'<p class="small">No state records match this selection.</p>';
    const selected=list.querySelector('[aria-pressed=true]');
    list.scrollTop=selected?selected.offsetTop-(list.clientHeight-selected.offsetHeight)/2:0;
    if(refocus)(selected||list.querySelector('button'))?.focus({preventScroll:true});
  }
  function renderBehavior(data,scope) {
    const factors=data.cohort?.factors||{}, definitions=data.definitions||{};
    $('factors-body').innerHTML=Object.entries(factors).map(([key,f])=>{const ci=f.known_fraction_interval95;
      return `<tr><th scope="row">${escape(definitions[key]?.label||key.replace(/_/g,' '))}</th><td>${pct(f.fraction_among_known)}</td><td>${ci?`${pct(ci[0])}–${pct(ci[1])}`:'—'}</td><td>${f.total_cases?pct(f.unknown/f.total_cases):'—'}</td></tr>`;
    }).join('')||'<tr><td colspan="4">No recorded-factor cohort is available.</td></tr>';
    $('factors-caption').textContent=`Recorded factors · ${scope}`;
    $('factor-scope').textContent=`${scope} · ${fmt(data.cohort?.fatal_crashes)} fatal crashes`;
    const codes=(name,values)=>values?.length?`${name}: ${values.map(escape).join(', ')}`:'';
    $('factor-details').innerHTML=Object.entries(definitions).map(([key,d])=>`<p><strong>${escape(d.label||key)}</strong>${d.column?` · FARS field ${escape(d.column)}`:''}<br>${[codes('Yes',d.positive_codes),codes('No',d.negative_codes),codes('Unknown',d.unknown_codes),codes('Not applicable (excluded)',d.not_applicable_codes)].filter(Boolean).join(' · ')}</p>`).join('')+(data.limitations?.length?`<ul>${items(data.limitations)}</ul>`:'');
  }
  async function loadModel() {
    try {const data=await request('/api/public/model'); const e=data.evaluation||{};
      $('model-method').textContent=`${typeof data.method==='string'?data.method:'Historical state count model'}. Fit on ${(data.trained_years||[]).join(', ')||'2021–2024'} to project ${data.prediction_year||2025}; no traffic-volume adjustment.`;
      $('model-body').innerHTML=[['Count model',e.model],[`Baseline: ${e.baseline_method||'previous-year count'}`,e.baseline]].map(([name,m])=>`<tr><th scope="row">${escape(name)}</th><td>${fmt(m?.mae,1)}</td><td>${fmt(m?.rmse,1)}</td><td>${fmt(m?.poisson_deviance,2)}</td></tr>`).join('');
      $('evaluation-window').textContent=`Fit on ${(e.train_years||[]).join(', ')}, scored on ${e.test_year||'the held-out year'} across ${fmt(e.states_count||e.rows?.length)} jurisdictions.`;
      $('evaluation-window').classList.remove('inline-error');state.hasModel=true;
    }catch(error){$('evaluation-window').textContent=`Model evaluation unavailable: ${error.message} Use Retry above to try again.`;$('evaluation-window').classList.add('inline-error');}
  }
  // Links to #methods or #models land inside a closed <details>; open it, then scroll.
  function openHash() {const target=location.hash.length>1?document.getElementById(location.hash.slice(1)):null;const details=target?.closest('details');if(details){details.open=true;target.scrollIntoView();}}
  $('filters').addEventListener('submit',event=>event.preventDefault());
  $('state').addEventListener('change',updateView);$('year').addEventListener('change',updateView);
  $('reset').addEventListener('click',()=>{$('state').value='';$('year').value='';updateView();});
  $('state-ranking').addEventListener('click',event=>{const button=event.target.closest('[data-state]');if(button&&stateName(button.dataset.state)){$('state').value=button.dataset.state;updateView();}});
  $('retry').addEventListener('click',()=>{if(!state.hasModel)loadModel();state.states.length?updateView():initialize();});
  addEventListener('hashchange',openHash);
  document.addEventListener('click',event=>{if(event.target.closest('a[href^="#"]'))setTimeout(openHash);});
  async function initialize(){try {const [meta,states]=await Promise.all([request('/api/public/meta'),request('/api/public/states')]);renderMeta(meta);populateStates(states.states);await updateView();openHash();}catch(error){$('dataset-status').textContent='Dataset connection unavailable';showError(`${error.message} Choose Retry to connect to the public dataset.`);busy(false);} }
  openHash();loadModel();initialize();
})();
