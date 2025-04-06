import jwt
import razorpay
import redis
import base64
import hmac
import hashlib
import json
import secrets

from aiohttp import ClientSession
from app.config import AppConfig
from app.db import Mongo
from bson import ObjectId
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from minio import Minio
from datetime import datetime

import aiohttp
import certifi
import ssl


config = AppConfig()
key = config.jwt_secret_key
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="oauth2/token")
rzrpy_key = config.razorpay_key
rzrpy_secret = config.razorpay_secret
firebase_api_key = config.firebase_api_key
uri_prefix = config.domain_uri_prefix
apn = config.android_package_name
ibi = config.ios_bundle_id
isi = config.ios_app_store_id

set_is_subset = '$setIsSubset'
expr = '$expr'

rzrpy_client = razorpay.Client(auth=(rzrpy_key, rzrpy_secret))
s3_url = config.s3_url
access_key = config.s3_access_key
secret_key = config.s3_secret_key
redis_host = config.redis_host
redis_port = config.redis_port

db = Mongo()
movies_collection = db.movies
series_collection = db.series
playlists_collection = db.playlists
promos_collection = db.promos
users_collection = db.users


minio_client = Minio(
    s3_url,
    access_key=access_key,
    secret_key=secret_key,
    secure=True
)

redis_conn = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)  # noqa: E501


def encode_token(details):
    return jwt.encode(details, key, algorithm="HS256")


def decode_token(token: str = Depends(oauth2_scheme)):
    try:
        token = jwt.decode(token, key, algorithms=["HS256"])
        user_id = token['id']
        nonce = token.get('nonce')

        if redis_conn.exists(f"{user_id}:deregisteredDevices"):
            nonces = redis_conn.smembers(f"{user_id}:deregisteredDevices")
            if nonce in nonces:
                raise HTTPException(status_code=401, detail="Not Authorized")

        return token
    except redis.RedisError:
        raise HTTPException(
            status_code=500, detail="Forbidden - Network Error")
    except jwt.exceptions.DecodeError as e:
        print(str(e))
        raise HTTPException(status_code=403, detail="Forbidden - Token Error")


# EU country codes from
# https://abbreviations.yourdictionary.com/articles/list-of-europe-country-codes.html
euro_cfcodes = ['VA', 'GB', 'UA', 'TR', 'CH', 'RS', 'SM', 'RU', 'NO', 'ME',
                'MC', 'MD', 'MK', 'LI', 'XK', 'IM', 'IS', 'GI', 'GE', 'FO',
                'BA', 'BY', 'AM', 'AD', 'AL', 'SE', 'ES', 'SI', 'SK', 'RO',
                'PT', 'PL', 'NL', 'MT', 'LU', 'LT', 'LV', 'IT', 'IE', 'HU',
                'GR', 'DE', 'FR', 'FI', 'EE', 'DK', 'CZ', 'CY', 'HR', 'BG',
                'BE', 'AT']
country_currency_map = {'MU': 'MUR', 'IN': 'INR',
                        'NP': 'NPR', 'AE': 'AED', 'SG': 'SGD'}
currency_symbol_map = {"INR": '₹', "USD": '$', "MUR": "\u20a8",
                       "NPR": 'रू', "AED": 'د.إ', "SGD": 'S$', "EUR": '€'
                       }


def decode_headers(request: Request):
    result = {'child': False, 'currency': 'INR', 'sub_query': {}}
    cf_country = request.headers.get('cf-ipcountry', None)
    x_profile_token = request.headers.get('x-profile-token', None)
    if x_profile_token:
        token = jwt.decode(x_profile_token, key, algorithms=["HS256"])
        result["profile_id"] = token.get("profile_id", None)
        if token['isChild']:
            result['child'] = True
            result['sub_query'] = {'maturity': 'U'}
    if cf_country:
        if cf_country in country_currency_map:
            result['currency'] = country_currency_map.get(cf_country)
        elif cf_country in euro_cfcodes:
            result['currency'] = 'EUR'
        else:
            result['currency'] = 'USD'
    result['currency_symbol'] = currency_symbol_map[result['currency']]
    return result


