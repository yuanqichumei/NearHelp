import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { ApiError, post, topicsPath, usePolling } from './api';
import type { Guest, HotTopic, Topic, TopicDetail } from './api';
import { loadGuest, nicknameLimit, saveGuest } from './guest';
import { useNearby } from './location';
import { RegionControls, useRegion } from './region';
import type { Coordinates, RegionState } from './region';
import { usePlaceVisit } from './places';
import './style.css';

const characters = (value: string) => Array.from(value).length;
const dateFormat = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' });
const MapPage = lazy(() => import('./MapPage').then(({ MapPage }) => ({ default: MapPage })));
const communityTopics = (slug?: string) => slug ? '/api/communities/' + slug + '/topics' : topicsPath;
const topicLink = (id: number, slug?: string) => (slug ? '/places/' + slug : '') + '/topics/' + id;

function Icon({ name, size = 20 }: { name: 'chat' | 'plus' | 'close' | 'person'; size?: number }) {
  const paths = {
    chat: 'M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.4-3.2A7.5 7.5 0 1 1 20 11.5Z M9 11.5h.1 m3.4 0h.1 m3.4 0h.1',
    plus: 'M12 5v14M5 12h14',
    close: 'm6 6 12 12M18 6 6 18',
    person: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  };
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d={paths[name]} />
  </svg>;
}

function Meta({ post }: { post: { nickname: string; created_at: string } }) {
  return <div className="meta">
    <span className="avatar" aria-hidden="true">{Array.from(post.nickname)[0]}</span>
    <span className="author">{post.nickname}</span>
    <time dateTime={post.created_at}>{dateFormat.format(new Date(post.created_at))}</time>
  </div>;
}

function Modal({ title, close, busy = false, children }: {
  title: string; close: () => void; busy?: boolean; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return <dialog ref={ref} aria-labelledby="modal-title" onCancel={(event) => {
    event.preventDefault();
    if (!busy) close();
  }}>
    <div className="section-head">
      <h2 id="modal-title">{title}</h2>
      <button type="button" className="icon-button" aria-label="关闭" disabled={busy} onClick={close}>
        <Icon name="close" />
      </button>
    </div>
    {children}
  </dialog>;
}

function Field({ label, limit, value, onChange, multiline = false }: {
  label: string; limit: number; value: string; onChange: (value: string) => void; multiline?: boolean;
}) {
  const count = characters(value);
  const props = {
    value, required: true, 'aria-invalid': count > limit,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value),
  };
  return <label className="field">
    <span>{label}</span>
    {multiline ? <textarea {...props} rows={4} /> : <input {...props} />}
    <small className={count > limit ? 'error' : ''}>{count} / {limit}</small>
  </label>;
}

function NicknameDialog({ guest, close, change }: { guest: Guest; close: () => void; change: (guest: Guest) => void }) {
  const [nickname, setNickname] = useState(guest.nickname);
  return <Modal title="编辑匿名昵称" close={close}>
    <form onSubmit={(event) => {
      event.preventDefault();
      change({ ...guest, nickname: nickname.trim() });
      close();
    }}>
      <Field label="昵称" value={nickname} onChange={setNickname} limit={nicknameLimit} />
      <button className="primary" disabled={!nickname.trim() || characters(nickname) > nicknameLimit}>保存昵称</button>
    </form>
  </Modal>;
}

function TopicDialog({ guest, close, slug, point }: {
  guest: Guest; close: () => void; slug?: string; point?: Coordinates;
}) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [postPoint] = useState(point);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !title.trim() || !content.trim() || characters(title) > 80 || characters(content) > 2000) return;
    setBusy(true);
    setError('');
    try {
      const region = postPoint ? { lat: postPoint[0], lon: postPoint[1] } : undefined;
      const topic = await post<{ id: number }>(communityTopics(slug), { ...guest, title, content, region });
      window.location.assign(topicLink(topic.id, slug));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '发布失败。');
      setBusy(false);
    }
  }

  return <Modal title="发布新话题" close={close} busy={busy}>
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <Field label="标题" value={title} onChange={setTitle} limit={80} />
        <Field label="内容" value={content} onChange={setContent} limit={2000} multiline />
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={busy || !title.trim() || !content.trim() ||
        characters(title) > 80 || characters(content) > 2000}>{busy ? '发布中…' : '发布话题'}</button>
    </form>
  </Modal>;
}

const sourceName = (source: string) => ({ zhihu: '知乎', manual: '人工收录' }[source] ?? source);

