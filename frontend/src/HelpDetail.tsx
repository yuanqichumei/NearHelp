import { useState } from 'react';
import type { FormEvent } from 'react';
import { post, usePolling } from './api';
import { locationPayload, requestLink, requestPath } from './helpApi';
import type { Account, RequestDetail, RequestItem } from './helpApi';
import { remainingTime, statusNames } from './HelpFeed';
import { Link, navigate } from './navigation';
import { readPosition } from './location';
import { characters, Field, Meta, Modal } from './ui';

export function PublishPage({ onPosition }: { onPosition: (position: GeolocationPosition) => void }) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [minutes, setMinutes] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const valid = !!title.trim() && !!content.trim() && characters(title) <= 80 && characters(content) <= 2000;

  async function publish(event: FormEvent) {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError('');
    try {
      const position = await readPosition().catch(() => {
        throw new Error('发布需要获取当前位置。请开启浏览器定位权限后重试。');
      });
      const location = locationPayload(position);
      const item = await post<RequestItem>('/api/help/requests', { title, content, minutes, location });
      onPosition(position);
      navigate(requestLink(item.id), true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '暂时无法发布。');
    } finally { setBusy(false); }
  }

  return <section className="card detail help-form">
    <h1>发布免费需求</h1>
    <p className="quiet">提交时使用浏览器定位。公开卡片只显示大致距离。</p>
    <form onSubmit={publish}>
      <fieldset disabled={busy}>
        <Field label="需要什么帮助？" value={title} onChange={setTitle} limit={80} />
        <Field label="具体说明" value={content} onChange={setContent} limit={2000} multiline />
        <label className="field">有效期<select value={minutes} onChange={(event) => setMinutes(Number(event.target.value))}>
          <option value={30}>30 分钟</option><option value={60}>1 小时</option><option value={180}>3 小时</option>
          <option value={1440}>24 小时</option>
        </select></label>
      </fieldset>
      <p className="quiet">请只发布低风险的小事，避免公开私人地址、联系方式或证件信息。</p>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={busy || !valid}>{busy ? '正在定位并发布…' : '定位并发布'}</button>
    </form>
  </section>;
}

export function TextForm({ label, action, submit }: {
  label: string; action: string; submit: (content: string) => Promise<void>;
}) {
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <form className="help-text-form" onSubmit={async (event) => {
    event.preventDefault();
    if (busy || !content.trim() || characters(content) > 500) return;
    setBusy(true);
    setError('');
    try { await submit(content); setContent(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '发送失败。'); }
    finally { setBusy(false); }
  }}>
    <fieldset disabled={busy}><Field label={label} value={content} onChange={setContent} limit={500} multiline /></fieldset>
    {error && <p className="error" role="alert">{error}</p>}
    <button className="primary" disabled={busy || !content.trim() || characters(content) > 500}>{action}</button>
  </form>;
}

export function SafetyActions({ id, target, blocked }: { id: string; target: string; blocked: () => void }) {
  const [reportOpen, setReportOpen] = useState(false);
  const [note, setNote] = useState('');
  return <div className="help-safety">
    <button className="text-button" onClick={() => setReportOpen(true)}>举报</button>
    <button className="text-button" onClick={async () => {
      if (!window.confirm('屏蔽后将停止与此用户的互动。你可以在「我的」解除屏蔽。')) return;
      try {
        await post('/api/help/blocks/' + target, { blocked: true });
        blocked();
      } catch (error) { setNote(error instanceof Error ? error.message : '操作失败。'); }
    }}>屏蔽</button>
    {note && <p role="status">{note}</p>}
    {reportOpen && <Modal title="举报用户" close={() => setReportOpen(false)}>
      <TextForm label="举报原因" action="提交举报" submit={async (content) => {
        await post(requestPath(id) + '/reports/' + target, { reason: content });
        setReportOpen(false);
        setNote('举报已提交。');
      }} />
    </Modal>}
  </div>;
}

