import { useState } from 'react';
import { post, usePolling } from './api';
import { dateFormat } from './ui';

type Visibility = 'all' | 'visible' | 'hidden';
type Answer = { id: number; content: string; nickname: string; created_at: string; title: string;
  venue: string; parent_id: number | null; hidden: number; parent_hidden: number };
const endpoint = '/api/admin/discussion-answers';

export function AdminDiscussionAnswers() {
  const [open, setOpen] = useState(false);
  return <details className="card detail" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>管理讨论发言</summary>{open && <AnswerFilters />}
  </details>;
}

function AnswerFilters() {
  const [visibility, setVisibility] = useState<Visibility>('all');
  const [pages, setPages] = useState<number[]>([]);
  const before = pages.at(-1);
  const path = endpoint + '?visibility=' + visibility + (before ? '&before=' + before : '');
  return <>
    <label className="compact-field">发言范围<select value={visibility} onChange={event => {
      setVisibility(event.target.value as Visibility); setPages([]);
    }}>
      <option value="all">全部发言</option><option value="visible">公开中</option><option value="hidden">已下架</option>
    </select></label>
    <AnswerList key={path} path={path} next={cursor => setPages([...pages, cursor])}
      previous={before ? () => setPages(pages.slice(0,-1)) : undefined} />
  </>;
}

function AnswerList({ path, previous, next }: { path: string; previous?: () => void; next: (cursor: number) => void }) {
  const { data, error, refresh } = usePolling<{ items: Answer[]; next_before: number | null }>(path, 15000);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  async function change(answer: Answer) {
    if (busy) return;
    if (!answer.hidden && !window.confirm(answer.parent_id ? '下架这条回复？' : '下架这条回答及其下方的回复？')) return;
    setBusy(true);
    try {
      await post(endpoint + '/' + answer.id, { action: answer.hidden ? 'restore' : 'hide' });
      setFeedback(answer.hidden ? (answer.parent_hidden ? '已撤销单独下架，原回答恢复后可见。' : '发言已恢复。') : '发言已下架。');
      refresh();
    } catch (reason) { setFeedback(reason instanceof Error ? reason.message : '操作失败，请重试。'); }
    finally { setBusy(false); }
  }
  if (error) return <p className="error" role="alert">{error.message}</p>;
  return <>
    {feedback && <p role="status">{feedback}</p>}
    {!data ? <p role="status">正在读取发言…</p> : data.items.length === 0 ? <p>当前范围内没有发言。</p> :
      <ul className="topic-list">{data.items.map(item => <li className="card admin-item" key={item.id}>
        <strong>{item.venue} · {item.title}</strong>
        <p className="hot-meta">{item.nickname} · {dateFormat.format(new Date(item.created_at))} · {item.parent_id ? '回复' : '回答'}
          {item.hidden ? ' · 已下架' : item.parent_hidden ? ' · 随原回答下架' : ' · 公开中'}</p>
        <p className="post-content">{item.content}</p>
        <button className="guest-button" disabled={busy} onClick={() => void change(item)}>
          {item.hidden ? '恢复发言' : '下架发言'}</button>
      </li>)}</ul>}
    {previous && <button className="text-button" disabled={busy} onClick={previous}>上一页发言</button>}
    {data?.next_before != null && <button className="text-button" disabled={busy} onClick={() => next(data.next_before!)}>下一页发言</button>}
  </>;
}
