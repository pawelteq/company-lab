(() => {
  'use strict';
  const svg = document.querySelector('svg'), tip = document.querySelector('.tooltip');
  const NS = 'http://www.w3.org/2000/svg', origin = location.origin;
  let features = [], items = [], powiatyList = [], gminyList = [];
  let selection = {city:'',region:'',county:'',municipality:''}, mode = 'cities', ready = false;
  let view = [0,0,760,720], priorRegion = '', priorCounty = '', priorMunicipality = '';
  let powiatyFeatures = null, gminyFeatures = null;
  let showPowiaty = false, showGminy = false;
  let powiatyPromise = null, gminyPromise = null;
  const financialMode = new URLSearchParams(location.search).has('financial');
  let financialPayload = null;
  const provinceCodes = {'dolnoslaskie':'02','kujawsko-pomorskie':'04','lubelskie':'06','lubuskie':'08','lodzkie':'10','malopolskie':'12','mazowieckie':'14','opolskie':'16','podkarpackie':'18','podlaskie':'20','pomorskie':'22','slaskie':'24','swietokrzyskie':'26','warminsko-mazurskie':'28','wielkopolskie':'30','zachodniopomorskie':'32'};
  if(financialMode) document.body.classList.add('financial-mode');
  const project = ([lon,lat]) => [(lon-14)*72, (55-lat)*118+6];
  const norm = s => (s || '').toLocaleLowerCase('pl').replace(/ł/g, 'l').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/^(powiat|gmina|m\.|miasto)\s+/i, '').trim();
  function node(tag, attrs, text) { const el = document.createElementNS(NS,tag); Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,String(v))); if(text!=null)el.textContent=text; return el; }
  function rings(f) { return f.geometry.type==='Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat(); }
  function bounds(f) { const p=rings(f).flat().map(project); return [Math.min(...p.map(v=>v[0])),Math.min(...p.map(v=>v[1])),Math.max(...p.map(v=>v[0])),Math.max(...p.map(v=>v[1]))]; }
  function announce(type, extra={}) { parent.postMessage({type,...extra},origin); }

  function getSelectedList(key) {
    if (!selection) return [];
    if (Array.isArray(selection[key])) return selection[key].map(norm).filter(Boolean);
    const s = selection[key] || '';
    return typeof s === 'string' ? s.split(',').map(norm).filter(Boolean) : [];
  }

  function isItemActive(name, list) {
    if (!name || !list || !list.length) return false;
    const n = norm(name);
    return list.some(item => item === n || item.includes(n) || n.includes(item));
  }

  function activate(el,fn,label) {
    el.setAttribute('role','button');
    el.setAttribute('tabindex','0');
    el.setAttribute('aria-label',label);
    el.addEventListener('click',fn);
    el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();fn(e);}});
    el.addEventListener('focus',()=>tip.textContent=label);
    el.addEventListener('mouseenter',()=>tip.textContent=label);
    el.append(node('title',{},label));
  }

  function loadPowiaty(cb) {
    if (powiatyFeatures) { cb?.(); return Promise.resolve(powiatyFeatures); }
    if (!powiatyPromise) {
      powiatyPromise = fetch('powiaty.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{
        powiatyFeatures = data.features;
        return powiatyFeatures;
      }).catch(()=>{
        powiatyPromise = null;
        tip.textContent = 'Nie udało się pobrać granic powiatów.';
        return null;
      });
    }
    return powiatyPromise.then(data=>{ if(data) cb?.(); return data; });
  }

  function loadGminy(cb) {
    if (gminyFeatures) { cb?.(); return Promise.resolve(gminyFeatures); }
    if (!gminyPromise) {
      gminyPromise = fetch('gminy.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{
        gminyFeatures = data.features;
        return gminyFeatures;
      }).catch(()=>{
        gminyPromise = null;
        tip.textContent = 'Nie udało się pobrać granic gmin.';
        return null;
      });
    }
    return gminyPromise.then(data=>{ if(data) cb?.(); return data; });
  }

  function render() {
    svg.replaceChildren();svg.setAttribute('viewBox',view.join(' '));
    const unit=view[2]/760, fontUnit=view[2]/Math.min(760,svg.clientWidth || 760), compact=svg.clientWidth<420;

    if (financialMode && financialPayload) {
      renderFinancial(unit, fontUnit, compact);
      return;
    }

    const activeCounties = Array.from(new Set(getSelectedList('counties').concat(getSelectedList('county'))));
    const activeGminy = Array.from(new Set(getSelectedList('municipalities').concat(getSelectedList('municipality'))));
    const activeRegions = Array.from(new Set(getSelectedList('regions').concat(getSelectedList('region'))));
    const activeCities = Array.from(new Set(getSelectedList('cities').concat(getSelectedList('city'))));

    if (mode === 'powiaty') {
      // MODE: POWIATY (Interactive county map)
      if (!powiatyFeatures) {
        tip.textContent = 'Wczytywanie granic powiatów…';
        loadPowiaty(() => { tip.textContent = ''; render(); });
        for(const f of features) {
          const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
          svg.append(node('path',{d,fill:'#f0f4f2',stroke:'#c2d4cc',class:'province-bg'}));
        }
        return;
      }
      const pCountMap = new Map();
      powiatyList.forEach(p => {
        pCountMap.set(norm(p.county), p.count);
        pCountMap.set(norm(p.county_key), p.count);
      });
      const maxCount = Math.max(1, ...powiatyList.map(p => p.count));

      // Province background contours
      for(const f of features) {
        const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
        svg.append(node('path',{d,fill:'#f5f8f7',stroke:'#a8c2b7','stroke-width':'1.8','vector-effect':'non-scaling-stroke',class:'province-bg'}));
      }

      for (const f of powiatyFeatures) {
        const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
        const rawName = f.properties.name || '';
        const nName = norm(rawName);
        let count = pCountMap.get(nName) || 0;
        if (!count) {
          for (const [k, v] of pCountMap.entries()) {
            if (k && (k === nName || k.includes(nName) || nName.includes(k))) { count = v; break; }
          }
        }
        const isSelected = isItemActive(rawName, activeCounties);
        let fill;
        if (isSelected) {
          fill = '#bae6fd';
        } else if (activeCounties.length > 0) {
          fill = '#f1f5f9';
        } else if (count) {
          fill = `hsl(199 55% ${Math.max(68, 94 - 26 * Math.sqrt(count / maxCount))}%)`;
        } else {
          fill = '#f8fafc';
        }
        const path = node('path', { d, fill, class: isSelected ? 'powiat-polygon active' : 'powiat-polygon', 'fill-rule': 'evenodd', 'aria-pressed': isSelected });
        const pLabel = rawName.startsWith('powiat') || rawName.startsWith('m.') ? rawName : `Powiat ${rawName}`;
        const title = count ? `${pLabel}: ${count.toLocaleString('pl-PL')} firm. Kliknij, aby filtrować (Ctrl+klik: zaznacz kilka).` : `${pLabel}: brak firm. Kliknij, aby wybrać (Ctrl+klik: zaznacz kilka).`;
        activate(path, (e) => {
          if (suppressClick) return;
          const ctrl = !!(e && (e.ctrlKey || e.metaKey));
          announce('company-map-select-county', { county: rawName, ctrlKey: ctrl });
        }, title);
        svg.append(path);
      }

      // Add labels for prominent or selected powiaty
      for (const f of powiatyFeatures) {
        const rawName = f.properties.name || '';
        const isSelected = isItemActive(rawName, activeCounties);
        let count = pCountMap.get(norm(rawName)) || 0;
        if (isSelected || (unit < 0.7 && count > 50) || (unit < 0.4 && count > 10)) {
          const [x1,y1,x2,y2] = bounds(f);
          const x = (x1 + x2) / 2, y = (y1 + y2) / 2;
          const text = node('text', { x, y, class: 'label', 'font-size': (isSelected ? 11 : 9) * fontUnit });
          text.append(node('tspan', { x, dy: 0 }, rawName));
          if (count) text.append(node('tspan', { x, dy: 11 * fontUnit, 'font-weight': 700 }, count.toLocaleString('pl-PL')));
          svg.append(text);
        }
      }
      return;
    }

    if (mode === 'gminy') {
      // MODE: GMINY (Interactive municipality map)
      if (!gminyFeatures) {
        tip.textContent = 'Wczytywanie granic gmin…';
        loadGminy(() => { tip.textContent = ''; render(); });
        for(const f of features) {
          const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
          svg.append(node('path',{d,fill:'#f0f4f2',stroke:'#c2d4cc',class:'province-bg'}));
        }
        return;
      }
      const gCountMap = new Map();
      gminyList.forEach(g => {
        gCountMap.set(norm(g.municipality), g.count);
        gCountMap.set(norm(g.muni_key), g.count);
      });
      const maxGminaCount = Math.max(1, ...gminyList.map(g => g.count));

      for(const f of features) {
        const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
        svg.append(node('path',{d,fill:'#f5f8f7',stroke:'#a8c2b7','stroke-width':'1.8','vector-effect':'non-scaling-stroke',class:'province-bg'}));
      }

      for (const f of gminyFeatures) {
        const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
        const rawName = f.properties.name || '';
        const nName = norm(rawName);
        let count = gCountMap.get(nName) || 0;
        if (!count) {
          for (const [k, v] of gCountMap.entries()) {
            if (k && (k === nName || k.includes(nName) || nName.includes(k))) { count = v; break; }
          }
        }
        const isSelected = isItemActive(rawName, activeGminy);
        let fill;
        if (isSelected) {
          fill = '#bae6fd';
        } else if (activeGminy.length > 0) {
          fill = '#f1f5f9';
        } else if (count) {
          fill = `hsl(199 50% ${Math.max(70, 95 - 25 * Math.sqrt(count / maxGminaCount))}%)`;
        } else {
          fill = '#f8fafc';
        }
        const path = node('path', { d, fill, class: isSelected ? 'gmina-polygon active' : 'gmina-polygon', 'fill-rule': 'evenodd', 'aria-pressed': isSelected });
        const gLabel = rawName.startsWith('Gmina') ? rawName : `Gmina ${rawName}`;
        const title = count ? `${gLabel}: ${count.toLocaleString('pl-PL')} firm. Kliknij, aby filtrować (Ctrl+klik: zaznacz kilka).` : `${gLabel}: brak firm. Kliknij, aby wybrać (Ctrl+klik: zaznacz kilka).`;
        activate(path, (e) => {
          if (suppressClick) return;
          const ctrl = !!(e && (e.ctrlKey || e.metaKey));
          announce('company-map-select-gmina', { municipality: rawName, ctrlKey: ctrl });
        }, title);
        svg.append(path);
      }
      return;
    }

    // MODE: REGIONS or CITIES
    const counts=new Map();items.forEach(p=>counts.set(p.region_key,(counts.get(p.region_key)||0)+p.count));
    const max=Math.max(1,...counts.values());

    for(const f of features) {
      const key=f.properties.key, count=counts.get(key)||0;
      const isSelected = activeRegions.includes(key) || activeRegions.includes(norm(f.properties.name));
      let fill;
      if (activeRegions.length > 0) {
        fill = isSelected ? '#d5eee3' : '#edf2ef';
      } else {
        fill = count ? `hsl(155 26% ${93-18*Math.sqrt(count/max)}%)` : '#f0f4f2';
      }
      const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
      const path=node('path',{d,fill,class:isSelected?'province active':'province','fill-rule':'evenodd','aria-pressed':isSelected});
      if(count) {
        activate(path,(e)=>{
          if (suppressClick) return;
          const ctrl = !!(e && (e.ctrlKey || e.metaKey));
          announce('company-map-select-region', { region: key, ctrlKey: ctrl });
        },`${f.properties.name}: ${count.toLocaleString('pl-PL')} firm. Filtruj województwo (Ctrl+klik: zaznacz kilka).`);
      } else {
        path.append(node('title',{},`${f.properties.name}: brak firm dla bieżących filtrów`));
      }
      svg.append(path);
    }

    if (showGminy && gminyFeatures) {
      const gGroup = node('g', { class: 'layer-gminy' });
      for (const f of gminyFeatures) {
        const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
        const rawName = f.properties.name || '';
        const name = rawName ? `Gmina ${rawName}` : 'Gmina';
        const isSelected = isItemActive(rawName, activeGminy);
        const path=node('path',{d,class:isSelected?'gmina-boundary active':'gmina-boundary'});
        activate(path, (e) => {
          if (suppressClick) return;
          const ctrl = !!(e && (e.ctrlKey || e.metaKey));
          announce('company-map-select-gmina', { municipality: rawName, ctrlKey: ctrl });
        }, `${name} — kliknij, aby filtrować gminę (Ctrl+klik: zaznacz kilka)`);
        gGroup.append(path);
      }
      svg.append(gGroup);
    }

    if (showPowiaty && powiatyFeatures) {
      const pGroup = node('g', { class: 'layer-powiaty' });
      for (const f of powiatyFeatures) {
        const d=rings(f).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
        const rawName = f.properties.name || '';
        const name = rawName ? (rawName.startsWith('powiat') || rawName.startsWith('m.') ? rawName : `Powiat ${rawName}`) : 'Powiat';
        const isSelected = isItemActive(rawName, activeCounties);
        const path=node('path',{d,class:isSelected?'powiat-boundary active':'powiat-boundary'});
        activate(path, (e) => {
          if (suppressClick) return;
          const ctrl = !!(e && (e.ctrlKey || e.metaKey));
          announce('company-map-select-county', { county: rawName, ctrlKey: ctrl });
        }, `${name} — kliknij, aby filtrować powiat (Ctrl+klik: zaznacz kilka)`);
        pGroup.append(path);
      }
      svg.append(pGroup);
    }

    if(mode==='regions') {
      for(const f of features) {
        const [x1,y1,x2,y2]=bounds(f);
        const centres={'slaskie':[18.85,50.28],'malopolskie':[20.2,49.72],'podkarpackie':[22.4,50.0]};
        const [x,y]=centres[f.properties.key]?project(centres[f.properties.key]):[(x1+x2)/2,(y1+y2)/2];
        const name=f.properties.name, count=counts.get(f.properties.key)||0;
        const text=node('text',{x,y,class:'label','font-size':(compact?9:12)*fontUnit});
        const parts=name==='Zachodniopomorskie'?['Zachodnio','pomorskie']:name.includes('-')?name.split('-'):[name];
        parts.forEach((part,i)=>text.append(node('tspan',{x,dy:i?(compact?11:14)*fontUnit:0},part+(i<parts.length-1?'-':''))));
        text.append(node('tspan',{x,dy:(compact?12:17)*fontUnit,'font-weight':700},count.toLocaleString('pl-PL')));svg.append(text);
      }
    } else {
      const points=items.filter(p=>p.status==='matched'&&Number.isFinite(p.lat)&&Number.isFinite(p.lon));
      const top=new Set(points.filter(p=>!activeRegions.length||activeRegions.includes(p.region_key)).slice(0,activeRegions.length?10:12).map(p=>p.city_key+'|'+p.region_key));
      for(const p of [...points].reverse()) {
        const [x,y]=project([p.lon,p.lat]);
        const active=isItemActive(p.city_key, activeCities);
        const inRegion=!activeRegions.length||activeRegions.includes(p.region_key);
        const radius=(active?10:Math.max(2.8, Math.min(10, 2.5+Math.log10(1+p.count)*2.2)))*unit;
        if(active)svg.append(node('circle',{cx:x,cy:y,r:radius+5*unit,class:'selected-halo'}));
        const fill=active?'#02261e':inRegion?'#093d31':'#5c776e';
        const opacity=inRegion?1:0.5;
        const dot=node('circle',{cx:x,cy:y,r:radius,fill,class:'dot',opacity,'aria-pressed':active});
        const title=`${p.city}, ${p.region}: ${p.count.toLocaleString('pl-PL')} firm. Kliknij, aby filtrować (Ctrl+klik: zaznacz kilka).`;
        activate(dot,(e)=>{
          if (suppressClick) return;
          const ctrl = !!(e && (e.ctrlKey || e.metaKey));
          announce('company-map-select-city', { city: p.city_key, region: p.region_key, ctrlKey: ctrl });
        },title);
        if(!top.has(p.city_key+'|'+p.region_key)&&!active)dot.setAttribute('tabindex','-1');
        svg.append(dot);
      }
      for(const p of points) {
        const active=isItemActive(p.city_key, activeCities);
        if(!active && (activeCities.length||!top.has(p.city_key+'|'+p.region_key)))continue;
        const [x,y]=project([p.lon,p.lat]);
        svg.append(node('text',{x:x+12*unit,y:y-10*unit,class:'city-label','font-size':(active?14:compact?10:12)*fontUnit},p.city));
      }
    }
  }

  function financeFeatures() {
    const level = financialPayload?.level;
    if (level === 'county') return powiatyFeatures || [];
    if (level === 'municipality') return gminyFeatures || [];
    return features;
  }

  function financeFeatureId(feature) {
    return financialPayload?.level === 'voivodeship'
      ? provinceCodes[feature.properties.key]
      : String(feature.properties.code || '');
  }

  function financeColor(value, values, scale, viewMode) {
    if (value == null || !Number.isFinite(value)) return '#d9dcde';
    if (viewMode === 'change') {
      const maxAbs = Math.max(1e-9, ...values.map(v => Math.abs(v)));
      const t = Math.min(1, Math.abs(value) / maxAbs);
      if (Math.abs(value) < maxAbs * .08) return '#eee9e4';
      return value < 0
        ? ['#dce7eb','#a6c1ca','#5f8d9d','#315d6f'][Math.min(3, Math.floor(t * 4))]
        : ['#f7dfd3','#eead8f','#da7045','#9e3513'][Math.min(3, Math.floor(t * 4))];
    }
    const palette = ['#f7e7df','#f0c8b5','#e9a27f','#d96f43','#9e3513'];
    const sorted = [...values].sort((a,b)=>a-b);
    if (!sorted.length) return '#d9dcde';
    const percentile = q => {
      const pos=(sorted.length-1)*q, low=Math.floor(pos), high=Math.ceil(pos);
      return low===high?sorted[low]:sorted[low]+(sorted[high]-sorted[low])*(pos-low);
    };
    if (scale?.method === 'minmax' || scale?.method === 'manual' || scale?.method === 'percentile') {
      const validManual = scale.method === 'manual' && Number.isFinite(scale.min) && Number.isFinite(scale.max) && scale.min < scale.max;
      const lo = validManual ? scale.min : scale.method === 'percentile' ? percentile(.05) : sorted[0];
      const hi = validManual ? scale.max : scale.method === 'percentile' ? percentile(.95) : sorted.at(-1);
      const t = Math.max(0, Math.min(.999, (value-lo) / Math.max(1e-9,hi-lo)));
      return palette[Math.floor(t*palette.length)];
    }
    let bucket = 0;
    for (let i=1;i<palette.length;i++) {
      const threshold = percentile(i/(palette.length-1));
      if (value >= threshold) bucket = i;
    }
    return palette[bucket];
  }

  function renderFinancial(unit, fontUnit, compact) {
    const level = financialPayload.level;
    if (level === 'county' && !powiatyFeatures) {
      tip.textContent='Wczytywanie granic powiatów…'; loadPowiaty(render); return;
    }
    if (level === 'municipality' && !gminyFeatures) {
      tip.textContent='Wczytywanie granic gmin…'; loadGminy(render); return;
    }
    const regionMap = new Map((financialPayload.regions || []).map(region => [String(region.region_id), region]));
    const values = (financialPayload.regions || []).map(region => region.value).filter(Number.isFinite);
    const candidates = [];
    const regionPaths = [];
    for (const feature of financeFeatures()) {
      const id = financeFeatureId(feature), region = regionMap.get(id);
      const d=rings(feature).map(r=>'M'+r.map(c=>project(c).map(v=>v.toFixed(2)).join(',')).join('L')+'Z').join('');
      const selected = id === financialPayload.selectedRegionId;
      const fill = region?.insufficient_data ? '#d9dcde' : financeColor(region?.value, values, financialPayload.scale, financialPayload.view);
      const path=node('path',{d,fill,class:`financial-region${selected?' active':''}${region?.insufficient_data?' insufficient':''}`,'fill-rule':'evenodd','aria-pressed':selected});
      const label = region?.insufficient_data
        ? `${region.region_name}: niewystarczająca liczba danych (${region.metric_company_count}/${financialPayload.minCompanies}).`
        : region?.value == null
          ? `${region?.region_name || feature.properties.name}: brak danych.`
          : `${region.region_name}. ${financialPayload.metricLabel}: ${region.formatted_value}. Firmy z wartością: ${region.metric_company_count}. Pozycja: ${region.rank || '—'} z ${region.rank_total || '—'}.`;
      activate(path,()=>announce('financial-map-select',{regionId:id,regionName:region?.region_name || feature.properties.name}),label);
      path.setAttribute('data-region-id', id);
      regionPaths.push(path);
      svg.append(path);
      if (region?.value != null && !region.insufficient_data) {
        const [x1,y1,x2,y2]=bounds(feature);
        const centres={'slaskie':[18.85,50.28],'malopolskie':[20.2,49.72],'podkarpackie':[22.4,50.0]};
        const point=level==='voivodeship'&&centres[feature.properties.key]?project(centres[feature.properties.key]):[(x1+x2)/2,(y1+y2)/2];
        candidates.push({feature,region,x:point[0],y:point[1],size:Math.max(x2-x1,y2-y1)});
      }
    }
    const focusIndex = Math.max(0, regionPaths.findIndex(path => path.getAttribute('data-region-id') === String(financialPayload.selectedRegionId || '')));
    regionPaths.forEach((path,index)=>path.setAttribute('tabindex',index===focusIndex?'0':'-1'));
    const occupied=[];
    const showDense = level==='voivodeship' || (level==='county' && view[2]<540) || (level==='municipality' && view[2]<190);
    if (financialPayload.showValues && showDense) {
      candidates.sort((a,b)=>(b.region.metric_company_count||0)-(a.region.metric_company_count||0));
      for (const item of candidates) {
        const minDistance=level==='voivodeship'?50*unit:level==='county'?25*unit:20*unit;
        if (occupied.some(point=>Math.hypot(point.x-item.x,point.y-item.y)<minDistance)) continue;
        occupied.push(item);
        const size=(level==='voivodeship'?(compact?9:11):level==='county'?7.5:6.5)*fontUnit;
        const text=node('text',{x:item.x,y:item.y,class:'financial-label','font-size':size});
        if (level==='voivodeship' && financialPayload.showNames) text.append(node('tspan',{x:item.x,dy:0,class:'region-name'},item.region.region_name));
        text.append(node('tspan',{x:item.x,dy:level==='voivodeship'&&financialPayload.showNames?size*1.25:0,class:'region-value'},item.region.formatted_value));
        svg.append(text);
      }
    }
    tip.textContent = level==='municipality' && view[2]>=190
      ? 'Przybliż mapę, aby zobaczyć wartości gmin · kliknij obszar po szczegóły'
      : 'Kliknij region po szczegóły · przeciągnij i użyj kółka do powiększania';
  }

  const btnPowiaty = document.querySelector('#toggle-powiaty');
  const btnGminy = document.querySelector('#toggle-gminy');

  if (btnPowiaty) {
    btnPowiaty.onclick = () => {
      announce('company-map-set-mode', { mode: mode === 'powiaty' ? 'cities' : 'powiaty' });
    };
  }

  if (btnGminy) {
    btnGminy.onclick = () => {
      announce('company-map-set-mode', { mode: mode === 'gminy' ? 'cities' : 'gminy' });
    };
  }

  window.addEventListener('message',e=>{
    if(e.source!==parent||e.origin!==origin)return;
    if(e.data?.type==='company-map-hello'&&ready)announce('company-map-ready');
    if(e.data?.type==='company-map-pointerup'){if(drag)endDrag({pointerId:drag.id});return;}
    if(e.data?.type==='financial-map-focus'){
      const target=financeFeatures().find(feature=>financeFeatureId(feature)===String(e.data.regionId||''));
      if(target){const [a,b,c,d]=bounds(target);const pad=financialPayload?.level==='voivodeship'?80:30;const size=Math.max(c-a,(d-b)*760/720)+pad;view=[(a+c-size)/2,(b+d-size*720/760)/2,size,size*720/760];render();}
      return;
    }
    if(e.data?.type==='financial-map-data'&&financialMode){
      financialPayload=e.data.payload||null;
      const level=financialPayload?.level;
      if(level==='county'&&!powiatyFeatures){loadPowiaty(render);return;}
      if(level==='municipality'&&!gminyFeatures){loadGminy(render);return;}
      render();return;
    }
    if(e.data?.type!=='company-map-data'||!Array.isArray(e.data.items))return;
    items=e.data.items;
    powiatyList=Array.isArray(e.data.powiaty)?e.data.powiaty:[];
    gminyList=Array.isArray(e.data.gminy)?e.data.gminy:[];
    selection=Object.assign({city:'',region:'',county:'',municipality:''},e.data.selection||{});
    mode=e.data.mode || 'cities';

    if (mode === 'powiaty' && !powiatyFeatures) {
      loadPowiaty(() => render());
    } else if (mode === 'gminy' && !gminyFeatures) {
      loadGminy(() => render());
    }

    if(selection.region!==priorRegion){
      priorRegion=selection.region;
      const firstReg = (selection.region || '').split(',')[0].trim();
      const f=features.find(f=>f.properties.key===firstReg);
      if(f && (!selection.region.includes(',') )){
        const [a,b,c,d]=bounds(f);
        const size=Math.max(c-a,(d-b)*760/720)+80;
        view=[(a+c-size)/2,(b+d-size*720/760)/2,size,size*720/760];
      }else if (!selection.county && !selection.municipality) {
        view=[0,0,760,720];
      }
    }
    if (selection.county !== priorCounty) {
      priorCounty = selection.county;
      const firstCounty = (selection.county || '').split(',')[0].trim();
      if (firstCounty && !selection.county.includes(',') && powiatyFeatures) {
        const pf = powiatyFeatures.find(f => {
          const n = norm(f.properties.name);
          const sc = norm(firstCounty);
          return n === sc || sc.includes(n) || n.includes(sc);
        });
        if (pf) {
          const [a,b,c,d]=bounds(pf);
          const size=Math.max(c-a,(d-b)*760/720)+60;
          view=[(a+c-size)/2,(b+d-size*720/760)/2,size,size*720/760];
        }
      }
    }
    render();
  });

  function zoom(factor){const [x,y,w,h]=view;const width=Math.max(100,Math.min(900,w*factor)),height=width*720/760;view=[x+(w-width)/2,y+(h-height)/2,width,height];render();}
  let wheelFrame=0;
  let drag=null, suppressClick=false;
  svg.addEventListener('pointerdown',e=>{
    if(e.button!==0 || !e.isPrimary)return;
    const matrix=svg.getScreenCTM(); if(!matrix)return;
    suppressClick=false;
    cancelAnimationFrame(wheelFrame);
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,view:[...view],inverse:matrix.inverse(),moved:false};
  });
  window.addEventListener('pointermove',e=>{
    if(!drag || e.pointerId!==drag.id)return;
    if(!(e.buttons&1)){endDrag(e);return;}
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    if(!drag.moved && Math.hypot(dx,dy)<5)return;
    if(!drag.moved){
      drag.moved=true;suppressClick=true;
      try{svg.setPointerCapture(e.pointerId);}catch{}
      svg.classList.add('dragging');
    }
    e.preventDefault();
    const m=drag.inverse;
    view=[drag.view[0]-m.a*dx-m.c*dy,drag.view[1]-m.b*dx-m.d*dy,drag.view[2],drag.view[3]];
    svg.setAttribute('viewBox',view.join(' '));
  });
  function endDrag(e){
    if(!drag || e.pointerId!==drag.id)return;
    const id=drag.id;drag=null;
    svg.classList.remove('dragging');
    try{if(svg.hasPointerCapture(id))svg.releasePointerCapture(id);}catch{}
  }
  window.addEventListener('pointerup',endDrag);
  window.addEventListener('pointercancel',endDrag);
  svg.addEventListener('lostpointercapture',endDrag);
  window.addEventListener('blur',()=>{if(drag)endDrag({pointerId:drag.id});});
  svg.addEventListener('click',e=>{
    if(suppressClick && e.detail!==0){e.preventDefault();e.stopImmediatePropagation();}
  },true);
  svg.addEventListener('keydown',e=>{
    if(!financialMode || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(e.key))return;
    const target=e.target?.closest?.('.financial-region');
    if(!target)return;
    const paths=[...svg.querySelectorAll('.financial-region')];
    const current=paths.indexOf(target);
    if(current<0||!paths.length)return;
    let next=current;
    if(e.key==='Home')next=0;
    else if(e.key==='End')next=paths.length-1;
    else if(e.key==='ArrowLeft'||e.key==='ArrowUp')next=(current-1+paths.length)%paths.length;
    else next=(current+1)%paths.length;
    paths[current].setAttribute('tabindex','-1');
    paths[next].setAttribute('tabindex','0');
    paths[next].focus();
    e.preventDefault();
  });
  svg.addEventListener('dragstart',e=>e.preventDefault());
  svg.addEventListener('wheel',e=>{
    e.preventDefault();
    if(drag)return;
    const matrix=svg.getScreenCTM(); if(!matrix)return;
    const point=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());
    const [x,y,w,h]=view;
    const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?300:1);
    const width=Math.max(70,Math.min(950,w*Math.exp(Math.max(-.35,Math.min(.35,delta*.002)))));
    const ratio=width/w;
    view=[point.x-(point.x-x)*ratio,point.y-(point.y-y)*ratio,width,h*ratio];
    svg.setAttribute('viewBox',view.join(' '));
    cancelAnimationFrame(wheelFrame);wheelFrame=requestAnimationFrame(render);
  },{passive:false});
  document.querySelector('#in').onclick=()=>zoom(.75);document.querySelector('#out').onclick=()=>zoom(1.33);
  document.querySelector('#whole').onclick=()=>{view=[0,0,760,720];render();};
  window.addEventListener('resize',()=>{if(ready)render();});
  fetch('poland.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{
    features=data.features;ready=true;render();announce('company-map-ready');
    setTimeout(() => loadPowiaty(), 800);
  }).catch(()=>{tip.textContent='Nie udało się pobrać granic mapy.';announce('company-map-error');});
})();
