"""Public venue questions and attributed extracts from nearby answers."""
import re
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, StringConstraints

from .auth import current_help_user, require_help_user, same_origin
from .db import connect
from .discussion_catalog import QUESTIONS, feature
from .discussion_insights import cached_insights, refresh_insights
from .help_requests import Discovery, Fix, NewComment, RequestId, throttle
from .location import Point, distance
from .moderation import require_admin


class AnswerLocation(Fix):
    timestamp: Annotated[float, Field(allow_inf_nan=False)]  # Unix seconds


class Answer(NewComment):
    location: AnswerLocation | None = None
    theme: str = Field(default="", max_length=16)
    ai_consent: bool = False


class InsightQuery(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]


class Selection(Point):
    venue: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    question: str = Field(max_length=32)
    zhihu_url: str = Field(default="", max_length=200)
    expected_topic_id: RequestId | None = None


VISIBLE = """NOT EXISTS (SELECT 1 FROM account_blocks b WHERE
    (b.blocker_id=:viewer AND b.blocked_id=c.guest_id) OR
    (b.blocked_id=:viewer AND b.blocker_id=c.guest_id))
    AND NOT EXISTS (SELECT 1 FROM comments parent JOIN account_blocks b ON
       ((b.blocker_id=:viewer AND b.blocked_id=parent.guest_id) OR
        (b.blocked_id=:viewer AND b.blocker_id=parent.guest_id))
       WHERE parent.id=c.parent_id)
    AND NOT EXISTS (SELECT 1 FROM discussion_hidden h WHERE h.comment_id IN (c.id, c.parent_id))"""
ROUND = """SELECT d.*,t.title FROM discussion_rounds d JOIN topics t ON t.id=d.topic_id"""


def viewer_id(db, request):
    actor = current_help_user(db, request)
    return actor["id"] if actor else None


def local_sources(db, topic_id, viewer):
    return db.execute(f"""SELECT id,content,theme,ai_consent FROM (
        SELECT c.id,c.content,s.theme,a.comment_id IS NOT NULL AS ai_consent,
            row_number() OVER (PARTITION BY c.guest_id ORDER BY c.id DESC) AS n
        FROM comments c JOIN discussion_local l ON c.id=l.comment_id
        LEFT JOIN discussion_themes s ON s.comment_id=c.id
        LEFT JOIN discussion_ai_consent a ON a.comment_id=c.id
        WHERE c.topic_id=:id AND c.parent_id IS NULL AND length(trim(c.content))>=6 AND {VISIBLE}
        ) WHERE n=1 ORDER BY id DESC LIMIT 80""", {"id": topic_id, "viewer": viewer}).fetchall()


def summary(rows):
    # Pick a substantive passage from each author. Prefer varied wording across the three excerpts.
    candidates = []
    themes = {}
    for row in rows:
        passage = row["content"].strip()
        chars = re.sub(r"\W", "", passage.casefold())
        if len(chars) < 6:
            continue
        grams = set(zip(chars, chars[1:]))
        if row["theme"]:
            item = themes.setdefault(row["theme"], {"label": row["theme"], "people": 0, "comment_id": row["id"]})
            item["people"] += 1
        candidates.append((row["id"], passage, grams))
    count = len(candidates)
    extracts = []
    covered = set()
    while count >= 3 and candidates and len(extracts) < 3:
        choice = max(candidates, key=lambda c: len(c[2] - covered) / len(c[2]))
        candidates.remove(choice)
        if not choice[2] - covered:
            break
        extracts.append({"comment_id": choice[0], "text": choice[1]})
        covered.update(choice[2])
    return {"contributors": count if count >= 3 else 0, "extracts": extracts,
            "themes": list(themes.values()) if count >= 3 else []}


