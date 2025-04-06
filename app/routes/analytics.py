from app.db import Mongo
from fastapi import APIRouter
from fastapi.exceptions import HTTPException

db = Mongo()
analytics_collection = db.analytics

router = APIRouter()


@router.get("")
async def get_analytics(filter: str):
    if filter not in ["movies", "series", "songs"]:
        raise HTTPException(status_code=400, detail="Bad request")
    result = []
    async for data in analytics_collection.find({"type": filter}):
        data["_id"] = str(data["_id"])
        result.append(data)

    return {'analytics': result}
