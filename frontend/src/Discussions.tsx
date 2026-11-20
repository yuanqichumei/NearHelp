import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { post, usePolling } from './api';
import { AreaControls } from './HelpFeed';
import { locationPayload } from './helpApi';
import type { Account, HelpArea } from './helpApi';
import { Link } from './navigation';
import { recentPositionTime } from './location';
import { dateFormat, Icon } from './ui';
import './discussions.css';

type Featured = { id: number; title: string; venue: string; count: number };
type Answer = { id: number; content: string; parent_id: number | null; nickname: string; created_at: string };
type Thread = { title: string; venue: string; active: boolean; answers: Answer[]; angle: string; zhihu_url: string;
  older: number | null; themes: string[]; summary: { contributors: number; extracts: { comment_id: number; text: string }[];
    themes: { label: string; people: number; comment_id: number }[] } };
type Catalog = { questions: { key: string; title: string; url: string }[];
  venues: { topic_id: number; venue: string; question_key: string; zhihu_url: string }[] };
const apiPath = '/api/discussions';
const problem = (reason: unknown) => reason instanceof Error ? reason.message : '暂时无法连接，请重试。';

export function DiscussionList({ region }: { region: HelpArea }) {
  const [lat, lon] = region.area.point;
  const body = JSON.stringify({ lat, lon, radius: region.radius });
  return <>
    <section className="location-panel home-location"><AreaControls region={region} compact /></section>
    <h1 className="talk-heading">附近讨论</h1>
    <NearbyQuestions key={body} body={body} />
  </>;
}

function NearbyQuestions({ body }: { body: string }) {
  const { data, error } = usePolling<Featured[]>(apiPath + '/nearby', 5000, body);
  if (error) return <p className="notice" role="alert">{error.message}</p>;
  if (!data) return <p role="status">正在查找附近的话题…</p>;
  if (!data.length) return <div className="empty"><h2>这个范围里还没有会场话题</h2>
    <p>可以调整上方的地区或范围，也可以先看看附近的求助。</p><Link href="/">查看附近求助</Link></div>;
  return <ul className="topic-list">{data.map(item => <li className="card talk-feature" key={item.id}>
    <Link href={'/discussions/' + item.id}><span className="talk-place"><Icon name="pin" size={16} />{item.venue} · 本期一问</span>
      <h2>{item.title}</h2><div className="talk-foot"><span>{item.count} 条发言</span>
        <strong>{item.count ? '参与讨论' : '写第一条回答'} →</strong></div></Link>
  </li>)}</ul>;
}

export function DiscussionPage({ id, region, account, login }: {
  id: string; region: HelpArea; account?: Account | null; login: () => void;
}) {
  const [before, setBefore] = useState<number>();
  const [target, setTarget] = useState<number>();
  const [draft, setDraft] = useState('');
  const [parent, setParent] = useState<Answer>();
  const [useLocation, setUseLocation] = useState(false);
  const [theme, setTheme] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const { data, error, refresh } = usePolling<Thread>(apiPath + '/' + id + (before ? '?before=' + before : ''), 3000);
  useEffect(() => {
    if (target && data?.answers.some(a => a.id === target)) {
      document.getElementById('answer-' + target)?.focus();
      setTarget(undefined);
    }
  }, [data, target]);
  function showSource(n: number) {
    if (data?.answers.some(a => a.id === n)) document.getElementById('answer-' + n)?.focus();
    else { setTarget(n); setBefore(n + 1); }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!account) { login(); return; }
    if (busy || !draft.trim()) return;
    setBusy(true); setMessage('');
    try {
      const pos = region.position;
      const fixTime = recentPositionTime(pos);
      if (useLocation && fixTime === undefined) throw new Error('请重新定位，或取消勾选后直接发表。');
      await post(apiPath + '/' + id + '/answers', { content: draft.trim(), parent_id: parent?.id,
        theme: useLocation && !parent ? theme : '',
        ...(useLocation && pos && fixTime !== undefined && { location: { ...locationPayload(pos), timestamp: fixTime / 1000 } }) });
      setDraft(''); setTheme(''); setParent(undefined); setBefore(undefined); refresh();
    } catch (reason) { setMessage(problem(reason)); } finally { setBusy(false); }
  }
  if (error) return <p className="notice" role="alert">{error.message} <Link href="/discussions">返回附近讨论</Link></p>;
  if (!data) return <p role="status">正在读取讨论…</p>;
  return <article className="talk-thread">
    <Link href="/discussions" className="back">返回附近讨论</Link>
    <div className="card detail"><span className="talk-place">{data.venue} · {data.active ? '本期一问' : '往期讨论'}</span>
      <h1>{data.title}</h1></div>
    <section className="card detail"><h2>会场里的回答</h2>
      {data.active && <form onSubmit={send} className="talk-form">
        {parent && <p>回复 {parent.nickname} <button type="button" className="text-button" onClick={() => setParent(undefined)}>取消回复</button></p>}
        <label className="field">{parent ? '写下回复' : '说说我的看法'}<textarea id="discussion-draft" maxLength={500} required
          value={draft} onChange={e => setDraft(e.target.value)} /></label>
        {!parent && <label className="help-checkbox"><input type="checkbox" checked={useLocation}
          onChange={e => setUseLocation(e.target.checked)} />使用设备定位，让会场 1 公里内的回答参与观点小结</label>}
        {useLocation && !parent && <><button type="button" className="text-button" disabled={region.locating} onClick={() => void region.locate()}>
          {region.locating ? '正在定位…' : region.position ? '重新定位' : '获取当前位置'}</button>
          <small>{region.error || (region.position ? '已取得设备位置' : region.privacyHint)}</small>
          <label className="field">我的关注点（可选）<select value={theme} onChange={e => setTheme(e.target.value)}>
            <option value="">直接发表</option>{data.themes.map(t => <option key={t}>{t}</option>)}</select></label></>}
        {message && <p className="error" role="alert">{message}</p>}
        <button className="primary" disabled={!draft.trim() || busy}>{busy ? '发送中…' : parent ? '发送回复' : '发表看法'}</button>
      </form>}
      {!data.answers.length && <p className="quiet">还没有人回答。你会怎么选？</p>}
      {data.answers.map(a => <article className="talk-answer" key={a.id} id={'answer-' + a.id} tabIndex={-1}>
        <small>{a.nickname} · {dateFormat.format(new Date(a.created_at))}</small>
        {a.parent_id && <button className="text-button" onClick={() => showSource(a.parent_id!)}>回复了 #{a.parent_id} 的回答</button>}
        <p className="post-content">{a.content}</p>
        {!a.parent_id && data.active && <button className="text-button" onClick={() => {
          setParent(a); setUseLocation(false); document.getElementById('discussion-draft')?.focus();
        }}>回复</button>}
      </article>)}
      {before && <button className="text-button" onClick={() => setBefore(undefined)}>回到最新发言</button>}
      {data.older && <button className="guest-button" onClick={() => setBefore(data.older!)}>更早的发言</button>}
    </section>
    <section className="card detail"><h2>附近观点小结</h2>
      {data.summary.extracts.length ? <><p className="quiet">从 {data.summary.contributors} 位附近参与者的回答中摘录，每人最多一条。</p>
        {!!data.summary.themes.length && <p>大家主动标记的关注点：{data.summary.themes.map(t => <button className="text-button"
          key={t.label} onClick={() => showSource(t.comment_id)}>{t.label}（{t.people} 人）</button>)}</p>}
        {data.summary.extracts.map(e => <blockquote key={e.comment_id}>{e.text} <button className="text-button"
          onClick={() => showSource(e.comment_id)}>查看原回答</button></blockquote>)}</> :
        <p className="quiet">至少 3 位附近参与者留下有内容的回答后，这里会摘出不同的看法。</p>}</section>
    <details className="card detail"><summary>换个角度想 · AI 视角</summary>
      <p>{data.angle}</p><small>随本期问题预先生成</small></details>
    {data.zhihu_url && <a className="card talk-reading" href={data.zhihu_url} rel="noopener noreferrer" target="_blank">知乎相关讨论 <span>查看原文 ↗</span></a>}
  </article>;
}

