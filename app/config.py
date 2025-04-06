from pydantic import BaseSettings
from typing import Set


class AppConfig(BaseSettings):
    allowed_origins: Set[str]
    jwt_secret_key: str
    mongo_uri: str
    db_name: str
    s3_url: str
    s3_access_key: str
    s3_secret_key: str
    razorpay_key: str
    razorpay_secret: str
    razorpay_webhook_secret: str
    transcode_secret: str
    cdn_url: str
    paytm_mid: str
    paytm_key: str
    paytm_website: str
    paytm_client_id: str
    paytm_env: str
    redis_host: str = "redis-svc"
    redis_port: int = 6379
    cf_account_id: str
    cf_api_token: str
    cf_account_hash: str
    fb_app_secret: str
    firebase_api_key: str
    android_package_name: str
    ios_bundle_id: str
    ios_app_store_id: str
    domain_uri_prefix: str
    sendgrid_from_email: str
    sendgrid_api_key: str
    base_url: str
    sms_sender_id: str
    sms_access_token: str
    justpay_api_url: str
    justpay_api_key: str
    justpay_merchant_id: str
    justpay_client_id: str
    justpay_redirect_url: str
    phonepe_callback_url: str
    phonepe_merchant_id: str
    phonepe_uri_success: str
    phonepe_uri_fail: str
    phonepe_key: str
    phonepe_key_index: str
    phonepe_api_host: str
    hash_sms: str