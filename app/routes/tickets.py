from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from pytz import timezone
from fastapi import APIRouter, HTTPException, Depends, Security, BackgroundTasks  # noqa: E501

from .utils import decode_headers, decode_token, rzrpy_client, get_current_employee  # noqa: E501
from ..routes.paytm_orders import capture_paytm_order
from ..models.ticket import Ticket, CaptureTicket
from ..models.tracking_params import OrderTrackingParams
from ..models.order import CaptureOrder
from ..models.emails import Messages
from ..models.sms import SMSMessage

db = Mongo()
users_collection = db.users
movies_collection = db.movies
series_collection = db.series
tickets_collection = db.tickets

router = APIRouter()


@router.get("")
async def get_tickets(
    current: int = 1,
    size: int = 10,
    content_id: str = None,
    start_date: str = None,
    end_date: str = None,
    paid: bool = False,
    currency: str = None,
    token=Security(get_current_employee, scopes=["Orders:read"])
):
    tickets = []
    query = {}
    if start_date and end_date:
        query['date'] = {"$gte": datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S").isoformat(),
                         "$lte": datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").isoformat()}
    if content_id:
        query['content_id'] = content_id

    query['paid'] = paid

    if currency:
        query['currency'] = currency

    total = await tickets_collection.count_documents(query)
    async for ticket in tickets_collection.find(query).sort('date', -1).skip((current - 1) * 10).limit(size):  # noqa: E501
        ticket['_id'] = str(ticket['_id'])
        user = await users_collection.find_one({'_id': ticket['user']})
        user_str = ''
        if user and 'email' in user:
            user_str += f'Email: {user["email"]}\n'
        if user and 'mobile' in user:
            user_str += f'Mobile: {user["mobile"]}'

        expires_in = datetime.strptime(
            ticket['date'], '%Y-%m-%dT%H:%M:%S%z') + timedelta(days=int(ticket.get('streamPeriod')))
        end_time = expires_in
        now = datetime.now(timezone("Asia/Kolkata"))
        if now < end_time and ticket.get('paid', False):
            ticket['expiresInHrs'] = (end_time - now) / 3600

        ticket['user'] = user_str
        tickets.append(ticket)
    return {"tickets": tickets, "total": total, 'movies': []}


@router.get("/{id}")
async def get_ticket_details(
    id: str,
    token=Security(get_current_employee, scopes=["Orders:read"])
):
    ticket = await tickets_collection.find_one({'_id': id})

    if ticket:
        ticket['_id'] = str(ticket['_id'])
        user = await users_collection.find_one({'_id': ticket['user']})
        user_str = ''
        if user and 'email' in user:
            user_str += f'Email: {user["email"]}\n'
        if user and 'mobile' in user:
            user_str += f'Mobile: {user["mobile"]}'
        ticket['user'] = user_str

        if ticket['paid']:
            return ticket

        payments = rzrpy_client.order.payments(id)
        for payment in payments['items']:
            if payment['status'] == 'captured':
                ticket['paid'] = True

                end_time = datetime.now() + \
                    timedelta(days=int(ticket['streamPeriod']))
                user_ticket = {
                    'name': ticket['name'],
                    'start': datetime.now().isoformat(timespec='seconds'),
                    'end': end_time.isoformat(timespec='seconds'),
                    'id': ticket['content_id'],
                    'type': ticket['type']
                }

                await users_collection.update_one(
                    {'_id': ticket['user']},
                    {'$push': {'tickets': user_ticket}}
                )
                await tickets_collection.update_one(
                    {'_id': id},
                    {"$set": {"paid": True}}
                )

                break

        return ticket
    else:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("")
async def create_ticket(
    ticket: Ticket,
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
            {'_id': ObjectId(token['id'])},
            {'$push': {'tickets': user_ticket}}
        )
        send_ticket_alert(user, user_ticket, tasks)
        return {"success": True, "ticket": {**ticket, "paid": True}}


async def generate_ticket(metadata, video, user, currency, token, ticket):
    metadata['name'] = video['title']
    metadata['currency'] = currency
    if video['model'] != 'ticket':
        raise HTTPException(status_code=400, detail="Bad request")

    if 'activeSubscription' in user:
        subscriber_price = video['subscriberPrice']
        amount = subscriber_price.get(currency) if isinstance(
            subscriber_price, dict) else subscriber_price
    else:
        non_subscriber_price = video['nonSubscriberPrice']
        amount = non_subscriber_price.get(currency) if isinstance(
            non_subscriber_price, dict) else non_subscriber_price

    ticket_obj = rzrpy_client.order.create(data={
        "amount": amount * 100,
        "currency": currency,
        "notes": {
            "user_id": token["id"]
        }
    })
    await tickets_collection.insert_one({
        '_id': ticket_obj['id'],
        'amount': amount,
        'user': ObjectId(token['id']),
        'streamPeriod': video['streamPeriod'],
        'paid': False,
        'date': str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')),
        **metadata,
        **OrderTrackingParams.parse_params(ticket.tracking)
    })
    return {"success": True, "id": ticket_obj['id'], "amount": amount}


def send_ticket_alert(user, user_ticket, tasks: BackgroundTasks):
    if user.get('email'):
        subject, body = Messages.on_successful_ticket_purchase(
            user, user_ticket)
        tasks.add_task(Messages.send_email,
                       user['email'], subject, body)
    if user.get('mobile'):
        body = SMSMessage.on_successful_ticket_purchase(user_ticket)
        tasks.add_task(SMSMessage.send_sms, user["mobile"], body)
