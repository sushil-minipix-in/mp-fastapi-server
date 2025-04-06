from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime
from fastapi import APIRouter, HTTPException, Security, Depends, Request, BackgroundTasks

from .utils import decode_headers, get_current_employee, get_similar_query, send_update, get_history
from .utils import decode_token, pop_random, insert_share_link, construct_social_preview_image
from .utils import verify_update_content
from ..models.series import SeriesAddModel
from ..models.episode import EpisodeAddModel

db = Mongo()
series_collection = db.series
playlists_collection = db.playlists
promos_collection = db.promos

router = APIRouter()


@router.get("/{id}")
async def get_series(
    id: str,
    request: Request,
    headers: dict = Depends(decode_headers)
):
    if ObjectId.is_valid(id) is False:
        raise HTTPException(status_code=422, detail="Invalid id")

    token = request.headers.get('authorization', False)
    admin = False
    if token:
        token = decode_token(token.split(" ")[1])
        admin = (token.get('admin', False) or token.get('superadmin', False))

    currency = headers.get('currency')
    sub_query = headers.get('sub_query', {})
    query = {'_id': ObjectId(id)}
    if admin is False:
        query['availability'] = {'$ne': 'unpublished'}
    series = await series_collection.find_one(query)
    if series:
        series['_id'] = str(series['_id'])
        if headers.get('child') is True and series['maturity'] != "U":
            raise HTTPException(status_code=412, detail='Content restricted')
        if admin is False:
            series = await populate_series_data(series, sub_query, currency, headers, token)
            return series
        else:
            return series

    else:
        raise HTTPException(status_code=404, detail='Not found')


@router.get("/{id}/episodes")
async def get_episodes(id: str, request: Request):
    token = request.headers.get('authorization', False)
    admin = False
    if token:
        token = decode_token(token.split(" ")[1])
        admin = (token.get('admin', False) or token.get('superadmin', False))

    series = await series_collection.find_one({'_id': ObjectId(id)})
    if series:
        return get_all_episodes(series, admin)
    else:
        raise HTTPException(status_code=404, detail='Not found')


@router.get("")
async def get_all_series(
    token=Security(get_current_employee, scopes=["Series:read"])
):
    series = []
    query = {}
    if token['partner']:
        query = {"partner": token["id"]}
    async for content in series_collection.find(query).sort('title'):
        content["_id"] = str(content["_id"])
        series.append(content)
    return {"series": series}


@router.post("")
async def create_series(
    series: SeriesAddModel,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Series:create"])
):
    result = await series.save(token)
    if result:
        bg.add_task(insert_share_link, result, 'series')
    bg.add_task(send_update,  series.title,
                'series', 'created', token['email'])
    return {"success": True}


@router.post("/{id}/episodes")
async def create_episode(
    id: str,
    episode: EpisodeAddModel,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Series:create"])
):
    try:
        await episode.save(id)
    except Exception as e:
        if str(e) in ["Series not found", "Episode already exists"]:
            return {"success": False, "message": str(e)}
        else:
            raise HTTPException(status_code=500, detail='Internal Server Error')
    bg.add_task(send_update,  episode.name,
                'episode', 'created', token['email'])
    return {"success": True}


@router.put("/{id}")
async def update_series(
    id: str,
    series: SeriesAddModel,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Series:update"])
):
    if series.availability == "unpublished":
        await verify_update_content(id, "series")
    await series.save(token, id)
    bg.add_task(send_update,  series.title,
                'series', 'updated', token['email'], series.availability)
    return {"success": True}


@router.delete("/{id}")
async def delete_series(
    id: str,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Series:delete"])
):
    await verify_update_content(id, "series")
    series = await series_collection.find_one({"_id": ObjectId(id)})
    await series_collection.delete_one({'_id': ObjectId(id)})
    bg.add_task(send_update,  series["title"],
                'series', 'deleted', token['email'])
    return {'success': True}


@router.delete("/{id}/episodes")
async def delete_episode(
    id: str,
    season: int,
    number: int,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Series:delete"])
):
    series = await series_collection.find_one({"_id": ObjectId(id)})
    await series_collection.update_one({'_id': ObjectId(id)}, {'$pull': {'episodes': {'season': season, 'number': number}}})  # noqa: E501
    bg.add_task(send_update,  series['title'],
                f'episode {number} from season {season}', 'deleted', token['email'])
    return {'success': True}


async def populate_series_data(series, sub_query, currency, headers, token):
    query = get_similar_query(series, sub_query)
    similar = await get_similar_series(query)
    series["social_preview_image"] = construct_social_preview_image(
        series.get("trailerImage", ""))
    if "profile_id" in headers:
        series["watchHistory"] = await get_history(token, headers["profile_id"], str(series["_id"]), "series")

    if series['availability'] == 'restricted':
        end = series.get('endDate', None)
        start_aware = datetime.fromisoformat(series['startDate'])
        now = datetime.now(start_aware.tzinfo)
        end = datetime.fromisoformat(end) < now if end else False
        if now < start_aware or end:
            for episode in series.get('episodes', []):
                episode.pop('playbackUrl', 0)
                episode.pop('iosPlaybackUrl', 0)

    if series['model'] == 'ticket':
        subscriber_price = series.get('subscriberPrice')
        non_subscriber_price = series.get('nonSubscriberPrice')
        if isinstance(subscriber_price, dict):
            subscriber_price = subscriber_price.get(currency)
        if isinstance(non_subscriber_price, dict):
            non_subscriber_price = non_subscriber_price.get(currency)
        series['subscriberPrice'] = subscriber_price
        series['nonSubscriberPrice'] = non_subscriber_price
        series['currency'] = currency
        series['currency_symbol'] = headers.get('currency_symbol')

    series['similarSeries'] = similar
    series['_id'] = str(series['_id'])
    series['slugUrl'] = f"series/{series.get('slug','series')}-{series['_id']}"
    return series


async def get_similar_series(query):
    series, similar = [], []
    async for doc in series_collection.find(query).limit(25):
        doc['_id'] = str(doc['_id'])
        doc['slugUrl'] = f"series/{doc.get('slug','series')}-{doc['_id']}"
        series.append(doc)

    if len(series) < 5:
        return series

    similar = [pop_random(series) for _ in range(5)]

    return similar


def get_all_episodes(series, admin):

    if series['availability'] == 'restricted' and admin is False:
        end = series.get('endDate', None)
        start_aware = datetime.fromisoformat(series['startDate'])
        now = datetime.now(start_aware.tzinfo)
        end = datetime.fromisoformat(end) < now if end else False
        if now < start_aware or end:
            for episode in series.get('episodes', []):
                episode.pop('playbackUrl', 0)
                episode.pop('iosPlaybackUrl', 0)

    return {"episodes": series.get('episodes', [])}
