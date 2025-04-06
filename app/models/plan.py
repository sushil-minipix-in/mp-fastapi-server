from app.db import Mongo
from bson.objectid import ObjectId
from datetime import date
from pydantic import BaseModel
from typing import List, Optional, Dict

db = Mongo()
plans_collection = db.plans
apple_plans_collection = db.applePlans
android_plans_collection = db.androidPlans


class PurchaseDetails(BaseModel):
    purchaseDate: date
    quantity: int
    description: str


class Plan(BaseModel):
    name: str
    hindiName: Optional[str]
    price: Dict[str, int]
    duration: int
    features: List[str]
    hindiFeatures: Optional[List[str]]
    reseller: Optional[str] = None
    resellerPrice: Optional[int] = None
    resellerCredits: Optional[int] = None
    resellerPurchaseHistory: Optional[List[PurchaseDetails]] = None
    suspended: Optional[bool] = False
    planType: Optional[str] = 'web'

    async def save(self, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v is not None}
        if id:
            await plans_collection.update_one({'_id': ObjectId(id)}, {'$set': doc})  # noqa: E501
            return id
        else:
            plan = await plans_collection.insert_one(doc)
            return plan.inserted_id

    @classmethod
    async def update_status(cls, id, suspended):
        await plans_collection.update_one({'_id': ObjectId(id)}, {'$set': {'suspended': suspended}})  # noqa: E501


class ApplePlan(BaseModel):
    planId: str
    planType: str
    price: int
    duration: int
    description: str
    suspended: Optional[bool] = False

    async def save(self, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v is not None}

        if id:
            await apple_plans_collection.update_one({'_id': ObjectId(id)}, {'$set': doc})
        else:
            await apple_plans_collection.insert_one(doc)

        return True

    @classmethod
    async def update_status(cls, id, suspended):
        await apple_plans_collection.update_one({'_id': ObjectId(id)}, {'$set': {'suspended': suspended}})


class AndroidPlan(BaseModel):
    planId: str
    planType: str
    price: int
    duration: int
    suspended: Optional[bool] = False

    async def save(self, id=None):
        doc = {k: v for k, v in self.__dict__.items() if v is not None}

        if id:
            await android_plans_collection.update_one({'_id': ObjectId(id)}, {'$set': doc})
        else:
            await android_plans_collection.insert_one(doc)

        return True

    @classmethod
    async def update_status(cls, id, suspended):
        await android_plans_collection.update_one({'_id': ObjectId(id)}, {'$set': {'suspended': suspended}})