import base64
import json
import hashlib
import nanoid

from app.config import AppConfig
from app.db import Mongo

from datetime import date, timedelta, datetime
from pytz import timezone
from aiohttp import ClientSession
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from fastapi import HTTPException, Security, Header, Body
from bson.objectid import ObjectId
from uuid import uuid4

from .utils import decode_token, get_current_employee, make_api_request
from ..models.order import Order, CaptureOrder, OrderTrackingParams

db = Mongo()
users_collection = db.users
plans_collection = db.plans
orders_collection = db.orders
discounts_collection = db.discounts

router = APIRouter()
config = AppConfig()


success_redirect_url = config.phonepe_uri_success
fail_redirect_url = config.phonepe_uri_fail
merchant_id = config.phonepe_merchant_id
key = config.phonepe_key
key_index = config.phonepe_key_index
phonepe_url = config.phonepe_api_host
phonepe_api_callback_url = config.phonepe_callback_url

v3_recurring_init = "/v3/recurring/debit/init"

phonepe_urls = {
    'api_url': phonepe_url,
    'v3_recurring_init': v3_recurring_init,
    'v4_debit': "/v4/debit",
    'v3_create_subscription': '/v3/recurring/subscription/create',
}


def get_headers(x_verify, merchant_id=False, callback=False, redirect=False):
    header = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-Verify": x_verify
    }
    if callback:
        header['X-CALLBACK-URL'] = phonepe_api_callback_url
        header['X-CALLBACK-MODE'] = 'POST'
    if merchant_id:
        header['X-MERCHANT-ID'] = merchant_id
    return header


def get_payload(amount, user, emandate=False):
    user_id = user['_id']
    name = user.get("name", "na")
    email = user.get("email", "")
    mobile = user.get("mobile", None)
    mobile_number = mobile.strip()[0:11] if mobile else ''
    unique_id = str(uuid4())
    payload = {
        "merchantId": merchant_id,
        "merchantUserId": "MUID_" + str(user_id),
        "amount": amount,
        "mobileNumber": mobile_number,
        "email": email,
    }
    recurring = {
        'merchantSubscriptionId': "ppe_sub_" + unique_id,
        'subscriptionName': "MiniPIX Subscription",
        'authWorkflowType': 'TRANSACTION',
        'amountType': 'FIXED',
        'frequency': 'YEARLY',
        'recurringCount': 30,
        'description': "MiniPIX Subscription",
    }
    one_time = {
        "transactionId": "ppe_t_" + unique_id,
        "merchantOrderId": "ppe_moid_" + unique_id,
        "message": "MiniPIX Subscription",
        "expiresIn": 3600,
        "shortName": name
    }
    payload.update(recurring if emandate else one_time)
    payload_json = json.dumps(payload)
    payload_base64 = base64.b64encode(payload_json.encode("utf-8")).decode()  # noqa: E501
    return payload, payload_base64


async def phonepay_payment(amount, user):
    payload, payload_base64 = get_payload(amount, user)
    transaction_id = payload['transactionId']
    x_verify_string = f"{payload_base64}/v4/debit{key}"
    x_verify_hash = (hashlib.sha256(x_verify_string.encode())).hexdigest()
    x_verify_final = f"{x_verify_hash}###{key_index}"
    transaction_data = {
        "pay_load": payload,
        "pay_load_b64": payload_base64,
        "x-verify": x_verify_final,
        "transactionId": transaction_id
    }
    body = {"request": payload_base64}
    res = {'success': False}
    async with ClientSession() as session:
        async with session.post(
            f"{phonepe_url}/v4/debit",
            headers=get_headers(x_verify_final, False, True, False),
            json=body
        ) as response:
            res = await response.json()
            status = res['code'] == 'SUCCESS'
            if status:
                transaction_data["response_from_pp"] = res
                base64.b64encode(
                    json.dumps(transaction_data).encode("utf-8")
                ).decode()
            res = {
                'success': status,
                **res.get('data', {}),
                'transactionId': payload['transactionId']
            }
    return res


async def check_phonepe_transactions(order):
    try:
        transaction_id = order['_id']
        base = f"/v3/transaction/{merchant_id}/{transaction_id}/status"
        sha = base + key
        sha256 = (hashlib.sha256(sha.encode())).hexdigest()
        x_verify = sha256 + "###" + key_index
        headers = get_headers(x_verify)
        async with ClientSession() as session:
            async with session.get(phonepe_url + base, headers=headers) as response:  # noqa: E501
                res = await response.json()
                result = {
                    "key": key,
                    "key_index": key_index,
                    "merchant_id": merchant_id,
                    "transactionId": transaction_id,
                    "sha": sha,
                    "sha256": sha256,
                    "xverify": x_verify,
                    "pp_response": res
                }
                base64.b64encode(
                    json.dumps(result.encode("utf-8"))
                ).decode()
                status = res['success'] and res['code'] == 'PAYMENT_SUCCESS'
                res = {
                    "success": status,
                    "paid": status,
                    **res.get('data', {})
                }
                return res
    except Exception as e:
        return {'success': False, 'message': str(e)}


