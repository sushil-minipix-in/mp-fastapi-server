from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Security

from .utils import get_current_employee
from ..models.media_house import MediaHouse

db = Mongo()
media_houses_collection = db.media_houses

router = APIRouter()


@router.get("")
async def get_media_houses(
    token=Security(get_current_employee, scopes=["Media Houses:read"])
):
    directors, producers, singers, lyricists = await MediaHouse.get_all()
    return {
        "directors": directors,
        "producers": producers,
        "singers": singers,
        "lyricists": lyricists
    }


@router.post("")
async def create_media_house(
    mh: MediaHouse,
    token=Security(get_current_employee, scopes=["Media Houses:create"])
):
    await media_houses_collection.insert_one(mh.dict(include={"name", "mhType", "hindiName"}))  # noqa: E501
    return {"success": True}


@router.delete("/{id}")
async def delete_media_house(
    id: str,
    token=Security(get_current_employee, scopes=["Media Houses:delete"])
):
    await media_houses_collection.delete_one({'_id': ObjectId(id)})
    return {"success": True}
