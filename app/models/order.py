import math

from app.db import Mongo
from bson.objectid import ObjectId
from datetime import date, timedelta, datetime
from pydantic import BaseModel, validator
from typing import Optional
from razorpay.errors import SignatureVerificationError

from ..models.discount import Discount
from ..models.tracking_params import OrderTrackingParams
import nanoid

db = Mongo()
orders_collection = db.orders
plans_collection = db.plans
discounts_collection = db.discounts
users_collection = db.users

ALPHANUMERIC_CHARACTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'


class Order(BaseModel):
    planId: str
    discountCode: Optional[str] = None
    tracking: Optional[OrderTrackingParams] = dict

    @validator('discountCode')
    def validate_discount_code(cls, value):
        if value:
            value = value.strip().upper()
        return value

    @classmethod
    async def get_count(cls, mtd=False) -> int:
        if mtd:
            start_date = date.today().replace(day=1).isoformat()
            count = await orders_collection.count_documents(filter={
                "date": {"$gte": start_date}
            })
        else:
            count = await orders_collection.count_documents(filter={})

        return count

    @classmethod
    async def get_upgrade_options(cls, order, user_id):
        amount = order.get("total_price", 0)
        user = await users_collection.find_one({
            '_id': ObjectId(user_id)
        })

        if amount <= 0 or (not user) or ('activeSubscription' not in user):
            return []

        subscriptions = user.get('subscriptions', [])
        subscription = user['subscriptions'].pop() if subscriptions else None
        if subscription and subscription['order_id'] != str(order["_id"]):
            return []

        query = {
            "suspended": False,
            "reseller": {"$exists": False},
            f"price.{order['currency']}": {"$gt": amount}
        }

        start = datetime.strptime(subscription['startDate'], '%Y-%m-%d')
        end = datetime.strptime(subscription['endDate'], '%Y-%m-%d')
        now = datetime.now()
        days_total = (end - start).days
        days_left = (end - now).days
        discount = 0
        if days_total > 0:
            discount = math.floor((order['amount'] / days_total) * days_left)
        plans = []
        async for plan in plans_collection.find(query):
            plan['_id'] = str(plan['_id'])
            price = plan.get('price', {}).get(order['currency'], -1)
            if price > 0 and price - discount > 0:
                plan["actual_price"] = price
                plan["discount_price"] = discount
                plan["price"] = price - discount
                plan["startDate"] = str(date.today())
                plan["endDate"] = str(
                    date.today() + timedelta(days=plan['duration']))
                plan["currency"] = order['currency']
                plan["currency_symbol"] = order.get('currency_symbol')
                plans.append(plan)
        return plans

    @classmethod
    async def get_upgrade_amount(cls, plans, plan_id):
        plan = list(filter(lambda x: x['_id'] == plan_id, plans))
        if plan:
            plan = plan[0]
            plan = {
                'success': True,
                'amount': plan['price'],
                'duration': plan['duration'],
                'total_price': plan['actual_price'],
                'plan_id': plan['_id'],
                'plan': plan['name'],
                'startDate': plan['startDate'],
                'endDate': plan['endDate'],
                'discountAmount': plan['discount_price'],
                'discountCode': 'upgrade'
            }
            return plan
        return {'success': False}

    async def get_amount(self, currency):
        discount = {"success": False,
                    'discountCode': None, "discountAmount": 0}
        doc = await discounts_collection.find_one({'code': self.discountCode})
        if doc and self.planId in doc.get('applicableOn', []):
            invalid = Discount.is_invalid_time(doc)
            allow_currency = doc.get('allowedCurrency', None) in [
                None, currency]
            if allow_currency and invalid is False and 'tokens' not in doc:
                discount = {"success": True, "discountAmount": doc['amount'],
                            'plan_id': self.planId, 'discountCode': self.discountCode}  # noqa: E501
            if allow_currency and invalid is False and doc.get('tokensUsed', 0) < doc.get('tokens', -1):  # noqa: E501
                discount = {"success": True, "discountAmount": doc['amount'],
                            'plan_id': self.planId, 'discountCode': self.discountCode}  # noqa: E501

        plan = await plans_collection.find_one({'_id': ObjectId(self.planId)})  # noqa: E501
        if plan:
            price = plan.get('price', {}).get(currency, -1)
            main_cost = price
            if price <= 0:
                return {'success': False}
            if discount['success']:
                offer = round(
                    price * (discount['discountAmount'] / 100), 2)
                price = max(round(price - offer, 2), 0)
                discount['discountAmount'] = offer
            start_date = str(date.today())
            end_date = str(
                date.today() + timedelta(days=plan['duration']))
            return {**discount, 'success': True, 'amount': price,
                    'plan': plan['name'], 'duration': plan['duration'],
                    'startDate': start_date, 'endDate': end_date,
                    'total_price': main_cost, 'plan_id': str(plan['_id'])}
        return {'success': False}

    async def create_subscription(self, rzrpy_client, currency, user_id):
        ''' created,authenticated,active,pending,
            halted,cancelled,completed,expired '''

        plan = await plans_collection.find_one({'_id': ObjectId(self.planId)})
        if not plan:
            return {'success': False, 'message': 'plan not available'}
        price = plan.get('price', {}).get(currency, 0)
        rzr_plan = plan.get('rpPlans', {}).get(f"{currency}_{price}")
        if not rzr_plan or price <= 0:
            return {'success': False, 'message': 'plan not available'}
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        order_id = f"rp{nanoid.generate(ALPHANUMERIC_CHARACTERS, 18)}"
        start_date = str(date.today())
        end_date = str(date.today() + timedelta(days=plan['duration']))
        # if user['eligible_for_trial']:
        #     start_date = str(date.today())
        #     end_date = str(date.today() + timedelta(days=2))

        response = rzrpy_client.subscription.create({
            'plan_id': rzr_plan,
            'total_count': 99,
            'customer_notify': 1,
            'notes': {
                'user_id': user_id,
                'order_id': order_id
            }
        })
        print(response)
        valid = response['status'] == 'created'
        return {
            'success': valid,
            'plan': plan['name'],
            'amount': price,
            'status': response['status'],
            'currency': currency,
            'id': response['id'],
            'total_count': response['total_count'],
            'remaining_count': response['remaining_count'],
            'startDate': start_date,
            'endDate': end_date,
            'pg': 'razorpay',
            'user': user_id,
            'duration': plan['duration'],
            'order_id': order_id
        }


