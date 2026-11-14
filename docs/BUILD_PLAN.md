# Build Plan: AI Lecture Companion (localhost prototype)

> **For every Claude session:** this file is the single source of truth. Read it fully, then do **only your phase**. Don't rename anything in the shared contract (sections 3–5). If you need something new, add it and don't change what exists. When you finish, add a short "Phase N: done" note at the bottom of **this file** (section 9). **Read the Phase log (section 9) first: it lists helpers that already exist.**

---

## 1. What we're building

There are two use cases for students and one for lecturers.

1. **After each class (student):** each "class day" has its own page. A student who missed the class reads an AI-written lecture generated from the lecturer's material, with the original slides beside it. They can highlight any passage and ask follow-up questions 24/7, and they can add notes.
2. **Exam preparation (student):** the student can take a **self-evaluation test** at any time. It covers all class days. The result shows which lectures they're weak on, with **links to those class-day pages**.
3. **Lecturer:** the lecturer creates a class (course), uploads material for each class day and generates quizzes. A quiz is either **homework** or **live in class** (students join through a QR code). A dashboard shows **which topics students struggle with most**, using quiz errors, chat questions and questions the AI flagged as not covered.

### Class-day page layout (fixed)
```
┌─────────────────────────┬─────────────────────┐
│                         │  Slides (PDF)       │
│   AI's Lecture          │                     │
│   (markdown, selectable)├─────────────────────┤
│                         │  Chat (tutor)       │
│                         │                     │
└─────────────────────────┴─────────────────────┘
```

### How this meets the brief's Level 2 requirements
- **Real material:** the lecturer's PDFs. Generation and chat are grounded only in the extracted text.
- **Actions:** it generates and scores quizzes, tags every question and mistake to a topic, flags questions the material doesn't cover for the lecturer, and builds a "lectures to review" list.
- **Boundary:** the tutor explains and guides but **won't give answers to an open homework quiz**. This is enforced in code, not only in the prompt. It also says when something isn't in the material instead of inventing an answer.
- **Logs:** every LLM call is written to `agent_logs`.

---

## 2. Stack (decided, no build step)

| Part | Choice |
|---|---|
| Backend | Python 3.11+, **FastAPI**, Uvicorn |
| DB | **SQLite via the stdlib `sqlite3`** (decided in Phase 0; use the helpers in `app/db.py`) |
| Frontend | **Plain HTML + vanilla JS** served by FastAPI from `/static`, **Tailwind via CDN**, `marked.js` via CDN for markdown |
| PDF text | `pypdf` |
| Slides display | the browser's native PDF viewer in an `<iframe>` |
| QR | `qrcode[pil]` |
| LLM | `app/llm.py` wrapper. `LLM_PROVIDER=mock|anthropic|openai`, key in `.env`. **Mock mode returns canned but realistic output, so everyone can build before the key is added.** |
| Retrieval | none (no vector DB). One lecture's material fits in the context window, so pass the extracted text plus the generated lecture directly. |

Everything runs with `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.

---

## 3. Repo layout and file ownership

The team shares the code through **one GitHub repo**. Each phase owns its files to avoid merge conflicts.

```
lecture-companion/
├── CLAUDE.md                    # instructions for Claude Code sessions
├── README.md                    # Phase 4 (Phase 0 wrote a short "Run it" version)
├── requirements.txt             # Phase 0 (others may append)
├── .env.example                 # Phase 0
├── app/
│   ├── main.py                  # Phase 0: app, router includes, static mount, page routes
│   ├── db.py                    # Phase 0: connection, schema creation
│   ├── llm.py                   # Phase 0: complete(), complete_json(), mock mode, logging
│   ├── ingest.py                # Phase 0: PDF→text, generate lecture md + topics + question bank
│   ├── prompts.py               # Phase 0 creates; each phase adds its own prompts
│   ├── routes_lecturer.py       # Phase 3
│   ├── routes_chat.py           # Phase 1
│   ├── routes_quiz.py           # Phase 2
│   └── insights.py              # Phase 3
├── static/
│   ├── common.js / common.css   # Phase 0 (api() fetch helper, student-name helper, nav)
│   ├── index.html               # Phase 0 (course list)
│   ├── lecture.html / .js       # Phase 1
│   ├── quiz.html / .js          # Phase 2
│   ├── selfeval.html / .js      # Phase 2
│   ├── course.html              # Phase 2 (student course home; script is inline)
│   └── lecturer.html / .js      # Phase 3
├── data/
│   ├── app.db
│   └── uploads/                 # PDFs stored as {lecture_id}.pdf
├── seed/
│   ├── material/                # 2–3 real lecture PDFs from ONE real course
│   ├── sample_pdfs.py           # Phase 0: demo PDFs used when material/ is empty
│   ├── seed_course.py           # Phase 0: creates the course + ingests the PDFs
│   └── seed_fake_activity.py    # Phase 3: about 120 fake students' activity
└── docs/
    ├── BUILD_PLAN.md            # this file (everyone appends to section 9)
    ├── HACKATHON_BRIEF.md       # condensed challenge brief
    ├── architecture.md          # Phase 4
    └── example_interactions.md  # Phase 4
