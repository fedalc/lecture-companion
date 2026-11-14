# CLAUDE.md

Hackathon prototype: **AI Lecture Companion** (Reply Student Tech Clash 2026, "AI on Campus").
Time budget is 3–4 hours in total, so favour working and simple over complete.

## Read first
1. `docs/BUILD_PLAN.md`: the **single source of truth**. It has the phases, file ownership, data model,
   API contract and the Phase log. Read the Phase log (section 9) before writing code: it lists helpers
   that already exist.
2. `docs/HACKATHON_BRIEF.md`: what the judges require and how they score.

## Working rules
- The user tells you which **phase** you're doing. Do only that phase and edit only the files it owns
  (section 3 of the plan). Other phases run in parallel in other sessions.
- Don't rename or change anything in the shared contract (plan sections 3–5). Adding is fine.
- Call the LLM only through `app/llm.py` (`complete`, `complete_json`). Put prompts in `app/prompts.py`
  under your phase's section, with inputs in XML tags (`<material>`, `<topics>`, `<message>`, `<highlight>`)
  so mock mode works.
- Use the DB helpers in `app/db.py` (`query`, `query_one`, `execute`). Plain sqlite3, no ORM.
- Frontend: plain HTML + vanilla JS + Tailwind CDN. Reuse `static/common.js` (`api`, `renderNav`,
  `getStudentName`, `pathId`, `escapeHtml`, `statusBadge`, `comingSoon`).
- Develop in **mock mode** (`LLM_PROVIDER=mock` in `.env`). It needs no API key.
- When the phase is finished: append a "Phase N: done" entry to section 9 of `docs/BUILD_PLAN.md`
  (what was built, contract differences, known issues), then commit on a branch named `phase-N`.

## Commands
```bash
pip install -r requirements.txt
python seed/seed_course.py          # resets the DB! use --keep to keep data
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Pages: `/` (student), `/course/{id}`, `/lecture/{id}`, `/quiz/{id}`, `/selfeval/{id}`, `/lecturer`.
