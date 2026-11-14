"""Phase 1 owns this file: tutor chat + notes.
Contract (build plan section 5):
  POST /api/lectures/{lid}/chat   {student_name, message, highlighted_text?} -> {reply, topic_id, flagged, refused}
  GET  /api/lectures/{lid}/chat?student_name=
  GET/POST /api/lectures/{lid}/notes
Addition: DELETE /api/notes/{nid}

Guardrail: if the lecture has an OPEN homework quiz and the student's message closely matches one of its
questions, the tutor is never asked for an answer. A separate refusal prompt explains the concept and is
given only the question text (never the options or the correct index), so the answer key cannot leak.
"""
import difflib
import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import prompts
from app.db import execute, query, query_one
from app.llm import complete, complete_json

router = APIRouter(prefix="/api", tags=["chat"])

HISTORY_TURNS = 8
MATCH_THRESHOLD = 0.6
MAX_MATERIAL_CHARS = 60_000

STOPWORDS = set("""the and for are but not you your with this that what which who whom how why when where
does did can could would should will from into about than then them they their there these those its it's
was were been being have has had any all some one two out our more most such only own same very just also
is of to in on at by as an or be a i me my we do so if no
statement statements best describes describe following true false correct option options answer question""".split())


class ChatIn(BaseModel):
    student_name: str = "Guest"
    message: str
    highlighted_text: str | None = None


class NoteIn(BaseModel):
    student_name: str = "Guest"
    highlighted_text: str | None = None
    content: str


# ---------------------------------------------------------------- guardrail helpers

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def _tokens(s: str) -> set[str]:
    return {w for w in _norm(s).split() if len(w) >= 3 and w not in STOPWORDS}


def homework_match_score(message: str, question: str) -> float:
    """max(fuzzy ratio, share of the question's content words that appear in the message).
    The ratio only counts when the message is about as long as the question (a pasted/paraphrased
    question), and containment only for questions with >= 3 content words, so short study questions
    like "What is X?" are not refused."""
    m, q = _norm(message), _norm(question)
    if not m or not q:
        return 0.0
    ratio = difflib.SequenceMatcher(None, m, q).ratio() if len(m) >= 0.6 * len(q) else 0.0
    qt = _tokens(question)
    containment = len(qt & _tokens(message)) / len(qt) if len(qt) >= 3 else 0.0
    return max(ratio, containment)


def find_open_homework_question(lid: int, text: str) -> dict | None:
    rows = query("SELECT q.id, q.text, q.topic_id FROM questions q JOIN quizzes z ON z.id = q.quiz_id "
                 "WHERE z.lecture_id=? AND z.kind='homework' AND z.is_open=1", (lid,))
    best, best_score = None, 0.0
    for r in rows:
        s = homework_match_score(text, r["text"])
        if s > best_score:
            best, best_score = r, s
    return best if best_score >= MATCH_THRESHOLD else None


# ---------------------------------------------------------------- chat

def _lecture_or_404(lid: int) -> dict:
    lec = query_one("SELECT * FROM lectures WHERE id=?", (lid,))
    if not lec:
        raise HTTPException(404, "Lecture not found")
    return lec


@router.post("/lectures/{lid}/chat")
def chat(lid: int, body: ChatIn):
    lec = _lecture_or_404(lid)
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Empty message")
    highlight = (body.highlighted_text or "").strip() or None
    student = body.student_name.strip() or "Guest"

    topics = query("SELECT id, name, summary FROM topics WHERE lecture_id=?", (lid,))
    topic_ids = {t["id"] for t in topics}
    topics_json = json.dumps(topics, ensure_ascii=False)
    material = (lec["material_text"] or "")[:MAX_MATERIAL_CHARS]

    history_rows = query("SELECT role, content FROM chat_messages WHERE lecture_id=? AND student_name=? "
                         "ORDER BY id DESC LIMIT ?", (lid, student, HISTORY_TURNS))[::-1]
    history = "\n".join(f"{r['role'].upper()}: {r['content']}" for r in history_rows) or "(none)"

    user_msg_id = execute("INSERT INTO chat_messages (lecture_id, student_name, role, content, highlighted_text) "
                          "VALUES (?,?,?,?,?)", (lid, student, "user", message, highlight))

    flagged = refused = False
    hw = find_open_homework_question(lid, message + " " + (highlight or ""))
    if hw:
        refused = True
        topic_id = hw["topic_id"]
        reply = complete(prompts.REFUSAL_SYSTEM,
                         prompts.REFUSAL_USER.format(material=material, topics_json=topics_json,
                                                     question=hw["text"], message=message),
                         kind="refusal", lecture_id=lid)
    else:
        user_prompt = prompts.TUTOR_USER.format(
            material=material, lecture=lec["lecture_md"] or "", topics_json=topics_json,
            history=history, highlight=highlight or "", message=message)
        try:
            out = complete_json(prompts.TUTOR_SYSTEM, user_prompt,
                                schema_hint='{"reply": str, "covered": bool, "topic_id": int|null}',
                                kind="tutor", lecture_id=lid)
            reply = str(out.get("reply") or "").strip()
            flagged = out.get("covered") is False
            topic_id = out.get("topic_id")
        except Exception:
            reply, topic_id = "", None
        if not reply:  # JSON failed: fall back to a plain-text answer
            reply = complete(prompts.TUTOR_SYSTEM, user_prompt, kind="chat", lecture_id=lid)
        try:
            topic_id = int(topic_id) if topic_id is not None else None
        except (TypeError, ValueError):
            topic_id = None
        if topic_id not in topic_ids:
            topic_id = None

    execute("UPDATE chat_messages SET topic_id=?, flagged=?, refused=? WHERE id=?",
            (topic_id, int(flagged), int(refused), user_msg_id))
    execute("INSERT INTO chat_messages (lecture_id, student_name, role, content, topic_id, flagged, refused) "
            "VALUES (?,?,?,?,?,?,?)", (lid, student, "assistant", reply, topic_id, int(flagged), int(refused)))
    return {"reply": reply, "topic_id": topic_id, "flagged": flagged, "refused": refused}


@router.get("/lectures/{lid}/chat")
def chat_history(lid: int, student_name: str = "Guest"):
    rows = query("SELECT id, role, content, highlighted_text, topic_id, flagged, refused, created_at "
                 "FROM chat_messages WHERE lecture_id=? AND student_name=? ORDER BY id", (lid, student_name))
    for r in rows:
        r["flagged"], r["refused"] = bool(r["flagged"]), bool(r["refused"])
    return rows


# ---------------------------------------------------------------- notes

@router.get("/lectures/{lid}/notes")
def list_notes(lid: int, student_name: str = "Guest"):
    return query("SELECT id, highlighted_text, content, created_at FROM notes "
                 "WHERE lecture_id=? AND student_name=? ORDER BY id DESC", (lid, student_name))


@router.post("/lectures/{lid}/notes")
def add_note(lid: int, body: NoteIn):
    _lecture_or_404(lid)
    if not body.content.strip():
        raise HTTPException(400, "Empty note")
    nid = execute("INSERT INTO notes (lecture_id, student_name, highlighted_text, content) VALUES (?,?,?,?)",
                  (lid, body.student_name.strip() or "Guest", (body.highlighted_text or "").strip() or None,
                   body.content.strip()))
    return query_one("SELECT id, highlighted_text, content, created_at FROM notes WHERE id=?", (nid,))


@router.delete("/notes/{nid}")
def delete_note(nid: int, student_name: str = "Guest"):
    execute("DELETE FROM notes WHERE id=? AND student_name=?", (nid, student_name))
    return {"ok": True}
