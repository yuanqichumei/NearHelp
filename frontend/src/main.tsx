import { lazy, Suspense, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, usePolling } from './api';
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

const HelpMap = lazy(() => import('./MapPage'));

function App() {
  const [account, setAccount] = useState<Account | null>();
  const [authError, setAuthError] = useState('');
  const path = usePath();
  const region = useHelpArea(account);
  useEffect(() => {
    let live = true;
    api<Account | null>('/api/auth/me').then((user) => {
      if (live) setAccount(user);
    }).catch((reason) => {
      if (!live) return;
      setAuthError(reason instanceof Error ? reason.message : '无法读取登录状态。');
      setAccount(null);
    });
    return () => { live = false; };
  }, []);
  return <Workspace key={account?.id ?? (account === undefined ? 'loading' : 'guest')}
    account={account} update={setAccount} path={path} region={region} authError={authError} />;
}

function Workspace({ account, update, path, region, authError }: {
  account: Account | null | undefined; update: (value: Account | null) => void;
  path: string; region: HelpArea; authError: string;
}) {
  const [continueTo, setContinueTo] = useState('/');
  const discovery = useDiscovery(region, account === undefined ? undefined : account?.id ?? null,
    path === '/' || path === '/map');
  const inbox = usePolling<InboxData>(account ? '/api/help/inbox' : null, 7000);
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
  if (path === '/') page = <HelpFeed region={region} data={discovery?.data} error={discovery?.error} signedIn={!!account} />;
  else if (path === '/map') page = <Suspense fallback={<p role="status">正在加载地图…</p>}>
    <HelpMap region={region} data={discovery?.data} />
  </Suspense>;
  else if (path === '/archive' || archiveTopic || archivePlace) page = <Archive key={path}
    slug={archivePlace?.[1]} id={archiveTopic ?? archivePlace?.[2]} />;
  else if (account === undefined) page = <p className="notice" role="status">正在读取登录状态…</p>;
  else if (path === '/account') page = <AccountPage account={account} update={update} returnTo={continueTo} />;
  else if (path === '/publish') page = account ? <PublishPage onPosition={region.usePosition} />
    : <LoginRequired reason="登录后可以发布免费需求。" signIn={login} />;
  else if (mine) page = <HelpDetail key={mine} id={mine} account={account} signIn={login} />;
  else if (path === '/messages' || chat) page = !account
    ? <LoginRequired reason="登录后可以查看协助申请和私信。" signIn={login} />
    : chat ? <ChatPage key={chat} id={chat} refreshInbox={inbox.refresh} /> : <Inbox data={inbox.data} error={inbox.error} />;
  else page = <div className="notice"><h1>页面不存在</h1><Link className="back" href="/">返回附近需求</Link></div>;

  return <>
    <header className="site-header">
      <div className="shell topbar">
        <Link className="brand" href="/" aria-label="NearTalk 首页">
          <span className="brand-icon"><Icon name="chat" size={25} /></span><span>NearTalk</span>
        </Link>
        <div className="help-top-right">
          <span className="help-top-area">{region.area.name}</span>
          <button className="guest-button" onClick={() => login('/')}>
            <Icon name="person" size={17} />{account ? account.nickname : '游客 · 登录'}
          </button>
        </div>
      </div>
    </header>
    <main className="shell help-shell">
      {authError && <p className="notice" role="status">{authError}</p>}
      {region.sharingError && <p className="notice" role="status">{region.sharingError}</p>}
      {page}
    </main>
    <nav className="help-nav" aria-label="主导航">
      <div className="shell">
        <Link href="/" aria-current={path === '/' || path === '/map' ? 'page' : undefined}>附近</Link>
        <Link href="/publish" aria-current={path === '/publish' ? 'page' : undefined}>发布</Link>
        <Link href="/messages" aria-current={path.startsWith('/messages') ? 'page' : undefined}>
          消息{unread > 0 && <span className="help-unread" aria-label={unread + ' 条待处理消息'}>{unread}</span>}
        </Link>
        <Link href="/account" aria-current={path === '/account' ? 'page' : undefined}>我的</Link>
      </div>
    </nav>
  </>;
}

createRoot(document.getElementById('root')!).render(<App />);
