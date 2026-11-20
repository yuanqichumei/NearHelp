"""Free, location-scoped help requests and consent-based collaboration."""

import math
import time
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path as ApiPath, Request
from pydantic import BaseModel, Field, StringConstraints

from .auth import current_help_user, public_account, require_help_user, same_origin
from .db import connect
from .location import ACTIVE_SECONDS, Point, count_band, distance, rate_limit, require_session

HELP_COMMUNITY = "neartalk-help"
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Reply = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
RequestId = Annotated[int, ApiPath(ge=1, le=2**63 - 1)]
HELP_FIELDS = """h.topic_id AS id, h.author_id, h.lat, h.lon, h.expires_at, h.status, h.reward_cents,
                 h.hidden_at, h.pinned_until, t.title, t.content, t.created_at, a.nickname"""
HELP_FROM = """FROM help_requests h JOIN topics t ON t.id = h.topic_id
               JOIN accounts a ON a.id = h.author_id"""
UNSUPPORTED_TASKS = (
    "买卖枪支", "買賣槍支", "代管银行卡", "代管銀行卡", "出借银行卡", "出借銀行卡",
    "代购处方药", "代購處方藥", "代充博彩", "上门看护儿童", "上門看護兒童",
)


class Discovery(Point):
    radius: Literal[500, 1000, 3000] = 1000


class Fix(Point):
    accuracy: Annotated[float, Field(ge=0, le=500, allow_inf_nan=False)]


class NewHelp(BaseModel):
    title: Title
    content: Description
    minutes: Literal[30, 60, 180, 1440]
    location: Fix
    reward_cents: Annotated[int, Field(strict=True, ge=0, le=1000000)] = 0


class Text(BaseModel):
    content: Reply


class NewComment(Text):
    parent_id: Annotated[int, Field(gt=0, le=2**63 - 1)] | None = None


class Preferences(BaseModel):
    share_presence: bool
    discoverable: bool


class OfferDecision(BaseModel):
    decision: Literal["accepted", "declined"]


class Resolution(BaseModel):
    status: Literal["resolved", "cancelled"]


class Block(BaseModel):
    blocked: bool = True


class Report(BaseModel):
    reason: Reply


def cleanup_help(connection, now):
    connection.execute("DELETE FROM help_presence WHERE seen_at <= ?", (now - ACTIVE_SECONDS,))
    connection.execute("DELETE FROM account_sessions WHERE expires_at <= ?", (now,))
    connection.execute("UPDATE help_requests SET lat=NULL, lon=NULL WHERE lat IS NOT NULL AND expires_at <= ?", (now,))


def round_point(point, resolution):
    return tuple(round(round(value * resolution) / resolution, 5) for value in (point.lat, point.lon))


def blocked(connection, first, second):
    return bool(connection.execute(
        """SELECT 1 FROM account_blocks
           WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)""",
        (first, second, second, first),
    ).fetchone())


def throttle(connection, request, actor, action, now, limit):
    rate_limit(connection, request, "help-ip-" + action, now, max(60, limit * 4))
    rate_limit(connection, request, "help-user-" + action, now, limit, actor)


def effective_state(row, now):
    if row["status"] in {"open", "in_progress"} and row["expires_at"] <= now:
        return "expired"
    return row["status"]


def pinned(row, now):
    return (row["pinned_until"] or 0) > now and row["hidden_at"] is None and effective_state(row, now) == "open"


def item_view(row, now):
    return {**{key: row[key] for key in ("id", "author_id", "nickname", "title", "created_at", "expires_at", "reward_cents")},
            "status": effective_state(row, now), "is_pinned": pinned(row, now)}


