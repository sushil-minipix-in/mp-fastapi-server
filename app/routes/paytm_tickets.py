from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from pytz import timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from .utils import decode_headers, decode_token, decode_admin_token
from .paytm_orders import create_paytm_order, capture_paytm_order
from ..models.paytm import PaytmTicket
from ..models.tracking_params import OrderTrackingParams
from ..models.emails import Messages
from ..models.sms import SMSMessage
from ..routes.tickets import send_ticket_alert

db = Mongo()
users_collection = db.users
movies_collection = db.movies
series_collection = db.series
tickets_collection = db.tickets

router = APIRouter()


@router.post("")
async def create_ticket(
    ticket: PaytmTicket,
    token=Depends(decode_token),
    headers=Depends(decode_headers)
):
    currency = headers.get('currency')
    if ticket.type == 'movie':
        video = await movies_collection.find_one({'_id': ObjectId(ticket.id)})
        metadata = {'content_id': ticket.id, 'type': 'movie'}
    else:
        video = await series_collection.find_one({'_id': ObjectId(ticket.id)})
        metadata = {'content_id': ticket.id, 'type': 'series'}
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})

    if video and user:
        result = await generate_ticket(metadata, video, user, currency, token, ticket)
        return result
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/{ticket_id}")
async def get_ticket_details(
    ticket_id: str,
    tasks: BackgroundTasks,
    token=Depends(decode_admin_token)
):
    ticket = await tickets_collection.find_one({'_id': ticket_id})
    user = None
    if ticket:
        user = await users_collection.find_one({"_id": ticket["user"]})
    if not ticket or not user:
        raise HTTPException(400, "Bad Inputs")
    ticket["user"] = str(ticket["user"])
    result = await capture_paytm_order(ticket_id)
    await tickets_collection.update_one(
        {'_id': ticket['_id']},
        {'$set': {'paid': result['success'], **result}}
    )
    if result['success'] is True:
        end_time = datetime.now() + \
            timedelta(days=int(ticket['streamPeriod']))
        user_ticket = {
            'name': ticket.get('name', '-'),
            'start': datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds'),
            'end': end_time.isoformat(timespec='seconds'),
            'type': ticket['type'],
            'id': ticket['content_id'],
            'order_id': ticket_id,
            'amount': ticket['amount'],
            'currency': 'INR'
        }

        await users_collection.update_one(
            {'_id': ticket["user"]},
            {'$push': {'tickets': user_ticket}}
        )
        send_ticket_alert(user, user_ticket, tasks)
        return {"success": True, "ticket": {**ticket, "paid": True}}
    else:
        return result


@router.post("/{ticket_id}/charge")
async def capture_ticket(
    ticket_id: str,
    tasks: BackgroundTasks,
    token=Depends(decode_token)
):
    ticket = await tickets_collection.find_one({'_id': ticket_id})
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    if not ticket or not user:
        raise HTTPException(status_code=400, detail="Bad Inputs")
    ticket["user"] = str(ticket["_id"])
    result = await capture_paytm_order(ticket_id)
    await tickets_collection.update_one(
        {'_id': ticket['_id']},
        {'$set': {'paid': result['success'], **result}}
    )
    if result['success']:
        end_time = datetime.now() + \
            timedelta(days=int(ticket['streamPeriod']))
        user_ticket = {
            'name': ticket.get('name', '-'),
            'start': datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds'),
            'end': end_time.isoformat(timespec='seconds'),
            'type': ticket['type'],
            'id': ticket['content_id'],
            'order_id': ticket_id,
            'amount': ticket['amount'],
            'currency': 'INR'
        }

        await users_collection.update_one(
            {'_id': user["_id"]},
            {'$push': {'tickets': user_ticket}}
        )
        send_ticket_alert(user, user_ticket, tasks)
        return {"success": True, "ticket": {**ticket, "paid": True}}


async def generate_ticket(metadata, video, user, currency, token, ticket):
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

    result = {
        'amount': amount,
        'user_id': token["id"],
        'channelId': ticket.channelId
    }
    await create_paytm_order(result)
    if result['success'] is not True:
        return {**result, 'message': 'Paytm initTransaction failed'}

    ticket_id = result.pop('id')
    await tickets_collection.insert_one({
        '_id': ticket_id,
        'amount': amount,
        'user': ObjectId(token['id']),
        'streamPeriod': video['streamPeriod'],
        'paid': False,
        'date': str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')),
        'pg': 'paytm',
        **metadata,
        **result,
        **OrderTrackingParams.parse_params(ticket.tracking)
    })
    return {
        "success": True,
        "id": ticket_id,
        **result
    }
