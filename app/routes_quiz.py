"""Phase 2: quizzes (homework / live), QR codes, self-evaluation and the "lectures to review" report.

Contract: build plan section 5. Additions are listed in the Phase 2 entry of the Phase log.
Quiz generation reuses app.ingest.generate_questions() (prompts QUESTIONS_SYSTEM / QUESTIONS_USER).
"""
import io
import json
import os
import random
import socket

import qrcode
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.db import execute, query, query_one
from app.ingest import generate_questions

router = APIRouter(prefix="/api", tags=["quiz"])

SELF_EVAL_PER_LECTURE = 2
WEAK_THRESHOLD = 0.6  # a lecture scored below 60% is marked "Review this lecture"
KIND_LABEL = {"homework": "Homework", "live": "Live quiz", "self_eval": "Self-evaluation", "bank": "Question bank"}


# ------------------------------------------------------------------ helpers

def _lan_ip() -> str:
    """The machine's LAN IP (UDP-socket trick: connect() sends no packets, it only picks a route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def join_url(request: Request, qid: int) -> str:
    """URL phones on the same Wi-Fi can open. PUBLIC_BASE_URL in .env overrides the detection."""
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        base = f"http://{_lan_ip()}:{request.url.port or 8000}"
    return f"{base}/quiz/{qid}"


def _get_quiz(qid: int) -> dict:
    quiz = query_one("SELECT * FROM quizzes WHERE id=?", (qid,))
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    return quiz


def _question_lecture_ids(question_ids: list[int]) -> dict[int, int | None]:
    """question_id -> lecture_id. Uses the quiz's lecture, else the topic's lecture, else the bank
    question with the same text (self-eval questions are copies of bank questions)."""
    if not question_ids:
        return {}
    marks = ",".join("?" * len(question_ids))
    rows = query(f"""
        SELECT q.id, COALESCE(qz.lecture_id, t.lecture_id,
               (SELECT bz.lecture_id FROM questions bq JOIN quizzes bz ON bz.id = bq.quiz_id
                 WHERE bz.kind='bank' AND bz.course_id = qz.course_id AND bq.text = q.text LIMIT 1)) AS lecture_id
        FROM questions q JOIN quizzes qz ON qz.id = q.quiz_id
        LEFT JOIN topics t ON t.id = q.topic_id
        WHERE q.id IN ({marks})""", tuple(question_ids))
    return {r["id"]: r["lecture_id"] for r in rows}


# ------------------------------------------------------------------ create quiz (LLM)

class QuizCreate(BaseModel):
    kind: str = "homework"
    n: int = 5
    title: str | None = None


@router.post("/lectures/{lid}/quizzes")
def create_quiz(lid: int, body: QuizCreate):
    if body.kind not in ("homework", "live"):
        raise HTTPException(400, "kind must be 'homework' or 'live'")
    lec = query_one("SELECT id, title, status FROM lectures WHERE id=?", (lid,))
    if not lec:
        raise HTTPException(404, "Lecture not found")
    if lec["status"] != "ready":
        raise HTTPException(409, "The class day isn't ready yet (material still processing)")
    n = max(1, min(body.n, 15))
    title = body.title or f"{KIND_LABEL[body.kind]}: {lec['title']}"
    try:
        qid = generate_questions(lid, kind=body.kind, n=n, title=title, is_open=True)
    except Exception as e:  # LLM/provider failure (already in agent_logs)
        raise HTTPException(502, f"The AI provider failed: {type(e).__name__}: {str(e)[:200]}")
    if not query_one("SELECT 1 FROM questions WHERE quiz_id=?", (qid,)):
        execute("DELETE FROM quizzes WHERE id=?", (qid,))
        raise HTTPException(502, "The AI returned no valid questions, try again")
    return {"quiz_id": qid}


# ------------------------------------------------------------------ take a quiz

@router.get("/quizzes/{qid}")
def get_quiz(qid: int, request: Request):
    """Questions WITHOUT correct_index / explanation."""
    quiz = _get_quiz(qid)
    lec = query_one("SELECT id, title, number FROM lectures WHERE id=?", (quiz["lecture_id"],)) \
        if quiz["lecture_id"] else None
    course = query_one("SELECT id, name FROM courses WHERE id=?", (quiz["course_id"],))
    qs = query("SELECT id, topic_id, text, options_json FROM questions WHERE quiz_id=? ORDER BY id", (qid,))
    lec_ids = _question_lecture_ids([q["id"] for q in qs]) if quiz["kind"] == "self_eval" else {}
    titles = {l["id"]: l["title"] for l in query("SELECT id, title FROM lectures WHERE course_id=?",
                                                 (quiz["course_id"],))}
    return {
        "id": quiz["id"], "kind": quiz["kind"], "title": quiz["title"], "is_open": bool(quiz["is_open"]),
        "course_id": quiz["course_id"], "course_name": course["name"] if course else None,
        "lecture_id": quiz["lecture_id"], "lecture_title": lec["title"] if lec else None,
        "join_url": join_url(request, qid),
        "questions": [{
            "id": q["id"], "topic_id": q["topic_id"], "text": q["text"], "options": json.loads(q["options_json"]),
            "lecture_title": titles.get(lec_ids.get(q["id"])) if lec_ids else None,
        } for q in qs],
    }


class AnswerIn(BaseModel):
    question_id: int
    chosen_index: int | None = None


class AttemptIn(BaseModel):
    student_name: str = "Guest"
    answers: list[AnswerIn]


@router.post("/quizzes/{qid}/attempts")
def submit_attempt(qid: int, body: AttemptIn):
    quiz = _get_quiz(qid)
    if not quiz["is_open"]:
        raise HTTPException(403, "This quiz is closed")
    qs = {q["id"]: q for q in query("SELECT * FROM questions WHERE quiz_id=?", (qid,))}
    chosen = {a.question_id: a.chosen_index for a in body.answers if a.question_id in qs}
    name = (body.student_name or "Guest").strip()[:60] or "Guest"

    aid = execute("INSERT INTO attempts (quiz_id, student_name, score, total) VALUES (?,?,?,?)",
                  (qid, name, 0, len(qs)))
    results, score = [], 0
    for q_id, q in qs.items():  # unanswered questions count as wrong (stored with chosen_index NULL)
        c = chosen.get(q_id)
        ok = c is not None and c == q["correct_index"]
        score += ok
        execute("INSERT INTO answers (attempt_id, question_id, chosen_index, is_correct) VALUES (?,?,?,?)",
                (aid, q_id, c, int(ok)))
        results.append({"question_id": q_id, "chosen_index": c, "is_correct": ok,
                        "correct_index": q["correct_index"], "explanation": q["explanation"]})
    execute("UPDATE attempts SET score=? WHERE id=?", (score, aid))
    return {"attempt_id": aid, "score": score, "total": len(qs), "results": results}


# ------------------------------------------------------------------ QR + live results (projector)

@router.get("/quizzes/{qid}/qr")
def quiz_qr(qid: int, request: Request):
    _get_quiz(qid)
    img = qrcode.make(join_url(request, qid), box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/quizzes/{qid}/results")
def quiz_results(qid: int):
    """Aggregate results (for the live-quiz projector view). No student names."""
    quiz = _get_quiz(qid)
    agg = query_one("SELECT COUNT(*) AS n, AVG(score * 1.0 / NULLIF(total, 0)) AS avg FROM attempts WHERE quiz_id=?",
                    (qid,))
    per_q = query("""
        SELECT q.id, q.text, COUNT(a.id) AS n_answers, COALESCE(AVG(a.is_correct), 0) AS pct_correct
        FROM questions q LEFT JOIN answers a ON a.question_id = q.id
        WHERE q.quiz_id=? GROUP BY q.id ORDER BY q.id""", (qid,))
    return {"quiz_id": qid, "is_open": bool(quiz["is_open"]), "n_attempts": agg["n"],
            "avg_score": round(agg["avg"] or 0, 3), "questions": per_q}


# ------------------------------------------------------------------ student course home

@router.get("/courses/{cid}/open-quizzes")
def open_quizzes(cid: int, student_name: str | None = None):
    """Open homework quizzes of a course (for the student course home), with the student's best score."""
    rows = query("""
        SELECT qz.id, qz.title, qz.kind, qz.lecture_id, l.title AS lecture_title, l.number,
               (SELECT COUNT(*) FROM questions WHERE quiz_id = qz.id) AS n_questions
        FROM quizzes qz LEFT JOIN lectures l ON l.id = qz.lecture_id
        WHERE qz.course_id=? AND qz.kind='homework' AND qz.is_open=1
        ORDER BY l.number, qz.id""", (cid,))
    for r in rows:
        best = query_one("SELECT score, total FROM attempts WHERE quiz_id=? AND student_name=? "
                         "ORDER BY score DESC LIMIT 1", (r["id"], student_name)) if student_name else None
        r["best"] = best
    return rows


