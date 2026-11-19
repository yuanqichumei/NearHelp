import { useEffect, useState } from 'react';
import { ApiError, post } from './api';

const consentKey = 'neartalk.nearby';

export async function visitorSession() {
  const open = () => post<void>('/api/visitor/session', {});
  if (navigator.locks) await navigator.locks.request('neartalk-visitor', open);
  else await open();
}

let pendingPosition: Promise<GeolocationPosition> | undefined;

export function readPosition(): Promise<GeolocationPosition> {
  pendingPosition ??= new Promise<GeolocationPosition>((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('当前浏览器无法定位。'));
    // The browser's own timeout may start only after the permission prompt closes.
    const timer = window.setTimeout(() => reject(new Error('定位等待超时。')), 12000);
    navigator.geolocation.getCurrentPosition(
      (position) => { window.clearTimeout(timer); resolve(position); },
      (error) => { window.clearTimeout(timer); reject(error); },
      { timeout: 10000, maximumAge: 15000, enableHighAccuracy: true },
    );
  }).finally(() => { pendingPosition = undefined; });
  return pendingPosition;
}

function storedConsent() {
  try { return localStorage.getItem(consentKey) === 'on'; }
  catch { return false; }
}

export function useNearby() {
  const [enabled, setEnabled] = useState(storedConsent);
  const [position, setPosition] = useState<GeolocationPosition>();
  const [error, setError] = useState('');

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === consentKey) setEnabled(storedConsent());
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let pending = false;
    async function update() {
      if (pending || stopped || document.hidden) return;
      pending = true;
      try {
        const current = await readPosition();
        if (stopped || document.hidden) return;
        setPosition(current);
        if (current.coords.accuracy > 500) {
          setError('当前位置精度不足，请到信号较好的地方再试。');
          return;
        }
        await post('/api/location/heartbeat', {
          lat: Number(current.coords.latitude.toFixed(3)),
          lon: Number(current.coords.longitude.toFixed(3)),
        });
        if (stopped || document.hidden) return;
        setError('');
      } catch (cause) {
        if (stopped) return;
        setError(cause instanceof ApiError && [401, 403].includes(cause.status)
          ? '访客会话已失效，请重新开启统计。'
          : '暂时无法更新附近人数，请检查定位权限或网络。');
      } finally {
        pending = false;
      }
    }
    void update();
    const timer = window.setInterval(update, 60000);
    document.addEventListener('visibilitychange', update);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', update);
    };
  }, [enabled]);

  async function change(next: boolean) {
    if (!next) {
      setEnabled(false);
      try { localStorage.removeItem(consentKey); } catch { /* Browser storage can be blocked. */ }
    }
    setError('');
    try {
      let current: GeolocationPosition | undefined;
      if (next) {
        current = await readPosition();
        setPosition(current);
        await visitorSession();
      }
      await post<void>('/api/location/consent', { enabled: next });
      if (next) {
        try { localStorage.setItem(consentKey, 'on'); } catch { /* Consent remains in this tab. */ }
        setEnabled(true);
      }
      return current;
    } catch {
      setError(next ? '无法开启统计，请检查定位权限或网络。' : '已停止上报，已有记录会自动过期。');
    }
  }

  return { enabled, position, error, change };
}

export type NearbyState = ReturnType<typeof useNearby>;
