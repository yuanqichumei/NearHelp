import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AreaControls, AreaSummary } from './HelpFeed';
import type { Discovery, HelpArea } from './helpApi';
import { Link } from './navigation';

const key = import.meta.env.VITE_GEOAPIFY_MAP_KEY;
const osmTiles = import.meta.env.DEV || import.meta.env.VITE_ALLOW_OSM_TILES === 'true';
const osmCredit = '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>';

export default function HelpMap({ region, data }: { region: HelpArea; data?: Discovery }) {
  const element = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map>(undefined);
  const self = useRef<L.CircleMarker>(undefined);
  const circle = useRef<L.Circle>(undefined);
  const [tilesUnavailable, setTilesUnavailable] = useState(false);
  const [initialCenter] = useState(region.area.point);
  useEffect(() => {
    if (!element.current) return;
    const instance = L.map(element.current, { maxZoom: 19, minZoom: 2 }).setView(initialCenter, 16);
    map.current = instance;
    circle.current = L.circle(initialCenter, { radius: 500, color: '#197458', fillOpacity: .08 }).addTo(instance);
    const url = key ? 'https://maps.geoapify.com/v1/tile/osm-bright/{z}/{x}/{y}.png?apiKey=' + encodeURIComponent(key)
      : osmTiles ? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png' : undefined;
    if (url) {
      const attribution = key ? osmCredit + ' · <a href="https://www.geoapify.com/">© Geoapify</a>' : osmCredit;
      L.tileLayer(url, { attribution, detectRetina: true, maxNativeZoom: 19 })
        .on('tileerror', () => setTilesUnavailable(true)).on('tileload', () => setTilesUnavailable(false))
        .addTo(instance);
    } else setTilesUnavailable(true);
    return () => { instance.remove(); map.current = undefined; };
  }, [initialCenter]);
  const [lat, lon] = region.area.point;
  useEffect(() => {
    map.current?.setView([lat, lon], region.radius === 500 ? 16 : region.radius === 1000 ? 15 : 14);
    circle.current?.setLatLng([lat, lon]).setRadius(region.radius);
  }, [lat, lon, region.radius]);
  useEffect(() => {
    if (!region.position || !map.current) return;
    const { latitude, longitude } = region.position.coords;
    self.current ??= L.circleMarker([latitude, longitude], {
      radius: 7, color: '#fff', fillColor: '#17614b', fillOpacity: 1,
    }).bindTooltip('你的位置').addTo(map.current);
    self.current.setLatLng([latitude, longitude]);
  }, [region.position]);
  return <>
    <Link className="back" href="/">返回附近需求</Link>
    <section className="card map-card">
      <h1>附近地图</h1>
      <AreaControls region={region} />
      <AreaSummary region={region} data={data} />
      <div className="map-canvas" ref={element} role="region" aria-label="附近地图" />
      {tilesUnavailable && <p className="quiet" role="status">底图暂不可用，仍可浏览区域需求。</p>}
      <div className="help-controls">
        <button className="guest-button" onClick={() => {
          const center = map.current?.getCenter().wrap();
          if (center) region.choose([center.lat, center.lng], '地图所选区域');
        }}>浏览地图当前区域</button>
        {data && <Link className="back" href="/">查看 {data.requests.length} 条附近待解决需求</Link>}
      </div>
    </section>
  </>;
}
