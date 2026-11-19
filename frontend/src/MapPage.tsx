import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { api } from './api';
import type { NearbyState } from './location';
import type { PlaceSearch } from './places';
import { RegionControls } from './region';
import type { Coordinates, RegionState } from './region';
const tileKey = import.meta.env.VITE_GEOAPIFY_MAP_KEY;
const osmTiles = import.meta.env.DEV || import.meta.env.VITE_ALLOW_OSM_TILES === 'true';
const osmCredit = '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>';

export function MapPage({ nearby, region }: { nearby: NearbyState; region: RegionState }) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map>(undefined);
  const marker = useRef<L.CircleMarker>(undefined);
  const placeMarkers = useRef<L.LayerGroup>(undefined);
  const [tilesUnavailable, setTilesUnavailable] = useState(false);
  const [changing, setChanging] = useState(false);
  const [startingCenter] = useState(region.area.point);
  const [searchCenter, setSearchCenter] = useState<Coordinates>(startingCenter);
  const [search, setSearch] = useState<PlaceSearch>();
  const [searchError, setSearchError] = useState('');

  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, { maxZoom: 19, minZoom: 2 }).setView(startingCenter, 15);
    map.current = instance;
    placeMarkers.current = L.layerGroup().addTo(instance);
    const url = tileKey
      ? 'https://maps.geoapify.com/v1/tile/osm-bright/{z}/{x}/{y}.png?apiKey=' + encodeURIComponent(tileKey)
      : osmTiles ? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png' : undefined;
    if (url) {
      const attribution = tileKey ? osmCredit + ' · <a href="https://www.geoapify.com/">© Geoapify</a>' : osmCredit;
      L.tileLayer(url, { attribution, detectRetina: true, maxNativeZoom: 19 }).on('tileerror', () => setTilesUnavailable(true))
        .on('tileload', () => setTilesUnavailable(false)).addTo(instance);
    } else {
      setTilesUnavailable(true);
    }
    return () => {
      instance.remove();
      map.current = undefined;
      marker.current = undefined;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setSearch(undefined);
    setSearchError('');
    const [lat, lon] = searchCenter.map((coordinate) => coordinate.toFixed(2));
    api<PlaceSearch>(`/api/places/nearby?lat=${lat}&lon=${lon}`, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setSearch(result);
      }).catch((error) => {
        if (!controller.signal.aborted) setSearchError(error instanceof Error ? error.message : '地点暂不可用。');
      });
    return () => controller.abort();
  }, [searchCenter]);

  useEffect(() => {
    const layer = placeMarkers.current;
    if (!layer) return;
    layer.clearLayers();
    for (const place of search?.places ?? []) {
      const link = document.createElement('a');
      link.textContent = place.name + ' · 进入社区';
      link.href = '/places/' + place.slug;
      L.circleMarker([place.latitude, place.longitude], {
        radius: 7, color: '#12604a', fillColor: '#cef1dc', weight: 2, fillOpacity: 1,
      }).bindPopup(link).addTo(layer);
    }
  }, [search]);

  useEffect(() => {
    const position = region.devicePosition ?? nearby.position;
    if (!position || !map.current) return;
    const { latitude, longitude } = position.coords;
    const point: Coordinates = [latitude, longitude];
    marker.current ??= L.circleMarker(point, { radius: 8, color: '#fff', fillColor: '#17614b', fillOpacity: 1 })
      .bindTooltip('你的位置').addTo(map.current);
    marker.current.setLatLng(point);
  }, [region.devicePosition, nearby.position]);

  const [areaLat, areaLon] = region.area.point;
  const followsLocation = region.area.followsLocation;
  const latestPosition = useRef<GeolocationPosition>(undefined);
  latestPosition.current = region.devicePosition;
  useEffect(() => {
    const center: Coordinates = [areaLat, areaLon];
    const coords = followsLocation ? latestPosition.current?.coords : undefined;
    const viewCenter: Coordinates = coords ? [coords.latitude, coords.longitude] : center;
    map.current?.setView(viewCenter, followsLocation ? 16 : 15);
    setSearchCenter((previous) => previous[0] === areaLat && previous[1] === areaLon ? previous : center);
  }, [areaLat, areaLon, followsLocation, region.locationRevision]);

  return <>
    <a className="back" href="/">返回首页</a>
    <section className="card map-card" aria-labelledby="map-title">
      <h1 id="map-title">探索附近</h1>
      <RegionControls region={region} />
      <div className="nearby-summary">
        <p role="status">{nearby.error || (nearby.enabled ? '正在参与活跃统计。' : '你尚未参与活跃统计。')}</p>
        <button className="guest-button" disabled={changing} onClick={async () => {
          setChanging(true);
          try {
            const current = await nearby.change(!nearby.enabled);
            if (current && current.coords.accuracy <= 1000) region.usePosition(current);
          }
          finally { setChanging(false); }
        }}>{nearby.enabled ? '关闭统计' : '开启统计'}</button>
      </div>
      <p className="quiet">开启后，前台页面约每分钟上报约百米精度的位置，位置约 5 分钟后过期。人数区间包含自己，位置来自浏览器定位。地点搜索使用约公里精度的地图中心。</p>
      <div className="map-controls">
        <button className="guest-button" onClick={() => {
          const center = map.current?.getCenter().wrap();
          if (center) {
            const point: Coordinates = [center.lat, center.lng];
            region.select(point, '地图所选地区');
          }
        }}>使用地图此区域</button>
      </div>
      <div className="map-canvas" ref={element} role="region" aria-label="附近地图" />
      {tilesUnavailable && <p className="quiet" role="status">底图暂不可用。</p>}
      <div className="place-list">
        <h2>附近地点</h2>
        <p className="quiet" role="status">{searchError || (!search ? '正在查询地点…'
          : search.status === 'unavailable' ? '地点服务暂不可用，显示已收录的校园地点。'
          : search.places.length === 0 ? '当前区域暂无已收录地点。' : '')}</p>
        {search?.places.length ? <ul className="hot-list">
          {search.places.map((place) => <li key={place.slug}>
            <a className="hot-link" href={'/places/' + place.slug}>{place.name}</a>
            <span className="hot-meta">{place.category}</span>
          </li>)}
        </ul> : null}
        {search?.places.some((place) => place.source === 'cityuhk') &&
          <a className="hot-meta" href="https://www.cityu.edu.hk/visit/way-finding-system-on-campus">香港城市大学校园目录</a>}
        {search?.places.some((place) => place.source === 'geoapify') &&
          <p className="hot-meta"><a href="https://www.geoapify.com/">Geoapify</a> · <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a></p>}
      </div>
    </section>
  </>;
}
