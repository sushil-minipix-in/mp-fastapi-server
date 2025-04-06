import uuid

from aiohttp import ClientSession, FormData
from app.config import AppConfig
from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, BackgroundTasks, Request  # noqa: E501
from minio import Minio
from minio.error import S3Error

from .utils import decode_admin_token, minio_client


db = Mongo()
movies_collection = db.movies
series_collection = db.series
songs_collection = db.songs

config = AppConfig()
s3_url = config.s3_url
cdn_url = config.cdn_url
access_key = config.s3_access_key
secret_key = config.s3_secret_key
cf_account_id = config.cf_account_id
cf_api_token = config.cf_api_token
cf_account_hash = config.cf_account_hash
img_prefix = config.db_name
error_message = "Internal Server Error"


router = APIRouter()


@router.post("")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    token=Depends(decode_admin_token)
):
    size = request.headers['content-length']
    if int(size) / 1024 / 1024 > 2:
        raise HTTPException(
            status_code=400, detail="Image size greater than 2MB")
    try:
        result = minio_client.put_object(
            "minipix-content",
            "images/" + str(uuid.uuid4()) + "." + file.content_type.split("/")[1],
            file.file,
            length=-1,
            part_size=5 * 1024 * 1024,
            content_type=file.content_type
        )
        return {"success": True, "url": "https://" + cdn_url + "/" + result.object_name}  # noqa: E501
    except S3Error as error:
        print(str(error))
        raise HTTPException(status_code=500, detail=error_message)


@router.post("/cloudflare")
async def upload_to_cloudflare_images(
    file: UploadFile = File(...),
    token=Depends(decode_admin_token)
):
    try:
        file_bytes = await file.read()
        data = FormData()
        data.add_field(
            'file',
            file_bytes,
            filename=f"{img_prefix}-{str(uuid.uuid4())}"
        )
        headers = {"Authorization": f"Bearer {cf_api_token}"}
        async with ClientSession() as session:
            async with session.post(
                f"https://api.cloudflare.com/client/v4/accounts/{cf_account_id}/images/v1",  # noqa: E501
                headers=headers,
                data=data
            ) as resp:
                res = await resp.json()
                if res["success"]:
                    img_url = f"https://ibee-cdn.net/cdn-cgi/imagedelivery/{cf_account_hash}/{res['result']['id']}"  # noqa: E501
                    return {"success": True, "url": img_url}
                else:
                    {"success": False, "errors": res['errors'], "messages": res['messages']}  # noqa: E501
    except Exception as error:
        print(str(error))
        raise HTTPException(status_code=500, detail=error_message)


async def update_subtitle_document(id, language, type, operator, url):
    [id, season, number] = id.split("_") if '_' in id else [
        id, None, None]
    query = f"subtitles.{language}"

    if season:
        doc = await series_collection.update_one(
            {'_id': ObjectId(id)},
            {operator: {f'episodes.$[episode].{query}': url}},
            array_filters=[
                {"episode.season": int(season), "episode.number": int(number)}]
        )
    elif 'movie' in type:
        doc = await movies_collection.update_one(
            {'_id': ObjectId(id)},
            {operator: {query: url}}
        )
    else:
        doc = await songs_collection.update_one(
            {'_id': ObjectId(id)},
            {operator: {query: url}}
        )
    return doc and doc.modified_count == 1


def get_subtitle_extension(mime, name):
    shaka_mimes = {
        'sbv': 'text/x-subviewer',
        'srt': 'text/srt',
        'vtt': 'text/vtt',
        'webvtt': "text/vtt",
        'ttml': 'application/ttml+xml',
        'lrc': 'application/x-subtitle-lrc',
        'ssa': 'text/x-ssa',
        'ass': 'text/x-ssa',
    }
    ext = name.split(".")[-1]
    if ext in shaka_mimes.keys():
        return ext
    for k, v in shaka_mimes.items():
        mime = mime.split(
            "/")[-1] if mime and "/" in mime else mime.replace(".", "")
        if mime in v:
            return k


@router.post("/subtitles/{id}")
async def upload_subtitles(
    id: str,
    language: str,
    type: str,
    tasks: BackgroundTasks,
    file: UploadFile = File(...),
    token=Depends(decode_admin_token)
):
    try:
        type = 'movies' if 'mov' in type else 'songs'
        type = 'series' if '_' in id else type
        ext = get_subtitle_extension(file.content_type, file.filename)
        ext = f".{ext}" if ext else ""
        result = minio_client.put_object(
            type,
            f"{id}/{language}{ext}",
            file.file,
            length=-1,
            part_size=5 * 1024 * 1024,
            content_type=file.content_type
        )

        url = "https://" + cdn_url + f"/{type}/" + result.object_name
        tasks.add_task(update_subtitle_document, id,
                       language, type, "$set", url)

        return {"success": True, "url": url}
    except S3Error as error:
        print(str(error))
        raise HTTPException(status_code=500, detail=error_message)


@router.delete("/subtitles/{id}")
async def delete_subtitle(
    id: str,
    language: str,
    url: str,
    token=Depends(decode_admin_token)
):
    [*host, bucket, content_id, name] = url.split("/")
    success = await update_subtitle_document(content_id, language, bucket, "$unset", 1)
    if success:
        minio_client.remove_object(bucket, f"{content_id}/{name}")
    return {"success": success}
