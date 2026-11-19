"""Verify a deployed API with isolated temporary test content."""
import sqlite3
import subprocess
import time
from uuid import uuid4

import httpx

base = 'https://hacker.guihongyu.com/api/communities/cityu-hackathon/topics'
alice = {'guest_id': str(uuid4()), 'nickname': '部署验收甲'}
bob = {'guest_id': str(uuid4()), 'nickname': '部署验收乙'}
topic_id = None
try:
    with httpx.Client(timeout=15) as a, httpx.Client(timeout=15) as b:
        response = a.post(base, json={**alice, 'title': '部署验收临时话题', 'content': '验证跨客户端发布与持久化'})
        response.raise_for_status()
        topic_id = response.json()['id']
        assert any(t['id'] == topic_id for t in b.get(base).json())
        detail = f'{base}/{topic_id}'
        response = b.post(detail + '/comments', json={**bob, 'content': '<b>纯文本回复</b>'})
        response.raise_for_status()
        assert a.get(detail).json()['comments'][0]['content'] == '<b>纯文本回复</b>'
        subprocess.run(['systemctl', 'restart', 'neartalk'], check=True)
        for attempt in range(20):
            time.sleep(0.5)
            response = a.get(detail)
            if response.status_code == 200:
                break
        response.raise_for_status()
        assert len(response.json()['comments']) == 1
        print('PASS: HTTPS, independent client topic/comment writes, service restart persistence')
finally:
    with sqlite3.connect('/var/lib/neartalk/neartalk.sqlite3') as connection:
        if topic_id is not None:
            connection.execute('DELETE FROM comments WHERE topic_id = ? AND guest_id = ?', (topic_id, bob['guest_id']))
            connection.execute('DELETE FROM topics WHERE id = ? AND guest_id = ?', (topic_id, alice['guest_id']))
        connection.execute('DELETE FROM write_events WHERE guest_id IN (?, ?)', (alice['guest_id'], bob['guest_id']))
