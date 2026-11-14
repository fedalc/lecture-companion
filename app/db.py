"""SQLite access (stdlib sqlite3). Every phase uses these helpers.

Usage:
    from app.db import query, query_one, execute
    rows = query("SELECT * FROM lectures WHERE course_id=?", (cid,))   # list[dict]
    row  = query_one("SELECT * FROM lectures WHERE id=?", (lid,))      # dict | None
    new_id = execute("INSERT INTO notes (...) VALUES (?,?)", (a, b))   # lastrowid
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    lecturer_name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    number INTEGER,
    title TEXT NOT NULL,
    date TEXT,
    slides_path TEXT,
    material_text TEXT,
    lecture_md TEXT,
    status TEXT DEFAULT 'uploaded'   -- uploaded | generating | ready | error
);
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    name TEXT NOT NULL,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    lecture_id INTEGER REFERENCES lectures(id),
    kind TEXT NOT NULL,              -- homework | live | self_eval | bank
    title TEXT,
    is_oral INTEGER DEFAULT 0,
    is_sample INTEGER DEFAULT 0,
    is_open INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id),
    topic_id INTEGER REFERENCES topics(id),
    text TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_index INTEGER NOT NULL,
    explanation TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id),
    student_name TEXT,
    score INTEGER,
    total INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id),
    question_id INTEGER NOT NULL REFERENCES questions(id),
    chosen_index INTEGER,
    is_correct INTEGER
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    student_name TEXT,
    role TEXT NOT NULL,              -- user | assistant
    content TEXT NOT NULL,
    highlighted_text TEXT,
    topic_id INTEGER REFERENCES topics(id),
    flagged INTEGER DEFAULT 0,
    refused INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    student_name TEXT,
    highlighted_text TEXT,
    content TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,       -- also the key used in student_name columns
    role TEXT NOT NULL,              -- student | teacher
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS enrollments (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, course_id)
);
CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT DEFAULT CURRENT_TIMESTAMP,
    kind TEXT,
    lecture_id INTEGER,
    prompt TEXT,
    response TEXT,
    model TEXT,
    latency_ms INTEGER
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(courses)")}
        if "teacher_id" not in cols:  # added for the multi-user showcase; old DBs get it here
            conn.execute("ALTER TABLE courses ADD COLUMN teacher_id INTEGER REFERENCES users(id)")

        # Keep existing prototype databases compatible with newer quiz types.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(quizzes)").fetchall()}
        if "is_oral" not in columns:
            conn.execute("ALTER TABLE quizzes ADD COLUMN is_oral INTEGER DEFAULT 0")
        if "is_sample" not in columns:
            conn.execute("ALTER TABLE quizzes ADD COLUMN is_sample INTEGER DEFAULT 0")


def _get_or_create_user(conn: sqlite3.Connection, name: str, role: str) -> sqlite3.Row:
    """The user with this name (whatever its role), creating it with `role` if missing."""
    u = conn.execute("SELECT id, role FROM users WHERE name=?", (name,)).fetchone()
    if not u:
        conn.execute("INSERT INTO users (name, role) VALUES (?,?)", (name, role))
        u = conn.execute("SELECT id, role FROM users WHERE name=?", (name,)).fetchone()
    return u


def backfill_users() -> None:
    """Idempotent: turn existing free-text identities into users.
    Courses with a lecturer_name but no teacher_id get a teacher user; every student_name found in
    attempts / chat_messages / notes becomes a student user enrolled in that course."""
    with connect() as conn:
        for c in conn.execute("SELECT id, lecturer_name FROM courses WHERE teacher_id IS NULL "
                              "AND TRIM(COALESCE(lecturer_name,'')) != ''").fetchall():
            name = c["lecturer_name"].strip()
            u = _get_or_create_user(conn, name, "teacher")
            if u["role"] == "teacher":
                conn.execute("UPDATE courses SET teacher_id=? WHERE id=?", (u["id"], c["id"]))
        pairs = conn.execute("""
            SELECT DISTINCT a.student_name AS name, z.course_id AS cid
              FROM attempts a JOIN quizzes z ON z.id = a.quiz_id
            UNION SELECT DISTINCT m.student_name, l.course_id
              FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id
            UNION SELECT DISTINCT n.student_name, l.course_id
              FROM notes n JOIN lectures l ON l.id = n.lecture_id""").fetchall()
        for p in pairs:
            name = (p["name"] or "").strip()
            if not name or name == "Guest":
                continue
            u = _get_or_create_user(conn, name, "student")
            if u["role"] == "student":
                conn.execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?,?)",
                             (u["id"], p["cid"]))


def query(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def reset_db() -> None:
    """Delete the database file and recreate the schema (used by the seed script)."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