export function HelpDetail({ id, account, signIn }: { id: string; account: Account | null; signIn: () => void }) {
  const path = requestPath(id);
  const { data, refresh, error } = usePolling<RequestDetail>(path, 4000);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');

  async function action(endpoint: string, body: object) {
    setBusy(true);
    setProblem('');
    try { await post(endpoint, body); refresh(); }
    catch (reason) { setProblem(reason instanceof Error ? reason.message : '操作失败。'); }
    finally { setBusy(false); }
  }

  if (error) return <p className="notice" role="status">{error.message}</p>;
  if (!data) return <p className="notice" role="status">正在加载需求…</p>;
  const open = data.status === 'open' || data.status === 'in_progress';
  return <>
    <Link className="back" href="/">返回附近需求</Link>
    <article className="card detail">
      <Meta post={data} />
      <div className="help-tag-row"><span className="help-tag">免费求助</span>
        <span>{statusNames[data.status]}{open && ' · ' + remainingTime(data.expires_at)}</span></div>
      <h1>{data.title}</h1>
      <p className="post-content">{data.content}</p>
      <div className="help-controls">
        {data.chat_id && <Link className="primary help-action" href={'/messages/' + data.chat_id}>打开私信</Link>}
        {data.is_owner && open && <>
          <button className="primary" disabled={busy} onClick={() => void action(path + '/state', { status: 'resolved' })}>标记已解决</button>
          <button className="guest-button" disabled={busy} onClick={() => {
            if (window.confirm('取消后，这条需求会退出附近列表。')) void action(path + '/state', { status: 'cancelled' });
          }}>取消需求</button>
        </>}
        {!data.is_owner && data.status === 'open' && !data.offers.length &&
          <button className="primary" disabled={busy} onClick={() =>
            account ? void action(path + '/offers', {}) : signIn()}>我可以帮忙</button>}
        {!data.is_owner && data.offers.length > 0 && !data.chat_id &&
          <span className="quiet">{data.offers[0].status === 'pending' && data.status === 'open'
            ? '已申请，等待对方接受' : '协助申请已结束'}</span>}
      </div>
      {problem && <p role="alert" className="error">{problem}</p>}
      {account && !data.is_owner && <SafetyActions id={id} target={data.author_id} blocked={() => navigate('/')} />}
    </article>
    {data.is_owner && data.offers.length > 0 && <section className="card discussion detail">
      <h2>协助申请</h2>
      <ul className="hot-list">{data.offers.map((offer) => <li key={offer.helper_id}>
        <span>{offer.nickname}</span>
        {offer.status === 'pending' && data.status === 'open' ? <div className="help-controls">
          <button className="primary" disabled={busy} onClick={() => void action(
            path + '/offers/' + offer.helper_id, { decision: 'accepted' },
          )}>接受协助</button>
          <button className="guest-button" disabled={busy} onClick={() => void action(
            path + '/offers/' + offer.helper_id, { decision: 'declined' },
          )}>拒绝</button>
        </div> : <span className="hot-meta">{offer.status === 'accepted' ? '已接受'
          : offer.status === 'declined' ? '已结束' : '申请已关闭'}</span>}
        <SafetyActions id={id} target={offer.helper_id} blocked={refresh} />
      </li>)}</ul>
    </section>}
    <section className="card discussion">
      <h2>公开回复 <span className="count">{data.replies.length}</span></h2>
      {data.replies.length === 0 && <p className="quiet">还没有回复。</p>}
      <ul className="comments">{data.replies.map((reply) => <li key={reply.id}>
        <Meta post={reply} />
        <p className="post-content">{reply.content}</p>
        {account && account.id !== reply.author_id &&
          <SafetyActions id={id} target={reply.author_id} blocked={refresh} />}
      </li>)}</ul>
      {open && (account ? <TextForm label="公开回复" action="发送回复" submit={async (content) => {
        await post(path + '/replies', { content }); refresh();
      }} /> : <button className="guest-button" onClick={signIn}>登录后回复</button>)}
    </section>
  </>;
}
