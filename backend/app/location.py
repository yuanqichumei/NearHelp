"""Short-lived anonymous presence and aggregate nearby counts."""

import hashlib
import hmac
import math
import re
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .db import connect

COOKIE = "neartalk_geo"
ACTIVE_SECONDS = 300
SESSION_SECONDS = 30 * 86400
RADIUS = 500
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class Point(BaseModel):
    lat: Latitude
    lon: Longitude


class Consent(BaseModel):
    enabled: bool


def distance(lat1, lon1, lat2, lon2):
    lat_delta = math.radians(lat2 - lat1)
    lon_delta = math.radians(lon2 - lon1)
    a = (math.sin(lat_delta / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(lon_delta / 2) ** 2)
    return 12_742_000 * math.asin(math.sqrt(min(1.0, a)))


def nearby_count(connection, lat, lon, now):
    candidates = connection.execute(
        "SELECT lat, lon FROM geo_presence WHERE lat BETWEEN ? AND ? AND seen_at > ?",
        (lat - .0046, lat + .0046, now - ACTIVE_SECONDS),
    )
    return sum(distance(lat, lon, row["lat"], row["lon"]) <= RADIUS for row in candidates)


def count_band(count):
    if count < 3:
        return str(count)
    if count < 5:
        return "3–4"
    if count < 10:
        return "5–9"
    if count < 20:
        return "10–19"
    if count < 50:
        return "20–49"
    return "50+"


def cleanup(connection, now):
    connection.execute("DELETE FROM geo_presence WHERE seen_at <= ?", (now - ACTIVE_SECONDS,))
    connection.execute("UPDATE geo_sessions SET last_report = NULL WHERE last_report <= ?", (now - ACTIVE_SECONDS,))
    connection.execute("DELETE FROM community_visits WHERE seen_at <= ?", (now - 2 * 86400,))
    connection.execute("DELETE FROM geo_sessions WHERE expires_at <= ?", (now,))
    connection.execute("DELETE FROM geo_rate WHERE bucket < ?", (int(now // 60) - 1,))


def session(connection, request, now):
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{43}", token):
        return None
    return connection.execute(
        "SELECT id, enabled, last_report FROM geo_sessions WHERE id = ? AND expires_at > ?",
        (hashlib.sha256(token.encode()).hexdigest(), now),
    ).fetchone()


def require_session(connection, request, now):
    entry = session(connection, request, now)
    if entry is None:
        raise HTTPException(401, "请先启动浏览器访客会话。")
    return entry


def rate_limit(connection, request, action, now, limit, session_id=None):
    # Only a keyed digest is retained, briefly, for abuse limits.
    row = connection.execute("SELECT value FROM geo_meta WHERE key = 'ip_key'").fetchone()
    if row is None:
        key = secrets.token_hex(32)
        connection.execute("INSERT INTO geo_meta VALUES ('ip_key', ?)", (key,))
    else:
        key = row["value"]
    peer = session_id or (request.client.host if request.client else "")
    actor = hmac.new(bytes.fromhex(key), peer.encode(), "sha256").hexdigest()
    bucket = int(now // 60)
    row = connection.execute(
        "SELECT hits FROM geo_rate WHERE actor = ? AND action = ? AND bucket = ?",
        (actor, action, bucket),
    ).fetchone()
    if row is not None and row["hits"] >= limit:
        raise HTTPException(429, "请求太频繁，请稍后再试。", headers={"Retry-After": "60"})
    connection.execute(
        """INSERT INTO geo_rate VALUES (?, ?, ?, 1)
           ON CONFLICT(actor, action, bucket) DO UPDATE SET hits = hits + 1""",
        (actor, action, bucket),
    )


def location_router(path):
    router = APIRouter(prefix="/api")

    @router.post("/visitor/session", status_code=204)
    def start_session(request: Request, response: Response):
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if session(connection, request, now):
                return
            rate_limit(connection, request, "session", now, 30)
            token = secrets.token_urlsafe(32)
            connection.execute("INSERT INTO geo_sessions (id, expires_at) VALUES (?, ?)",
                               (hashlib.sha256(token.encode()).hexdigest(), now + SESSION_SECONDS))
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                            secure=request.url.scheme == "https", samesite="strict")

    @router.post("/location/consent", status_code=204)
    def set_consent(body: Consent, request: Request):
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            visitor = require_session(connection, request, now)
            rate_limit(connection, request, "consent", now, 120)
            connection.execute("UPDATE geo_sessions SET enabled = ? WHERE id = ?", (body.enabled, visitor["id"]))
            if not body.enabled:
                connection.execute("DELETE FROM geo_presence WHERE session_id = ?", (visitor["id"],))

    @router.post("/location/heartbeat")
    def heartbeat(body: Point, request: Request):
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            visitor = require_session(connection, request, now)
            if not visitor["enabled"]:
                raise HTTPException(403, "附近活跃统计已关闭。")
            rate_limit(connection, request, "heartbeat", now, 180)
            # Reusing the result prevents rapid sweeps across neighboring coordinates.
            if visitor["last_report"] is not None and visitor["last_report"] > now - 55:
                previous = connection.execute("SELECT band, lat, lon FROM geo_presence WHERE session_id = ?",
                                              (visitor["id"],)).fetchone()
                band = previous["band"] if previous else None
                if band == "hidden":
                    band = count_band(nearby_count(connection, previous["lat"], previous["lon"], now))
                return {"radius_m": RADIUS, "band": band}
            lat, lon = round(body.lat, 3), round(body.lon, 3)
            connection.execute(
                """INSERT INTO geo_presence VALUES (?, ?, ?, ?, NULL)
                   ON CONFLICT(session_id) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, seen_at=excluded.seen_at""",
                (visitor["id"], lat, lon, now),
            )
            band = count_band(nearby_count(connection, lat, lon, now))
            connection.execute("UPDATE geo_presence SET band = ? WHERE session_id = ?", (band, visitor["id"]))
            connection.execute("UPDATE geo_sessions SET last_report = ? WHERE id = ?", (now, visitor["id"]))
            return {"radius_m": RADIUS, "band": band}

    return router
