import logging
import os
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .db import DEFAULT_COMMUNITY, connect
from .zhihu import ZhihuError, fetch_hot_list

ZHIHU = "zhihu"
MANUAL = "manual"
logger = logging.getLogger(__name__)


def save_hot_topic(connection, community, source, title, original_url, rank=None):
    title = title.strip()
    link = urlsplit(original_url)
    if (not title or link.scheme not in {"https", "http"} or not link.hostname or link.username is not None
            or any(character.isspace() or ord(character) < 32 for character in original_url)):
        raise ValueError("需要提供标题和有效的 HTTP(S) 原文链接")
    query = urlencode(sorted((key, value) for key, value in parse_qsl(link.query, keep_blank_values=True)
                             if not key.lower().startswith("utm_")))
    url_key = urlunsplit(("", link.netloc.lower(), link.path.rstrip("/"), query, ""))
    existing = connection.execute(
        "SELECT topic_id FROM hot_topics WHERE community_slug = ? AND source = ? AND url_key = ?",
        (community, source, url_key),
    ).fetchone()
    if existing:
        topic_id = existing["topic_id"]
        connection.execute("UPDATE topics SET title = ? WHERE id = ?", (title, topic_id))
        connection.execute("UPDATE hot_topics SET original_url = ?, rank = ? WHERE topic_id = ?",
                           (original_url, rank, topic_id))
    else:
        topic_id = connection.execute(
            """INSERT INTO topics (community_slug, guest_id, nickname, title, content)
               VALUES (?, '', '社会热榜', ?, '')""",
            (community, title),
        ).lastrowid
        connection.execute(
            "INSERT INTO hot_topics VALUES (?, ?, ?, ?, ?, ?)",
            (topic_id, community, source, url_key, original_url, rank),
        )
    return topic_id


def refresh_zhihu(path, community, ttl):
    now = time.time()
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        state = connection.execute(
            "SELECT fetched_at, retry_after FROM hot_cache WHERE community_slug = ? AND source = ?",
            (community, ZHIHU),
        ).fetchone()
        if state and (state["retry_after"] > now or (state["fetched_at"] or 0) + ttl > now):
            return
        connection.execute(
            """INSERT INTO hot_cache VALUES (?, ?, NULL, ?)
               ON CONFLICT (community_slug, source) DO UPDATE SET retry_after = excluded.retry_after""",
            (community, ZHIHU, now + 120),
        )

    try:
        hot_list = fetch_hot_list()
    except ZhihuError:
        # Preserve the last successful snapshot and avoid retrying on every poll.
        logger.warning("Zhihu hot-list refresh failed")
        return
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE hot_topics SET rank = NULL WHERE community_slug = ? AND source = ?",
                           (community, ZHIHU))
        for rank, item in enumerate(hot_list.items):
            save_hot_topic(connection, community, ZHIHU, item.title, item.url, rank)
        connection.execute("UPDATE hot_cache SET fetched_at = ?, retry_after = 0 WHERE community_slug = ? AND source = ?",
                           (time.time(), community, ZHIHU))


def list_hot_topics(path, community=DEFAULT_COMMUNITY):
    try:
        ttl = max(1, int(os.environ.get("ZHIHU_CACHE_TTL", "1800")))
    except ValueError:
        ttl = 1800
    enabled = bool(os.environ.get("ZHIHU_ACCESS_SECRET", "").strip())
    if enabled:
        refresh_zhihu(path, community, ttl)
    with connect(path) as connection:
        rows = connection.execute(
            """SELECT h.topic_id, h.source, t.title, h.original_url,
                      (SELECT COUNT(*) FROM comments c WHERE c.topic_id = t.id) AS comment_count
               FROM hot_topics h JOIN topics t ON t.id = h.topic_id
               LEFT JOIN hot_cache s ON s.community_slug = h.community_slug AND s.source = h.source
               WHERE h.community_slug = ?
                 AND (h.source = ? OR (? AND h.rank IS NOT NULL AND s.fetched_at >= ?))
               ORDER BY h.source = ? DESC, h.rank, t.id DESC""",
            (community, MANUAL, enabled, time.time() - 2 * ttl, MANUAL),
        )
        return [dict(row) for row in rows]