async def generate_phonepe_order(order_details, user, platform, pay_type):
    _id = str(nanoid.generate(size=19))
    while True:
        order = await orders_collection.find_one({"_id": f"pp_{_id}"})
        if order or _id.startswith("_"):
            _id = str(nanoid.generate(size=19))
        else:
            break
    payload = {
        'merchantId': merchant_id,
        'merchantUserId': str(user['_id']),
        'merchantTransactionId': f"pp_{_id}",
        'amount': int(order_details.get('amount', 0) * 100),
        'redirectUrl': success_redirect_url,
        'redirectMode': 'GET',
        'callbackUrl': phonepe_api_callback_url,
        'paymentInstrument': {
            'type': 'PAY_PAGE'
        }
    }
    if platform == "android" and pay_type == "intent":
        payload["deviceContext"] = {
            "deviceOS": "ANDROID"
        }
        payload["paymentInstrument"] = {
            "type": "UPI_INTENT",
            "targetApp": "com.phonepe.app"
        }
    payload_json = json.dumps(payload)
    payload_base64 = base64.b64encode(payload_json.encode("utf-8")).decode()

    request_body = {'request': payload_base64}
    sha256_sum = (hashlib.sha256(
        f"{payload_base64}/pg/v1/pay{key}".encode())).hexdigest()
    x_verify_header = f"{sha256_sum}###{key_index}"
    headers = {
        'Content-Type': 'application/json',
        'X-VERIFY': x_verify_header
    }

    if platform == "android" and pay_type != "intent":
        await orders_collection.insert_one({'_id': payload['merchantTransactionId'], **order_details, 'paid': False})
        return {"base64Body": payload_base64, "checksum": x_verify_header, "id": payload['merchantTransactionId']}

    async with ClientSession() as session:
        async with session.post(phonepe_url, json=request_body, headers=headers) as response:
            res = await response.json()
            return res


@router.post("")
async def create_order(
    order: Order,
    platform: str = "web",
    pay_type: str = "upi",
    token=Depends(decode_token)
):
    plan = await plans_collection.find_one({'_id': ObjectId(order.planId)})
    if plan is None:
        return {"success": False, "message": "Plan not found"}
    amount = plan.get("price", {}).get('INR', 0)
    code = order.discountCode
    utm_data = OrderTrackingParams.parse_params(order.tracking)
    if utm_data == {}:
        utm_data = {
            "utm_source": "NA",
            "utm_medium": "NA",
            "platform": platform
        }
    order_details = {
        'amount': amount,
        'user': ObjectId(token['id']),
        'plan': plan['name'],
        'duration': plan['duration'],
        'date': str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')),
        'pg': 'PhonePe',
        'discountCode': code if code is not None else 'None',  # noqa: E501
        'currency': 'INR',
        'utm_data': utm_data,
        'status': "pending"
    }
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    if user is None:
        return {"success": False, "message": "User not found"}

    phonepe_order = await generate_phonepe_order(order_details, user, platform, pay_type)

    if platform == "android" and pay_type != "intent":
        return {"base64Body": phonepe_order["base64Body"], "checksum": phonepe_order["checksum"], "id": phonepe_order['id'], "amount": amount/100}

    if phonepe_order['success']:
        await orders_collection.insert_one({
            '_id': phonepe_order['data']['merchantTransactionId'], **order_details, 'paid': False
        })

        return {
            "status": "success",
            "success": True,
            "id": phonepe_order['data']['merchantTransactionId'],
            "amount": amount / 100,
            "pp_order": phonepe_order,
            "response_status": "success"
        }
    else:
        return phonepe_order


