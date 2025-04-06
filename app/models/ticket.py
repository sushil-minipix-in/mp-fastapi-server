from pydantic import BaseModel
from typing import Optional

from ..models.tracking_params import OrderTrackingParams


class Ticket(BaseModel):
    id: str
    type: Optional[str] = 'movie'
    tracking: Optional[OrderTrackingParams] = dict


class CaptureTicket(BaseModel):
    paymentId: str
    signature: str
