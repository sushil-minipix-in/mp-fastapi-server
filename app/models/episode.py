from app.db import Mongo
from bson.objectid import ObjectId
from pydantic import BaseModel
from typing import List, Optional, Dict

db = Mongo()
series_collection = db.series


class EpisodeAddModel(BaseModel):
    name: str
    description: str
    season: int
    number: int
    actors: Optional[List[str]]
    directors: Optional[List[str]]
    producers: Optional[List[str]]
    cardImage: str
    skipIntroStart: Optional[int] = None
    skipIntroEnd: Optional[int] = None
    duration: int
    old: Optional[Dict] = None
    creditsStart: Optional[int] = None
    download: Optional[bool] = False
    videoUploadDateTime: Optional[str] = None

    async def save(self, id):
        series = await series_collection.find_one({'_id': ObjectId(id)})
        if not series:
            raise ValueError('Series not found')

        if 'episodes' in series and not self.old:
            for episode in series['episodes']:
                if episode['season'] == self.season and episode['number'] == self.number:  # noqa: E501
                    raise ValueError('Episode already exists')

        doc = {k: v for k, v in self.__dict__.items() if v == 0 or v}

        if 'old' in doc:
            season = doc['old']['season']
            number = doc['old']['number']
            doc['playbackUrl'] = doc['old'].get('playbackUrl', None)
            doc['iosPlaybackUrl'] = doc['old'].get('iosPlaybackUrl', None)
            doc['videoUploadDateTime'] = doc['old'].get('videoUploadDateTime', None)  # noqa: E501
            doc['subtitles'] = doc['old'].get('subtitles', None)
            doc = {k: v for k, v in doc.items() if v is not None}
            del doc['old']

            await series_collection.update_one(
                {'_id': ObjectId(id)},
                {'$set': {'episodes.$[episode]': doc}},
                array_filters=[
                    {"episode.season": season, "episode.number": number}]
            )

            return

        await series_collection.update_one(
            {'_id': ObjectId(id)},
            {'$push': {'episodes': {
                '$each': [doc],
                '$sort': {'season': 1, 'number': 1}
            }}}
        )
