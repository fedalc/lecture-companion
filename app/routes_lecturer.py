"""Phase 3 owns this file: course creation, PDF upload, quiz management, insights.
Contract (build plan section 5). Upload flow: save PDF to data/uploads/{lecture_id}.pdf,
set lectures.slides_path, then BackgroundTasks.add_task(app.ingest.process_lecture, lid).
"""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app import insights
from app.db import UPLOAD_DIR, execute, query, query_one
from app.ingest import process_lecture

router = APIRouter(prefix="/api", tags=["lecturer"])

MAX_PDF_BYTES = 40 * 1024 * 1024


def _course(cid: int) -> dict:
    c = query_one("SELECT id, name, lecturer_name FROM courses WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Course not found")
    return c


# ------------------------------------------------------------------ courses + class days

class CourseIn(BaseModel):
    name: str
    lecturer_name: str = ""


@router.post("/courses")
def create_course(body: CourseIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Course name is required")
    cid = execute("INSERT INTO courses (name, lecturer_name) VALUES (?,?)", (name, body.lecturer_name.strip()))
    return {"id": cid, "name": name, "lecturer_name": body.lecturer_name.strip()}


@router.post("/courses/{cid}/lectures")
async def upload_lecture(cid: int, background: BackgroundTasks, title: str = Form(...),
                         date_: str = Form("", alias="date"), file: UploadFile = File(...)):
    _course(cid)
    title = title.strip()
    if not title:
        raise HTTPException(400, "Title is required")
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Please upload a PDF file")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF is too large (max 40 MB)")
    number = (query_one("SELECT MAX(number) AS m FROM lectures WHERE course_id=?", (cid,))["m"] or 0) + 1
    lid = execute("INSERT INTO lectures (course_id, number, title, date, status) VALUES (?,?,?,?,'uploaded')",
                  (cid, number, title, date_.strip() or date.today().isoformat()))
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"{lid}.pdf"
    dest.write_bytes(data)
    execute("UPDATE lectures SET slides_path=? WHERE id=?", (str(dest), lid))
    background.add_task(process_lecture, lid)
    return {"id": lid, "number": number, "title": title, "status": "uploaded"}


@router.post("/lectures/{lid}/regenerate")
def regenerate_lecture(lid: int, background: BackgroundTasks):
    """Re-run ingestion (e.g. after an 'error' status). Keeps the uploaded PDF."""
    lec = query_one("SELECT id, status FROM lectures WHERE id=?", (lid,))
    if not lec:
        raise HTTPException(404, "Lecture not found")
    if lec["status"] == "generating":
        raise HTTPException(409, "Already generating")
    execute("UPDATE lectures SET status='uploaded' WHERE id=?", (lid,))
    background.add_task(process_lecture, lid)
    return {"id": lid, "status": "uploaded"}


# ------------------------------------------------------------------ quizzes

@router.get("/courses/{cid}/quizzes")
def list_quizzes(cid: int, include_all: bool = False):
    """Homework and live quizzes (add ?include_all=true for bank and self-evaluation quizzes too)."""
    _course(cid)
    kinds = "" if include_all else "AND z.kind IN ('homework','live')"
    rows = query(f"""
        SELECT z.id, z.lecture_id, l.number AS lecture_number, l.title AS lecture_title, z.kind, z.title,
               z.is_open, z.created_at,
               (SELECT COUNT(*) FROM questions q WHERE q.quiz_id = z.id) AS n_questions,
               (SELECT COUNT(*) FROM attempts a WHERE a.quiz_id = z.id) AS n_attempts,
               (SELECT AVG(a.score * 1.0 / NULLIF(a.total, 0)) FROM attempts a WHERE a.quiz_id = z.id) AS avg_score
        FROM quizzes z LEFT JOIN lectures l ON l.id = z.lecture_id
        WHERE z.course_id = ? {kinds}
        ORDER BY z.created_at DESC, z.id DESC""", (cid,))
    for r in rows:
        r["is_open"] = bool(r["is_open"])
        r["avg_score"] = round(r["avg_score"], 3) if r["avg_score"] is not None else None
    return rows


class QuizPatch(BaseModel):
    is_open: bool | None = None
    title: str | None = None


@router.patch("/quizzes/{qid}")
def patch_quiz(qid: int, body: QuizPatch):
    if not query_one("SELECT id FROM quizzes WHERE id=?", (qid,)):
        raise HTTPException(404, "Quiz not found")
    if body.is_open is not None:
        execute("UPDATE quizzes SET is_open=? WHERE id=?", (int(body.is_open), qid))
    if body.title and body.title.strip():
        execute("UPDATE quizzes SET title=? WHERE id=?", (body.title.strip(), qid))
    q = query_one("SELECT id, kind, title, is_open FROM quizzes WHERE id=?", (qid,))
    q["is_open"] = bool(q["is_open"])
    return q


# ------------------------------------------------------------------ insights

@router.get("/courses/{cid}/insights")
def get_insights(cid: int):
    _course(cid)
    return insights.course_insights(cid)


class SummaryIn(BaseModel):
    topic_id: int | None = None


@router.post("/courses/{cid}/insights/misconceptions")
def misconceptions(cid: int, body: SummaryIn):
    _course(cid)
    try:
        return insights.summarise_misconceptions(cid, body.topic_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # LLM/provider failure (already in agent_logs)
        raise HTTPException(502, f"The AI provider failed: {type(e).__name__}: {str(e)[:200]}")
