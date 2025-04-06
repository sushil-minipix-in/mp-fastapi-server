import base64
import json
import hashlib
import nanoid

from app.config import AppConfig
from app.db import Mongo

from datetime import date, timedelta, datetime
from pytz import timezone
from aiohttp import ClientSession
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from fastapi import HTTPException, Security, Header, Body
from bson.objectid import ObjectId
from uuid import uuid4

from .utils import decode_token, get_current_employee
from ..models.order import Order, CaptureOrder, OrderTrackingParams
from ..models.emails import Messages

db = Mongo()
users_collection = db.users
plans_collection = db.plans
orders_collection = db.orders
discounts_collection = db.discounts

router = APIRouter()
config = AppConfig()

phonepe_api_callback_url = config.phonepe_callback_url
merchant_id = config.phonepe_merchant_id




def get_headers(x_verify, merchant_id=False, callback=False, redirect=False):
    header = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-Verify": x_verify
    }
    if callback:
        header['X-CALLBACK-URL'] = phonepe_api_callback_url
        header['X-CALLBACK-MODE'] = 'POST'
    if merchant_id:
        header['X-MERCHANT-ID'] = merchant_id

    return header
