from typing import Optional

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import random
import uuid
from datetime import datetime, date
from pytz import timezone


from app.db import Mongo

from .utils import redis_conn, encode_token

from ..models.sms import SMSMessage

router = APIRouter()

db = Mongo()
users_collection = db.users

# Constants
OTP_EXPIRY_TIME = 300  # 5 minutes
MAX_OTP_REQUESTS_PER_HOUR = 100
MAX_FAILED_ATTEMPTS = 100
BLACKLIST_DURATION = 3600  # 1 hour
DEFAULT_PHONE_NUMBER = "+919999999999"
DEFAULT_OTP = "1234"

class OTPRequest(BaseModel):
    phone_number: str


class OTPVerify(BaseModel):
    phone_number: str
    otp: str
    session_token: str = 'static-session-token'
    device_info: Optional[str]
    device_id: Optional[str]
    client_id: Optional[str]


def get_client_info(request: Request):
    """Extracts client details (IP and User-Agent)."""
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")
    return client_ip, user_agent

@router.post("/generate-otp")
async def generate_otp(request: Request, otp_request: OTPRequest):
    phone_number = otp_request.phone_number
    client_ip, user_agent = get_client_info(request)

    # Predefined mobile number, OTP, and session token
    if phone_number == "+919999999999":
        return JSONResponse(
            status_code=200,
            content={"message": "OTP sent", "session_token": "static-session-token"}
        )

    if redis_conn.get(f"blacklist:{phone_number}"):
        return JSONResponse(status_code=403, content={"error": "Too many failed attempts. Try again later."})

    otp_request_count = redis_conn.get(f"otp_requests:{phone_number}") or 0
    if int(otp_request_count) >= MAX_OTP_REQUESTS_PER_HOUR:
        return JSONResponse(status_code=429, content={"error": "Too many OTP requests. Try again later."})

    otp = "".join(random.choices("0123456789", k=4))
    session_token = str(uuid.uuid4())

    redis_conn.setex(
        f"otp:{phone_number}",
        OTP_EXPIRY_TIME,
        f"{otp}:{session_token}:{client_ip}:{user_agent}"
    )

    redis_conn.incr(f"otp_requests:{phone_number}")
    redis_conn.expire(f"otp_requests:{phone_number}", 3600)

    # sms api call
    body, template_id = SMSMessage.get_otp_body(otp)
    await SMSMessage.send_sms(phone_number, body, template_id)
    print(f"Sending OTP {otp} to {phone_number}")

    return JSONResponse(status_code=200, content={"message": "OTP sent", "session_token": session_token})

@router.post("/verify-otp")
async def verify_otp(request: Request, otp_verify: OTPVerify, tasks: BackgroundTasks):
    phone_number = otp_verify.phone_number
    input_otp = otp_verify.otp
    input_session_token = otp_verify.session_token
    client_ip, user_agent = get_client_info(request)

    # Check if the request is for the predefined mobile number
    if phone_number == "+919999999999":
        if input_otp == "1234" and input_session_token == "static-session-token":
            user = await users_collection.find_one({"mobile": phone_number})
            if user:
                print("Existing User")
                return await existing_user_login(otp_verify, user)
            else:
                print("New User")
                return await new_user_login(otp_verify, tasks)
        return JSONResponse(status_code=400, content={"error": "Invalid OTP or session token."})

    # Check if the user is blacklisted
    if redis_conn.get(f"blacklist:{phone_number}"):
        return JSONResponse(status_code=403, content={"error": "Too many failed attempts. Try again later."})

    # Retrieve stored OTP data
    stored_data = redis_conn.get(f"otp:{phone_number}")

    if not stored_data:
        return JSONResponse(status_code=400, content={"error": "OTP expired or invalid."})

    stored_otp, stored_token, stored_ip, stored_user_agent = stored_data.split(":")

    # Validate OTP
    if input_otp != stored_otp:
        # Increase failed attempts count
        failed_attempts = redis_conn.incr(f"failed_attempts:{phone_number}")

        if failed_attempts >= MAX_FAILED_ATTEMPTS:
            redis_conn.setex(f"blacklist:{phone_number}", BLACKLIST_DURATION, "1")
            redis_conn.delete(f"failed_attempts:{phone_number}")
            return JSONResponse(status_code=403, content={"error": "Too many failed attempts. Try again in 1 hour."})

        redis_conn.expire(f"failed_attempts:{phone_number}", 3600)
        return JSONResponse(status_code=400, content={"error": f"Invalid OTP. Attempts left: {MAX_FAILED_ATTEMPTS - failed_attempts}"})

    # Validate session token
    if input_session_token != stored_token:
        return JSONResponse(status_code=400, content={"error": "Invalid session token."})

    # Validate IP and User-Agent
    if client_ip != stored_ip or user_agent != stored_user_agent:
        return JSONResponse(status_code=400, content={"error": "Device mismatch detected."})

    # OTP verified successfully, delete OTP and reset failed attempts
    redis_conn.delete(f"otp:{phone_number}")
    redis_conn.delete(f"failed_attempts:{phone_number}")

    # login the user
    user = await users_collection.find_one({"mobile": phone_number})
    if user:
        print("Existing User")
        return await existing_user_login(otp_verify, user)
    else:
        print("New User")
        return await new_user_login(otp_verify, tasks)


async def existing_user_login(otp_verify: OTPVerify, user):
    device_id = otp_verify.device_id
    device_info = otp_verify.device_info
    client_id = otp_verify.client_id
    devices = {}
    for k, v in user.get('devices', {}).items():
        if v.get('client_id').lower() != 'web':
            devices[k] = v
    if device_id not in devices and client_id.lower() != 'web':
        if len(devices.keys()) >= 5:
            raise HTTPException(
                status_code = 403, detail = "5 devices allowed per account")
        nonce = str(uuid.uuid4())
        if client_id and client_id.lower() != 'web':
            device = {
                'name': device_info,
                'nonce': nonce,
                'registeredOn': str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec = 'seconds')),
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

async def new_user_login(otp_verify: OTPVerify, tasks: BackgroundTasks):
    phone_number = otp_verify.phone_number
    device_id = otp_verify.device_id
    device_info = otp_verify.device_info
    client_id = otp_verify.client_id
    doc = {
        "profiles": {},
        "master_profile": None,
        "createdAt": str(datetime.now(timezone("Asia/Kolkata")).isoformat(timespec = 'seconds')),
        "apple_id": str(uuid.uuid4()),
        "mobile": phone_number
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
    doc['profiles'][profile_id] = { 'name': 'me' }
    doc['master_profile'] = profile_id
    doc['devices'] = devices

    user = await users_collection.insert_one(doc)
    token = encode_token(
        {"id": str(user.inserted_id), "nonce": device_id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "id": str(user.inserted_id)
    }