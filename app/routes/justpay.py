import os
import base64
import asyncio
import nanoid
from datetime import datetime, timedelta, date
from time import time
from pytz import timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from bson.objectid import ObjectId
import httpx
from app.db import Mongo
from .utils import decode_headers, decode_token, make_api_request
from .. import AppConfig
from ..models.justpay import get_customer_id, activate_mandate_manually
from ..models.order import Order

router = APIRouter()

# Database Collections
db = Mongo()
orders_collection = db.orders
mandates_collection = db.mandates
users_collection = db.users
discounts_collection = db.discounts

config = AppConfig()

# Juspay Configuration
BASE_URL = config.justpay_api_url
api_key = config.justpay_api_key
redirect_url = config.justpay_redirect_url
encoded_key = base64.b64encode(f"{api_key}:".encode()).decode()
AUTHORIZATION = f"Basic {encoded_key}"
SUCCESS_STATUSES = ["NEW", "CHARGED"]
FAILED_STATUSES = ["FAILURE", "ERROR"]
PENDING_STATUSES = ["PENDING_VBV", "AUTHORIZING"]
ALPHANUMERIC_CHARACTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


@router.post("")
async def create_juspay_order(
        order: Order,
        token = Depends(decode_token),
        headers = Depends(decode_headers)
):
    """Create a Juspay order."""
    currency = headers['currency']
    plan_id = order.planId
    result = await order.get_amount(currency)
    if result.get('success') is not True or result.get('amount', 0) <= 0:
        return {"success": False, "Message": "Plan not available "}
    result["amount"] = max(result["amount"], 1)
    del result['success']
    result = {
        **result,
        'currency': currency,
        'date': datetime.now(timezone("Asia/Kolkata")).isoformat(timespec = 'seconds'),
        'user_id': token['id'],
        'user': ObjectId(token["id"]),
        'paid': False,
        'pg': "juspay"
    }
    user = await users_collection.find_one({"_id": ObjectId(token['id'])})
    if not user:
        raise HTTPException(400, "User not found")

    if "activeSubscription" in user and user.get("activeSubscription"):
        return {'success': False, 'message': "User is already subscribed"}

    frequency = None

    if result['duration'] == 7:
        frequency = "WEEKLY"
    elif result['duration'] == 30:
        frequency = "MONTHLY"
    elif result['duration'] == 365:
        frequency = "YEARLY"
    elif result["duration"] == 1:
        frequency = "DAILY"

    customer_id = await get_customer_id(user)

    order_id = f"jp{nanoid.generate(ALPHANUMERIC_CHARACTERS, 18)}"
    print(order_id)

    # if user['eligible_for_trial']:
    #     trial_payload = {
    #     "order_id": order_id,
    #     "amount": "1.0",
    #     "currency": "INR",
    #     "customer_id": customer_id,
    #     "customer_email": user.get("email"),
    #     "customer_phone": user.get("mobile"),
    #     "payment_page_client_id": os.getenv("JUSTPAY_CLIENT_ID"),
    #     "options.create_mandate": "REQUIRED",
    #     "mandate.max_amount": str(float(result["amount"])),
    #     # "mandate.frequency": "ASPRESENTED",
    #     # "mandate.start_date": str(int((datetime.now()+timedelta(days=7)).timestamp())),
    #     "metadata.auto_refund_post_success": "true",
    #     "return_url": redirect_url
    #     }
    #
    #     res = await make_api_request(method = "POST", url = f"{BASE_URL}/session", payload = trial_payload,
    #                                  headers = {"Authorization": AUTHORIZATION})
    #
    #     await mandates_collection.insert_one({
    #         "order_id": order_id,
    #         **result,
    #         "trial": True,
    #         "status": "CREATED",
    #         "customer_id": customer_id
    #     })
    #
    #     return res


    payload = {
        "order_id": order_id,
        "amount": str(float(result["amount"])),
        "customer_id": customer_id,
        "customer_email": user.get("email"),
        "customer_phone": user.get("mobile"),
        "payment_page_client_id": os.getenv("JUSTPAY_CLIENT_ID"),
        "options.create_mandate": "REQUIRED",
        "mandate.max_amount": str(float(result["amount"])),
        "mandate.frequency": frequency,
        "mandate.start_date": str(int((datetime.now()).timestamp())),
        "metadata.auto_refund_post_success": "true",
        "return_url": redirect_url
    }

    res = await make_api_request(method = "POST", url = f"{BASE_URL}/session", payload = payload,
                                 headers = {"Authorization": AUTHORIZATION})

    await mandates_collection.insert_one({
        "order_id": order_id,
        **result,
        "trial": False,
        "status": "CREATED",
        "customer_id": customer_id
    })

    return res


@router.get("/{order_id}")
async def get_order_status(order_id: str, token=Depends(decode_token)):
    res = await make_api_request(method = "GET", url = f"{BASE_URL}/orders/{order_id}",
                                 headers = {"Authorization": AUTHORIZATION})

    status = res["txn_detail"]["status"]

    if status in ["CHARGED", "AUTO_REFUNDED"]:
        mandate_obj = res["mandate"]
        mandate_obj = {**mandate_obj, "order_id": order_id}
        result = await activate_mandate_manually(mandate_obj)
        return result
    else:
        return {"success": False, "message": "Payment Failed"}