class CaptureOrder(BaseModel):
    paymentId: str
    signature: Optional[str]

    async def capture_razorpay_order(self, rzrpy_client, order):
        try:
            params_dict = {
                'razorpay_order_id': order['_id'],
                'razorpay_payment_id': self.paymentId,
                'razorpay_signature': self.signature
            }
            rzrpy_client.utility.verify_payment_signature(params_dict)
            doc = rzrpy_client.payment.capture(
                self.paymentId,
                order['amount'] * 100,
                {'currency': order['currency']}
            )
            captured = doc['status'] == 'captured'
            if captured:
                code = "Paid"
                messgae = doc['status']
            else:
                code = f"{doc['error_code']}-{doc['error_source']}-{doc['error_step']}"  # noqa: E501
                messgae = f"{doc['error_reason']} - {doc['error_description']}"
            return {
                'paid': captured,
                'paymentId': self.paymentId,
                'paymentSignature': self.signature,
                'message': messgae,
                'code': code}
        except SignatureVerificationError:
            return {'paid': False, 'message': "Bad Razorpay Signature",
                    'code': "Bad Razorpay Signature"}

    async def verify_subscription_order(self, rzrpy_client, sub_id):
        try:
            # rzrpy_client.utility.verify_subscription_payment_signature({
            #     'razorpay_subscription_id': sub_id,
            #     'razorpay_payment_id': self.paymentId,
            #     'razorpay_signature': self.signature
            # })
            response = rzrpy_client.subscription.fetch(sub_id)
            return {
                'paid': response['status'] in ['created', 'authenticated', 'active'],  # noqa: E501
                'sub_status': response['status'],
                'id': response['id'],
                'paid_count': response['paid_count'],
                'total_count': response['total_count'],
                'paymentId': self.paymentId,
                # 'paymentSignature': self.signature,
            }
        except Exception:
            return {'paid': False}
