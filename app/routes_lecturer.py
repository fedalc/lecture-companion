"""Phase 3 owns this file: course creation, PDF upload, quiz management, insights.
Contract (build plan section 5). Upload flow: save PDF to data/uploads/{lecture_id}.pdf,
set lectures.slides_path, then BackgroundTasks.add_task(app.ingest.process_lecture, lid).
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["lecturer"])