# ------------------------------------------------------------------ self-evaluation

class SelfEvalIn(BaseModel):
    student_name: str = "Guest"


@router.post("/courses/{cid}/self-eval")
def create_self_eval(cid: int, body: SelfEvalIn):
    """Sample SELF_EVAL_PER_LECTURE bank questions per ready lecture into a new self_eval quiz.
    No LLM call, so it opens instantly. Questions are copied (topic_id kept) so answers count for insights."""
    if not query_one("SELECT id FROM courses WHERE id=?", (cid,)):
        raise HTTPException(404, "Course not found")
    bank = query("""
        SELECT q.*, qz.lecture_id FROM questions q JOIN quizzes qz ON qz.id = q.quiz_id
        JOIN lectures l ON l.id = qz.lecture_id
        WHERE qz.course_id=? AND qz.kind='bank' AND l.status='ready'
        ORDER BY l.number, l.id, q.id""", (cid,))
    by_lecture: dict[int, list[dict]] = {}
    for q in bank:
        by_lecture.setdefault(q["lecture_id"], []).append(q)
    if not by_lecture:
        raise HTTPException(409, "No class day has a question bank yet")

    name = (body.student_name or "Guest").strip()[:60] or "Guest"
    qid = execute("INSERT INTO quizzes (course_id, lecture_id, kind, title, is_open) VALUES (?,?,?,?,1)",
                  (cid, None, "self_eval", f"Self-evaluation: {name}"))
    for questions in by_lecture.values():  # dict keeps lecture order
        for q in random.sample(questions, min(SELF_EVAL_PER_LECTURE, len(questions))):
            execute("INSERT INTO questions (quiz_id, topic_id, text, options_json, correct_index, explanation) "
                    "VALUES (?,?,?,?,?,?)",
                    (qid, q["topic_id"], q["text"], q["options_json"], q["correct_index"], q["explanation"]))
    return {"quiz_id": qid}