```

---

## 4. Data model (shared contract)

```
courses        (id, name, lecturer_name, created_at)
lectures       (id, course_id, number, title, date, slides_path,
                material_text, lecture_md, status['uploaded'|'generating'|'ready'|'error'])
topics         (id, lecture_id, name, summary)                  -- 3–6 per lecture, from ingest
quizzes        (id, course_id, lecture_id NULL, kind['homework'|'live'|'self_eval'|'bank'],
                title, is_open BOOL, created_at)
questions      (id, quiz_id, topic_id, text, options_json, correct_index, explanation)
attempts       (id, quiz_id, student_name, score, total, created_at)
answers        (id, attempt_id, question_id, chosen_index, is_correct)
chat_messages  (id, lecture_id, student_name, role['user'|'assistant'], content,
                highlighted_text NULL, topic_id NULL, flagged BOOL, refused BOOL, created_at)
notes          (id, lecture_id, student_name, highlighted_text, content, created_at)
agent_logs     (id, ts, kind, lecture_id NULL, prompt, response, model, latency_ms)
```

**The question bank:** during ingest, each lecture gets a `quizzes` row with `kind='bank'` holding about 6 questions tagged to its topics. The self-evaluation test samples from the bank, so it opens instantly and needs no LLM call at test time.

**Student identity:** there's no auth. The student enters a name once and it's kept in `localStorage`, then sent as `student_name`.

**People (added for the showcase, see Phase log "Showcase: multi-user"):**
```
users        (id, name UNIQUE, role['student'|'teacher'], created_at)
enrollments  (user_id, course_id)          -- students ↔ courses
courses      + teacher_id NULL              -- the course's teacher; lecturer_name mirrors their name
```
Still no auth: the current user is picked in the nav switcher and their **name** is what's sent as `student_name`.

---

## 5. API contract (shared)

All responses are JSON unless noted.

**Shared (Phase 0)**
- `GET /api/health` → `{ok, llm_provider, model}`
- `GET /api/courses` → `[{id, name, lecturer_name}]`
- `GET /api/courses/{cid}` → `{id, name, lecturer_name}`
- `GET /api/courses/{cid}/lectures` → `[{id, number, title, date, status}]`
- `GET /api/lectures/{lid}` → `{id, course_id, number, title, date, lecture_md, status, topics:[{id,name,summary}]}`
- `GET /api/lectures/{lid}/slides` → the PDF file

**Chat and notes (Phase 1)**
- `POST /api/lectures/{lid}/chat` `{student_name, message, highlighted_text?}` → `{reply, topic_id, flagged, refused}`
- `GET /api/lectures/{lid}/chat?student_name=` → message history `[{role, content, ...}]`
- `GET/POST /api/lectures/{lid}/notes` `{student_name, highlighted_text, content}`

**Quizzes and self-evaluation (Phase 2)**
- `POST /api/lectures/{lid}/quizzes` `{kind:'homework'|'live', n:5}` → `{quiz_id}` (generated by the LLM from the material)
- `GET /api/quizzes/{qid}` → questions **without** `correct_index`
- `POST /api/quizzes/{qid}/attempts` `{student_name, answers:[{question_id, chosen_index}]}` → `{score, total, results:[{question_id, is_correct, correct_index, explanation}]}`
- `GET /api/quizzes/{qid}/qr` → PNG of `http://<LAN-IP>:8000/quiz/{qid}`
- `POST /api/courses/{cid}/self-eval` `{student_name}` → `{quiz_id}` (samples 2 bank questions per lecture)
- `GET /api/attempts/{aid}/report` → `{per_lecture:[{lecture_id, title, score, total, weak:bool, url:"/lecture/{id}", weak_topics:[...]}]}`

