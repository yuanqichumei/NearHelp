import { useState } from 'react';
import type { FormEvent } from 'react';
import { post, usePolling } from './api';
import type { Account, Profile, RequestItem } from './helpApi';
import { requestLink } from './helpApi';
import { statusNames } from './HelpFeed';
import { Link, navigate } from './navigation';

export function LoginRequired({ reason, signIn }: { reason: string; signIn: () => void }) {
  return <div className="empty">
    <p>{reason}</p>
    <button className="primary" onClick={signIn}>登录或注册</button>
  </div>;
}

export function AccountPage({ account, update, returnTo, adminLogin = false }: {
  account: Account | null;
  update: (value: Account | null) => void;
  returnTo: string;
  adminLogin?: boolean;
}) {
  const [wantsRegister, setRegister] = useState(false);
  const register = !adminLogin && wantsRegister;
  const [nickname, setNickname] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const next = await post<Account>(register ? '/api/auth/register' : '/api/auth/login',
        register ? { username, password, nickname } : { username, password });
      setPassword('');
      update(next);
      navigate(returnTo, true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法登录。');
    } finally { setBusy(false); }
  }

  if (account) return <ProfilePage key={account.id} account={account} update={update} />;
  return <section className="card detail help-form">
    <h1>{adminLogin ? '管理员登录' : register ? '创建账号' : '登录 Around You'}</h1>
    {!adminLogin && <p className="quiet">使用账号可在不同设备上继续之前的互助。</p>}
    <form onSubmit={signIn}>
      <fieldset disabled={busy}>
        {register && <label className="field">公开昵称<input required maxLength={24} value={nickname}
          onChange={(event) => setNickname(event.target.value)} autoComplete="nickname" /></label>}
        <label className="field">账号<input required autoComplete="username" autoCapitalize="none"
          pattern="[A-Za-z0-9_]{3,24}" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label className="field">密码<input required type="password" minLength={10} maxLength={128}
          autoComplete={register ? 'new-password' : 'current-password'}
          value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="help-controls">
        <button className="primary" disabled={busy}>{register ? '完成注册' : '登录'}</button>
        {!adminLogin && <button className="guest-button" type="button" disabled={busy} onClick={() => {
          setRegister(!register); setError('');
        }}>{register ? '已有账号，去登录' : '创建账号'}</button>}
      </div>
    </form>
    <Link className="back" href="/">继续以游客身份浏览</Link>
  </section>;
}

function ProfilePage({ account, update }: { account: Account; update: (value: Account | null) => void }) {
  const myRequests = usePolling<RequestItem[]>('/api/help/mine', 12000);
  const blocks = usePolling<Profile[]>('/api/help/blocks', 12000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [nicknameDraft, setNicknameDraft] = useState<string>();
  const [nicknameSaved, setNicknameSaved] = useState(false);

  async function save(path: string, body: object, apply: (result: Account) => void) {
    if (busy) return;
    setBusy(true);
    setError('');
    try { apply(await post<Account>(path, body)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : '操作失败。'); }
    finally { setBusy(false); }
  }

  return <>
    <section className="card detail help-form">
      <h1>{account.nickname}</h1>
      {nicknameDraft === undefined ? <button type="button" className="guest-button" disabled={busy} onClick={() => {
        setNicknameSaved(false); setError(''); setNicknameDraft(account.nickname);
      }}>修改昵称</button> : <form onSubmit={(event) => {
        event.preventDefault();
        const nickname = nicknameDraft.trim();
        if (!nickname || nickname === account.nickname) return;
        void save('/api/auth/profile', { nickname }, next => {
          update(next); setNicknameDraft(undefined); setNicknameSaved(true);
        });
      }}>
        <label className="field">公开昵称<input required maxLength={24} autoComplete="nickname" autoFocus value={nicknameDraft}
          disabled={busy} onChange={event => setNicknameDraft(event.target.value)} /></label>
        <div className="help-controls">
          <button className="primary" disabled={busy || !nicknameDraft.trim() || nicknameDraft.trim() === account.nickname}>保存昵称</button>
          <button type="button" className="guest-button" disabled={busy} onClick={() => { setNicknameDraft(undefined); setError(''); }}>取消</button>
        </div>
      </form>}
      {nicknameSaved && <p className="quiet" role="status">昵称已更新。</p>}
      {account.is_admin && <Link className="back" href="/admin">管理公开需求</Link>}
      {account.is_demo && <p className="quiet">这是本浏览器的访客身份。刷新后可继续使用，清除网站数据会失去访问记录的凭证。 <Link href="/login">使用已有账号</Link></p>}
      <h2>附近隐私</h2>
      <label className="help-checkbox"><input type="checkbox" checked={account.share_presence} disabled={busy}
        onChange={(event) => void save('/api/help/preferences', {
          share_presence: event.target.checked, discoverable: account.discoverable,
        }, update)} />参与附近活跃人数统计</label>
      <label className="help-checkbox"><input type="checkbox" checked={account.discoverable} disabled={busy}
        onChange={(event) => void save('/api/help/preferences', {
          share_presence: account.share_presence, discoverable: event.target.checked,
        }, update)} />允许附近用户发现我的公开昵称</label>
      <p className="quiet">开启统计并授权定位后，前台页面才会上报粗略位置。</p>
      {error && <p className="error" role="alert">{error}</p>}
      {!account.is_demo && <button className="guest-button" disabled={busy} onClick={() => void save('/api/auth/logout', {}, () => {
        update(null);
        navigate('/', true);
      })}>退出登录</button>}
    </section>
    <section className="card detail">
      <h2>我参与的需求</h2>
      {myRequests.error && <p role="status">{myRequests.error.message}</p>}
      {myRequests.data?.length === 0 && <p className="quiet">还没有参与过需求。</p>}
      <ul className="hot-list">{myRequests.data?.map((item) => <li key={item.id}>
        <Link href={requestLink(item.id)}>{item.title}</Link> <span className="hot-meta">{statusNames[item.status]}</span>
      </li>)}</ul>
    </section>
    <section className="card detail">
      <h2>已屏蔽账号</h2>
      {blocks.error && <p role="status">{blocks.error.message}</p>}
      {blocks.data?.length === 0 && <p className="quiet">没有已屏蔽的账号。</p>}
      <ul className="hot-list">{blocks.data?.map((profile) => <li className="section-head" key={profile.id}>
        <span>{profile.nickname}</span>
        <button className="guest-button" disabled={busy} onClick={() => void save(
          '/api/help/blocks/' + profile.id, { blocked: false }, () => blocks.refresh(),
        )}>解除屏蔽</button>
      </li>)}</ul>
    </section>
    <Link className="back" href="/archive">查看旧版讨论</Link>
  </>;
}
