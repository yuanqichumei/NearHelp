import { lazy, Suspense, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { post, usePolling } from './api';
import { Archive } from './Archive';
import { AccountPage, LoginRequired } from './HelpAccount';
import { HelpDetail, PublishPage } from './HelpDetail';
import { HelpFeed } from './HelpFeed';
import { ChatPage, Inbox } from './HelpMessages';
import { useDiscovery, useHelpArea } from './helpApi';
import type { Account, HelpArea, InboxData } from './helpApi';
import { Link, navigate, usePath } from './navigation';
import { Icon } from './ui';
import './style.css';
import { DiscussionList, DiscussionPage, DiscussionEditor } from './Discussions';

const HelpMap = lazy(() => import('./MapPage'));
const AdminRequests = lazy(() => import('./AdminRequests'));

function App() {
  const [account, setAccount] = useState<Account | null>();
  const [authError, setAuthError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const path = usePath();
  const region = useHelpArea(account);
  useEffect(() => {
    let live = true;
    const start = () => post<Account | null>('/api/auth/session', {});
    const session = navigator.locks ? navigator.locks.request('nearhelp-session', start) : start();
    session.then((user) => {
      if (live) setAccount(user);
    }).catch((reason) => {
      if (!live) return;
      setAuthError(reason instanceof Error ? reason.message : '无法读取登录状态。');
    });
    return () => { live = false; };
  }, [attempt]);
  if (authError) return <main className="shell"><p className="notice" role="alert">{authError}</p>
    <button className="primary" onClick={() => { setAuthError(''); setAttempt(attempt + 1); }}>重试连接</button></main>;
  return <Workspace key={account?.id ?? (account === undefined ? 'loading' : 'guest')}
    account={account} update={(next) => { setAccount(next); if (!next) setAttempt(attempt + 1); }} path={path} region={region} />;
}

function Workspace({ account, update, path, region }: {
  account: Account | null | undefined; update: (value: Account | null) => void;
  path: string; region: HelpArea;
}) {
  const [continueTo, setContinueTo] = useState('/');
  const discovery = useDiscovery(region, account === undefined ? undefined : account?.id ?? null,
    path === '/' || path === '/map');
  const inbox = usePolling<InboxData>(account ? '/api/help/inbox' : null, 3000);
  const mine = /^\/requests\/([1-9]\d*)\/?$/.exec(path)?.[1];
  const chat = /^\/messages\/([1-9]\d*)\/?$/.exec(path)?.[1];
  const archiveTopic = /^\/topics\/([1-9]\d*)\/?$/.exec(path)?.[1];
  const archivePlace = /^\/places\/(place-[a-f0-9]{24})(?:\/topics\/([1-9]\d*))?\/?$/.exec(path);
  const unread = inbox.data ? inbox.data.chats.reduce((total, item) => total + item.unread, 0)
    + inbox.data.pending.reduce((total, item) => total + item.offers, 0) : 0;

  function login(next = path) {
    setContinueTo(next === '/account' ? '/' : next);
    navigate('/account');
  }

  let page;
  const discussion = /^\/discussions\/([1-9]\d*)\/?$/.exec(path)?.[1];
  if (path === '/') page = <HelpFeed region={region} data={discovery?.data} error={discovery?.error} account={account} signIn={login} />;
  else if (path === '/discussions') page = <DiscussionList region={region} />;
  else if (discussion) page = <DiscussionPage key={discussion} id={discussion} region={region} account={account} login={login} />;
  else if (path === '/map') page = <Suspense fallback={<p role="status">正在加载地图…</p>}>
    <HelpMap region={region} data={discovery?.data} />
  </Suspense>;
  else if (path === '/archive' || archiveTopic || archivePlace) page = <Archive key={path}
    slug={archivePlace?.[1]} id={archiveTopic ?? archivePlace?.[2]} />;
  else if (account === undefined) page = <p className="notice" role="status">正在准备你的身份…</p>;
  else if (path === '/admin' || path === '/admin/') {
    if (!account || account.is_demo) page = <AccountPage account={null} update={update} returnTo="/admin" adminLogin />;
    else if (account.is_admin) page = <Suspense fallback={<p role="status">正在载入需求管理…</p>}><DiscussionEditor region={region} /><AdminRequests /></Suspense>;
    else page = <section className="notice"><h1>当前账号没有管理权限</h1>
      <Link className="back" href="/account">返回我的账号</Link></section>;
  }
  else if (path === '/account') page = <AccountPage account={account} update={update} returnTo={continueTo} />;
  else if (path === '/login') page = <AccountPage account={null} update={update} returnTo="/" />;
  else if (path === '/publish') page = account ? <PublishPage region={region} />
    : <LoginRequired reason="登录后可以发布需求。" signIn={() => login()} />;
  else if (mine) page = <HelpDetail key={mine} id={mine} account={account} signIn={() => login()} />;
  else if (path === '/messages' || chat) page = !account
    ? <LoginRequired reason="登录后可以查看协助申请和私信。" signIn={() => login()} />
    : chat ? <ChatPage key={chat} id={chat} refreshInbox={inbox.refresh} /> : <Inbox data={inbox.data} error={inbox.error} />;
  else page = <div className="notice"><h1>页面不存在</h1><Link className="back" href="/">返回附近需求</Link></div>;

  return <>
    <header className="site-header">
      <div className="shell topbar">
        <Link className="brand" href="/" aria-label="NearHelp 首页">
          <span className="brand-icon"><Icon name="chat" size={25} /></span><span>NearHelp</span>
        </Link>
        <div className="help-top-right">
          <button className="guest-button" onClick={() => login('/')}>
            <Icon name="person" size={17} />{account ? account.nickname : account === undefined ? '连接中' : '游客 · 登录'}
          </button>
        </div>
      </div>
    </header>
    <main className="shell help-shell">
      {region.sharingError && <p className="notice" role="status">{region.sharingError}</p>}
      {(path === '/' || path === '/discussions') && <div className="discovery-tabs" aria-label="附近内容">
        <Link href="/" aria-current={path === '/' ? 'page' : undefined}>附近求助</Link>
        <Link href="/discussions" aria-current={path === '/discussions' ? 'page' : undefined}>附近讨论</Link>
      </div>}
      {page}
    </main>
    <nav className="help-nav" aria-label="主导航">
      <div className="shell">
        <Link href="/" aria-current={path === '/' || path === '/map' || path.startsWith('/discussions') ? 'page' : undefined}><Icon name="pin" />附近</Link>
        <Link href="/publish" aria-current={path === '/publish' ? 'page' : undefined}><Icon name="plus" />发布</Link>
        <Link href="/messages" aria-current={path.startsWith('/messages') ? 'page' : undefined}>
          <Icon name="chat" />消息{unread > 0 && <span className="help-unread" aria-label={unread + ' 条待处理消息'}>{unread}</span>}
        </Link>
        <Link href="/account" aria-current={path === '/account' || path.startsWith('/admin') ? 'page' : undefined}><Icon name="person" />我的</Link>
      </div>
    </nav>
  </>;
}

createRoot(document.getElementById('root')!).render(<App />);
