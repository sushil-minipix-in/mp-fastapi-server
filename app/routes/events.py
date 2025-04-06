import json
import jwt
import OpenSSL
import time

from app.db import Mongo
from app.config import AppConfig
from bson.objectid import ObjectId
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from pydantic import BaseModel
from nanoid import generate

from .utils import rzrpy_client, decode_token
from ..models.emails import Messages
from ..models.sms import SMSMessage

router = APIRouter()

config = AppConfig()
db = Mongo()
users_collection = db.users
orders_collection = db.orders
apple_plans_collection = db.applePlans


class OrderBody(BaseModel):
    signedPayload: str


class AppleOrder(BaseModel):
    appAccountToken: str
    amount: float
    currency: str
    environment: str
    orderId: str


apple_root_cert_pem = """-----BEGIN CERTIFICATE-----
MIICQzCCAcmgAwIBAgIILcX8iNLFS5UwCgYIKoZIzj0EAwMwZzEbMBkGA1UEAwwS
QXBwbGUgUm9vdCBDQSAtIEczMSYwJAYDVQQLDB1BcHBsZSBDZXJ0aWZpY2F0aW9u
IEF1dGhvcml0eTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkGA1UEBhMCVVMwHhcN
MTQwNDMwMTgxOTA2WhcNMzkwNDMwMTgxOTA2WjBnMRswGQYDVQQDDBJBcHBsZSBS
b290IENBIC0gRzMxJjAkBgNVBAsMHUFwcGxlIENlcnRpZmljYXRpb24gQXV0aG9y
aXR5MRMwEQYDVQQKDApBcHBsZSBJbmMuMQswCQYDVQQGEwJVUzB2MBAGByqGSM49
AgEGBSuBBAAiA2IABJjpLz1AcqTtkyJygRMc3RCV8cWjTnHcFBbZDuWmBSp3ZHtf
TjjTuxxEtX/1H7YyYl3J6YRbTzBPEVoA/VhYDKX1DyxNB0cTddqXl5dvMVztK517
IDvYuVTZXpmkOlEKMaNCMEAwHQYDVR0OBBYEFLuw3qFYM4iapIqZ3r6966/ayySr
MA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMAoGCCqGSM49BAMDA2gA
MGUCMQCD6cHEFl4aXTQY2e3v9GwOAEZLuN+yRhHFD/3meoyhpmvOwgPUnPWTxnS4
at+qIxUCMG1mihDK1A3UT82NQz60imOlM27jbdoXt2QfyFMm+YhidDkLF1vLUagM
6BgD56KyKA==
-----END CERTIFICATE-----
"""

apple_intermediate_cert_pem = """-----BEGIN CERTIFICATE-----
MIIDFjCCApygAwIBAgIUIsGhRwp0c2nvU4YSycafPTjzbNcwCgYIKoZIzj0EAwMw
ZzEbMBkGA1UEAwwSQXBwbGUgUm9vdCBDQSAtIEczMSYwJAYDVQQLDB1BcHBsZSBD
ZXJ0aWZpY2F0aW9uIEF1dGhvcml0eTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkG
A1UEBhMCVVMwHhcNMjEwMzE3MjAzNzEwWhcNMzYwMzE5MDAwMDAwWjB1MUQwQgYD
VQQDDDtBcHBsZSBXb3JsZHdpZGUgRGV2ZWxvcGVyIFJlbGF0aW9ucyBDZXJ0aWZp
Y2F0aW9uIEF1dGhvcml0eTELMAkGA1UECwwCRzYxEzARBgNVBAoMCkFwcGxlIElu
Yy4xCzAJBgNVBAYTAlVTMHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEbsQKC94PrlWm
ZXnXgtxzdVJL8T0SGYngDRGpngn3N6PT8JMEb7FDi4bBmPhCnZ3/sq6PF/cGcKXW
sL5vOteRhyJ45x3ASP7cOB+aao90fcpxSv/EZFbniAbNgZGhIhpIo4H6MIH3MBIG
A1UdEwEB/wQIMAYBAf8CAQAwHwYDVR0jBBgwFoAUu7DeoVgziJqkipnevr3rr9rL
JKswRgYIKwYBBQUHAQEEOjA4MDYGCCsGAQUFBzABhipodHRwOi8vb2NzcC5hcHBs
ZS5jb20vb2NzcDAzLWFwcGxlcm9vdGNhZzMwNwYDVR0fBDAwLjAsoCqgKIYmaHR0
cDovL2NybC5hcHBsZS5jb20vYXBwbGVyb290Y2FnMy5jcmwwHQYDVR0OBBYEFD8v
lCNR01DJmig97bB85c+lkGKZMA4GA1UdDwEB/wQEAwIBBjAQBgoqhkiG92NkBgIB
BAIFADAKBggqhkjOPQQDAwNoADBlAjBAXhSq5IyKogMCPtw490BaB677CaEGJXuf
QB/EqZGd6CSjiCtOnuMTbXVXmxxcxfkCMQDTSPxarZXvNrkxU3TkUMI33yzvFVVR
T4wxWJC994OsdcZ4+RGNsYDyR5gmdr0nDGg=
-----END CERTIFICATE-----
"""

