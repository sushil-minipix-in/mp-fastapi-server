from aiohttp import ClientSession
from ..config import AppConfig
from ..routes.utils import make_api_request

config = AppConfig()
access_token = config.sms_access_token
sender_id = config.sms_sender_id
hash_sms = config.hash_sms


class SMSMessage():

    @classmethod
    async def send_sms(cls, to_mobile, body, template_id):
        try:
            API_ENDPOINT = "https://services.engagenest.com/core/v1/sms/403f585a-6d2a-42dc-b801-b861ee1a2102/send"
            API_KEY = "b9938ed1-233f-4321-9994-6f4cbaca0399"
            headers = {
                "X-EN-Api-Key": API_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "from": "MiniPX",
                "to": to_mobile,
                "country": "IN",
                "body": body,
                "templateId": template_id,
                "entityId": "1701160593727105205",
                "messageType": 2,
                "customId": to_mobile,
                "flash": False,
                "serviceType": 0
            }

            result = await make_api_request(
                method="POST",
                url=API_ENDPOINT,
                headers=headers,
                payload=payload
            )
            print(result)

        except Exception as e:
            print(str(e))
            print("Error in sending SMS")

    @classmethod
    def get_otp_body(cls, otp):
        body = f"<#> {otp} is Your MiniPIX verification code. Enjoy watching! {hash_sms} - MiniPIX"
        return body, "1707174187884936906"

    @classmethod
    def on_successful_registration(cls):
        body = "Thank you for Downloading the MiniPIX app. Watch unlimited movies, web series, songs, and more. https://bit.ly/3N9AV3b"

        return body

    @classmethod
    def on_successful_subscription_purchase(cls):
        body = "Thank you for buying a subscription. Watch your favorite movie and web series on MiniPIX"

        return body

    @classmethod
    def on_successful_ticket_purchase(cls, details):
        content_type = details['type']
        body = f"Thank you for buying a Ticket. Watch your favorite {'Movie' if content_type == 'movie' else 'Series'} {details['name']} on MiniPIX"

        return body

    @classmethod
    def on_successful_upgrade(cls):
        body = "Your plan has been upgraded. Don't miss out on exclusive content, blockbuster movies on MiniPIX"

        return body

    @classmethod
    def on_subscription_expired(cls):
        body = "Your plan has expired. Renew your plan today to continue watching unlimited movies, web series, and more on MiniPIX. https://bit.ly/3N9AV3b"

        return body
