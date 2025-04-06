from typing import Optional

from app.db import Mongo
from pydantic import BaseModel, validator

db = Mongo()
media_houses_collection = db.media_houses


class MediaHouse(BaseModel):
    name: str
    hindiName: Optional[str] = None
    mhType: str

    @validator('name')
    def validate_name(cls, v):
        value = v.strip()

        if len(value) < 3 or len(value) > 35:
            raise ValueError("Name should be between 3..35 characters")
        return value

    @classmethod
    async def get_all(cls):
        directors, producers, singers, lyricists = [], [], [], []
        async for media_house in media_houses_collection.find({}):
            media_house["_id"] = str(media_house["_id"])
            if media_house["mhType"] == "Director":
                directors.append(media_house)
            elif media_house["mhType"] == "Producer":
                producers.append(media_house)
            elif media_house["mhType"] == "Singer":
                singers.append(media_house)
            elif media_house["mhType"] == "Lyricist":
                lyricists.append(media_house)
            else:
                continue

        return directors, producers, singers, lyricists
