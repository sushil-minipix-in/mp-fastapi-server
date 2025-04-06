import re

from app.db import Mongo
from bson.objectid import ObjectId
from pydantic import BaseModel, validator
from typing import List, Literal, Optional

db = Mongo()
songs_collection = db.songs


class Song(BaseModel):
    title: str
    language: str
    genre: List[str]
    maturity: str
    year: str
    actors: List[str]
    singers: List[str]
    lyricists: List[str]
    directors: Optional[List[str]] = None
    producers: Optional[List[str]] = None
    cardImage: Optional[str] = None
    trailerImage: Optional[str] = None
    duration: int
    model: Literal['subscription', 'free']
    availability: Optional[str] = 'unpublished'
    comments: Optional[str] = None
    slug: Optional[str] = None
    oldUrl: Optional[str] = None
    videoUploadDateTime: Optional[str] = None

    @validator('slug')
    def slug_validator(cls, value):
        if value is not None:
            value = re.sub(r'[^A-Za-z0-9\-]+', '', value)
        return value

    @classmethod
    async def get_count(cls, token):
        query = {}
        if token["partner"]:
            query["partner"] = token["id"]
        total = await songs_collection.count_documents(filter=query)
        query["availability"] = "unpublished"
        unpublished = await songs_collection.count_documents(
            filter=query
        )
        return total, unpublished

    @classmethod
    async def get_all(cls, token):
        query = {}
        if token['partner']:
            query = {"partner": token["id"]}
        songs = []
        async for song in songs_collection.find(query):
            song['_id'] = str(song['_id'])
            songs.append(song)
        return songs

    @classmethod
    async def get_by_id(cls, id):
        song = await songs_collection.find_one({'_id': ObjectId(id)})
        if song:
            song['_id'] = str(song['_id'])
            return True, song
        else:
            return False, None

    @classmethod
    async def delete(cls, id):
        song = await songs_collection.find_one({'_id': ObjectId(id)})
        result = await songs_collection.delete_one({'_id': ObjectId(id)})
        return result.acknowledged, song["title"]

    async def save(self, token, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v is not None}
        if token['partner']:
            doc['partner'] = token['id']
        if not token['superadmin']:
            doc['availability'] = 'unpublished'
        if id:
            if doc['availability'] == 'perpetual' and 'comments' in doc:
                del doc['comments']
                query = {
                    '$set': doc,
                    '$unset': {'comments': True}
                }
            else:
                query = {'$set': doc}
            result = await songs_collection.update_one(
                {'_id': ObjectId(id)},
                query
            )
        else:
            result = await songs_collection.insert_one(doc)

        return result.acknowledged
