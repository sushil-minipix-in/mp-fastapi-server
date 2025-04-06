from fastapi import APIRouter, Depends, HTTPException

from .utils import decode_admin_token
from ..models.partner import Partner

router = APIRouter()


@router.get("")
async def get_partners(token=Depends(decode_admin_token)):
    partners = await Partner.get_all()
    return {'partners': partners}


@router.post("")
async def create_partner(partner: Partner, token=Depends(decode_admin_token)):
    if token['superadmin']:
        await partner.save()
        return {'success': True}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.put("/{id}")
async def update_partner(
    id: str,
    partner: Partner,
    token=Depends(decode_admin_token)
):
    if token['superadmin']:
        await partner.save()
        return {'success': True}
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.delete("/{id}")
async def delete_partner(id: str, token=Depends(decode_admin_token)):
    if not token['superadmin']:
        raise HTTPException(status_code=403, detail="Forbidden")

    await Partner.delete(id)
    return {'success': True}
