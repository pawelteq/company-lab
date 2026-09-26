import { useEffect, useRef, useState } from 'react';
import { useApi } from './api';
import './location-map.css';

export type LocationSelection = {
  city: string;
  region: string;
  county?: string;
  municipality?: string;
  cities?: string[];
  regions?: string[];
  counties?: string[];
  municipalities?: string[];
};

type Place = {
  city: string | null;
  region: string | null;
  county?: string | null;
  municipality?: string | null;
  city_key: string;
  region_key: string;
  count: number;
  status: string;
  lat?: number;
  lon?: number;
};

type CountyItem = {
  county: string;
  county_key: string;
  region: string;
  region_key: string;
  count: number;
};

type MunicipalityItem = {
  municipality: string;
  muni_key: string;
  county: string;
  county_key: string;
  region: string;
  region_key: string;
  count: number;
};

type Locations = {
  collection_id: string;
  items: Place[];
  powiaty?: CountyItem[];
  gminy?: MunicipalityItem[];
  total: number;
  mapped: number;
  gazetteer_available: boolean;
};

const norm = (s: string) => s.toLocaleLowerCase('pl').replace(/ł/g, 'l').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
const fmt = (n: number) => n.toLocaleString('pl-PL');

function getList(value?: string | string[]): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.map(s => s.trim()).filter(Boolean);
  return value.split(',').map(s => s.trim()).filter(Boolean);
}

function toggleItem(list: string[], item: string): string[] {
  const normItem = norm(item);
  const exists = list.some(x => norm(x) === normItem);
  if (exists) {
    return list.filter(x => norm(x) !== normItem);
  }
  return [...list, item];
}

