import { useState } from 'react';
import { defaultAreas, requestLink, requestPath } from './helpApi';
import type { Account, Discovery, HelpArea, Profile, Radius, Status } from './helpApi';
import { post } from './api';
import { Link, navigate } from './navigation';
import { Icon } from './ui';

export const statusNames: Record<Status, string> = {
  open: '待解决', in_progress: '进行中', resolved: '已解决', expired: '已过期', cancelled: '已取消',
};

export function Reward({ cents }: { cents: number }) {
  return <span className={'help-tag' + (cents ? ' reward' : '')}>{cents
    ? '悬赏 HK$' + (cents / 100).toLocaleString('en-HK', { maximumFractionDigits: 2 })
    : '免费互助'}</span>;
}

export function publishedSince(date: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(date)) / 60000));
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return minutes + ' 分钟前';
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? hours + ' 小时前' : Math.floor(hours / 24) + ' 天前';
}

export function remainingTime(expires: number) {
  const minutes = Math.ceil((expires * 1000 - Date.now()) / 60000);
  if (minutes <= 0) return '已到期';
  if (minutes < 60) return '剩余 ' + minutes + ' 分钟';
  return '剩余 ' + Math.floor(minutes / 60) + ' 小时 ' + (minutes % 60) + ' 分钟';
}

export function AreaControls({ region }: { region: HelpArea }) {
  const names = defaultAreas.map((area) => area.name);
  return <>
    <div className="location-line">
      <div><span className="location-name"><Icon name="pin" size={18} />{region.position ? '' : '浏览 · '}{region.area.name}</span>
        <p className="location-hint" role="status">{region.locating ? '正在获取设备位置…' : region.position
          ? '定位成功 · 精度约 ' + Math.ceil(region.position.coords.accuracy) + ' 米'
          : region.error ? '可手动选区继续浏览' : '开启定位，发现附近的需求。'}</p></div>
      <button className="guest-button" onClick={() => void region.locate()} disabled={region.locating}>
        {region.locating ? '正在定位…' : region.position || region.error ? '重新定位' : '获取当前位置'}
      </button>
    </div>
    {region.error && <p className="error" role="alert">{region.error}</p>}
    <div className="help-controls">
      <label className="compact-field">浏览区域
        <select value={region.area.name} onChange={(event) => {
          const next = defaultAreas.find((area) => area.name === event.target.value);
          if (next) region.choose(next.point, next.name);
        }}>
          {!names.includes(region.area.name) && <option value={region.area.name}>{region.area.name}</option>}
          {defaultAreas.map((area) => <option key={area.name}>{area.name}</option>)}
        </select>
      </label>
      <label className="compact-field">范围
        <select value={region.radius} onChange={(event) => region.setRadius(Number(event.target.value) as Radius)}>
          <option value={500}>500 米</option><option value={1000}>1 公里</option><option value={3000}>3 公里</option>
        </select>
      </label>
    </div>
  </>;
}

export function AreaSummary({ region, data }: { region: HelpArea; data?: Discovery }) {
  const distance = region.radius < 1000 ? region.radius + ' 米' : region.radius / 1000 + ' 公里';
  const active = data?.active_band === 'hidden' ? '最近活跃人数较少'
    : data ? data.active_band + ' 人最近活跃' : '正在获取活跃人数';
  return <p className="help-summary" role="status">附近 {distance} · {active}</p>;
}

export function HelpFeed({ region, data, error, account, signIn }: {
  region: HelpArea; data?: Discovery; error?: string; account?: Account | null; signIn: () => void;
}) {
  const [sending, setSending] = useState<number>();
  const [offerError, setOfferError] = useState('');
  async function offer(id: number) {
    if (!account) { signIn(); return; }
    setSending(id);
    setOfferError('');
    try { await post(requestPath(id) + '/offers', {}); navigate(requestLink(id)); }
    catch (reason) { setOfferError(reason instanceof Error ? reason.message : '申请失败，请重试。'); }
    finally { setSending(undefined); }
  }
  return <>
    <section className="location-panel" aria-label="定位与浏览范围">
      <AreaControls region={region} />
    </section>
    <div className="section-head feed-head">
      <h1>附近需求</h1>
      <Link className="map-link" href="/map"><Icon name="pin" size={16} />查看地图</Link>
    </div>
    {error && <p className="notice" role="status">{error}</p>}
    {offerError && <p className="error" role="alert">{offerError}</p>}
    {!data && !error && <p className="notice" role="status">正在加载附近信息…</p>}
    {data && (
      data.requests.length ? <ul className="topic-list">
        {data.requests.map((item) => <li key={item.id} className="card topic-card">
          <Link className="card-main" href={requestLink(item.id)}>
            <div className="help-tag-row">
              <Reward cents={item.reward_cents} />
              <span className="hot-meta">{statusNames[item.status]}</span>
            </div>
            <h3>{item.title}</h3><p className="summary">{item.summary}</p>
            <p className="help-item-meta">
              约 {item.distance_m} 米 · {publishedSince(item.created_at)} · {item.nickname}
            </p>
          </Link>
          <div className="card-foot">
            <Link href={requestLink(item.id) + '#comments'}><Icon name="chat" size={16} />评论 {item.comment_count}</Link>
            {account?.id === item.author_id ? <Link href={requestLink(item.id)}>管理需求</Link>
              : item.has_offered ? <Link href={requestLink(item.id)}>查看申请</Link>
              : <button className="offer-button" disabled={sending !== undefined} onClick={() => void offer(item.id)}>
                {sending === item.id ? '发送中…' : '我能帮忙'}</button>}
          </div>
        </li>)}
      </ul> : <div className="empty">
        <span className="empty-icon"><Icon name="chat" size={26} /></span>
        <h3>附近暂时没有待解决的需求。</h3>
        <div className="empty-actions"><Link className="primary help-action" href="/publish">发布需求</Link>
          {region.radius < 3000 && <button className="guest-button" onClick={() =>
            region.setRadius(region.radius === 500 ? 1000 : 3000)}>扩大搜索范围</button>}</div>
      </div>
    )}
    {data && <details className="directory">
      <summary>附近活跃与公开昵称</summary><AreaSummary region={region} data={data} />
      <NearbyUsers users={data.users} signedIn={!!account} />
    </details>}
  </>;
}

function NearbyUsers({ users, signedIn }: { users: Profile[]; signedIn: boolean }) {
  if (!signedIn) return <div className="empty"><p>登录后可查看主动公开的附近用户。</p><Link className="back" href="/account">登录</Link></div>;
  if (!users.length) return <p className="notice">附近暂无可展示的公开资料。</p>;
  return <ul className="card hot-list">
    {users.map((profile) => <li key={profile.id}><span className="author">{profile.nickname}</span></li>)}
  </ul>;
}
