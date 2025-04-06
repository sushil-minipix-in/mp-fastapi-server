from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Security, HTTPException, Depends

from .utils import decode_headers, get_current_employee
from ..models.playlist import Playlist

db = Mongo()
playlists_collection = db.playlists
movies_collections = db.movies
series_collections = db.series
songs_collection = db.songs

router = APIRouter()


@router.get("")
async def get_playlists(
    page: str,
    token=Security(get_current_employee, scopes=["Playlists:read"])
):
    playlists = []
    async for playlist in playlists_collection.find({"page": page}):
        playlist["_id"] = str(playlist["_id"])
        playlists.append(playlist)

    return {'playlists': playlists}


@router.get("/{name}")
async def get_playlist(
    name: str,
    page: str,
    headers: dict = Depends(decode_headers)
):
    if headers['child']:
        page = f"{page}-kids"
    playlist = await playlists_collection.find_one({'name': name, 'page': page})  # noqa: E501
    if playlist:
        playlist['_id'] = str(playlist['_id'])
        result = []
        content = playlist.get('content', [])[::-1]
        content_type = get_content_type(page)
        for item in content:
            _id = item
            if "|" in item:
                content_type, _id = item.split("|")

            if content_type == "movie":
                data = await movies_collections.find_one({"_id": ObjectId(_id)})
                if data:
                    data['_id'] = str(data["_id"])
                    data['slugUrl'] = f"movies/{data.get('slug','movie')}-{_id}"
                    data['type'] = "movie"
                    result.append(data)
            if content_type == "series":
                data = await series_collections.find_one({"_id": ObjectId(_id)})
                if data:
                    data['_id'] = str(data["_id"])
                    data['slugUrl'] = f"series/{data.get('slug','series')}-{_id}"
                    data['type'] = "series"
                    result.append(data)
            if content_type == "song":
                data = await songs_collection.find_one({"_id": ObjectId(_id)})
                if data:
                    data['_id'] = str(data["_id"])
                    data['type'] = "song"
                    result.append(data)
        return {"playlist": playlist, "data": result}
    else:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("")
async def create_playlist(
    playlist: Playlist,
    token=Security(get_current_employee, scopes=["Playlists:create"])
):
    await playlist.save()
    return {'success': True}


@router.put("/{id}")
async def update_playlist(
    playlist: Playlist,
    id: str,
    token=Security(get_current_employee, scopes=["Playlists:update"])
):
    await playlist.save(id)
    return {'success': True}


@router.delete("/{id}")
async def delete_playlist(
    id: str,
    token=Security(get_current_employee, scopes=["Playlists:delete"])
):
    await playlists_collection.delete_one({'_id': ObjectId(id)})
    return {'success': True}


def get_content_type(page):
    _type = None
    if page in ["home", "home-kids"]:
        _type = None
    elif page in ["movies", "movies-kids"]:
        _type = "movie"
    elif page in ["series", "series-kids"]:
        _type = "series"
    elif page in ["songs", "songs-kids"]:
        _type = "song"
    elif page in ["search", "search-kids"]:
        _type = None

    return _type
