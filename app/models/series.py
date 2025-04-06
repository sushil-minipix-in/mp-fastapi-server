import re

from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime, date
from pydantic import BaseModel, validator
from typing import List, Optional, Dict

db = Mongo()
series_collection = db.series


class Series(BaseModel):
    @classmethod
    async def get_count(cls, token):
        query = {}
        if token["partner"]:
            query["partner"] = token["id"]
        total = await series_collection.count_documents(filter=query)
        query["availability"] = "unpublished"
        unpublished = await series_collection.count_documents(
            filter=query
        )
        return total, unpublished


class SeriesAddModel(BaseModel):
    title: str
    language: List[str]
    description: str
    genre: List[str]
    actors: List[str]
    directors: List[str]
    producers: List[str]
    availability: Optional[str] = "unpublished"
    startDate: Optional[datetime]
    endDate: Optional[datetime]
    cardImage: str
    detailImage: str
    trailerImage: str
    model: str
    maturity: Optional[str] = None
    streamPeriod: Optional[int]
    subscriberPrice: Optional[Dict[str, int]] = None
    nonSubscriberPrice: Optional[Dict[str, int]] = None
    trailer: Optional[str] = None
    metaTitle: Optional[str] = None
    metaDescription: Optional[str] = None
    metaKeywords: Optional[List[str]] = None
    videoUploadDateTime: Optional[str] = None
    slug: Optional[str] = None
    oldUrl: Optional[str] = None

    @validator('slug')
    def slug_validator(cls, value):
        if value is not None:
            value = re.sub(r'[^A-Za-z0-9\-]+', '', value)
        return value

    @validator('startDate')
    def start_date_validator(cls, value):
        if value is not None:
            try:
                value = value.isoformat()
            except Exception:
                raise ValueError('Expected iso datetime format for startDate')
        return value

    @validator('endDate')
    def end_date_validator(cls, value):
        if value is not None:
            try:
                value = value.isoformat()
            except Exception:
                raise ValueError('Expected iso datetime format for endDate')
        return value

    async def save(self, token, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v is not None}
        doc["lastmod"] = str(date.today().isoformat())
        if token['partner']:
            doc['partner'] = token['id']

        if not token['superadmin']:
            doc['availability'] = 'unpublished'

        if id:
            if doc['availability'] != 'unpublished' and 'comments' in doc:
                del doc['comments']
                query = {'$set': doc, '$unset': {'comments': 1}}
            else:
                query = {'$set': doc}
            await series_collection.update_one({'_id': ObjectId(id)}, query)  # noqa: E501
        else:
            series = await series_collection.insert_one(doc)
            return str(series.inserted_id)