def get_help(connection, request_id):
    row = connection.execute(
        f"SELECT {HELP_FIELDS} {HELP_FROM} WHERE h.topic_id=? AND h.hidden_at IS NULL", (request_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "找不到这个需求。")
    return row


def visible_help(connection, request_id, actor):
    row = get_help(connection, request_id)
    if actor and blocked(connection, actor, row["author_id"]):
        raise HTTPException(404, "找不到这个需求。")
    return row


def require_owner(row, account):
    if row["author_id"] != account["id"]:
        raise HTTPException(403, "只有发布者可以执行此操作。")


def responders(connection, item, actor=None):
    ids = connection.execute(
        """SELECT guest_id AS id FROM comments WHERE topic_id=?
           UNION SELECT helper_id FROM help_offers WHERE request_id=?""", (item["id"], item["id"]),
    )
    return sum(row["id"] != item["author_id"] and not blocked(connection, actor, row["id"]) for row in ids)


def help_router(path):
    router = APIRouter(prefix="/api/help")

    @router.post("/nearby")
    def nearby(body: Discovery, request: Request):
        same_origin(request)
        now = time.time()
        lat, lon = round_point(body, 500)
        extent = body.radius / 110000
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = current_help_user(connection, request)
            actor = account["id"] if account else require_session(connection, request, now)["id"]
            throttle(connection, request, actor, "nearby", now, 30)
            candidates = connection.execute(
                f"""SELECT {HELP_FIELDS},
                    (SELECT count(*) FROM comments c WHERE c.topic_id=h.topic_id AND NOT EXISTS (
                        SELECT 1 FROM account_blocks b WHERE (b.blocker_id=? AND b.blocked_id=c.guest_id)
                        OR (b.blocked_id=? AND b.blocker_id=c.guest_id))) AS comment_count,
                    EXISTS(SELECT 1 FROM help_offers o WHERE o.request_id=h.topic_id AND o.helper_id=?) AS has_offered
                    {HELP_FROM}
                    WHERE h.hidden_at IS NULL AND h.status='open' AND h.expires_at>? AND h.lat BETWEEN ? AND ?""",
                (actor, actor, actor, now, lat - extent, lat + extent),
            ).fetchall()
            presence = connection.execute(
                """SELECT p.lat,p.lon,a.id,a.nickname,a.discoverable FROM help_presence p
                   JOIN accounts a ON a.id=p.account_id
                   WHERE a.share_presence=1 AND p.seen_at>? AND p.lat BETWEEN ? AND ?""",
                (now - ACTIVE_SECONDS, lat - extent, lat + extent),
            ).fetchall()
            results = []
            for item in candidates:
                meters = distance(lat, lon, item["lat"], item["lon"])
                if meters <= body.radius and not blocked(connection, actor, item["author_id"]):
                    results.append((meters, item))
            results.sort(key=lambda entry: (not pinned(entry[1], now), int(entry[0] // 100), -entry[1]["id"]))
            items = [{**item_view(item, now), "summary": item["content"][:140],
                      "distance_m": min(body.radius, max(100, math.ceil(meters / 100) * 100)),
                      "comment_count": item["comment_count"], "has_offered": bool(item["has_offered"]),
                      "response_count": responders(connection, item, actor)}
                     for meters, item in results[:60]]
            active = [row for row in presence if distance(lat, lon, row["lat"], row["lon"]) <= body.radius]
            profiles = []
            if account:
                directory = connection.execute(
                    """SELECT a.id,a.nickname FROM help_presence p JOIN accounts a ON a.id=p.account_id
                       WHERE a.discoverable=1 AND a.share_presence=1 AND p.seen_at>?
                         AND round(p.lat,2)=round(?,2) AND round(p.lon,2)=round(?,2) AND a.id!=?""",
                    (now - ACTIVE_SECONDS, lat, lon, actor),
                )
                profiles = [dict(row) for row in directory if not blocked(connection, actor, row["id"])]
        # Small samples stay hidden, including in the opt-in directory.
        users = sorted(profiles, key=lambda profile: profile["nickname"].casefold())[:30] if len(profiles) >= 3 else []
        band = "hidden" if len(active) < 3 else count_band(len(active))
        return {"requests": items, "active_band": band, "users": users}

    @router.post("/preferences")
    def preferences(body: Preferences, request: Request):
        same_origin(request)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            throttle(connection, request, account["id"], "preferences", time.time(), 12)
            connection.execute("UPDATE accounts SET share_presence=?, discoverable=? WHERE id=?",
                               (body.share_presence, body.discoverable, account["id"]))
            if not body.share_presence:
                connection.execute("DELETE FROM help_presence WHERE account_id=?", (account["id"],))
            updated = connection.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone()
            return public_account(updated)

    @router.post("/presence", status_code=204)
    def heartbeat(body: Fix, request: Request):
        same_origin(request)
        now = time.time()
        lat, lon = round_point(body, 1000)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            if not account["share_presence"]:
                raise HTTPException(403, "附近活跃统计未开启。")
            throttle(connection, request, account["id"], "presence", now, 8)
            connection.execute(
                """INSERT INTO help_presence VALUES (?, ?, ?, ?)
                   ON CONFLICT(account_id) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, seen_at=excluded.seen_at
                   WHERE help_presence.seen_at <= excluded.seen_at - 45""",
                (account["id"], lat, lon, now),
            )

    @router.post("/requests", status_code=201)
    def publish(body: NewHelp, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            if any(task in f"{body.title}\n{body.content}" for task in UNSUPPORTED_TASKS):
                raise HTTPException(422, "请只发布低风险的日常求助。")
            throttle(connection, request, account["id"], "publish", now, 3)
            connection.execute("INSERT OR IGNORE INTO communities VALUES (?)", (HELP_COMMUNITY,))
            topic_id = connection.execute(
                "INSERT INTO topics (community_slug, guest_id, nickname, title, content) VALUES (?, ?, ?, ?, ?)",
                (HELP_COMMUNITY, account["id"], account["nickname"], body.title, body.content),
            ).lastrowid
            connection.execute(
                "INSERT INTO help_requests (topic_id, author_id, lat, lon, expires_at,reward_cents) VALUES (?, ?, ?, ?, ?, ?)",
                (topic_id, account["id"], *round_point(body.location, 500), now + body.minutes * 60, body.reward_cents),
            )
            return item_view(get_help(connection, topic_id), now)

    @router.get("/mine")
    def mine(request: Request):
        with connect(path) as connection:
            account = require_help_user(connection, request)
            rows = connection.execute(
                f"""SELECT {HELP_FIELDS} {HELP_FROM}
                    WHERE h.hidden_at IS NULL AND (h.author_id=? OR EXISTS (SELECT 1 FROM help_offers o
                        WHERE o.request_id=h.topic_id AND o.helper_id=?))
                    ORDER BY h.topic_id DESC LIMIT 100""",
                (account["id"], account["id"]),
            )
            return [item_view(row, time.time()) for row in rows
                    if not blocked(connection, account["id"], row["author_id"])]

    @router.get("/requests/{request_id}")
    def detail(request_id: RequestId, request: Request):
        now = time.time()
        with connect(path) as connection:
            account = current_help_user(connection, request)
            actor = account["id"] if account else None
            item = visible_help(connection, request_id, actor)
            is_owner = actor == item["author_id"]
            replies = connection.execute(
                """SELECT id, parent_id, guest_id AS author_id, nickname, content, created_at FROM comments
                   WHERE topic_id=? ORDER BY COALESCE(parent_id,id),id""",
                (request_id,),
            )
            offers = connection.execute(
                """SELECT o.helper_id, o.status, a.nickname FROM help_offers o
                   JOIN accounts a ON a.id=o.helper_id
                   WHERE o.request_id=? AND (? OR o.helper_id=?) ORDER BY o.offered_at""",
                (request_id, is_owner, actor),
            )
            chat = connection.execute(
                "SELECT * FROM help_conversations WHERE request_id=? AND (owner_id=? OR helper_id=?)",
                (request_id, actor, actor),
            ).fetchone()
            return {
                **item_view(item, now), "content": item["content"], "is_owner": is_owner,
                "response_count": responders(connection, item, actor),
                "replies": [dict(reply) for reply in replies if not blocked(connection, actor, reply["author_id"])],
                "offers": [dict(offer) for offer in offers if not blocked(connection, actor, offer["helper_id"])],
                "chat_id": chat["request_id"] if chat and not blocked(connection, chat["owner_id"], chat["helper_id"]) else None,
            }

    @router.post("/requests/{request_id}/replies", status_code=201)
    def reply(request_id: RequestId, body: NewComment, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            item = visible_help(connection, request_id, account["id"])
            if effective_state(item, now) not in {"open", "in_progress"}:
                raise HTTPException(409, "该需求已关闭。")
            if body.parent_id is not None:
                parent = connection.execute(
                    "SELECT guest_id FROM comments WHERE id=? AND topic_id=? AND parent_id IS NULL",
                    (body.parent_id, request_id),
                ).fetchone()
                if not parent or blocked(connection, account["id"], parent["guest_id"]):
                    raise HTTPException(422, "请选择本需求中可见的一级评论进行回复。")
            throttle(connection, request, account["id"], "reply", now, 15)
            reply_id = connection.execute(
                "INSERT INTO comments (topic_id, parent_id, guest_id, nickname, content) VALUES (?, ?, ?, ?, ?)",
                (request_id, body.parent_id, account["id"], account["nickname"], body.content),
            ).lastrowid
        return {"id": reply_id}

    @router.post("/requests/{request_id}/offers", status_code=204)
    def offer(request_id: RequestId, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            item = visible_help(connection, request_id, account["id"])
            if item["author_id"] == account["id"]:
                raise HTTPException(403, "不能协助自己的需求。")
            if effective_state(item, now) != "open":
                raise HTTPException(409, "该需求已停止接受协助。")
            throttle(connection, request, account["id"], "offer", now, 12)
            connection.execute("INSERT OR IGNORE INTO help_offers VALUES (?, ?, 'pending', ?)",
                               (request_id, account["id"], now))

    @router.post("/requests/{request_id}/offers/{helper_id}", status_code=204)
    def decide(request_id: RequestId, helper_id: str, body: OfferDecision, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            item = get_help(connection, request_id)
            require_owner(item, account)
            if effective_state(item, now) != "open" or blocked(connection, account["id"], helper_id):
                raise HTTPException(409, "当前无法处理这条协助申请。")
            throttle(connection, request, account["id"], "decision", now, 20)
            updated = connection.execute(
                "UPDATE help_offers SET status=? WHERE request_id=? AND helper_id=? AND status='pending'",
                (body.decision, request_id, helper_id),
            )
            if not updated.rowcount:
                raise HTTPException(409, "申请已处理或不存在。")
            if body.decision == "accepted":
                connection.execute("UPDATE help_requests SET status='in_progress',lat=NULL,lon=NULL,pinned_until=NULL WHERE topic_id=?",
                                   (request_id,))
                connection.execute("UPDATE help_offers SET status='declined' WHERE request_id=? AND status='pending'",
                                   (request_id,))
                connection.execute("INSERT INTO help_conversations VALUES (?, ?, ?)",
                                   (request_id, account["id"], helper_id))

    @router.post("/requests/{request_id}/state", status_code=204)
    def close(request_id: RequestId, body: Resolution, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            item = get_help(connection, request_id)
            require_owner(item, account)
            if effective_state(item, now) not in {"open", "in_progress"}:
                raise HTTPException(409, "该需求已关闭。")
            throttle(connection, request, account["id"], "state", now, 15)
            connection.execute("UPDATE help_requests SET status=?, lat=NULL, lon=NULL, pinned_until=NULL WHERE topic_id=?",
                               (body.status, request_id))
            connection.execute("UPDATE help_offers SET status='declined' WHERE request_id=? AND status='pending'",
                               (request_id,))

    @router.post("/blocks/{target_id}", status_code=204)
    def block(target_id: str, body: Block, request: Request):
        same_origin(request)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            if target_id == account["id"] or not connection.execute(
                "SELECT 1 FROM accounts WHERE id=?", (target_id,),
            ).fetchone():
                raise HTTPException(404, "找不到该用户。")
            throttle(connection, request, account["id"], "block", time.time(), 20)
            if body.blocked:
                connection.execute("INSERT OR IGNORE INTO account_blocks VALUES (?, ?)", (account["id"], target_id))
            else:
                connection.execute("DELETE FROM account_blocks WHERE blocker_id=? AND blocked_id=?",
                                   (account["id"], target_id))

    @router.get("/blocks")
    def blocks(request: Request):
        with connect(path) as connection:
            account = require_help_user(connection, request)
            return [dict(row) for row in connection.execute(
                """SELECT a.id, a.nickname FROM account_blocks b JOIN accounts a ON a.id=b.blocked_id
                   WHERE b.blocker_id=? ORDER BY a.nickname""", (account["id"],),
            )]

    @router.post("/requests/{request_id}/reports/{target_id}", status_code=204)
    def report(request_id: RequestId, target_id: str, body: Report, request: Request):
        same_origin(request)
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            account = require_help_user(connection, request)
            item = get_help(connection, request_id)
            participant = target_id == item["author_id"] or connection.execute(
                """SELECT 1 FROM help_offers WHERE request_id=? AND helper_id=?
                   UNION SELECT 1 FROM comments WHERE topic_id=? AND guest_id=?""",
                (request_id, target_id, request_id, target_id),
            ).fetchone()
            if target_id == account["id"] or not participant:
                raise HTTPException(404, "找不到可举报的用户。")
            throttle(connection, request, account["id"], "report", now, 8)
            connection.execute(
                """INSERT OR IGNORE INTO help_reports (reporter_id,target_id,request_id,reason,reported_at)
                   VALUES (?,?,?,?,?)""", (account["id"], target_id, request_id, body.reason, now),
            )

    return router
