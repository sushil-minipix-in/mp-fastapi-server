import uuid

from app.db import Mongo
from bson.objectid import ObjectId
from datetime import date, timedelta
from pydantic import BaseModel
from typing import Optional

db = Mongo()
resellers_collection = db.resellers
users_collection = db.users
plans_collection = db.plans
orders_collection = db.orders


class Reseller(BaseModel):
    name: str
    company: str
    email: str
    phone: str
    gstin: str
    city: str
    state: str
    active: bool = True

    async def save(self, id=None):
        if id:
            doc = {k: v for k, v in self.__dict__.items() if v is not None}
            result = await resellers_collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": doc}
            )
        else:
            doc = {k: v for k, v in self.__dict__.items() if v is not None}
            doc["apiKey"] = str(uuid.uuid4())

            result = await resellers_collection.insert_one(doc)

        return True if result.acknowledged else False

    @classmethod
    async def delete(cls, id: str):
        result = await resellers_collection.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"active": False}}
        )

        return True if result.acknowledged else False


class Subscription(BaseModel):
    name: str
    email: Optional[str] = None
    mobile: Optional[str] = None
    plan: str

    async def save(self, reseller_id: str, reseller_name: str):
        doc = {k: v for k, v in self.__dict__.items() if v}

        if doc["email"]:
            user = await users_collection.find_one({"email": doc["email"]})
        elif doc["mobile"]:
            user = await users_collection.find_one({"mobile": doc["mobile"]})
        else:
            return False, "Email or Mobile is mandatory"

        plan = await plans_collection.find_one({"_id": ObjectId(doc["plan"])})
        if not plan or plan["reseller"] != reseller_id:
            return False, "Plan not found for reseller"
        elif plan["resellerCredits"] == 0:
            return False, "Reseller credits exhausted for this plan"
        else:
            await plans_collection.update_one(
                {"_id": plan["_id"]},
                {"$inc": {"resellerCredits": -1}}
            )

        if not user:
            doc['createdAt'] = str(date.today())
            subscription = {
                "name": plan["name"],
                "startDate": str(date.today()),
                "endDate": str(date.today() + timedelta(days=plan["duration"]))
            }
            doc["activeSubscription"] = True
            doc["subscriptions"] = [subscription]

            result = await users_collection.insert_one(doc)
            if result.inserted_id:
                order = {
                    "_id": f"reseller_{str(uuid.uuid4())}",
                    "user": result.inserted_id,
                    "amount": plan["price"],
                    "plan": plan["name"],
                    "reseller": reseller_id,
                    "duration": plan["duration"],
                    "paid": True,
                    "thirdParty": reseller_name
                }
                await orders_collection.insert_one(order)
                return True, None
            else:
                return False, "Unable to create user"

        if "activeSubscription" in user and user["activeSubscription"]:
            current_subscription = user["subscriptions"].pop()
            new_start_date = date.fromisoformat(current_subscription["endDate"]) + timedelta(days=1)  # noqa: E501
            subscription = {
                "name": plan["name"],
                "startDate": str(new_start_date),
                "endDate": str(new_start_date + timedelta(days=plan["duration"]))
            }
        else:
            subscription = {
                "name": plan["name"],
                "startDate": str(date.today()),
                "endDate": str(date.today() + timedelta(days=plan["duration"]))
            }

        order = {
            "user": user["_id"],
            "amount": plan["price"],
            "plan": plan["name"],
            "reseller": reseller_id,
            "duration": plan["duration"],
            "paid": True,
            "pg": "reseller",
            "thirdParty": reseller_name
        }

        await orders_collection.insert_one(order)
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"activeSubscription": True}, "$push": {"subscriptions": subscription}}  # noqa: E501
        )
        return True, None
