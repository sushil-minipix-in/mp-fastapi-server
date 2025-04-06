from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Security
from pydantic import BaseModel, validator
from typing import Optional

from .utils import get_current_employee

db = Mongo()
languages_collection = db.languages

router = APIRouter()


class Language(BaseModel):
    name: str
    hindiName: Optional[str] = None
    nativeName: Optional[str] = None
    cardImage: Optional[str] = None

    @validator("name")
    def name_validator(cls, v):
        value = v.strip()
        if len(value) < 3 or len(value) > 35:
            raise ValueError('Name should be between 3..35 characters')
        return value


@router.get("")
async def get_languages():
    languages = []
    async for lang in languages_collection.find():
        lang["_id"] = str(lang["_id"])
        languages.append(lang)
    languages = sorted(languages, key=lambda language: language['name'])
    return {"success": True, "languages": languages}


@router.post("")
async def create_language(
    language: Language,
    token=Security(get_current_employee, scopes=["Languages:create"])
):
    doc = {k: v for k, v in language.__dict__.items() if v}
    await languages_collection.insert_one(doc)
    return {"success": True}


@router.put("/{id}")
async def update_language(
    id: str,
    language: Language,
    token=Security(get_current_employee, scopes=["Languages:update"])
):
    doc = {}
    if language.nativeName:
        doc['nativeName'] = language.nativeName
    if language.cardImage:
        doc['cardImage'] = language.cardImage

    await languages_collection.update_one({'_id': ObjectId(id)}, {'$set': doc})
    return {"success": True}


@router.delete("/{id}")
async def delete_language(
    id: str,
    token=Security(get_current_employee, scopes=["Languages:delete"])
):
    await languages_collection.delete_one({'_id': ObjectId(id)})
    return {"success": True}
