import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { spawnSync } from 'node:child_process';

// Only called with the local preview server and temporary SQLite file created by demo.mjs.
export async function verifyDiscussionRound({ backend, python, db, phone, origin }) {
  const guests = [];
  let admin;
  try {
    const venuePosition = spawnSync(python, ['-c',
      'import sqlite3,sys,json; print(json.dumps(sqlite3.connect(sys.argv[1]).execute("SELECT lat,lon FROM discussion_rounds WHERE active=1 ORDER BY topic_id LIMIT 1").fetchone()))',
      db], { cwd: backend, windowsHide: true, encoding: 'utf8' });
    assert.equal(venuePosition.status, 0, venuePosition.stderr);
    const [latitude, longitude] = JSON.parse(venuePosition.stdout);
    const answers = ['代码生成以后仍要有人检查和维护。', '我们遇到的问题来自需求本身。', '现场测试让我理解了用户的选择。'];
    for (const [index, text] of answers.entries()) {
      const page = await phone(index === 0 ? 320 : 375);
      guests.push(page);
      await page.context().setGeolocation({ latitude, longitude, accuracy: 20 });
      await page.getByRole('link', { name: 'Around Talk', exact: true }).click();
      await page.getByRole('link', { name: /如果 AI 写了九成代码/ }).click();
      assert.equal(await page.locator('.talk-composer').getByRole('checkbox').count(), 0);
      await page.getByLabel('说说我的看法').fill(text);
      await page.getByRole('button', { name: '发表看法', exact: true }).click();
      await page.locator('.talk-answer').getByText(text, { exact: true }).waitFor();
    }
    const viewer = guests[0];
    await viewer.bringToFront();
    await viewer.getByText(/从 3 位附近参与者的回答中摘录/).waitFor();
    assert.equal(await viewer.getByRole('button', { name: '查看原回答' }).count(), 3);
    const first = viewer.locator('blockquote').first();
    const quote = await first.evaluate(el => el.firstChild.textContent.trim());
    await first.getByRole('button', { name: '查看原回答' }).click();
    assert((await viewer.locator(':focus').innerText()).includes(quote));
    assert(await viewer.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const oldUrl = viewer.url();

    const account = 'agenda_editor';
    const password = randomBytes(24).toString('base64url');
    const created = spawnSync(python, ['-m', 'app.create_admin', '--db', db, '--username', account, '--password-stdin'],
      { cwd: backend, windowsHide: true, input: password + '\n', encoding: 'utf8' });
    assert.equal(created.status, 0, created.stderr);
    admin = await phone(320);
    await admin.goto(new URL('/admin', origin).href);
    await admin.getByLabel('账号', { exact: true }).fill(account);
    await admin.getByLabel('密码', { exact: true }).fill(password);
    await admin.getByRole('button', { name: '登录', exact: true }).click();
    await admin.getByText('管理讨论发言', { exact: true }).click();
    const answerItem = admin.getByRole('listitem').filter({ hasText: answers[0] });
    admin.once('dialog', dialog => dialog.accept());
    await answerItem.getByRole('button', { name: '下架发言' }).click();
    await viewer.bringToFront();
    await viewer.locator('.talk-answer').getByText(answers[0], { exact: true }).waitFor({ state: 'hidden' });
    await viewer.getByText(/至少 3 位附近参与者/).waitFor();
    await admin.getByRole('combobox', { name: /^发言范围/ }).selectOption('hidden');
    await answerItem.getByRole('button', { name: '恢复发言' }).click();
    await viewer.bringToFront();
    await viewer.getByText(/从 3 位附近参与者的回答中摘录/).waitFor();
    await admin.getByText('管理讨论发言', { exact: true }).click();
    await admin.getByText('管理讨论话题', { exact: true }).click();
    const newTopic = '本次黑客松，你觉得哪个作品更好？';
    const topicItem = admin.getByRole('listitem').filter({ hasText: newTopic });
    await topicItem.getByRole('button', { name: /置顶（/ }).click();
    await topicItem.getByRole('button', { name: '取消置顶' }).waitFor();
    const talkList = await phone(320);
    guests.push(talkList);
    await talkList.getByRole('link', { name: 'Around Talk', exact: true }).click();
    const firstCard = talkList.locator('.talk-feature').first();
    await firstCard.getByText(newTopic, { exact: true }).waitFor();
    await firstCard.getByText('置顶', { exact: true }).waitFor();
    admin.once('dialog', dialog => dialog.accept());
    await topicItem.getByRole('button', { name: '下架' }).click();
    await talkList.getByText(newTopic, { exact: true }).waitFor({ state: 'hidden' });
    await topicItem.getByRole('button', { name: '恢复公开' }).click();
    await talkList.getByText(newTopic, { exact: true }).waitFor();
    await admin.getByText('管理讨论话题', { exact: true }).click();
    await admin.getByText('管理会场一问', { exact: true }).click();
    const selectVenue = admin.getByRole('combobox', { name: /^会场/ });
    const question = admin.getByRole('combobox', { name: /^本期问题/ });
    await question.selectOption('learning');
    await admin.getByLabel(/知乎问题或回答链接/).fill('');
    await admin.getByRole('button', { name: '保存本期问题' }).click();
    await admin.getByText(/已更新「香港城市大学」/).waitFor();
    await viewer.getByText(/往期讨论/).waitFor();
    assert.equal(await viewer.getByLabel('说说我的看法').count(), 0);
    await viewer.getByRole('link', { name: '返回附近讨论' }).click();
    await viewer.getByRole('link', { name: /有了 AI，学编程还应该/ }).click();
    assert.notEqual(viewer.url(), oldUrl);
    assert.equal(await viewer.getByRole('link', { name: /知乎相关讨论/ }).count(), 0);

    await selectVenue.selectOption('@new');
    await admin.getByLabel('公开会场名称').fill('临时测试会场');
    await admin.getByLabel('浏览区域').selectOption('广州天河');
    await question.selectOption('tools');
    const overflow = await admin.evaluate(() => [...document.querySelectorAll('main *')]
      .filter(el => el.getBoundingClientRect().right > innerWidth + 1)
      .map(el => el.tagName + '.' + el.className + ' ' + Math.round(el.getBoundingClientRect().right)));
    assert.deepEqual(overflow, [], '会场编辑表单存在横向溢出：' + overflow.join(', '));
    assert(await admin.evaluate(() => document.documentElement.scrollWidth <= innerWidth), '会场编辑表单可横向滚动');
    await admin.getByRole('button', { name: '保存本期问题' }).click();
    await admin.getByText(/已更新「临时测试会场」/).waitFor();
    await selectVenue.selectOption('香港城市大学');
    assert.equal(await question.inputValue(), 'learning');
    await selectVenue.selectOption('临时测试会场');
    assert.equal(await question.inputValue(), 'tools');
    await viewer.getByRole('link', { name: '返回附近讨论' }).click();
    assert.equal(await viewer.getByText(/临时测试会场/).count(), 0);
    await viewer.locator('.region-toggle').click();
    await viewer.getByLabel('浏览区域').selectOption('广州天河');
    await viewer.getByRole('link', { name: /临时测试会场/ }).click();
    await viewer.getByRole('heading', { name: /哪一步交给 AI/ }).waitFor();
    console.log('PASS: automatic local contribution, citations, hide and restore, 320px layout, venue creation, question rotation, archived read-only thread and per-venue discovery.');
  } finally {
    if (admin) await admin.context().close();
    await Promise.all(guests.map(page => page.context().close()));
  }
}