**Lecturer (Phase 3)**
- `POST /api/courses` `{name, lecturer_name}`
- `POST /api/courses/{cid}/lectures` multipart `{title, date, file}` → saves the PDF and runs `ingest.process_lecture(lid)` as a FastAPI BackgroundTask
- `GET /api/courses/{cid}/quizzes` → list with `kind` and `is_open`. `PATCH /api/quizzes/{qid}` `{is_open}`
- `GET /api/courses/{cid}/insights` → `{topics:[{topic_id, lecture_title, name, error_rate, n_answers, n_questions, n_flagged, struggle_score}], flagged_questions:[...], recent_questions:[...]}`

**People (showcase addition)**
- `GET /api/users?role=` → `[{id, name, role, course_ids}]` · `GET /api/users/{uid}`
- `POST /api/users` `{name | names:[...], role, course_ids?, new_courses?}` · `PATCH /api/users/{uid}` `{name?, course_ids?, new_courses?}` · `DELETE /api/users/{uid}` (`new_courses`: course names to create for a teacher)
- `POST /api/users/join` `{name, course_id?}` → get-or-create a student (QR joiners)
- `GET /api/courses?student_id=|teacher_id=` filters; `POST /api/courses` also takes `teacher_id`

**Page routes (Phase 0 registers them, owners build them)**
`/` → course list · `/course/{cid}` · `/lecture/{lid}` · `/quiz/{qid}` · `/selfeval/{cid}` · `/lecturer` · `/people`

---

## 6. Phases

```
Phase 0 (foundation) ──┬──> Phase 1 (class-day page + tutor)      ─┐
      ~45 min          ├──> Phase 2 (quizzes + self-evaluation)    ├──> Phase 4 (integration, docs, demo)
                       └──> Phase 3 (lecturer + dashboard)        ─┘        ~45 min
                              ~1.5 h, IN PARALLEL
```

Phases 1–3 start only after Phase 0 has been pushed. Each one works on its own branch (`phase-1`, `phase-2`, `phase-3`), runs in **mock mode** and touches only its own files.

### Phase 0: Foundation ✅ DONE
**Goal:** a running app with the schema, the LLM wrapper, ingestion and one seeded course. Every page route returns a placeholder. (See the Phase log for details.)

