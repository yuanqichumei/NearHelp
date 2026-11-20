import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { post, usePolling } from './api';
import { locationPayload, requestLink, requestPath } from './helpApi';
import type { Account, HelpArea, RequestDetail, RequestItem } from './helpApi';
import { remainingTime, Reward, statusNames } from './HelpFeed';
import { Link, navigate } from './navigation';
import { recentPositionTime } from './location';
import { characters, Field, Meta, Modal } from './ui';

export function PublishPage({ region }: { region: HelpArea }) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [minutes, setMinutes] = useState(60);
  const [paid, setPaid] = useState(false);
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const cents = paid ? Math.round(Number(amount) * 100) : 0;
  const validAmount = !paid || (/^\d{1,5}(\.\d{1,2})?$/.test(amount) && cents > 0 && cents <= 1000000);
  const valid = !!title.trim() && !!content.trim() && characters(title) <= 80 && characters(content) <= 2000 && validAmount;

  async function publish(event: FormEvent) {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError('');
    try {
      if (!region.position || recentPositionTime(region.position) === undefined) throw new Error('请重新获取当前位置后发布，已填写的内容会保留。');
      const location = locationPayload(region.position);
      const item = await post<RequestItem>('/api/help/requests', { title, content, minutes, location, reward_cents: cents });
      navigate(requestLink(item.id), true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '暂时无法发布。');
    } finally { setBusy(false); }
  }

  return <section className="card detail help-form">
    <h1>发布需求</h1>
    <div className="location-line"><p className="quiet" role="status">{region.locating ? '正在定位…' : region.position
      ? '定位成功 · 精度约 ' + Math.ceil(region.position.coords.accuracy) + ' 米' : region.privacyHint || '开启定位，将需求发给附近的人。'}</p>
      <button className="guest-button" disabled={region.locating || busy} onClick={() => void region.locate()}>
        {region.position || region.error ? '重新定位' : '获取当前位置'}</button></div>
    {region.error && <p className="error" role="alert">{region.error}</p>}
    <form onSubmit={publish}>
      <fieldset disabled={busy}>
        <Field label="需要什么帮助？" value={title} onChange={setTitle} limit={80} />
        <Field label="具体说明" value={content} onChange={setContent} limit={2000} multiline />
        <label className="field">互助方式<select value={paid ? 'reward' : 'free'}
          onChange={event => setPaid(event.target.value === 'reward')}>
          <option value="free">免费互助</option><option value="reward">悬赏</option>
        </select></label>
        {paid && <label className="field">悬赏金额（HK$）<input inputMode="decimal" required maxLength={8}
          value={amount} onChange={event => setAmount(event.target.value)} placeholder="例如 5" />
          <small>{amount && !validAmount ? '请输入 0.01 至 10,000 港元，最多两位小数。' : '仅展示约定金额，平台不收付款。'}</small></label>}
        <label className="field">有效期<select value={minutes} onChange={(event) => setMinutes(Number(event.target.value))}>
          <option value={30}>30 分钟</option><option value={60}>1 小时</option><option value={180}>3 小时</option>
          <option value={1440}>24 小时</option>
        </select></label>
      </fieldset>
      <p className="quiet">请只发布低风险的小事，避免公开私人地址、联系方式或证件信息。</p>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="primary" disabled={busy || region.locating || !valid}>{busy ? '正在发布…' : '发布需求'}</button>
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
  const { data, refresh, error } = usePolling<RequestDetail>(path, 2500);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [replyTo, setReplyTo] = useState<number>();
  useEffect(() => {
    if (data && window.location.hash === '#comments') document.getElementById('comments')?.scrollIntoView();
  }, [data?.id]);

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
  const names = new Map(data.replies.map(reply => [reply.id, reply.nickname]));
  return <>
    <Link className="back" href="/">返回附近需求</Link>
    <article className="card detail">
      <Meta post={data} />
      <div className="help-tag-row"><Reward cents={data.reward_cents} />
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
            account ? void action(path + '/offers', {}) : signIn()}>我能帮忙</button>}
        {!data.is_owner && data.offers.length > 0 && !data.chat_id &&
          <span className="quiet">{data.offers[0].status === 'pending' && data.status === 'open'
            ? '已申请，等待对方接受' : '本次申请未获接受'}</span>}
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
    <section id="comments" className="card discussion">
      <h2>公开评论 <span className="count">{data.replies.length}</span></h2>
      {data.replies.length === 0 && <p className="quiet">还没有评论。</p>}
      <ul className="comments">{data.replies.map((reply) => <li key={reply.id} className={reply.parent_id ? 'child-comment' : undefined}>
        <Meta post={reply} />
        {reply.parent_id && <small className="quiet">回复 {names.get(reply.parent_id) ?? '原评论'}</small>}
        <p className="post-content">{reply.content}</p>
        {open && !reply.parent_id && <button className="text-button" onClick={() => account ? setReplyTo(reply.id) : signIn()}>回复</button>}
        {account && account.id !== reply.author_id &&
          <SafetyActions id={id} target={reply.author_id} blocked={refresh} />}
        {open && account && replyTo === reply.id && <>
          <TextForm label={'回复 ' + reply.nickname} action="发送回复" submit={async content => {
            await post(path + '/replies', { content, parent_id: reply.id }); setReplyTo(undefined); refresh();
          }} />
          <button className="text-button" onClick={() => setReplyTo(undefined)}>取消回复</button>
        </>}
      </li>)}</ul>
      {open && (account ? <TextForm label="公开评论" action="发表评论" submit={async (content) => {
        await post(path + '/replies', { content }); refresh();
      }} /> : <button className="guest-button" onClick={signIn}>登录后评论</button>)}
    </section>
  </>;
}
