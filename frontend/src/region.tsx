import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { readPosition, visitorSession } from './location';

export type Coordinates = [number, number];
type Scope = '1' | '5' | '10' | 'city';
type Area = { name: string; point: Coordinates; followsLocation?: boolean };
const areas: Area[] = [
  { name: '香港九龙塘', point: [22.34, 114.17] },
  { name: '深圳福田', point: [22.545, 114.06] },
  { name: '广州天河', point: [23.13, 113.325] },
];
const scopes: Scope[] = ['1', '5', '10', 'city'];
const storageKey = 'neartalk.region';
const manualKey = 'neartalk.region-manual';

function initialRegion(): { area: Area; scope: Scope } {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
    if (saved && scopes.includes(saved.scope) && typeof saved.area?.name === 'string' &&
      Array.isArray(saved.area.point) && saved.area.point.length === 2 &&
      saved.area.point.every(Number.isFinite) && Math.abs(saved.area.point[0]) <= 90 &&
      Math.abs(saved.area.point[1]) <= 180) return saved;
  } catch { /* The default area is still available. */ }
  return { area: areas[0], scope: '5' };
}

export function useRegion(position: GeolocationPosition | undefined, showStats: boolean) {
  const [selection, setSelection] = useState(initialRegion);
  const { area, scope } = selection;
  const [lat, lon] = area.point;
  const query = `lat=${lat}&lon=${lon}&scope=${scope}`;
  const [result, setResult] = useState<{ query: string; city: string | null; band: string | null }>();
  const [failedQuery, setFailedQuery] = useState('');
  const [devicePosition, setDevicePosition] = useState<GeolocationPosition>();
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState('');
  const [locationRevision, setLocationRevision] = useState(0);
  const locationAttempt = useRef(0);

  function select(point: Coordinates, name: string, followsLocation = false) {
    if (!followsLocation) {
      locationAttempt.current += 1;
      setLocating(false);
      setLocationError('');
      try { sessionStorage.setItem(manualKey, 'yes'); } catch { /* Manual selection still works. */ }
    }
    const coarse = point.map((value) => Number((Math.round(value * 200) / 200).toFixed(3))) as Coordinates;
    setSelection((previous) => {
      if (previous.area.name === name && previous.area.point[0] === coarse[0] &&
          previous.area.point[1] === coarse[1] && !!previous.area.followsLocation === followsLocation) return previous;
      return { area: { point: coarse, name, followsLocation }, scope: previous.scope };
    });
  }

  function usePosition(current: GeolocationPosition) {
    try { sessionStorage.removeItem(manualKey); } catch { /* The new region still works. */ }
    setDevicePosition(current);
    select([current.coords.latitude, current.coords.longitude], '当前位置', true);
  }

  async function locate() {
    const attempt = ++locationAttempt.current;
    setLocating(true);
    setLocationError('');
    try {
      const current = await readPosition();
      if (attempt !== locationAttempt.current) return;
      if (current.coords.accuracy > 1000) {
        setLocationError('定位精度不足，可以手动选择地区。');
        return;
      }
      usePosition(current);
      setLocationRevision((revision) => revision + 1);
    } catch {
      if (attempt === locationAttempt.current) setLocationError('暂时无法定位，可以手动选择地区。');
    } finally {
      if (attempt === locationAttempt.current) setLocating(false);
    }
  }

  useEffect(() => {
    if (!showStats) return;
    try {
      if (sessionStorage.getItem(manualKey)) return;
    } catch { /* Browser location permission still applies. */ }
    void locate();
    return () => { locationAttempt.current += 1; };
  }, [showStats]);

  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(selection)); } catch { /* This tab can still browse. */ }
  }, [selection]);
  useEffect(() => {
    function sync(event: StorageEvent) {
      if (event.key === storageKey) setSelection(initialRegion());
    }
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  useEffect(() => {
    if (position && area.followsLocation && position.coords.accuracy <= 1000) {
      usePosition(position);
    }
  }, [position, area.followsLocation]);

  useEffect(() => {
    if (!showStats) return;
    const controller = new AbortController();
    let pending = false;
    async function load() {
      if (pending || document.hidden) return;
      pending = true;
      try {
        await visitorSession();
        if (controller.signal.aborted || document.hidden) return;
        const stats = await api<{ city: string | null; band: string | null }>(
          '/api/regions/stats?' + query, { signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          setResult({ query, ...stats });
          setFailedQuery('');
        }
      } catch {
        if (!controller.signal.aborted) setFailedQuery(query);
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = window.setInterval(load, 60000);
    document.addEventListener('visibilitychange', load);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', load);
    };
  }, [query, showStats]);

  return {
    area, scope, query, select, usePosition, locate, locating, locationError, devicePosition, locationRevision,
    setScope: (next: Scope) => setSelection((previous) => ({ ...previous, scope: next })),
    stats: result?.query === query ? result : undefined,
    failed: failedQuery === query,
  };
}

export type RegionState = ReturnType<typeof useRegion>;

export function RegionControls({ region }: { region: RegionState }) {
  const { area, scope, stats, failed } = region;
  const range = scope === 'city' ? (stats?.city ? stats.city + '同城' : '同城') : '附近 ' + scope + ' 公里';
  const label = failed ? '暂时无法更新活跃人数。' : !stats ? '正在获取活跃人数…'
    : stats.band === null ? '该地区暂不支持同城范围，请选择公里数。'
    : range + ' · ' + stats.band + ' 人最近活跃';
  return <>
    <div className="map-controls">
      <label>浏览地区 <select value={area.name} onChange={(event) => {
        const next = areas.find((entry) => entry.name === event.target.value);
        if (next) region.select(next.point, next.name);
      }}>
        {!areas.some((entry) => entry.name === area.name) && <option disabled>{area.name}</option>}
        {areas.map((entry) => <option key={entry.name}>{entry.name}</option>)}
      </select></label>
      <label>浏览范围 <select value={scope} onChange={(event) => region.setScope(event.target.value as Scope)}>
        <option value="1">1 公里</option>
        <option value="5">5 公里</option>
        <option value="10">10 公里</option>
        <option value="city">同城{stats?.city ? ' · ' + stats.city : ''}</option>
      </select></label>
      <button className="guest-button" onClick={() => void region.locate()} disabled={region.locating}>
        {region.locating ? '正在定位…' : '定位到我'}
      </button>
    </div>
    {region.locationError && <p className="quiet" role="status">{region.locationError}</p>}
    <p role="status" className="nearby-home">{label}</p>
  </>;
}
