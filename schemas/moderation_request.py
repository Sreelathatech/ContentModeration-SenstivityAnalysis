from pydantic import BaseModel
from datetime import datetime

class ModerationRequest(BaseModel):
    sync_timestamp: datetime