def discussion_router(path):
    router = APIRouter(prefix="/api/discussions")

    @router.get("/catalog")
    def catalog(request: Request):
        with connect(path) as db:
            require_admin(db, request)
            venues = [dict(row) for row in db.execute(
                "SELECT topic_id,venue,question_key,zhihu_url FROM discussion_rounds WHERE active=1 ORDER BY venue")]
        return {"questions": [{"key": k, "title": v["title"], "url": v["url"]} for k, v in QUESTIONS.items()],
                "venues": venues}

    @router.post("/feature")
    def select(body: Selection, request: Request):
        same_origin(request)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            admin = require_admin(db, request)
            throttle(db, request, admin["id"], "discussion-select", time.time(), 20)
            if body.question not in QUESTIONS:
                raise HTTPException(422, "请选择题库中的问题。")
            if body.zhihu_url and not re.fullmatch(r"https://(?:www\.)?zhihu\.com/question/[0-9]+(?:/answer/[0-9]+)?/?", body.zhihu_url):
                raise HTTPException(422, "请填写知乎问题或回答的 HTTPS 原文链接。")
            current = db.execute("SELECT topic_id FROM discussion_rounds WHERE venue=? AND active=1", (body.venue,)).fetchone()
            if body.expected_topic_id != (current[0] if current else None):
                raise HTTPException(409, "会场已存在或本期题目已更新，请重新选择会场再保存。")
            return {"id": feature(db, body.venue, body.lat, body.lon, body.question, body.zhihu_url)}

    @router.post("/nearby")
    def nearby(body: Discovery, request: Request):
        with connect(path) as db:
            actor = viewer_id(db, request)
            venues = []
            for row in db.execute(ROUND + " WHERE d.active=1 AND d.lat BETWEEN ? AND ?",
                                  (body.lat - .04, body.lat + .04)):
                meters = distance(row["lat"], row["lon"], body.lat, body.lon)
                if meters <= body.radius:
                    total = db.execute(f"SELECT count(*) FROM comments c WHERE c.topic_id=:id AND {VISIBLE}",
                                       {"id": row["topic_id"], "viewer": actor}).fetchone()[0]
                    venues.append((meters, {"id": row["topic_id"], "title": row["title"], "venue": row["venue"], "count": total}))
            return [item for _, item in sorted(venues, key=lambda x: (x[0], x[1]["id"]))]

    @router.get("/{topic_id}")
    def detail(topic_id: RequestId, request: Request, before: Annotated[int, Query(gt=0, le=2**63-1)] | None = None):
        with connect(path) as db:
            db.execute("BEGIN")
            row = db.execute(ROUND + " WHERE d.topic_id=?", (topic_id,)).fetchone()
            if not row:
                raise HTTPException(404, "找不到这场讨论。")
            args = {"id": topic_id, "viewer": viewer_id(db, request), "before": before}
            rows = db.execute(f"""SELECT c.id,c.content,c.nickname,c.created_at,c.parent_id
                FROM comments c WHERE c.topic_id=:id AND {VISIBLE} AND (:before IS NULL OR c.id<:before)
                ORDER BY c.id DESC LIMIT 51""", args).fetchall()
            sources = local_sources(db, topic_id, args["viewer"])
            return {"id": topic_id, "title": row["title"], "venue": row["venue"], "active": bool(row["active"]),
                    "angle": QUESTIONS[row["question_key"]]["angle"], "zhihu_url": row["zhihu_url"],
                    "themes": QUESTIONS[row["question_key"]]["themes"],
                    "answers": [dict(r) for r in rows[:50]], "older": rows[49]["id"] if len(rows)>50 else None,
                    "summary": summary(sources), "insights": cached_insights(db, topic_id, sources)}

    @router.post("/{topic_id}/insights")
    def update_insights(topic_id: RequestId, body: InsightQuery, request: Request):
        same_origin(request)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            admin = require_admin(db, request)
            throttle(db, request, admin["id"], "discussion-insights", time.time(), 3)
            row = db.execute(ROUND + " WHERE d.topic_id=?", (topic_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "找不到这场讨论。")
            sources = local_sources(db, topic_id, None)
        return refresh_insights(path, topic_id, row["title"], body.query, sources)

    @router.post("/{topic_id}/answers", status_code=201)
    def answer(topic_id: RequestId, body: Answer, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            account = require_help_user(db, request)
            row = db.execute("SELECT * FROM discussion_rounds WHERE topic_id=?", (topic_id,)).fetchone()
            if not row:
                raise HTTPException(404, "找不到这场讨论。")
            if not row["active"]:
                raise HTTPException(409, "本期讨论已结束，可以继续阅读。")
            if body.theme and body.theme not in QUESTIONS[row["question_key"]]["themes"]:
                raise HTTPException(422, "请选择本话题的关注点。")
            throttle(db, request, account["id"], "discussion-answer", now, 12)
            if body.parent_id is not None and not db.execute(f"""SELECT 1 FROM comments c WHERE c.topic_id=:id
                AND c.id=:parent AND c.parent_id IS NULL AND {VISIBLE}""",
                {"id": topic_id, "parent": body.parent_id, "viewer": account["id"]}).fetchone():
                raise HTTPException(422, "请选择本话题下的一条回答进行回复。")
            cid = db.execute("INSERT INTO comments(topic_id,parent_id,guest_id,nickname,content) VALUES (?,?,?,?,?)",
                             (topic_id, body.parent_id, account["id"], account["nickname"], body.content)).lastrowid
            loc = body.location
            if loc and -10 <= now-loc.timestamp <= 300 and distance(loc.lat, loc.lon, row["lat"], row["lon"]) <= 1000:
                db.execute("INSERT INTO discussion_local VALUES (?)", (cid,))
                if body.ai_consent and body.parent_id is None:
                    db.execute("INSERT INTO discussion_ai_consent VALUES (?)", (cid,))
                if body.theme and body.parent_id is None:
                    db.execute("INSERT INTO discussion_themes VALUES (?,?)", (cid, body.theme))
            return {"id": cid}

    return router
