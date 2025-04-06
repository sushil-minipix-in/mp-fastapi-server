from fastapi import APIRouter, BackgroundTasks, Security, HTTPException, Request

from .utils import get_current_employee, send_update, decode_token, verify_update_content
from ..models.song import Song

router = APIRouter()


@router.get("")
async def get_songs(
    token=Security(get_current_employee, scopes=["Songs:read"])
):
    songs = await Song.get_all(token)
    return {'songs': songs}


@router.get("/{id}")
async def get_song(id: str, request: Request):
    token = request.headers.get('authorization', False)
    admin = False
    if token:
        token = decode_token(token.split(" ")[1])
        admin = (token.get('admin', False) or token.get('superadmin', False))
    success, song = await Song.get_by_id(id)
    if not success or (song['availability'] == 'unpublished' and admin is False):
        raise HTTPException(status_code=404, detail="Not found")
    return song


@router.post("", status_code=201)
async def create_song(
    song: Song,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Songs:create"])
):
    result = await song.save(token)
    bg.add_task(send_update, song.title, 'song', 'created', token['email'])
    return {'success': result}


@router.put("/{id}")
async def update_song(
    id: str,
    song: Song,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Songs:update"])
):
    if song.availability == "unpublished":
        await verify_update_content(id, "song")
    result = await song.save(token, id)
    bg.add_task(send_update, song.title, 'song', 'updated',
                token['email'], song.availability)
    return {'success': result}


@router.delete("/{id}")
async def delete_song(
    id: str,
    bg: BackgroundTasks,
    token=Security(get_current_employee, scopes=["Songs:delete"])
):
    await verify_update_content(id, "song")
    result, title = await Song.delete(id)
    bg.add_task(send_update, title, 'song', 'deleted', token['email'])
    return {'success': result}