@router.post("/{orderId}/upgrade")
async def create_upgrade_order(
    order_id: str,
    plan_id: str,
    tracking: OrderTrackingParams = Body({}, embed=True),
    platform: str = 'web',
    pay_type: str = "upi",
    token=Depends(decode_token),
):
    query = {"_id": order_id, 'user': token['id']}
    order = await orders_collection.find_one(query)
    user = await users_collection.find_one({"_id": ObjectId(token["id"])})
    utm_data = OrderTrackingParams.parse_params(tracking)
    if not user:
        raise HTTPException(404, "User not found")
    result = {'success': False}
    if order and order['currency'] == "INR" and order['paid']:
        plans = await Order.get_upgrade_options(order, token['id'])
        result = await Order.get_upgrade_amount(plans, plan_id)

    if result and result['success'] is not True:
        return {"success": False, "Message": "Plan not available"}
    del result['success']

    result = {**result, 'paid': False, 'currency': "INR"}
    plan = {
        'name': result["plan"],
        "_id": result["plan_id"],
        "duration": result["duration"],
    }
    if utm_data == {}:
        utm_data = {
            "utm_source": "NA",
            "utm_medium": "NA",
            "platform": platform
        }
    order_details = {
        'amount': result["amount"],
        'user': ObjectId(token['id']),
        'plan': plan['name'],
        'duration': plan['duration'],
        'date': str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')),
        'pg': 'PhonePe',
        'discountCode': result["discountCode"],  # noqa: E501
        'currency': 'INR',
        'utm_data': utm_data,
        'status': 'pending'
    }
    phonepe_order = await generate_phonepe_order(order_details, user, platform, pay_type)
    if platform == "android":
        return {"base64Body": phonepe_order["base64Body"], "checksum": phonepe_order["checksum"], "id": phonepe_order['id'], "amount": result["amount"]/100}

    if phonepe_order['success']:
        await orders_collection.insert_one({
            '_id': phonepe_order['data']['merchantTransactionId'], **order_details, 'paid': False
        })

        return {
            "status": "success",
            "success": True,
            "id": phonepe_order['data']['merchantTransactionId'],
            "amount": result["amount"] / 100,
            "pp_order": phonepe_order,
            "response_status": "success"
        }
    else:
        return phonepe_order


@router.post("/phonepe/checkpayment")
async def capture_order_phonepe(
    details: CaptureOrder,
    token=Depends(decode_token)
):
    pp_transection_id = details.paymentId
    pp_transection_id = pp_transection_id[-26:]

    query = {'_id': pp_transection_id}
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    order = await orders_collection.find_one(query)

    if order is None or user is None:
        return {
            "success": False,
            "message": "No order found with this detail.",
            "redirect_url": f'{fail_redirect_url}'
        }

    paymentstatus = await check_phonepe_transactions(order)
    valid = paymentstatus['success']
    if valid:
        subscription = {
            'name': order['plan'],
            'startDate': str(date.today()),
            'endDate': str(date.today() + timedelta(days=order['duration'])),
            'order_id': pp_transection_id
        }
        await update_subscriptions(subscription, user['_id'])
        await update_discount(order['_id'])
    await orders_collection.update_one(query, {'$set': paymentstatus})
    return {
        **paymentstatus,
        'redirect_url': success_redirect_url if valid else fail_redirect_url
    }


