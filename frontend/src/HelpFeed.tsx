import { useState } from 'react';
import { defaultAreas, requestLink } from './helpApi';
import type { Discovery, HelpArea, Profile, Radius, Status } from './helpApi';
import { Link } from './navigation';
import { Icon } from './ui';

export const statusNames: Record<Status, string> = {
  open: '待解决', in_progress: '进行中', resolved: '已解决', expired: '已过期', cancelled: '已取消',
};

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
      <button className="guest-button" onClick={() => void region.locate()} disabled={region.locating}>
        {region.locating ? '正在定位…' : '定位到我'}
      </button>
    </div>
    {region.error && <p className="error" role="status">{region.error}</p>}
  </>;
}

export function AreaSummary({ region, data }: { region: HelpArea; data?: Discovery }) {
  const distance = region.radius < 1000 ? region.radius + ' 米' : region.radius / 1000 + ' 公里';
  const active = data?.active_band === 'hidden' ? '最近活跃人数较少'
    : data ? data.active_band + ' 人最近活跃' : '正在获取活跃人数';
  return <p className="help-summary" role="status">附近 {distance} · {active}</p>;
}

export function HelpFeed({ region, data, error, signedIn }: {
  region: HelpArea; data?: Discovery; error?: string; signedIn: boolean;
}) {
  const [directory, setDirectory] = useState(false);
  return <>
    <section className="hero help-hero" aria-labelledby="help-title">
      <div className="hero-copy">
        <h1 id="help-title">身边的小事，<br />附近有人帮</h1>
        <p>{region.position ? '看看附近有哪些人需要帮忙。' : '开启定位，发现附近正在发生的小事。'}</p>
        <AreaControls region={region} />
        <AreaSummary region={region} data={data} />
      </div>
      <Link className="guest-button help-map-link" href="/map">打开地图</Link>
    </section>
    <div className="section-head feed-head">
      <div className="help-tabs" role="group" aria-label="附近内容筛选">
        <button aria-pressed={!directory} onClick={() => setDirectory(false)}>附近需求</button>
        <button aria-pressed={directory} onClick={() => setDirectory(true)}>附近用户</button>
      </div>
      <Link className="primary help-action" href="/publish"><Icon name="plus" />发布需求</Link>
    </div>
    {error && <p className="notice" role="status">{error}</p>}
    {!data && !error && <p className="notice" role="status">正在加载附近信息…</p>}
    {data && (directory ? <NearbyUsers users={data.users} signedIn={signedIn} /> : (
      data.requests.length ? <ul className="topic-list">
        {data.requests.map((item) => <li key={item.id}>
          <Link className="card topic-card" href={requestLink(item.id)}>
            <div className="help-tag-row">
              <span className="help-tag">免费求助</span>
              <span className="hot-meta">{statusNames[item.status]} · {remainingTime(item.expires_at)}</span>
            </div>
            <h3>{item.title}</h3><p className="summary">{item.summary}</p>
            <p className="help-item-meta">
              约 {item.distance_m} 米 · {publishedSince(item.created_at)} · {item.nickname} · {item.response_count} 人回应
            </p>
          </Link>
        </li>)}
      </ul> : <div className="empty">
        <span className="empty-icon"><Icon name="chat" size={26} /></span>
        <h3>附近暂时没有待解决的需求</h3>
        <Link className="back" href="/publish">发布一个需求</Link>
      </div>
    ))}
  </>;
}

function NearbyUsers({ users, signedIn }: { users: Profile[]; signedIn: boolean }) {
  if (!signedIn) return <div className="empty"><p>登录后可查看主动公开的附近用户。</p><Link className="back" href="/account">登录</Link></div>;
  if (!users.length) return <p className="notice">附近暂无可展示的公开资料。</p>;
  return <ul className="card hot-list">
    {users.map((profile) => <li key={profile.id}><span className="author">{profile.nickname}</span></li>)}
  </ul>;
}
