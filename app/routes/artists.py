from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Security

from .utils import get_current_employee
from ..models.artist import Artist, ArtistCreateModel

db = Mongo()
artists_collection = db.artists

router = APIRouter()


@router.get("")
async def get_artists(
    token=Security(get_current_employee, scopes=["Artists:read"])
):
    artists = await Artist.get_all()
    return {"artists": artists}


@router.post("")
async def create_artist(
    artist: ArtistCreateModel,
    token=Security(get_current_employee, scopes=["Artists:create"])
):
    await artists_collection.insert_one(artist.dict(include={'name', 'gender', 'hindiName'}))  # noqa: E501
    return {"success": True}


@router.delete("/{id}")
async def delete_artist(
    id: str,
    token=Security(get_current_employee, scopes=["Artists:delete"])
):
    await artists_collection.delete_one({'_id': ObjectId(id)})
    return {"success": True}
