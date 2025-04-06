import asyncio
import time
import base64
import motor.motor_asyncio
from datetime import datetime, timedelta
from bson.objectid import ObjectId

from app.config import AppConfig
from app.routes.utils import make_api_request

config = AppConfig()
mongo_uri = config.mongo_uri
db_name = config.db_name
BASE_URL = config.justpay_api_url
api_key = config.justpay_api_key
encoded_key = base64.b64encode(f"{api_key}:".encode()).decode()
AUTHORIZATION = f"Basic {encoded_key}"
ALPHANUMERIC_CHARACTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
db = client[db_name]
mandates_collection = db.mandates
pending_orders_collection = db.pending_orders
users_collection = db.users
orders_collection = db.orders

current_date = datetime.now().date()
MAX_RETRIES = 3  # Maximum retries before marking mandate as inactive

async def update_payment_status(mandate_obj):
    mandate = await mandates_collection.find_one({"mandate_id": mandate_obj["mandate_id"]})
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


async def verify_pending_orders():
    async for order in pending_orders_collection.find({"paid": False}):
        order_id = order["pending_order_id"]
        res = await make_api_request(method = "GET", url = f"{BASE_URL}/orders/{order_id}",
                                     headers = {"Authorization": AUTHORIZATION})
        print(f"Order verification response for {order_id}: {res}")

        status = res.get("txn_detail", {}).get("status", "UNKNOWN")

        if status in ["CHARGED", "AUTO_REFUNDED"]:
            mandate_obj = res.get("mandate", {})
            mandate_obj = {**mandate_obj, "order_id": order_id}
            result = await update_payment_status(mandate_obj)
            print(f"Mandate {order_id} activation result: {result}")
            return result
        else:
            print(f"Payment for order {order_id} failed.")
            return {"success": False, "message": "Payment Failed"}


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    print("Starting Mandate Execution ->", time.ctime())
    loop.run_until_complete(verify_pending_orders())
    print("Completed Mandate Execution ->", time.ctime())
    loop.close()