function HotTopics() {
  const { data, error } = usePolling<HotTopic[]>('/api/hot-topics');
  return <section className="hot-section" aria-labelledby="hot-title">
    <h2 id="hot-title">社会热榜</h2>
    {error && <p className="notice" role="status">暂时无法刷新热榜。</p>}
    {!data && !error && <p className="notice" role="status">正在加载热榜…</p>}
    {data?.length === 0 && <p className="notice">暂无热榜话题。</p>}
    {!!data?.length && <ul className="card hot-list">
      {data.map((topic) => <li key={topic.topic_id}>
        <a className="hot-link" href={'/topics/' + topic.topic_id}>{topic.title}</a>
        <span className="hot-meta">{sourceName(topic.source)} · {topic.comment_count} 条评论</span>
      </li>)}
    </ul>}
  </section>;
}

function Feed({ compose, region }: { compose: () => void; region: RegionState }) {
  return <>
    <section className="hero" aria-labelledby="home-title">
      <div className="hero-copy">
        <span className="community"><span aria-hidden="true" />{region.area.name}</span>
        <h1 id="home-title">附近说</h1>
        <p>和同一个地方的人，聊聊身边的事。</p>
        <a className="primary map-entry" href="/map">探索附近地图</a>
      </div>
      <div className="hero-art" aria-hidden="true">
        <div className="orbit orbit-large" /><div className="orbit orbit-small" />
        <div className="bubble bubble-back"><i /><i /></div>
        <div className="bubble bubble-front"><i /><i /><i /></div>
      </div>
    </section>
    <section className="card map-card region-panel" aria-labelledby="region-title">
      <h2 id="region-title">地区动态</h2>
      <RegionControls region={region} />
    </section>
    {region.scope === 'city' && region.stats?.city === null
      ? null
      : <TopicList key={region.query} compose={compose} regionalPath={'/api/regions/topics?' + region.query} />}
    <HotTopics />
  </>;
}

function TopicList({ compose, slug, regionalPath }: { compose: () => void; slug?: string; regionalPath?: string }) {
  const { data, error } = usePolling<Topic[]>(regionalPath ?? communityTopics(slug));
  return <section aria-labelledby="feed-title">
      <div className="section-head feed-head">
        <h2 id="feed-title">{regionalPath ? '地区话题' : '社区话题'}</h2>
        <button className="primary" onClick={compose}><Icon name="plus" />发布话题</button>
      </div>
      {error && <p className="notice" role="status">{error.message} 页面会自动重试。</p>}
      {!data && !error && <p className="notice" role="status">正在加载话题…</p>}
      {data?.length === 0 && <div className="empty">
        <span className="empty-icon"><Icon name="chat" size={26} /></span>
        <h3>还没有话题</h3>
        <p>发个话题，开启社区的第一场对话。</p>
      </div>}
      {data && data.length > 0 && <ul className="topic-list">
        {data.map((topic) => <li key={topic.id}>
          <a className="card topic-card" href={topicLink(topic.id,
            slug ?? (topic.community_slug?.startsWith('place-') ? topic.community_slug : undefined))}>
            <Meta post={topic} />
            <h3>{topic.title}</h3>
            <p className="summary">{topic.summary}</p>
            <span className="reply-count"><Icon name="chat" size={17} />{topic.comment_count} 条评论</span>
          </a>
        </li>)}
      </ul>}
    </section>;
}

function Detail({ id, guest, slug }: { id: string; guest: Guest; slug?: string }) {
  const path = communityTopics(slug) + '/' + id;
  const { data, error, refresh } = usePolling<TopicDetail>(path);
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [writeError, setWriteError] = useState('');

  async function reply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !content.trim() || characters(content) > 500) return;
    setBusy(true);
    setWriteError('');
    try {
      await post(path + '/comments', { ...guest, content });
      setContent('');
      refresh();
    } catch (reason) {
      setWriteError(reason instanceof Error ? reason.message : '评论发送失败。');
    } finally {
      setBusy(false);
    }
  }

  return <>
    <a className="back" href={slug ? '/places/' + slug : '/'}>返回社区话题</a>
    {error && <p className="notice" role="status">
      {error.message}{!(error instanceof ApiError && error.status === 404) && ' 页面会自动重试。'}
    </p>}
    {!data && !error && <p className="notice" role="status">正在加载话题…</p>}
    {data && <>
      <article className="card detail">
        <Meta post={data} />
        <h1>{data.title}</h1>
        {data.content && <p className="post-content">{data.content}</p>}
        {data.hot_topic && <a className="back" href={data.hot_topic.original_url}
          target="_blank" rel="noopener noreferrer">
          {data.hot_topic.source === 'zhihu' ? '查看知乎原文' : '查看原文'}
        </a>}
      </article>
      <section className="card discussion" aria-labelledby="comments-title">
        <h2 id="comments-title">评论 <span className="count">{data.comments.length}</span></h2>
        {data.comments.length === 0 && <p className="quiet">还没有评论。</p>}
        <ul className="comments">
          {data.comments.map((comment) => <li key={comment.id}>
            <Meta post={comment} />
            <p className="post-content">{comment.content}</p>
          </li>)}
        </ul>
        <form onSubmit={reply}>
          <fieldset disabled={busy}>
            <Field label="发表评论" value={content} onChange={setContent} limit={500} multiline />
          </fieldset>
          {writeError && <p className="error" role="alert">{writeError}</p>}
          <button className="primary" disabled={busy || !content.trim() || characters(content) > 500}>
            {busy ? '发送中…' : '发送评论'}
          </button>
        </form>
      </section>
    </>}
  </>;
}

