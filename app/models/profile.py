from app.db import Mongo
from bson.objectid import ObjectId
from pydantic import BaseModel
from typing import Optional, Dict

db = Mongo()
users_collection = db.users

pull = '$pull'
push = '$push'


class ProfileCreateModel(BaseModel):
    name: str
    isChild: Optional[bool] = None
    iconPath: Optional[str] = None
    pin: Optional[int] = None


class Profile(BaseModel):
    pin: int
    profile_id: str

    @classmethod
    async def verify_pin(cls, user_id, profile_id, pin):
        user = await users_collection.find_one({'_id': ObjectId(user_id)})
        if user and 'profiles' in user:
            profile = user['profiles'][profile_id]
            correct_pin = profile.get('pin')
            if correct_pin:
                return int(pin) == correct_pin, profile.get('isChild')
            else:
                return True, profile.get('isChild')
        return False, False

    @classmethod
    def mask_pin(cls, user):
        profiles = {}
        for key, profile in user.get('profiles', {}).items():
            if profile.get('pin'):
                profiles[key] = {**profile, 'locked': True, 'pin': 'xxxx'}
            else:
                profiles[key] = {**profile, 'locked': False, 'pin': 'xxxx'}
        user['profiles'] = profiles


class DeleteWatchHistory(BaseModel):
    remove_watched: list = []

    async def delete_items(self, id, profile_id):
        items = self.remove_watched
        if len(items) == 0:
            raise ValueError("list empty")
        user = await users_collection.find_one({"_id": ObjectId(id)})
        if not user:
            raise ValueError("user not found")

        profiles = user.get("profiles", {})
        if profile_id not in profiles:
            raise ValueError("profile not found")

        new_watch_history = []
        for item in profiles[profile_id]["watchHistory"]:
            if item.get("id") and item["id"] not in items:
                new_watch_history.append(item)

        await users_collection.update_one(
            {"_id": ObjectId(id)},
            {
                "$set": {
                    f"profiles.{profile_id}.watchHistory": new_watch_history
                }
            }
        )


class ProfileUpdateModel(BaseModel):
    name: Optional[str] = None
    watched: Optional[Dict] = None
    wishToWatch: Optional[Dict] = None
    removeWatched: Optional[Dict] = None
    removeWishToWatch: Optional[Dict] = None
    likes: Optional[Dict] = None
    dislikes: Optional[Dict] = None
    removeLiked: Optional[Dict] = None
    removeDisliked: Optional[Dict] = None
    iconPath: Optional[str] = None
    pin: Optional[int] = None
    isChild: Optional[bool] = None
    drop_lock: Optional[bool] = None
    master_profile: Optional[str] = None

    async def update(self, id, profile_id):
        new_doc = {k: v for k, v in self.__dict__.items() if v}

        doc = {}

        if self.master_profile and self.pin:
            await users_collection.update_one(
                {"_id": ObjectId(id), 'master_profile': self.master_profile},
                {"$set": {f'profiles.{profile_id}.pin': self.pin}}
            )
            return

        if self.drop_lock is True and self.pin:
            await users_collection.update_one(
                {"_id": ObjectId(id), f'profiles.{profile_id}.pin': self.pin},
                {"$unset": {f'profiles.{profile_id}.pin': ""}}
            )
            return

        doc[f"profiles.{profile_id}.name"] = new_doc.get('name', None)
        doc[f"profiles.{profile_id}.iconPath"] = new_doc.get('iconPath', None)
        doc[f"profiles.{profile_id}.pin"] = new_doc.get('pin', None)
        if 'isChild' in new_doc:
            doc[f"profiles.{profile_id}.isChild"] = new_doc['isChild']
        doc = {k: v for k, v in doc.items() if v is not None}
        if doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": {**doc}}
            )

        if "watched" in new_doc:
            if "type" not in new_doc["watched"] or "id" not in new_doc["watched"] or "progress" not in new_doc["watched"] or "time" not in new_doc["watched"]:
                raise ValueError("Required Parameters Missing")
            user = await users_collection.find_one({"_id": ObjectId(id)})
            profile = user.get("profiles", {})[profile_id]
            watch_history = profile.get("watchHistory", [])
            new_watch_history = []
            for content in watch_history:
                if content["id"] != new_doc["watched"]["id"]:
                    new_watch_history.append(content)
            new_watch_history.append(new_doc["watched"])
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {
                    "$set": {f"profiles.{profile_id}.watchHistory": new_watch_history}
                }
            )

            return

        if "removeWatched" in new_doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {pull: {f'profiles.{profile_id}.watchHistory':
                        {'id': new_doc['removeWatched']['id']}}}
            )
            return

        if "wishToWatch" in new_doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {pull: {
                    f'profiles.{profile_id}.wishList': {'_id': new_doc['wishToWatch']['_id']}}}  # noqa: E501
            )

            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {push: {f'profiles.{profile_id}.wishList': new_doc['wishToWatch']}})  # noqa: E501
            return

        if "removeWishToWatch" in new_doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {pull: {f'profiles.{profile_id}.wishList':
                        {'_id': new_doc['removeWishToWatch']['_id']}}}
            )
            return

        if "likes" in new_doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {pull: {f'profiles.{profile_id}.dislikes': {'_id': new_doc['likes']['_id']}},  # noqa: E501
                 push: {f'profiles.{profile_id}.likes': new_doc['likes']}}
            )
            return

        if "removeLiked" in new_doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {pull: {f'profiles.{profile_id}.likes':
                        {'_id': new_doc['removeLiked']['_id']}}}
            )
            return

        if "dislikes" in new_doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {pull: {f'profiles.{profile_id}.likes': {'_id': new_doc['dislikes']['_id']}},  # noqa: E501
                 push: {f'profiles.{profile_id}.dislikes': new_doc['dislikes']}}  # noqa: E501
            )
            return

        if "removeDisliked" in new_doc:
            await users_collection.update_one(
                {"_id": ObjectId(id)},
                {pull: {
                    f'profiles.{profile_id}.dislikes': {'_id': new_doc['removeDisliked']['_id']}}}  # noqa: E501
            )
