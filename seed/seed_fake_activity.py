"""Add fake student activity so the lecturer dashboard tells a story. Run AFTER seed_course.py.

    python seed/seed_fake_activity.py                       # ~120 students on the newest course
    python seed/seed_fake_activity.py --students 80 --course-id 1
    python seed/seed_fake_activity.py --hard "Gradient descent,Precision and recall"

What it creates (no LLM calls, questions are copied from each lecture's question bank):
- one homework quiz per class day (only the newest one stays open) and a closed live quiz for class 1,
- quiz attempts and answers for most students, plus self-evaluation attempts for about half of them,
- tutor chat questions (user + assistant rows), some flagged "not covered" and a few refused.
Two "hard" topics are skewed (low correct rate, many questions, more flags) so they top the struggle chart.
By default: the 3rd topic of class day 2 and the 4th topic of the last class day.
"""
import argparse
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import connect, init_db, query, query_one  # noqa: E402

FIRST = ["Giulia", "Marco", "Sofia", "Luca", "Aurora", "Matteo", "Alice", "Lorenzo", "Ginevra", "Leonardo",
         "Emma", "Francesco", "Beatrice", "Alessandro", "Chiara", "Tommaso", "Martina", "Gabriele", "Sara",
         "Riccardo", "Anna", "Andrea", "Elena", "Davide", "Noemi", "Pietro", "Viola", "Federico", "Greta",
         "Simone", "Camilla", "Edoardo", "Laura", "Nicolò", "Irene", "Samuele", "Arianna", "Filippo",
         "Bianca", "Diego", "Amir", "Lina", "Yuki", "Omar", "Priya", "Jonas", "Mei", "Lucas", "Fatima", "Ivan"]

ASK = [
    "I don't really get {t}. Can you explain it with a simple example?",
    "Why do we need {t}? What problem does it solve?",
    "Can you explain {t} step by step?",
    "What's the difference between {t} and {o}?",
    "I keep mixing up {t} and {o}, how do I tell them apart?",
    "Is there an intuitive way to think about {t}?",
    "What happens if we get {t} wrong in practice?",
    "Can you explain this part again?",
]
HIGHLIGHT_ASK = ["Can you explain this part again?", "What does this mean?", "Why is this true?",
                 "Can you give me an example of this?"]
NOT_COVERED_TOPIC = [
    "How is {t} done in libraries like PyTorch or scikit-learn?",
    "Is there a formal proof of why {t} works?",
    "How does {t} scale to really huge datasets?",
    "Is {t} still used in modern deep learning?",
    "Which textbook chapter covers {t} in more depth?",
]
NOT_COVERED_GENERIC = [
    "Will we need to know the derivations for the exam?",
    "What programming language should we use for the project?",
    "Is there a recommended book for the whole course?",
    "How does this relate to large language models like ChatGPT?",
    "Are we going to cover neural networks later?",
]


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def logit(p):
    return math.log(p / (1 - p))


