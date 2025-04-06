from app.db import Mongo
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from bson import ObjectId

from datetime import datetime
from pytz import timezone

from .utils import decode_token, decode_headers, rzrpy_client
from ..models.order import Order, CaptureOrder
from ..models.tracking_params import OrderTrackingParams

router = APIRouter()

db = Mongo()
orders_collection = db.orders
users_collection = db.users
mandates_collection = db.mandates


@router.post("")
async def create_subscription(
    order: Order,
    token=Depends(decode_token),
    header=Depends(decode_headers)
):
    currency = header.get('currency')
    result = await order.create_subscription(rzrpy_client, currency, token['id'])
    print(result)
    if not result['success']:
        raise HTTPException(status_code=500, detail="Internal Server Error")

    await mandates_collection.insert_one({
        "subscription_id": result["id"],
        **result,
        "trial": True,
        "status": "CREATED",
        "duration": result["duration"],
        "order_id": result["order_id"]
    })

    await orders_collection.insert_one({
        '_id': result['id'],
        'subscription': True,
        'user': ObjectId(token['id']),
        'user_id': token['id'],
        'paid': False,
        'date': datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds'),
        **result,
        **OrderTrackingParams.parse_params(order.tracking)
    })
    return {'success': True, **result}


@router.post("/{subscription_id}/charge")
async def capture_subscription(
    subscription_id: str,
    capture: CaptureOrder,
    tasks: BackgroundTasks,
    token=Depends(decode_token)
):
    subscription = await orders_collection.find_one({'_id': subscription_id})
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    if not subscription or not user:
        raise HTTPException(status_code=400, detail="Bad request")

    result = await capture.verify_subscription_order(rzrpy_client, subscription_id)

    await orders_collection.update_one(
        {'_id': subscription_id},
        {'$set': {**result}}
    )

    if result['sub_status'] not in ['created', 'active', 'authenticated']:
        return {'success': False, **result}

    subscription.update({'payment_id': capture.paymentId})
    if result['paid_count'] == 1:
        tasks.add_task(update_subscriptions,
                       subscription, subscription['user'])

    return {'success': True, **result}


async def update_subscriptions(order, user_id):
    subscription = {
        'name': order['plan'],
        'startDate': order['startDate'],
        'endDate': order['endDate'],
        'order_id': str(order['_id']),
        'payment_id': order.get('payment_id'),
        'amount': order.get('amount')
    }
    await users_collection.update_one(
        {'_id': user_id},
        {'$set': {'activeSubscription': True},
            '$push': {'subscriptions': subscription}}
    )


@router.post("/cancel/{sub_id}")
async def cancel_emandate(sub_id: str, request: Request):
    try:
        token = request.headers.get('authorization', False)
        token = decode_token(token.split(" ")[1])
        admin = token.get('admin', False) or token.get('superadmin', False)
        query = {'_id': sub_id} if admin else {
            '_id': sub_id, 'user_id': token['id']}
        order = await orders_collection.find_one(query)
        body = {"$set": {"paid": True, "subscription_status": 'cancel'}}
        if order:
            response = rzrpy_client.subscription.cancel(sub_id)
            if response['status'] == "cancelled":
                await orders_collection.update_one(query, body)
                return {'success': True}
        return {'success': False}
    except Exception as e:
        print(str(e.with_traceback()))
        return {'success': False}
