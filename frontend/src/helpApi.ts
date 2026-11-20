import { useEffect, useRef, useState } from 'react';
import { api, post } from './api';
import { readPosition, visitorSession } from './location';

export type Point = [number, number];
export type Radius = 500 | 1000 | 3000;
export type Status = 'open' | 'in_progress' | 'resolved' | 'expired' | 'cancelled';
export type Profile = { id: string; nickname: string };
export type Account = Profile & { username: string; is_demo: boolean; is_admin: boolean; share_presence: boolean; discoverable: boolean };

export interface RequestItem {
  id: number;
  author_id: string;
  nickname: string;
  title: string;
  created_at: string;
  expires_at: number;
  status: Status;
  reward_cents: number;
  is_pinned: boolean;
}

export interface RequestPreview extends RequestItem {
  summary: string;
  distance_m: number;
  comment_count: number;
  has_offered: boolean;
}

export interface Discovery {
  requests: RequestPreview[];
  active_band: string;
  users: Profile[];
}

export interface RequestDetail extends RequestItem {
  content: string;
  is_owner: boolean;
  response_count: number;
  chat_id: number | null;
  replies: { id: number; parent_id: number | null; author_id: string; nickname: string; created_at: string; content: string }[];
  offers: { helper_id: string; nickname: string; status: 'pending' | 'accepted' | 'declined' }[];
}

export interface InboxData {
  pending: { request_id: number; title: string; offers: number }[];
  chats: { request_id: number; title: string; nickname: string; unread: number }[];
}

export type Message = { id: number; mine: boolean; content: string; created_at: string };
export type Conversation = { title: string; nickname: string; peer_id: string; messages: Message[]; has_older: boolean };

export const defaultAreas = [
  { name: '香港城市大学', point: [22.338, 114.172] as Point },
  { name: '深圳福田', point: [22.544, 114.058] as Point },
  { name: '广州天河', point: [23.13, 113.324] as Point },
];

export const requestPath = (id: number | string) => '/api/help/requests/' + id;
export const requestLink = (id: number | string) => '/requests/' + id;
export const chatPath = (id: number | string) => '/api/help/chats/' + id;

function coordinates(position: GeolocationPosition) {
  const { latitude, longitude, accuracy } = position.coords;
  if (!Number.isFinite(latitude) || Math.abs(latitude) > 90 || !Number.isFinite(longitude) ||
      Math.abs(longitude) > 180 || !Number.isFinite(accuracy) || accuracy < 0) throw new Error('设备返回的位置无效，请重新定位。');
  return { lat: Number(latitude.toFixed(3)), lon: Number(longitude.toFixed(3)), accuracy };
}

export function locationPayload(position: GeolocationPosition) {
  const point = coordinates(position);
  if (point.accuracy > 500) throw new Error('目前只有大致位置。发布需要 500 米以内的精度，请开启精确位置或到开阔处重试。');
  return point;
}

