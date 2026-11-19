import { post } from './api';

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
