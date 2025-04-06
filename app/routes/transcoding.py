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


class Body(BaseModel):
    id: str
    type: str


config = AppConfig()
transcode_secret = config.transcode_secret
cdn_url = config.cdn_url

router = APIRouter()


@router.post("")
async def handle_callback(body: Body, secret: str):
    if secret != transcode_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    now_date_time = datetime.now(timezone.utc).astimezone().isoformat()

    if body.type == "movies":
        prefix = f'https://{cdn_url}/movies/{body.id}/{body.id}'

        await movies_collection.update_one(
            {'_id': ObjectId(body.id)},
            {
                '$set': {
                    'playbackUrl': f'{prefix}_h264.mpd',
                    'iosPlaybackUrl': f'{prefix}_h264.m3u8',
                    'videoUploadDateTime': now_date_time
                }
            }
        )
    elif body.type == "episode":
        [series_id, season_number, episode_number] = body.id.split('_')
        prefix = f'https://{cdn_url}/series/{body.id}/{body.id}'

        await series_collection.update_one(
            {'_id': ObjectId(series_id)},
            {
                '$set': {
                    'episodes.$[episode].playbackUrl': f'{prefix}_h264.mpd',
                    'episodes.$[episode].iosPlaybackUrl': f'{prefix}_h264.m3u8',  # noqa: E501
                    'episodes.$[episode].videoUploadDateTime': now_date_time
                }
            },
            array_filters=[
                {
                    "episode.season": int(season_number),
                    "episode.number": int(episode_number)
                }
            ]
        )
    elif body.type == "songs":
        prefix = f'https://{cdn_url}/songs/{body.id}/{body.id}'

        await songs_collection.update_one(
            {'_id': ObjectId(body.id)},
            {
                '$set': {
                    'playbackUrl': f'{prefix}_h264.mpd',
                    'iosPlaybackUrl': f'{prefix}_h264.m3u8',
                    'videoUploadDateTime': now_date_time
                }
            }
        )
    elif body.type == "movie_trailer":
        prefix = f'https://{cdn_url}/movies/{body.id}_trailer'

        await movies_collection.update_one(
            {'_id': ObjectId(body.id)},
            {
                '$set': {
                    'trailer': f'{prefix}/stream.mpd',
                    'iosTrailer': f'{prefix}/stream.m3u8',
                    'mp4Trailer': f'{prefix}_480p.mp4'
                }
            }
        )
    elif body.type == "series_trailer":
        prefix = f'https://{cdn_url}/series/{body.id}_trailer'

        await series_collection.update_one(
            {'_id': ObjectId(body.id)},
            {
                '$set': {
                    'trailer': f'{prefix}/stream.mpd',
                    'iosTrailer': f'{prefix}/stream.m3u8',
                    'mp4Trailer': f'{prefix}_480p.mp4',
                    'videoUploadDateTime': now_date_time
                }
            }
        )

    return {'success': True}
