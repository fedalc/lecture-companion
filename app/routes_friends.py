"""Friend search and requests for the local multi-user student prototype."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import execute, query, query_one

router = APIRouter(prefix="/api/students", tags=["friends"])


def _student(uid: int) -> dict:
    user = query_one("SELECT id, name FROM users WHERE id=? AND role='student'", (uid,))
    if not user:
        raise HTTPException(404, "Student not found")
    return user


@router.get("/search")
def search_students(q: str, student_id: int):
    me = _student(student_id)
    term = q.strip()[:40]
    if len(term) < 2:
        return []
    return query("""
        SELECT u.id, u.name,
          (SELECT r.status FROM friend_requests r
           WHERE (r.from_user_id=? AND r.to_user_id=u.id) OR (r.from_user_id=u.id AND r.to_user_id=?)
           ORDER BY CASE r.status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END LIMIT 1) AS relationship
        FROM users u WHERE u.role='student' AND u.id!=? AND u.name LIKE ? COLLATE NOCASE
        ORDER BY u.name COLLATE NOCASE LIMIT 12
    """, (student_id, student_id, student_id, f"%{term}%"))


class RequestIn(BaseModel):
    from_user_id: int
    to_user_id: int


@router.post("/friend-requests")
def send_request(body: RequestIn):
    _student(body.from_user_id)
    target = _student(body.to_user_id)
    if body.from_user_id == body.to_user_id:
        raise HTTPException(400, "You can't add yourself")
    existing = query_one("""SELECT id,status FROM friend_requests WHERE
        ((from_user_id=? AND to_user_id=?) OR (from_user_id=? AND to_user_id=?))
        AND status IN ('pending','accepted') LIMIT 1""",
        (body.from_user_id, body.to_user_id, body.to_user_id, body.from_user_id))
    if existing:
        raise HTTPException(409, "A request or friendship already exists")
    execute("""INSERT INTO friend_requests (from_user_id,to_user_id,status,created_at,updated_at)
        VALUES (?,?, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(from_user_id,to_user_id) DO UPDATE SET status='pending', updated_at=CURRENT_TIMESTAMP""",
        (body.from_user_id, body.to_user_id))
    return {"sent": True, "to_name": target["name"]}


@router.get("/friends")
def list_friends(student_id: int):
    _student(student_id)
    return query("""SELECT r.id AS request_id, u.id, u.name FROM friend_requests r
        JOIN users u ON u.id=CASE WHEN r.from_user_id=? THEN r.to_user_id ELSE r.from_user_id END
        WHERE r.status='accepted' AND (r.from_user_id=? OR r.to_user_id=?)
        ORDER BY u.name COLLATE NOCASE""", (student_id, student_id, student_id))


@router.get("/friend-requests")
def list_requests(student_id: int):
    _student(student_id)
    return {
        "incoming": query("""SELECT r.id,u.name FROM friend_requests r JOIN users u ON u.id=r.from_user_id
            WHERE r.to_user_id=? AND r.status='pending' ORDER BY r.id DESC""", (student_id,)),
        "outgoing": query("""SELECT r.id,u.name FROM friend_requests r JOIN users u ON u.id=r.to_user_id
            WHERE r.from_user_id=? AND r.status='pending' ORDER BY r.id DESC""", (student_id,)),
    }


class RequestAction(BaseModel):
    student_id: int
    action: str


@router.patch("/friend-requests/{request_id}")
def answer_request(request_id: int, body: RequestAction):
    _student(body.student_id)
    if body.action not in ("accept", "decline"):
        raise HTTPException(400, "Action must be accept or decline")
    row = query_one("SELECT id FROM friend_requests WHERE id=? AND to_user_id=? AND status='pending'",
                    (request_id, body.student_id))
    if not row:
        raise HTTPException(404, "Incoming request not found")
    status = "accepted" if body.action == "accept" else "declined"
    execute("UPDATE friend_requests SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, request_id))
    return {"id": request_id, "status": status}


@router.delete("/friends/{request_id}")
def remove_friend(request_id: int, student_id: int):
    _student(student_id)
    row = query_one("""SELECT id FROM friend_requests WHERE id=? AND status='accepted'
        AND (from_user_id=? OR to_user_id=?)""", (request_id, student_id, student_id))
    if not row:
        raise HTTPException(404, "Friendship not found")
    execute("UPDATE friend_requests SET status='declined', updated_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
    return {"removed": True}
