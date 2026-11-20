import { useState } from 'react';
import { ApiError, post, usePolling } from './api';
import { statusNames } from './HelpFeed';
import type { Status } from './helpApi';
import { Link } from './navigation';
import { dateFormat } from './ui';
import { AdminDiscussionAnswers } from './AdminDiscussionAnswers';
import './admin.css';

type Visibility = 'all' | 'visible' | 'hidden';
type Action = 'hide' | 'restore' | 'pin' | 'unpin';
interface AdminItem {
  id: number;
  title: string;
  content: string;
  nickname: string;
  status: Status;
  created_at: string;
  is_hidden: boolean;
  is_pinned: boolean;
  pinned_until: number | null;
  report_count: number;
}

export default function AdminRequests() {
  const [topicsOpen, setTopicsOpen] = useState(false);
  return <section className="admin-requests">
    <Link className="back" href="/account">返回我的账号</Link>
    <AdminDiscussionAnswers />
    <details className="card detail" onToggle={event => setTopicsOpen(event.currentTarget.open)}>
      <summary>管理讨论话题</summary>
      {topicsOpen && <AdminPostList endpoint="/api/admin/discussion-topics" label="话题" />}
    </details>
    <AdminPostList endpoint="/api/admin/requests" label="需求" />
  </section>;
}

function AdminPostList({ endpoint, label }: { endpoint: string; label: string }) {
  const [filter, setFilter] = useState<Visibility>('all');
  const [pages, setPages] = useState<number[]>([]);
  const before = pages.at(-1);
  const path = endpoint + '?visibility=' + filter + (before ? '&before=' + before : '');
  return <div>
    <div className="section-head admin-heading">
      {label === '需求' && <h1>管理公开需求</h1>}
      <label className="compact-field"><span className="sr-only">{label === '需求' ? '显示范围' : '话题范围'}</span>
        <select value={filter} onChange={event => {
          setFilter(event.target.value as Visibility);
          setPages([]);
        }}>
          <option value="all">全部{label}</option><option value="visible">公开中</option><option value="hidden">已下架</option>
        </select>
      </label>
    </div>
    <ModerationList key={path} path={path} endpoint={endpoint} label={label} previous={before ? () => setPages(pages.slice(0, -1)) : undefined}
      next={cursor => setPages([...pages, cursor])} />
  </div>;
}

function ModerationList({ path, endpoint, label, previous, next }: {
  path: string; endpoint: string; label: string; previous?: () => void; next: (cursor: number) => void;
}) {
  const { data, error, refresh } = usePolling<{ items: AdminItem[]; next_before: number | null }>(path, 15000);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState('');
  const [problem, setProblem] = useState('');
  async function act(item: AdminItem, action: Action) {
    if (busy || (action === 'hide' && !window.confirm('下架「' + item.title + '」？它将从公开列表移除，你可以稍后恢复。'))) return;
    setBusy(true);
    setResult('');
    setProblem('');
    try {
      await post(endpoint + '/' + item.id, { action });
      const messages = { hide: '已下架', restore: '已恢复公开', pin: '已在附近列表置顶', unpin: '已取消置顶' };
      setResult('「' + item.title + '」' + messages[action] + '。');
    } catch (err) { setProblem(err instanceof Error ? err.message : '操作失败，请重试。'); }
    finally { setBusy(false); refresh(); }
  }
  if (error instanceof ApiError && [401, 403].includes(error.status)) return <p className="notice" role="alert">{error.message}</p>;
  return <>
    {error && <p className="notice" role="alert">{error.message} <button className="text-button" onClick={refresh}>重试</button></p>}
    {problem && <p className="error" role="alert">{problem}</p>}
    {result && <p className="notice" role="status">{result}</p>}
    {!data && !error && <p className="notice" role="status">正在读取{label}…</p>}
    {data && (data.items.length ? <ul className="topic-list">
      {data.items.map(item => <li className="card admin-item" key={item.id}>
        <h2>{item.title}</h2>
        <p className="hot-meta">{item.nickname} · {dateFormat.format(new Date(item.created_at))} · {label === '话题'
          ? item.status === 'open' ? '讨论中' : '已结束' : statusNames[item.status]}</p>
        <div className="admin-flags">
          {item.is_hidden && <span className="help-tag">已下架</span>}
          {item.is_pinned && item.pinned_until && <span className="help-tag">置顶至 {dateFormat.format(new Date(item.pinned_until * 1000))}</span>}
          {item.report_count > 0 && <span className="help-tag reward">{item.report_count} 次举报</span>}
        </div>
        {item.content && <details><summary>查看正文</summary><p className="post-content">{item.content}</p></details>}
        {label === '话题' && !item.is_hidden && <Link href={'/discussions/' + item.id}>打开话题</Link>}
        <div className="admin-actions">
          {item.is_hidden ? <button className="guest-button" disabled={busy} onClick={() => void act(item, 'restore')}>恢复公开</button> : <>
            {(item.is_pinned || item.status === 'open') && <button className="guest-button" disabled={busy}
              onClick={() => void act(item, item.is_pinned ? 'unpin' : 'pin')}>{item.is_pinned ? '取消置顶' : '置顶（最多 12 小时）'}</button>}
            <button className="text-button admin-hide" disabled={busy} onClick={() => void act(item, 'hide')}>下架</button>
          </>}
        </div>
      </li>)}
    </ul> : <p className="empty">当前范围内没有{label}。</p>)}
    {(previous || data?.next_before) && <nav className="admin-actions" aria-label={label + '翻页'}>
      {previous && <button className="guest-button" disabled={busy} onClick={previous}>上一页</button>}
      {data?.next_before != null && <button className="guest-button" disabled={busy} onClick={() => next(data.next_before!)}>下一页</button>}
    </nav>}
  </>;
}