root_cert = OpenSSL.crypto.load_certificate(
    OpenSSL.crypto.FILETYPE_PEM,
    apple_root_cert_pem
)
intermediate_cert = OpenSSL.crypto.load_certificate(
    OpenSSL.crypto.FILETYPE_PEM,
    apple_intermediate_cert_pem
)

store = OpenSSL.crypto.X509Store()
store.add_cert(root_cert)
store.add_cert(intermediate_cert)


@router.post("/apple_order")
async def handle_apple_order(body: OrderBody):
    headers = jwt.get_unverified_header(body.signedPayload)
    if not headers:
        raise HTTPException(status_code=400, detail="Bad request")

    x5c = headers['x5c']
    signing_cert = f"-----BEGIN CERTIFICATE-----\n{x5c[0]}\n-----END CERTIFICATE-----"  # noqa: E501
    signing_cert_pem = OpenSSL.crypto.load_certificate(
        OpenSSL.crypto.FILETYPE_PEM,
        signing_cert
    )

    try:
        store_context = OpenSSL.crypto.X509StoreContext(store, signing_cert_pem)  # noqa: E501
        store_context.verify_certificate()

        payload = jwt.decode(
            body.signedPayload,
            load_pem_x509_certificate(signing_cert.encode('utf-8'), default_backend()).public_key(),  # noqa: E501
            algorithms=["ES256"]
        )

        if payload['notificationType'] == 'SUBSCRIBED' or payload['notificationType'] == 'DID_RENEW':  # noqa: E501
            signed_transaction_info = payload['data']['signedTransactionInfo']
            signed_transaction_info = jwt.decode(
                signed_transaction_info,
                options={"verify_signature": False}
            )
            print(signed_transaction_info)
            user = await users_collection.find_one({
                "apple_id": signed_transaction_info["appAccountToken"]
            })
            order_id = str('apple' + generate())
            while True:
                order_obj = await orders_collection.find_one({"_id": order_id})
                if order_obj:
                    order_id = str('apple_' + generate())
                else:
                    break
            subscription = {
                'order_id': order_id,
                'name': signed_transaction_info['productId'],
                'apple': 1,
                'startDate': str(datetime.strptime(time.ctime(signed_transaction_info['purchaseDate'] / 1000), '%c').date()),  # noqa: E501
                'endDate': str(datetime.strptime(time.ctime(signed_transaction_info['expiresDate'] / 1000), '%c').date()),  # noqa: E501
                'amount': signed_transaction_info.get('price')/1000 if "price" in signed_transaction_info else plan.get('price'),
                'currency': signed_transaction_info['currency'],
            }
            plan = await apple_plans_collection.find_one({'planId': signed_transaction_info['productId']})
            await orders_collection.insert_one({
                '_id': order_id,
                'user': user['_id'],
                'amount': signed_transaction_info.get('price')/1000 if "price" in signed_transaction_info else plan.get('price'),
                'plan': signed_transaction_info['productId'],
                'startDate': str(datetime.strptime(time.ctime(signed_transaction_info['purchaseDate'] / 1000), '%c').date()),  # noqa: E501
                'endDate': str(datetime.strptime(time.ctime(signed_transaction_info['expiresDate'] / 1000), '%c').date()),  # noqa: E501
                'date': str(datetime.strptime(time.ctime(signed_transaction_info['purchaseDate'] / 1000), '%c').isoformat()),  # noqa: E501
                'pg': 'apple',
                'paid': True,
                'currency': signed_transaction_info['currency'],
                'environment': signed_transaction_info.get('environment')
            })
            await update_subscriptions(subscription, user['_id'])

        return {"success": True}
    except OpenSSL.crypto.X509StoreContextError:
        return {"success": False}


