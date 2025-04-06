import bcrypt

from app.db import Mongo
from bson.objectid import ObjectId
from pydantic import BaseModel, validator
from typing import Tuple, Optional

db = Mongo()
admins_collection = db.admins

permissions = {
    'Movies': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Series': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Songs': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Artists': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Media Houses': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Genres': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Languages': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Plans': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Users': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Banners': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Playlists': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Orders': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    },
    'Discounts': {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    }
}


class Permission(BaseModel):
    resource: str
    action: str
    value: bool

    async def save(self, admin_id: str):
        await admins_collection.update_one(
            {'_id': ObjectId(admin_id)},
            {
                '$set': {
                    f"permissions.{self.resource}.{self.action}": self.value
                }
            }
        )


class Admin(BaseModel):
    name: str
    email: str
    password: Optional[str] = None

    @validator('password')
    def password_validator(cls, v):
        value = v.strip()
        if len(value) < 8:
            raise ValueError('Password is too short')
        return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()

    async def save(self, id=None):
        new_doc = {k: v for k, v in self.__dict__.items() if v}
        if id:
            await admins_collection.update_one(
                {'_id': ObjectId(id)},
                {'$set': new_doc}
            )
        else:
            await admins_collection.update_one(
                {'email': self.email},
                {
                    '$set': {
                        **new_doc,
                        'superadmin': False,
                        'permissions': permissions
                    }
                },
                upsert=True
            )

    @classmethod
    async def validate_credentials(cls, email, password) -> Tuple[bool, str]:
        doc = await admins_collection.find_one({"email": email})
        if doc:
            return bcrypt.checkpw(
                password.encode(),
                doc["password"].encode()
            ), str(doc["_id"])
        else:
            return False, None

    @classmethod
    async def get_all(cls, filter):
        admins = []
        if filter:
            async for admin in admins_collection.find({"superadmin": False}):
                admin["_id"] = str(admin["_id"])
                admins.append(admin)
        else:
            async for admin in admins_collection.find({}):
                admin["_id"] = str(admin["_id"])
                admins.append(admin)

        return admins

    @classmethod
    async def get_by_id(cls, id: str):
        admin = await admins_collection.find_one({"_id": ObjectId(id)})
        if admin:
            admin['_id'] = str(admin['_id'])
            return True, admin
        else:
            return False, None

    @classmethod
    async def delete(cls, id: str):
        await admins_collection.delete_one({'_id': ObjectId(id)})
