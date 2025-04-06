import base64

from bson import ObjectId
from pydantic import BaseModel
from datetime import datetime, timedelta, date
from pytz import timezone
from fastapi import HTTPException
from six import reraise
from watchfiles import awatch

from app.routes.utils import make_api_request

from ..config import AppConfig
from ..db import Mongo

db = Mongo()
users_collection = db.users
tickets_collection = db.tickets
orders_collection = db.orders
mandates_collection = db.mandates
pending_orders_collection = db.pending_orders

config = AppConfig()

# Juspay Configuration
BASE_URL = config.justpay_api_url
BASE_URL = config.justpay_api_url
api_key = config.justpay_api_key
encoded_key = base64.b64encode(f"{api_key}:".encode()).decode()
AUTHORIZATION = f"Basic {encoded_key}"

class JustpayTicket(BaseModel):
    content_id: str
    content_type: str

async def get_customer_id(user):
    customer_id = ""
    if "jp_customer_id" not in user:
        mobile, email = "", ""
        if "mobile" in user:
            mobile = user['mobile'][3:]
        if "email" in user:
            email = user["email"]
        if "mobile" not in user:
            mobile = "9999999999"
        print(email)
        print(mobile)
        cus_payload = {
            'object_reference_id': str(user["_id"]),
            'mobile_number': mobile,
            'email_address': email,
            'options.get_client_auth_token': "false",
        }
        cus_res = await make_api_request(method = "POST", url = f"{BASE_URL}/customers", payload = cus_payload,
                                         headers = {"Authorization": AUTHORIZATION})
        if "id" in cus_res:
            customer_id = cus_res['id']
            await users_collection.update_one({"_id": user["_id"]}, {"$set": {"jp_customer_id": customer_id}})
    else:
        customer_id = user['jp_customer_id']
    return customer_id

async def update_ticket_details(event):
    ticket_id = event["content"]["order"]["order_id"]
    customer_id = event["content"]["order"]["customer_id"]
    paid = True if event["content"]["order"]["status"] == "CHARGED" else False
    ticket = await tickets_collection.find_one({'_id': ticket_id})
    user = await users_collection.find_one({'jp_customer_id': customer_id})
    if not ticket or not user:
        raise HTTPException(status_code=400, detail="Bad Inputs")

    await tickets_collection.update_one(
        {'_id': ticket['_id']},
        {'$set': {'paid': paid}}
    )
    if paid:
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

ex_payload = {
   "id":"evt_V2_2315aaacaeb14ef7bd08a7233f794b12",
   "date_created":"2024-12-23T10:27:03Z",
   "content":{
      "mandate":{
         "gateway":"PAYTM_V2",
         "mandate_id":"mz6eqMZg5ChntZFgzYdMES",
         "status":"CREATED",
         "frequency":"MONTHLY",
         "last_updated":"2024-12-23T10:26:44Z",
         "start_date":"1734949601",
         "max_amount":1,
         "block_fund":False,
         "currency":"INR",
         "payment_info":{
            "payment_method":"UPI_COLLECT",
            "payment_method_type":"UPI"
         },
         "rule_value":23,
         "amount_rule":"VARIABLE",
         "rule_type":"AFTER",
         "revokable_by_customer":True,
         "order_id":"jp-order-67693ae136528a0452373973",
         "end_date":"2681634401",
         "customer_id":"cth_wKq7vPHicwk5yJnJ",
         "mandate_token":"cdc9325d587b43e1a918713855ee23ec",
         "mandate_type":"EMANDATE"
      }
   },
   "event_name":"MANDATE_CREATED"
}

async def create_mandate(event):
    mandate = await mandates_collection.find_one({"order_id": event["content"]["mandate"]["order_id"]})
    if not mandate:
        return
    await mandates_collection.update_one(
        {"order_id": event["content"]["mandate"]["order_id"]},
        {
            "$set": {"mandate_id": event["content"]["mandate"]["mandate_id"]}
        }
    )
    return


async def update_user_subscription(event):
    order = await orders_collection.find_one({
        "$or": [
            {"_id": event["content"]["mandate"]["order_id"]},
            {"mandate_id": event["content"]["mandate"]["mandate_id"]}
        ]
    })
    if not order:
        return

    user = await users_collection.find_one({"_id": ObjectId(order["user_id"])})
    if not user:
        return


    # update order status
    await orders_collection.update_one(
        {"_id": event["content"]["mandate"]["order_id"]},
        {
            "$set": {
                "paid": True,
                "mandate_id": event["content"]["mandate"]["mandate_id"]
            }
        }
    )

    # store mandate_id for the user and update user subscription
    user_subscription = {
        'name': order['plan'],
        'startDate': order['startDate'],
        'endDate': order['endDate'],
        'order_id': str(order['_id']),
        'mandate_id': event["content"]["mandate"]["mandate_id"]
    }
    await users_collection.update_one(
        {"_id": ObjectId(order["user_id"])},
        {
            "$set": {
                "activeSubscription": True,
                "eligible_for_trial": False,
            },
            '$push': {'subscriptions': user_subscription}
        }
    )


