import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';

// The caller always creates its own temporary SQLite database and local preview server.
export async function verifyModeration({ backend, python, db, phone, origin, viewer, title }) {
  const account = 'test_moderator';
  const password = randomBytes(24).toString('base64url');
  const created = spawnSync(python, ['-m', 'app.create_admin', '--db', db, '--username', account, '--password-stdin'],
    { cwd: backend, windowsHide: true, input: password + '\n', encoding: 'utf8' });
  assert.equal(created.status, 0, created.stderr);
  const admin = await phone(360);
  try {
    const denied = await admin.request.get(new URL('/api/admin/requests', origin).href);
    assert.equal(denied.status(), 403);
    await admin.goto(new URL('/admin', origin).href);
    await admin.getByRole('heading', { name: '管理员登录' }).waitFor();
    await admin.getByLabel('账号', { exact: true }).fill(account);
    await admin.getByLabel('密码', { exact: true }).fill(password);
    await admin.getByRole('button', { name: '登录', exact: true }).click();
    const item = admin.getByRole('listitem').filter({ has: admin.getByRole('heading', { name: title, exact: true }) });
    await item.getByRole('button', { name: /^置顶/ }).click();
    const badge = viewer.getByRole('listitem').filter({ hasText: title }).getByText('置顶', { exact: true });
    await badge.waitFor();
    await item.getByRole('button', { name: '取消置顶' }).click();
    await badge.waitFor({ state: 'hidden' });
    admin.once('dialog', dialog => dialog.accept());
    await item.getByRole('button', { name: '下架' }).click();
    await viewer.getByText(title, { exact: true }).waitFor({ state: 'hidden' });
    await admin.getByLabel('显示范围').selectOption('hidden');
    await item.getByRole('button', { name: '恢复公开' }).click();
    await viewer.getByText(title, { exact: true }).waitFor();
    await admin.reload();
    await item.getByRole('button', { name: /^置顶/ }).waitFor();
    const profile = admin.getByRole('navigation').getByRole('link', { name: '我的', exact: true });
    await profile.click();
    await admin.getByRole('link', { name: '管理公开需求' }).waitFor();
    console.log('PASS: guest/admin separation, moderator login, local pin/unpin, hide/filter/restore, session persistence.');
  } finally {
    await admin.context().close();
  }
}
