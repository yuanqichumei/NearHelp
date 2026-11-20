from contextlib import contextmanager
from pathlib import Path
import sqlite3
from .discussion_catalog import seed

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
    parent_id INTEGER REFERENCES comments(id),
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
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    nickname TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0,1)),
    is_demo INTEGER NOT NULL DEFAULT 0,
    share_presence INTEGER NOT NULL DEFAULT 0,
    discoverable INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS account_sessions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS account_sessions_expiry ON account_sessions(expires_at);
CREATE TABLE IF NOT EXISTS help_presence (
    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    seen_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS help_presence_expiry ON help_presence(seen_at);
CREATE TABLE IF NOT EXISTS help_requests (
    topic_id INTEGER PRIMARY KEY REFERENCES topics(id),
    author_id TEXT NOT NULL REFERENCES accounts(id),
    lat REAL,
    lon REAL,
    expires_at REAL NOT NULL,
    hidden_at REAL,
    pinned_until REAL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'resolved', 'cancelled')),
    reward_cents INTEGER NOT NULL DEFAULT 0 CHECK (reward_cents BETWEEN 0 AND 1000000)
);
CREATE INDEX IF NOT EXISTS help_requests_area ON help_requests(status, lat, expires_at);
CREATE TABLE IF NOT EXISTS help_offers (
    request_id INTEGER NOT NULL REFERENCES help_requests(topic_id),
    helper_id TEXT NOT NULL REFERENCES accounts(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
    offered_at REAL NOT NULL,
    PRIMARY KEY (request_id, helper_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS help_one_helper ON help_offers(request_id) WHERE status = 'accepted';
CREATE TABLE IF NOT EXISTS help_conversations (
    request_id INTEGER PRIMARY KEY REFERENCES help_requests(topic_id),
    owner_id TEXT NOT NULL REFERENCES accounts(id),
    helper_id TEXT NOT NULL REFERENCES accounts(id)
);
CREATE TABLE IF NOT EXISTS help_messages (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES help_conversations(request_id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    read_at REAL
);
CREATE INDEX IF NOT EXISTS help_messages_chat ON help_messages(request_id, id);
CREATE TABLE IF NOT EXISTS account_blocks (
    blocker_id TEXT NOT NULL REFERENCES accounts(id),
    blocked_id TEXT NOT NULL REFERENCES accounts(id),
    PRIMARY KEY (blocker_id, blocked_id)
);
CREATE TABLE IF NOT EXISTS help_reports (
    id INTEGER PRIMARY KEY,
    reporter_id TEXT NOT NULL REFERENCES accounts(id),
    target_id TEXT NOT NULL REFERENCES accounts(id),
    request_id INTEGER NOT NULL REFERENCES help_requests(topic_id),
    reason TEXT NOT NULL,
    reported_at REAL NOT NULL,
    UNIQUE (reporter_id, target_id, request_id)
);
CREATE INDEX IF NOT EXISTS help_reports_request ON help_reports(request_id);
CREATE TABLE IF NOT EXISTS discussion_rounds (
    topic_id INTEGER PRIMARY KEY REFERENCES topics(id),
    venue TEXT NOT NULL,
    lat REAL NOT NULL, lon REAL NOT NULL,
    question_key TEXT NOT NULL,
    zhihu_url TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS discussion_local (
    comment_id INTEGER PRIMARY KEY REFERENCES comments(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS discussion_themes (
    comment_id INTEGER PRIMARY KEY REFERENCES discussion_local(comment_id) ON DELETE CASCADE,
    theme TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discussion_ai_consent (
    comment_id INTEGER PRIMARY KEY REFERENCES discussion_local(comment_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS discussion_votes (
    comment_id INTEGER NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    value INTEGER NOT NULL CHECK(value IN (-1, 1)),
    PRIMARY KEY (comment_id, account_id)
);
CREATE TABLE IF NOT EXISTS discussion_insights (
    topic_id INTEGER PRIMARY KEY REFERENCES discussion_rounds(topic_id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS discussion_hidden (
    comment_id INTEGER PRIMARY KEY REFERENCES comments(id) ON DELETE CASCADE,
    hidden_at REAL NOT NULL
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
        connection.execute("BEGIN IMMEDIATE")
        # Existing databases retain their topics, accounts, messages and row IDs.
        for table, column, definition in (
            ("accounts", "is_demo", "INTEGER NOT NULL DEFAULT 0"),
            ("accounts", "is_admin", "INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0,1))"),
            ("help_requests", "reward_cents", "INTEGER NOT NULL DEFAULT 0 CHECK (reward_cents BETWEEN 0 AND 1000000)"),
            ("help_requests", "hidden_at", "REAL"),
            ("help_requests", "pinned_until", "REAL"),
            ("comments", "parent_id", "INTEGER REFERENCES comments(id)"),
            ("discussion_rounds", "featured", "INTEGER NOT NULL DEFAULT 1"),
            ("discussion_rounds", "hidden_at", "REAL"),
            ("discussion_rounds", "pinned_until", "REAL"),
        ):
            if column not in {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        connection.execute("INSERT OR IGNORE INTO communities (slug) VALUES (?)", (DEFAULT_COMMUNITY,))
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_primary_question_per_venue ON discussion_rounds(venue) WHERE active=1 AND featured=1")
        connection.execute("DROP INDEX IF EXISTS one_feature_per_venue")
        seed(connection)


if __name__ == "__main__":
    from .config import database_path

    initialize(database_path())
