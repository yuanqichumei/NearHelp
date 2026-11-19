"""Private text conversations opened only by an accepted help offer."""

import time

from fastapi import APIRouter, HTTPException, Request

from .auth import require_help_user, same_origin
from .db import connect
from .help_requests import RequestId, Text, blocked, throttle


def conversation(connection, request_id, actor):
    item = connection.execute(
        """SELECT c.*,t.title,a.nickname
           FROM help_conversations c JOIN topics t ON t.id=c.request_id
           JOIN accounts a ON a.id=CASE WHEN c.owner_id=? THEN c.helper_id ELSE c.owner_id END
           WHERE c.request_id=? AND (c.owner_id=? OR c.helper_id=?)""",
        (actor, request_id, actor, actor),
    ).fetchone()
    if not item or blocked(connection, item["owner_id"], item["helper_id"]):
        raise HTTPException(404, "找不到这段会话。")
    return item


def messages_router(path):
    router = APIRouter(prefix="/api/help")

    @router.get("/inbox")
    def inbox(request: Request):
        now = time.time()
        with connect(path) as connection:
            actor = require_help_user(connection, request)["id"]
            pending = connection.execute(
                """SELECT o.request_id,t.title,COUNT(*) AS offers FROM help_offers o
                   JOIN help_requests h ON h.topic_id=o.request_id JOIN topics t ON t.id=h.topic_id
                   WHERE h.author_id=? AND h.status='open' AND h.expires_at>? AND o.status='pending'
                     AND NOT EXISTS (SELECT 1 FROM account_blocks b
                        WHERE (b.blocker_id=h.author_id AND b.blocked_id=o.helper_id)
                           OR (b.blocker_id=o.helper_id AND b.blocked_id=h.author_id))
                   GROUP BY o.request_id ORDER BY o.request_id DESC""",
                (actor, now),
            ).fetchall()
            chats = connection.execute(
                """SELECT c.request_id,c.owner_id,c.helper_id,t.title,a.nickname,
                   (SELECT COUNT(*) FROM help_messages m WHERE m.request_id=c.request_id
                        AND m.read_at IS NULL AND m.account_id!=?) AS unread
                   FROM help_conversations c JOIN topics t ON t.id=c.request_id
                   JOIN accounts a ON a.id=CASE WHEN c.owner_id=? THEN c.helper_id ELSE c.owner_id END
                   WHERE c.owner_id=? OR c.helper_id=?
                   ORDER BY coalesce((SELECT MAX(m.id) FROM help_messages m WHERE m.request_id=c.request_id),0) DESC,
                      c.request_id DESC""",
                (actor, actor, actor, actor),
            )
            return {"pending": [dict(row) for row in pending],
                    "chats": [{key: row[key] for key in ("request_id", "title", "nickname", "unread")}
                              for row in chats if not blocked(connection, row["owner_id"], row["helper_id"])]}

    @router.get("/chats/{request_id}")
    def messages(request_id: RequestId, request: Request, before: int | None = None):
        with connect(path) as connection:
            actor = require_help_user(connection, request)["id"]
            item = conversation(connection, request_id, actor)
            rows = connection.execute(
                """SELECT id,account_id=?,content,created_at FROM help_messages
                   WHERE request_id=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT 101""",
                (actor, request_id, before, before),
            ).fetchall()
            return {
                "title": item["title"], "nickname": item["nickname"],
                "peer_id": item["helper_id"] if item["owner_id"] == actor else item["owner_id"],
                "messages": [{"id": row[0], "mine": bool(row[1]), "content": row[2], "created_at": row[3]}
                             for row in reversed(rows[:100])],
                "has_older": len(rows) > 100,
            }

    @router.post("/chats/{request_id}/messages", status_code=201)
    def send(request_id: RequestId, body: Text, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            actor = require_help_user(connection, request)["id"]
            conversation(connection, request_id, actor)
            throttle(connection, request, actor, "message", now, 30)
            message_id = connection.execute(
                "INSERT INTO help_messages (request_id,account_id,content) VALUES (?,?,?)",
                (request_id, actor, body.content),
            ).lastrowid
        return {"id": message_id}

    @router.post("/chats/{request_id}/read/{message_id}", status_code=204)
    def mark_read(request_id: RequestId, message_id: RequestId, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            actor = require_help_user(connection, request)["id"]
            conversation(connection, request_id, actor)
            throttle(connection, request, actor, "read", now, 30)
            connection.execute(
                """UPDATE help_messages SET read_at=?
                   WHERE request_id=? AND account_id!=? AND read_at IS NULL AND id<=?""",
                (now, request_id, actor, message_id),
            )

    return router
