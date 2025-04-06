import uuid
from aiohttp import ClientSession
from app.config import AppConfig
from app.db import Mongo
from datetime import datetime, date
from pytz import timezone
from bson.objectid import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, Security, BackgroundTasks  # noqa: E501
from pymongo import DESCENDING
from typing import Optional

from .utils import decode_headers, decode_token, get_current_employee, encode_token, redis_conn  # noqa: E501
from ..models.user import User, UserRegistrationModel, UserUpdateModel, enhance_user, RegisterDevice  # noqa: E501
from ..models.user import populate_watch_history
from ..models.profile import ProfileCreateModel, ProfileUpdateModel, Profile, DeleteWatchHistory
from ..models.emails import Messages

config = AppConfig()
key = config.jwt_secret_key

db = Mongo()
users_collection = db.users
orders_collection = db.orders
movies_collection = db.movies
series_collection = db.series

http_not_found_err = 'Not found'
datetime_format = '%Y-%m-%d %H:%M:%S'

router = APIRouter()


@router.get("/{user_id}/tickets")
async def get_user_active_tickets(
    user_id: str,
    token=Depends(decode_token),
    headers: dict = Depends(decode_headers)
):
    if token["id"] == user_id or 'admin' in token:
        success, user = await User.get(user_id)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    if success:
        result = []
        sub_query = headers.get('sub_query', {})
        tickets = get_active_tickets(user, {})
        ids = [ObjectId(i) for i in tickets.keys()]
        query = {'$and': [{'_id': {'$in': ids}}, sub_query]}

        async for movie in movies_collection.find(query):
            movie['_id'] = str(movie['_id'])
            movie = {
                **movie,
                'type': 'movie',
                **tickets.get(movie['_id'], {})
            }
            result.append(movie)
        async for series in series_collection.find(query):
            series['_id'] = str(series['_id'])
            series = {
                **series,
                'type': 'series',
                **tickets.get(series['_id'], {})
            }
            result.append(series)
        return {'tickets': result}
    else:
        raise HTTPException(status_code=404, detail=http_not_found_err)


@router.get("/{id}")
async def get_user(id: str, token=Depends(decode_token)):
    if token["id"] == id or 'admin' in token:
        success, user = await User.get(id)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    if success:
        user['_id'] = str(user['_id'])
        await enhance_user(user)
        return user
    else:
        raise HTTPException(status_code=404, detail=http_not_found_err)


@router.get("")
async def get_users(
    current: int = 1,
    size: int = 10,
    search_text: Optional[str] = None,
    active_subscription: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    token=Security(get_current_employee, scopes=["Users:read"])
):
    users = []
    if search_text:
        query = {
            '$or': [
                {"email": search_text},
                {"mobile": f"+{search_text.replace(' ', '')}"}
            ]
        }
        async for user in users_collection.find(query).limit(size):
            user["_id"] = str(user["_id"])
            users.append(user)

        return {"users": users, "total": len(users)}
    elif active_subscription and start_date and end_date:
        subscription_flag = True if active_subscription == 'true' else False
        query = {
            'activeSubscription': subscription_flag if subscription_flag else {'$exists': False},  # noqa: E501
            'createdAt': {'$gte': datetime.strptime(start_date, datetime_format).isoformat(), '$lte': datetime.strptime(end_date, datetime_format).isoformat()}  # noqa: E501
        }
    elif active_subscription:
        subscription_flag = True if active_subscription == 'true' else False
        query = {
            'activeSubscription': subscription_flag if subscription_flag else {'$exists': False}  # noqa: E501
        }
    elif start_date and end_date:
        query = {
            'createdAt': {'$gte': datetime.strptime(start_date, datetime_format).isoformat(), '$lte': datetime.strptime(end_date, datetime_format).isoformat()}  # noqa: E501
        }
    else:
        query = {}

    skips = size * (current - 1)
    async for user in users_collection.find(query).limit(size).skip(skips).sort([("_id", DESCENDING)]):
        user["_id"] = str(user["_id"])
        users.append(user)
    count = await users_collection.count_documents(query)

    return {"users": users, "total": count}


