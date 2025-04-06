import json
from uuid import uuid4

from app.config import AppConfig
from app.db import Mongo
from ..models.emails import Messages
from ..models.tracking_params import OrderTrackingParams
from ..models.paytm import PaytmOrder
from ..models.order import Order
from .utils import decode_headers, decode_token

from aiohttp import ClientSession
from bson import ObjectId
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from paytmchecksum import PaytmChecksum
from paytmpg import MerchantProperty, LibraryConstants


config = AppConfig()
if config.paytm_env == "staging":
    paytm_env = LibraryConstants.STAGING_ENVIRONMENT
    paytm_url = "https://securegw-stage.paytm.in"
    paytm_callback_url = "https://securegw-stage.paytm.in/theia/paytmCallback"
else:
    paytm_env = LibraryConstants.PRODUCTION_ENVIRONMENT
    paytm_url = "https://securegw.paytm.in"
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
headers = {"Content-type": "application/json"}


async def create_paytm_emandate_order(result):
    order_id = "paytm_sub_" + str(uuid4())
    # CC , DC , PBI , BANK_MANDATE , UPI
    units = {
        1: 'DAY', 7: 'WEEK', 30: 'MONTH',
        60: 'BI_MONTHLY', 90: 'QUARTER',
        180: 'SEMI_ANNUALLY', 365: 'YEAR'
    }
    params = {
        "body": {
            "requestType": "NATIVE_SUBSCRIPTION",
            "mid": config.paytm_mid,
            "websiteName": config.paytm_website,
            "orderId": order_id,
            "subscriptionAmountType": "FIX",
            "subscriptionFrequency": "1",
            "subscriptionFrequencyUnit": units.get(result['duration'], 'DAY'),
            "subscriptionStartDate": date.today().strftime("%Y-%m-%d"),
            "subscriptionGraceDays": "0",
            "subscriptionExpiryDate": "2031-05-20",
            "subscriptionEnableRetry": "1",
            "txnAmount": {
                "value": f"{round(result['amount'])}.00",
                "currency": "INR",
            },
            "userInfo": {
                "custId": result['user_id'],
            }
        }
    }

    checksum = PaytmChecksum.generateSignature(
        json.dumps(params["body"]), config.paytm_key)
    params["head"] = {"signature": checksum, "channelId": result['channelId']}
    url = f"{paytm_url}/subscription/create?mid={config.paytm_mid}&orderId={order_id}"
    async with ClientSession() as session:
        async with session.post(url, headers=headers, data=json.dumps(params)
                                ) as response:
            response = await response.json()
            result_info = response['body']['resultInfo']
            result.update({
                'message': result_info['resultMsg'],
                'code': result_info,
                'id': order_id,
                'MID': config.paytm_mid
            })
            if result_info['resultCode'] == "0000":
                result['txnToken'] = response['body']['txnToken']
                result['subscriptionId'] = response['body']['subscriptionId']
                result['signature'] = response['head']['signature']
                result['success'] = True
            else:
                result['success'] = False


async def capture_paytm_emandate_order(order_id, sub_id):
    '''
    INIT, ACTIVE, REJECT, IN_AUTHORIZATION, AUTHORIZED, AUTHORIZATION_FAILED, EXPIRED, CLOSED, SUSPENDED
    '''
    params = {
        "body": {
            "mid": config.paytm_mid,
            "subsId": sub_id
        }
    }
    checksum = PaytmChecksum.generateSignature(
        json.dumps(params["body"]), config.paytm_key)
    params["head"] = {
        "tokenType": "AES",
        "signature": checksum
    }
    url = f"{paytm_url}/subscription/checkStatus"
    async with ClientSession() as session:
        async with session.post(url, headers=headers,
                                data=json.dumps(params)) as response:
            response = await response.json()
            status_code = response['body']['resultInfo']['code']
            payment_id = response['body']['orderId']
            result = {
                'message': response['body']['resultInfo']['message'],
                'code': response['body']['resultInfo']['code'],
                'id': order_id,
                'MID': config.paytm_mid,
                'sub_status': response['body']['status']
            }
            if status_code == '3006':
                result['success'] = True
                result['paid'] = True
                result['paymentId'] = payment_id
            else:
                result['success'] = False
                result['paid'] = False
            return result


@router.post("")
async def create_emandate_order(
    order: PaytmOrder,
    token=Depends(decode_token),
    header=Depends(decode_headers)
):
    tmp_order = Order(planId=order.planId, discountCode=None)
    result = await tmp_order.get_amount('INR')

    if result.get("success") is not True or result.get("amount", 0) <= 0:
        return {"success": False, "detail": "Plan not available"}
    del result["success"]

    result["currency"] = 'INR'
    result["date"] = date.today().strftime("%Y-%m-%d")
    result["user_id"] = token["id"]
    result["channelId"] = order.channelId

    await create_paytm_emandate_order(result)
    order_id = result.pop('id', 0)
    await orders_collection.insert_one({
        '_id': order_id,
        'subscription': True,
        'user': ObjectId(token['id']),
        **result, "paid": False,
        **OrderTrackingParams.parse_params(order.tracking)
    })

    return {'success': True, **result, 'id': order_id}


@router.post("/{order_id}/charge")
async def capture_emandate_order(
    order_id: str,
    tasks: BackgroundTasks,
    token=Depends(decode_token)
):

    order = await orders_collection.find_one({'_id': order_id})  # noqa: E501
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    if not order or not user:
        raise HTTPException(status_code=400, detail="Bad Payment Inputs")

    result = await capture_paytm_emandate_order(order_id, order['subscriptionId'])

    await orders_collection.update_one(
        {'_id': order_id},
        {'$set': {**result}}
    )

    if result.get('paid') is not True:
        subject, body = Messages.on_subscription_error(result)
        tasks.add_task(Messages.send_ses_email,
                       user.get('email'), subject, body)
        return {"success": False, **result}

    return {"success": True, **result}


@router.post("/cancel/{id}")
async def cancel_emandate(id: str, request: Request):
    token = request.headers.get('authorization', '   ')
    token = decode_token(token.split(" ")[1])
    admin = (token.get('admin', False) or token.get('superadmin', False))
    query = {'_id': id} if admin else {'_id': id, 'user_id': token['id']}
    order = await orders_collection.find_one(query)
    body = {"$set": {"paid": True, "subscription_status": 'cancel'}}
    if order:
        params = {
            "body": {
                "mid": config.paytm_mid,
                "subsId": order['subscriptionId'],
            }
        }
        checksum = PaytmChecksum.generateSignature(
            json.dumps(params["body"]), config.paytm_key)
        params["head"] = {
            "tokenType": "AES",
            "signature": checksum
        }
        url = f"{paytm_url}/subscription/cancel"
        async with ClientSession() as session:
            async with session.post(
                    url,
                    headers=headers,
                    data=json.dumps(params)) as response:
                response = await response.json()
                if response['body']['resultInfo']['code'] == "200":
                    await orders_collection.update_one(query, body)
                    return {'success': True}
    return {'success': False}