def ts(day: str, rng: random.Random, max_days: int = 6) -> str:
    """A UTC timestamp (like SQLite's CURRENT_TIMESTAMP) between the class day and min(day + max_days, now)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)
    start = datetime.fromisoformat(day) if day else now - timedelta(days=7)
    start = start.replace(hour=9)
    end = min(start + timedelta(days=max_days), now)
    if end <= start:
        start, end = now - timedelta(hours=6), now
    t = start + (end - start) * rng.random()
    return t.strftime("%Y-%m-%d %H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--course-id", type=int, default=None, help="default: newest course")
    ap.add_argument("--students", type=int, default=120)
    ap.add_argument("--hard", default="", help="comma-separated topic names to make hard")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    init_db()

    course = query_one("SELECT * FROM courses WHERE id=?", (args.course_id,)) if args.course_id \
        else query_one("SELECT * FROM courses ORDER BY id DESC LIMIT 1")
    if not course:
        sys.exit("No course found. Run seed/seed_course.py first.")
    lectures = query("SELECT * FROM lectures WHERE course_id=? AND status='ready' ORDER BY number, id",
                     (course["id"],))
    if not lectures:
        sys.exit("The course has no ready class days.")
    topics_by_lec = {l["id"]: query("SELECT * FROM topics WHERE lecture_id=? ORDER BY id", (l["id"],))
                     for l in lectures}
    all_topics = [t for l in lectures for t in topics_by_lec[l["id"]]]
    bank = {l["id"]: query("""SELECT q.* FROM questions q JOIN quizzes z ON z.id=q.quiz_id
                              WHERE z.lecture_id=? AND z.kind='bank' ORDER BY q.id""", (l["id"],))
            for l in lectures}

    # ---- which topics are hard
    if args.hard:
        names = [n.strip().lower() for n in args.hard.split(",") if n.strip()]
        hard = {t["id"] for t in all_topics if t["name"].lower() in names}
    else:
        hard = set()
        picks = [(lectures[1] if len(lectures) > 1 else lectures[0], 2), (lectures[-1], 3)]
        for lec, idx in picks:
            ts_ = topics_by_lec[lec["id"]]
            if ts_:
                hard.add(ts_[min(idx, len(ts_) - 1)]["id"])
    hard_names = [t["name"] for t in all_topics if t["id"] in hard]
    print(f"Course {course['id']} '{course['name']}': {len(lectures)} class days, {len(all_topics)} topics")
    print(f"Hard topics: {', '.join(hard_names) or '(none)'}")

    names = []
    for i in range(args.students):
        n = f"{FIRST[i % len(FIRST)]} {chr(65 + (i * 7) % 26)}."
        names.append(n if n not in names else f"{n}{i}")
    ability = {n: rng.gauss(0, 0.7) for n in names}
    # each question has a "popular" wrong option that confused students pick
    popular_wrong = {}

    def answer(conn, attempt_id, q, student):
        base = logit(0.32) if q["topic_id"] in hard else logit(0.82)
        correct = rng.random() < sigmoid(base + ability[student])
        opts = json.loads(q["options_json"])
        if correct:
            chosen = q["correct_index"]
        else:
            wrong = [i for i in range(len(opts)) if i != q["correct_index"]]
            pw = popular_wrong.setdefault(q["id"], rng.choice(wrong))
            chosen = pw if rng.random() < 0.7 else rng.choice(wrong)
        conn.execute("INSERT INTO answers (attempt_id, question_id, chosen_index, is_correct) VALUES (?,?,?,?)",
                     (attempt_id, q["id"], chosen, int(correct)))
        return int(correct)

    def copy_quiz(conn, lec, kind, title, qs, is_open, created):
        cur = conn.execute("INSERT INTO quizzes (course_id, lecture_id, kind, title, is_open, created_at) "
                           "VALUES (?,?,?,?,?,?)", (course["id"], lec["id"] if lec else None, kind, title,
                                                    int(is_open), created))
        zid = cur.lastrowid
        out = []
        for q in qs:
            c = conn.execute("INSERT INTO questions (quiz_id, topic_id, text, options_json, correct_index, "
                             "explanation) VALUES (?,?,?,?,?,?)",
                             (zid, q["topic_id"], q["text"], q["options_json"], q["correct_index"],
                              q["explanation"]))
            out.append({**q, "id": c.lastrowid})
        return zid, out

    def attempt(conn, zid, qs, student, created):
        cur = conn.execute("INSERT INTO attempts (quiz_id, student_name, score, total, created_at) "
                           "VALUES (?,?,?,?,?)", (zid, student, 0, len(qs), created))
        aid = cur.lastrowid
        score = sum(answer(conn, aid, q, student) for q in qs)
        conn.execute("UPDATE attempts SET score=? WHERE id=?", (score, aid))

    n_att = n_chat = n_flag = n_ref = 0
    with connect() as conn:
        # ---- homework (one per class day, only the newest stays open) + a live quiz for class 1
        for i, lec in enumerate(lectures):
            qs = bank[lec["id"]]
            if not qs:
                continue
            is_last = i == len(lectures) - 1
            zid, qcopy = copy_quiz(conn, lec, "homework", f"Homework: {lec['title']}", qs, is_last,
                                   ts(lec["date"], rng, 0))
            takers = [s for s in names if rng.random() < (0.55 if is_last else 0.8)]
            for s in takers:
                attempt(conn, zid, qcopy, s, ts(lec["date"], rng, 2 if is_last else 6))
                n_att += 1
            if i == 0:
                zid, qcopy = copy_quiz(conn, lec, "live", f"Live quiz: {lec['title']}", qs[:4], False,
                                       ts(lec["date"], rng, 0))
                for s in names:
                    if rng.random() < 0.6:
                        attempt(conn, zid, qcopy, s, ts(lec["date"], rng, 0))
                        n_att += 1

        # ---- self-evaluation (2 bank questions per class day) for about half of the students
        last_day = lectures[-1]["date"]
        for s in names:
            if rng.random() < 0.5:
                qs = [q for l in lectures for q in rng.sample(bank[l["id"]], min(2, len(bank[l["id"]])))]
                when = ts(last_day, rng, 2)
                zid, qcopy = copy_quiz(conn, None, "self_eval", f"Self-evaluation: {s}", qs, True, when)
                attempt(conn, zid, qcopy, s, when)
                n_att += 1

        # ---- chat questions
        def chat(lec, student, content, topic_id, flagged=0, refused=0, highlight=None):
            when = ts(lec["date"], rng, 6)
            if refused:
                reply = ("That looks like a question from your open homework, so I won't give you the answer. "
                         "Re-read how the lecture defines the idea and try again.")
            elif flagged:
                reply = "That isn't covered in this class's material, so I've passed your question to your lecturer."
            else:
                reply = "Good question! Here's how the lecture explains it..."
            for role, text in (("user", content), ("assistant", reply)):
                conn.execute("INSERT INTO chat_messages (lecture_id, student_name, role, content, "
                             "highlighted_text, topic_id, flagged, refused, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (lec["id"], student, role, text, highlight if role == "user" else None, topic_id,
                              flagged, refused, when))

        topic_lec = {t["id"]: l for l in lectures for t in topics_by_lec[l["id"]]}
        weights = [6 if t["id"] in hard else 1 for t in all_topics]
        for s in names:
            for _ in range(rng.choice([0, 0, 1, 1, 2, 3, 4])):
                t = rng.choices(all_topics, weights)[0]
                lec = topic_lec[t["id"]]
                others = [o for o in topics_by_lec[lec["id"]] if o["id"] != t["id"]] or [t]
                o = rng.choice(others)
                if rng.random() < 0.3 and t.get("summary"):
                    chat(lec, s, rng.choice(HIGHLIGHT_ASK), t["id"], highlight=t["summary"][:160])
                else:
                    chat(lec, s, rng.choice(ASK).format(t=t["name"], o=o["name"]), t["id"])
                n_chat += 1

        # flagged "not covered": tied to topics (hard ones more often) or general
        for _ in range(max(6, args.students // 6)):
            s = rng.choice(names)
            if rng.random() < 0.65:
                t = rng.choices(all_topics, [4 if t["id"] in hard else 1 for t in all_topics])[0]
                chat(topic_lec[t["id"]], s, rng.choice(NOT_COVERED_TOPIC).format(t=t["name"]), t["id"], flagged=1)
            else:
                chat(rng.choice(lectures), s, rng.choice(NOT_COVERED_GENERIC), None, flagged=1)
            n_chat += 1
            n_flag += 1

        # a few refused homework-answer requests on the open homework
        last_qs = bank[lectures[-1]["id"]]
        for _ in range(min(5, len(last_qs))):
            q = rng.choice(last_qs)
            chat(lectures[-1], rng.choice(names), f"What's the answer to this? {q['text']}", q["topic_id"],
                 refused=1)
            n_chat += 1
            n_ref += 1

    print(f"Added {len(names)} students: {n_att} quiz attempts, {n_chat} chat questions "
          f"({n_flag} flagged, {n_ref} refused).")
    print(f"Open http://localhost:8000/lecturer  ->  Insights")


if __name__ == "__main__":
    main()
