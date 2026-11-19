"""Provider-backed place catalog and community visit statistics."""

from datetime import datetime
from functools import lru_cache
import hashlib
import http.client
import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request as ApiRequest
from pydantic import BaseModel, ValidationError

from .db import connect
from .location import ACTIVE_SECONDS, Latitude, Longitude, distance, rate_limit, require_session
from .zhihu import NoRedirects

SEARCH_RADIUS = 2000
CATEGORIES = {
    "education.university": "大学",
    "education.library": "图书馆",
    "catering.cafe": "咖啡馆",
    "commercial.shopping_mall": "购物中心",
}
CATALOG_URL = "https://www.cityu.edu.hk/visit/way-finding-system-on-campus"


class Place(BaseModel):
    source: str
    source_id: str
    name: str
    category: str
    latitude: Latitude
    longitude: Longitude
    timezone: str | None = None

    @property
    def slug(self):
        digest = hashlib.sha256(f"{self.source}:{self.source_id}".encode()).hexdigest()[:24]
        return "place-" + digest

    def public(self):
        return {"slug": self.slug, **self.model_dump(exclude={"timezone"})}


# Named sites in the CityUHK campus directory. Coordinates mark the site or its building.
CITYU = (
    Place(source="cityuhk", source_id="main-campus", name="香港城市大学", category="大学",
          latitude=22.3376, longitude=114.1721, timezone="Asia/Hong_Kong"),
    Place(source="cityuhk", source_id="run-run-shaw-library", name="邵逸夫图书馆", category="图书馆",
          latitude=22.336447, longitude=114.172522, timezone="Asia/Hong_Kong"),
)
CITYU_ALIASES = (
    {"city university of hong kong", "香港城市大學", "香港城市大学"},
    {"run run shaw library", "邵逸夫圖書館", "邵逸夫图书馆"},
)


class ProviderError(Exception):
    pass


def provider_json(path, params, key):
    url = "https://api.geoapify.com" + path + "?" + urlencode({**params, "apiKey": key})
    try:
        request = Request(url, headers={"Accept": "application/json"})
        with build_opener(NoRedirects()).open(request, timeout=6) as response:
            return json.loads(response.read(1_000_000))
    except (OSError, ValueError, http.client.HTTPException):
        raise ProviderError from None


@lru_cache(maxsize=160)
def provider_places(lat, lon, period, key):
    search = provider_json("/v2/places", {
        "categories": ",".join(CATEGORIES),
        "filter": f"circle:{lon},{lat},{SEARCH_RADIUS}",
        "bias": f"proximity:{lon},{lat}",
        "limit": 25,
    }, key)
    if not isinstance(search, dict) or not isinstance(search.get("features"), list):
        raise ProviderError
    places = {}
    for feature in search["features"]:
        try:
            props = feature["properties"]
            name = props["name"].strip()
            source_id = props["place_id"]
            if not name or not isinstance(source_id, str) or not source_id:
                continue
            keys = props.get("categories", [])
            category = next((name for code, name in CATEGORIES.items() if code in keys), "地点")
            place = Place(source="geoapify", source_id=source_id, name=name[:180], category=category,
                          latitude=props["lat"], longitude=props["lon"])
            for campus, aliases in zip(CITYU, CITYU_ALIASES):
                if name.casefold() in aliases and distance(
                    place.latitude, place.longitude, campus.latitude, campus.longitude,
                ) <= 800:
                    place = campus
                    break
            places[place.slug] = place
        except (AttributeError, KeyError, TypeError, ValidationError):
            continue
    return tuple(places.values())


def place_timezone(place, key):
    payload = provider_json("/v1/geocode/reverse", {"lat": place["latitude"], "lon": place["longitude"]}, key)
    try:
        name = payload["features"][0]["properties"]["timezone"]["name"]
        return ZoneInfo(name).key
    except (IndexError, KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
        raise ProviderError from None


def save_places(connection, places):
    connection.executemany(
        """INSERT INTO places VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(slug) DO UPDATE SET name=excluded.name, category=excluded.category,
             latitude=excluded.latitude, longitude=excluded.longitude""",
        [(p.slug, p.source, p.source_id, p.name, p.category, p.latitude, p.longitude, p.timezone)
         for p in places],
    )


def find_place(connection, slug):
    place = connection.execute("SELECT * FROM places WHERE slug = ?", (slug,)).fetchone()
    if place is None:
        raise HTTPException(404, "地点不存在。请从地图选择地点。")
    return dict(place)


def places_router(path):
    router = APIRouter(prefix="/api")

    @router.get("/places/nearby")
    def search(lat: Latitude, lon: Longitude, request: ApiRequest):
        now = time.time()
        lat, lon = round(lat, 2), round(lon, 2)
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rate_limit(connection, request, "places", now, 25)
        key = os.environ.get("GEOAPIFY_PLACES_KEY", "").strip()
        fallback = [p for p in CITYU if distance(lat, lon, p.latitude, p.longitude) <= SEARCH_RADIUS]
        found = {p.slug: p for p in fallback}
        status = "catalog"
        if key:
            try:
                found.update((p.slug, p) for p in provider_places(lat, lon, int(now // 900), key))
                status = "ready"
            except ProviderError:
                status = "unavailable"
        if found:
            with connect(path) as connection:
                save_places(connection, found.values())
        places = sorted(found.values(), key=lambda p: distance(lat, lon, p.latitude, p.longitude))
        return {"places": [p.public() for p in places], "status": status}

    @router.get("/communities/{slug}")
    def community(slug: str):
        with connect(path) as connection:
            return find_place(connection, slug)

    @router.post("/communities/{slug}/visit")
    def visit(slug: str, request: ApiRequest):
        now = time.time()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            require_session(connection, request, now)
            rate_limit(connection, request, "visit", now, 180)
            place = find_place(connection, slug)
        timezone = place["timezone"]
        if timezone is None:
            try:
                timezone = place_timezone(place, os.environ.get("GEOAPIFY_PLACES_KEY", "").strip())
            except ProviderError:
                raise HTTPException(503, "暂时无法读取地点时区，请稍后重试。") from None
        today = datetime.fromtimestamp(now, ZoneInfo(timezone)).date().isoformat()
        with connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            visitor = require_session(connection, request, now)
            if place["timezone"] is None:
                connection.execute("UPDATE places SET timezone = ? WHERE slug = ?", (timezone, slug))
            connection.execute("INSERT OR IGNORE INTO communities (slug) VALUES (?)", (slug,))
            connection.execute(
                """INSERT INTO community_visits VALUES (?, ?, ?, ?)
                   ON CONFLICT(community_slug, session_id, local_day) DO UPDATE SET seen_at =
                   MAX(seen_at, excluded.seen_at)""",
                (slug, visitor["id"], today, now),
            )
            counts = connection.execute(
                """SELECT
                     COUNT(DISTINCT CASE WHEN seen_at > ? THEN session_id END) AS recent_visitors,
                     COUNT(CASE WHEN local_day = ? THEN 1 END) AS today_visitors
                   FROM community_visits WHERE community_slug = ? AND (local_day = ? OR seen_at > ?)""",
                (now - ACTIVE_SECONDS, today, slug, today, now - ACTIVE_SECONDS),
            ).fetchone()
            topics = connection.execute("SELECT COUNT(*) FROM topics WHERE community_slug = ?", (slug,)).fetchone()[0]
        return {**dict(counts), "active_topics": topics, "timezone": timezone}

    return router
