"""Approximate distance and pilot-city scopes for the home feed."""

from typing import Literal
import time

from fastapi import Request

from .db import DEFAULT_COMMUNITY, connect
from .location import ACTIVE_SECONDS, Point, count_band, distance, rate_limit, require_session

Scope = Literal["1", "5", "10", "city"]
CITY_AREAS = (
    # Approximate pilot coverage, not administrative boundaries.
    ("香港", 22.15, 22.51, 113.82, 114.45, 22.319, 114.169),
    ("深圳", 22.44, 22.88, 113.74, 114.64, 22.543, 114.058),
    ("广州", 22.58, 23.95, 112.95, 114.10, 23.13, 113.32),
)
LEGACY_POINT = (22.3376, 114.1721)


def city_at(lat, lon):
    candidates = ((distance(lat, lon, center_lat, center_lon), name)
                  for name, south, north, west, east, center_lat, center_lon in CITY_AREAS
                  if south <= lat <= north and west <= lon <= east)
    return min(candidates, default=(0, None))[1]


def coarse_point(point: Point):
    return tuple(round(round(value * 200) / 200, 3) for value in (point.lat, point.lon))


def match_area(lat, lon, scope):
    city = city_at(lat, lon)
    if scope == "city":
        return lambda other_lat, other_lon: city is not None and city_at(other_lat, other_lon) == city
    radius = int(scope) * 1000
    return lambda other_lat, other_lon: distance(lat, lon, other_lat, other_lon) <= radius


def regional_topics(path, point, scope):
    lat, lon = coarse_point(point)
    contains = match_area(lat, lon, scope)
    with connect(path) as connection:
        connection.create_function("in_region", 2, contains, deterministic=True)
        rows = connection.execute(
            """SELECT t.id, t.community_slug, t.nickname, t.title, t.created_at,
                 CASE WHEN length(t.content) > 140 THEN substr(t.content, 1, 140) || '…'
                      ELSE t.content END AS summary,
                 (SELECT COUNT(*) FROM comments c WHERE c.topic_id = t.id) AS comment_count
               FROM topics t
               LEFT JOIN topic_regions r ON r.topic_id = t.id
               LEFT JOIN places p ON p.slug = t.community_slug
               WHERE (r.topic_id IS NOT NULL OR p.slug IS NOT NULL OR t.community_slug = ?)
                 AND in_region(coalesce(r.lat, p.latitude, ?), coalesce(r.lon, p.longitude, ?))
                 AND NOT EXISTS (SELECT 1 FROM hot_topics h WHERE h.topic_id = t.id)
               ORDER BY t.id DESC""",
            (DEFAULT_COMMUNITY, *LEGACY_POINT),
        )
        return [dict(row) for row in rows]


def regional_stats(path, point, scope, request: Request):
    lat, lon = coarse_point(point)
    city = city_at(lat, lon)
    now = time.time()
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        visitor = require_session(connection, request, now)
        rate_limit(connection, request, "region-stats", now, 120)
        rate_limit(connection, request, "region-viewer", now, 8, visitor["id"])
        if scope == "city" and city is None:
            return {"city": city, "band": None}
        contains = match_area(lat, lon, scope)
        connection.create_function("in_region", 2, contains, deterministic=True)
        count = connection.execute(
            "SELECT COUNT(*) FROM geo_presence WHERE seen_at > ? AND in_region(lat, lon)",
            (now - ACTIVE_SECONDS,),
        ).fetchone()[0]
    return {"city": city, "band": count_band(count)}
