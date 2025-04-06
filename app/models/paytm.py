from typing import Literal, Optional
from pydantic import BaseModel

from ..models.tracking_params import OrderTrackingParams


class PaytmOrder(BaseModel):
    channelId: Literal['WEB', 'WAP'] = 'WEB'
    planId: str
    discountCode: str
    tracking: Optional[OrderTrackingParams] = dict


class PaytmTicket(BaseModel):
    channelId: Literal['WEB', 'WAP'] = 'WEB'
    id: str
    type: str
    tracking: Optional[OrderTrackingParams] = dict
