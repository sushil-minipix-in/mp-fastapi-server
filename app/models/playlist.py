from app.db import Mongo
from bson.objectid import ObjectId
from pydantic import BaseModel
from typing import List, Optional

db = Mongo()
playlists_collection = db.playlists


class Playlist(BaseModel):
    name: str
    page: str
    profile: Optional[str] = 'adult'
    position: int
    content: List[str]

    async def save(self, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v}

        existing = await playlists_collection.find_one(
            {
                'page': doc['page'],
                'position': doc['position']
            }
        )

        if id:
            if existing and id != str(existing['_id']):
                raise ValueError("Playlist already exists at that position")
            await playlists_collection.replace_one({'_id': ObjectId(id)}, doc)
        else:
            if existing:
                raise ValueError("Playlist already exists at that position")
            await playlists_collection.insert_one(doc)
