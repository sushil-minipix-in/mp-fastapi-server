import asyncio
import motor.motor_asyncio
from bson.objectid import ObjectId

from app.config import AppConfig
from app.routes.utils import generate_dynamic_link

config = AppConfig()
mongo_uri = config.mongo_uri
db_name = config.db_name

client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
db = client[db_name]
movies_collection = db.movies
series_collection = db.series


async def update_short_links():
    async for movie in movies_collection.find():
        if 'shareLink' not in movie:
            share_link = await generate_dynamic_link(movie, 'movies')
            await movies_collection.update_one({"_id": ObjectId(movie['_id'])}, {'$set': {'shareLink': share_link}})
    async for series in series_collection.find():
        if 'shareLink' not in series:
            share_link = await generate_dynamic_link(series, 'series')
            await series_collection.update_one({"_id": ObjectId(series['_id'])}, {'$set': {'shareLink': share_link}})


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(update_short_links())
    loop.close()
