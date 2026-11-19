import type { Guest } from './api';

const key = 'neartalk.guest';
export const nicknameLimit = 24;

export function loadGuest(): Guest {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? 'null') as Guest | null;
    if (typeof saved?.nickname === 'string' && saved.nickname.trim() &&
        typeof saved.guest_id === 'string' &&
        /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(saved.guest_id)) {
      return saved;
    }
  } catch {
    // A blocked storage area or an invalid saved value can be replaced.
  }
  // getRandomValues also works when testing on a phone over local-network HTTP.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  const guest = {
    guest_id: [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-'),
    nickname: '访客 ' + hex.slice(0, 4).toUpperCase(),
  };
  saveGuest(guest);
  return guest;
}

export function saveGuest(guest: Guest) {
  try {
    localStorage.setItem(key, JSON.stringify(guest));
  } catch {
    // Keep the guest usable for this page when browser storage is unavailable.
  }
}
