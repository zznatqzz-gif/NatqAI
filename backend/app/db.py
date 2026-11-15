import sqlite3
from contextlib import contextmanager
from .config import DATABASE_PATH

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS projects (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chats (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL DEFAULT 'محادثة جديدة',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS attachments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
 original_name TEXT NOT NULL,
 stored_name TEXT NOT NULL UNIQUE,
 mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
 size INTEGER NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_attachments_chat ON attachments(user_id, chat_id, id);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
 content TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id, id);
CREATE TABLE IF NOT EXISTS usage_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
 model TEXT NOT NULL DEFAULT '',
 prompt_tokens INTEGER NOT NULL DEFAULT 0,
 completion_tokens INTEGER NOT NULL DEFAULT 0,
 total_tokens INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_usage_user_created ON usage_events(user_id, created_at);
CREATE TABLE IF NOT EXISTS wallets (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 balance INTEGER NOT NULL DEFAULT 0,
 currency TEXT NOT NULL DEFAULT 'USD'
);
CREATE TABLE IF NOT EXISTS deployment_sources (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 stored_name TEXT NOT NULL UNIQUE,
 original_name TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 file_count INTEGER NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_deployment_sources_user_project ON deployment_sources(user_id, project_id, id DESC);
CREATE TABLE IF NOT EXISTS deployment_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 source_id INTEGER NOT NULL REFERENCES deployment_sources(id) ON DELETE CASCADE,
 railway_project_id TEXT NOT NULL,
 railway_service_id TEXT NOT NULL,
 railway_environment_id TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','uploading','triggered','failed')),
 message TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_deployment_runs_user_project ON deployment_runs(user_id, project_id, id DESC);
CREATE TABLE IF NOT EXISTS user_integrations (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 provider TEXT NOT NULL,
 encrypted_secret TEXT NOT NULL,
 provider_account_id TEXT NOT NULL DEFAULT '',
 provider_account_name TEXT NOT NULL DEFAULT '',
 verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(user_id, provider)
);
CREATE TABLE IF NOT EXISTS media_jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 media_type TEXT NOT NULL CHECK(media_type IN ('image','video')),
 prompt TEXT NOT NULL,
 reference_url TEXT,
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 output_url TEXT,
 provider_job_id TEXT NOT NULL DEFAULT '',
 error TEXT,
 attempt_count INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 3,
 next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 started_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_media_jobs_user_created ON media_jobs(user_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_media_jobs_status ON media_jobs(status, id);
"""

@contextmanager
def connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with connection() as conn:
        conn.executescript(SCHEMA)
        # Additive migration for databases created before durable media retries.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(media_jobs)").fetchall()}
        additions = {
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "max_attempts": "INTEGER NOT NULL DEFAULT 3",
            "next_attempt_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "started_at": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE media_jobs ADD COLUMN {name} {definition}")
        # Additive deployment tracking fields; keep the original local workflow status
        # separate from Railway's remote deployment state.
        deployment_columns = {row[1] for row in conn.execute("PRAGMA table_info(deployment_runs)").fetchall()}
        deployment_additions = {
            "remote_status": "TEXT NOT NULL DEFAULT ''",
            "deployment_id": "TEXT NOT NULL DEFAULT ''",
            "deployment_url": "TEXT NOT NULL DEFAULT ''",
            "last_checked_at": "TEXT",
        }
        for name, definition in deployment_additions.items():
            if name not in deployment_columns:
                conn.execute(f"ALTER TABLE deployment_runs ADD COLUMN {name} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_jobs_due ON media_jobs(status, next_attempt_at, id)")
