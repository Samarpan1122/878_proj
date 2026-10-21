'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const fmt = (x, digits = 0) => Number.isFinite(Number(x)) && x !== null ? Number(x).toLocaleString('en-US', {maximumFractionDigits:digits, minimumFractionDigits:digits}) : '—';
  const pct = x => x === null || x === undefined ? 'Unavailable' : `${fmt(Number(x)*100,1)}%`;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = {states:[], boundaries:null, generation:0, forecastGeneration:0};
  const ns = 'http://www.w3.org/2000/svg';
  function node(tag, attrs={}, text=null) { const el = document.createElementNS(ns,tag); Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v))); if(text!==null)el.textContent=text; return el; }
  async function request(path) {
    const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),25000);
    try { const response=await fetch(path,{signal:controller.signal,headers:{Accept:'application/json'}}); if(!response.ok)throw new Error(`The service returned HTTP ${response.status}.`); return await response.json(); }
    catch(error) { if(error.name==='AbortError')throw new Error('The request timed out. Please try again.'); throw error; }
    finally {clearTimeout(timeout);}
  }
  function query() {const params=new URLSearchParams();if($('state').value)params.set('state',$('state').value);if($('year').value)params.set('year',$('year').value);return params.toString();}
  function scopeLabel() {return `${state.states.find(s=>String(s.state_fips)===$('state').value)?.state_name || 'United States'} · ${$('year').value||'2021–2024'}`;}
  function busy(value) {$('explore-results').setAttribute('aria-busy',String(value));$('apply').disabled=value;$('download').setAttribute('aria-disabled',String(value));}
  function showError(message) {$('global-error').hidden=false;$('global-error-detail').textContent=message;}
  function textList(values) {return `<ul>${(values||[]).map(x=>`<li>${escape(typeof x==='string'?x:JSON.stringify(x))}</li>`).join('')}</ul>`;}
  function renderMeta(meta) {
    $('dataset-status').textContent=`${fmt(meta.total_crashes)} fatal-crash records · ${fmt(meta.states_count)} jurisdictions`;
    $('connection-status').textContent='Connected to the public data service';
    $('snapshot').textContent=`Snapshot built ${meta.built_at?new Date(meta.built_at).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}):'date not supplied'} · Observations through ${meta.data_as_of||'2024-12-31'}.`;
    if(meta.limitations?.length)$('limitations').innerHTML=meta.limitations.map(x=>`<li>${escape(x)}</li>`).join('');
    $('source-register').innerHTML=(meta.sources||[]).map(source=>{
      const url=/^https:\/\//.test(source.url||'')?source.url:null;
      return `<div class="source-item"><strong>${url?`<a href="${escape(url)}">${escape((source.name||'Source')+(source.year?' · '+source.year:''))}</a>`:escape((source.name||'Source')+(source.year?' · '+source.year:''))}</strong>${source.description?`<p>${escape(source.description)}</p>`:''}${source.rows?`<p>${fmt(source.rows)} records · <a href="/api/public/meta">retrieval date and SHA-256</a></p>`:''}${source.license||source.rights?`<p>${escape(source.license||source.rights)}</p>`:''}</div>`;
    }).join('')||'<p>No source metadata was supplied.</p>';
  }
  function populateStates(states) {
    state.states=states.slice().sort((a,b)=>a.state_name.localeCompare(b.state_name));
    const options=state.states.map(s=>`<option value="${Number(s.state_fips)}">${escape(s.state_name)}</option>`).join('');
    $('state').insertAdjacentHTML('beforeend',options);$('forecast-state').insertAdjacentHTML('beforeend',options);$('state').disabled=false;$('forecast-state').disabled=false;
    const params=new URLSearchParams(location.search);if(state.states.some(s=>String(s.state_fips)===params.get('state')))$('state').value=params.get('state');
    if(['2021','2022','2023','2024'].includes(params.get('year')))$('year').value=params.get('year');
    $('forecast-state').value=$('state').value || '31';
  }
  async function updateView() {
    const generation=++state.generation; const filters=query();const scope=scopeLabel();
    busy(true);$('view-status').textContent=`Loading ${scope}…`;$('global-error').hidden=true;
    $('factor-status').textContent='Loading the selected cohort…';
    try {
      const [summary,map,behavior]=await Promise.all([request(`/api/public/summary?${filters}`),request(`/api/public/map?${filters}`),request(`/api/public/behaviors?${filters}`)]);
      if(generation!==state.generation)return;
      renderSummary(summary,scope); renderMap(map,summary); renderBehavior(behavior,scope);
      $('view-status').textContent=`Showing ${scope}`;$('factor-scope').textContent=scope;
      $('download').href=`/api/public/summary?${filters}`;
      history.replaceState(null,'',`${location.pathname}${filters?'?'+filters:''}${location.hash}`);
      if($('state').value){$('forecast-state').value=$('state').value;clearForecast();}
    } catch(error) {
      if(generation!==state.generation)return;
      $('view-status').textContent='Update failed. The previous results have not changed.';
      $('factor-status').textContent='Update failed. The previously displayed cohort remains.';
      showError(`${error.message} Choose Try again to reload the selected geography and year.`);
    } finally {if(generation===state.generation)busy(false);}
  }
  function renderSummary(data,scope) {
    $('crashes').textContent=fmt(data.fatal_crashes);$('fatalities').textContent=fmt(data.fatalities);$('located').textContent=fmt(data.located_crashes);
    $('scope-description').textContent=`${scope}. Observed fatal crashes; no traffic-exposure adjustment.`;
    const annual=(data.years||[]).slice().sort((a,b)=>a.year-b.year); const max=Math.max(...annual.map(r=>r.fatal_crashes),1);
    $('annual-caption').textContent=`${scope} · annual records`;
    $('annual-body').innerHTML=annual.map(r=>`<tr><th scope="row">${escape(r.year)}</th><td>${fmt(r.fatal_crashes)}</td><td>${fmt(r.fatalities)}</td></tr>`).join('')||'<tr><td colspan="3">No annual records match this selection.</td></tr>';
    $('annual-chart').innerHTML=annual.map(r=>`<div class="annual-bar"><span>${fmt(r.fatal_crashes)}</span><div class="bar" style="height:${Math.max(r.fatal_crashes/max*103,2)}px"></div><span>${escape(r.year)}</span></div>`).join('');
    $('annual-chart').setAttribute('aria-label',`Fatal crashes: ${annual.map(r=>`${r.year}: ${fmt(r.fatal_crashes)}`).join('; ')}`);
    const ranked=(data.states||[]).slice().sort((a,b)=>b.fatal_crashes-a.fatal_crashes);
    $('states-title').textContent=$('state').value?'Selected state':'State comparison';
    $('state-ranking').innerHTML=ranked.map((r,i)=>`<button type="button" class="rank-button" data-state="${Number(r.state_fips)}" aria-pressed="${String(r.state_fips)===$('state').value}" aria-label="Explore ${escape(r.state_name)}, ${fmt(r.fatal_crashes)} fatal crashes"><span class="rank-number">${i+1}</span><span>${escape(r.state_name)}</span><span class="rank-value">${fmt(r.fatal_crashes)}</span></button>`).join('')||'<p class="small">No state records match this selection.</p>';
  }
  function renderMap(data,summary) {
    const selected=Number($('state').value)||null;const features=state.boundaries?.features||[];
    const selectedShape=features.find(f=>Number(f.id)===selected);
    const coordinates=f=>f.geometry.type==='Polygon'?f.geometry.coordinates:f.geometry.coordinates.flat();
    const bounds=[-125,24,-66,50];
    if(selectedShape){const pts=coordinates(selectedShape).flat();const lngs=pts.map(p=>p[0]>0?p[0]-360:p[0]);const lats=pts.map(p=>p[1]);bounds.splice(0,4,Math.min(...lngs),Math.min(...lats),Math.max(...lngs),Math.max(...lats));}
    const width=940,height=540; const svg=node('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':`${scopeLabel()} fatal-crash geographic cells. State selection is also available in the geography menu.`});
    svg.append(node('title',{},`${scopeLabel()} observed fatal crashes`));
    function project(lng,lat,id) {
      if(lng>0)lng-=360;
      if(selected){const dx=bounds[2]-bounds[0]||1,dy=bounds[3]-bounds[1]||1;const scale=Math.min(850/dx,440/dy);return [width/2+(lng-(bounds[0]+bounds[2])/2)*scale,height/2-(lat-(bounds[1]+bounds[3])/2)*scale];}
      if(Number(id)===2)return [30+(lng+180)/51*220,500-(lat-50)/22*100];
      if(Number(id)===15)return [278+(lng+161)/7*140,496-(lat-18)/5*85];
      return [45+(lng+125)/59*850,42+(50-lat)/26*360];
    }
    if(!selected){svg.append(node('rect',{x:22,y:390,width:230,height:120,class:'map-frame'}));svg.append(node('text',{x:34,y:530,class:'map-label'},'Alaska · inset scale'));svg.append(node('text',{x:282,y:530,class:'map-label'},'Hawaii · inset scale'));}
    for(const feature of features){const id=Number(feature.id);if(id>56||selected&&id!==selected)continue;const rings=coordinates(feature);let d='';for(const ring of rings){d+=ring.map((p,i)=>{const xy=project(p[0],p[1],id);return `${i?'L':'M'}${xy[0].toFixed(1)},${xy[1].toFixed(1)}`;}).join('')+'Z';}
      const stateName=state.states.find(s=>Number(s.state_fips)===id)?.state_name||feature.properties.name;
      const path=node('path',{d,class:`map-state${selected===id?' selected':''}`,tabindex:0,role:'button','aria-label':`Explore ${stateName}`,'data-state':id});path.append(node('title',{},stateName));svg.append(path);
    }
    for(const feature of data.features||[]){const prop=feature.properties;const [lng,lat]=feature.geometry.coordinates;if(!Number.isFinite(lng)||!Number.isFinite(lat))continue;const [x,y]=project(lng,lat,prop.state_fips);const radius=Math.max(1.7,Math.min(10,Math.sqrt(Number(prop.fatal_crashes))*.62));svg.append(node('circle',{cx:x.toFixed(1),cy:y.toFixed(1),r:radius.toFixed(1),class:'map-point'}));}
    if(!features.length)svg.append(node('text',{x:30,y:25,class:'map-label'},'Geographic plot · longitude / latitude; boundary layer unavailable'));
    $('map').replaceChildren(svg);
    $('map-title').textContent=selected?`${state.states.find(s=>Number(s.state_fips)===selected)?.state_name||'Selected state'} · geographic distribution`:'United States · geographic distribution';
    $('map-caption').textContent=`Each point aggregates fatal crashes into a ${data.cell_degrees||.25}° geographic cell. Larger points indicate more crashes. Cells with fewer than ${data.min_count||5} crashes per state and year are omitted. Select a state boundary to focus the view.`;
    const c=data.coverage||{};$('map-coverage').textContent=`${fmt(c.mapped_crashes)} crashes mapped · ${fmt(c.suppressed_crashes)} below the cell threshold · ${fmt(c.unlocated_crashes)} without coordinates. Sparse state-year cells are omitted before years are pooled.`;
    if(!(data.features||[]).length)$('map-coverage').textContent+=' No cells meet the display threshold for this selection.';
  }
  function renderBehavior(data,scope) {
    const factors=data.cohort?.factors||{};const definitions=data.definitions||{};
    $('factors-body').innerHTML=Object.entries(factors).map(([key,f])=>{
      const label=definitions[key]?.label||key.replace(/_/g,' ');const ci=f.known_fraction_interval95;
      return `<tr><th scope="row">${escape(label)}</th><td>${fmt(f.yes)}</td><td>${fmt(f.no)}</td><td>${fmt(f.unknown)}</td><td>${fmt(f.not_applicable)}</td><td><div class="factor-share"><span class="factor-meter" aria-hidden="true"><i style="width:${Math.max(0,Math.min(100,Number(f.fraction_among_known)*100))}%"></i></span>${pct(f.fraction_among_known)}</div>${ci?`<span class="factor-ci">95% interval ${pct(ci[0])}–${pct(ci[1])}</span>`:''}</td></tr>`;
    }).join('')||'<tr><td colspan="6">No recorded-factor cohort is available.</td></tr>';
    $('factor-status').textContent=`${scope} · ${fmt(data.cohort?.fatal_crashes)} fatal crashes in this cohort.`;
    $('factor-details').innerHTML=Object.entries(definitions).map(([key,d])=>`<p><strong>${escape(d.label||key)}.</strong> ${escape(d.description||d.definition||'The factor follows the source-coded crash record.')}</p>`).join('')+textList(data.limitations)+ '<p>Intervals describe the estimated recorded share among known cases. They do not account for systematic underreporting or changes in coding.</p>';
  }
  async function loadModel() {
    try {const data=await request('/api/public/model'); const e=data.evaluation||{};
      $('forecast-method').textContent=typeof data.method==='string'?data.method:'Historical state count model; no traffic-volume adjustment.';
      $('evaluation-window').textContent=`Fit on ${(e.train_years||[]).join(', ')}; evaluated on ${e.test_year||'the held-out year'}. ${e.rows?.length||51} jurisdiction predictions.`;
      $('model-body').innerHTML=[['Deployed count model',e.model],['Previous-year count',e.baseline]].map(([name,m])=>`<tr><th scope="row">${name}</th><td>${fmt(m?.mae,2)}</td><td>${fmt(m?.rmse,2)}</td><td>${fmt(m?.poisson_deviance,3)}</td></tr>`).join('');
      $('model-details').innerHTML=`<p><strong>Method:</strong> ${escape(typeof data.method==='string'?data.method:JSON.stringify(data.method))}</p><p><strong>Model ID:</strong> ${escape(data.model_id)}</p><p><strong>Deployment fit:</strong> ${(data.trained_years||[]).map(escape).join(', ')}. Forecast year: ${escape(data.prediction_year)}.</p>${textList(data.limitations)}`;
    }catch(error){$('evaluation-window').textContent=`Model evidence unavailable: ${error.message}`;$('evaluation-window').classList.add('inline-error');$('model-body').innerHTML='<tr><td colspan="4">Use the model evidence link to retry the API.</td></tr>';}
  }
  function clearForecast(){state.forecastGeneration++;$('forecast-result').innerHTML='<p>Select Run forecast to calculate the chosen state’s estimate.</p>';$('forecast-button').disabled=false;}
  async function forecast(event) {event.preventDefault();const id=$('forecast-state').value;if(!id)return;const generation=++state.forecastGeneration;$('forecast-button').disabled=true;$('forecast-result').innerHTML='<p>Calculating from the deployed model…</p>';
    try {const data=await request(`/api/public/forecast?state=${encodeURIComponent(id)}`);if(generation!==state.forecastGeneration)return;$('forecast-result').innerHTML=`<p><strong>${escape(data.state_name)} · ${escape(data.year)}</strong></p><div class="forecast-number">${fmt(data.expected_fatal_crashes,1)}<span>expected fatal crashes</span></div><p>${fmt(data.last_observed_crashes)} observed in ${escape(data.last_observed_year)}.</p><p>${escape(data.interpretation||'A model estimate, not an observed result.')}</p>${data.limitations?.length?`<details><summary>Forecast limitations</summary>${textList(data.limitations)}</details>`:''}`;
    }catch(error){if(generation===state.forecastGeneration)$('forecast-result').innerHTML=`<p class="inline-error">Forecast unavailable. ${escape(error.message)} Select Run forecast to try again.</p>`;}
    finally{if(generation===state.forecastGeneration)$('forecast-button').disabled=false;}
  }
  function selectState(id){if(!state.states.some(s=>String(s.state_fips)===String(id)))return;$('state').value=String(id);updateView();}
  $('filters').addEventListener('submit',event=>{event.preventDefault();updateView();});
  $('reset').addEventListener('click',()=>{$('state').value='';$('year').value='';updateView();});
  $('state').addEventListener('change',updateView);$('year').addEventListener('change',updateView);
  $('state-ranking').addEventListener('click',event=>{const button=event.target.closest('[data-state]');if(button)selectState(button.dataset.state);});
  $('map').addEventListener('click',event=>{const button=event.target.closest('[data-state]');if(button)selectState(button.dataset.state);});
  $('map').addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){const button=event.target.closest('[data-state]');if(button){event.preventDefault();selectState(button.dataset.state);}}});
  $('forecast-form').addEventListener('submit',forecast);$('forecast-state').addEventListener('change',clearForecast);
  $('copy-api').addEventListener('click',async()=>{const url=`${location.origin}/api/public/summary?state=31&year=2024`;try{await navigator.clipboard.writeText(url);$('copy-status').textContent='Request URL copied.';}catch{$('copy-status').textContent='Copy the request URL displayed above.';$('api-command').textContent=url;}});
  $('retry').addEventListener('click',()=>state.states.length?updateView():initialize());
  async function initialize(){try {const [meta,states,boundaries]=await Promise.all([request('/api/public/meta'),request('/api/public/states'),request('/assets/states.json').catch(()=>null)]);state.boundaries=boundaries;renderMeta(meta);populateStates(states.states);await updateView();}catch(error){$('dataset-status').textContent='Dataset connection unavailable';$('connection-status').textContent='Service connection unavailable';showError(`${error.message} Try again to connect to the public dataset.`);busy(false);} }
  loadModel();initialize();
})();