@router.post("/update_apple_order")
async def update_apple_order(
    payload: AppleOrder,
    token=Depends(decode_token)
):
    apple_payload = {k: v for k, v in payload.__dict__.items()
                     if v is not None}

    user = await users_collection.find_one({"apple_id": apple_payload["appAccountToken"]})
    if not user:
        return {'success': False, 'message': "User Not Found"}
    if str(user['_id']) != token["id"]:
        return {'success': False, 'message': "Invalid Authorization"}

    await orders_collection.update_one(
        {"_id": apple_payload["orderId"]},
        {
            "$set": {
                "amount": apple_payload["amount"],
                "currency": apple_payload["currency"],
                "environment": apple_payload["environment"]
            }
        }
    )

    subscriptions = user.get('subscriptions', [])
    new_subscriptions = []
    for item in subscriptions:
        if item.get('orderId', "") == apple_payload["orderId"]:
            item['amount'] = apple_payload["amount"]
        new_subscriptions.append(item)
    await users_collection.update_one(
        {
            "apple_id": apple_payload["appAccountToken"]
        },
        {
            "$set": {"subscriptions": new_subscriptions}
        }
    )

    return {'success': True}


@router.post("/restore_apple_purchase")
async def restore_apple_purchase(
    user_id: str,
    restore_payload: dict,
    token=Depends(decode_token)
):
    if token["id"] != user_id:
        return {"success": False, "detail": "Forbidden"}
    # find the previous user.
    apple_id = restore_payload.get("appAccountToken", None)
    if not apple_id:
        return {"success": False, "message": "Invalid Payload"}
    old_user = await users_collection.find_one({"apple_id": apple_id, "activeSubscription": True})
    if not old_user:
        return {"success": False, "message": "Apple ID not found"}
    # get new_user details
    new_user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not new_user:
        return {"success": False, 'message': "User not found"}
    existing_subscriptions = old_user.get("subscriptions", [])
    latest_subscription = {}
    if len(existing_subscriptions) > 0:
        latest_subscription = existing_subscriptions[-1]
    # remove subscriptions for the old user
    await users_collection.update_one(
        {"_id": old_user["_id"]},
        {
            "$unset": {"activeSubscription": 1, "subscriptions": 1}
        })
    # update subscriptions for the new user
    await users_collection.update_one(
        {"_id": ObjectId(new_user["_id"])},
        {
            "$set": {"activeSubscription": True},
            "$push": {
                "subscriptions": latest_subscription
            }
        }
    )
    return {"success": True, "user_id": str(new_user["_id"])}


async def update_subscriptions(subscription, user_id):
    await users_collection.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': {'activeSubscription': True},
            '$push': {'subscriptions': subscription}}
    )


async def razorpay_recurring_subscription(body):
    payment_id = body['payload']['payment']['entity']['id']
    sub_body = body['payload']['subscription']['entity']
    query = {'_id': sub_body['id'], "subscription_status": {"$ne": 'cancel'}}
    order = await orders_collection.find_one(query)
    user = await users_collection.find_one({'_id': ObjectId(order['user_id'])})
    for sub in user.get('subscriptions', []):
        if sub.get('payment_id') == payment_id:
            return {"success": False, "detail": "Already captured"}
    first = sub_body['paid_count'] == 1
    start_date = order['startDate'] if first else order['endDate']
    new_end_date = str(
        datetime.strptime(order['endDate'], "%Y-%m-%d").date()
        + timedelta(days=order['duration']))
    end_date = order['endDate'] if first else new_end_date
    subscription = {
        'name': order['plan'],
        'startDate': start_date,
        'endDate': end_date,
        'order_id': str(order['_id']),
        'payment_id': payment_id,
        'amount': order.get('amount')
    }
    doc = {'paid_count': sub_body['paid_count'],
           'total_count': sub_body['total_count'],
           'startDate': start_date, 'endDate': end_date, 'paid': True}
    await update_subscriptions(subscription, user['_id'])
    await orders_collection.update_one({'_id': sub_body['id']}, {"$set": doc})
    return {"success": True, 'email': user.get('email'), 'subscription': subscription}  # noqa: E501


async def razorpay_capture_payment(body):
    payment_id = body['payload']['payment']['entity']['id']
    payload = body['payload']['order']['entity']
    order = await orders_collection.find_one({'_id': payload['id'], 'paid': False})  # noqa: E501
    user = await users_collection.find_one({'_id': ObjectId(order['user_id'])})
    for sub in user.get('subscriptions', []):
        if sub.get('payment_id') == payment_id:
            return {"success": False, "detail": "Already captured"}
    subscription = {
        'name': order['plan'],
        'startDate': order['startDate'],
        'endDate': order['endDate'],
        'order_id': str(order['_id']),
        'payment_id': payment_id
    }
    if payload['status'] == 'paid':
        doc = {'paid': True, "paymentId": payment_id}
        await update_subscriptions(subscription, user['_id'])
        user["_id"] = str(user["_id"])
        await orders_collection.update_one({'_id': payload['id']}, {"$set": doc})  # noqa: E501
        order_type = "subscription"
        if "discountCode" in order and order.get("discountCode") == "upgrade":
            order_type = "upgrade"
        return {
            "success": True,
            'email': user.get('email'),
            'subscription': subscription,
            "user": user,
            "order_type": order_type
        }
    return {"success": False}


