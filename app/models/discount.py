from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime
from pydantic import BaseModel, validator
from typing import Optional, List

db = Mongo()
discounts_collection = db.discounts


class Discount(BaseModel):
    code: str
    amount: int
    tokens: Optional[int] = None
    validFor: Optional[str] = None
    applicableOn: List[str] = []
    startDate: Optional[datetime] = None
    endDate: Optional[datetime] = None
    allowedCurrency: Optional[str] = None

    @classmethod
    def is_invalid_time(cls, doc):
        start = doc.get('startDate', None)
        end = doc.get('endDate', None)
        start = datetime.fromisoformat(start) if start else False
        end = datetime.fromisoformat(end) if end else False
        now = datetime.now(start.tzinfo) if start else start
        return (start and start > now) or (end and end < now)

    @validator('code')
    def validate_code(cls, v):
        value = v.strip().upper()
        return value

    @validator('tokens')
    def validate_tokens(cls, v):
        if v <= 0:
            raise ValueError('Tokens must be greater than 0')

        return v

    @validator('startDate')
    def start_date_validator(cls, value):
        if value is not None:
            try:
                value = value.isoformat()
            except Exception:
                raise ValueError('Expected iso date format for startDate')
        return value

    @validator('endDate')
    def end_date_validator(cls, value):
        if value is not None:
            try:
                value = value.isoformat()
            except Exception:
                raise ValueError('Expected iso date format for endDate')
        return value

    async def save(self, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v}

        if id:
            await discounts_collection.replace_one({'_id': ObjectId(id)}, doc)
        else:
            await discounts_collection.insert_one(doc)
