import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from pathlib import Path
from sqlite3 import OperationalError
import time
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Path as ApiPath, Request
from pydantic import BaseModel, StringConstraints

from .config import database_path, demo_enabled
from .auth import auth_router, require_account, same_origin
from .db import DEFAULT_COMMUNITY, connect, initialize
from .hot_topics import list_hot_topics
from .help_messages import messages_router
from .help_requests import HELP_COMMUNITY, cleanup_help, help_router
from .location import Latitude, Longitude, Point, cleanup, location_router
from .moderation import moderation_router
from .places import places_router
from .regions import Scope, coarse_point, regional_stats, regional_topics

Nickname = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
TopicContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
CommentContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
TopicId = Annotated[int, ApiPath(ge=1, le=2**63 - 1)]
WINDOW = 60
# The IP allowance accommodates multiple guests behind a shared campus address.
LIMITS = {"topic": (3, 60), "comment": (12, 240)}
TOPIC_FIELDS = "t.id, t.nickname, t.title, t.content, t.created_at"
COMMENT_FIELDS = "id, topic_id, nickname, content, created_at"


class Guest(BaseModel):
    guest_id: UUID
    nickname: Nickname


class NewTopic(Guest):
    title: Title
    content: TopicContent
    region: Point | None = None


class NewComment(Guest):
    content: CommentContent


def require_community(connection, slug):
    if slug == HELP_COMMUNITY or connection.execute(
        "SELECT 1 FROM communities WHERE slug = ?", (slug,),
    ).fetchone() is None:
        raise HTTPException(404, "社区不存在")


def require_topic(connection, slug, topic_id):
    if slug == HELP_COMMUNITY:
        raise HTTPException(404, "话题不存在")
    topic = connection.execute(
        f"SELECT {TOPIC_FIELDS} FROM topics t WHERE t.community_slug = ? AND t.id = ?",
        (slug, topic_id),
    ).fetchone()
    if topic is None:
        raise HTTPException(404, "话题不存在")
    return topic


def record_write(connection, request, guest_id, action):
    now = time.time()
    client_ip = request.client.host if request.client else "unknown"
    guest_limit, ip_limit = LIMITS[action]
    connection.execute("DELETE FROM write_events WHERE created_at <= ?", (now - WINDOW,))
    guest_count, ip_count = connection.execute(
        """
        SELECT COALESCE(SUM(guest_id = ?), 0), COALESCE(SUM(client_ip = ?), 0)
        FROM write_events WHERE action = ?
        """,
        (guest_id, client_ip, action),
    ).fetchone()
    if guest_count >= guest_limit or ip_count >= ip_limit:
        raise HTTPException(429, "操作太频繁，请稍后再试", headers={"Retry-After": str(WINDOW)})
    connection.execute(
        "INSERT INTO write_events (guest_id, client_ip, action, created_at) VALUES (?, ?, ?, ?)",
        (guest_id, client_ip, action, now),
    )


def create_app(db_path: Path | None = None) -> FastAPI:
    path = db_path if db_path is not None else database_path()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize(path)

        def purge():
            with connect(path) as connection:
                now = time.time()
                cleanup(connection, now)
                cleanup_help(connection, now)

        async def periodically():
            while True:
                await asyncio.sleep(60)
                try:
                    await asyncio.to_thread(purge)
                except OperationalError:
                    logging.getLogger(__name__).warning("Geographic activity cleanup will retry")

        purge()
        task = asyncio.create_task(periodically())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="NearHelp", lifespan=lifespan)
    app.state.demo_guests = demo_enabled()
    app.include_router(location_router(path))
    app.include_router(places_router(path))
    app.include_router(auth_router(path))
    app.include_router(help_router(path))
    app.include_router(messages_router(path))
    app.include_router(moderation_router(path))

    @app.middleware("http")
    async def no_api_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        with connect(path) as connection:
            connection.execute("SELECT slug FROM communities LIMIT 1").fetchone()
        return {"status": "ok"}

    @app.get("/api/hot-topics")
    def hot_topics():
        return list_hot_topics(path)

    @app.get("/api/regions/topics")
    def list_regional_topics(lat: Latitude, lon: Longitude, scope: Scope = "5"):
        return regional_topics(path, Point(lat=lat, lon=lon), scope)

    @app.get("/api/regions/stats")
    def get_regional_stats(lat: Latitude, lon: Longitude, request: Request, scope: Scope = "5"):
        return regional_stats(path, Point(lat=lat, lon=lon), scope, request)

    @app.get("/api/communities/{slug}/topics")
    def list_topics(slug: str):
        with connect(path) as connection:
            require_community(connection, slug)
            rows = connection.execute(
                f"""SELECT t.id, t.nickname, t.title, t.created_at,
                    CASE WHEN length(t.content) > 140 THEN substr(t.content, 1, 140) || '…'
                        ELSE t.content END AS summary,
                    (SELECT COUNT(*) FROM comments c WHERE c.topic_id = t.id) AS comment_count
                    FROM topics t WHERE t.community_slug = ?
                    AND NOT EXISTS (SELECT 1 FROM hot_topics h WHERE h.topic_id = t.id)
                    ORDER BY t.id DESC""",
                (slug,),
            ).fetchall()
            return [dict(row) for row in rows]

    @app.post("/api/communities/{slug}/topics", status_code=201)
    def create_topic(slug: str, topic: NewTopic, request: Request):
        same_origin(request)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            require_community(connection, slug)
            account = require_account(connection, request)
            guest_id = account["id"]
            record_write(connection, request, guest_id, "topic")
            cursor = connection.execute(
                "INSERT INTO topics (community_slug, guest_id, nickname, title, content) VALUES (?, ?, ?, ?, ?)",
                (slug, guest_id, account["nickname"], topic.title, topic.content),
            )
            if slug == DEFAULT_COMMUNITY and topic.region is not None:
                connection.execute("INSERT INTO topic_regions VALUES (?, ?, ?)",
                                   (cursor.lastrowid, *coarse_point(topic.region)))
            return dict(require_topic(connection, slug, cursor.lastrowid))

    @app.get("/api/communities/{slug}/topics/{topic_id}")
    def get_topic(slug: str, topic_id: TopicId):
        with connect(path) as connection:
            connection.execute("BEGIN")
            topic = require_topic(connection, slug, topic_id)
            comments = connection.execute(
                f"SELECT {COMMENT_FIELDS} FROM comments WHERE topic_id = ? ORDER BY id",
                (topic_id,),
            ).fetchall()
            hot = connection.execute(
                "SELECT source, original_url FROM hot_topics WHERE topic_id = ?", (topic_id,),
            ).fetchone()
            return {**dict(topic), "comments": [dict(comment) for comment in comments],
                    **({"hot_topic": dict(hot)} if hot else {})}

    @app.post("/api/communities/{slug}/topics/{topic_id}/comments", status_code=201)
    def create_comment(slug: str, topic_id: TopicId, comment: NewComment, request: Request):
        same_origin(request)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            require_topic(connection, slug, topic_id)
            account = require_account(connection, request)
            guest_id = account["id"]
            record_write(connection, request, guest_id, "comment")
            cursor = connection.execute(
                "INSERT INTO comments (topic_id, guest_id, nickname, content) VALUES (?, ?, ?, ?)",
                (topic_id, guest_id, account["nickname"], comment.content),
            )
            return dict(connection.execute(
                f"SELECT {COMMENT_FIELDS} FROM comments WHERE id = ?", (cursor.lastrowid,),
            ).fetchone())

    return app


app = create_app()
