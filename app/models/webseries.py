from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, validator
from typing import List, Optional
from pymongo import DESCENDING

from datetime import date

from app.db import Mongo
from app.routes.utils import get_similar_query, pop_random

db = Mongo()
webseries_collection = db.webseries

class Availability(str, Enum):
    PERPETUAL = "perpetual"
    RESTRICTED = "restricted"
    UNPUBLISHED = "unpublished"

class Model(str, Enum):
    SUBSCRIPTION = "subscription"
    FREE = "free"

class WebSeries(BaseModel):
    title: str
    hindiTitle: Optional[str]
    description: str
    year: int
    hindiDescription: Optional[str]
    slug: str
    language: List[str]
    hindiLanguage: Optional[List[str]]
    genre: List[str]
    hindiGenre: Optional[List[str]]
    actors: List[str]
    hindiActors: Optional[List[str]]
    directors: List[str]
    hindiDirectors: Optional[List[str]]
    producers: List[str]
    hindiProducers: Optional[List[str]]
    maturity: str
    hindiMaturity: Optional[str]
    availability: Availability = Availability.UNPUBLISHED
    model: Model = Model.SUBSCRIPTION
    metaTitle: str
    metaDescription: str
    metaKeywords: List[str]
    numberOfEpisodes: int
    trailerImage: str # 512 X 288
    cardImage: str # 300 X 400
    longVerticalImage: str # 375 X 563
    publishDate: Optional[date] = None

    @validator("publishDate")
    def validate_publish_date(cls, value):
        if value is not None:
            try:
                value = value.isoformat()
            except Exception:
                raise ValueError('Expected iso datetime format for endDate')
        return value

    async def save(self, token: str, webseries_id = None):
        doc = {k:v for k,v in self.__dict__.items() if v}

        if not token["superadmin"]:
            doc["availability"] = Availability.UNPUBLISHED

        if "publishDate" in doc and date.fromisoformat(doc["publishDate"]) > date.today():
            doc["availability"] = Availability.UNPUBLISHED

        result = {}
        if not webseries_id:
            inserted_doc = await webseries_collection.insert_one(doc)
            result["webseries_id"] = str(inserted_doc.inserted_id)
        else:
            await webseries_collection.update_one(
                {"_id": ObjectId(webseries_id)},
                {"$set": doc}
            )
            result["webseries_id"] = webseries_id
        result["success"] = True

        return result

    @classmethod
    async def get_webseries_by_id(cls, webseries_id: str, token: dict):
        if token and "admin" in token:
            result = await webseries_collection.find_one({"_id": ObjectId(webseries_id)})
            if not result:
                return {'success': False, 'message': "Webseries Not Found"}
            result["_id"] = str(result["_id"])
            return {'success': True, **result}
        else:
            result = await webseries_collection.find_one({"_id": ObjectId(webseries_id), "availability": "perpetual"})
            if not result:
                return {'success': False, 'message': "Webseries Not Found"}
            result["_id"] = str(result["_id"])
            similar_webseries_query = get_similar_query(result, {})
            result["similar_webseries"] = await get_similar_webseries(similar_webseries_query)
            return {'success': True, **result}


    @classmethod
    async def get_webseries(cls, page: int = 1, pageSize: int = 10, filterBy: str = None):
        result = []
        query = {}
        if filterBy == "all":
            async for webseries in (webseries_collection.find(query, {'_id': 1, 'title': 1}).sort("_id", DESCENDING)):
                webseries["_id"] = str(webseries["_id"])
                result.append(webseries)
            return {'webseries': result}
        total = await webseries_collection.count_documents(query)
        async for webseries in (webseries_collection.find(query)
            .sort("_id", DESCENDING).skip((page - 1) * pageSize).limit(pageSize)):
            webseries["_id"] = str(webseries["_id"])
            result.append(webseries)
        return {'webseries': result, "total": total}

    @classmethod
    async def delete_webseries(cls, webseries_id: str, token: dict):
        webseries = await webseries_collection.find_one({"_id": ObjectId(webseries_id)})

        if not webseries:
            return {"success": False, "message": "Webseries not found"}
        if webseries["availability"] == "perpetual" and token["superadmin"] is not True:
            return {"success": False, "message": "Not authorized"}

        await webseries_collection.delete_one({"_id": ObjectId(webseries_id)})

        return {"success": True, "message": "Deleted webseries successfully"}



async def get_similar_webseries(query):
    webseries, similar = [], []
    async for doc in webseries_collection.find(query).limit(25):
        doc['_id'] = str(doc['_id'])
        webseries.append(doc)

    if len(webseries) < 5:
        return webseries

    similar = [pop_random(webseries) for _ in range(5)]

    return similar
