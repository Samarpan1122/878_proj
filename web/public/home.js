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
  let pendingView=null;
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
  function color(feature){const n=feature.properties.fatal_crashes;const t=Math.min(1,Math.log1p(n)/Math.log(350));return [Math.round(64+114*t),Math.round(105+69*t),255,235];}
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
      getPosition:f=>f.geometry.coordinates,getElevation:f=>Math.sqrt(f.properties.fatal_crashes)*4400,
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
      ...(place?place.layers():[crashLayer()])
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
      view={...initialView(),...pendingView};pendingView=null;scene=new deck.Deck({parent:$('deck'),initialViewState:view,controller:{touchRotate:true},layers:[],
        onViewStateChange:({viewState})=>{view=viewState;},
        onClick:info=>{if(place&&!info.object&&info.coordinate&&view.zoom>=10)place.onMapClick(info.coordinate[1],info.coordinate[0]);},
        onError:error=>{mapFailed=true;failure('The 3D view could not render','Your browser could not initialize or maintain WebGL. Try again, or open the data explorer for the same observations.');console.warn('GeoCrash map renderer:',error.message);},
        getTooltip:({object,layer})=>!object?null:place&&layer.id.startsWith('place-')?place.tooltip(object):CELL_LAYERS.has(layer.id)?{text:`${fmt(object.properties.fatal_crashes)} fatal crashes\n${nameFor(object.properties.state_fips)} · ${years()}\n0.25° geographic cell · count, not risk`,className:'deck-tooltip'}:{text:object.properties.name,className:'deck-tooltip'}});
    }catch(error){mapFailed=true;failure('3D rendering is unavailable','This browser does not support the graphics needed for the map. The full data explorer and screening engine remain available.');}
  }
  function fly(target){
    if(!scene){if(!mapFailed)pendingView=target;return;}
    if(mapFailed)return;
    const nextView={...view,...target,transitionDuration:reduced.matches?0:1100,transitionInterpolator:new deck.FlyToInterpolator()};
    $('tilt').setAttribute('aria-pressed',String(nextView.pitch>0));
    view=nextView;scene.setProps({initialViewState:nextView});
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
    $('crashes').textContent=fmt(data.fatal_crashes);$('fatalities').textContent=fmt(data.fatalities);$('cells').textContent=fmt(map.features.length);
    const c=map.coverage;
    $('summary-note').textContent=`${fmt(c.mapped_crashes)} crashes mapped; ${fmt(c.suppressed_crashes)} below the cell threshold; ${fmt(c.unlocated_crashes)} without coordinates. Counts are not traffic-adjusted risk.`;
    const params=new URLSearchParams();if(currentState)params.set('state',currentState);if(currentYear)params.set('year',currentYear);
    $('details').href='/explore/'+(params.size?'?'+params:'');
    if(!place)$('view-status').textContent=`NHTSA FARS · ${years()} · ${currentState?nameFor(currentState):fmt(data.fatal_crashes)+' fatal-crash records'} · historical data`;
  }
  async function update(preset=null,{fromBoot=false}={}){
    if(!fromBoot)exitPlace(false);const ticket=++generation,requestedState=$('state').value,requestedYear=$('year').value;
    $('apply').disabled=true;$('panel').setAttribute('aria-busy','true');$('view-status').textContent='Loading historical observations…';
    if(!mapFailed)$('error').hidden=true;
    const params=new URLSearchParams();if(requestedState)params.set('state',requestedState);if(requestedYear)params.set('year',requestedYear);
    try{
      const [data,map]=await Promise.all([request('/api/public/summary?'+params),request('/api/public/map?'+params)]);
      if(ticket!==generation)return;
      currentState=requestedState;currentYear=requestedYear;currentPreset=preset;cells=map.features;
      $('cell-detail').hidden=true;renderSummary(data,map);renderMap();
      if(!place){document.body.classList.toggle('selected',Boolean(currentState));fly(stateView(currentState,preset));}
      history.replaceState(null,'',location.pathname+(params.size?'?'+params:''));
    }catch(error){if(ticket!==generation)return;$('view-status').textContent='Data update failed · previous results retained';failure('The data could not load',`${error.message} Try again to load the selected state and year.`);}
    finally{if(ticket===generation){$('apply').disabled=false;$('panel').setAttribute('aria-busy','false');}}
  }
  function choose(id,preset=null){$('state').value=id;if(preset&&!satellite)setSatellite(true);return update(preset);}
  function reset(){ $('state').value='';$('year').value='';update(); }
  $('filters').addEventListener('submit',event=>{event.preventDefault();update();});
  $('reset').addEventListener('click',()=>fly(stateView(currentState,currentPreset)));
  $('reset-panel').addEventListener('click',reset);
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
  window.GeoCrash={request,failure,fly,enterPlace,exitPlace,redraw:renderMap,getView:()=>view,isMapReady:()=>Boolean(scene)&&!mapFailed};
  boot();
})();