### Phase 1: Class-day page and tutor agent (~1.5 h)
**Owns:** `routes_chat.py`, `static/lecture.html/.js`, chat prompts in `prompts.py`.
1. Build the 3-panel layout from section 1: rendered `lecture_md` on the left, the slides iframe at top right, chat at bottom right. Each panel scrolls on its own. It should look clean. *(Phase 0 already built a working version; polish and extend it.)*
2. **Highlight to ask:** selecting text in the lecture shows a small popup with "Ask about this" and "Add note". Ask pre-fills the chat with the quoted passage. Note saves through the notes API, and saved notes appear as a list or margin markers. *(Popup and quote are already wired; the notes list is still missing.)*
3. The **tutor agent** in `POST /chat`:
   - Context: the lecture's `material_text`, `lecture_md`, the topics and the last ~8 messages.
   - Behaviour: explain and give analogies, end with a short check question when it helps, and answer only from the material. If the material doesn't cover the question, say so and set `flagged=true`, which sends it to the lecturer.
   - **Code guardrail:** if the lecture has an **open homework quiz** and the message closely matches one of its questions (normalised token overlap or fuzzy match ≥ 0.6, or the LLM judge says it's asking for a quiz answer), **don't send it to the tutor for an answer**. Return a guiding refusal that explains the concept without giving the answer, with `refused=true`.
   - **Topic tagging:** a cheap second LLM call (or the same call returning JSON) picks a `topic_id` from the lecture's topics.
4. **Done when:** in mock mode you can highlight, ask, see the reply, add a note, and trigger both the "not covered → flagged" path and the "homework answer → refused" path.

### Phase 2: Quizzes and self-evaluation (~1.5 h)
**Owns:** `routes_quiz.py`, `static/quiz.html/.js`, `static/selfeval.html/.js`, `static/course.html`, quiz prompts.
1. `POST /lectures/{lid}/quizzes`: the LLM generates N multiple-choice questions from the material, each tagged to a topic, with a short explanation of *why* the answer is right. *(Reuse `app.ingest.generate_questions()`.)*
2. `quiz.html`: a mobile-friendly page that shows one question at a time, then the results with explanations. It works for homework and for live quizzes.
3. `GET /quizzes/{qid}/qr`: a QR code pointing at the **LAN IP** (detect it with a UDP-socket trick) so phones on the same Wi-Fi can join. A "show fullscreen QR" view is for the projector.
4. **Student course home** (`course.html`): the list of class days, each linking to `/lecture/{id}`, and a big **"Take self-evaluation test"** button. *(Already working from Phase 0.)*
5. **Self-evaluation:** sample 2 bank questions per lecture and take the test. The result page shows the score per lecture, marks lectures under 60% as **"Review this lecture"** with a link to `/lecture/{id}`, and lists the weak topics.
6. Every answer goes into `answers` so Phase 3's dashboard picks it up.
7. **Done when:** in mock mode you can create a homework quiz, take it, see the QR, and take a self-evaluation that links to the weak lectures.

### Phase 3: Lecturer side and insights dashboard (~1.5 h)
**Owns:** `routes_lecturer.py`, `insights.py`, `static/lecturer.html/.js`, `seed/seed_fake_activity.py`.
1. `lecturer.html` has tabs:
   - **Class:** create a course and add a class day (title, date, PDF upload). The status badge polls until `ready`, and there's a "preview as student" link.
   - **Quizzes:** for each class day, "Generate homework quiz" and "Generate live quiz" buttons (they call the Phase 2 endpoint; in mock mode, stub the call if Phase 2 isn't merged yet). There's an open/close toggle and a QR button.
   - **Insights:** the main screen.
2. `insights.py` computes, for each topic, `error_rate` (from `answers`), `n_questions` (chat messages tagged to the topic), `n_flagged`, and `struggle_score = 0.6*error_rate + 0.3*norm(n_questions) + 0.1*norm(n_flagged)`.
3. The Insights UI: a ranked bar chart of topics by struggle score (Chart.js via CDN), grouped by class day. A panel lists **"Questions the material didn't answer"** (flagged), and another shows recent anonymised student questions. Optional: a "Summarise misconceptions" button that sends the top topic's wrong answers and questions to the LLM.
4. `seed_fake_activity.py` adds about 120 fake students with quiz attempts and chat messages. **Skew it so 2 topics clearly stand out**, so the dashboard tells a story.
5. **Done when:** after running both seed scripts, `/lecturer` shows a convincing dashboard and uploading a PDF creates a new class day.

### Phase 4: Integration, real LLM, docs and demo (~45 min)
1. Merge all branches. Set `LLM_PROVIDER` and the key in `.env`. Re-run the seed with the **real** LLM on the real course PDFs.
2. Run the demo script end to end (section 7) and fix what breaks. Tune the prompts (lecture quality, tutor tone, refusal wording).
3. Write `README.md` (how to run, models, libraries, custom logic), `docs/architecture.md` (input → knowledge → tools → decisions → output, guardrails, memory, logs; a diagram of the agent loop) and `docs/example_interactions.md` (at least 4 real transcripts, **including the homework refusal and a "not in the material" flag**). Export some `agent_logs` rows as evidence.
4. Take screenshots and, optionally, record a 60–90 s demo video.

---

## 7. Demo script (what the judges see, about 2 min)
1. **Lecturer:** upload today's slides. A few moments later the class day is "ready".
2. **Student who missed class:** open the class day and read the AI lecture next to the slides. Highlight a confusing paragraph and choose "Ask about this" to get a grounded explanation that ends with a check question.
3. **Boundary:** paste the homework quiz question into the chat. The tutor refuses to answer it and guides instead.
4. **Not covered:** ask something outside the material. The tutor says it isn't covered and flags it.
5. **Exam preparation:** take the self-evaluation test. The result says to review Lectures 2 and 3, with links.
6. **Lecturer dashboard:** the struggle chart shows the top topics, and the flagged question from step 4 appears live. *"The questions nobody asks in a 200-person hall still reach the lecturer."*

## 8. Prioritisation if time runs out
**Must have:** Phase 0, the 3-panel page with chat, the refusal guardrail, self-evaluation with weak-lecture links, and the insights dashboard on seeded data.
**Cut first:** notes, the live-quiz QR (keep homework quizzes), the upload UI (the seed script is enough), and the misconception summary.

## 9. Phase log
_(Each session appends: phase, what was done, anything that differs from the contract, known issues.)_

### Phase 0: done (2026-11-14)
**Built:** schema, LLM wrapper with mock mode, ingestion, seed script and frontend shell. Tested in mock mode (seed → 3 ready lectures, 15 topics, 18 bank questions, all pages return 200).

**Helpers other phases should use (don't rewrite them):**
- `app/db.py`: `query(sql, params) -> list[dict]`, `query_one(...) -> dict|None`, `execute(...) -> lastrowid`, `UPLOAD_DIR`. Plain `sqlite3`, no ORM.
- `app/llm.py`: `complete(system, user, kind, lecture_id)` and `complete_json(system, user, schema_hint, kind, lecture_id)`. **Mock mode reads the XML tags in the user prompt**: `<material>`, `<topics>` (JSON list of `{id,name,summary}`), `<message>`, `<highlight>`. Use those tags in your prompts and the mock output follows your data. Mock kinds: `lecture`, `topics`, `questions`, `chat`, `topic_tag`. Any other kind returns `"(mock <kind> response)"`; add a branch in `_mock()` if your phase needs realistic mock output (adding a branch is fine, don't change existing ones).
- `app/ingest.py`: `process_lecture(lid)` (for upload background tasks) and `generate_questions(lecture_id, kind, n, title, is_open=True) -> quiz_id` (for homework/live quizzes).
- `app/prompts.py`: ingest prompts plus empty sections for Phases 1–3.
- `static/common.js`: `api(path, {method, body})` (JSON or FormData; throws an `Error` with `.status`), `getStudentName()` (non-blocking name dialog), `pathId()`, `escapeHtml()`, `statusBadge(status)`, `renderNav(role, crumbs)`, `comingSoon(what, phase)`.

**Frontend state:**
- `/`, `/course/{cid}`: complete.
- `/lecture/{lid}`: working 3-panel layout, rendered lecture, slides iframe, chat UI (calls `POST /chat`; shows "not connected yet" until Phase 1), highlight popup (Ask about this / Add note).
- `/lecturer`: tab shell + read-only class list with "Preview as student".
- `/quiz/{qid}`, `/selfeval/{cid}`: "coming soon" placeholders.

**Differences from the contract:** added `GET /api/health` and `GET /api/courses/{cid}`. `course.html` has its script inline (no `course.js`). Router stub files exist for Phases 1–3 and are already included in `main.py`, so just add routes to `router`.

**Seed:** if `seed/material/` is empty, the seed generates a 3-lecture sample course ("Introduction to Machine Learning"). The seed **resets the DB** unless `--keep` is passed.

**Known issues:** in mock mode the lecture is a reformatted copy of the slides (by design). The real-provider paths (anthropic/openai) haven't been tested against a live key yet; Phase 4 must check them.

### Phase 1: done (2026-11-14)
**Built:** tutor chat, guardrails and notes (`app/routes_chat.py`), Phase 1 prompts (`TUTOR_*`, `REFUSAL_*` in `app/prompts.py`), and the class-day page (`static/lecture.html/.js`). Tested in mock mode with curl and in the browser: highlight → ask, plain question, "not covered" → `flagged`, open homework question → `refused`, add/list/delete notes, history and notes survive a reload.

**How the tutor works:**
- `POST /chat` first runs the **code guardrail**: it compares message + highlight with every question of the lecture's quizzes where `kind='homework' AND is_open=1`. It refuses (`refused=true`) when either check passes: the `difflib` text similarity is ≥ 0.75 (only when the message is ≥ 60% of the question's length), or ≥ 60% of the question's content words appear in the message (only when the question has ≥ 3 content words). The refusal prompt gets only the question text, **never the options or `correct_index`**.
- Otherwise one `complete_json(kind="tutor")` call returns `{reply, covered, topic_id}`: `flagged = not covered`, and `topic_id` is checked against the lecture's topics. If the JSON fails, it falls back to a plain `complete(kind="chat")`.
- `topic_id`, `flagged` and `refused` are stored on **both** the user row and the assistant row in `chat_messages`, so Phase 3 can count either one (count `role='user'` to avoid double counting).

**Differences from the contract (additions only):** `DELETE /api/notes/{nid}?student_name=`. `GET /chat` and `GET /notes` take `?student_name=` (default `Guest`). `GET /chat` returns `{id, role, content, highlighted_text, topic_id, flagged, refused, created_at}`. `POST /notes` returns the new note row.

**`app/llm.py`:** added mock kinds `tutor` (covered when there's a highlight or ≥ 2 content words overlap the material) and `refusal`. Existing branches are unchanged.

**Page:** the bottom-right panel has "Ask the tutor" and "My notes (n)" tabs. Notes are written in an inline form (no `prompt()`), shown as cards, and marked in the lecture with `<mark>`. Clicking a mark jumps to its card and the other way round. Refused and flagged replies show a badge, in the live chat and in the history.

**Known issues:** no LLM judge for the guardrail (fuzzy and token matching only), so a heavily reworded homework question can get through. A note's mark only appears when the passage sits inside one text node (a selection across bold text or list items isn't marked, but the note is still saved). Mock bank and homework questions share the template "Which statement best describes X?", so in mock mode pasting that template for another topic is also refused.

**LLM provider (found during Phase 1):** the hackathon key is an **OpenRouter** key (`sk-or-v1-…`) whose staff guardrail allows only 5 models: `anthropic/claude-sonnet-5.5`, `anthropic/claude-haiku-5.5`, `openai/gpt-6.1-terra`, `openai/gpt-6-luna` and `deepseek/deepseek-v4.1-flash`. The key's spending limit is $10. Working `.env`: `LLM_PROVIDER=openai`, `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=anthropic/claude-sonnet-5.5`, and the key in `OPENAI_API_KEY`. No code change is needed (`llm.py` already reads `OPENAI_BASE_URL`). Any other model returns a 404 "guardrail restrictions" error. When the LLM fails, `POST /chat` now returns a 502 with a short message.

### Phase 2: done (2026-11-14)
**Built:** quizzes, QR, self-evaluation and the report (`app/routes_quiz.py`), the quiz page (`static/quiz.html/.js`), the self-evaluation page (`static/selfeval.html/.js`) and a homework list on the course home (`static/course.html`). Tested in mock mode with a script and in the browser (desktop and a 375 px phone viewport): create a homework quiz, take it, see results with explanations, QR/projector view with live results, self-evaluation → "Review this lecture" links.

**How it works:**
- `POST /lectures/{lid}/quizzes` reuses `ingest.generate_questions()` (no new prompts; uses `QUESTIONS_*`). `n` is clamped to 1–15, the lecture must be `ready` (409 otherwise), LLM failure → 502, a quiz with 0 valid questions is deleted → 502. Optional `title` in the body (default `"Homework: <lecture>"` / `"Live quiz: <lecture>"`).
- `POST /quizzes/{qid}/attempts` scores server-side and writes one `answers` row per question of the quiz; unanswered questions are stored with `chosen_index=NULL, is_correct=0`. Closed quiz (`is_open=0`) → 403.
- Self-evaluation **copies** 2 random bank questions per `ready` lecture into a new `self_eval` quiz (`lecture_id NULL`, `topic_id` kept), so its answers count in Phase 3's per-topic error rate. No LLM call.
- The report finds each question's lecture via the quiz's `lecture_id`, else the topic's lecture, else the bank question with the same text. `weak = score/total < 0.6`. `weak_topics` = topics of wrongly answered questions.
- QR: `qrcode` PNG of `http://<LAN-IP>:<port>/quiz/{qid}` (UDP-socket trick). `PUBLIC_BASE_URL` in `.env` overrides it (e.g. if the LAN IP detection picks the wrong interface).

**Differences from the contract (additions only):**
- `GET /quizzes/{qid}` also returns `kind, title, is_open, course_id, course_name, lecture_id, lecture_title, join_url`, and per question `topic_id` and `lecture_title` (only for self_eval).
- `POST /attempts` also returns `attempt_id`, and each result has `chosen_index`.
- `GET /attempts/{aid}/report` also returns `score, total, kind, quiz_id, course_id, student_name, created_at`, and each lecture has `number`. Works for any attempt, not only self-eval.
- New: `GET /api/quizzes/{qid}/results` → `{n_attempts, avg_score, questions:[{id, text, n_answers, pct_correct}]}` (anonymous aggregates, used by the projector view).
- New: `GET /api/courses/{cid}/open-quizzes?student_name=` → open homework quizzes with `n_questions` and the student's `best` score.

**Pages for Phase 3 to link to:** `/quiz/{qid}` (students), **`/quiz/{qid}?present=1`** (fullscreen QR + live results that refresh every 3 s, for the projector), `/selfeval/{cid}?attempt={aid}` (re-open a report). `quiz.js` defines `runQuiz`, `renderReview`, `scoreRing`; it only auto-runs on `/quiz/` paths, so `selfeval.html` loads it as a library.

**Known issues:** in mock mode every question uses the "Which statement best describes X?" template. The shared nav (Phase 0) wraps awkwardly on a phone. Testing left a few quizzes/attempts in `data/app.db` (students "T" and "Giulia"); re-run the seed to clear them. Students can retake a quiz as often as they like (every attempt counts in insights).

### Phase 3: done (2026-11-14)
**Built:** lecturer API (`app/routes_lecturer.py`), struggle statistics + misconception summary (`app/insights.py`), the lecturer page (`static/lecturer.html/.js`), `seed/seed_fake_activity.py`, the `MISCONCEPTIONS_*` prompts and a `misconceptions` mock kind in `app/llm.py` (existing branches unchanged). Tested in mock mode with curl and in the browser (desktop + 375 px): create course, upload a PDF (status polls `uploaded → generating → ready`), generate homework/live quizzes, open/close toggle, QR link, insights chart/table, misconception summary, and a live "not covered" chat question appearing at the top of the flagged list.

**Run the demo data:** `python seed/seed_course.py && python seed/seed_fake_activity.py` (options: `--students 120`, `--course-id`, `--hard "Topic A,Topic B"`, `--seed`). By default the hard topics are the 3rd topic of class day 2 and the 4th topic of the last class day (sample course: *Gradient descent*, *Precision and recall*, scores ≈ 0.78 / 0.75 vs ≤ 0.3 for the rest). With the real course PDFs, pass `--hard` with two real topic names. The seed makes no LLM calls: it copies bank questions into one homework quiz per class day (**only the newest one stays open**, so the Phase 1 refusal path has something to match) and a closed live quiz for class 1, plus self-evaluations for ~half the students, ~200 tutor questions (user + assistant rows), ~20 flagged and 5 refused. Timestamps are UTC like SQLite's `CURRENT_TIMESTAMP`, so live demo messages sort on top.

**How insights work:** per topic of the course, `error_rate` = wrong / all answers to questions tagged to the topic (every quiz kind, including bank copies in self-evals; unanswered counts as wrong), `n_questions` = `chat_messages` with `role='user'` tagged to the topic, `n_flagged` = those with `flagged=1`. `struggle_score = 0.6*error_rate + 0.3*n_questions/max + 0.1*n_flagged/max`. Flagged and recent questions never include `student_name`.

**Differences from the contract (additions only):**
- `POST /api/courses` returns `{id, name, lecturer_name}`. `POST /courses/{cid}/lectures` returns `{id, number, title, status}`; `number` is auto-assigned (max + 1), `date` defaults to today, non-PDF → 400, > 40 MB → 413.
- New: `POST /api/lectures/{lid}/regenerate` (re-run ingest, e.g. after `error`; the page shows a Retry button).
- `GET /courses/{cid}/quizzes` returns only homework/live by default (`?include_all=true` adds bank + self_eval), each with `lecture_number, lecture_title, n_questions, n_attempts, avg_score`.
- `PATCH /quizzes/{qid}` also accepts `title`; returns `{id, kind, title, is_open}`.
- `GET /insights` topics also have `summary, lecture_id, lecture_number`; flagged/recent items have `lecture_number, lecture_title, topic_name, created_at` (recent also `flagged, refused`); plus `totals: {n_students, n_attempts, n_chat, n_flagged, n_refused}`.
- New: `POST /api/courses/{cid}/insights/misconceptions` `{topic_id?}` (default: top struggle topic) → `{topic_id, topic_name, lecture_title, summary}` (markdown, one LLM call, kind `misconceptions`; 502 on LLM failure).

**Page:** `/lecturer#class|#quizzes|#insights` opens a tab directly. The selected course is kept in `localStorage`. Insights refresh every 8 s while the tab is visible. Bars are coloured by class day (fixed categorical palette, class N → slot N) with a legend, tooltips with the breakdown, and a "Table view" toggle. Quiz rows link to `/quiz/{id}?present=1` (QR + live results) and `/quiz/{id}`.

**Known issues:** the misconception summary in mock mode is a template; check its quality with the real model in Phase 4. Uploads run ingest in a FastAPI background task in the same process, so a slow real-LLM ingest blocks nothing but is lost if the server restarts (use Retry). There is no auth on lecturer routes (prototype).

### Showcase: multi-user — done (2026-11-14)
**Built:** real students and teachers instead of free-text names. `users` + `enrollments` tables and `courses.teacher_id` (`app/db.py`, added by `init_db()` with `ALTER TABLE` on old DBs), `app/routes_users.py`, the `/people` page (`static/people.html`, inline script), and a user switcher in the shared nav (`static/common.js`). Tested with the TestClient, curl and in the browser (desktop + 375 px).

**How it works:**
- `static/common.js`: `getCurrentUser()` / `setCurrentUser(u)` hold `{id, name, role}` per tab in `sessionStorage` (new tabs default to the last pick in `localStorage`), so two tabs can be two different people. The nav switcher is the **only** way to change who you act as (/people is setup only, reached from the switcher's "Manage people"). `getStudentName()` keeps its signature and returns the current user's name; with nobody picked it opens `showUserPicker()` (searchable, this course's students first, plus "New student? Join" → `POST /api/users/join`, so QR joiners still work). The old free-text name dialog is gone (`showNameDialog()` now opens the picker).
- Nav: students get no view tabs (logo = home); teachers get Dashboard · Student view. The user chip opens the switcher. Picking a teacher goes to `/lecturer`; picking a student on `/lecturer` goes to `/`.
- Scoping (frontend only, no auth): `/` lists the student's enrolled courses (a teacher sees their own); `/lecturer` lists only the teacher's courses, "New course" uses the current teacher (no free-text lecturer field), and a non-teacher gets a "pick a teacher" card.
- /people: add students (one per line) or a teacher; a teacher can be given existing courses (ticking one moves it to them) and/or **new courses** typed one per line, also from a teacher's Edit form.
- Names are unique and are still the key in `student_name` columns: renaming a student on /people updates attempts / chat_messages / notes; renaming a teacher updates `courses.lecturer_name`. Deleting a user keeps their history (insights unchanged).
- `backfill_users()` runs at startup (idempotent): old DBs get a teacher per `lecturer_name` and a student user per `student_name` found in the history, enrolled in that course.
- Seeds: `seed_course.py` creates the `--lecturer` as a teacher user; `seed_fake_activity.py` creates every fake student as an enrolled user, so you can switch into any of them and see their chats, notes and attempts.

**Known issues:** no auth, anyone can act as anyone (by design for the showcase). Courses can't be deleted from the UI. A teacher previewing a class day chats under their own name, which counts as one more "student" in the insights totals.

### Showcase: friends — done (2026-11-14)
**Built:** real friends between students instead of the hard-coded "Giulia, Marco and Sara" card. `friendships` table (`requester_id, addressee_id, status pending|accepted`, cascades on user delete) and `users.last_seen` (added by `init_db()` with `ALTER TABLE` on old DBs), `app/routes_friends.py`, a heartbeat in `static/common.js` (`startHeartbeat()`, called by `renderNav`), and the friends card + "Friends" dialog on `/` (`static/index.html`). A teacher's "Student view" now shows only "Your courses" (no streak/friends/tasks). Tested with the TestClient and in the browser.

**API (new, additions only):**
- `GET /api/users/{uid}/friends` → `{friends:[{id, name, online, last_seen}], incoming, outgoing, n_online}` (students only, 400 for teachers).
- `POST /api/users/{uid}/friends` `{to_id}` → `{status}`; if `to_id` already asked you, it accepts instead.
- `POST /api/users/{uid}/friends/{oid}/accept`, `DELETE /api/users/{uid}/friends/{oid}` (decline, cancel or unfriend).
- `POST /api/users/{uid}/seen`: every open, visible page pings it each 60 s; "online" = seen in the last 3 minutes.

**Demo data:** `python seed/seed_friends.py` (after `seed_fake_activity.py`) replaces all friendships with a random network: each student gets a random number of friends (`--min 1 --max 8`, mostly classmates, `--classmates 0.85`) plus 0–`--pending 2` incoming requests. `--keep` adds instead of replacing, `--seed` makes it repeatable. A student can end up a bit above `--max` because others pick them too.

**Known issues:** no auth (anyone acting as a student can send/accept for them). The streak card is still hard-coded. Seeded fake students are never "online" unless someone switches into them in a tab.