@router.patch("/{id}")
async def update_user(
    id: str,
    user: UserUpdateModel,
    token=Depends(decode_token)
):
    if token["id"] == id:
        try:
            success = await user.update(id)
            return {"success": success}

        except Exception as e:
            if str(e) == 'The user with the provided phone number already exists (PHONE_NUMBER_EXISTS).':
                raise HTTPException(
                    status_code=400, detail="Mobile already exists")
            if str(e) == 'The user with the provided email already exists (EMAIL_EXISTS).':
                raise HTTPException(
                    status_code=400,
                    detail="Email already exists"
                )
            else:
                raise HTTPException(status_code=400, detail="Bad Request")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/send_otp")
async def send_otp(account: str, type: str):
    if type not in ['email', 'mobile']:
        raise HTTPException(status_code=400, detail="Bad request")

    user = await users_collection.find_one({type: account})
    if user:
        pass
    else:
        if type == 'email':
            user = UserRegistrationModel(email=account)
        else:
            user = UserRegistrationModel(mobile=account)
        await user.save()

    async with ClientSession() as session:
        payload = {'account': account, 'type': type}
        async with session.post("http://otp-svc/send", json=payload) as response:  # noqa: E501
            if response.status == 201:
                return {"success": True}
            else:
                return {"success": False}


@router.get("/{id}/profiles")
async def get_profiles(id: str, token=Depends(decode_token)):
    if token["id"] == id:
        success, user = await User.get(id)
        if success and 'profiles' in user:
            Profile.mask_pin(user)
            return {'profiles': user['profiles']}
        else:
            raise HTTPException(status_code=404, detail=http_not_found_err)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/{id}/profiles/{profile_id}")
async def get_profile(id: str, profile_id: str, token=Depends(decode_token)):
    if token["id"] == id:
        success, user = await User.get(id)
        if success and 'profiles' in user and profile_id in user['profiles']:
            Profile.mask_pin(user)
            profile = user['profiles'][profile_id]
            if "watchHistory" in profile:
                profile["watchHistory"] = await populate_watch_history(profile["watchHistory"])
            return {'profile': profile}
        else:
            raise HTTPException(status_code=404, detail=http_not_found_err)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{id}/profiles")
async def create_profile(
    id: str,
    profile: ProfileCreateModel,
    token=Depends(decode_token)
):
    if token["id"] == id:
        success, user = await User.get(id)
        if success:
            profiles = len(user.get("profiles", []))
            profile_id = str(uuid.uuid4())
            if profiles <= 5:
                doc = {f"profiles.{profile_id}.{k}": v for k, v in profile.__dict__.items() if v is not None}  # noqa: E501
                await users_collection.update_one(
                    {'_id': ObjectId(id)},
                    {"$set": {**doc}}
                )
                return {"success": True, 'profile_id': profile_id}
            else:
                raise HTTPException(
                    status_code=403, detail="Max limit breached")
        else:
            raise HTTPException(status_code=404, detail=http_not_found_err)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.patch("/{id}/profiles/{profile_id}")
async def update_profile(
    id: str,
    profile_id: str,
    profile: ProfileUpdateModel,
    token=Depends(decode_token)
):
    if token["id"] == id:
        success, user = await User.get(id)
        if success and 'profiles' in user and profile_id in user['profiles']:
            await profile.update(id, profile_id)
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail=http_not_found_err)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.delete("/{id}/profiles/{profile_id}/watchHistory")
async def delete_watch_history(
    id: str,
    profile_id: str,
    profile: DeleteWatchHistory,
    token=Depends(decode_token)
):
    if token["id"] == id:
        try:
            await profile.delete_items(id, profile_id)
            return {"success": True}
        except Exception as e:
            if str(e) in ["list empty", "user not found", "profile not found"]:
                return {"success": False, "message": str(e)}
            else:
                return {"sucess": False, "message": "Bad Request"}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.delete("/{id}/profiles/{profile_id}")
async def delete_profile(id: str, profile_id: str, token=Depends(decode_token)):  # noqa: E501
    if token["id"] == id:
        success, user = await User.get(id)
        if success and 'profiles' in user and profile_id in user['profiles']:
            if user['master_profile'] == profile_id:
                raise HTTPException(
                    status_code=400, detail="Deleting master profile is not allowed")  # noqa: E501
            await users_collection.update_one(
                {'_id': ObjectId(id)},
                {"$unset": {f'profiles.{profile_id}': ""}}
            )
            return {'success': True}
        else:
            raise HTTPException(status_code=404, detail=http_not_found_err)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{id}/profiles/{profile_id}/verify_pin")
