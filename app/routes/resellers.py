from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Header, Security, HTTPException
from typing import Optional

from .utils import get_current_employee
from ..models.reseller import Reseller, Subscription

db = Mongo()
resellers_collection = db.resellers

router = APIRouter()


@router.get("")
async def get_resellers(
    token=Security(get_current_employee, scopes=["Plans:read"])
):
    resellers = []

    async for reseller in resellers_collection.find({}):
        reseller["_id"] = str(reseller["_id"])
        resellers.append(reseller)

    return {"resellers": resellers}


@router.get("/{id}")
async def get_reseller(
    id: str,
    token=Security(get_current_employee, scopes=["Plans:read"])
):
    reseller = await resellers_collection.find({"_id": ObjectId(id)})
    if not reseller:
        raise HTTPException(status_code=404, detail="Not found")

    reseller["_id"] = str(reseller["_id"])
    return {"reseller": reseller}


@router.post("")
async def create_reseller(
    reseller: Reseller,
    token=Security(get_current_employee, scopes=["Plans:create"])
):
    status = await reseller.save()
    return {"success": status}


@router.put("/{id}")
async def update_reseller(
    id: str,
    reseller: Reseller,
    token=Security(get_current_employee, scopes=["Plans:update"])
):
    status = await reseller.save(id)
    return {"success": status}


@router.delete("/{id}")
async def delete_reseller(
    id: str,
    token=Security(get_current_employee, scopes=["Plans:delete"])
):
    status = await Reseller.delete(id)
    return {"success": status}


@router.post("/{id}/create_subscription")
async def create_subscription(
    id: str,
    subscription: Subscription,
    x_api_key: Optional[str] = Header(None)
):
    reseller = await resellers_collection.find_one({"_id": ObjectId(id)})
    if not reseller:
        raise HTTPException(status_code=403, detail="Forbidden")

    if reseller["apiKey"] != x_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    success, message = await subscription.save(id, reseller["name"])
    return {"success": True} if success else {"success": False, "reason": message}  # noqa: E501
