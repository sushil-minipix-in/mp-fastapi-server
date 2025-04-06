from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Security, Depends

from .utils import get_current_employee, decode_headers
from ..models.discount import Discount

db = Mongo()
discounts_collection = db.discounts
plans_collection = db.plans

router = APIRouter()


@router.post("/validate")
async def validate_discount(
    code: str,
    plan_id: str,
    header: dict = Depends(decode_headers)
):
    code = code.strip().upper()
    currency = header['currency']
    discount = {'success': False, 'cf_currency': currency}
    doc = await discounts_collection.find_one({'code': code})
    plan = await plans_collection.find_one({'_id': ObjectId(plan_id)})
    if plan and doc and plan_id in doc.get('applicableOn', []):
        price = plan.get('price', {}).get(currency, -1)
        allow_fx = doc.get('allowedCurrency', None) in [None, currency]
        if price <= 0 or allow_fx is not True:
            return discount
        if Discount.is_invalid_time(doc):
            return discount
        discount['actual_price'] = price
        discount['discountAmount'] = round(price * (doc['amount'] / 100), 2)
        discount['price'] = max(
            round(price - discount['discountAmount'], 2), 1)
        if 'tokens' not in doc:
            discount = {**discount, "success": True,
                        'planId': plan_id, 'discountCode': code}
        if doc.get('tokensUsed', 0) < doc.get('tokens', -1):
            discount = {**discount, "success": True,
                        'planId': plan_id, 'discountCode': code}
    return discount


@router.get("")
async def get_discounts(
    token=Security(get_current_employee, scopes=["Discounts:read"])
):
    discounts = []
    async for discount in discounts_collection.find():
        discount["_id"] = str(discount["_id"])
        discounts.append(discount)
    return {'discounts': discounts}


@router.post("")
async def create_discount(
    discount: Discount,
    token=Security(get_current_employee, scopes=["Discounts:create"])
):
    await discount.save()
    return {'success': True}


@router.put("/{id}")
async def update_discount(
    discount: Discount,
    id: str,
    token=Security(get_current_employee, scopes=["Discounts:update"])
):
    await discount.save(id)
    return {'success': True}


@router.delete("/{id}")
async def delete_discount(
    id: str,
    token=Security(get_current_employee, scopes=["Discounts:delete"])
):
    await discounts_collection.delete_one({'_id': ObjectId(id)})
    return {'success': True}
