import re

from app.db import Mongo
from bson.regex import Regex
from bson.objectid import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime

from .utils import decode_headers

db = Mongo()
movies_collection = db.movies
series_collection = db.series
songs_collection = db.songs
playlists_collection = db.playlists
languages_collection = db.languages
genres_collection = db.genres

router = APIRouter()
date_time_format = "%Y-%m-%dT%H:%M:%S"


async def language_search(language: str, sub_query: dict):
    content_list = []
    query = {'availability': {'$ne': 'unpublished'}, **sub_query}
    async for movie in movies_collection.find({'language': language, **query}):
        movie['_id'] = str(movie['_id'])
        movie['slugUrl'] = f"movies/{movie.get('slug','movie')}-{movie['_id']}"
        movie['type'] = 'movies'
        content_list.append(movie)
    async for series in series_collection.find({'language': language, **query}):  # noqa: E501
        series['_id'] = str(series['_id'])
        series['slugUrl'] = f"series/{series.get('slug','series')}-{series['_id']}"
        series['type'] = 'series'
        content_list.append(series)
    return {'data': content_list}


async def get_all_playlist_content(filter):
    playlists = []
    async for playlist in playlists_collection.find({"page": filter}).sort("position"):
        playlists.append(playlist)
    playlist_content = {}
    playlist_order = []
    for p in playlists:
        playlist_content, playlist_order = await get_default_playlist(p, playlist_content, playlist_order, filter)

    return playlist_content, playlist_order


@router.get("/languages")
async def get_content_by_language(
    headers=Depends(decode_headers)
):
    sub_query = headers["sub_query"]
    content = {}
    async for language in languages_collection.find({}):
        language["_id"] = str(language["_id"])
        data = await language_search(language['name'], sub_query)
        content[language['name']] = data["data"]
    return {"success": True, "content": content}


@router.get("/genres")
async def get_content_by_genre(
    headers=Depends(decode_headers)
):
    sub_query = headers["sub_query"]
    content = {}
    async for genre in genres_collection.find({}):
        movies, series = [], []
        genre["_id"] = str(genre["_id"])
        movies = await get_movies_by_genre(genre['name'], sub_query)
        series = await get_series_by_genre(genre['name'], sub_query)
        content[genre['name']] = movies + series
    return {"success": True, "content": content}


@router.get("")
async def search(
    filter: Optional[str] = None,
    q: Optional[str] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    headers=Depends(decode_headers)
):
    child = headers['child']
    sub_query = headers['sub_query']
    if not (filter or q or genre or language):
        raise HTTPException(status_code=400, detail="Bad request")

    if language:
        result = await language_search(language, sub_query)
        return result

    if child and filter:
        filter = f"{filter}-kids"

    if filter in ["home", "home-kids", "movies", "movies-kids", "series", "series-kids", "songs", "songs-kids"]:
        playlist_content, playlist_order = await get_all_playlist_content(filter)

        return {'playlists': playlist_content, 'order': playlist_order}
    else:
        if genre:
            movies = await get_movies_by_genre(genre, sub_query)
            series = await get_series_by_genre(genre, sub_query)
            return {'results': movies + series}

        regx = Regex(q, re.IGNORECASE)
        query = {
            '$and': [
                sub_query,
                {
                    '$or': [
                        {'title': regx},
                        {'actors': regx},
                        {'directors': regx},
                        {'producers': regx},
                        {'genre': regx}
                    ],
                    'availability': {'$in': ['perpetual', 'restricted']}}
            ]
        }
        movies = []
        series = []
        songs = []
        async for movie in movies_collection.find(query).limit(10):
            movie['_id'] = str(movie['_id'])
            movie['slugUrl'] = f"movies/{movie.get('slug','movie')}-{movie['_id']}"
            movie['type'] = 'movie'
            if movie.get("availability") == "restricted":
                start = datetime.fromisoformat(
                    movie["startDate"]).strftime(date_time_format)
                end = datetime.fromisoformat(
                    movie.get("endDate")).strftime(date_time_format)
                now = datetime.now().isoformat(timespec="seconds")
                if now > start or now < end:
                    movies.append(movie)
            else:
                movies.append(movie)

        async for doc in series_collection.find(query).limit(10):
            doc['_id'] = str(doc['_id'])
            doc['slugUrl'] = f"series/{doc.get('slug','series')}-{doc['_id']}"
            doc['type'] = 'series'
            if doc.get("availability") == "restricted":
                start = datetime.fromisoformat(
                    doc["startDate"]).strftime(date_time_format)
                end = datetime.fromisoformat(
                    doc.get("endDate")).strftime(date_time_format)
                now = datetime.now().isoformat(timespec="seconds")
                if now > start or now < end:
                    series.append(doc)
            else:
                series.append(doc)
        async for song in songs_collection.find(query):
            song["_id"] = str(song["_id"])
            song["type"] = "song"
            songs.append(song)

        return {'results': movies + series + songs}


