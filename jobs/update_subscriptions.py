import asyncio
import datetime
import motor.motor_asyncio

from app.config import AppConfig
from app.models.emails import Messages
from app.models.sms import SMSMessage

config = AppConfig()
mongo_uri = config.mongo_uri
db_name = config.db_name

client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)

db = client[db_name]
users_collection = db.users


async def update_subscriptions():
    expired_subscriptions = 0
    try:
        async for user in users_collection.find({'activeSubscription': True}):
            today = datetime.date.today()
            subscriptions = user.get("subscriptions", [])
            if subscriptions:
                end_date = user['subscriptions'][-1]['endDate']
                target = datetime.date.fromisoformat(end_date)
                if (today - target).total_seconds() > 0:
                    await users_collection.update_one(
                        {'_id': user['_id']},
                        {'$unset': {'activeSubscription': ''}}
                    )
                    expired_subscriptions += 1
                    await send_alert(user)
    except Exception as _:
        print(f"Error Updating user: {str(user['_id'])}")
    print("Expired subscriptions: ", expired_subscriptions)


async def send_alert(user):
    try:
        if 'email' in user:
            subject, body = Messages.on_subscription_expired(user)
            await Messages.send_email(user["email"], subject, body)
        if "mobile" in user:
            body = SMSMessage.on_subscription_expired()
            await SMSMessage.send_sms(user["mobile"], body)
    except Exception:
        pass


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(update_subscriptions())
    loop.close()
