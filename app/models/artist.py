from typing import Optional

from app.db import Mongo
from pydantic import BaseModel, validator

db = Mongo()
artists_collection = db.artists


class Artist(BaseModel):
    @classmethod
    async def get_all(cls):
        artists = []
        async for artist in artists_collection.find({}):
            artist['_id'] = str(artist['_id'])
            artists.append(artist)

        return artists


class ArtistCreateModel(BaseModel):
    name: str
    hindiName: Optional[str]
    gender: str

    @validator("name")
    def name_validator(cls, v):
        value = v.strip()
        if len(value) < 3:
            raise ValueError('Name is too short')
        return value

    @validator("gender")
    def gender_validator(cls, v):
        value = v.strip()
        if not (value == "M" or value == "F"):
            raise ValueError('Gender is invalid')
        return value
