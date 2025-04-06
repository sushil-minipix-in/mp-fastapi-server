import re
import uuid

from app.db import Mongo
from aiohttp import ClientSession
from bson.objectid import ObjectId
from datetime import date, datetime
from firebase_admin import auth
from pydantic import BaseModel, validator
from typing import Optional, Tuple, Literal, List


db = Mongo()
users_collection = db.users
otp_collection = db.otp
plans_collection = db.plans
orders_collection = db.orders
movies_collection = db.movies
series_collection = db.series
songs_collection = db.songs

Interests = ["Shoppers", "Technology Mobile Enthusiasts",
             "News & Policits/Avid News Readers",
             "Food & Dining / Cooking Enthusiasts",
             "Sports & Fitness / Health & Fitness Buffs"]


class User(BaseModel):
    @classmethod
    async def get(cls, id):
        doc = await users_collection.find_one({'_id': ObjectId(id)})
        if doc:
            doc['_id'] = str(doc['_id'])
            return True, doc
        else:
            return False, None

    @classmethod
    async def get_count(cls, token):
        query = {}
        if token["partner"]:
            query = {"partner": token["id"]}
        count = await users_collection.count_documents(filter=query)
        return count

    @classmethod
    async def update(cls, id: str, fields):
        doc = await users_collection.find_one({"_id": ObjectId(id)})
        if doc:
            return True
        else:
            return False

    @classmethod
    async def cancel_subscription(cls, id: str, reason: str):
        user = await users_collection.find_one({'_id': ObjectId(id)})
        if not user or not reason:
            return False
        query = {'$unset': {'activeSubscription': 1}}
        subscripitons = user.get('subscriptions', [])
        if subscripitons:
            position = len(subscripitons) - 1
            query['$set'] = {
                f"subscriptions.{position}.cancelled": True,
                f"subscriptions.{position}.reason": reason
            }

        result = await users_collection.update_one(
            {'_id': ObjectId(id)},
            {**query}
        )
        return result.acknowledged, user.get('email')

    @classmethod
    async def validate_credentials_by_email(
        cls,
        email,
        password
    ) -> Tuple[bool, str]:
        user = await users_collection.find_one({"email": email})

        if user:
            async with ClientSession() as session:
                payload = {'account': email, 'otp': password}
                async with session.post("http://otp-svc/validate", json=payload) as response:  # noqa: E501
                    if response.status == 200:
                        return True, str(user["_id"])
                    else:
                        return False, None
        else:
            return False, None

    @classmethod
    async def validate_credentials_by_mobile(
        cls,
        mobile,
        password
    ) -> Tuple[bool, str]:
        user = await users_collection.find_one({"mobile": mobile})

        if user:
            async with ClientSession() as session:
                payload = {'account': mobile, 'otp': password}
                async with session.post("http://otp-svc/validate", json=payload) as response:  # noqa: E501
                    if response.status == 200:
                        return True, str(user["_id"])
                    else:
                        return False, None
        else:
            return False, None


class UserRegistrationModel(BaseModel):
    email: Optional[str] = None
    mobile: Optional[str] = None

    @validator('email')
    def email_validator(cls, v):
        if v is None:
            return None
        value = v.strip()
        if len(value) < 5:
            raise ValueError('Email is too short')
        return value

    @validator('mobile')
    def mobile_validator(cls, v):
        if v is None:
            return None
        value = v.strip()
        if len(value) > 15:
            raise ValueError('Mobile needs to be less than 15 characters')
        elif not re.match(r"^\+\d+\.\d+$", value):
            raise ValueError('Mobile not formatted properly')
        return value

    async def save(self):
        doc = None
        if self.email:
            doc = await users_collection.find_one({"email": self.email})

        if self.mobile:
            doc = await users_collection.find_one({"mobile": self.mobile})

        if doc is not None:
            return False

        new_doc = {k: v for k, v in self.__dict__.items() if v}
        new_doc['createdAt'] = str(date.today())
        new_doc['apple_id'] = str(uuid.uuid4())
        profile_id = str(uuid.uuid4())
        new_doc['master_profile'] = profile_id
        new_doc['profiles'] = {}
        new_doc['profiles'][profile_id] = {'name': 'me'}
        user = await users_collection.insert_one(new_doc)
        return user.inserted_id


