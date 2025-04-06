import aiohttp
import base64
import firebase_admin
import jwt
import os
import uuid

from app.db import Mongo
from bson.objectid import ObjectId
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from datetime import date, datetime
from pytz import timezone
from fastapi import APIRouter, Form, HTTPException, Request, BackgroundTasks
from firebase_admin import auth, credentials
from typing import Optional

from .utils import encode_token, encode_admin_token, parse_fb_signed_request
from ..models.admin import Admin
from ..models.user import User
from ..models.partner import Partner
from ..models.emails import Messages
from ..models.sms import SMSMessage

db = Mongo()
admins_collection = db.admins
users_collection = db.users
partners_collection = db.partners

if os.path.isfile("firebaseAdmin.json"):
    cred = credentials.Certificate("firebaseAdmin.json")
    firebase_app = firebase_admin.initialize_app(cred)

apple_jwt_aud = ['com.aaonxt.ott']
apple_jwt_iss = 'https://appleid.apple.com'


def ensure_bytes(key):
    if isinstance(key, str):
        key = key.encode('utf-8')
    return key


def decode_value(val):
    decoded = base64.urlsafe_b64decode(ensure_bytes(val) + b'==')
    return int.from_bytes(decoded, 'big')


def rsa_pem_from_jwk(jwk):
    return RSAPublicNumbers(
        n=decode_value(jwk['n']),
        e=decode_value(jwk['e'])
    ).public_key(default_backend()).public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )


router = APIRouter()


@router.post("/token")
async def get_token(
    username: str = Form(...),
    password: str = Form(...),
    client_id: str = Form(...)
):
    if client_id == "admin":
        success, _id = await Admin.validate_credentials(username, password)
    elif client_id == "partner":
        success, _id = await Partner.validate_credentials(username, password)
    elif client_id == "user_email":
        success, _id = await User.validate_credentials_by_email(username, password)  # noqa: E501
    elif client_id == "user_mobile":
        success, _id = await User.validate_credentials_by_mobile(username, password)  # noqa: E501
    else:
        raise HTTPException(status_code=400, detail="Bad Request")

    if success:
        if client_id == "admin":
            admin = await admins_collection.find_one({'_id': ObjectId(_id)})
            token = encode_admin_token({"id": _id, "email": admin["email"]}, admin['superadmin'], admin['permissions'])  # noqa: E501
        elif client_id == "partner":
            partner = await partners_collection.find_one({'_id': ObjectId(_id)})
            token = encode_admin_token({"id": _id, "email": partner["email"]}, False, partner['permissions'], True)  # noqa: E501
        else:
            token = encode_token({"id": _id})
        return {"access_token": token, "token_type": "bearer", "id": _id}
    else:
        raise HTTPException(status_code=401, detail="Incorrect credentials")


@router.post("/firebase")
async def login_with_firebase(
    tasks: BackgroundTasks,
    access_token=Form(...),
    device_info: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None)
):
    decoded_token = auth.verify_id_token(access_token)
    uid = decoded_token['uid']
    user = await users_collection.find_one({'firebase_id': uid})

    if user and user.get('account_suspended', None) is True:
        raise HTTPException(status_code=404, detail="Account does not exist")

    if user:
        return await existing_user_login(device_id, client_id, device_info, user)

    else:
        return await new_user_login(uid, device_id, device_info, client_id, tasks)


@router.post("/apple")
async def login_with_apple(access_token: Optional[str] = Form(None)):
    if access_token:
        async with aiohttp.ClientSession() as session:
            url = 'https://appleid.apple.com/auth/keys'
            async with session.get(url) as response:
                res = await response.json()

                headers = jwt.get_unverified_header(access_token)
                if not headers:
                    raise HTTPException(status_code=400, detail="Bad token")

                if 'kid' in headers:
                    return await apple_login(res, headers, access_token)
                else:
                    raise HTTPException(status_code=400, detail="Bad token")

    else:
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/facebook_ddc")
async def facebook_data_deletion_callback(request: Request):
    form = await request.form()
    data = parse_fb_signed_request(form.get('signed_request'))
    if data and 'user_id' in data:
        result = auth.get_users(
            [auth.ProviderIdentifier('facebook.com', data['user_id'])])
        for user in result.users:
            auth.update_user(user.uid, {'providers_to_delete': 'facebook.com'})
    return {
        'url': "https://beta.minipix.in/user-data-deletion",
        'confirmation_code': data['user_id']
    }


