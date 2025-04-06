import bcrypt

from app.db import Mongo
from bson.objectid import ObjectId
from pydantic import BaseModel, validator
from typing import Tuple, Optional


db = Mongo()
partners_collection = db.partners

permissions = {
    'Movies': {
        'create': True,
        'read': True,
        'update': True,
        'delete': True
    },
    'Series': {
        'create': True,
        'read': True,
        'update': True,
        'delete': True
    },
    'Songs': {
        'create': True,
        'read': True,
        'update': True,
        'delete': True
    },
    'Artists': {
        'create': True,
        'read': True,
        'update': True,
        'delete': False
    },
    'Media Houses': {
        'create': True,
        'read': True,
        'update': True,
        'delete': False
    },
}


class Partner(BaseModel):
    name: str
    email: str
    password: Optional[str] = None

    @validator('password')
    def password_validator(cls, v):
        value = v.strip()
        if len(value) < 8:
            raise ValueError('Password is too short')
        return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()

    async def save(self):
        new_doc = {k: v for k, v in self.__dict__.items() if v}
        await partners_collection.update_one(
            {'email': self.email},
            {
                '$set': {
                    **new_doc,
                    'permissions': permissions
                }
            },
            upsert=True
        )

    @classmethod
    async def validate_credentials(cls, email, password) -> Tuple[bool, str]:
        doc = await partners_collection.find_one({"email": email})
        if doc:
            return bcrypt.checkpw(
                password.encode(),
                doc["password"].encode()
            ), str(doc["_id"])
        else:
            return False, None

    @classmethod
    async def get_all(cls):
        partners = []
        async for partner in partners_collection.find({}):
            partner["_id"] = str(partner["_id"])
            partners.append(partner)

        return partners

    @classmethod
    async def delete(cls, id: str):
        await partners_collection.delete_one({'_id': ObjectId(id)})
