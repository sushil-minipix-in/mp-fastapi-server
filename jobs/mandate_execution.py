import asyncio
import time
import nanoid
import base64
import motor.motor_asyncio
from datetime import datetime, timedelta

from app.config import AppConfig
from app.routes.utils import make_api_request
from pytz import timezone

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

current_date = datetime.now().date()
MAX_RETRIES = 3  # Maximum retries before marking mandate as inactive


def should_execute_mandate(mandate, retry_count) -> bool:
    end_date = datetime.strptime(mandate["endDate"], "%Y-%m-%d").date()
    execution_date = end_date - timedelta(days = 1) + timedelta(days = retry_count)
    print(f"Checking execution for mandate {mandate['mandate_id']} - Attempt {retry_count + 1}")
    return current_date == execution_date


async def verify_pending_order_if_present(mandate) -> bool:
    """
    Check if a pending order exists and if 25 hours have passed since it was triggered.
    If a pending order exists and 25 hours have not passed, return True (skip execution).
    Otherwise, return False (allow execution).
    """
    pending_order_id = mandate.get("pending_order_id")
    triggered_at = mandate.get("triggered_at")

    if not pending_order_id or not triggered_at:
        return False  # No pending order, proceed with execution

    try:
        triggered_time = datetime.fromisoformat(triggered_at)
        time_elapsed = datetime.now(timezone("Asia/Kolkata")) - triggered_time

        if time_elapsed.total_seconds() < 25 * 3600:  # 25 hours
            print(f"Skipping execution for mandate {mandate['mandate_id']} due to active pending order.")
            return True  # Skip execution

    except Exception as e:
        print(f"Error processing pending order verification: {e}")

    return False

async def execute_mandates():
    count = 0
    async for mandate in mandates_collection.find({"status": "ACTIVE"}):
        end_date = datetime.strptime(mandate["endDate"], "%Y-%m-%d").date()
        retry_count = mandate.get("retry_count", 0)

        if current_date < (end_date - timedelta(days = 1)):
            print(f"Mandate {mandate['mandate_id']} is not yet eligible for execution.")
            continue

        if should_execute_mandate(mandate, retry_count):
            should_skip = await verify_pending_order_if_present(mandate)
            if not should_skip:
                try:
                    execution_payload = {
                        "merchant_id": "minipix",
                        "mandate_id": mandate["mandate_id"],
                        "order.customer_id": mandate["customer_id"],
                        "order.amount": str(float(mandate["total_price"])),
                        "order.order_id": f"jp{nanoid.generate(ALPHANUMERIC_CHARACTERS, 18)}",
                        "order.currency": "INR",
                        "format": "json"
                        }
                    res = await make_api_request(method = "POST", url = f"{BASE_URL}/txns", payload = execution_payload,
                                                 headers = {"Authorization": AUTHORIZATION})
                    print(f"Mandate {mandate['mandate_id']} execution response: {res}")

                    doc = mandate
                    del doc["_id"]
                    await pending_orders_collection.insert_one(
                        {
                            **mandate,
                            "pending_order_id": res["order_id"],
                            "paid": False,
                            "triggered_at": str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec = 'seconds'))
                            }
                        )
                    await mandates_collection.update_one(
                        {"mandate_id": mandate["mandate_id"]},
                        {
                            "$set": {
                                "paid": False,
                                "retry_count": retry_count + 1,
                                "pending_order_id": res["order_id"],
                                "triggered_at": str(
                                    datetime.now(timezone("Asia/Kolkata")).isoformat(timespec = 'seconds'))
                                }
                            }
                        )
                    print(f"Executed mandate {mandate['mandate_id']} - Retry {retry_count + 1}")
                    count += 1
                except Exception as e:
                    print(f"Error executing mandate {mandate['mandate_id']}: {str(e)}")
                else:
                    print(f"Skipped because a pending order still needs to be verified: {mandate['mandate_id']}")
        else:
            if retry_count >= MAX_RETRIES:
                await mandates_collection.update_one(
                    {"mandate_id": mandate["mandate_id"]},
                    {"$set": {"status": "INACTIVE", "message": "Unpaid after 3 retries"}}
                    )
                await users_collection.update_one({"_id": mandate["user"]}, {"$set": {"activeSubscription": False}})
                print(f"Mandate {mandate['mandate_id']} marked as INACTIVE after {MAX_RETRIES} failed attempts.")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    print("Starting Mandate Execution ->", time.ctime())
    loop.run_until_complete(execute_mandates())
    print("Completed Mandate Execution ->", time.ctime())
    loop.close()