def encode_admin_token(details, superadmin=False, permissions={}, partner=False):  # noqa: E501
    details["partner"] = partner
    details["admin"] = True
    details["superadmin"] = superadmin
    scopes = []
    if not superadmin:
        for resource in permissions.keys():
            for (action, value) in permissions[resource].items():
                if value:
                    scopes.append(f"{resource}:{action}")
        details["scopes"] = scopes

    return jwt.encode(details, key, algorithm="HS256")


def decode_admin_token(token: str = Depends(oauth2_scheme)):
    details = jwt.decode(token, key, algorithms=["HS256"])
    if "admin" not in details:
        raise HTTPException(status_code=403, detail="Forbidden")

    return details

def decode_jwt_token(token):
    try:
        token = token.split(" ")[-1]
        return jwt.decode(token, key, algorithms=["HS256"])
    except Exception as _:
        return False

def get_current_employee(
    security_scopes: SecurityScopes,
    token=Depends(decode_admin_token)
):
    if token['superadmin']:
        return token

    scopes = token.get("scopes", [])

    for scope in security_scopes.scopes:
        if scope not in scopes:
            raise HTTPException(status_code=403, detail="Forbidden")
    return token


def remove_object(url: str):
    [_, _, _, bucket, path] = url.split('/')
    minio_client.remove_object(bucket, path)


async def send_update(
    content_title,
    content_type,
    action,
    employee,
    availability=None
):
    if availability:
        payload = {
            'text': f"{employee} {action} {content_type} {availability} {content_title}"
        }
    else:
        payload = {
            'text': f"{employee} {action} {content_type} {content_title}"
        }
    async with ClientSession() as session:
        await session.post(
            "https://hooks.slack.com/services/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",  # noqa: E501
            json=payload
        )


def get_similar_query(content, sub_query):
    genre = content.get('genre', [])
    actors = content.get('actors', [])
    language = content.get('language', [])

    genre_query = {expr: {set_is_subset: ["$genre", genre]}}
    language_query = {expr: {set_is_subset: ["$language", language]}}
    actors_query = {expr: {set_is_subset: ["$actors", actors]}}
    return {
        '$and':
            [
                sub_query,
                {'_id': {'$ne': ObjectId(content['_id'])}},
                {
                    '$or': [actors_query, genre_query, language_query],
                    'availability': 'perpetual'
                }
            ]
    }


def pop_random(content_list):
    content = secrets.choice(content_list)
    content_list.remove(content)
    return content


async def create_rp_plan(plan, plans_collection):
    rp_plans = plan.get('rpPlans', {})

    for cur, price in plan.get('price', {}).items():
        key = f"{cur}_{price}"
        if key in rp_plans:
            continue
        try:
            result = rzrpy_client.plan.create({
                'period': 'daily',
                'interval': plan['duration'],
                'item': {
                    'name': f"{plan['name']} {cur} {price}",
                    'amount': price * 100,
                    'currency': cur,
                    'description': plan.get('description', '')
                },
                'notes': {'unique_key': key}
            })

            rp_plans[key] = result['id']
        except razorpay.errors.BadRequestError:
            pass
    await plans_collection.update_one(
        {'_id': ObjectId(plan['_id'])},
        {
            '$set': {
                'rpPlans': rp_plans
            }
        }
    )


def parse_fb_signed_request(signed_request):
    encoded_sig, payload = signed_request.split('.', 2)
    secret = config.fb_app_secret

    encoded_sig = encoded_sig.encode('ascii')
    payload = payload.encode('ascii')
    encoded_sig += "=" * ((4 - len(encoded_sig) % 4) % 4)
    payload += "=" * ((4 - len(payload) % 4) % 4)

    sig = base64.urlsafe_b64decode(encoded_sig)
    data = json.loads(base64.urlsafe_b64decode(payload))

    # check the signature
    expected_sig = hmac.new(secret, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, sig):
        return None
    else:
        return data


async def generate_dynamic_link(content, content_type):
    content['_id'] = str(content['_id'])
    payload = {
        "dynamicLinkInfo": {
            "domainUriPrefix": uri_prefix,
            "link": f"https://minipix.in/{content_type}/{content.get('slug', content_type)}-{content.get('_id')}",
            "androidInfo": {
                "androidPackageName": apn
            },
            "iosInfo": {
                "iosBundleId": ibi,
                "iosAppStoreId": isi
            },
            "navigationInfo": {
                "enableForcedRedirect": 1,
            },
            "socialMetaTagInfo": {
                "socialTitle": content.get('title'),
                "socialDescription": content.get('description'),
                "socialImageLink": content.get('cardImage')
            }
        },
        "suffix": {
            "option": "SHORT"
        }
    }

    async with ClientSession() as session:
        async with session.post(
            f"https://firebasedynamiclinks.googleapis.com/v1/shortLinks?key={firebase_api_key}",  # noqa: E501
            json=payload
        ) as response:
            res = await response.json()
            return res["shortLink"]


