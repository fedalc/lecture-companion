# AI Lecture Companion

Hackathon prototype for *AI on Campus* (Reply Student Tech Clash 2026). The full plan is in the
Hackathon project: `claude/build_plan.md`. (Phase 4 expands this README.)

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # LLM_PROVIDER=mock works without a key

python seed/seed_course.py         # sample course, or your PDFs from seed/material/
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 (student) and http://localhost:8000/lecturer (lecturer).

## Use your own course material

Put 2–3 lecture PDFs in `seed/material/`, named `01_Topic.pdf`, `02_Topic.pdf`, …, then:

```bash
python seed/seed_course.py --course "Your course" --lecturer "Prof. Name"
```

## People and switching user

Use the user chip at the top right to switch to any student or teacher. Its "Manage people" link opens
the setup page (`/people`): add students (one name per line) and enroll them in courses, or add a teacher
and create their courses right there. Each tab keeps its own user, so a teacher and a student can run side
by side. The seeds create the course's teacher and ~120 enrolled students.

## Switch to a real LLM

In `.env`, set `LLM_PROVIDER=anthropic` (or `openai`) and the matching API key, then re-run the seed script.
Every LLM call is logged in the `agent_logs` table of `data/app.db`.
