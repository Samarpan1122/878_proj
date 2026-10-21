'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const fmt = value => Number(value).toLocaleString('en-US');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const presets = [
    {name:'Omaha',state:31,lat:41.26,lng:-96.03},
    {name:'Chicago',state:17,lat:41.88,lng:-87.63},
    {name:'Dallas',state:48,lat:32.78,lng:-96.80},
    {name:'New York',state:36,lat:40.75,lng:-73.98},
    {name:'Los Angeles',state:6,lat:34.04,lng:-118.27}
  ];
  let states=[],boundaries=null,cells=[],scene=null,summary=null,generation=0,mapFailed=false;
  let currentState='',currentYear='',currentPreset=null;
  let view={longitude:-98,latitude:38.5,zoom:3.75,pitch:48,bearing:-12,minZoom:2,maxZoom:9,maxPitch:65};
  const initialView=()=>({...view,longitude:-98,latitude:38.5,zoom:innerWidth<761?2.8:3.75,pitch:48,bearing:-12});
  const nameFor=id=>states.find(s=>Number(s.state_fips)===Number(id))?.state_name || 'United States';
  const years=()=>currentYear||'2021–2024';
  async function request(url){
    const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),25000);
    try {const response=await fetch(url,{signal:ctrl.signal});if(!response.ok)throw new Error(`Data service returned HTTP ${response.status}.`);return await response.json();}
    catch(error){if(error.name==='AbortError')throw new Error('The data request timed out.');throw error;}
    finally{clearTimeout(timer);}
  }
  function failure(title,message){$('error-title').textContent=title;$('error-message').textContent=message;$('error').hidden=false;}
  function color(feature){const n=feature.properties.fatal_crashes;const t=Math.min(1,Math.log1p(n)/Math.log(350));return [Math.round(64+114*t),Math.round(105+69*t),255,235];}
  function layers(){
    if(!window.deck||!boundaries)return[];
    return [
      new deck.GeoJsonLayer({id:'state-boundaries',data:boundaries,stroked:true,filled:true,pickable:true,
        getFillColor:f=>String(Number(f.id))===currentState?[32,55,88,255]:[24,36,52,255],
        getLineColor:[83,108,142,180],lineWidthMinPixels:.75,getLineWidth:800,
        updateTriggers:{getFillColor:currentState},onClick:({object})=>{if(object&&states.some(s=>Number(s.state_fips)===Number(object.id)))choose(String(Number(object.id)));}}),
      new deck.ColumnLayer({id:'fatal-crash-columns',data:cells,diskResolution:6,radius:4400,extruded:true,pickable:true,
        getPosition:f=>f.geometry.coordinates,getElevation:f=>Math.sqrt(f.properties.fatal_crashes)*4400,
        getFillColor:color,material:{ambient:.55,diffuse:.65,shininess:28},
        onClick:({object})=>{if(!object)return;const p=object.properties;const coordinates=object.geometry.coordinates;
          $('cell-detail').textContent=`Selected cell: ${fmt(p.fatal_crashes)} fatal crashes, ${fmt(p.fatalities)} fatalities. ${nameFor(p.state_fips)} · ${years()}. Center ${coordinates[1].toFixed(3)}°, ${coordinates[0].toFixed(3)}°. Cell aggregates are not street-level locations.`;
          $('cell-detail').hidden=false;document.body.classList.add('selected');}})
    ];
  }
  function renderMap(){if(scene&&!mapFailed)scene.setProps({layers:layers()});}
  function initMap(){
    if(!window.deck){mapFailed=true;failure('3D rendering is unavailable','The graphics library did not load. You can still explore the same real data using the data explorer.');return;}
    try {
      view=initialView();scene=new deck.Deck({parent:$('deck'),initialViewState:view,controller:{touchRotate:true},layers:[],
        onViewStateChange:({viewState})=>{view=viewState;},
        onError:error=>{mapFailed=true;failure('The 3D view could not render','Your browser could not initialize or maintain WebGL. Try again, or open the data explorer for the same observations.');console.warn('GeoCrash map renderer:',error.message);},
        getTooltip:({object,layer})=>!object?null:layer.id==='fatal-crash-columns'?{text:`${fmt(object.properties.fatal_crashes)} fatal crashes\n${nameFor(object.properties.state_fips)} · ${years()}\n0.25° geographic cell · count, not risk`,className:'deck-tooltip'}:{text:object.properties.name,className:'deck-tooltip'}});
    }catch(error){mapFailed=true;failure('3D rendering is unavailable','This browser does not support the graphics needed for the map. The full data explorer and screening engine remain available.');}
  }
  function fly(target){
    if(!scene||mapFailed)return;
    const nextView={...view,...target,transitionDuration:reduced.matches?0:1100,transitionInterpolator:new deck.FlyToInterpolator()};
    $('tilt').setAttribute('aria-pressed',String(nextView.pitch>0));
    view=nextView;scene.setProps({initialViewState:nextView});
  }
  function stateView(id,preset){
    if(!id)return initialView();
    if(preset)return{longitude:preset.lng,latitude:preset.lat,zoom:innerWidth<761?6:6.5,pitch:53,bearing:-15};
    const row=states.find(s=>Number(s.state_fips)===Number(id));if(!row)return initialView();
    const feature=boundaries.features.find(f=>Number(f.id)===Number(id));
    const coords=feature?.geometry.type==='Polygon'?feature.geometry.coordinates.flat():feature?.geometry.coordinates.flat(2)||[];
    const lngs=coords.map(p=>p[0]>0?p[0]-360:p[0]),lats=coords.map(p=>p[1]);
    const span=Math.max(Math.max(...lngs)-Math.min(...lngs),(Math.max(...lats)-Math.min(...lats))*1.5,1);
    return{longitude:Number(id)===2?-152:row.lng,latitude:row.lat,zoom:Math.max(3,Math.min(7,Math.log2(330/span)-(innerWidth<761?.8:0))),pitch:45,bearing:-10};
  }
  function renderSummary(data,map){
    summary=data;$('scope-name').textContent=currentState?nameFor(currentState):'United States';$('summary-years').textContent=years();
    $('crashes').textContent=fmt(data.fatal_crashes);$('fatalities').textContent=fmt(data.fatalities);$('cells').textContent=fmt(map.features.length);
    const c=map.coverage;
    $('summary-note').textContent=`${fmt(c.mapped_crashes)} crashes mapped; ${fmt(c.suppressed_crashes)} below the cell threshold; ${fmt(c.unlocated_crashes)} without coordinates. Counts are not traffic-adjusted risk.`;
    const params=new URLSearchParams();if(currentState)params.set('state',currentState);if(currentYear)params.set('year',currentYear);
    $('details').href='/explore/'+(params.size?'?'+params:'');
    $('view-status').textContent=`NHTSA FARS · ${years()} · ${currentState?nameFor(currentState):fmt(data.fatal_crashes)+' fatal-crash records'} · historical data`;
  }
  async function update(preset=null){
    const ticket=++generation,requestedState=$('state').value,requestedYear=$('year').value;
    $('apply').disabled=true;$('panel').setAttribute('aria-busy','true');$('view-status').textContent='Loading historical observations…';
    if(!mapFailed)$('error').hidden=true;
    const params=new URLSearchParams();if(requestedState)params.set('state',requestedState);if(requestedYear)params.set('year',requestedYear);
    try{
      const [data,map]=await Promise.all([request('/api/public/summary?'+params),request('/api/public/map?'+params)]);
      if(ticket!==generation)return;
      currentState=requestedState;currentYear=requestedYear;currentPreset=preset;cells=map.features;
      $('cell-detail').hidden=true;document.body.classList.toggle('selected',Boolean(currentState));
      document.querySelectorAll('[data-preset]').forEach(button=>button.setAttribute('aria-pressed',String(preset?.name===button.textContent)));
      renderSummary(data,map);renderMap();fly(stateView(currentState,preset));
      history.replaceState(null,'',location.pathname+(params.size?'?'+params:''));
    }catch(error){if(ticket!==generation)return;$('view-status').textContent='Data update failed · previous results retained';failure('The data could not load',`${error.message} Try again to load the selected state and year.`);}
    finally{if(ticket===generation){$('apply').disabled=false;$('panel').setAttribute('aria-busy','false');}}
  }
  function choose(id,preset=null){$('state').value=id;return update(preset);}
  function reset(){ $('state').value='';$('year').value='';update(); }
  $('filters').addEventListener('submit',event=>{event.preventDefault();update();});
  $('reset').addEventListener('click',()=>fly(stateView(currentState,currentPreset)));
  $('reset-panel').addEventListener('click',reset);
  $('tilt').addEventListener('click',()=>{const isTilted=$('tilt').getAttribute('aria-pressed')==='true';fly({pitch:isTilted?0:48,bearing:isTilted?0:-12});});
  $('zoom-in').addEventListener('click',()=>fly({zoom:Math.min(9,view.zoom+.7)}));
  $('zoom-out').addEventListener('click',()=>fly({zoom:Math.max(2,view.zoom-.7)}));
  $('retry').addEventListener('click',()=>{if(mapFailed)location.reload();else if(!states.length)boot();else update(currentPreset);});
  for(const [index,preset] of presets.entries()){const button=document.createElement('button');button.type='button';button.textContent=preset.name;button.dataset.preset=String(index);button.setAttribute('aria-pressed','false');button.disabled=true;button.addEventListener('click',()=>choose(String(preset.state),preset));$('presets').append(button);}
  async function boot(){
    try {
      const [list,geo]=await Promise.all([request('/api/public/states'),request('/assets/states.json')]);
      states=list.states.sort((a,b)=>a.state_name.localeCompare(b.state_name));boundaries=geo;
      for(const state of states){const option=document.createElement('option');option.value=String(state.state_fips);option.textContent=state.state_name;$('state').append(option);}
      $('state').disabled=false;document.querySelectorAll('[data-preset]').forEach(b=>b.disabled=false);
      const params=new URLSearchParams(location.search);if(states.some(s=>String(s.state_fips)===params.get('state')))$('state').value=params.get('state');
      if(['2021','2022','2023','2024'].includes(params.get('year')))$('year').value=params.get('year');
      if(!scene&&!mapFailed)initMap();await update();
    }catch(error){failure('The map could not load',`${error.message} The data explorer offers the same historical records.`);$('view-status').textContent='Data unavailable · choose Try again';}
  }
  boot();
})();
