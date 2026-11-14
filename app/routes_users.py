"""People for the showcase: students and teachers you can set up and "act as" (no auth, prototype).

  GET    /api/users?role=            -> [{id, name, role, course_ids}]
  GET    /api/users/{uid}            -> {id, name, role, course_ids}
  POST   /api/users                  {name | names:[...], role, course_ids?, new_courses?} -> user | [users]
  PATCH  /api/users/{uid}            {name?, course_ids?, new_courses?}
  (new_courses: names of courses to create and give to a teacher)
  DELETE /api/users/{uid}            (history rows stay, so insights don't change)
  POST   /api/users/join             {name, course_id?} -> get-or-create a student (QR joiners)

A user's name is the key stored in the existing student_name columns, so it is unique and a rename
is propagated to attempts / chat_messages / notes (students) or courses.lecturer_name (teachers).
Students are linked to courses through `enrollments`; a course has one teacher (`courses.teacher_id`).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect, execute, query, query_one

router = APIRouter(prefix="/api", tags=["users"])

ROLES = ("student", "teacher")


def _course_ids(u: dict) -> list[int]:
    if u["role"] == "teacher":
        rows = query("SELECT id FROM courses WHERE teacher_id=? ORDER BY id", (u["id"],))
    else:
        rows = query("SELECT course_id AS id FROM enrollments WHERE user_id=? ORDER BY course_id", (u["id"],))
    return [r["id"] for r in rows]


def _user(uid: int) -> dict:
    u = query_one("SELECT id, name, role FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(404, "User not found")
    u["course_ids"] = _course_ids(u)
    return u


def _clean_name(name: str) -> str:
    name = (name or "").strip()[:60]
    if not name:
        raise HTTPException(400, "Name is required")
    return name


def _set_courses(conn, uid: int, role: str, name: str, course_ids: list[int]) -> None:
    valid = {r[0] for r in conn.execute("SELECT id FROM courses")}
    ids = [c for c in dict.fromkeys(course_ids) if c in valid]
    if role == "student":
        conn.execute("DELETE FROM enrollments WHERE user_id=?", (uid,))
        conn.executemany("INSERT INTO enrollments (user_id, course_id) VALUES (?,?)", [(uid, c) for c in ids])
    else:
        conn.execute("UPDATE courses SET teacher_id=NULL, lecturer_name='' WHERE teacher_id=?", (uid,))
        conn.executemany("UPDATE courses SET teacher_id=?, lecturer_name=? WHERE id=?", [(uid, name, c) for c in ids])


def _add_new_courses(conn, uid: int, role: str, name: str, new_courses: list[str] | None) -> None:
    """Create courses owned by this teacher (ignored for students)."""
    if role != "teacher":
        return
    for title in dict.fromkeys((c or "").strip()[:120] for c in new_courses or []):
        if title:
            conn.execute("INSERT INTO courses (name, lecturer_name, teacher_id) VALUES (?,?,?)", (title, name, uid))


@router.get("/users")
def list_users(role: str | None = None):
    sql, params = "SELECT id, name, role FROM users", ()
    if role:
        sql, params = sql + " WHERE role=?", (role,)
    users = query(sql + " ORDER BY role DESC, name COLLATE NOCASE", params)
    enr: dict[int, list[int]] = {}
    for r in query("SELECT user_id, course_id FROM enrollments ORDER BY course_id"):
        enr.setdefault(r["user_id"], []).append(r["course_id"])
    for r in query("SELECT teacher_id, id FROM courses WHERE teacher_id IS NOT NULL ORDER BY id"):
        enr.setdefault(r["teacher_id"], []).append(r["id"])
    for u in users:
        u["course_ids"] = enr.get(u["id"], [])
    return users


@router.get("/users/{uid}")
def get_user(uid: int):
    return _user(uid)


class UserIn(BaseModel):
    name: str = ""
    names: list[str] | None = None   # bulk add: one user per name (duplicates are skipped)
    role: str = "student"
    course_ids: list[int] = []
    new_courses: list[str] = []      # teachers only: courses to create for them


@router.post("/users")
def create_user(body: UserIn):
    if body.role not in ROLES:
        raise HTTPException(400, "role must be 'student' or 'teacher'")
    if body.names is not None:
        created = []
        with connect() as conn:
            for raw in body.names:
                name = (raw or "").strip()[:60]
                if not name or conn.execute("SELECT 1 FROM users WHERE name=?", (name,)).fetchone():
                    continue
                uid = conn.execute("INSERT INTO users (name, role) VALUES (?,?)", (name, body.role)).lastrowid
                _set_courses(conn, uid, body.role, name, body.course_ids)
                _add_new_courses(conn, uid, body.role, name, body.new_courses)
                created.append(uid)
        return [_user(uid) for uid in created]
    name = _clean_name(body.name)
    if query_one("SELECT 1 FROM users WHERE name=?", (name,)):
        raise HTTPException(409, f"'{name}' already exists")
    with connect() as conn:
        uid = conn.execute("INSERT INTO users (name, role) VALUES (?,?)", (name, body.role)).lastrowid
        _set_courses(conn, uid, body.role, name, body.course_ids)
        _add_new_courses(conn, uid, body.role, name, body.new_courses)
    return _user(uid)


class UserPatch(BaseModel):
    name: str | None = None
    course_ids: list[int] | None = None
    new_courses: list[str] | None = None


@router.patch("/users/{uid}")
def patch_user(uid: int, body: UserPatch):
    u = _user(uid)
    name = u["name"]
    with connect() as conn:
        if body.name is not None and body.name.strip() != u["name"]:
            name = _clean_name(body.name)
            if conn.execute("SELECT 1 FROM users WHERE name=? AND id!=?", (name, uid)).fetchone():
                raise HTTPException(409, f"'{name}' already exists")
            conn.execute("UPDATE users SET name=? WHERE id=?", (name, uid))
            if u["role"] == "student":
                for table in ("attempts", "chat_messages", "notes"):
                    conn.execute(f"UPDATE {table} SET student_name=? WHERE student_name=?", (name, u["name"]))
            else:
                conn.execute("UPDATE courses SET lecturer_name=? WHERE teacher_id=?", (name, uid))
        if body.course_ids is not None:
            _set_courses(conn, uid, u["role"], name, body.course_ids)
        _add_new_courses(conn, uid, u["role"], name, body.new_courses)
    return _user(uid)


@router.delete("/users/{uid}")
def delete_user(uid: int):
    u = _user(uid)
    with connect() as conn:
        conn.execute("DELETE FROM enrollments WHERE user_id=?", (uid,))
        if u["role"] == "teacher":
            conn.execute("UPDATE courses SET teacher_id=NULL, lecturer_name='' WHERE teacher_id=?", (uid,))
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
    return {"ok": True}


class JoinIn(BaseModel):
    name: str
    course_id: int | None = None


@router.post("/users/join")
def join(body: JoinIn):
    """Get-or-create a student by name (e.g. someone who scanned a QR code), enrolled in course_id."""
    name = _clean_name(body.name)
    u = query_one("SELECT id, role FROM users WHERE name=?", (name,))
    if u and u["role"] != "student":
        raise HTTPException(409, f"'{name}' is a teacher")
    uid = u["id"] if u else execute("INSERT INTO users (name, role) VALUES (?, 'student')", (name,))
    if body.course_id and query_one("SELECT 1 FROM courses WHERE id=?", (body.course_id,)):
        execute("INSERT OR IGNORE INTO enrollments (user_id, course_id) VALUES (?,?)", (uid, body.course_id))
    return _user(uid)
