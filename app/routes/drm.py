import os
import jwt

from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from datetime import datetime

db = Mongo()
users_collection = db.users
movies_collection = db.movies
series_collection = db.series
songs_collection = db.songs

router = APIRouter()
key = os.environ.get("JWT_SECRET_KEY")

play_response_true = "play=true"


@router.get("", response_class=PlainTextResponse)
async def get_license(token: str, type: str, id: str, profile_token: str = None):
    decoded = jwt.decode(token, key, algorithms=["HS256"])
    user = await users_collection.find_one({'_id': ObjectId(decoded['id'])})
    content = await get_content(id, type)

    if profile_token:
        decoded_profile = jwt.decode(profile_token, key, algorithms=["HS256"])
        is_child = decoded_profile.get("isChild", False)
        if is_child and content["maturity"] != "U":
            return "play=false"

    if content['model'] == 'free':
        return play_response_true
    elif content['model'] == 'ticket':
        if content['subscriberPrice']['INR'] == 0 and user['activeSubscription']:
            return play_response_true
        else:
            response = get_active_tickets(user.get('tickets', []), id)
            return response
    elif content['model'] == 'subscription' and user['activeSubscription'] and content['availability'] == 'perpetual':  # noqa: E501
        return play_response_true
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/apple", response_class=PlainTextResponse)
async def get_license(customdata: str):
    profile_token = None
    try:
        [id, type, token, profile_token] = customdata.split("::")
    except Exception:
        [id, type, token] = customdata.split("::")
    decoded = jwt.decode(token, key, algorithms=["HS256"])
    user = await users_collection.find_one({'_id': ObjectId(decoded['id'])})
    content = await get_content(id, type)
    if profile_token:
        decoded_profile = jwt.decode(profile_token, key, algorithms=["HS256"])
        is_child = decoded_profile.get("isChild", False)
        if is_child and content["maturity"] != "U":
            return "play=false"

    if content['model'] == 'free':
        return play_response_true
    elif content['model'] == 'ticket':
        response = get_active_tickets(user.get('tickets', []), id)
        return response
    elif content['model'] == 'subscription' and user['activeSubscription'] and content['availability'] == 'perpetual':  # noqa: E501
        return play_response_true
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


def get_active_tickets(tickets, content_id):
    ticket = [t for t in tickets if t["id"] == content_id][-1]
    end_time = datetime.strptime(ticket['end'], '%Y-%m-%dT%H:%M:%S')  # noqa: E501
    if datetime.now() < end_time:
        return play_response_true
    return HTTPException(status_code=403, detail="Forbidden")


async def get_content(id, type):
    if type == "movie":
        content = await movies_collection.find_one({'_id': ObjectId(id)})
    elif type == "series":
        content = await series_collection.find_one({'_id': ObjectId(id)})
    elif type == "song":
        content = await songs_collection.find_one({'_id': ObjectId(id)})
    else:
        raise HTTPException(status_code=400, detail="Bad request")

    date_time_format = "%Y-%m-%dT%H:%M:%S"
    if content.get("availability") == "restricted":
        start = datetime.fromisoformat(
            content["startDate"]).strftime(date_time_format)
        end = datetime.fromisoformat(
            content["endDate"]).strftime(date_time_format)
        now = datetime.now().isoformat(timespec="seconds")
        if now < start or now > end:
            raise HTTPException(status_code=403, detail="Content Restricted")

    return content
