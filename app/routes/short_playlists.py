from fastapi import APIRouter, Security, Depends

from app.models.short_playlist import ShortPlaylist
from app.routes.utils import get_current_employee, decode_token

router = APIRouter()

@router.get("")
async def get_playlists(
    page: str = "home",
    playlist_id: str = None,
    pageNo: int = 1,
    pageSize: int = 10,
    filterBy: str = None,
    token: str = Depends(decode_token)
):
    result = await ShortPlaylist.get_playlists(
        token=token,
        page=page,
        playlist_id=playlist_id,
        pageNo=pageNo,
        pageSize=pageSize,
        filterBy=filterBy
    )
    return result

@router.post("")
async def create_playlist(playlist: ShortPlaylist, token=Security(get_current_employee, scopes=["Playlists:create"])):
    result = await playlist.save(playlist_id = None)
    return result

@router.put("/{playlist_id}")
async def update_playlist(playlist_id: str, playlist: ShortPlaylist, token=Security(get_current_employee, scopes=["Playlists:update"])):
    result = await playlist.save(playlist_id = playlist_id)
    return result

@router.delete("/{playlist_id}")
async def delete_playlist(playlist_id: str, token=Security(get_current_employee, scopes=["Playlists:delete"])):
    result = await ShortPlaylist.delete_playlist(playlist_id=playlist_id)
    return result