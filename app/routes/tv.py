import random
import string
import uuid

from app.db import Mongo
from bson.objectid import ObjectId
from datetime import datetime, date
from fastapi import APIRouter, Depends, Form, HTTPException
from typing import Optional

from .utils import encode_token, decode_token

db = Mongo()
tokens_collection = db.tokens
users_collection = db.users

router = APIRouter()


@router.post("/generate_token")
async def generate_token(
    device_info: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None)
):
    token = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for _ in range(4))
    doc = {
        'token': token,
        'createdAt': datetime.now()
    }
    if device_info and device_id and client_id:
        doc.update({
            'device_name': device_info,
            'device_id': device_id,
            'client_id': client_id
        })
    await tokens_collection.insert_one(doc)
    return {'token': token}


@router.get("/{token}")
async def fetch_token(token: str):
    token_record = await tokens_collection.find_one({'token': token})

    if 'access_token' in token_record:
        return {
            'access_token': token_record['access_token'],
            'token_type': 'bearer',
            'id': token_record['user_id']
        }
    else:
        return {'success': False}


@router.post("/login")
async def login(token: str = Form(...), jwt=Depends(decode_token)):
    nonce = str(uuid.uuid4())
    user_id = jwt['id']
    user = await users_collection.find_one({'_id': ObjectId(user_id)})
    access_token = encode_token({"id": user_id, "nonce": nonce})
    doc = await tokens_collection.find_one({'token': token})

    if doc and user:
        devices = {}
        for k, v in user.get('devices', {}).items():
            if v.get('client_id').lower() != 'web':
                devices[k] = v
        if len(devices.keys()) >= 5:
            raise HTTPException(
                status_code=403, detail="5 devices allowed per account")
        if "device_id" in doc:
            device = {
                'name': doc.get('device_name'),
                'nonce': nonce,
                'registeredOn': str(date.today()),
                'client_id': doc.get('client_id')
            }
            await users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {f"devices.{doc.get('device_id')}": device}}
            )
        await tokens_collection.update_one(
            {'token': token},
            {'$set': {'access_token': access_token,
                      'user_id': user_id, 'nonce': nonce}}
        )
        return {'success': True}
    else:
        return {'success': False}
