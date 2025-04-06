import csv
from io import StringIO

from bson import ObjectId
from pydantic import BaseModel, ValidationError
from typing import Optional

from pymongo import ASCENDING

from app.db import Mongo

db = Mongo()
episodes_collection = db.episodes

class Episode(BaseModel):
    title: str
    hindiTitle: Optional[str]
    episodeNo: int
    seriesId: str
    tcIn: Optional[int] # HH:MM:SS
    tcOut: Optional[int]
    playbackUrl: Optional[str]
    iosPlaybackUrl: Optional[str]
    thumbnailImage: Optional[str]

    async def save(self, episode_id: str = None):
        doc = {k: v for k, v in self.__dict__.items() if v}
        result = {}
        if not episode_id:
            inserted_doc = await episodes_collection.insert_one(doc)
            result["episode_id"] = str(inserted_doc.inserted_id)
        else:
            await episodes_collection.update_one(
                {"_id": ObjectId(episode_id)},
                {"$set": doc}
            )
            result["episode_id"] = episode_id
        result["success"] = True
        return result


    @classmethod
    async def get_episodes(cls, series_id: str, page: int = 1, pageSize: int = 10, filterBy: str = None):
        result = []
        query = {"seriesId": series_id}
        if filterBy == "all":
            async for episode in episodes_collection.find(query).sort("episodeNo", ASCENDING):
                episode["_id"] = str(episode["_id"])
                result.append(episode)
            return {'episodes': result}
        total = await episodes_collection.count_documents(query)
        async for episode in (episodes_collection.find(query)
                .sort("episodeNo", ASCENDING).skip((page - 1) * pageSize).limit(pageSize)):
            episode["_id"] = str(episode["_id"])
            result.append(episode)
        return {'episodes': result, "total": total}

    @classmethod
    async def get_episode_by_id(cls, episode_id: str):
        episode = await episodes_collection.find_one({"_id": ObjectId(episode_id)})
        if not episode:
            return {'success': False, 'message': "Episode Not found"}
        episode["_id"] = str(episode["_id"])
        return {'success': True, "episode": episode}

    @classmethod
    async def delete_episode(cls, episode_id: str):
        episode = await episodes_collection.find_one({"_id": ObjectId(episode_id)})
        if not episode:
            return {'success': False, 'message': "Episode Not found"}
        await episodes_collection.delete_one({"_id": ObjectId(episode_id)})
        return {'success': True, "message": "Deleted episode"}

    @classmethod
    async def bulk_upload_episodes(cls, file):
        content = await file.read()
        decoded_content = content.decode('utf-8')
        csv_reader = csv.DictReader(StringIO(decoded_content))

        errors = []
        valid_episodes = []
        existing_episodes = {}

        async for record in episodes_collection.find({}, {"seriesId": 1, "episodeNo": 1}):
            key = (record["seriesId"], record["episodeNo"])
            existing_episodes[key] = True

        for idx, row in enumerate(csv_reader, start = 1):
            if not any(row.values()):
                continue
            try:
                stripped_row = {k: v.strip() if v else v for k, v in row.items()}
                episode = Episode(
                    title = stripped_row['title'],
                    episodeNo = int(stripped_row['episodeNo']),
                    seriesId = stripped_row['seriesId'],
                    tcIn = int(stripped_row.get('tcIn')) if stripped_row.get('tcIn') is not None else None,
                    tcOut = int(stripped_row.get('tcOut')) if stripped_row.get('tcOut') is not None else None,
                    playbackUrl = stripped_row.get('playbackUrl'),
                    iosPlaybackUrl = stripped_row.get('iosPlaybackUrl')
                )
                key = (episode.seriesId, episode.episodeNo)


                if key in existing_episodes or any(ep for ep in valid_episodes if
                                                   ep.seriesId == episode.seriesId and ep.episodeNo == episode.episodeNo):
                    errors.append(
                        f"Row {idx}: Conflict with existing episodeNo {episode.episodeNo} for seriesId {episode.seriesId}.")
                else:
                    valid_episodes.append(episode)
            except ValidationError as e:
                errors.append(f"Row {idx}: {e.errors()}")

        if errors:
            return {
                "success": "False",
                "errors": errors
            }

        if valid_episodes:
            await  episodes_collection.insert_many([episode.dict() for episode in valid_episodes])

        return {
            "success": "True",
            "message": f"{len(valid_episodes)} episodes uploaded successfully."
        }