@router.post("/razorpay_subscription")
async def handle_razorpay_callbacks(request: Request, tasks: BackgroundTasks):
    # https://razorpay.com/docs/webhooks/payloads/subscriptions#subscription-charged
    # try:
        result = {'success': False}
        # secret = config.razorpay_webhook_secret
        body = await request.json()
        raw_body = json.dumps(body, separators=(',', ':'))
        # sign = request.headers['X-Razorpay-Signature']
        # rzrpy_client.utility.verify_webhook_signature(raw_body, sign, secret)
        print(body["event"])
        if body['event'] not in ["subscription.charged", "order.paid"]:
            return {"success": False, "detail": "Webhook Not configured"}
        if body['event'] == "subscription.charged":
            result = await razorpay_recurring_subscription(body)
        if body['event'] == "order.paid":
            result = await razorpay_capture_payment(body)
        # send_alert(result["user"], result, tasks, "razorpay")
        return result
    # except Exception as e:
    #     print(str(e))
    #     return {"success": False}


@router.post("/paytm_subscription")
async def capture_paytm_subscription_callbacks(request: Request, tasks: BackgroundTasks):
    # https://business.paytm.com/docs/subscription-status-webhook?ref=callbackWebhook
    form = await request.form()
    subs_id = form['SUBS_ID']
    payment_id = form['BANKTXNID']
    order_id = form['ORDERID']
    status = form['STATUS']
    print(form, subs_id, payment_id, order_id)
    if status == 'TXN_SUCCESS':
        query = {'_id': order_id, 'subscription_status': {"$ne": 'cancel'}}
        order = await orders_collection.find_one(query)
        user = await users_collection.find_one({'_id': order['user']})
        if not order or not user:
            return {'success': False, "detail": f"{status} event"}

        for sub in user.get('subscriptions', []):
            if sub.get('payment_id') == payment_id:
                return {'success': False, "detail": "Already Captured"}
        one_paid = order.get('paid_count') == 1
        start_date = order['endDate'] if one_paid else order['startDate']
        new_end_date = str(
            datetime.strptime(order['endDate'], "%Y-%m-%d").date()
            + timedelta(days=order['duration']))
        end_date = new_end_date if one_paid else order['endDate']
        subscription = {
            'name': order['plan'],
            'startDate': start_date,
            'endDate': end_date,
            'order_id': str(order['_id']),
            'payment_id': payment_id
        }
        await update_subscriptions(subscription, user['_id'])
        user = await users_collection.find_one({"_id": user["_id"]})
        doc = {"$set": {'startDate': start_date, 'endDate': end_date},
               "$inc": {'paid_count': 1}}
        await orders_collection.update_one({'_id': order_id}, doc)
        send_alert(user, order, tasks, "paytm")
        return {"success": True}
    else:
        return {'success': False, "detail": f"{status} event"}


def send_alert(user, order, tasks: BackgroundTasks, pg: str):
    if pg == "paytm":
        send_paytm_alert(user, order, tasks)
    elif pg == "razorpay":
        send_razorpay_alert(user, order, tasks)


def send_paytm_alert(user, order, tasks: BackgroundTasks):
    if user and 'email' in user:
        subject, body = "", ""
        if 'discountCode' in order and order.get("discountCode") == "upgrade":
            subject, body = Messages.on_successful_upgrade(user)
        else:
            subject, body = Messages.on_successful_subsription_purchase(
                user)
        tasks.add_task(Messages.send_email, user["email"], subject, body)
    if user and "mobile" in user:
        body = ""
        if 'discountCode' in order and order.get("discountCode") == "upgrade":
            body = SMSMessage.on_successful_upgrade()
        else:
            body = SMSMessage.on_successful_subscription_purchase()
        tasks.add_task(SMSMessage.send_sms, user["mobile"], body)


def send_razorpay_alert(user, order, tasks: BackgroundTasks):
    if order['success'] and order['email'] and order["user"]:
        if order["order_type"] == "upgrade":
            subject, body = Messages.on_successful_upgrade(user)
        else:
            subject, body = Messages.on_successful_subsription_purchase(
                user)
        tasks.add_task(Messages.send_email,
                       order['email'], subject, body)
    if order["success"] and user and "mobile" in user:
        if order["order_type"] == "upgrade":
            body = SMSMessage.on_successful_upgrade()
        else:
            body = SMSMessage.on_successful_subscription_purchase()
        tasks.add_task(SMSMessage.send_sms, user["mobile"], body)
