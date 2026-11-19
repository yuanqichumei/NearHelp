from contextlib import contextmanager
from pathlib import Path
import sqlite3

DEFAULT_COMMUNITY = "cityu-hackathon"
SCHEMA = """
CREATE TABLE IF NOT EXISTS communities (
    slug TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    community_slug TEXT NOT NULL REFERENCES communities(slug),
    guest_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS topics_community ON topics(community_slug, id DESC);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id),
    guest_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS comments_topic ON comments(topic_id, id);
CREATE TABLE IF NOT EXISTS write_events (
    guest_id TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS write_events_time ON write_events(created_at);
CREATE TABLE IF NOT EXISTS hot_topics (
    topic_id INTEGER PRIMARY KEY REFERENCES topics(id),
    community_slug TEXT NOT NULL REFERENCES communities(slug),
    source TEXT NOT NULL,
    url_key TEXT NOT NULL,
    original_url TEXT NOT NULL,
    rank INTEGER,
    UNIQUE (community_slug, source, url_key)
);
CREATE TABLE IF NOT EXISTS hot_cache (
    community_slug TEXT NOT NULL REFERENCES communities(slug),
    source TEXT NOT NULL,
    fetched_at REAL,
    retry_after REAL NOT NULL,
    PRIMARY KEY (community_slug, source)
);
CREATE TABLE IF NOT EXISTS geo_sessions (
    id TEXT PRIMARY KEY,
    expires_at REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    last_report REAL
);
CREATE TABLE IF NOT EXISTS geo_presence (
    session_id TEXT PRIMARY KEY REFERENCES geo_sessions(id) ON DELETE CASCADE,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    seen_at REAL NOT NULL,
    band TEXT
);
CREATE INDEX IF NOT EXISTS geo_presence_seen ON geo_presence(seen_at);
CREATE INDEX IF NOT EXISTS geo_presence_lat ON geo_presence(lat);
CREATE TABLE IF NOT EXISTS geo_rate (
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    bucket INTEGER NOT NULL,
    hits INTEGER NOT NULL,
    PRIMARY KEY (actor, action, bucket)
);
CREATE TABLE IF NOT EXISTS geo_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS places (
    slug TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT,
    UNIQUE (source, source_id)
);
CREATE TABLE IF NOT EXISTS community_visits (
    community_slug TEXT NOT NULL REFERENCES communities(slug),
    session_id TEXT NOT NULL REFERENCES geo_sessions(id) ON DELETE CASCADE,
    local_day TEXT NOT NULL,
    seen_at REAL NOT NULL,
    PRIMARY KEY (community_slug, session_id, local_day)
);
CREATE INDEX IF NOT EXISTS community_visits_seen ON community_visits(seen_at);
CREATE INDEX IF NOT EXISTS community_visits_day ON community_visits(community_slug, local_day);
CREATE TABLE IF NOT EXISTS topic_regions (
    topic_id INTEGER PRIMARY KEY REFERENCES topics(id) ON DELETE CASCADE,
    lat REAL NOT NULL,
    lon REAL NOT NULL
);
"""


@contextmanager
def connect(path: Path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SCHEMA)
        connection.execute("INSERT OR IGNORE INTO communities (slug) VALUES (?)", (DEFAULT_COMMUNITY,))


if __name__ == "__main__":
    from .config import database_path

    initialize(database_path())
