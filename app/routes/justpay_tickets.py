import os
import base64
import asyncio
import random
from datetime import datetime, timedelta, date
from math import trunc
from time import time

from aiohttp import ClientSession
from pytz import timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Security, Request
from bson.objectid import ObjectId
from app.db import Mongo
from .utils import decode_headers, decode_token, make_api_request
from ..config import AppConfig
from ..models.justpay import JustpayTicket, get_customer_id

router = APIRouter()

db = Mongo()
users_collection = db.users
movies_collection = db.movies
series_collection = db.series
tickets_collection = db.tickets

config = AppConfig()

# Juspay Configuration
BASE_URL = config.justpay_api_url
api_key = config.justpay_api_key
encoded_key = base64.b64encode(f"{api_key}:".encode()).decode()
AUTHORIZATION = f"Basic {encoded_key}"
justpay_client_id = config.justpay_client_id

@router.post("")
async def create_justpay_ticket(
    ticket: JustpayTicket,
    token=Depends(decode_token),
    headers=Depends(decode_headers)
):
    currency = headers.get('currency')
    if ticket.content_type == 'movie':
        video = await movies_collection.find_one({'_id': ObjectId(ticket.content_id)})
        metadata = {'content_id': ticket.content_id, 'type': 'movie'}
    else:
        video = await series_collection.find_one({'_id': ObjectId(ticket.content_id)})
        metadata = {'content_id': ticket.content_id, 'type': 'series'}
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})

    if video and video["model"] == "ticket" and user:
        result = await generate_justpay_ticket(metadata, video, user, currency, token, ticket)
        return result
    else:
        raise HTTPException(status_code=403, detail="Forbidden")




async def generate_justpay_ticket(metadata, video, user, currency, token, ticket):
    metadata['name'] = video['title']
    metadata['currency'] = currency
    if video['model'] != 'ticket' or currency != 'INR':
        raise HTTPException(status_code=400, detail="Bad request")

    if 'activeSubscription' in user:
        subscriber_price = video['subscriberPrice']
        amount = subscriber_price.get(currency) if isinstance(
            subscriber_price, dict) else subscriber_price
    else:
        non_subscriber_price = video['nonSubscriberPrice']
        amount = non_subscriber_price.get(currency) if isinstance(
            non_subscriber_price, dict) else non_subscriber_price
    customer_id = await get_customer_id(user)
    result = {
        'amount': amount,
        'user_id': token["id"],
        'customer_id': customer_id
    }
    res = await create_justpay_order(result)
    if res['status'] != "CREATED":
        return {**result, 'message': 'Justpay initTransaction failed'}

    result = {**result, **res}

    ticket_id = result.pop('order_id')
    await tickets_collection.insert_one({
        '_id': ticket_id,
        'amount': amount,
        'user': ObjectId(token['id']),
        'streamPeriod': video['streamPeriod'],
        'paid': False,
        'date': str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')),
        'pg': 'justpay',
        **metadata,
        **result,
    })
    return {
        "success": True,
        "id": ticket_id,
        **result,
        **res
    }


async def create_justpay_order(data):

    order_id = f"jp-ticket-{ObjectId()}"
    payload = {
        "order_id": order_id,
        "amount": str(float(data["amount"])),
        "customer_id": data["customer_id"],
        "customer_email": data.get("email"),
        "customer_phone": data.get("mobile"),
        "payment_page_client_id": justpay_client_id,
        "return_url": "https://minipix.in"
    }
    res = await make_api_request(method = "POST", url = f"{BASE_URL}/orders", payload = payload,
                                 headers = {"Authorization": AUTHORIZATION})

    return res