export function LocationMap({ collection, query, status, segment, selection, onChange, extraQuery }: {
  extraQuery?: string; collection: string; query: string; status: string; segment: string;
  selection: LocationSelection; onChange: (value: LocationSelection) => void;
}) {
  const params = new URLSearchParams({ collection, q: query, status, segment });
  if (selection.county) params.set('county', selection.county);
  if (selection.municipality) params.set('municipality', selection.municipality);
  const state = useApi<Locations>(`/api/profiles/locations?${params}&${extraQuery || ''}`);
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [search, setSearch] = useState('');
  const [listLimit, setListLimit] = useState(30);
  const [mode, setMode] = useState<'cities' | 'regions' | 'powiaty' | 'gminy'>('cities');
  const [listTab, setListTab] = useState<'cities' | 'powiaty' | 'gminy'>('cities');
  const data = state.loading || state.error ? undefined : state.data;

  useEffect(() => {
    function receive(event: MessageEvent) {
      if (event.source !== frame.current?.contentWindow || event.origin !== window.location.origin) return;
      if (event.data?.type === 'company-map-ready') { setReady(true); setMapError(false); }
      if (event.data?.type === 'company-map-error') setMapError(true);
      if (event.data?.type === 'company-map-select-county') {
        const c = event.data.county || '';
        const ctrl = !!event.data.ctrlKey;
        if (!c) {
          onChange({ city: '', region: selection.region, county: '', municipality: '' });
          return;
        }
        const cNorm = norm(c);
        const matched = (data?.powiaty ?? []).find(p => {
          const pk = norm(p.county_key);
          const pn = norm(p.county);
          return pk === cNorm || pn === cNorm || pk.includes(cNorm) || cNorm.includes(pk) || pn.includes(cNorm) || cNorm.includes(pn);
        });
        const countyKey = matched ? matched.county_key : cNorm;
        const regionKey = matched ? matched.region_key : selection.region;

        if (ctrl) {
          const current = getList(selection.county);
          const next = toggleItem(current, countyKey);
          onChange({
            city: '',
            region: selection.region,
            county: next.join(','),
            municipality: selection.municipality,
            counties: next,
          });
        } else {
          const isCurrent = selection.county === countyKey;
          onChange(isCurrent
            ? { city: '', region: selection.region, county: '', municipality: '' }
            : { city: '', region: regionKey, county: countyKey, municipality: '', counties: [countyKey] }
          );
        }
        return;
      }
      if (event.data?.type === 'company-map-select-gmina') {
        const m = event.data.municipality || '';
        const ctrl = !!event.data.ctrlKey;
        if (!m) {
          onChange({ city: '', region: selection.region, county: selection.county, municipality: '' });
          return;
        }
        const mNorm = norm(m);
        const matched = (data?.gminy ?? []).find(g => {
          const mk = norm(g.muni_key);
          const mn = norm(g.municipality);
          return mk === mNorm || mn === mNorm || mk.includes(mNorm) || mNorm.includes(mk) || mn.includes(mNorm) || mNorm.includes(mn);
        });
        const muniKey = matched ? matched.muni_key : mNorm;
        const countyKey = matched ? matched.county_key : selection.county;
        const regionKey = matched ? matched.region_key : selection.region;

        if (ctrl) {
          const current = getList(selection.municipality);
          const next = toggleItem(current, muniKey);
          onChange({
            city: '',
            region: selection.region,
            county: selection.county,
            municipality: next.join(','),
            municipalities: next,
          });
        } else {
          const isCurrent = selection.municipality === muniKey;
          onChange(isCurrent
            ? { city: '', region: selection.region, county: selection.county, municipality: '' }
            : { city: '', region: regionKey, county: countyKey, municipality: muniKey, municipalities: [muniKey] }
          );
        }
        return;
      }
      if (event.data?.type === 'company-map-select-region') {
        const r = event.data.region || '';
        const ctrl = !!event.data.ctrlKey;
        const rNorm = norm(r);
        if (ctrl) {
          const current = getList(selection.region);
          const next = toggleItem(current, rNorm);
          onChange({
            city: '',
            region: next.join(','),
            county: selection.county,
            municipality: selection.municipality,
            regions: next,
          });
        } else {
          const isCurrent = selection.region === rNorm;
          onChange(isCurrent
            ? { city: '', region: '', county: '', municipality: '' }
            : { city: '', region: rNorm, county: '', municipality: '', regions: [rNorm] }
          );
        }
        return;
      }
      if (event.data?.type === 'company-map-select-city') {
        const { city, region, ctrlKey } = event.data;
        if (!city) return;
        if (ctrlKey) {
          const current = getList(selection.city);
          const next = toggleItem(current, city);
          onChange({
            city: next.join(','),
            region: selection.region,
            county: selection.county,
            municipality: selection.municipality,
            cities: next,
          });
        } else {
          const isCurrent = selection.city === city && selection.region === region;
          onChange(isCurrent
            ? { city: '', region: '', county: '', municipality: '' }
            : { city, region: region || selection.region, county: selection.county, municipality: '', cities: [city] }
          );
        }
        return;
      }
      if (event.data?.type === 'company-map-set-mode') {
        const nextMode = event.data.mode;
        if (nextMode) {
          setMode(nextMode);
          if (nextMode === 'powiaty' || nextMode === 'gminy' || nextMode === 'cities') {
            setListTab(nextMode);
          }
        }
        return;
      }
      if (event.data?.type !== 'company-map-select' || !data) return;
      const { city, region, county, municipality } = event.data;
      if (typeof city !== 'string' || typeof region !== 'string') return;
      if (city && !data.items.some(p => p.city_key === city && p.region_key === region)) return;
      if (!city && region && !data.items.some(p => p.region_key === region)) return;
      onChange({ city, region, county: county ? norm(county) : '', municipality: municipality ? norm(municipality) : '' });
    }
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [data, onChange, selection]);

  useEffect(() => {
    if (ready) frame.current?.contentWindow?.postMessage({
      type: 'company-map-data',
      items: data?.items ?? [],
      powiaty: data?.powiaty ?? [],
      gminy: data?.gminy ?? [],
      selection,
      mode
    }, window.location.origin);
  }, [ready, data, selection, mode]);

  useEffect(() => {
    const onPointerUp = () => {
      frame.current?.contentWindow?.postMessage({ type: 'company-map-pointerup' }, window.location.origin);
    };
    window.addEventListener('pointerup', onPointerUp);
    return () => window.removeEventListener('pointerup', onPointerUp);
  }, []);

  useEffect(() => { setListLimit(30); }, [search, selection.region, listTab]);
  useEffect(() => { if (selection.city) setMode('cities'); }, [selection.city]);

  const items = data?.items ?? [];
  const powiaty = (data?.powiaty ?? []).filter(p => (!selection.region || getList(selection.region).includes(p.region_key)) &&
    norm(`${p.county} ${p.region}`).includes(norm(search)));
  const gminy = (data?.gminy ?? []).filter(g => (!selection.region || getList(selection.region).includes(g.region_key)) &&
    (!selection.county || getList(selection.county).some(c => norm(g.county).includes(norm(c)) || norm(c).includes(norm(g.county)))) &&
    norm(`${g.municipality} ${g.county} ${g.region}`).includes(norm(search)));
  const cities = items.filter(p => (!selection.region || getList(selection.region).includes(p.region_key)) &&
    (!selection.county || getList(selection.county).some(c => norm(p.county || '').includes(norm(c)))) &&
    norm(`${p.city ?? ''} ${p.region ?? ''}`).includes(norm(search)));

  const chosen = items.find(p => p.city_key === norm(selection.city) && p.region_key === norm(selection.region));
  const regionLabel = items.find(p => p.region_key === norm(selection.region))?.region ?? selection.region;
  const active = !!(selection.city || selection.region || selection.county || selection.municipality);

  function chooseCity(p: Place, ctrl?: boolean) {
    const city = p.city_key || '__missing__';
    if (ctrl) {
      const current = getList(selection.city);
      const next = toggleItem(current, city);
      onChange({ city: next.join(','), region: selection.region, county: selection.county, municipality: selection.municipality, cities: next });
    } else {
      onChange(selection.city === city && selection.region === p.region_key ? { city: '', region: '', county: '', municipality: '' } : { city, region: p.region_key, county: p.county ? norm(p.county) : '', municipality: '', cities: [city] });
    }
  }

  function chooseCounty(p: CountyItem, ctrl?: boolean) {
    if (ctrl) {
      const current = getList(selection.county);
      const next = toggleItem(current, p.county_key);
      onChange({ city: '', region: selection.region, county: next.join(','), municipality: selection.municipality, counties: next });
    } else {
      onChange(selection.county === p.county_key ? { city: '', region: selection.region, county: '', municipality: '' } : { city: '', region: p.region_key, county: p.county_key, municipality: '', counties: [p.county_key] });
    }
  }

  function chooseGmina(g: MunicipalityItem, ctrl?: boolean) {
    if (ctrl) {
      const current = getList(selection.municipality);
      const next = toggleItem(current, g.muni_key);
      onChange({ city: '', region: selection.region, county: selection.county, municipality: next.join(','), municipalities: next });
    } else {
      onChange(selection.municipality === g.muni_key ? { city: '', region: selection.region, county: selection.county, municipality: '' } : { city: '', region: g.region_key, county: g.county_key, municipality: g.muni_key, municipalities: [g.muni_key] });
    }
  }

  const selCounties = getList(selection.county);
  const selGminy = getList(selection.municipality);
  const selRegions = getList(selection.region);
  const selCities = getList(selection.city);

  let areaTitle = 'Cała Polska';
  if (selGminy.length > 1) {
    areaTitle = `Wybrane gminy (${selGminy.length}): ${selGminy.map(k => data?.gminy?.find(g => norm(g.muni_key) === norm(k) || norm(g.municipality) === norm(k))?.municipality || k).join(', ')}`;
  } else if (selGminy.length === 1) {
    const gObj = data?.gminy?.find(g => norm(g.muni_key) === norm(selGminy[0]) || norm(g.municipality) === norm(selGminy[0]));
    areaTitle = `Gmina ${gObj?.municipality || selGminy[0]}${gObj?.county ? `, pow. ${gObj.county}` : ''} · ${regionLabel || ''}`.trim();
  } else if (selCounties.length > 1) {
    areaTitle = `Wybrane powiaty (${selCounties.length}): ${selCounties.map(k => data?.powiaty?.find(p => norm(p.county_key) === norm(k) || norm(p.county) === norm(k))?.county || k).join(', ')}`;
  } else if (selCounties.length === 1) {
    const cObj = data?.powiaty?.find(p => norm(p.county_key) === norm(selCounties[0]) || norm(p.county) === norm(selCounties[0]));
    areaTitle = `Powiat ${cObj?.county || selCounties[0]} · ${regionLabel || ''}`.trim();
  } else if (selCities.length > 1) {
    areaTitle = `Wybrane miejscowości (${selCities.length}): ${selCities.join(', ')}`;
  } else if (selection.city === '__missing__') {
    areaTitle = 'Brak pełnej lokalizacji';
  } else if (selection.city) {
    areaTitle = `${chosen?.city ?? selection.city} · ${regionLabel}`;
  } else if (selRegions.length > 1) {
    areaTitle = `Wybrane województwa (${selRegions.length}): ${selRegions.join(', ')}`;
  } else if (selection.region) {
    areaTitle = `Woj. ${regionLabel}`;
  }

  return (
    <section className="location-card" aria-label="Filtr lokalizacji firm">
      <div className="location-heading">
        <div>
          <h2>Wybierz miejsce. Poznaj firmy.</h2>
          <p>Kliknij miasto, powiat lub gminę na mapie lub wybierz z listy, aby zawęzić katalog poniżej.</p>
        </div>
        <button disabled={!active} onClick={() => onChange({ city: '', region: '', county: '', municipality: '' })}>
          Wyczyść lokalizację
        </button>
      </div>
      <div className="location-layout">
        <div className="location-map-area">
          <div className="location-map-controls">
            <div className="map-tabs" role="group" aria-label="Warstwa mapy">
              <button aria-pressed={mode === 'cities'} onClick={() => { setMode('cities'); setListTab('cities'); }}>Miejscowości</button>
              <button aria-pressed={mode === 'regions'} onClick={() => setMode('regions')}>Województwa</button>
              <button aria-pressed={mode === 'powiaty'} onClick={() => { setMode('powiaty'); setListTab('powiaty'); }}>Powiaty</button>
              <button aria-pressed={mode === 'gminy'} onClick={() => { setMode('gminy'); setListTab('gminy'); }}>Gminy</button>
            </div>
            <span className="map-legend">
              <i /> Wybrane <i className="muted-dot" /> Pozostałe
            </span>
          </div>
          <iframe
            ref={frame}
            src="/maps/poland.html?v=20260921-9"
            title="Interaktywna mapa Polski — wybierz lokalizację firm"
            onLoad={() => {
              frame.current?.contentWindow?.postMessage({ type: 'company-map-hello' }, window.location.origin);
            }}
          />
          {state.loading && <div className="map-state" role="status">Wczytywanie lokalizacji…</div>}
          {state.error && <div className="map-state" role="alert">Nie udało się wczytać lokalizacji: {state.error}</div>}
          {mapError && <div className="map-state" role="alert">Nie udało się wczytać granic. Wybierz miejscowość z listy obok.</div>}
          <div className="map-selection" aria-live="polite">
            <span>WYBRANY OBSZAR</span>
            <strong>{areaTitle}</strong>
          </div>
        </div>

        <aside className="location-list">
          <div className="location-type-tabs" role="tablist" aria-label="Typ obszaru">
            <button
              type="button"
              role="tab"
              aria-selected={listTab === 'cities'}
              className={listTab === 'cities' ? 'active' : ''}
              onClick={() => { setListTab('cities'); setSearch(''); if (mode !== 'regions') setMode('cities'); }}
            >
              Miejscowości
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={listTab === 'powiaty'}
              className={listTab === 'powiaty' ? 'active' : ''}
              onClick={() => { setListTab('powiaty'); setSearch(''); setMode('powiaty'); }}
            >
              Powiaty
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={listTab === 'gminy'}
              className={listTab === 'gminy' ? 'active' : ''}
              onClick={() => { setListTab('gminy'); setSearch(''); setMode('gminy'); }}
            >
              Gminy
            </button>
          </div>

          <label htmlFor="city-search">
            {listTab === 'cities' ? 'Znajdź miejscowość' : listTab === 'powiaty' ? 'Znajdź powiat' : 'Znajdź gminę'}
          </label>
          <input
            id="city-search"
            type="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={listTab === 'cities' ? 'np. Warszawa, Poznań…' : listTab === 'powiaty' ? 'np. poznański, wołomiński…' : 'np. Tarnowo Podgórne, Piaseczno…'}
          />

          <p className="location-list-caption">
            {selection.region ? `Woj. ${regionLabel}` : 'Wszystkie województwa'} · {fmt(listTab === 'cities' ? cities.length : listTab === 'powiaty' ? powiaty.length : gminy.length)} {listTab === 'cities' ? 'lokalizacji' : listTab === 'powiaty' ? 'powiatów' : 'gmin'}
          </p>

          {(selection.region || selection.county || selection.municipality) && (
            <button className="text-button" onClick={() => onChange({ city: '', region: '', county: '', municipality: '' })}>
              ← Wszystkie obszary (Polska)
            </button>
          )}

          <div className="city-options" aria-label="Opcje obszaru">
            {listTab === 'cities' && cities.slice(0, listLimit).map(p => {
              const isSelected = getList(selection.city).some(c => norm(c) === norm(p.city_key)) && (!selection.region || getList(selection.region).includes(p.region_key));
              return (
                <button
                  key={`${p.city_key}|${p.region_key}`}
                  className={isSelected ? 'selected' : ''}
                  aria-pressed={isSelected}
                  title="Kliknij, aby wybrać (Ctrl+klik: zaznacz kilka)"
                  onClick={(e) => chooseCity(p, e.ctrlKey || e.metaKey)}
                >
                  <span>
                    <strong>{p.city || 'Brak miejscowości'}</strong>
                    <small>{p.region || 'Brak województwa'}{p.status !== 'matched' ? ' · bez pewnego punktu' : ''}</small>
                  </span>
                  <b>{fmt(p.count)}</b>
                </button>
              );
            })}

            {listTab === 'powiaty' && powiaty.slice(0, listLimit).map(p => {
              const isSelected = getList(selection.county).some(c => norm(c) === norm(p.county_key) || norm(c) === norm(p.county));
              return (
                <button
                  key={`${p.county_key}|${p.region_key}`}
                  className={isSelected ? 'selected' : ''}
                  aria-pressed={isSelected}
                  title="Kliknij, aby wybrać (Ctrl+klik: zaznacz kilka)"
                  onClick={(e) => chooseCounty(p, e.ctrlKey || e.metaKey)}
                >
                  <span>
                    <strong>Powiat {p.county}</strong>
                    <small>woj. {p.region}</small>
                  </span>
                  <b>{fmt(p.count)}</b>
                </button>
              );
            })}

            {listTab === 'gminy' && gminy.slice(0, listLimit).map(g => {
              const isSelected = getList(selection.municipality).some(m => norm(m) === norm(g.muni_key) || norm(m) === norm(g.municipality));
              return (
                <button
                  key={`${g.muni_key}|${g.county_key}`}
                  className={isSelected ? 'selected' : ''}
                  aria-pressed={isSelected}
                  title="Kliknij, aby wybrać (Ctrl+klik: zaznacz kilka)"
                  onClick={(e) => chooseGmina(g, e.ctrlKey || e.metaKey)}
                >
                  <span>
                    <strong>Gmina {g.municipality}</strong>
                    <small>pow. {g.county}, woj. {g.region}</small>
                  </span>
                  <b>{fmt(g.count)}</b>
                </button>
              );
            })}

            {!state.loading && listTab === 'cities' && !cities.length && <p>Brak miejscowości pasujących do wyszukiwania.</p>}
            {!state.loading && listTab === 'powiaty' && !powiaty.length && <p>Brak powiatów pasujących do wyszukiwania.</p>}
            {!state.loading && listTab === 'gminy' && !gminy.length && <p>Brak gmin pasujących do wyszukiwania.</p>}

            {((listTab === 'cities' && cities.length > listLimit) ||
              (listTab === 'powiaty' && powiaty.length > listLimit) ||
              (listTab === 'gminy' && gminy.length > listLimit)) && (
              <button onClick={() => setListLimit(n => n + 50)}>Pokaż kolejne</button>
            )}
          </div>
        </aside>
      </div>
      <div className="location-footer">
        <p>
          {data ? (
            <>
              <strong>{fmt(data.mapped)}</strong> z {fmt(data.total)} firm z bieżących filtrów ma punkt na mapie. {fmt(data.total - data.mapped)} bez jednoznacznego punktu pozostaje dostępnych na liście.
            </>
          ) : (
            'Liczby uwzględniają wyszukiwanie i filtry działalności.'
          )}
        </p>
        <small>
          Mapa przedstawia miejscowości siedzib, nie adresy inwestycji. Punkty są przybliżone. <a href="https://www.geonames.org/" target="_blank" rel="noreferrer">GeoNames (CC BY 4.0)</a> · <a href="https://gisco-services.ec.europa.eu/distribution/v2/nuts/" target="_blank" rel="noreferrer">Eurostat / GISCO, granice 2024</a>.
        </small>
      </div>
    </section>
  );
}
