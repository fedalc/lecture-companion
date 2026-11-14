"""Phase 2 owns this file: quizzes, QR codes, self-evaluation.
Contract (build plan section 5). Tip: app.ingest.generate_questions() already creates an
LLM-generated quiz for a lecture; reuse it for homework/live quizzes.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["quiz"])
