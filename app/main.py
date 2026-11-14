"""FastAPI entry point.  Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import llm, routes_chat, routes_lecturer, routes_quiz
from app.db import init_db, query, query_one

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="AI Lecture Companion")


@app.on_event("startup")
def _startup():
    init_db()


# ------------------------------------------------------------------ routers owned by other phases
app.include_router(routes_chat.router)      # Phase 1
app.include_router(routes_quiz.router)      # Phase 2
app.include_router(routes_lecturer.router)  # Phase 3


# ------------------------------------------------------------------ shared API (Phase 0)

@app.get("/api/health")
def health():
    return {"ok": True, "llm_provider": llm.PROVIDER, "model": llm.MODEL}


@app.get("/api/courses")
def list_courses():
    return query("SELECT id, name, lecturer_name FROM courses ORDER BY id")


@app.get("/api/student/dashboard")
def student_dashboard(student_name: str = "Guest"):
    """Open quizzes, homework and exams the named student has not attempted yet."""
    name = (student_name or "Guest").strip()[:60] or "Guest"
    tasks = query("""
        SELECT qz.id, qz.title, qz.kind, qz.course_id, c.name AS course_name,
               qz.lecture_id, l.title AS lecture_title, l.number, qz.is_oral, qz.is_sample,
               (SELECT COUNT(*) FROM questions WHERE quiz_id=qz.id) AS n_questions
        FROM quizzes qz
        JOIN courses c ON c.id=qz.course_id
        LEFT JOIN lectures l ON l.id=qz.lecture_id
        WHERE qz.kind IN ('live', 'homework', 'exam') AND qz.is_open=1
          AND NOT EXISTS (
              SELECT 1 FROM attempts a WHERE a.quiz_id=qz.id AND a.student_name=?
          )
          AND EXISTS (SELECT 1 FROM questions WHERE quiz_id=qz.id)
        ORDER BY c.name, l.number, qz.id
    """, (name,))
    return {
        "courses": query("SELECT id, name, lecturer_name FROM courses ORDER BY id"),
        "tasks": tasks,
    }


@app.get("/api/courses/{cid}")
def get_course(cid: int):
    c = query_one("SELECT id, name, lecturer_name FROM courses WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Course not found")
    return c


@app.get("/api/courses/{cid}/lectures")
def list_lectures(cid: int):
    return query("SELECT id, number, title, date, status FROM lectures WHERE course_id=? "
                 "ORDER BY number, id", (cid,))


@app.get("/api/lectures/{lid}")
def get_lecture(lid: int):
    lec = query_one("SELECT id, course_id, number, title, date, lecture_md, status "
                    "FROM lectures WHERE id=?", (lid,))
    if not lec:
        raise HTTPException(404, "Lecture not found")
    lec["topics"] = query("SELECT id, name, summary FROM topics WHERE lecture_id=? ORDER BY id", (lid,))
    return lec


@app.get("/api/lectures/{lid}/slides")
def get_slides(lid: int):
    lec = query_one("SELECT slides_path FROM lectures WHERE id=?", (lid,))
    if not lec or not lec["slides_path"] or not Path(lec["slides_path"]).exists():
        raise HTTPException(404, "Slides not found")
    return FileResponse(lec["slides_path"], media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


# ------------------------------------------------------------------ pages

def _page(name: str):
    return FileResponse(STATIC / name)


@app.get("/")
def page_home():
    return _page("index.html")


@app.get("/course/{cid}")
def page_course(cid: int):
    return _page("course.html")


@app.get("/lecture/{lid}")
def page_lecture(lid: int):
    return _page("lecture.html")


@app.get("/quiz/{qid}")
def page_quiz(qid: int):
    return _page("quiz.html")


@app.get("/selfeval/{cid}")
def page_selfeval(cid: int):
    return _page("selfeval.html")


@app.get("/lecturer")
def page_lecturer():
    return _page("lecturer.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