class UserUpdateModel(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    dob: Optional[date] = None
    gender: Literal[None, 'Others', 'Female', 'Male'] = None
    interests: Optional[List[str]] = None
    allow_email: Optional[bool] = None
    allow_push: Optional[bool] = None
    allow_sms: Optional[bool] = None

    @validator('name')
    def name_validator(cls, value):
        if value is not None:
            value = value.strip()
            if len(value) < 2 or len(value) > 25:
                raise ValueError('Name should be between 2..25 characters')
        return value

    @validator('email')
    def email_validator(cls, value):
        if value is not None:
            value = value.strip()
            if len(value) < 5:
                raise ValueError('Email is too short')
        return value

    @validator('mobile')
    def mobile_validator(cls, value):
        if value is not None:
            value = value.strip()
            if len(value) > 15:
                raise ValueError('Mobile needs to be less than 15 characters')
            elif not re.match(r"^\+\d+$", value):
                raise ValueError('Mobile not formatted properly')
        return value

    @validator('dob')
    def dob_validator(cls, value):
        if value is not None:
            try:
                value = value.isoformat()
            except Exception:
                raise ValueError('Expected iso date format for DOB')
        return value

    async def update(self, id):

        if self.email or self.name or self.mobile:
            doc = {}
            firebase_doc = {}
            if self.email:
                doc = {'email': self.email}
                firebase_doc = {'email': self.email}

            if self.mobile:
                doc = {**doc, 'mobile': self.mobile}
                firebase_doc = {**firebase_doc, 'phone_number': self.mobile}

            if self.name:
                doc = {**doc, 'name': self.name}
                firebase_doc = {**firebase_doc, 'display_name': self.name}

            user = await users_collection.find_one({'_id': ObjectId(id)})
            if doc and user:
                try:
                    auth.update_user(user['firebase_id'], **firebase_doc)
                    await users_collection.update_one(
                        {"_id": ObjectId(id)},
                        {"$set": doc}
                    )
                    return True
                except Exception as e:
                    raise ValueError(str(e))
        else:
            new_doc = {k: v for k, v in self.__dict__.items() if v is not None}

            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": new_doc}
            )
            return True


async def enhance_user(user):
    profiles = {}
    for key, value in user.get('profiles', {}).items():
        if value.get('pin'):
            profiles[key] = {**value, 'locked': True, 'pin': 'xxxx'}
        else:
            profiles[key] = {**value, 'locked': False, 'pin': 'xxxx'}

        if "watchHistory" in value:
            profiles[key]["watchHistory"] = await populate_watch_history(value["watchHistory"])
    user['profiles'] = profiles

    enhanced_subscriptions = []
    subscriptions = user.get('subscriptions', [])
    for subscription in subscriptions:
        end = datetime.strptime(subscription['endDate'], '%Y-%m-%d')
        now = datetime.now()
        subscription['expiresInDays'] = (end - now).days
        order = await orders_collection.find_one({"_id": subscription.get('order_id')})  # noqa: E501
        if order:
            subscription['amount'] = order['amount']
            subscription['currency'] = order.get('currency', '')
            subscription['planId'] = order.get('plan_id', '')
            subscription['subscription_status'] = order.get(
                'subscription_status')
        enhanced_subscriptions.append(subscription)
    user['subscriptions'] = enhanced_subscriptions
    if user.get('activeSubscription') and subscriptions:
        user['activeOrderId'] = subscriptions.pop().get('order_id')
    user['all_interests'] = Interests


class RegisterDevice(BaseModel):
    device_info: str
    device_id: str


async def populate_watch_history(profile_watch_history):
    watch_history = []
    for content in profile_watch_history:
        if content.get('progress', 0) < 97:
            if content.get("type") == "movie" and content.get("id") is not None:
                data = await movies_collection.find_one({"_id": ObjectId(content["id"])})
                if data:
                    content["slugUrl"] = f"movies/{data.get('slug', 'movies')}-{data['_id']}"
                    content['model'] = data['model']
                    watch_history.append(content)
            elif content.get("type") == "series" and content.get("id") is not None:
                data = await series_collection.find_one({"_id": ObjectId(content["id"])})
                if data:
                    content["slugUrl"] = f"series/{data.get('slug', 'series')}-{data['_id']}"
                    content['model'] = data['model']
                    watch_history.append(content)
            elif content.get("type") == "song" and content.get("id") is not None:
                data = await songs_collection.find_one({"_id": ObjectId(content["id"])})
                if data:
                    content['model'] = data['model']
                    watch_history.append(content)
            else:
                watch_history.append(content)
    return watch_history
