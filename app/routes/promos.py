from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, HTTPException, Security, BackgroundTasks, Depends  # noqa: E501

from .utils import get_current_employee, remove_object, decode_headers
from ..models.promo import Promo

db = Mongo()
promos_collection = db.promos
movies_collections = db.movies
series_collections = db.series
songs_collections = db.songs
webseries_collection = db.webseries


router = APIRouter()


async def fetch_slug_data(promos):
    proj = {
        'slug': 1,
        'title': 1,
        'hindiTitle': 1,
        'description': 1,
        'hindiDescription': 1,
        'year': 1,
        'genre': 1,
        'language': 1,
        'maturity': 1
    }
    query = {'_id': {'$in': [ObjectId(i) for i in promos.keys()]}}
    async for movie in movies_collections.find(query, proj):
        _id = str(movie.pop('_id'))
        movie['slugUrl'] = f"movies/{movie.get('slug','movie')}-{_id}"
        promos[_id].update(movie)
    async for series in series_collections.find(query, proj):
        _id = str(series.pop('_id'))
        series['slugUrl'] = f"series/{series.get('slug','series')}-{_id}"
        promos[_id].update(series)
    async for song in songs_collections.find(query, proj):
        _id = str(song.pop('_id'))
        promos[_id].update(song)
    async for webseries in webseries_collection.find(query, proj):
        _id = str(webseries.pop('_id'))
        promos[_id].update(webseries)


@router.get("")
async def get_promos(filter: str, headers=Depends(decode_headers)):
    accept = ["home", "movies", "series", "songs", "home-kids",
              "movies-kids", "series-kids", "songs-kids", "webseries"]
    lookup = {'movies': 'movie', 'series': 'series', 'songs': 'song',
              'movies-kids': 'movie', 'series-kids': 'series', 'songs-kids': 'song'}
    if filter not in accept:
        raise HTTPException(status_code=400, detail="Bad request")

    if headers['child'] and 'kids' not in filter:
        filter = f"{filter}-kids"
    promos = dict()
    async for promo in promos_collection.find({'page': filter}).limit(10):
        promo['_id'] = str(promo["_id"])
        promos = await get_all_promos(promos, promo, lookup, filter)

    promos = sorted(promos.values(), key=lambda x: x.get('position'))
    return {"promos": promos}


@router.patch("")
async def update_promos(
    promo: Promo,
    token: str = Security(get_current_employee, scopes=["Banners:create"])
):
    result = await promo.save()
    return {"success": result}


@router.put("/{id}")
async def update_promo(
    promo: Promo,
    id: str,
    token: str = Security(get_current_employee, scopes=["Banners:update"])
):
    success = await promo.save(id)
    return {"success": success}


@router.delete("/{id}")
async def delete_promo(
    id: str,
    tasks: BackgroundTasks,
    token: str = Security(get_current_employee, scopes=["Banners:delete"])
):
    promo = await promos_collection.find_one({'_id': ObjectId(id)})
    tasks.add_task(remove_object, promo['bannerImage'])
    await promos_collection.delete_one({'_id': ObjectId(id)})
    return {'success': True}


async def get_song_model(promo):
    song = await songs_collections.find_one({'_id': ObjectId(promo['song'])})
    key_name = promo.get('promoType', 'song')
    if song:
        promo['model'] = song['model']
        promo['cardImage'] = song.get("cardImage")

    return promo, key_name


async def get_all_promos(promos, promo, lookup, filter):
    if 'home' in filter:
        key_name = promo.get('promoType')
        if key_name == 'static':
            promos[promo['_id']] = {**promo, 'slug': 'coming-soon'}

        if key_name == 'song':
            promo, _ = await get_song_model(promo)
    elif filter == 'songs' or filter == 'songs-kids':
        promo, key_name = await get_song_model(promo)
    else:
        key_name = lookup.get(filter)
    _id = promo.get(key_name)
    if _id:
        promos[_id] = promo
    await fetch_slug_data(promos)

    return promos
