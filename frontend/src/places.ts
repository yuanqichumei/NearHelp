import { useEffect, useState } from 'react';
import { api, ApiError, post } from './api';
import { visitorSession } from './location';

export interface Place {
  slug: string;
  source: string;
  name: string;
  category: string;
  latitude: number;
  longitude: number;
}

export interface PlaceSearch {
  places: Place[];
  status: 'catalog' | 'ready' | 'unavailable';
}

interface Visits {
  recent_visitors: number;
  today_visitors: number;
  active_topics: number;
  timezone: string;
}

export function usePlaceVisit(slug?: string) {
  const [place, setPlace] = useState<Place>();
  const [visits, setVisits] = useState<Visits>();
  const [error, setError] = useState('');

  useEffect(() => {
    if (!slug) return;
    const path = '/api/communities/' + slug;
    let stopped = false;
    let pending = false;
    let missing = false;

    api<Place>(path).then((result) => {
      if (!stopped) setPlace(result);
    }).catch((reason) => {
      if (stopped) return;
      missing = reason instanceof ApiError && reason.status === 404;
      setError(reason instanceof Error ? reason.message : '无法读取地点信息。');
    });

    async function visit() {
      if (stopped || pending || missing || document.hidden) return;
      pending = true;
      try {
        await visitorSession();
        if (stopped || document.hidden) return;
        const counts = await post<Visits>(path + '/visit', {});
        if (stopped) return;
        setVisits(counts);
        setError('');
      } catch (reason) {
        if (stopped) return;
        missing = reason instanceof ApiError && reason.status === 404;
        setError(reason instanceof Error ? reason.message : '无法更新社区访问。');
      } finally {
        pending = false;
      }
    }
    void visit();
    const interval = window.setInterval(visit, 60000);
    document.addEventListener('visibilitychange', visit);
    return () => {
      stopped = true;
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', visit);
    };
  }, [slug]);

  return { place, visits, error };
}