async def activate_mandate(event):
    mandate = await mandates_collection.find_one({"mandate_id": event["content"]["order"]['mandate']["mandate_id"]})
    if not mandate:
        return

    # Check if the mandate was already modified today
    today = datetime.now().strftime("%Y-%m-%d")
    if "lastModified" in mandate and mandate["lastModified"] == today:
        return

    user = await users_collection.find_one({"_id": ObjectId(mandate["user_id"])})
    if not user:
        return

    del mandate["_id"]
    del mandate["order_id"]

    # create a paid order since there was a successful payment
    order_id = ObjectId()
    await orders_collection.insert_one({
        "_id": order_id,
        **mandate,
        "paid": True
    })

    # update the mandate start and end dates in the mandates collection
    new_start = None
    new_end = None
    if mandate["trial"]:
        new_start = datetime.now()
        new_end = (new_start + timedelta(days = 2)).strftime("%Y-%m-%d")
    else:
        new_start = datetime.now()
        new_end = (new_start + timedelta(days = mandate["duration"])).strftime("%Y-%m-%d")

    await mandates_collection.update_one(
        {"mandate_id": event["content"]["mandate"]["mandate_id"]},
        {
            "$set": {
                "startDate": new_start.strftime("%Y-%m-%d"),
                "endDate": new_end,
                "trial": False,
                "paid": True,
                "status": event["content"]["mandate"]["status"],
                "lastModified": today
            }
        }
    )

    # update user subscription
    user_subscription = {
        'name': mandate['plan'],
        'startDate': new_start.strftime("%Y-%m-%d"),
        'endDate': new_end,
        'order_id': str(order_id),
        'mandate_id': event["content"]["mandate"]["mandate_id"]
    }

    await users_collection.update_one(
        {"_id": ObjectId(mandate["user_id"])},
        {
            "$set": {
                "activeSubscription": True,
                "eligible_for_trial": False,
            },
            '$push': {'subscriptions': user_subscription}
        }
    )

async def activate_mandate_manually(mandate_obj):
    mandate = await mandates_collection.find_one({"order_id": mandate_obj["order_id"]})
    if not mandate:
        return {"success": False, "message": "Mandate not found"}

    # Check if the mandate was already modified today
    today = datetime.now().strftime("%Y-%m-%d")
    if "lastModified" in mandate and mandate["lastModified"] == today:
        return {"success": False, "message": "Payment status already updated"}

    user = await users_collection.find_one({"_id": ObjectId(mandate["user_id"])})
    if not user:
        return {"success": False, "message": "User not found"}

    del mandate["_id"]
    del mandate["order_id"]

    # Create a paid order since there was a successful payment
    order_id = ObjectId()
    await orders_collection.insert_one({
        "_id": order_id,
        **mandate,
        "paid": True
    })

    # Update the mandate start and end dates in the mandates collection
    new_start = datetime.now()
    new_end = (new_start + timedelta(days = 2)).strftime("%Y-%m-%d") if mandate["trial"] else (
                new_start + timedelta(days = mandate["duration"])).strftime("%Y-%m-%d")

    await mandates_collection.update_one(
        {"order_id": mandate_obj["order_id"]},
        {"$set": {
            "startDate": new_start.strftime("%Y-%m-%d"),
            "endDate": new_end,
            "trial": False,
            "paid": True,
            "status": mandate_obj["mandate_status"],
            "lastModified": today,
            "mandate_id": mandate_obj["mandate_id"]
        }}
    )

    await pending_orders_collection.update_one({"pending_order_id": mandate_obj["order_id"]}, {"$set":{"paid": True}})
    await mandates_collection.update_one({"order_id": mandate_obj["order_id"]}, {"$set": {"status": "ACTIVE"}})

    # Update user subscription
    user_subscription = {
        "name": mandate["plan"],
        "startDate": new_start.strftime("%Y-%m-%d"),
        "endDate": new_end,
        "order_id": str(order_id),
        "mandate_id": mandate_obj["mandate_id"],
        "amount": mandate["amount"]
    }

    await users_collection.update_one(
        {"_id": ObjectId(mandate["user_id"])},
        {
            "$set": {
                "activeSubscription": True,
                "eligible_for_trial": False,
            },
        "$push": {"subscriptions": user_subscription}
        }
    )

    return {"success": True, "message": "Mandate manually activated"}

async def expire_or_revoke_mandate(event):
    mandate = await mandates_collection.find_one({"mandate_id": event["content"]["mandate"]["mandate_id"]})
    if not mandate:
        return
    # stop mandate
    await mandates_collection.update_one(
        {"mandate_id": event["content"]["mandate"]["mandate_id"]},
        {
            "$set": {"status": event["content"]["mandate"]["status"]}
        }
    )
    return