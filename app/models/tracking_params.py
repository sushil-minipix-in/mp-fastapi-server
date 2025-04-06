from pydantic import BaseModel
from typing import Optional


class OrderTrackingParams(BaseModel):
    source: Optional[str] = None
    medium: Optional[str] = None
    last_page: Optional[str] = None
    platform: Optional[str] = None
    campaign: Optional[str] = None
    renewal: Optional[bool] = False

    @classmethod
    def parse_params(cls, tracking):
        if isinstance(tracking, dict):
            return tracking
        if isinstance(tracking, OrderTrackingParams):
            return tracking.__dict__
        return {}
