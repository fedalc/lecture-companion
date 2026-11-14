"""Phase 1 owns this file: tutor chat + notes.
Contract (build plan section 5):
  POST /api/lectures/{lid}/chat   {student_name, message, highlighted_text?} -> {reply, topic_id, flagged, refused}
  GET  /api/lectures/{lid}/chat?student_name=
  GET/POST /api/lectures/{lid}/notes
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["chat"])
