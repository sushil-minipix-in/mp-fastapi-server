from app.db import Mongo
from fastapi import APIRouter, HTTPException, BackgroundTasks, Security, Depends, Request  # noqa: E501
from bson.objectid import ObjectId
from datetime import datetime

from .utils import decode_token, remove_object, get_current_employee
from .utils import send_update, decode_headers, get_similar_query, construct_social_preview_image
from .utils import pop_random, insert_share_link, verify_update_content, get_history
from ..models.movie import MovieAddModel

db = Mongo()
movies_collection = db.movies
playlists_collection = db.playlists
promos_collection = db.promos

router = APIRouter()


@router.get("/{id}")
async def get_movie(
    id: str,
    request: Request,
    headers: dict = Depends(decode_headers)
):
    if ObjectId.is_valid(id) is False:
        raise HTTPException(status_code=422, detail="Invalid id")

    currency = headers['currency']
    sub_query = headers.get('sub_query', {})
    query = {'_id': ObjectId(id)}
    token = request.headers.get('authorization', False)
    admin = False
    if token:
        token = decode_token(token.split(" ")[1])
        admin = (token.get('admin', False) or token.get('superadmin', False))
    if admin is False:
        query['availability'] = {'$ne': 'unpublished'}
    movie = await movies_collection.find_one(query)
    if movie:
        movie['_id'] = str(movie['_id'])
        if headers.get('child') is True and movie['maturity'] != "U":
            raise HTTPException(status_code=412, detail='Content restricted')
        if admin is False:
            movie = await populate_movie_data(movie, sub_query, currency, headers, token)
            return movie
        elif admin:
            return movie
    else:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("")
async def get_movies(
    token=Security(get_current_employee, scopes=["Movies:read"])
):
    movies = []
    query = {}
    if token['partner']:
        query = {"partner": token["id"]}
    async for mov in movies_collection.find(query).sort('title'):
        mov["_id"] = str(mov["_id"])
        movies.append(mov)

    return {"movies": movies}


@router.post("")
async def create_movie(
    movie: MovieAddModel,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Movies:create"]),
):
    result = await movie.save(token)
    if result:
        bg.add_task(insert_share_link, result, 'movies')
    bg.add_task(send_update, movie.title, 'movie', 'created',  token['email'])
    return {"success": True}


@router.put("/{id}")
async def update_movie(
    id: str,
    movie: MovieAddModel,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Movies:update"])
):
    if movie.availability == "unpublished":
        await verify_update_content(id, "movie")
    await movie.save(token, id)
    bg.add_task(send_update, movie.title, 'movie', 'updated',
                token['email'], movie.availability)
    return {"success": True}


@router.delete("/{id}")
async def delete_movie(
    id: str,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Movies:delete"])
):
    await verify_update_content(id, "movie")
    movie = await movies_collection.find_one({'_id': ObjectId(id)})
    await movies_collection.delete_one({'_id': ObjectId(id)})
    tasks.add_task(send_update, movie['title'], 'movie', 'deleted', token['email'])  # noqa: E501
    if "cardImage" in movie:
        tasks.add_task(remove_object, movie['cardImage'])
    if "detailImage" in movie:
        tasks.add_task(remove_object, movie['detailImage'])
    if 'playbackUrl' in movie:
        tasks.add_task(remove_object, movie['playbackUrl'])
    return {'success': True}


async def populate_movie_data(movie, sub_query, currency, headers, token):
    query = get_similar_query(movie, sub_query)
    similar = await get_similar_movies(query)
    movie["social_preview_image"] = construct_social_preview_image(
        movie.get("trailerImage", ""))
    if 'profile_id' in headers:
        movie["watchHistory"] = await get_history(token, headers["profile_id"], str(movie["_id"]), "movie")

    if movie['availability'] == 'restricted':
        end = movie.get('endDate', None)
        start_aware = datetime.fromisoformat(movie['startDate'])
        now = datetime.now(start_aware.tzinfo)
        end = datetime.fromisoformat(end) < now if end else False
        if now < start_aware or end:
            movie.pop('playbackUrl', 0)
            movie.pop('iosPlaybackUrl', 0)

    if movie['model'] == 'ticket':
        subscriber_price, non_subscriber_price = get_movie_prices(movie, currency)  # noqa: E501

        movie['subscriberPrice'] = subscriber_price
        movie['nonSubscriberPrice'] = non_subscriber_price
        movie['currency'] = currency
        movie['currency_symbol'] = headers.get('currency_symbol', currency)

    movie['similarMovies'] = similar
    movie['_id'] = str(movie['_id'])
    movie['slugUrl'] = f"movies/{movie.get('slug','movie')}-{movie['_id']}"
    return movie


def get_movie_prices(movie, currency):
    subscriber_price = movie.get('subscriberPrice')
    non_subscriber_price = movie.get('nonSubscriberPrice')
    if isinstance(subscriber_price, dict):
        subscriber_price = subscriber_price.get(currency)
    if isinstance(non_subscriber_price, dict):
        non_subscriber_price = non_subscriber_price.get(currency)

    return subscriber_price, non_subscriber_price


async def get_similar_movies(query):
    movies, similar = [], []
    async for mov in movies_collection.find(query).limit(25):
        mov['_id'] = str(mov['_id'])
        mov['slugUrl'] = f"movies/{mov.get('slug','movie')}-{mov['_id']}"
        movies.append(mov)

    if len(movies) < 5:
        return movies

    similar = [pop_random(movies) for _ in range(5)]

    return similar
