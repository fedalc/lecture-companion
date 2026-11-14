"""Friends between students: requests, accept/decline, and who is online.

  GET    /api/users/{uid}/friends            -> {friends:[{id,name,online,last_seen}], incoming:[...], outgoing:[...], n_online}
  POST   /api/users/{uid}/friends            {to_id} -> send a request (accepts it if `to_id` already asked you)
  POST   /api/users/{uid}/friends/{oid}/accept
  DELETE /api/users/{uid}/friends/{oid}      decline / cancel / unfriend
  POST   /api/users/{uid}/seen               heartbeat; "online" = seen in the last ONLINE_MINUTES

One row per pair in `friendships` (requester -> addressee), status pending | accepted.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect, execute, query, query_one

router = APIRouter(prefix="/api", tags=["friends"])

ONLINE_MINUTES = 3


def _student(uid: int) -> dict:
    u = query_one("SELECT id, name, role FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(404, "User not found")
    if u["role"] != "student":
        raise HTTPException(400, "Only students have friends")
    return u


@router.post("/users/{uid}/seen")
def seen(uid: int):
    execute("UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE id=?", (uid,))
    return {"ok": True}


@router.get("/users/{uid}/friends")
def list_friends(uid: int):
    _student(uid)
    online = f"(u.last_seen IS NOT NULL AND u.last_seen >= datetime('now', '-{ONLINE_MINUTES} minutes'))"
    friends = query(f"""
        SELECT u.id, u.name, u.last_seen, {online} AS online FROM friendships f
          JOIN users u ON u.id = CASE WHEN f.requester_id=? THEN f.addressee_id ELSE f.requester_id END
         WHERE f.status='accepted' AND (f.requester_id=? OR f.addressee_id=?)
         ORDER BY online DESC, u.name COLLATE NOCASE""", (uid, uid, uid))
    for f in friends:
        f["online"] = bool(f["online"])
    incoming = query("""SELECT u.id, u.name, f.created_at FROM friendships f JOIN users u ON u.id=f.requester_id
                         WHERE f.addressee_id=? AND f.status='pending' ORDER BY f.created_at DESC""", (uid,))
    outgoing = query("""SELECT u.id, u.name, f.created_at FROM friendships f JOIN users u ON u.id=f.addressee_id
                         WHERE f.requester_id=? AND f.status='pending' ORDER BY f.created_at DESC""", (uid,))
    return {"friends": friends, "incoming": incoming, "outgoing": outgoing,
            "n_online": sum(f["online"] for f in friends)}


class RequestIn(BaseModel):
    to_id: int


@router.post("/users/{uid}/friends")
def send_request(uid: int, body: RequestIn):
    _student(uid)
    _student(body.to_id)
    if uid == body.to_id:
        raise HTTPException(400, "You can't befriend yourself")
    with connect() as conn:
        mine = conn.execute("SELECT status FROM friendships WHERE requester_id=? AND addressee_id=?",
                            (uid, body.to_id)).fetchone()
        theirs = conn.execute("SELECT status FROM friendships WHERE requester_id=? AND addressee_id=?",
                              (body.to_id, uid)).fetchone()
        if theirs:  # they already asked (or you're friends): accept
            conn.execute("UPDATE friendships SET status='accepted' WHERE requester_id=? AND addressee_id=?",
                         (body.to_id, uid))
            return {"status": "accepted"}
        if mine:
            return {"status": mine["status"]}
        conn.execute("INSERT INTO friendships (requester_id, addressee_id) VALUES (?,?)", (uid, body.to_id))
    return {"status": "pending"}


@router.post("/users/{uid}/friends/{oid}/accept")
def accept(uid: int, oid: int):
    with connect() as conn:
        cur = conn.execute("UPDATE friendships SET status='accepted' "
                           "WHERE requester_id=? AND addressee_id=? AND status='pending'", (oid, uid))
        if not cur.rowcount:
            raise HTTPException(404, "No pending request from this user")
    return {"status": "accepted"}


@router.delete("/users/{uid}/friends/{oid}")
def remove(uid: int, oid: int):
    execute("DELETE FROM friendships WHERE (requester_id=? AND addressee_id=?) OR (requester_id=? AND addressee_id=?)",
            (uid, oid, oid, uid))
    return {"ok": True}
