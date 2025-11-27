from fastapi import APIRouter
from schemas.moderation_request import ModerationRequest
from orchestrator import run_moderation_pipeline

router = APIRouter(prefix="/moderation", tags=["Moderation Pipeline"])

@router.post("/")
async def run_moderation(req: ModerationRequest):
    """
    Trigger full moderation pipeline using the provided sync timestamp.
    """
    result = run_moderation_pipeline(req.sync_timestamp)
    return result