async def get_movies_by_genre(genre: str, sub_query: dict):
    movies = []
    query = {
        '$and': [
            sub_query,
            {
                'genre': genre,
                'availability': {'$in': ['perpetual']}
            }
        ]
    }
    async for movie in movies_collection.find(query).limit(20):
        movie['_id'] = str(movie['_id'])
        movie['slugUrl'] = f"movies/{movie.get('slug','movie')}-{movie['_id']}"
        movie['type'] = 'movie'
        movies.append(movie)
    return movies


async def get_series_by_genre(genre: str, sub_query: dict):
    series = []
    query = {
        '$and': [
            sub_query,
            {
                'genre': genre,
                'availability': {'$in': ['perpetual']}
            }
        ]
    }
    async for s in series_collection.find(query).limit(20):
        s['_id'] = str(s['_id'])
        s['slugUrl'] = f"series/{s.get('slug','series')}-{s['_id']}"
        s['type'] = 'series'
        series.append(s)

    return series


async def populate_content(content_type, content_id, content_list):
    if content_type == 'movie':
        movie = await movies_collection.find_one({'_id': ObjectId(content_id)})
        movie['_id'] = str(movie['_id'])
        movie['slugUrl'] = f"movies/{movie.get('slug','movie')}-{movie['_id']}"
        movie['type'] = 'movie'
        content_list.append(movie)
    if content_type == 'series':
        series = await series_collection.find_one({'_id': ObjectId(content_id)})
        series['_id'] = str(series['_id'])
        series['slugUrl'] = f"series/{series.get('slug','series')}-{series['_id']}"
        series['type'] = 'series'
        content_list.append(series)
    if content_type == 'song':
        song = await songs_collection.find_one({'_id': ObjectId(content_id)})  # noqa: E501
        song['_id'] = str(song['_id'])
        song['slugUrl'] = f"songs/{song.get('slug', 'song')}-{song['_id']}"
        song['type'] = 'song'
        content_list.append(song)

    return content_list


async def get_default_playlist(playlist, playlist_content, playlist_order: list, filter):
    content_list = []
    playlist["content"] = playlist["content"][::-1]
    try:
        if filter in ['home', 'home-kids']:
            for content in playlist['content']:
                content_type, content_id = content.split('|')
                content_list = await populate_content(content_type, content_id, content_list)

        elif filter in ['movies', 'movies-kids']:
            for content in playlist['content']:
                content_list = await populate_content('movie', content, content_list)

        elif filter in ['songs', 'songs-kids']:
            for content in playlist['content']:
                content_list = await populate_content('song', content, content_list)

        elif filter in ['series', 'series-kids']:
            for content in playlist['content']:
                content_list = await populate_content('series', content, content_list)

        playlist_content[playlist['name']] = content_list
        playlist_order.append(playlist['name'])

    except Exception:
        pass

    return playlist_content, playlist_order