async def existing_user_login(device_id, client_id, device_info, user):
    devices = {}
    for k, v in user.get('devices', {}).items():
        if v.get('client_id').lower() != 'web':
            devices[k] = v
    if device_id not in devices and client_id.lower() != 'web':
        if len(devices.keys()) >= 5:
            raise HTTPException(
                status_code=403, detail="5 devices allowed per account")
        nonce = str(uuid.uuid4())
        if client_id and client_id.lower() != 'web':
            device = {
                'name': device_info,
                'nonce': nonce,
                'registeredOn': str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')),
                'client_id': client_id
            }
            if 'apple_id' not in user:
                await users_collection.update_one(
                    {'_id': user['_id']},
                    {'$set': {
                        f"devices.{device_id}": device,
                        'apple_id': str(uuid.uuid4())
                    }}
                )
            else:
                await users_collection.update_one(
                    {'_id': user['_id']},
                    {'$set': {f"devices.{device_id}": device}}
                )
    else:
        device = devices.get(device_id, {})
        nonce = device.get('nonce')
    token = encode_token({"id": str(user['_id']), "nonce": nonce})
    return {
        "access_token": token,
        "token_type": "bearer",
        "id": str(user['_id'])
    }


async def new_user_login(uid, device_id, device_info, client_id, tasks: BackgroundTasks):
    firebase_user = auth.get_user(uid)
    user_data = {
        'name': firebase_user.display_name if firebase_user.display_name else '',
        'email': firebase_user.email if firebase_user.email else '',
        'mobile': firebase_user.phone_number if firebase_user.phone_number else ''
    }

    old_user = await users_collection.find_one(
        {
            'firebase_id': {'$exists': False},
            '$or': [
                {'email': firebase_user.email if firebase_user.email else 'NaN'},
                {'mobile': firebase_user.phone_number if firebase_user.phone_number else 'NaN'}
            ]
        }
    )

    if old_user:
        return await old_user_login(old_user, uid, device_id, device_info, client_id)

    doc = {
        "firebase_id": uid,
        "profiles": {},
        "master_profile": None,
        "createdAt": str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec='seconds')),
        "apple_id": str(uuid.uuid4()),
        **user_data
    }

    devices = {}
    if device_info and client_id and client_id.lower() != 'web':
        device = {
            'name': device_info,
            'nonce': str(uuid.uuid4()),
            'registeredOn': str(date.today()),
            'client_id': client_id
        }
        devices = {device_id: device}

    profile_id = str(uuid.uuid4())
    doc['profiles'][profile_id] = {
        'name': 'me', 'iconPath': 'https://imagedelivery.net/OcLeJlWAT97u4ZIYGPgNPw/9d83240c-253f-4ace-34f0-f730354cb900/profile'}
    doc['master_profile'] = profile_id
    doc['devices'] = devices

    user = await users_collection.insert_one(doc)
    token = encode_token(
        {"id": str(user.inserted_id), "nonce": device_id})
    if 'email' in doc:
        subject, body = Messages.on_successful_registration(doc)
        tasks.add_task(Messages.send_email, doc["email"], subject, body)
    if "mobile" in doc:
        body = SMSMessage.on_successful_registration()
        tasks.add_task(SMSMessage.send_sms, doc["mobile"], body)
    return {
        "access_token": token,
        "token_type": "bearer",
        "id": str(user.inserted_id)
    }


async def old_user_login(old_user, uid, device_id, device_info, client_id):
    await users_collection.update_one(
        {'_id': old_user['_id']},
        {'$set': {'firebase_id': uid}}
    )

    devices = {}
    for k, v in old_user.get('devices', {}).items():
        if v.get('client_id').lower() != 'web':
            devices[k] = v

    if device_id not in devices and client_id.lower() != 'web':
        if len(devices.keys()) >= 5:
            raise HTTPException(
                status_code=403, detail="5 devices allowed per account")
        nonce = str(uuid.uuid4())
        if client_id and client_id.lower() != 'web':
            device = {
                'name': device_info,
                'nonce': nonce,
                'registeredOn': str(date.today()),
                'client_id': client_id
            }
            if 'apple_id' not in old_user:
                await users_collection.update_one(
                    {'_id': old_user['_id']},
                    {'$set': {
                        f"devices.{device_id}": device,
                        'apple_id': str(uuid.uuid4())
                    }}
                )
            else:
                await users_collection.update_one(
                    {'_id': old_user['_id']},
                    {'$set': {f"devices.{device_id}": device}}
                )
    else:
        device = devices.get(device_id, {})
        nonce = device.get('nonce')
    token = encode_token({"id": str(old_user['_id']), "nonce": nonce})
    return {
        "access_token": token,
        "token_type": "bearer",
        "id": str(old_user['_id'])
    }


async def apple_login(res, headers, access_token):
    public_key = ''
    for key in res['keys']:
        if key['kid'] == headers['kid']:
            public_key = rsa_pem_from_jwk(key)

    decoded = jwt.decode(
        access_token,
        public_key,
        verify=True,
        algorithms=['RS256'],
        audience=apple_jwt_aud,
        issuer=apple_jwt_iss
    )

    user = await users_collection.find_one(
        {'email': decoded['email']}
    )
    if user:
        token = encode_token({"id": str(user['_id'])})
        return {
            "access_token": token,
            "token_type": "bearer",
            "id": str(user['_id'])
        }
    else:
        result = await users_collection.insert_one(
            {'email': decoded['email']}
        )
        token = encode_token({"id": str(result.inserted_id)})
        return {
            "access_token": token,
            "token_type": "bearer",
            "id": str(result.inserted_id)
        }
