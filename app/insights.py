"""Phase 3 owns this file: per-topic struggle statistics for the lecturer dashboard.

struggle_score = 0.6 * error_rate + 0.3 * norm(n_questions) + 0.1 * norm(n_flagged)
where norm(x) = x / max(x over the course's topics).

- error_rate: wrong answers / answers, over every quiz question tagged to the topic
  (homework, live, self-evaluation, bank). Unanswered questions count as wrong (Phase 2 stores them that way).
- n_questions: student chat messages (role='user') tagged to the topic.
- n_flagged: those of them that the tutor flagged as "not covered by the material".
"""
import json

from app import prompts
from app.db import query, query_one
from app.llm import complete


def course_insights(cid: int) -> dict:
    topics = query("""
        SELECT t.id AS topic_id, t.name, t.summary, l.id AS lecture_id, l.number AS lecture_number,
               l.title AS lecture_title
        FROM topics t JOIN lectures l ON l.id = t.lecture_id
        WHERE l.course_id = ? ORDER BY l.number, t.id""", (cid,))

    ans = {r["topic_id"]: r for r in query("""
        SELECT q.topic_id, COUNT(a.id) AS n, SUM(CASE WHEN a.is_correct THEN 0 ELSE 1 END) AS wrong
        FROM answers a JOIN questions q ON q.id = a.question_id
        JOIN topics t ON t.id = q.topic_id JOIN lectures l ON l.id = t.lecture_id
        WHERE l.course_id = ? GROUP BY q.topic_id""", (cid,))}

    chat = {r["topic_id"]: r for r in query("""
        SELECT m.topic_id, COUNT(*) AS n, SUM(m.flagged) AS flagged
        FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id
        WHERE l.course_id = ? AND m.role = 'user' AND m.topic_id IS NOT NULL
        GROUP BY m.topic_id""", (cid,))}

    for t in topics:
        a = ans.get(t["topic_id"]) or {"n": 0, "wrong": 0}
        c = chat.get(t["topic_id"]) or {"n": 0, "flagged": 0}
        t["n_answers"] = a["n"]
        t["error_rate"] = round((a["wrong"] or 0) / a["n"], 3) if a["n"] else 0.0
        t["n_questions"] = c["n"]
        t["n_flagged"] = c["flagged"] or 0

    max_q = max((t["n_questions"] for t in topics), default=0) or 1
    max_f = max((t["n_flagged"] for t in topics), default=0) or 1
    for t in topics:
        t["struggle_score"] = round(0.6 * t["error_rate"] + 0.3 * t["n_questions"] / max_q
                                    + 0.1 * t["n_flagged"] / max_f, 3)
    topics.sort(key=lambda t: t["struggle_score"], reverse=True)

    flagged = query("""
        SELECT m.id, m.lecture_id, l.number AS lecture_number, l.title AS lecture_title, m.content,
               m.highlighted_text, m.topic_id, t.name AS topic_name, m.created_at
        FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id LEFT JOIN topics t ON t.id = m.topic_id
        WHERE l.course_id = ? AND m.role = 'user' AND m.flagged = 1
        ORDER BY m.created_at DESC, m.id DESC LIMIT 50""", (cid,))

    recent = query("""
        SELECT m.id, m.lecture_id, l.number AS lecture_number, l.title AS lecture_title, m.content,
               m.topic_id, t.name AS topic_name, m.flagged, m.refused, m.created_at
        FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id LEFT JOIN topics t ON t.id = m.topic_id
        WHERE l.course_id = ? AND m.role = 'user'
        ORDER BY m.created_at DESC, m.id DESC LIMIT 30""", (cid,))

    totals = query_one("""
        SELECT
          (SELECT COUNT(DISTINCT student_name) FROM (
              SELECT a.student_name FROM attempts a JOIN quizzes z ON z.id = a.quiz_id WHERE z.course_id = ?
              UNION SELECT m.student_name FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id
                    WHERE l.course_id = ?)) AS n_students,
          (SELECT COUNT(*) FROM attempts a JOIN quizzes z ON z.id = a.quiz_id WHERE z.course_id = ?) AS n_attempts,
          (SELECT COUNT(*) FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id
             WHERE l.course_id = ? AND m.role = 'user') AS n_chat,
          (SELECT COUNT(*) FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id
             WHERE l.course_id = ? AND m.role = 'user' AND m.flagged = 1) AS n_flagged,
          (SELECT COUNT(*) FROM chat_messages m JOIN lectures l ON l.id = m.lecture_id
             WHERE l.course_id = ? AND m.role = 'user' AND m.refused = 1) AS n_refused
        """, (cid,) * 6)

    return {"topics": topics, "flagged_questions": flagged, "recent_questions": recent, "totals": totals}


def summarise_misconceptions(cid: int, topic_id: int | None = None) -> dict:
    """Send one topic's most-missed questions (with the wrong options students picked) and the students'
    chat questions to the LLM, and get back a short summary for the lecturer."""
    if topic_id is None:
        ranked = course_insights(cid)["topics"]
        if not ranked:
            return {"topic_id": None, "topic_name": None, "summary": "No topics yet."}
        topic_id = ranked[0]["topic_id"]
    topic = query_one("""SELECT t.id, t.name, t.summary, l.id AS lecture_id, l.title AS lecture_title
                         FROM topics t JOIN lectures l ON l.id = t.lecture_id
                         WHERE t.id = ? AND l.course_id = ?""", (topic_id, cid))
    if not topic:
        raise ValueError("Topic not found in this course")

    wrong = query("""
        SELECT q.text, q.options_json, q.correct_index, a.chosen_index, COUNT(*) AS n
        FROM answers a JOIN questions q ON q.id = a.question_id
        WHERE q.topic_id = ? AND a.is_correct = 0 AND a.chosen_index IS NOT NULL
        GROUP BY q.text, a.chosen_index ORDER BY n DESC LIMIT 12""", (topic_id,))
    wrong_lines = []
    for w in wrong:
        opts = json.loads(w["options_json"])
        chosen = opts[w["chosen_index"]] if 0 <= w["chosen_index"] < len(opts) else "?"
        wrong_lines.append(f"- Q: {w['text']}\n  Correct: {opts[w['correct_index']]}\n"
                           f"  Wrongly chosen ({w['n']}x): {chosen}")
    qs = query("""SELECT content FROM chat_messages WHERE topic_id = ? AND role = 'user'
                  ORDER BY id DESC LIMIT 25""", (topic_id,))

    summary = complete(
        prompts.MISCONCEPTIONS_SYSTEM,
        prompts.MISCONCEPTIONS_USER.format(
            lecture=topic["lecture_title"], topic=topic["name"], topic_summary=topic["summary"] or "",
            wrong_answers="\n".join(wrong_lines) or "(none)",
            questions="\n".join(f"- {q['content']}" for q in qs) or "(none)"),
        kind="misconceptions", lecture_id=topic["lecture_id"], max_tokens=800)
    return {"topic_id": topic_id, "topic_name": topic["name"], "lecture_title": topic["lecture_title"],
            "summary": summary}
