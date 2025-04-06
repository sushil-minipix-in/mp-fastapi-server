from app.db import Mongo
from bson.objectid import ObjectId
from fastapi import APIRouter, Body, Security, HTTPException, Depends, BackgroundTasks

from .utils import decode_headers, get_current_employee, create_rp_plan
from ..models.plan import ApplePlan, Plan, AndroidPlan

db = Mongo()
plans_collection = db.plans
resellers_collection = db.resellers
apple_plans_collection = db.applePlans
android_plans_collection = db.androidPlans

router = APIRouter()

create_plan_scope = "Plans:create"
read_plan_scope = "Plans:read"
update_plan_scope = "Plans:update"
exists = "$exists"


@router.get("")
async def get_plans(type: str = 'web', header: dict = Depends(decode_headers)):
    plans = []
    if type == 'web':
        currency = header['currency']
        symbol = header.get('currency_symbol', currency)
        async for plan in plans_collection.find({'reseller': {exists: False}, 'suspended': False}):
            plan['_id'] = str(plan['_id'])
            plan['price'] = plan.get('price', {}).get(currency, -1)
            plan['currency'] = currency
            plan['currency_symbol'] = symbol
            if plan['price'] > 0:
                plans.append(plan)

    if type == 'apple':
        async for apple_plan in apple_plans_collection.find({'planType': 'applePlan', 'suspended': False}):
            apple_plan['_id'] = str(apple_plan['_id'])
            plans.append(apple_plan)

    if type == 'android':
        async for android_plan in android_plans_collection.find({'planType': 'androidPlan', 'suspended': False}):
            android_plan['_id'] = str(android_plan['_id'])
            plans.append(android_plan)

    plans = sorted(plans, key=lambda x: x.get('duration'))
    return {'plans': plans}


@router.get("/admin")
async def get_plans_for_admin(
    token=Security(get_current_employee, scopes=[read_plan_scope])
):
    plans = []
    async for plan in plans_collection.find():
        plan["_id"] = str(plan["_id"])
        if "reseller" in plan:
            reseller = await resellers_collection.find_one({"_id": ObjectId(plan["reseller"])})  # noqa: E501
            plan["resellerName"] = reseller["name"]
        plans.append(plan)

    return {"plans": plans}


@router.get("/cms")
async def get_plans_cms(header: dict = Depends(decode_headers), type: str = 'web'):
    currency = header['currency']
    symbol = header.get('currency_symbol', currency)
    plans = []
    if type == 'web':
        async for plan in plans_collection.find({'reseller': {exists: False}}):
            plan['_id'] = str(plan['_id'])
            plan['price'] = plan.get('price', {})
            plan['currency'] = currency
            plan['currency_symbol'] = symbol
            plans.append(plan)

    if type == 'apple':
        async for apple_plan in apple_plans_collection.find({'planType': 'applePlan'}):
            apple_plan['_id'] = str(apple_plan['_id'])
            plans.append(apple_plan)

    if type == 'android':
        async for android_plan in android_plans_collection.find({'planType': 'androidPlan'}):
            android_plan['_id'] = str(android_plan['_id'])
            plans.append(android_plan)

    return {"plans": plans}


@router.post("")
async def create_plan(
    plan: Plan,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=[create_plan_scope])
):
    _id = await plan.save()
    if plan.reseller is None:
        doc = {k: v for k, v in plan.dict().items() if v is not None}
        doc['_id'] = str(_id)
        tasks.add_task(create_rp_plan, doc, plans_collection)
    return {"success": True}


@router.post("/applePlan")
async def create_apple_plan(
    plan: ApplePlan,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=[create_plan_scope])
):
    success = await plan.save()
    return {"success": success}


@router.post("/androidPlan")
async def create_android_plan(
    plan: AndroidPlan,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=[create_plan_scope])
):
    success = await plan.save()
    return {"success": success}


@router.delete("/{id}")
async def delete_plan(
    id: str,
    token=Security(get_current_employee, scopes=["Plans:delete"])
):
    await plans_collection.delete_one({'_id': ObjectId(id)})
    return {"success": True}


@router.get("/{id}")
async def get_plan_by_id(
    id: str,
    token=Security(get_current_employee, scopes=[read_plan_scope])
):
    if ObjectId.is_valid(id):
        plan = await plans_collection.find_one({'_id': ObjectId(id)})

    if plan:
        plan['_id'] = str(plan['_id'])
        return plan
    else:
        raise HTTPException(status_code=404, detail='Not found')


@router.get("/cms/{id}")
async def get_plan_cms_by_id(
    id: str,
    type: str,
    token=Security(get_current_employee, scopes=["Plans:read"])
):

    detail_message_404 = "Not found"

    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Not a valid plan id")

    if type == 'web':
        plan = await plans_collection.find_one({'_id': ObjectId(id)})

        if plan:
            plan['_id'] = str(plan['_id'])
            return plan
        else:
            raise HTTPException(status_code=404, detail=detail_message_404)

    if type == 'apple':
        plan = await apple_plans_collection.find_one({'_id': ObjectId(id)})

        if plan:
            plan['_id'] = str(plan['_id'])
            return plan
        else:
            raise HTTPException(status_code=404, detail=detail_message_404)

    if type == 'android':
        plan = await android_plans_collection.find_one({'_id': ObjectId(id)})

        if plan:
            plan['_id'] = str(plan['_id'])
            return plan
        else:
            raise HTTPException(status_code=404, detail=detail_message_404)


@router.put("/{id}")
async def update_plan(
    id: str,
    plan: Plan,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=[update_plan_scope])
):
    await plan.save(id)
    if plan.reseller is None:
        doc = {k: v for k, v in plan.dict().items() if v is not None}
        doc['_id'] = id
        tasks.add_task(create_rp_plan, doc, plans_collection)
    return {"success": True}


@router.put("/applePlan/{id}")
async def update_apple_plan(
    id: str,
    plan: ApplePlan,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=[update_plan_scope])
):
    await plan.save(id)
    return {"success": True}


@router.put("/androidPlan/{id}")
async def update_android_plan(
    id: str,
    plan: AndroidPlan,
    tasks: BackgroundTasks,
    token=Security(get_current_employee, scopes=[update_plan_scope])
):
    await plan.save(id)
    return {"success": True}


@router.patch("/{id}")
async def update_plan_status(
    id: str,
    suspended: bool = Body(..., embed=True),
    token=Security(get_current_employee, scopes=[update_plan_scope])
):
    await Plan.update_status(id, suspended)
    return {"success": True}


@router.patch("/applePlan/{id}")
async def update_apple_plan_status(
    id: str,
    suspended: bool = Body(..., embed=True),
    token=Security(get_current_employee, scopes=[update_plan_scope])
):
    await ApplePlan.update_status(id, suspended)
    return {"success": True}


@router.patch("/androidPlan/{id}")
async def update_android_plan_status(
    id: str,
    suspended: bool = Body(..., embed=True),
    token=Security(get_current_employee, scopes=[update_plan_scope])
):
    await AndroidPlan.update_status(id, suspended)
    return {"success": True}
