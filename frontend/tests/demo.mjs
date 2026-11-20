// Runs against a temporary local database. Never connects to an existing NearHelp server.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm, rmdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { chromium, webkit } from 'playwright-core';
import { preview } from 'vite';
import { verifyModeration } from './moderation.mjs';
import { verifyDiscussionRound } from './discussions.mjs';

const directory = await mkdtemp(join(tmpdir(), 'nearhelp-ui-'));
const db = join(directory, 'demo.sqlite3');
const backend = resolve('../backend');
const python = join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const api = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '0', '--no-access-log', '--no-use-colors'], {
  cwd: backend, windowsHide: true, env: { ...process.env, NEARTALK_DB_PATH: db, NEARHELP_DEMO_GUESTS: 'true' },
  stdio: ['ignore', 'ignore', 'pipe'],
});
const closed = once(api, 'close');
let server, browser;
try {
  const port = await new Promise((accept, reject) => {
    let log = '';
    const timer = setTimeout(() => reject(Error('Local API failed to start. ' + log)), 30000);
    api.stderr.on('data', chunk => {
      log += chunk.toString();
      const port = /Uvicorn running on http:\/\/127\.0\.0\.1:(\d+)/.exec(log);
      if (port) { clearTimeout(timer); accept(port[1]); }
    });
    api.once('error', reject);
    api.once('exit', () => { clearTimeout(timer); reject(Error(log)); });
  });
  process.env.NEARHELP_DEV_API_PORT = port;
  server = await preview({ logLevel: 'error', preview: { host: '127.0.0.1', port: 5319, strictPort: false } });
  const origin = server.resolvedUrls.local[0];
  const useWebKit = process.argv.includes('--webkit');
  browser = await (useWebKit ? webkit.launch() : chromium.launch({ channel: 'chrome' }));
  const position = { latitude: Math.random() * 30, longitude: Math.random() * 30, accuracy: 25 };
  async function phone(width) {
    const context = await browser.newContext({ viewport: { width, height: 740 }, hasTouch: true, isMobile: true,
      geolocation: position, permissions: ['geolocation'], ignoreHTTPSErrors: Boolean(process.env.NEARHELP_DEV_CERT) });
    const page = await context.newPage();
    page.setDefaultTimeout(16000);
    await page.goto(origin);
    await page.getByRole('button', { name: /^邻友·/ }).waitFor();
    return page;
  }
  const button = (p, name) => p.getByRole('button', { name, exact: true });
  const nav = (p, name) => p.getByRole('navigation').getByRole('link', { name, exact: true });
  const exact = (p, value) => p.getByText(value, { exact: true });
  async function checkLayout(page) {
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'horizontal overflow');
    const actionable = page.locator('main :is(button, textarea, input, select):visible').last();
    if (await actionable.count()) {
      await actionable.evaluate(el => el.scrollIntoView({ block: 'center' }));
      assert(await actionable.evaluate(el => {
        const box = el.getBoundingClientRect();
        return box.bottom <= document.querySelector('nav').getBoundingClientRect().top + 1;
      }), 'control covered by navigation');
    }
  }
  const [a, b] = await Promise.all([phone(375), phone(360)]);
  const label = await a.getByRole('button', { name: /^邻友·/ }).innerText();
  assert.notEqual(label, await b.getByRole('button', { name: /^邻友·/ }).innerText());
  for (const p of [a, b]) {
    await p.getByRole('link', { name: 'Around Talk', exact: true }).click();
    await p.getByRole('link', { name: /如果 AI 写了九成代码/ }).click();
  }
  const answer = '调试和承担责任也是作者做的工作。';
  await a.getByLabel('说说我的看法').fill(answer);
  await button(a, '发表看法').click();
  await exact(b, answer).waitFor();
  assert(await b.locator('.talk-answer').first().evaluate(el =>
    Boolean(el.compareDocumentPosition(document.getElementById('discussion-draft')) & Node.DOCUMENT_POSITION_FOLLOWING)));
  await button(b, '赞 0').click();
  await a.getByRole('button', { name: '赞 1', exact: true }).waitFor();
  await button(b, '踩 0').click();
  await a.getByRole('button', { name: '踩 1', exact: true }).waitFor();
  await b.getByRole('button', { name: '踩 1', pressed: true }).click();
  await a.getByRole('button', { name: '踩 0', exact: true }).waitFor();
  await button(b, '回复').click();
  await b.getByLabel('写下回复').fill('我们的队伍也碰到了类似的问题。');
  await button(b, '发送回复').click();
  await exact(a, '我们的队伍也碰到了类似的问题。').waitFor();
  await a.getByText('换个角度想 · AI 视角').click();
  await exact(a, '随本期问题预先生成').waitFor();
  assert.equal(await a.getByRole('link', { name: /知乎相关讨论/ }).count(), 0);
  await checkLayout(a);
  for (const p of [a, b]) await nav(p, '附近').click();
  console.log('PASS: guest venue discovery, answers, cross-device replies and attributed perspectives.');
  for (const p of [a, b]) {
    await p.getByRole('button', { name: /^(获取当前位置|重新定位)$/ }).click();
    await p.getByText(/定位成功 · 精度约/).waitFor();
  }
  const title = '借一个 Type-C 充电器半小时';
  await nav(a, '发布').click();
  await a.getByLabel(/需要什么帮助/).fill(title);
  await a.getByLabel(/具体说明/).fill('希望附近有人可以借我使用。');
  await a.getByLabel('互助方式').selectOption('reward');
  await a.getByLabel(/悬赏金额/).fill('5');
  await a.getByLabel('有效期').selectOption('60');
  await checkLayout(a);
  await button(a, '发布需求').click();
  await a.waitForURL('**/requests/*');
  const detail = a.url();
  await exact(b, title).waitFor();
  await exact(b, '1 条待解决').waitFor();
  await exact(b, '悬赏 HK$5').waitFor();
  await verifyModeration({ backend, python, db, phone, origin, viewer: b, title });
  await b.getByRole('link', { name: '评论 0' }).click();
  const content = '我这里有充电器，可以借给你。';
  await b.getByLabel(/公开评论/).fill(content);
  // Drop one comment request to exercise the actual error and retry UI.
  await b.route('**/replies', route => route.abort(), { times: 1 });
  await button(b, '发表评论').click();
  await b.getByRole('alert').waitFor();
  assert.equal(await b.getByLabel(/公开评论/).inputValue(), content);
  await button(b, '发表评论').click();
  await exact(a, content).waitFor();
  await button(a, '回复').click();
  await a.getByLabel(/^回复 邻友/).fill('好的，你在哪里？');
  await button(a, '发送回复').click();
  await exact(b, '好的，你在哪里？').waitFor();
  await nav(b, '附近').click();
  await b.getByRole('link', { name: '评论 2' }).waitFor();
  await button(b, '我能帮忙').click();
  await exact(b, '已申请，等待对方接受').waitFor();
  await a.getByRole('navigation').getByRole('link', { name: /^消息/ }).click();
  await a.getByRole('link', { name: title }).click();
  await button(a, '接受协助').click();
  await a.getByText(/^进行中/).waitFor();
  await a.getByRole('link', { name: '打开私信' }).click();
  const firstMessage = '我们在图书馆门口见面吧。';
  await a.getByLabel(/私信内容/).fill(firstMessage);
  await button(a, '发送消息').click();
  await b.getByRole('navigation').getByRole('link', { name: /^消息/ }).click();
  await exact(b, '1 条未读').waitFor();
  await b.getByRole('link', { name: new RegExp(title) }).click();
  await exact(b, firstMessage).waitFor();
  await b.getByLabel(/私信内容/).fill('好的，五分钟后到。');
  await button(b, '发送消息').click();
  await exact(a, '好的，五分钟后到。').waitFor();
  await b.reload();
  await exact(b, firstMessage).waitFor();
  await exact(b, '好的，五分钟后到。').waitFor();
  await checkLayout(b);
  await a.goto(detail);
  assert.equal(await a.getByRole('button', { name: /^邻友·/ }).innerText(), label);
  await button(a, '标记已解决').click();
  await exact(a, '已解决').waitFor();
  await exact(a, content).waitFor();
  await nav(b, '附近').click();
  await exact(b, '附近暂时没有待解决的需求。').waitFor();
  await checkLayout(b);
  console.log('PASS: two guest browser sessions, location, reward, comment retry, reply, offer, inbox, accepted chat, reload, resolution and mobile layout.');

  // Only the device callbacks are simulated here. The same UI and local API handle every outcome.
  const faults = await phone(320);
  await faults.addInitScript(() => {
    window.fixCalls = 0;
    window.fixError = 1;
    Object.defineProperty(navigator.geolocation, 'getCurrentPosition', { value(success, failure) {
      window.fixCalls++;
      if (window.fixError) failure({ code: window.fixError });
      else success({ coords: { latitude: 0, longitude: 0, accuracy: 3000 }, timestamp: Date.now() });
    } });
  });
  await faults.reload();
  await button(faults, '获取当前位置').waitFor();
  assert.equal(await faults.evaluate(() => window.fixCalls), 0);
  await button(faults, '获取当前位置').click();
  await faults.getByText(/定位权限被拒绝/).waitFor();
  assert.equal(await faults.evaluate(() => window.fixCalls), 1);
  await faults.getByLabel('浏览区域').selectOption('广州天河');
  await faults.getByRole('link', { name: '发布需求', exact: true }).click();
  await faults.getByLabel(/需要什么帮助/).fill('定位验证');
  await faults.getByLabel(/具体说明/).fill('仅本地运行');
  await button(faults, '发布需求').click();
  await faults.getByText(/请重新获取当前位置后发布/).waitFor();
  await faults.evaluate(() => { window.fixError = 3; });
  await button(faults, '获取当前位置').click();
  await faults.getByText(/定位超时/).waitFor();
  assert.equal(await faults.evaluate(() => window.fixCalls), 3);
  await faults.evaluate(() => { window.fixError = 2; });
  await button(faults, '重新定位').click();
  await faults.getByText(/手机暂时无法获取位置/).waitFor();
  await faults.evaluate(() => { window.fixError = 0; });
  await button(faults, '重新定位').click();
  await faults.getByText(/精度约 3000 米/).waitFor();
  await button(faults, '发布需求').click();
  await faults.getByText(/发布需要 500 米以内/).waitFor();
  await nav(faults, '附近').click();
  await faults.getByText(/精度约 3000 米/).waitFor();
  await checkLayout(faults);
  console.log('PASS: click-to-locate, permission denied, manual browsing, timeout fallback, unavailable and coarse fixes, publish location checks.');
  await verifyDiscussionRound({ backend, python, db, phone, origin });
} finally {
  await browser?.close();
  if (server) {
    server.httpServer.closeAllConnections();
    await new Promise(done => server.httpServer.close(done));
  }
  api.kill();
  await closed;
  for (const suffix of ['', '-wal', '-shm']) await rm(db + suffix, { force: true });
  await rmdir(directory);
}