async def insert_share_link(id, content_type):
    collection = movies_collection if content_type == 'movies' else series_collection
    content = await collection.find_one({"_id": ObjectId(id)})

    if content:
        share_link = await generate_dynamic_link(content, content_type)
        await collection.update_one({"_id": ObjectId(id)}, {"$set": {"shareLink": share_link}})


async def verify_update_content(id, content_type):

    query = {'$or': [{'content': {'$all': [id]}},
                     {'content': {'$all': [f"{content_type}|{id}"]}}]}

    playlists, promos = [], []
    async for playlist in playlists_collection.find(query):
        if playlist:
            playlists.append(playlist['name'])

    async for promo in promos_collection.find({f'{content_type}': id}):
        if promo:
            promos.append(promo['page'])

    if len(playlists) > 0 or len(promos) > 0:
        raise HTTPException(
            status_code=422,
            detail={
                'promos': promos,
                'playlists': playlists
            }
        )


async def verify_active_tickets(id, content_type):
    async for user in users_collection.find({"tickets": {"$exists": True}}):
        tickets = user["tickets"]
        for ticket in tickets:
            end_time = datetime.strptime(
                ticket['end'], '%Y-%m-%dT%H:%M:%S')
            if ticket["id"] == id and (datetime.now() < end_time):
                raise HTTPException(
                    status_code=406, detail={"error": "ticket", "message": f"This {content_type} has active ticket users"})


def construct_social_preview_image(url: str):
    try:
        split_url = url.split("/")
        split_url[5] = "width=1200,height=630"
        social_preview_image_url = "/".join(split_url)
        return social_preview_image_url
    except Exception:
        return url


async def get_history(token, profile_id, content_id, content_type):
    try:
        user = await users_collection.find_one({"_id": ObjectId(token["id"])})
        if user:
            profiles = user.get("profiles", {})
            if profiles and profile_id in profiles:
                for data in profiles[profile_id]["watchHistory"]:
                    if content_id == data["id"]:
                        set_value = data["progress"] <= 95
                        result = {
                            "progress": data["progress"] if set_value else 0,
                            "time": data["time"] if set_value else 0,
                        }
                        if content_type == "series":
                            return {
                                **result,
                                "season": data["season"],
                                "episode": data["episode"],
                            }
                        return result
            else:
                return {
                    "progress": 0,
                    "time": 0
                }
    except Exception as e:
        # print(e)
        return {
            "progress": 0,
            "time": 0,
            "season": 0,
            "episode": 0
        }

async def make_api_request(
        method: str,
        url: str,
        headers: dict = None,
        payload: dict = None,
        params: dict = None,
        ssl_verify: bool = True,
):
    """
    Utility function to make API requests using aiohttp.ClientSession.

    Args:
        method (str): HTTP method (GET, POST, PUT, DELETE, etc.).
        url (str): API endpoint URL.
        headers (dict, optional): Request headers.
        payload (dict, optional): Request body (for POST, PUT, etc.).
        params (dict, optional): Query parameters for the URL.
        ssl_verify (bool, optional): Whether to verify SSL certificates. Defaults to True.

    Returns:
        dict: Response JSON if available.
        str: Response text if JSON is not available.
    """
    try:
        # Create SSL context
        ssl_context = None
        if ssl_verify:
            ssl_context = ssl.create_default_context(cafile=certifi.where())

        async with aiohttp.ClientSession() as session:
            async with session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=payload,
                    params=params,
                    ssl=ssl_context
            ) as response:
                res = await response.json()
                # print(res)
                # response.raise_for_status()  # Raise exception for HTTP errors
                try:
                    return await response.json()  # Attempt to return JSON response
                except aiohttp.ContentTypeError:
                    return await response.text()  # Return raw text if JSON isn't available
    except aiohttp.ClientError as e:
        print(f"Client error occurred: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error occurred: {e}")
        raise
