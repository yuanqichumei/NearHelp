import { post } from './api';

export async function visitorSession() {
  const open = () => post<void>('/api/visitor/session', {});
  if (navigator.locks) await navigator.locks.request('neartalk-visitor', open);
  else await open();
}

let pendingPosition: Promise<GeolocationPosition> | undefined;

export function recentPositionTime(position?: GeolocationPosition): number | undefined {
  if (!position || !Number.isFinite(position.timestamp)) return;
  // Some WebKit providers return epoch microseconds. Both units must pass the same freshness check.
  const millis = position.timestamp >= 1e14 ? position.timestamp / 1000 : position.timestamp;
  const age = Date.now() - millis;
  if (age >= -10000 && age <= 300000) return millis;
}

function fix(highAccuracy: boolean): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    // The native timeout starts after permission is decided. Allow time to read the prompt.
    const timer = window.setTimeout(() => reject(new Error('定位等待超时，请回到此页后重新定位。')), 90000);
    const finish = (callback: () => void) => { window.clearTimeout(timer); callback(); };
    try {
      navigator.geolocation.getCurrentPosition(
        (position) => finish(() => resolve(position)),
        (error) => finish(() => reject(error)),
        { timeout: highAccuracy ? 20000 : 12000, maximumAge: 15000, enableHighAccuracy: highAccuracy },
      );
    } catch (error) { finish(() => reject(error)); }
  });
}

async function deviceFix() {
  if (!window.isSecureContext) throw new Error('定位需要 HTTPS。请用手机浏览器打开安全链接。');
  const policy = (document as Document & { featurePolicy?: { allowsFeature: (name: string) => boolean } }).featurePolicy;
  if (policy && !policy.allowsFeature('geolocation')) throw new Error('当前页面禁止定位，请在系统浏览器中直接打开 NearHelp。');
  if (!navigator.geolocation) throw new Error('当前浏览器不支持定位，可用 Safari 或 Chrome 打开。');
  try {
    return await fix(true).catch((error) => {
      if (error?.code === 2 || error?.code === 3) return fix(false);
      throw error;
    });
  } catch (error) {
    const code = (error as GeolocationPositionError | null)?.code;
    if (code === 1) throw new Error('定位权限被拒绝。请在系统定位服务和浏览器网站设置中允许位置，然后重新定位。');
    if (code === 3) throw new Error('定位超时，请到信号较好的位置重新定位。');
    if (code === 2) throw new Error('手机暂时无法获取位置。请检查系统定位服务后重试。');
    throw error instanceof Error ? error : new Error('定位失败，请重新定位或手动选区。');
  }
}

export function readPosition(): Promise<GeolocationPosition> {
  pendingPosition ??= deviceFix().finally(() => { pendingPosition = undefined; });
  return pendingPosition;
}
