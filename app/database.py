"""SQLite 连接管理与建表。"""
import sqlite3

from . import config

DDL = """
CREATE TABLE IF NOT EXISTS videos (
  bvid          TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  author_name   TEXT,
  author_mid    TEXT,
  cover_url     TEXT,
  pubdate       INTEGER,
  duration      INTEGER,
  tname         TEXT,
  view          INTEGER DEFAULT 0,
  like          INTEGER DEFAULT 0,
  coin          INTEGER DEFAULT 0,
  favorite      INTEGER DEFAULT 0,
  reply         INTEGER DEFAULT 0,
  danmaku       INTEGER DEFAULT 0,
  share         INTEGER DEFAULT 0,
  quality_score REAL,
  data_complete INTEGER DEFAULT 1,
  fetched_at    INTEGER
);

CREATE TABLE IF NOT EXISTS favorites (
  bvid       TEXT PRIMARY KEY,
  created_at INTEGER,
  FOREIGN KEY (bvid) REFERENCES videos(bvid)
);

CREATE TABLE IF NOT EXISTS video_notes (
  bvid       TEXT PRIMARY KEY,
  note       TEXT DEFAULT '',
  updated_at INTEGER,
  FOREIGN KEY (bvid) REFERENCES videos(bvid)
);

CREATE TABLE IF NOT EXISTS search_cache (
  cache_key  TEXT PRIMARY KEY,
  keyword    TEXT,
  time_range TEXT,
  bvids      TEXT,
  fetched_at INTEGER
);
"""


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()


def db_readable() -> bool:
    try:
        conn = get_conn()
        conn.execute("SELECT 1 FROM videos LIMIT 1")
        conn.close()
        return True
    except Exception:
        return False
