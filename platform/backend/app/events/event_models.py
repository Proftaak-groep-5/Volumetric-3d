from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict

class BaseEvent(BaseModel):
    event_type: str
    timestamp: datetime = datetime.utcnow()
    payload: Dict[str, Any]
