from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Security
from pydantic import BaseModel, validator
from typing import Optional

from .utils import get_current_employee

db = Mongo()
genres_collection = db.genres


router = APIRouter()


class Genre(BaseModel):
    name: str
    hindiName: Optional[str] = None
    cardImage: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        value = v.strip()

        if len(value) < 3 or len(value) > 35:
            raise ValueError("Name must be within 3..35 characters")
        return value


@router.get("")
async def get_genres():
    genres = []
    async for genre in genres_collection.find():
        genre["_id"] = str(genre["_id"])
        genres.append(genre)
    genres = sorted(genres, key=lambda genre: genre['name'])
    return {"success": True, "genres": genres}


@router.post("")
async def create_genre(
    genre: Genre,
    token=Security(get_current_employee, scopes=["Genres:create"])
):
    await genres_collection.insert_one({k: v for k, v in genre.__dict__.items() if v})  # noqa: E501
    return {"success": True}


@router.put("/{id}")
async def update_genre(
    id: str,
    genre: Genre,
    token=Security(get_current_employee, scopes=["Genres:update"])
):
    doc = {}
    if genre.cardImage:
        doc['cardImage'] = genre.cardImage

    await genres_collection.update_one({'_id': ObjectId(id)}, {'$set': doc})
    return {"success": True}


@router.delete("/{id}")
async def delete_genre(
    id: str,
    token=Security(get_current_employee, scopes=["Genres:delete"])
):
    await genres_collection.delete_one({'_id': ObjectId(id)})
    return {"success": True}
