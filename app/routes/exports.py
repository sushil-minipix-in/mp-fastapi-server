import csv

from app.db import Mongo
from fastapi import APIRouter, Security
from fastapi.responses import StreamingResponse
from io import StringIO

from .utils import get_current_employee

db = Mongo()
series_collection = db.series
movies_collection = db.movies
media_houses_collection = db.media_houses
genres_collection = db.genres
plans_collection = db.plans
users_collection = db.users
orders_collection = db.orders
languages_collection = db.languages
albums_collection = db.albums
artists_collection = db.artists

content_type_csv = "text/csv"
content_header = "attachment; filename=export.csv"

router = APIRouter()


@router.get("/series")
async def export_series(
    token=Security(get_current_employee, scopes=['Series:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for s in series_collection.find():
        if not header_written:
            csv_writer.writerow([*s.keys()])
            header_written = True
        csv_writer.writerow([*s.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/movies")
async def export_movies(
    token=Security(get_current_employee, scopes=['Movies:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for m in movies_collection.find():
        if not header_written:
            csv_writer.writerow([*m.keys()])
            header_written = True
        csv_writer.writerow([*m.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/albums")
async def export_albums(
    token=Security(get_current_employee, scopes=['Albums:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in albums_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/artists")
async def export_artists(
    token=Security(get_current_employee, scopes=['Artists:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in artists_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/media_houses")
async def export_media_houses(
    token=Security(get_current_employee, scopes=['Media Houses:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in media_houses_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/genres")
async def export_genres(
    token=Security(get_current_employee, scopes=['Genres:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in genres_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/languages")
async def export_languages(
    token=Security(get_current_employee, scopes=['Languages:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in languages_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/plans")
async def export_plans(
    token=Security(get_current_employee, scopes=['Plans:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in plans_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/users")
async def export_users(
    token=Security(get_current_employee, scopes=['Users:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in users_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response


@router.get("/orders")
async def export_orders(
    token=Security(get_current_employee, scopes=['Orders:read'])
):
    io_buffer = StringIO()
    csv_writer = csv.writer(io_buffer)
    header_written = False
    async for a in orders_collection.find():
        if not header_written:
            csv_writer.writerow([*a.keys()])
            header_written = True
        csv_writer.writerow([*a.values()])

    response = StreamingResponse(
        iter([io_buffer.getvalue()]), media_type=content_type_csv)
    response.headers['Content-Disposition'] = content_header

    return response
