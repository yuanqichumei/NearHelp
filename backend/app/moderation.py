"""Moderate public NearHelp requests using a locally provisioned account."""

import time
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .auth import require_help_user, same_origin
from .db import connect
from .help_requests import RequestId, effective_state, pinned, throttle

PIN_SECONDS = 12 * 3600
PAGE_SIZE = 40


class ModerationAction(BaseModel):
    action: Literal["hide", "restore", "pin", "unpin"]


class AnswerAction(BaseModel):
    action: Literal["hide", "restore"]


def require_admin(connection, request):
    actor = require_help_user(connection, request)
    if actor["is_demo"] or not actor["is_admin"]:
        raise HTTPException(403, "需要管理员权限。")
    return actor


def moderation_router(path):
    router = APIRouter(prefix="/api/admin")

    @router.get("/requests")
    def requests(request: Request, visibility: Literal["all", "visible", "hidden"] = "all",
                 before: Annotated[int, Query(gt=0, le=2**63 - 1)] | None = None):
        now = time.time()
        filters = {"all": "1", "visible": "h.hidden_at IS NULL", "hidden": "h.hidden_at IS NOT NULL"}
        with connect(path) as connection:
            require_admin(connection, request)
            rows = connection.execute(
                f"""SELECT h.topic_id AS id,t.title,t.content,t.nickname,t.created_at,h.status,
                         h.expires_at,h.hidden_at,h.pinned_until,
                         (SELECT COUNT(*) FROM help_reports r WHERE r.request_id=h.topic_id) AS report_count
                    FROM help_requests h JOIN topics t ON t.id=h.topic_id
                    WHERE {filters[visibility]} AND (? IS NULL OR h.topic_id<?)
                    ORDER BY h.topic_id DESC LIMIT ?""",
                (before, before, PAGE_SIZE + 1),
            ).fetchall()
        items = []
        for row in rows[:PAGE_SIZE]:
            item = {key: row[key] for key in ("id", "title", "content", "nickname", "created_at", "expires_at", "report_count")}
            is_pinned = pinned(row, now)
            items.append({**item, "is_hidden": row["hidden_at"] is not None, "is_pinned": is_pinned,
                          "status": effective_state(row, now), "pinned_until": row["pinned_until"] if is_pinned else None})
        return {"items": items, "next_before": items[-1]["id"] if len(rows) > PAGE_SIZE else None}

    @router.post("/requests/{request_id}", status_code=204)
    def moderate(request_id: RequestId, body: ModerationAction, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            actor = require_admin(connection, request)
            throttle(connection, request, actor["id"], "moderate", now, 30)
            row = connection.execute("SELECT status,expires_at,hidden_at FROM help_requests WHERE topic_id=?",
                                     (request_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "找不到这个需求。")
            if body.action == "pin":
                if row["hidden_at"] is not None or effective_state(row, now) != "open":
                    raise HTTPException(409, "只能置顶可见且仍在等待帮助的需求。")
                until = min(row["expires_at"], now + PIN_SECONDS)
                connection.execute("UPDATE help_requests SET pinned_until=? WHERE topic_id=?", (until, request_id))
            elif body.action == "hide":
                connection.execute("UPDATE help_requests SET hidden_at=coalesce(hidden_at,?),pinned_until=NULL WHERE topic_id=?",
                                   (now, request_id))
            elif body.action == "restore":
                connection.execute("UPDATE help_requests SET hidden_at=NULL WHERE topic_id=?", (request_id,))
            else:
                connection.execute("UPDATE help_requests SET pinned_until=NULL WHERE topic_id=?", (request_id,))

    @router.get("/discussion-answers")
    def answers(request: Request, visibility: Literal["all", "visible", "hidden"] = "all",
                before: Annotated[int, Query(gt=0, le=2**63 - 1)] | None = None):
        visible = "own.comment_id IS NULL AND parent.comment_id IS NULL"
        filters = {"visible": visible, "hidden": f"NOT ({visible})", "all": "1"}
        with connect(path) as connection:
            require_admin(connection, request)
            rows = connection.execute(f"""SELECT c.id,c.content,c.nickname,c.created_at,
                    c.parent_id,t.title,d.venue,own.comment_id IS NOT NULL AS hidden,
                    parent.comment_id IS NOT NULL AS parent_hidden
                FROM comments c JOIN discussion_rounds d ON d.topic_id=c.topic_id
                JOIN topics t ON t.id=c.topic_id
                LEFT JOIN discussion_hidden own ON own.comment_id=c.id
                LEFT JOIN discussion_hidden parent ON parent.comment_id=c.parent_id
                WHERE ({filters[visibility]}) AND (? IS NULL OR c.id<?)
                ORDER BY c.id DESC LIMIT ?""", (before, before, PAGE_SIZE+1)).fetchall()
            return {"items": [dict(row) for row in rows[:PAGE_SIZE]],
                    "next_before": rows[PAGE_SIZE-1]["id"] if len(rows)>PAGE_SIZE else None}

    @router.post("/discussion-answers/{comment_id}", status_code=204)
    def moderate_answer(comment_id: RequestId, body: AnswerAction, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            actor = require_admin(connection, request)
            throttle(connection, request, actor["id"], "moderate", now, 30)
            if not connection.execute("""SELECT 1 FROM comments c JOIN discussion_rounds d
                    ON d.topic_id=c.topic_id WHERE c.id=?""", (comment_id,)).fetchone():
                raise HTTPException(404, "找不到这条讨论发言。")
            if body.action == "hide":
                connection.execute("INSERT OR IGNORE INTO discussion_hidden(comment_id,hidden_at) VALUES (?,?)",
                                   (comment_id, now))
            else:
                connection.execute("DELETE FROM discussion_hidden WHERE comment_id=?", (comment_id,))

    return router
