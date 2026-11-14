"""Turn an uploaded PDF into a ready class day:
PDF -> material_text -> AI lecture (markdown) -> topics -> question bank (quiz kind='bank').

    from app.ingest import process_lecture
    process_lecture(lecture_id)   # safe to run as a FastAPI BackgroundTask
"""
import json
import traceback

from pypdf import PdfReader

from app import prompts
from app.db import execute, query, query_one
from app.llm import complete, complete_json

BANK_SIZE = 6
MAX_MATERIAL_CHARS = 60_000  # keep prompts a sane size


def extract_pdf_text(path: str) -> str:
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"--- Slide {i} ---\n{text}")
    return "\n\n".join(pages)


def process_lecture(lecture_id: int) -> None:
    lec = query_one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
    if not lec:
        return
    course = query_one("SELECT * FROM courses WHERE id=?", (lec["course_id"],))
    execute("UPDATE lectures SET status='generating' WHERE id=?", (lecture_id,))
    try:
        # 1. material
        material = lec["material_text"] or extract_pdf_text(lec["slides_path"])
        material = material[:MAX_MATERIAL_CHARS]
        if not material.strip():
            raise ValueError("No text could be extracted from the PDF (scanned slides?)")
        execute("UPDATE lectures SET material_text=? WHERE id=?", (material, lecture_id))

        # 2. AI lecture
        lecture_md = complete(
            prompts.LECTURE_SYSTEM,
            prompts.LECTURE_USER.format(course=course["name"], number=lec["number"],
                                        title=lec["title"], material=material),
            kind="lecture", lecture_id=lecture_id)
        execute("UPDATE lectures SET lecture_md=? WHERE id=?", (lecture_md, lecture_id))

        # 3. topics (replace any previous ones)
        old_topics = [t["id"] for t in query("SELECT id FROM topics WHERE lecture_id=?", (lecture_id,))]
        data = complete_json(prompts.TOPICS_SYSTEM, prompts.TOPICS_USER.format(material=material),
                             schema_hint='{"topics":[{"name":str,"summary":str}]}',
                             kind="topics", lecture_id=lecture_id)
        topics = []
        for t in data.get("topics", [])[:6]:
            tid = execute("INSERT INTO topics (lecture_id, name, summary) VALUES (?,?,?)",
                          (lecture_id, t["name"], t.get("summary", "")))
            topics.append({"id": tid, "name": t["name"], "summary": t.get("summary", "")})

        # 4. question bank
        old_banks = [q["id"] for q in query(
            "SELECT id FROM quizzes WHERE lecture_id=? AND kind='bank'", (lecture_id,))]
        generate_questions(lecture_id, kind="bank", n=BANK_SIZE,
                           title=f"Question bank: {lec['title']}", topics=topics, material=material)
        _cleanup(old_banks, old_topics)

        execute("UPDATE lectures SET status='ready' WHERE id=?", (lecture_id,))
    except Exception:
        traceback.print_exc()
        execute("UPDATE lectures SET status='error' WHERE id=?", (lecture_id,))


def generate_questions(lecture_id: int, kind: str, n: int, title: str,
                       topics: list[dict] | None = None, material: str | None = None,
                       is_open: bool = True) -> int:
    """Create a quiz of `n` LLM-generated questions for a lecture. Returns quiz_id.
    Phase 2 can reuse this for homework/live quizzes."""
    lec = query_one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
    topics = topics or query("SELECT id, name, summary FROM topics WHERE lecture_id=?", (lecture_id,))
    material = material or lec["material_text"]
    valid_ids = {t["id"] for t in topics}

    data = complete_json(
        prompts.QUESTIONS_SYSTEM,
        prompts.QUESTIONS_USER.format(material=material, topics_json=json.dumps(topics), n=n),
        schema_hint='{"questions":[{"topic_id":int,"text":str,"options":[str,str,str,str],'
                    '"correct_index":int,"explanation":str}]}',
        kind="questions", lecture_id=lecture_id)

    quiz_id = execute("INSERT INTO quizzes (course_id, lecture_id, kind, title, is_open) VALUES (?,?,?,?,?)",
                      (lec["course_id"], lecture_id, kind, title, int(is_open)))
    for q in data.get("questions", [])[:n]:
        opts = q.get("options", [])
        ci = q.get("correct_index", 0)
        if len(opts) < 2 or not (0 <= ci < len(opts)):
            continue  # guardrail: drop malformed questions
        tid = q.get("topic_id") if q.get("topic_id") in valid_ids else None
        execute("INSERT INTO questions (quiz_id, topic_id, text, options_json, correct_index, explanation) "
                "VALUES (?,?,?,?,?,?)",
                (quiz_id, tid, q["text"], json.dumps(opts), ci, q.get("explanation", "")))
    return quiz_id


def _cleanup(quiz_ids: list[int], topic_ids: list[int]) -> None:
    """Remove a previous generation's bank and topics when a lecture is regenerated."""
    for qid in quiz_ids:
        execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE quiz_id=?)", (qid,))
        execute("DELETE FROM questions WHERE quiz_id=?", (qid,))
        execute("DELETE FROM attempts WHERE quiz_id=?", (qid,))
        execute("DELETE FROM quizzes WHERE id=?", (qid,))
    for tid in topic_ids:
        execute("UPDATE questions SET topic_id=NULL WHERE topic_id=?", (tid,))
        execute("UPDATE chat_messages SET topic_id=NULL WHERE topic_id=?", (tid,))
        execute("DELETE FROM topics WHERE id=?", (tid,))
