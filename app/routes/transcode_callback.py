from app.config import AppConfig
from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

db = Mongo()
movies_collection = db.movies
series_collection = db.series
songs_collection = db.songs
episodes_collection = db.episodes


class Body(BaseModel):
    id: str
    type: str


config = AppConfig()
transcode_secret = config.transcode_secret
cdn_url = config.cdn_url

router = APIRouter()

@router.post("")
async def update_streams(body: Body):
    content_type, content_id = body.type, body.id
    now_date_time = datetime.now(timezone.utc).astimezone().isoformat()
    if content_type not in ["movies", "movie_trailers",
     "series_trailers", "episodes", "songs", "shorts"]:
        return {'success': False, "message": 'Invalid Input'}

    collection = None
    if content_type in ["movies", "movie_trailers"]:
        collection = movies_collection

    if content_type == "movies":
        await movies_collection.update_one(
            {"_id": ObjectId(content_id)},
            {
                "$set": {
                    "playbackUrl": f"https://{cdn_url}/movies/{content_id}/stream.mpd",
                    "iosPlaybackUrl": f"https://{cdn_url}/movies/{content_id}/stream.m3u8",
                    "videoUploadDateTime": now_date_time
                }
            }
        )

    if content_type == "movie_trailers":
        await movies_collection.update_one(
            {"_id": ObjectId(content_id)},
            {
                "$set": {
                    "trailer": f"https://{cdn_url}/{content_type}/{content_id}/stream.mpd",
                    "iosTrailer": f"https://{cdn_url}/{content_type}/{content_id}/stream.m3u8",
                }
            }
        )

    if content_type == "songs":
        await songs_collection.update_one(
            {"_id": ObjectId(content_id)},
            {
                "$set": {
                    "playbackUrl": f"https://{cdn_url}/{content_type}/{content_id}/stream.mpd",
                    "iosPlaybackUrl": f"https://{cdn_url}/{content_type}/{content_id}/stream.m3u8",
                    "videoUploadDateTime": now_date_time
                }
            }
        )

    if content_type == "series_trailers":
        await series_collection.update_one(
            {"_id": ObjectId(content_id)},
            {
                "$set": {
                    "trailer": f"https://{cdn_url}/{content_type}/{content_id}/stream.mpd",
                    "iosTrailer": f"https://{cdn_url}/{content_type}/{content_id}/stream.m3u8"
                }
            }
        )

    if content_type == "episodes":
        [series_id, season_number, episode_number] = body.id.split('_')
        await series_collection.update_one(
            {'_id': ObjectId(series_id)},
            {
                '$set': {
                    'episodes.$[episode].playbackUrl': f'https://{cdn_url}/{content_type}/{content_id}/stream.mpd',
                    'episodes.$[episode].iosPlaybackUrl': f'https://{cdn_url}/{content_type}/{content_id}/stream.m3u8',  # noqa: E501
                    'episodes.$[episode].videoUploadDateTime': now_date_time
                }
            },
            array_filters = [
                {
                    "episode.season": int(season_number),
                    "episode.number": int(episode_number)
                }
            ]
        )


    if content_type == "shorts":
        series_id, start_episode, end_episode = content_id.split('_')

        update_query = {
            "seriesId": series_id,
            "episodeNo": {"$gte": int(start_episode), "$lte": int(end_episode)}
        }
        update_data = {
            "$set": {
                "playbackUrl": f"https://{cdn_url}/shorts/{content_id}/stream.mpd",
                "iosPlaybackUrl": f"https://{cdn_url}/shorts/{content_id}/stream.m3u8"
            }
        }
        await episodes_collection.update_many(update_query, update_data)

    return {'success': True}

