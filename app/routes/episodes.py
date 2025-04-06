from fastapi import APIRouter, Security, UploadFile, File, status, HTTPException

from .utils import get_current_employee
from ..models.episodes import Episode

router = APIRouter()

@router.get("")
async def get_episodes(series_id: str, page: int = 1, pageSize : int = 10, filterBy: str = None):
    result = await Episode.get_episodes(series_id = series_id, page = page, pageSize = pageSize, filterBy = filterBy)
    return {**result, "page": page, "pageSize": pageSize}

@router.get("/{episode_id}")
async def get_episode_by_id(episode_id: str):
    result = await Episode.get_episode_by_id(episode_id=episode_id)
    return result

@router.post("")
async def create_episode(episode: Episode, token=Security(get_current_employee, scopes=["Series:create"])):
    result = await episode.save(episode_id = None)
    return result

@router.put("/{episode_id}")
async def update_episode(episode_id: str, episode: Episode, token=Security(get_current_employee, scopes=["Series:update"])):
    result = await episode.save(episode_id = episode_id)
    return result

@router.post("/bulkUpload")
async def bulk_upload_episodes(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST, detail = "File must be a CSV.")
    result = await Episode.bulk_upload_episodes(file = file)
    return result

@router.delete("/{episode_id}")
async def delete_episode(episode_id: str, token=Security(get_current_employee, scopes=["Series:delete"])):
    result = await Episode.delete_episode(episode_id)
    return result