function PlaceCommunity({ slug, activity, compose }: {
  slug: string; activity: ReturnType<typeof usePlaceVisit>; compose: () => void;
}) {
  const { place, visits, error } = activity;
  return <>
    <a className="back" href="/map">返回附近地图</a>
    {error && <p className="notice" role="status">{error}</p>}
    {!place && !error && <p className="notice" role="status">正在打开地点社区…</p>}
    {place && <section className="card detail">
      <p className="hot-meta">{place.category} · {place.source === 'cityuhk' ? '香港城市大学校园目录' : 'Geoapify · OpenStreetMap'}</p>
      <h1>{place.name}</h1>
      {visits && <ul className="place-metrics">
        <li>最近 5 分钟 <strong>{visits.recent_visitors}</strong> 人浏览</li>
        <li>今日 <strong>{visits.today_visitors}</strong> 人访问</li>
        <li><strong>{visits.active_topics}</strong> 条有效话题</li>
      </ul>}
      <p className="quiet">访问量按地点当地日期统计，包含远程浏览。</p>
      {place.source === 'geoapify' && <p className="hot-meta"><a href="https://www.geoapify.com/">Geoapify</a> · <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a></p>}
    </section>}
    {visits && <TopicList compose={compose} slug={slug} />}
  </>;
}

function App({ initialGuest }: { initialGuest: Guest }) {
  const nearby = useNearby();
  const location = window.location.pathname;
  const region = useRegion(nearby.position, location === '/' || location === '/map');
  const [guest, setGuest] = useState(initialGuest);
  const [modal, setModal] = useState<'nickname' | 'topic'>();
  const placeMatch = /^\/places\/(place-[a-f0-9]{24})(?:\/topics\/([1-9]\d*))?\/?$/.exec(location);
  const slug = placeMatch?.[1];
  const topicId = placeMatch?.[2] ?? /^\/topics\/([1-9]\d*)\/?$/.exec(location)?.[1];
  const activity = usePlaceVisit(slug);
  const close = () => setModal(undefined);

  return <>
    <header className="site-header">
      <div className="shell topbar">
        <a className="brand" href="/" aria-label="NearTalk 首页">
          <span className="brand-icon"><Icon name="chat" size={25} /></span>
          <span>NearTalk</span>
        </a>
        <button className="guest-button" onClick={() => setModal('nickname')} aria-label={'编辑匿名昵称 ' + guest.nickname}>
          <Icon name="person" size={17} /><span>{guest.nickname}</span>
        </button>
      </div>
    </header>
    <main className="shell">
      {topicId ? <Detail id={topicId} guest={guest} slug={slug} />
        : slug ? <PlaceCommunity slug={slug} activity={activity} compose={() => setModal('topic')} />
        : location === '/map' ? <Suspense fallback={<p role="status">正在加载地图…</p>}><MapPage nearby={nearby} region={region} /></Suspense>
        : location === '/' ? <Feed compose={() => setModal('topic')} region={region} />
        : <div className="notice"><h1>页面不存在</h1><a className="back" href="/">返回社区话题</a></div>}
    </main>
    {modal === 'nickname' && <NicknameDialog guest={guest} close={close} change={(next) => {
      saveGuest(next);
      setGuest(next);
    }} />}
    {modal === 'topic' && <TopicDialog guest={guest} close={close} slug={slug}
      point={location === '/' ? region.area.point : undefined} />}
  </>;
}

createRoot(document.getElementById('root')!).render(<App initialGuest={loadGuest()} />);
