from bson import ObjectId
from pydantic import BaseModel
from typing import List, Optional

from pymongo import ASCENDING

from app.db import Mongo

db = Mongo()
short_playlists_collection = db.short_playlists
webseries_collection = db.webseries

class ShortPlaylist(BaseModel):
    title: str
    hindiTitle: Optional[str]
    style: str
    page: str
    position: str
    content: List[str]

    async def save(self, playlist_id=None):
        doc = {k: v for k, v in self.__dict__.items() if v}

        existing = await short_playlists_collection.find_one(
            {
                'page': doc['page'],
                'position': doc['position']
            }
        )

        if playlist_id:
            if existing and playlist_id != str(existing['_id']):
                return {'success': False, "message":"Playlist already exists at that position"}
            await short_playlists_collection.replace_one({'_id': ObjectId(playlist_id)}, doc)
            return {'success': True, "playlist_id": playlist_id}
        else:
            if existing:
                return {'success': False, "message": "Playlist already exists at that position"}
            result = await short_playlists_collection.insert_one(doc)
            return {'success': True, "playlist_id": str(result.inserted_id)}


    @classmethod
    async def get_playlists(cls, filterBy: str, token: dict, page: str, playlist_id: str = None, pageNo: int = 1, pageSize: int = 10):
        result = []
        query = {}
        if playlist_id is None:
            query = {"page": page}
            if filterBy == "all":
                async for playlist in short_playlists_collection.find(query):
                    playlist["_id"] = str(playlist["_id"])
                    content_ids = playlist.get("content", [])
                    if content_ids and not token["admin"]:
                        await cls.populate_contents(content_ids, playlist)
                    result.append(playlist)
                return {"success": True, "playlists": result}
            async for playlist in (short_playlists_collection.find(query)
                .sort("position", ASCENDING).skip((pageNo - 1) * pageSize).limit(pageSize)):
                playlist["_id"] = str(playlist["_id"])
                content_ids = playlist.get("content", [])
                if content_ids and not token["admin"]:
                    await cls.populate_contents(content_ids, playlist)
                result.append(playlist)
            return {'success': True, 'playlists': result, "pageNo": pageNo, "pageSize": pageSize}
        if playlist_id:
            query = {"_id": ObjectId(playlist_id)}
            playlist = await short_playlists_collection.find_one(query)
            if not playlist:
                return {'success': False, "message": "Playlist Not Found"}
            playlist["_id"] = str(playlist["_id"])
            content_ids = playlist.get("content", [])
            if content_ids and not token["admin"]:
                await cls.populate_contents(content_ids, playlist)
            return {"success": True, "playlist": playlist}

    @classmethod
    async def populate_contents(cls, content_ids, playlist):
        content_object_ids = [ObjectId(id) for id in content_ids]
        webseries_list = await webseries_collection.find(
            {"_id": {"$in": content_object_ids}}
        ).to_list(None)
        webseries_list = [{**ws, "_id": str(ws["_id"])} for ws in webseries_list]
        webseries_dict = {str(ws["_id"]): ws for ws in webseries_list}
        ordered_webseries = [webseries_dict[str(ws_id)] for ws_id in content_ids if str(ws_id) in webseries_dict]
        playlist["webseries_details"] = ordered_webseries[::-1]

        # content_object_ids = [ObjectId(id) for id in content_ids]
        # webseries = await webseries_collection.find(
        #     {"_id": {"$in": content_object_ids}}
        # ).to_list(None)
        # for ws in webseries:
        #     ws["_id"] = str(ws["_id"])
        # playlist["webseries_details"] = webseries

    @classmethod
    async def delete_playlist(cls, playlist_id: str):
        playlist = await short_playlists_collection.find_one({"_id": ObjectId(playlist_id)})
        if not playlist:
            return {"success": False, "message": "Playlist Not Found"}
        await short_playlists_collection.delete_one({"_id": ObjectId(playlist_id)})
        return {'success': True, 'message': "Successfully Deleted Playlist"}