@router.get("/{id}")
async def get_pporder_details(
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
        if user and 'email' in user:
            user_str += f'Email: {user["email"]}\n'
        if user and 'mobile' in user:
            user_str += f'Mobile: {user["mobile"]}'
        order['user'] = user_str

        if order['paid'] is False:
            paymentstatus = await check_phonepe_transactions(order)  # noqa: E501
            if paymentstatus['success']:
                subscription = {
                    'name': order['plan'],
                    'startDate': str(date.today()),
                    'endDate': str(date.today() + timedelta(days=order['duration'])),
                    'order_id': order['_id']
                }
                paymentdata = paymentstatus['data']
                upd = {
                    'paid': True,
                    **paymentdata
                }
                await orders_collection.update_one({'_id': order['_id']}, {'$set': upd})  # noqa: E501
                await update_subscriptions(subscription, user['_id'])
                await update_discount(order['_id'])

                return {
                    **order,
                    **upd,
                    "success": True,
                    'message': paymentstatus['message'],
                    'redirect_url': f'{success_redirect_url}',
                    'payment_status': paymentstatus
                }
        else:
            return {**order, "success": False}
    else:
        raise HTTPException(status_code=404, detail="Not found")


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

    discount = await discounts_collection.find_one({'code': order['discountCode']})  # noqa: E501

    if not discount:
        return

    if 'tokensUsed' not in discount:
        await discounts_collection.update_one(
            {'_id': discount['_id']},
            {'$set': {'tokensUsed': 1}}
        )
    else:
        await discounts_collection.update_one(
            {'_id': discount['_id']},
            {'$set': {'tokensUsed': order['tokensUsed'] + 1}}
        )


async def recurring_init(session, sub_id, payload):
    load = {
        "merchantId": merchant_id,
        "merchantUserId": payload['merchantUserId'],
        "subscriptionId": sub_id,
        "transactionId": f"ppe_tid_{uuid4()}",
        "autoDebit": True,
        "amount": payload['amount']
    }
    payload64 = base64.b64encode(json.dumps(load).encode("utf-8")).decode()
    sha = payload64 + v3_recurring_init + key
    x_verify = (hashlib.sha256(sha.encode())).hexdigest() + '###' + key_index
    async with session.post(
        phonepe_url + v3_recurring_init,
        headers=get_headers(x_verify, False, True, True),
        json={"request": payload64}
    ) as resp:
        res = await resp.json()
        data = res.get('data', {})
        return {
            **res,
            'success': res['success'] and data.get('state') == 'ACCEPTED',
        }


async def submit_auth_request(session, body):
    url = "/v3/recurring/auth/init"
    payload64 = base64.b64encode(json.dumps(body).encode("utf-8")).decode()
    sha = payload64 + url + key
    x_verify = (hashlib.sha256(sha.encode())).hexdigest() + '###' + key_index
    async with session.post(
        phonepe_url + url,
        headers=get_headers(x_verify, False, True, True),
        json={"request": payload64}
    ) as resp:
        resp = await resp.json()
        return resp


@router.post("/emandate")
async def create_phonepe_subscription(
    order: Order,
    tasks: BackgroundTasks,
    token=Depends(decode_token)
):
    response = {'success': True}
    plan = await plans_collection.find_one({'_id': ObjectId(order.planId)})
    user = await users_collection.find_one({'_id': ObjectId(token['id'])})
    amount = plan.get("price", {}).get('INR', 0) * 100
    if not plan or not user or not response['success']:
        return {"success": False, "detail": "Bad Input data"}

    merchant_user_id = "MUID_" + token['id']
    transaction_id = "ppe_t_" + str(uuid4())

    payload, payload_base64 = get_payload(amount, user, True)
    sha = payload_base64 + '/v3/recurring/subscription/create' + key
    x_verify = (hashlib.sha256(sha.encode())).hexdigest() + '###' + key_index

    res, resp = {'success': False}, {'success': False}
    res = await make_api_request(
        method = "POST",
        url = f"{phonepe_url}/v3/recurring/subscription/create",
        headers = get_headers(x_verify),
        payload = {"request": payload_base64}
    )
    print(res)
    if res['success'] is not True or res['code'] != 'SUCCESS':
        return res
    sub_id = res['data']['subscriptionId']
    auth_body = {
                "merchantId": merchant_id,
                "merchantUserId": merchant_user_id,
                "subscriptionId": sub_id,
                "authRequestId": transaction_id,
                "amount": amount,
                "vpa": order.vpa_id
            }
    resp = await submit_auth_request(session, auth_body)

    if res.get('success'):
        await orders_collection.insert_one({
                "_id": payload['merchantSubscriptionId'],
                'paid': False,
                'amount': amount / 100,
                'user': ObjectId(token['id']),
                'user_id': token['id'],
                'plan': plan['name'],
                'duration': plan['duration'],
                'date': date.today().strftime("%Y-%m-%d"),
                'pg': 'phonepe',
                **resp
            })
        return resp


async def verify_vpa(vpa_id):
    url = f"/v3/vpa/{merchant_id}/{vpa_id}/validate"
    sha = url + key
    x_verify = (hashlib.sha256(sha.encode())).hexdigest() + '###' + key_index
    resp = {"success": False}
    async with ClientSession() as session:
        async with session.get(
            phonepe_url + url,
            headers=get_headers(x_verify)
        ) as resp:
            resp = await resp.json()
            data = resp.get('data')
            print(data)
    return {
        **resp,
        "success": resp["success"] and data.get('exists') and resp['code'] == "SUCCESS"
    }


@router.post("/callback_s2s")
async def handle_s2s_callback(
    bg: BackgroundTasks,
    req: Request,
    x_verify: str = Header(default=None)
):
    if x_verify is None:
        raise HTTPException(status_code=401, detail="Not authorised")

    req_json = await req.json()
    payload_base64 = req_json['response']
    sha256_sum = (hashlib.sha256(
        f"{payload_base64}{key}".encode())).hexdigest()
    if x_verify != f"{sha256_sum}###{key_index}":
        raise HTTPException(status_code=400, detail="Bad request")

    response = base64.b64decode(req_json['response']).decode('ascii')
    response_json = json.loads(response)
    success = response_json.get('success')
    if success:
        data = response_json.get('data', {})
        order_id = data.get('merchantTransactionId')
        order = await orders_collection.find_one({'_id': order_id})

        subscription = {
            'name': order['plan'],
            'startDate': str(date.today()),
            'endDate': str(date.today() + timedelta(days=order['duration'])),
            'orderId': order['_id'],
            'amount': order['amount'],
            'currency': 'INR',
            'utm_data': order.get('utm_data', {
                'utm_source': 'NA',
                'utm_medium': 'NA',
                'platform': 'NA'
            }),
            'status': "Active"
        }

        await orders_collection.update_one(
            {'_id': order_id},
            {'$set': {'paid': True, 'status': 'success'}}
        )
        await users_collection.update_one(
            {'_id': ObjectId(order['user'])},
            {
                '$set': {'activeSubscription': True},
                '$push': {'subscriptions': subscription}
            }
        )
        user = await users_collection.find_one({"_id": ObjectId(order["user"])})
        return {'success': True}
