from fastapi import APIRouter, Request, Header, BackgroundTasks, HTTPException

from app.models.justpay import update_ticket_details, update_user_subscription, activate_mandate, create_mandate, \
    expire_or_revoke_mandate

router = APIRouter()

@router.post("/justpay-callback")
async def justpay_s2s_callback(request: Request):
    req = await request.json()
    print(req['event_name'])

    # if req['event_name'] == "ORDER_SUCCEEDED" and "ticket" in req['content']['order']['order_id']:
    #     print(req)
    #     await update_ticket_details(req)

    if req['event_name'] == "ORDER_SUCCEEDED":
        print(req)
        await activate_mandate(req)
        return {"success": True}

    if req["event_name"] == "MANDATE_CREATED":
        await create_mandate(req)

    # if req["event_name"] == "MANDATE_ACTIVATED":
    #     await activate_mandate(req)

    if req["event_name"] == "MANDATE_EXPIRED" or req["event_name"] == "MANDATE_REVOKED":
        await expire_or_revoke_mandate(req)

    return {'success': True, 'message': "Webhook not configured for this event"}


@router.post("/razorpay-callback")
async def handle_razorpay_callback(request: Request):
    req = await request.json()
    # print(req)
    return


@router.post("/callback_s2s")
async def handle_s2s_callback(
    bg: BackgroundTasks,
    req: Request,
    x_verify: str = Header(default=None)
):
    if x_verify is None:
        raise HTTPException(status_code=401, detail="Not authorised")

    req_json = await req.json()
    payload_base64 = req_json['response']
    sha256_sum = (hashlib.sha256(
        f"{payload_base64}{key}".encode())).hexdigest()
    if x_verify != f"{sha256_sum}###{key_index}":
        raise HTTPException(status_code=400, detail="Bad request")

    response = base64.b64decode(req_json['response']).decode('ascii')
    response_json = json.loads(response)
    success = response_json.get('success')
    if success:
        data = response_json.get('data', {})
        order_id = data.get('merchantTransactionId')
        order = await orders_collection.find_one({'_id': order_id})

        subscription = {
            'name': order['plan'],
            'startDate': str(date.today()),
            'endDate': str(date.today() + timedelta(days=order['duration'])),
            'orderId': order['_id'],
            'amount': order['amount'],
            'currency': 'INR',
            'utm_data': order.get('utm_data', {
                'utm_source': 'NA',
                'utm_medium': 'NA',
                'platform': 'NA'
            }),
            'status': "Active"
        }

        await orders_collection.update_one(
            {'_id': order_id},
            {'$set': {'paid': True, 'status': 'success'}}
        )
        await users_collection.update_one(
            {'_id': ObjectId(order['user'])},
            {
                '$set': {'activeSubscription': True},
                '$push': {'subscriptions': subscription}
            }
        )
        user = await users_collection.find_one({"_id": ObjectId(order["user"])})
        await expire_subscriptions(user, order_id)
        bg.add_task(update_discount, order_id)
        if user and user.get("email"):
            subject, body = Messages.on_buying_subscription(user)
            bg.add_task(Messages.send_email, user["email"], subject, body)
        return {'success': True}
