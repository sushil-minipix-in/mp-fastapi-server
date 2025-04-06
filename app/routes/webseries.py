from fastapi import APIRouter, Security, Depends, Request

from .utils import get_current_employee, decode_token, decode_headers, decode_jwt_token

from ..models.webseries import WebSeries


router = APIRouter()

@router.get("")
async def get_webseries(
        page: int = 1,
        pageSize: int = 10,
        filterBy: str = None,
        token=Security(get_current_employee, scopes=["Series:read"])
):
    result = await WebSeries.get_webseries(page, pageSize, filterBy)
    return {'success': True, **result}

@router.get("/{webseries_id}")
async def get_webseries_by_id(webseries_id: str, request: Request, headers=Depends(decode_headers)):
    token = decode_jwt_token(request.headers.get('authorization', False))
    result = await WebSeries.get_webseries_by_id(webseries_id, token)
    return result

@router.post("")
async def create_webseries(webseries: WebSeries, token=Security(get_current_employee, scopes=["Series:create"])):
    result = await webseries.save(webseries_id=None, token=token)
    return result

@router.put("/{webseries_id}")
async def edit_webseries(webseries_id: str,
                         webseries: WebSeries,
                         token=Security(get_current_employee, scopes=["Series:edit"])
                         ):
    result = await webseries.save(webseries_id = webseries_id, token = token)
    return result

@router.delete("/{webseries_id}")
async def delete_webseries(webseries_id: str, token=Security(get_current_employee, scopes=["Series:delete"])):
    result = await WebSeries.delete_webseries(webseries_id=webseries_id, token=token)
    return result