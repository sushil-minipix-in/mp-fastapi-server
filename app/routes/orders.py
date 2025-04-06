from app.db import Mongo
from bson.objectid import ObjectId
from datetime import date, datetime, timedelta
from pytz import timezone
from fastapi import APIRouter, HTTPException, Body
from fastapi import Depends, Security, BackgroundTasks
from pymongo import DESCENDING

from .utils import decode_token, rzrpy_client, get_current_employee, decode_headers  # noqa: E501
from ..models.order import Order, CaptureOrder
from ..models.emails import Messages
from ..models.sms import SMSMessage
from ..models.tracking_params import OrderTrackingParams

db = Mongo()
orders_collection = db.orders
users_collection = db.users
discounts_collection = db.discounts

router = APIRouter()


@router.get("")
async def get_orders(
    current: int = 1,
    size: int = 10,
    plan: str = None,
    start_date: str = None,
    end_date: str = None,
    paid: bool = False,
    currency: str = None,
    token=Security(get_current_employee, scopes=["Orders:read"])
):
    orders = []
    query = {}
    if plan:
        query['plan'] = plan
    if start_date and end_date:
        query['date'] = {"$gte": datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S").isoformat(),
                         "$lte": datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").isoformat()}

    query['paid'] = paid

    if currency is not None:
        query['currency'] = currency

    total = await orders_collection.count_documents(query)
    async for order in orders_collection.find(query).sort("date", DESCENDING).skip((current - 1) * 10).limit(size):  # noqa: E501
        order['_id'] = str(order['_id'])
        user = await users_collection.find_one({'_id': ObjectId(order['user'])})
        user_str = ''
        if user and 'email' in user:
            user_str += f'Email: {user["email"]}\n'
        if user and 'mobile' in user:
            user_str += f'Mobile: {user["mobile"]}'
        order['user'] = user_str
        orders.append(order)
    return {"orders": orders, "total": total}


@router.get("/{id}")
async def get_order_details(
    id: str,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Orders:read"])
):
    order = await orders_collection.find_one({'_id': id})

    if order:
        user_id = order['user']
        order['_id'] = str(order['_id'])
        user = await users_collection.find_one({'_id': user_id})
        user_str = ''
        email = None
        if user:
            if 'email' in user:
                email = user["email"]
                user_str += f'Email: {user["email"]}\n'
            if 'mobile' in user:
                user_str += f'Mobile: {user["mobile"]}'

        order['user'] = user_str

        if order['paid'] is False:
            order = await check_order_status(order, user_id, email, tasks)
            return order
        else:
            return order
    else:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("")
async def create_order(
    order: Order,
    token=Depends(decode_token),
    header=Depends(decode_headers)
):
    currency = header['currency']
    plan_id = order.planId
    result = await order.get_amount(currency)
    if result.get('success') is not True or result.get('amount', 0) <= 0:
        return {"success": False, "Message": "Plan not available "}
    result["amount"] = max(result["amount"], 1)
    del result['success']
    result = {
        **result,
        'currency': currency,
        'date': datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds'),
        'user_id': token['id']
    }

    pg = 'razorpay'
    order_obj = rzrpy_client.order.create(data={
        "amount": result['amount'] * 100,
        "currency": currency,
        "notes": {
            "user_id": token["id"], "plan_id": plan_id
        }
    })
    result['id'] = order_obj['id']
    if order_obj['status'] == 'created':
        await orders_collection.insert_one({
            '_id': result['id'],
            'user': ObjectId(token['id']),
            **result, "paid": False, 'pg': pg,
            **OrderTrackingParams.parse_params(order.tracking)
        })
        return {
            "success": True, "id": result['id'],
            "amount": result['amount'],
            "currency": currency, 'pg': pg,
            'txnToken': result.get('txnToken'),
            'MID': result.get('MID')
        }
    else:
        return {"success": False, "Message": "Order creation failed "}


@router.post("/{order_id}/upgrade")
async def create_upgrade_order(
    order_id: str,
    plan_id: str,
    tracking: OrderTrackingParams = Body({}, embed=True),
    token=Depends(decode_token),
    header=Depends(decode_headers)
):
    currency = header['currency']
    query = {"_id": order_id, 'user': ObjectId(token['id'])}
    order = await orders_collection.find_one(query)
    result = {'success': False}
    if order and order['currency'] == currency and order['paid']:
        plans = await Order.get_upgrade_options(order, token['id'])
        result = await Order.get_upgrade_amount(plans, plan_id)

    if result and result['success'] is not True:
        return {"success": False, "Message": "Plan not available"}
    del result['success']

    result = {**result, 'paid': False, 'currency': currency, 'pg': 'razorpay',
              'date': datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')}

    order_obj = rzrpy_client.order.create(data={
        "amount": result['amount'] * 100,
        "currency": currency,
        "notes": {
            "user_id": token["id"], "plan_id": result['plan_id']
        }
    })
    if order_obj['status'] == 'created':
        await orders_collection.insert_one({
            '_id': order_obj['id'], 'amount': result['amount'],
            'user': ObjectId(token['id']), 'user_id': token['id'],
            **result, **OrderTrackingParams.parse_params(tracking)
        })
        return {"success": True, "id": order_obj['id'],
                "amount": result['amount'], "currency": currency}
    else:
        return {"success": False, "Message": "Order creation failed "}


@router.post("/{order_id}/charge")
async def capture_order(
    order_id: str,
    capture: CaptureOrder,
    tasks: BackgroundTasks,
    token=Depends(decode_token)
):

    order = await orders_collection.find_one({'_id': order_id, 'pg': 'razorpay'})  # noqa: E501
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    if not order or not user:
        raise HTTPException(status_code=400, detail="Bad Payment Inputs")

    result = await capture.capture_razorpay_order(rzrpy_client, order)

    await orders_collection.update_one(
        {'_id': order['_id']},
        {'$set': {**result}}
    )

    if result['paid'] is not True:
        return {"success": False, **result}

    tasks.add_task(update_subscriptions, order, order['user'], user.get('email'))  # noqa: E501
    tasks.add_task(update_discount, order['_id'])
    await send_alert(user, order, tasks)

    return {"success": True, **result}


@router.get("/{order_id}/upgrade_options")
async def upgrade_order(
    order_id: str,
    token=Depends(decode_token),
    header=Depends(decode_headers)
):
    currency = header['currency']
    query = {"_id": order_id, 'user': ObjectId(token['id'])}
    order = await orders_collection.find_one(query)
    if order and order.get('currency') == currency and order['paid']:
        plans = await Order.get_upgrade_options(order, token['id'])
        return {"plans": plans}
    else:
        return {"plans": []}


async def update_subscriptions(order, user_id, email):
    subscription = {
        'name': order['plan'],
        'startDate': order['startDate'],
        'endDate': order['endDate'],
        'order_id': str(order['_id']),
        'payment_id': order.get('payment_id')
    }
    await users_collection.update_one(
        {'_id': user_id},
        {'$set': {'activeSubscription': True},
            '$push': {'subscriptions': subscription}}
    )
    if email:
        subject, body = Messages.on_subscription_buy(subscription)
        await Messages.send_ses_email(email, subject, body)


async def update_discount(order_id):
    order = await orders_collection.find_one({'_id': order_id})

    if 'discountCode' not in order:
        return

    discount = await discounts_collection.find_one({
        'code': order['discountCode']
    })

    if not discount:
        return

    await discounts_collection.update_one(
        {'_id': discount['_id']},
        {'$inc': {'tokensUsed': 1}}
    )


async def check_order_status(order, user_id, email, tasks):
    payments = rzrpy_client.order.payments(id)
    for payment in payments['items']:
        if payment['status'] == 'captured':
            order['paid'] = True
            subscription = {
                'plan': order['plan'],
                '_id': order["_id"],
                'startDate': str(date.today()),
                'endDate': str(date.today() + timedelta(days=order['duration']))  # noqa: E501
            }
            tasks.add_task(update_subscriptions, subscription, user_id, email)  # noqa: E501
            await orders_collection.update_one({'_id': id}, {"$set": {"paid": True}})  # noqa: E501
            break

    return order


async def send_alert(user, order, tasks: BackgroundTasks):
    if 'discountCode' in order and order["discountCode"] == "upgrade":
        if user.get('email'):
            subject, body = Messages.on_successful_upgrade(user)
            tasks.add_task(Messages.send_email,
                           user['email'], subject, body)
        else:
            body = SMSMessage.on_successful_upgrade()
            tasks.add_task(SMSMessage.send_sms, user["mobile"], body)
    else:
        if user.get('email'):
            subject, body = Messages.on_successful_subsription_purchase(user)
            tasks.add_task(Messages.send_email,
                           user['email'], subject, body)
        else:
            body = SMSMessage.on_successful_subscription_purchase()
            tasks.add_task(SMSMessage.send_sms, user["mobile"], body)
