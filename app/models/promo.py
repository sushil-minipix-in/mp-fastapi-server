from app.db import Mongo
from bson.objectid import ObjectId
from pydantic import BaseModel, validator
from typing import Optional

db = Mongo()
promos_collection = db.promos


class Promo(BaseModel):
    page: str
    profile: Optional[str] = 'adult'
    promoType: Optional[str] = None
    movie: Optional[str] = None
    series: Optional[str] = None
    song: Optional[str] = None
    webseries: Optional[str] = None
    position: int
    bannerImage: str
    mobileImage: Optional[str] = None

    @validator('position')
    def validate_position(cls, v, values):
        if v < 0:
            raise ValueError('Position cannot be negative')

        return v
    
    # @validator('bannerImage')
    # def banner_image_morpher(cls, v):
    #     if v and "cdn-cgi" not in v:
    #         v = v.replace("images", "cdn-cgi/image/width=1600,height=450/images")
    #     return v
    #
    # @validator('mobileImage')
    # def mobile_image_morpher(cls, v):
    #     if v and "cdn-cgi" not in v:
    #         v = v.replace("images", "cdn-cgi/image/width=512,height=288/images")
    #     return v

    async def save(self, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v}

        existing = await promos_collection.find_one(
            {
                'page': doc['page'],
                'position': doc['position']
            }
        )

        if id:
            if existing and str(existing['_id']) != id:
                return False

            await promos_collection.replace_one({'_id': ObjectId(id)}, doc)
            return True
        else:
            if existing:
                return False
            await promos_collection.insert_one(doc)
            return True
