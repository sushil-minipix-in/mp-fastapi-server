from fastapi import APIRouter, Depends, HTTPException

from .utils import decode_admin_token
from ..models.admin import Admin, Permission
from ..models.user import User
from ..models.movie import Movie
from ..models.series import Series
from ..models.order import Order
from ..models.song import Song

router = APIRouter()


@router.get("/dashboard")
async def get_details(token=Depends(decode_admin_token)):
    subscribers = await User.get_count(token)
    movies, unpublished_movies = await Movie.get_count(token)
    series, unpublished_series = await Series.get_count(token)
    songs, unpublished_songs = await Song.get_count(token)
    orders_mtd = await Order.get_count(mtd=True)

    return {
        "subscribers": subscribers,
        "moviesAndSeries": movies + series,
        "ordersMTD": orders_mtd,
        "songs": songs,
        "unpublishedMovies": unpublished_movies,
        "unpublishedSeries": unpublished_series,
        "unpublishedSongs": unpublished_songs
    }


@router.get("")
async def get_employees(
    filter: bool = False,
    token=Depends(decode_admin_token)
):
    if not token['superadmin']:
        raise HTTPException(status_code=403, detail="Forbidden")

    admins = await Admin.get_all(filter=filter)
    return {"employees": admins}


@router.get("/{id}")
async def get_employee(id: str, token=Depends(decode_admin_token)):
    if not token['superadmin']:
        raise HTTPException(status_code=403, detail="Forbidden")

    success, employee = await Admin.get_by_id(id)
    if success:
        return employee
    else:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("")
async def create_admin(admin: Admin, token=Depends(decode_admin_token)):
    if token['superadmin']:
        await admin.save()
        return {'success': True}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.put("/{id}")
async def update_admin(
    id: str,
    admin: Admin,
    token=Depends(decode_admin_token)
):
    if token['superadmin']:
        await admin.save(id)
        return {'success': True}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.patch("/{id}")
async def update_permissions(
    id: str,
    p: Permission,
    token=Depends(decode_admin_token)
):
    if not token['superadmin']:
        raise HTTPException(status_code=403, detail="Forbidden")

    await p.save(id)
    return {'success': True}


@router.delete("/{id}")
async def delete_admin(id: str, token=Depends(decode_admin_token)):
    if not token['superadmin']:
        raise HTTPException(status_code=403, detail="Forbidden")

    await Admin.delete(id)
    return {'success': True}