export function useHelpArea(account: Account | null | undefined) {
  const [area, setArea] = useState(() => {
    try {
      const last = JSON.parse(sessionStorage.getItem('nearhelp-browse') ?? 'null');
      if (last && Date.now() - last.time < 3600000 && Array.isArray(last.point) && last.point.length === 2 &&
          last.point.every(Number.isFinite) && Math.abs(last.point[0]) <= 90 && Math.abs(last.point[1]) <= 180) {
        return { name: '上次浏览区域', point: last.point as Point };
      }
    } catch { /* Private browsing can restrict session storage. */ }
    return defaultAreas[0];
  });
  useEffect(() => {
    try {
      sessionStorage.setItem('nearhelp-browse', JSON.stringify({
        point: area.point.map(value => Number(value.toFixed(3))), time: Date.now(),
      }));
    } catch { /* The area still works for this page. */ }
  }, [area]);
  const [radius, setRadius] = useState<Radius>(500);
  const [position, setPosition] = useState<GeolocationPosition>();
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState('');
  const attempt = useRef(0);
  const followsDevice = useRef(false);

  function choose(point: Point, name: string) {
    attempt.current += 1;
    followsDevice.current = false;
    setPosition(undefined);
    setLocating(false);
    setError('');
    setArea({ point, name });
  }

  function usePosition(current: GeolocationPosition) {
    const coarse = coordinates(current);
    followsDevice.current = true;
    setPosition(current);
    setError('');
    setArea({ name: coarse.accuracy > 500 ? '设备大致位置' : '当前位置附近', point: [coarse.lat, coarse.lon] });
  }

  async function locate() {
    const id = ++attempt.current;
    setLocating(true);
    setError('');
    try {
      const current = await readPosition();
      if (id !== attempt.current) return;
      usePosition(current);
    } catch (reason) {
      if (id === attempt.current) {
        setPosition(undefined);
        if (followsDevice.current) setArea(previous => ({ ...previous, name: '上次浏览区域' }));
        followsDevice.current = false;
        setError(reason instanceof Error ? reason.message : '暂时无法定位。你仍可手动选区浏览。');
      }
    } finally {
      if (id === attempt.current) setLocating(false);
    }
  }

  const [sharingError, setSharingError] = useState('');
  const sharing = account?.share_presence;
  const accountId = account?.id;
  const hasPosition = Boolean(position);
  useEffect(() => {
    setSharingError('');
    if (!accountId || !sharing || !hasPosition) return;
    let stopped = false;
    let pending = false;
    let lastSent = 0;
    async function heartbeat() {
      if (stopped || document.hidden || pending || Date.now() - lastSent < 55000) return;
      pending = true;
      try {
        const current = await readPosition();
        if (stopped || document.hidden) return;
        const body = locationPayload(current);
        setPosition(current);
        if (followsDevice.current) {
          setArea((previous) => previous.point[0] === body.lat && previous.point[1] === body.lon
            ? previous : { name: '当前位置附近', point: [body.lat, body.lon] });
        }
        await post('/api/help/presence', body);
        lastSent = Date.now();
        if (!stopped) setSharingError('');
      } catch {
        if (!stopped) setSharingError('无法更新活跃位置，请重新定位后再试。');
      } finally {
        pending = false;
      }
    }
    void heartbeat();
    const timer = window.setInterval(heartbeat, 60000);
    document.addEventListener('visibilitychange', heartbeat);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', heartbeat);
    };
  }, [accountId, sharing, hasPosition]);

  return { area, radius, setRadius, choose, locate, usePosition, position, locating, error, sharingError };
}

export type HelpArea = ReturnType<typeof useHelpArea>;

export function useDiscovery(region: HelpArea, viewer: string | null | undefined, enabled: boolean) {
  const { radius } = region;
  const [lat, lon] = region.area.point;
  const key = [viewer, lat, lon, radius].join('/');
  const [result, setResult] = useState<{ key: string; data?: Discovery; error?: string }>();
  useEffect(() => {
    if (!enabled || viewer === undefined) return;
    let pending = false;
    let sessionReady = viewer !== null;
    const controller = new AbortController();
    async function load() {
      if (controller.signal.aborted || pending || document.hidden) return;
      pending = true;
      try {
        if (!sessionReady) {
          await visitorSession();
          sessionReady = true;
        }
        if (controller.signal.aborted || document.hidden) return;
        const data = await api<Discovery>('/api/help/nearby', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lat, lon, radius }), signal: controller.signal,
        });
        if (!controller.signal.aborted) setResult({ key, data });
      } catch (reason) {
        if (!controller.signal.aborted) setResult((previous) => ({
          key, data: previous?.key === key ? previous.data : undefined,
          error: reason instanceof Error ? reason.message : '暂时无法读取附近需求。',
        }));
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = window.setInterval(load, 6000);
    document.addEventListener('visibilitychange', load);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', load);
    };
  }, [key, enabled, viewer, lat, lon, radius]);
  return result?.key === key ? result : undefined;
}