async def verify_pin_for_profile(
    id: str,
    profile_id: str,
    pin: str,
    token=Depends(decode_token)
):
    if token['id'] == id:
        verified, child = await Profile.verify_pin(id, profile_id, pin)
        if verified:
            payload = {"id": id, "profile_id": profile_id}
            payload['isChild'] = child
            token = encode_token(payload)
            return {"access_token": token, "token_type": "bearer", **payload}
        else:
            raise HTTPException(
                status_code=403,
                detail="Forbidden - Pin failed"
            )
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{id}/cancel_subscription", status_code=201)
async def cancel_subscription(
    id: str,
    tasks: BackgroundTasks,
    reason: str = Body(..., embed=True),
    token=Security(get_current_employee, scopes=["Users:update"])
):
    result, email = await User.cancel_subscription(id, reason)
    # if result and email:
    #     subject, body = Messages.on_subscription_cancelled_by_admin()
    #     tasks.add_task(Messages.send_ses_email, email, subject, body)
    return {'success': result}


@router.post("/{id}/register_device")
async def register_new_device(
        id: str,
        device: RegisterDevice,
        token=Depends(decode_token)
):
    if token['id'] == id:
        device_info = {'name': device.device_info,
                       'registeredOn': str(date.today())}
        response = await users_collection.update_one(
            {'_id': ObjectId(id)},
            {'$set': {f"devices.{device.device_id}": device_info}}
        )
        return {'success': response.modifiedCount == 1}

    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/{id}/deregister_device")
async def deregister_device(
        id: str,
        device_id: Optional[str],
        all: bool = False,
        token=Depends(decode_token)
):
    if not all and not device_id:
        return HTTPException(status_code=400, detail="Bad request")

    if token['id'] == id:
        result = await de_register_device(id, device_id, all)
        return result
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.delete("/{id}")
async def delete_account(
        id: str,
        token=Depends(decode_token)
):
    if token['id'] == id:
        await users_collection.update_one(
            {'_id': ObjectId(id)},
            {
                '$unset': {
                    'mobile': True,
                    'email': True,
                    'firebase_id': True,
                    'apple_id': True
                },
                '$set': {'deleted': True}
            }
        )
        return {'success': True}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


async def de_register_device(id, device_id, all):
    query = {'_id': ObjectId(id)}
    user = await users_collection.find_one(query)
    devices = user.get('devices', {}) if user else {}
    valid = True if all else device_id in devices
    if not valid:
        return HTTPException(status_code=404, detail="Device not found")

    expired_nonces, valid = await get_expired_nonces(devices, all, user, device_id)

    if not valid:
        return {'success': False}
    if expired_nonces:
        redis_conn.sadd(f"{id}:deregisteredDevices", *expired_nonces)
        redis_conn.expire(f"{id}:deregisteredDevices", 30 * 86400)
    return {'success': len(expired_nonces) != 0}


async def get_expired_nonces(devices, all, user, device_id):
    expired_nonces = []
    if all:
        for device in devices.values():
            if device.get('nonce'):
                expired_nonces.append(device['nonce'])
    else:
        device = user['devices'][device_id]
        if device.get('nonce'):
            expired_nonces = [device['nonce']]

    unset = {"devices": 1} if all else {f"devices.{device_id}": 1}
    response = await users_collection.update_one(
        {'_id': user['_id']},
        {'$unset': unset}
    )
    valid = (response and response.acknowledged)

    return expired_nonces, valid


def get_active_tickets(user, tickets):
    for ticket in user.get('tickets', []):
        try:
            end_time = datetime.strptime(
                ticket['end'], '%Y-%m-%dT%H:%M:%S')
            now = datetime.now()
            if now < end_time:
                tickets[ticket['id']] = {
                    **ticket,
                    'expiresInHrs': (end_time - now) / 3600
                }
        except Exception:
            end_time = datetime.strptime(
                ticket['end'], '%Y-%m-%dT%H:%M:%S%z')
            now = datetime.now(timezone('Asia/Kolkata'))
            if now < end_time:
                tickets[ticket['id']] = {
                    **ticket,
                    'expiresInHrs': (end_time - now) / 3600
                }

    return tickets
