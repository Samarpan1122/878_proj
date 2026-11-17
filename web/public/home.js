'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const fmt = value => Number(value).toLocaleString('en-US');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let states=[],boundaries=null,cells=[],scene=null,summary=null,generation=0,mapFailed=false;
  let currentState='',currentYear='',currentPreset=null,satellite=false;
  let place=null; // {layers,tooltip,onMapClick,onExit,credit} supplied by place.js while a place is checked
  // ponytail: Esri World Imagery tiles need no key; attribution is shown in the legend while active.
  const IMAGERY='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  const CELL_LAYERS=new Set(['fatal-crash-columns','fatal-crash-points']);
  let view={longitude:-98,latitude:38.5,zoom:3.75,pitch:48,bearing:-12,minZoom:2,maxZoom:9,maxPitch:65};
  let pendingView=null,busy=0;
  const fxOf=()=>window.GeoCrashFx;
  function countUp(el,to){
    const from=Number(el.dataset.v||0),began=performance.now();el.dataset.v=to;
    if(reduced.matches||from===to){el.textContent=fmt(to);return;}
    (function tick(now){const k=Math.min(1,(now-began)/900);el.textContent=fmt(Math.round(from+(to-from)*(1-(1-k)**3)));if(k<1&&Number(el.dataset.v)===to)requestAnimationFrame(tick);})(began);
  }
  const initialView=()=>({...view,longitude:-98,latitude:38.5,zoom:innerWidth<761?2.8:3.75,pitch:48,bearing:-12,maxZoom:9});
  const nameFor=id=>states.find(s=>Number(s.state_fips)===Number(id))?.state_name || 'United States';
  const years=()=>currentYear||'2021–2024';
  async function request(url){
    const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),25000);
    try {const response=await fetch(url,{signal:ctrl.signal});if(!response.ok)throw new Error(`Data service returned HTTP ${response.status}.`);return await response.json();}
    catch(error){if(error.name==='AbortError')throw new Error('The data request timed out.');throw error;}
    finally{clearTimeout(timer);}
  }
  function failure(title,message){$('error-title').textContent=title;$('error-message').textContent=message;$('error').hidden=false;}
  const RAMP=[[70,110,255],[160,120,255],[255,110,90]];   // few crashes -> many
  function color(feature){
    const t=Math.min(1,Math.log1p(feature.properties.fatal_crashes)/Math.log(700))*(RAMP.length-1),i=Math.min(RAMP.length-2,Math.floor(t)),k=t-i;
    return [...RAMP[i].map((v,c)=>Math.round(v+(RAMP[i+1][c]-v)*k)),235];
  }
  const esc=value=>String(value).replace(/[&<>"']/g,ch=>'&#'+ch.charCodeAt(0)+';');
  function inspectCell({object}){
    if(!object)return;const p=object.properties;const coordinates=object.geometry.coordinates;
    $('cell-detail').textContent=`Selected cell: ${fmt(p.fatal_crashes)} fatal crashes, ${fmt(p.fatalities)} fatalities. ${nameFor(p.state_fips)} · ${years()}. Center ${coordinates[1].toFixed(3)}°, ${coordinates[0].toFixed(3)}°. Cell aggregates are not street-level locations.`;
    $('cell-detail').hidden=false;document.body.classList.add('selected');
  }
  function imagery(){
    return new deck.TileLayer({id:'satellite-imagery',data:IMAGERY,minZoom:0,maxZoom:19,tileSize:256,
      renderSubLayers:props=>{const [[west,south],[east,north]]=props.tile.boundingBox;
        return new deck.BitmapLayer(props,{data:null,image:props.data,bounds:[west,south,east,north]});}});
  }
  function crashLayer(){
    if(satellite)return new deck.ScatterplotLayer({id:'fatal-crash-points',data:cells,pickable:true,stroked:true,
      getPosition:f=>f.geometry.coordinates,getRadius:f=>Math.sqrt(f.properties.fatal_crashes)*1700,radiusMinPixels:3,radiusMaxPixels:42,
      getFillColor:f=>{const t=Math.min(1,Math.log1p(f.properties.fatal_crashes)/Math.log(350));return [255,Math.round(196-150*t),Math.round(64-40*t),215];},
      getLineColor:[255,255,255,230],lineWidthMinPixels:1,onClick:inspectCell});
    return new deck.ColumnLayer({id:'fatal-crash-columns',data:cells,diskResolution:6,radius:4400,extruded:true,pickable:true,
      getPosition:f=>f.geometry.coordinates,getElevation:f=>Math.sqrt(f.properties.fatal_crashes)*4400*(fxOf()?.rise?.(f.geometry.coordinates,view)??1),updateTriggers:{getElevation:fxOf()?.grow??1},
      getFillColor:color,material:{ambient:.55,diffuse:.65,shininess:28},onClick:inspectCell});
  }
  function layers(){
    if(!window.deck||!boundaries)return[];
    const selectedFill=satellite?[255,255,255,28]:[32,55,88,255],otherFill=satellite?[0,0,0,0]:[24,36,52,255];
    return [
      ...(satellite?[imagery()]:[]),
      new deck.GeoJsonLayer({id:'state-boundaries',data:boundaries,stroked:true,filled:true,pickable:true,
        getFillColor:f=>String(Number(f.id))===currentState?selectedFill:otherFill,
        getLineColor:satellite?[255,255,255,150]:[83,108,142,180],lineWidthMinPixels:satellite?1:.75,lineWidthMaxPixels:2,getLineWidth:800,
        pickable:!place,updateTriggers:{getFillColor:[currentState,satellite],getLineColor:satellite},onClick:({object})=>{if(object&&states.some(s=>Number(s.state_fips)===Number(object.id)))choose(String(Number(object.id)));}}),
      ...(place?place.layers():fxOf()?.replaying?[]:[crashLayer()]),
      ...(fxOf()?.layers?.()||[])
    ];
  }
  function setSatellite(on){
    satellite=on;$('satellite').setAttribute('aria-pressed',String(on));legend();renderMap();
  }
  function legend(){
    $('legend-key').innerHTML=place?'<i class="pin" aria-hidden="true"></i> Red pins = individual fatal crashes':satellite?'<i aria-hidden="true"></i> Larger dots = more fatal crashes':'<i aria-hidden="true"></i> Taller columns = more fatal crashes';
    $('legend-note').textContent=place?'NHTSA FARS 2021–2024 · fatal crashes only · police-reported locations':'0.25° cells · minimum 5 crashes per state/year';
    $('imagery-credit').hidden=!satellite&&!place?.credit;
    $('imagery-credit').textContent=[satellite&&'Imagery © Esri, Maxar, Earthstar Geographics',place?.credit].filter(Boolean).join(' · ');
  }
  function enterPlace(handlers){place=handlers;document.body.classList.add('selected','place');if(!satellite)setSatellite(true);else{legend();renderMap();}}
  function exitPlace(shouldFly=true){
    if(!place)return;const {onExit}=place;place=null;document.body.classList.remove('place');document.body.classList.toggle('selected',Boolean(currentState));
    legend();renderMap();onExit?.();if(shouldFly)fly({...stateView(currentState,currentPreset),maxZoom:9});
  }
  function renderMap(){if(scene&&!mapFailed)scene.setProps({layers:layers()});}
  function initMap(){
    if(!window.deck){mapFailed=true;failure('3D rendering is unavailable','The graphics library did not load. You can still explore the same real data using the data explorer.');return;}
    try {
      view={...initialView(),...pendingView};pendingView=null;
      if(!reduced.matches&&!new URLSearchParams(location.search).get('state'))view={...view,zoom:view.zoom-1.5,pitch:0,bearing:24};scene=new deck.Deck({parent:$('deck'),initialViewState:view,controller:{touchRotate:true},layers:[],
        onViewStateChange:({viewState})=>{view=viewState;},
        onClick:info=>{if(place&&!fxOf()?.replaying&&!info.object&&info.coordinate&&view.zoom>=10)place.onMapClick(info.coordinate[1],info.coordinate[0]);},
        onError:error=>{mapFailed=true;failure('The 3D view could not render','Your browser could not initialize or maintain WebGL. Try again, or open the data explorer for the same observations.');console.warn('GeoCrash map renderer:',error.message);},
        getTooltip:({object,layer})=>!object?null:place&&layer.id.startsWith('place-')?place.tooltip(object):CELL_LAYERS.has(layer.id)?{text:`${fmt(object.properties.fatal_crashes)} fatal crashes\n${nameFor(object.properties.state_fips)} · ${years()}\n0.25° geographic cell · count, not risk`,className:'deck-tooltip'}:{text:object.properties.name,className:'deck-tooltip'}});
    }catch(error){mapFailed=true;failure('3D rendering is unavailable','This browser does not support the graphics needed for the map. The full data explorer and screening engine remain available.');}
  }
  function fly(target,duration=1100){
    if(!scene){if(!mapFailed)pendingView=target;return;}
    if(mapFailed)return;
    const nextView={...view,...target,transitionDuration:reduced.matches?0:duration,transitionInterpolator:new deck.FlyToInterpolator()};
    $('tilt').setAttribute('aria-pressed',String(nextView.pitch>0));
    view=nextView;busy=performance.now()+nextView.transitionDuration+150;scene.setProps({initialViewState:nextView});
  }
  function stateView(id,preset){
    if(!id)return initialView();
    if(preset)return{longitude:preset.lng,latitude:preset.lat,zoom:innerWidth<761?6:6.5,pitch:53,bearing:-15,maxZoom:9};
    const row=states.find(s=>Number(s.state_fips)===Number(id));if(!row)return initialView();
    const feature=boundaries.features.find(f=>Number(f.id)===Number(id));
    const coords=feature?.geometry.type==='Polygon'?feature.geometry.coordinates.flat():feature?.geometry.coordinates.flat(2)||[];
    const lngs=coords.map(p=>p[0]>0?p[0]-360:p[0]),lats=coords.map(p=>p[1]);
    const span=Math.max(Math.max(...lngs)-Math.min(...lngs),(Math.max(...lats)-Math.min(...lats))*1.5,1);
    return{longitude:Number(id)===2?-152:row.lng,latitude:row.lat,zoom:Math.max(3,Math.min(7,Math.log2(330/span)-(innerWidth<761?.8:0))),pitch:45,bearing:-10,maxZoom:9};
  }
  function renderSummary(data,map){
    summary=data;$('scope-name').textContent=currentState?nameFor(currentState):'United States';$('summary-years').textContent=years();
    countUp($('crashes'),data.fatal_crashes);countUp($('fatalities'),data.fatalities);countUp($('cells'),map.features.length);
    const yearly=data.years||[],peak=Math.max(1,...yearly.map(y=>y.fatal_crashes)),minutes=yearly.length*525600/Math.max(1,data.fatal_crashes);
    $('pace').innerHTML=data.fatal_crashes?`One fatal crash every <b>${minutes<90?minutes.toFixed(1)+' min':(minutes/60).toFixed(1)+' h'}</b> · <b>${(data.fatalities/(yearly.length*365.25)).toFixed(1)}</b> deaths a day`:'';
    $('trend').innerHTML=yearly.length>1?yearly.map((y,i)=>`<div title="${fmt(y.fatal_crashes)} fatal crashes in ${y.year}"><b>${(y.fatal_crashes/1000).toFixed(y.fatal_crashes<10000?1:0)}k</b><i style="height:${Math.round(100*y.fatal_crashes/peak)}%;animation-delay:${i*90}ms"></i><span>${y.year}</span></div>`).join(''):'';
    $('trend').setAttribute('aria-label',yearly.map(y=>`${y.year}: ${fmt(y.fatal_crashes)} fatal crashes`).join(', '));
    const leaders=currentState?[]:[...(data.states||[])].sort((a,b)=>b.fatal_crashes-a.fatal_crashes).slice(0,3);
    $('leaders').innerHTML=leaders.map(row=>`<li><button type="button" data-fips="${Number(row.state_fips)}"><span>${esc(row.state_name)}</span><b>${fmt(row.fatal_crashes)}</b><i style="width:${Math.round(100*row.fatal_crashes/leaders[0].fatal_crashes)}%"></i></button></li>`).join('');
    const c=map.coverage;
    $('summary-note').textContent=`${fmt(c.mapped_crashes)} crashes mapped; ${fmt(c.suppressed_crashes)} below the cell threshold; ${fmt(c.unlocated_crashes)} without coordinates. Counts are not traffic-adjusted risk.`;
    const params=new URLSearchParams();if(currentState)params.set('state',currentState);if(currentYear)params.set('year',currentYear);
    $('details').href='/explore/'+(params.size?'?'+params:'');
    if(!place)$('view-status').textContent=`NHTSA FARS · ${years()} · ${currentState?nameFor(currentState):fmt(data.fatal_crashes)+' fatal-crash records'} · historical data`;
  }
  async function update(preset=null,{fromBoot=false,keepView=false}={}){
    fxOf()?.stop?.();if(!fromBoot)exitPlace(false);const ticket=++generation,requestedState=$('state').value,requestedYear=$('year').value;
    $('apply').disabled=true;$('panel').setAttribute('aria-busy','true');$('view-status').textContent='Loading historical observations…';
    if(!mapFailed)$('error').hidden=true;
    const params=new URLSearchParams();if(requestedState)params.set('state',requestedState);if(requestedYear)params.set('year',requestedYear);
    try{
      const [data,map]=await Promise.all([request('/api/public/summary?'+params),request('/api/public/map?'+params)]);
      if(ticket!==generation)return;
      currentState=requestedState;currentYear=requestedYear;currentPreset=preset;cells=map.features;
      $('cell-detail').hidden=true;renderSummary(data,map);if(!keepView)fxOf()?.onData?.();renderMap();
      if(!place){document.body.classList.toggle('selected',Boolean(currentState));if(!keepView)fly(stateView(currentState,preset),fromBoot?2600:1100);}
      history.replaceState(null,'',location.pathname+(params.size?'?'+params:''));
    }catch(error){if(ticket!==generation)return;$('view-status').textContent='Data update failed · previous results retained';failure('The data could not load',`${error.message} Try again to load the selected state and year.`);}
    finally{if(ticket===generation){$('apply').disabled=false;$('panel').setAttribute('aria-busy','false');}}
  }
  function choose(id,preset=null){$('state').value=id;if(preset&&!satellite)setSatellite(true);return update(preset);}
  function reset(){ $('state').value='';$('year').value='';update(); }
  $('filters').addEventListener('submit',event=>{event.preventDefault();update();});
  $('reset').addEventListener('click',()=>fly(stateView(currentState,currentPreset)));
  $('reset-panel').addEventListener('click',reset);
  $('leaders').addEventListener('click',event=>{const fips=event.target.closest('button')?.dataset.fips;if(fips)choose(fips);});
  $('tilt').addEventListener('click',()=>{const isTilted=$('tilt').getAttribute('aria-pressed')==='true';fly({pitch:isTilted?0:48,bearing:isTilted?0:-12});});
  $('satellite').addEventListener('click',()=>setSatellite(!satellite));
  const closeMenu=()=>{document.querySelector('.top').classList.remove('menu-open');$('menu-toggle').setAttribute('aria-expanded','false');};
  $('menu-toggle').addEventListener('click',()=>{const open=document.querySelector('.top').classList.toggle('menu-open');$('menu-toggle').setAttribute('aria-expanded',String(open));});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu();});
  document.addEventListener('click',event=>{if(!event.target.closest('#menu-toggle,#site-nav'))closeMenu();});
  $('zoom-in').addEventListener('click',()=>fly({zoom:Math.min(view.maxZoom||9,view.zoom+.7)}));
  $('zoom-out').addEventListener('click',()=>fly({zoom:Math.max(2,view.zoom-.7)}));
  $('retry').addEventListener('click',()=>{if(mapFailed)location.reload();else if(!states.length)boot();else update(currentPreset);});
  async function boot(){
    try {
      const [list,geo]=await Promise.all([request('/api/public/states'),request('/assets/states.json')]);
      states=list.states.sort((a,b)=>a.state_name.localeCompare(b.state_name));boundaries=geo;
      for(const state of states){const option=document.createElement('option');option.value=String(state.state_fips);option.textContent=state.state_name;$('state').append(option);}
      $('state').disabled=false;
      const params=new URLSearchParams(location.search);if(states.some(s=>String(s.state_fips)===params.get('state')))$('state').value=params.get('state');
      if(['2021','2022','2023','2024'].includes(params.get('year')))$('year').value=params.get('year');
      if(!scene&&!mapFailed)initMap();await update(null,{fromBoot:true});
    }catch(error){failure('The map could not load',`${error.message} The data explorer offers the same historical records.`);$('view-status').textContent='Data unavailable · choose Try again';}
  }
  // Hooks for place.js (loaded after this file): place checks reuse this map, its filters and its error card.
  // fx.js adds motion on top: it may nudge the camera (jump), step the year filter and read the visible cells.
  function jump(target){if(!scene||mapFailed)return;view={...view,...target,transitionDuration:0};scene.setProps({initialViewState:view});}
  const setYear=year=>{$('year').value=year;return update(currentPreset,{keepView:true});};
  window.GeoCrash={request,failure,fly,jump,setYear,setSatellite,enterPlace,exitPlace,redraw:renderMap,getView:()=>view,cells:()=>cells,
    busyUntil:()=>busy,hasPlace:()=>Boolean(place),isSatellite:()=>satellite,isMapReady:()=>Boolean(scene)&&!mapFailed};
  boot();
})();
