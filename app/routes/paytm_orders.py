import json

from .orders import send_alert

from ..models.tracking_params import OrderTrackingParams
from ..models.paytm import PaytmOrder
from ..models.order import Order
from .utils import decode_headers, decode_token, get_current_employee

from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Security
from datetime import datetime
from pytz import timezone


from bson import ObjectId
from app.config import AppConfig
from app.db import Mongo

from paytmpg import MerchantProperty, UserInfo, PaymentDetailsBuilder, Payment, Money, EnumCurrency, PaymentStatusDetailBuilder, LibraryConstants  # noqa: E501


config = AppConfig()
if config.paytm_env == "staging":
    paytm_env = LibraryConstants.STAGING_ENVIRONMENT
    paytm_callback_url = "https://securegw-stage.paytm.in/theia/paytmCallback"
else:
    paytm_env = LibraryConstants.PRODUCTION_ENVIRONMENT
    paytm_callback_url = "https://securegw.paytm.in/theia/paytmCallback"


MerchantProperty.set_callback_url(paytm_callback_url)

MerchantProperty.initialize(
    paytm_env,
    config.paytm_mid,
    config.paytm_key,
    config.paytm_client_id,
    config.paytm_website
)

db = Mongo()
orders_collection = db.orders
users_collection = db.users
discounts_collection = db.discounts

router = APIRouter()


async def create_paytm_order(result):
    order_id = f"p{str(ObjectId())}"
    user_info = UserInfo()
    user_info.set_cust_id(result['user_id'])
    txn_amount = Money(EnumCurrency.INR, str(round(result['amount'], 2)))
    payment_details = PaymentDetailsBuilder(
        channel_id=result['channelId'],
        order_id=order_id,
        txn_amount=txn_amount,
        user_info=user_info
    ).build()
    response = Payment.createTxnToken(payment_details)
    response = response.get_json_response()
    response = json.loads(response)
    status_code = response['body']['resultInfo']['resultCode']
    message = response['body']['resultInfo']['resultMsg']
    result.update({
        'message': message,
        'code': status_code,
        'id': order_id,
        'MID': config.paytm_mid
    })
    if status_code in ['0000', '0002']:
        result['txnToken'] = response['body']['txnToken']
        result['signature'] = response['head']['signature']
        result['success'] = True
    else:
        result['success'] = False


async def capture_paytm_order(order_id):
    read_timeout = 30 * 1000
    response = PaymentStatusDetailBuilder(
        order_id).set_read_timeout(read_timeout).build()
    response = Payment.getPaymentStatus(response).get_json_response()
    response = json.loads(response)
    status_code = response['body']['resultInfo']['resultCode']
    message = response['body']['resultInfo']['resultMsg']
    result = {
        'message': message,
        'code': status_code,
        'success': False
    }
    if status_code == '01':
        result['txnId'] = response['body']['txnId']
        result['bankTxnId'] = response['body']['bankTxnId']
        result['amount'] = float(response['body']['txnAmount'])
        result['success'] = True
    elif status_code in ['400', '402']:
        result['pending'] = True
    return result


@router.post("")
async def create_order(
    order: PaytmOrder,
    token=Depends(decode_token),
    header=Depends(decode_headers)
):
    currency = header['currency']
    if currency != 'INR':
        raise HTTPException(status_code=400, detail="Bad request")

    tmp_order = Order(planId=order.planId, discountCode=order.discountCode)
    result = await tmp_order.get_amount(currency)

    if result.get("success") is not True or result.get("amount", 0) <= 0:
        return {"success": False, "detail": "Plan not available"}
    result["amount"] = max(result["amount"], 1)
    del result["success"]

    result["currency"] = currency
    result["date"] = datetime.now(
        timezone("Asia/Kolkata")).isoformat(timespec='seconds')
    result["user_id"] = token["id"]
    result["channelId"] = order.channelId

    await create_paytm_order(result)
    order_id = result.pop('id')
    await orders_collection.insert_one({
        '_id': order_id,
        'user': ObjectId(token["id"]),
        'paid': False,
        **result,
        'pg': 'paytm',
        **OrderTrackingParams.parse_params(order.tracking)
    })

    return {
        "success": True,
        "id": order_id,
        **result
    }


@router.post("/{order_id}/upgrade")
async def create_upgrade_order(
    order_id: str,
    plan_id: str,
    channel_id: str,
    tracking: OrderTrackingParams = Body({}, embed=True),
    token=Depends(decode_token)
):
    query = {"_id": order_id, 'user': ObjectId(token['id'])}
    order = await orders_collection.find_one(query)
    result = {'success': False}
    if order and order['pg'] == 'paytm' and order['paid']:
        plans = await Order.get_upgrade_options(order, token['id'])
        result = await Order.get_upgrade_amount(plans, plan_id)

    if result and result['success'] is not True:
        return {"success": False, "message": "Plan not available"}
    del result['success']

    amount = result['amount']
    result = {
        **result,
        'pg': 'paytm',
        'paid': False,
        'currency': 'INR',
        'user_id': token['id'],
        'date': datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds'),
        'channelId': channel_id
    }

    await create_paytm_order(result)
    order_id = result.pop('id')
    await orders_collection.insert_one({
        '_id': order_id,
        'user': ObjectId(token['id']),
        **result,
        **OrderTrackingParams.parse_params(tracking)
    })
    return {
        "success": True,
        "id": order_id,
        "amount": amount / 100,
        **result
    }


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
        if user:
            if 'email' in user:
                user_str += f'Email: {user["email"]}\n'
            if 'mobile' in user:
                user_str += f'Mobile: {user["mobile"]}'

        order['user'] = user_str

        if order.get('paid', False) is False:
            result = await capture_paytm_order(id)
            order = {**order, **result}
            if order["success"]:
                await orders_collection.update_one(
                    {"_id": id},
                    {"$set": {"paid": True}}
                )
                subscription = {
                    'name': order['plan'],
                    'startDate': order['startDate'],
                    'endDate': order['endDate'],
                    'order_id': str(order['_id'])
                }
                tasks.add_task(update_subscriptions, subscription, user["_id"])
                tasks.add_task(update_discount, order["_id"])
            return order
        else:
            return order
    else:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/{order_id}/charge")
async def capture_order(
    order_id: str,
    tasks: BackgroundTasks,
    token=Depends(decode_token)
):

    order = await orders_collection.find_one({'_id': order_id, 'pg': 'paytm'})
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    if not order:
        raise HTTPException(status_code=400, detail="Bad Payment Inputs")

    result = await capture_paytm_order(order_id)
    await orders_collection.update_one(
        {'_id': order['_id']},
        {'$set': {**result, 'paid': result['success']}}
    )
    if result['success']:
        subscription = {
            'name': order['plan'],
            'startDate': order['startDate'],
            'endDate': order['endDate'],
            'order_id': str(order['_id'])
        }
        tasks.add_task(update_subscriptions, subscription, user["_id"])
        tasks.add_task(update_discount, order["_id"])
        await send_alert(user, order, tasks)
    else:
        return {"success": False, **result}

    return {"success": True, **result}


async def update_subscriptions(subscription, user_id):
    await users_collection.update_one(
        {'_id': user_id},
        {'$set': {'activeSubscription': True},
            '$push': {'subscriptions': subscription}}
    )


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
