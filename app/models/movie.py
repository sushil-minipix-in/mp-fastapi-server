import re

from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, validator
from typing import List, Optional, Dict

db = Mongo()
movies_collection = db.movies


class Movie(BaseModel):
    @classmethod
    async def get_count(cls, token):
        query = {}
        if token["partner"]:
            query["partner"] = token["id"]
        total = await movies_collection.count_documents(filter=query)
        query["availability"] = "unpublished"
        unpublished = await movies_collection.count_documents(
            filter=query
        )
        return total, unpublished


class Availability(str, Enum):
    PERPETUAL = "perpetual"
    RESTRICTED = "restricted"
    UNPUBLISHED = "unpublished"


class Model(str, Enum):
    TICKET = "ticket"
    SUBSCRIPTION = "subscription"
    FREE = "free"


class MovieAddModel(BaseModel):
    title: str
    description: str
    language: List[str]
    genre: List[str]
    maturity: str
    year: str
    actors: List[str]
    directors: List[str]
    producers: List[str]
    availability: Optional[Availability] = Availability.UNPUBLISHED
    startDate: Optional[datetime]
    endDate: Optional[datetime]
    detailImage: str
    cardImage: str
    trailerImage: str
    model: Model
    streamPeriod: Optional[int]
    subscriberPrice: Optional[Dict[str, int]] = None
    nonSubscriberPrice: Optional[Dict[str, int]] = None
    downloadUrl: Optional[str]
    skipIntroStart: Optional[int]
    skipIntroEnd: Optional[int]
    trailer: Optional[str] = None
    duration: int
    metaTitle: Optional[str] = None
    metaDescription: Optional[str] = None
    metaKeywords: Optional[List[str]] = None
    videoUploadDateTime: Optional[str] = None
    download: Optional[bool] = False
    comments: Optional[str] = None
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

    # @validator('cardImage')
    # def card_image_morpher(cls, v):
    #     if v and "cdn-cgi" not in v:
    #         v = v.replace(
    #             "images", "cdn-cgi/image/width=300,height=400/images")
    #     return v
    #
    # @validator('detailImage')
    # def detail_image_morpher(cls, v):
    #     if v and "cdn-cgi" not in v:
    #         v = v.replace(
    #             "images", "cdn-cgi/image/width=1500,height=500/images")
    #     return v
    #
    # @validator('trailerImage')
    # def trailer_image_morpher(cls, v):
    #     if v and "cdn-cgi" not in v:
    #         v = v.replace(
    #             "images", "cdn-cgi/image/width=512,height=288/images")
    #     return v

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
            await movies_collection.update_one({'_id': ObjectId(id)}, query)  # noqa: E501
        else:
            movie = await movies_collection.insert_one(doc)
            return str(movie.inserted_id)
