from fastapi import APIRouter, HTTPException
from typing import List
from app.models.short_playlist import ShortPlaylist

from datetime import date

from app.db import Mongo
db = Mongo()
webseries_collection = db.webseries

router = APIRouter()

@router.get("")
async def search(
    page: str = None,
    genre: str = None,
    language: str = None,
    q: str = None
):
    if not any([page,genre, language, q]):
        raise HTTPException(400, "Bad Request")
    if page and page != "coming-soon":
        result = await ShortPlaylist.get_playlists(
            token = {"admin": False},
            page=page,
            filterBy="all"
        )
        return result

    if page and page == "coming-soon":
        result = await get_coming_soon_content()
        return result
    if genre:
        result = await filter_content_by_genre([genre])
        return result
    if language:
        result = await filter_content_by_language([language])
        return result
    if q:
        result = await filter_content_by_text_search(q)
        return result


async def get_coming_soon_content():
    """
    Filter the unpublished content in the ascending order of Publish date - 'publishDate'
    """
    result = []
    current_date_iso = date.today().isoformat()
    async for data in webseries_collection.find(
            {
                "availability": "unpublished",
                "publishDate": {"$exists": True, "$ne": None, "$gt": current_date_iso},
                }
            ).sort("publishDate", 1):  # Sorting in ascending order
        data["_id"] = str(data["_id"])
        result.append(data)
    return result

async def filter_content_by_genre(genre: List[str]):
    """
    Filters web series by genre using an async for loop.
    """
    query = {"genre": {"$in": genre}}
    result = []
    async for ws in webseries_collection.find(query):
        ws["_id"] = str(ws["_id"])
        result.append(ws)
    return {"success": True, "result": result}


async def filter_content_by_language(language: List[str]):
    """
    Filters web series by language using an async for loop.
    """
    query = {"language": {"$in": language}}
    result = []
    async for ws in webseries_collection.find(query):
        ws["_id"] = str(ws["_id"])
        result.append(ws)
    return {"success": True, "result": result}


async def filter_content_by_text_search(q: str):
    """
    Filters web series by partial text search in the title, description, or slug fields using an async for loop.
    """
    query = {
        "$or": [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"slug": {"$regex": q, "$options": "i"}},
        ]
    }
    result = []
    async for ws in webseries_collection.find(query):
        ws["_id"] = str(ws["_id"])
        result.append(ws)
    return {"success": True, "result": result}