export function DiscussionEditor({ region }: { region: HelpArea }) {
  const [open, setOpen] = useState(false);
  return <details className="card detail" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>管理会场一问</summary>{open && <Editor region={region} />}</details>;
}

function Editor({ region }: { region: HelpArea }) {
  const { data, error, refresh } = usePolling<Catalog>(apiPath + '/catalog', 30000);
  if (error) return <p role="alert">{error.message}</p>;
  if (!data) return <p>正在读取题库…</p>;
  return <SelectionForm data={data} refresh={refresh} region={region} />;
}

function SelectionForm({ region, data, refresh }: { region: HelpArea; data: Catalog; refresh: () => void }) {
  const first = data.venues[0];
  const [venue, setVenue] = useState(first?.venue ?? '');
  const [expected, setExpected] = useState<number | undefined>(first?.topic_id);
  const [creating, setCreating] = useState(false);
  const [question, setQuestion] = useState(first?.question_key ?? 'authorship');
  const [url, setUrl] = useState<string | undefined>(first?.zhihu_url);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const selected = creating ? venue.trim() : venue || data.venues[0]?.venue;
  const reference = url ?? data.questions.find(q => q.key === question)?.url ?? '';
  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy || !selected) return;
    setBusy(true); setMessage('');
    try {
      const saved = await post<{ id: number }>(apiPath + '/feature', { venue: selected, question, zhihu_url: reference, lat: region.area.point[0], lon: region.area.point[1],
        expected_topic_id: creating ? null : expected });
      setCreating(false); setVenue(selected); setExpected(saved.id); refresh(); setMessage('已更新「' + selected + '」的本期问题。');
    } catch (reason) { setMessage(problem(reason)); refresh(); } finally { setBusy(false); }
  }
  return <form className="talk-form" onSubmit={save}>
    <label className="field">会场<select value={creating ? '@new' : selected} onChange={e => {
      const v = data.venues.find(item => item.venue === e.target.value);
      setCreating(!v); setVenue(v?.venue ?? ''); setExpected(v?.topic_id); setQuestion(v?.question_key ?? 'authorship'); setUrl(v?.zhihu_url);
    }}>{data.venues.map(v => <option key={v.venue}>{v.venue}</option>)}<option value="@new">添加会场</option></select></label>
    {creating && <><label className="field">公开会场名称<input required maxLength={40} value={venue} onChange={e => setVenue(e.target.value)} /></label>
      <p>新会场将使用下方浏览区域的中心。请在会场定位，或选择对应地区。</p><AreaControls region={region} /></>}
    <label className="field">本期问题<select value={question} onChange={e => { setQuestion(e.target.value); setUrl(undefined); }}>
      {data.questions.map(q => <option key={q.key} value={q.key}>{q.title}</option>)}</select></label>
    <label className="field">知乎问题或回答链接（可留空）<input type="url" value={reference} onChange={e => setUrl(e.target.value)} /></label>
    <small>更换问题会结束上一期，原链接和发言保留。</small>
    <button className="primary" disabled={busy}>保存本期问题</button>{message && <p role="status">{message}</p>}
  </form>;
}