@router.get("/attempts/{aid}/report")
def attempt_report(aid: int):
    """Score per lecture; lectures under 60% are weak and link to their class-day page."""
    att = query_one("SELECT * FROM attempts WHERE id=?", (aid,))
    if not att:
        raise HTTPException(404, "Attempt not found")
    quiz = _get_quiz(att["quiz_id"])
    rows = query("""
        SELECT a.question_id, a.is_correct, t.name AS topic_name
        FROM answers a JOIN questions q ON q.id = a.question_id
        LEFT JOIN topics t ON t.id = q.topic_id
        WHERE a.attempt_id=? ORDER BY a.id""", (aid,))
    lec_ids = _question_lecture_ids([r["question_id"] for r in rows])
    lectures = {l["id"]: l for l in query("SELECT id, number, title FROM lectures WHERE course_id=?",
                                          (quiz["course_id"],))}

    per: dict[int, dict] = {}
    for r in rows:
        lid = lec_ids.get(r["question_id"])
        if lid not in lectures:
            continue
        p = per.setdefault(lid, {"lecture_id": lid, "number": lectures[lid]["number"],
                                 "title": lectures[lid]["title"], "score": 0, "total": 0,
                                 "url": f"/lecture/{lid}", "weak_topics": []})
        p["total"] += 1
        p["score"] += r["is_correct"]
        if not r["is_correct"] and r["topic_name"] and r["topic_name"] not in p["weak_topics"]:
            p["weak_topics"].append(r["topic_name"])
    per_lecture = sorted(per.values(), key=lambda p: (p["number"] is None, p["number"], p["lecture_id"]))
    for p in per_lecture:
        p["weak"] = p["score"] / p["total"] < WEAK_THRESHOLD
    return {"attempt_id": aid, "quiz_id": quiz["id"], "kind": quiz["kind"], "course_id": quiz["course_id"],
            "student_name": att["student_name"], "score": att["score"], "total": att["total"],
            "created_at": att["created_at"], "per_lecture": per_lecture}
