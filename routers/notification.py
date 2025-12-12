from fastapi import APIRouter
from schemas.moderation_request import ModerationRequest
from orchestrator import run_moderation_pipeline
from modules.email_sender import send_moderation_report_email
import os

router = APIRouter(prefix="/notify", tags=["Notification"])


@router.post("/email")
async def send_email_notification(req: ModerationRequest):
    """
    Run moderation pipeline and send email notification with results.
    Attaches CSV report if any entities are flagged for review.
    
    Trigger via cron job:
    0 */4 * * * curl -X POST "http://localhost:9001/notify/email" ...
    """
    
    # 1. Run the moderation pipeline
    result = run_moderation_pipeline(req.sync_timestamp)
    
    # 2. Determine CSV path (only attach if flagged entities exist)
    csv_path = None
    if result.get("flagged_entities", 0) > 0:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        csv_path = os.path.join(project_root, "outputs", "review_final.csv")
        
        if not os.path.exists(csv_path):
            csv_path = None
    
    # 3. Send email notification
    email_result = send_moderation_report_email(
        summary=result,
        csv_path=csv_path
    )
    
    # 4. Return combined response
    return {
        "moderation": result,
        "email": email_result
    }
