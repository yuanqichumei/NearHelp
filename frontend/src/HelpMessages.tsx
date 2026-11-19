import { useEffect, useRef, useState } from 'react';
import { api, post, usePolling } from './api';
import { chatPath, requestLink } from './helpApi';
import type { Conversation, InboxData, Message } from './helpApi';
import { Link } from './navigation';
import { SafetyActions, TextForm } from './HelpDetail';
import { dateFormat } from './ui';

export function Inbox({ data, error }: { data?: InboxData; error?: Error }) {
  return <section className="card detail">
    <h1>消息</h1>
    {error && <p className="error" role="status">{error.message}</p>}
    {!data && !error && <p className="quiet">正在加载消息…</p>}
    {data && !data.pending.length && !data.chats.length && <p className="quiet">暂时没有消息。接受协助后会自动建立私信。</p>}
    {!!data?.pending.length && <><h2>待处理申请</h2><ul className="hot-list">
      {data.pending.map((notice) => <li key={notice.request_id}>
        <Link className="hot-link" href={requestLink(notice.request_id)}>{notice.title}</Link>
        <span className="hot-meta">{notice.offers} 人申请协助</span>
      </li>)}
    </ul></>}
    {!!data?.chats.length && <><h2>私信</h2><ul className="hot-list">
      {data.chats.map((chat) => <li key={chat.request_id}>
        <Link className="hot-link" href={'/messages/' + chat.request_id}>{chat.nickname} · {chat.title}</Link>
        {chat.unread > 0 && <span className="hot-meta">{chat.unread} 条未读</span>}
      </li>)}
    </ul></>}
  </section>;
}

export function ChatPage({ id, refreshInbox }: { id: string; refreshInbox: () => void }) {
  const path = chatPath(id);
  const { data, refresh, error } = usePolling<Conversation>(path, 4000);
  const [older, setOlder] = useState<Message[]>([]);
  const [more, setMore] = useState<boolean>();
  const [loading, setLoading] = useState(false);
  const [pageError, setPageError] = useState('');
  const lastRead = useRef(0);

  const lastIncoming = data?.messages.reduce((last, message) => message.mine ? last : message.id, 0);
  useEffect(() => {
    if (!lastIncoming || lastIncoming <= lastRead.current || document.hidden || error) return;
    let live = true;
    lastRead.current = lastIncoming;
    post(path + '/read/' + lastIncoming, {}).then(() => {
      if (live) refreshInbox();
    }).catch(() => { if (live) lastRead.current = 0; });
    return () => { live = false; };
  }, [data, lastIncoming, path, error]);

  async function loadOlder() {
    const before = older[0]?.id ?? data?.messages[0]?.id;
    if (loading || !before) return;
    setLoading(true);
    setPageError('');
    try {
      const previous = await api<Conversation>(path + '?before=' + before);
      setOlder((messages) => [...previous.messages, ...messages]);
      setMore(previous.has_older);
    } catch (reason) { setPageError(reason instanceof Error ? reason.message : '无法读取更早的消息。'); }
    finally { setLoading(false); }
  }

  if (error) return <p className="notice" role="status">{error.message}</p>;
  if (!data) return <p className="notice" role="status">正在打开私信…</p>;
  const messages = Array.from(new Map(
    [...older, ...data.messages].map((message) => [message.id, message]),
  ).values());
  return <>
    <Link className="back" href="/messages">返回消息</Link>
    <section className="card detail">
      <h1>{data.nickname}</h1>
      <Link className="back" href={requestLink(id)}>{data.title}</Link>
      <SafetyActions id={id} target={data.peer_id} blocked={refresh} />
      {messages.length === 0 && <p className="quiet">可以在这里商量如何帮忙。如需见面，可约在公开场所。</p>}
      {(more ?? data.has_older) && <button className="guest-button" onClick={() => void loadOlder()}
        disabled={loading}>查看更早消息</button>}
      {pageError && <p className="error" role="alert">{pageError}</p>}
      <ul className="help-chat" aria-label="聊天记录">
        {messages.map((message) => <li key={message.id} className={message.mine ? 'mine' : undefined}>
          <span className="sr-only">{message.mine ? '我' : data.nickname}</span>
          <p className="post-content">{message.content}</p>
          <time dateTime={message.created_at}>{dateFormat.format(new Date(message.created_at))}</time>
        </li>)}
      </ul>
      <TextForm label="私信内容" action="发送消息" submit={async (content) => {
        await post(path + '/messages', { content }); refresh();
      }} />
    </section>
  </>;
}
