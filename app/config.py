from pydantic import BaseSettings, Field
from typing import Set
from functools import lru_cache
import os

class AppConfig(BaseSettings):
    """
    Application configuration settings loaded from environment variables
    """
    # API and CORS settings
    allowed_origins: Set[str]
    base_url: str
    
    # Security settings
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    
    # Database settings
    mongo_uri: str
    db_name: str
    
    # Redis settings
    redis_host: str = Field(default="redis-svc", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    
    # Storage settings
    s3_url: str
    s3_access_key: str
    s3_secret_key: str
    cdn_url: str
    
    # Payment gateway settings
    razorpay_key: str
    razorpay_secret: str
    razorpay_webhook_secret: str
    
    paytm_mid: str
    paytm_key: str
    paytm_website: str
    paytm_client_id: str
    paytm_env: str
    
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
    
    # Media processing
    transcode_secret: str
    
    # Cloudflare settings
    cf_account_id: str
    cf_api_token: str
    cf_account_hash: str
    
    # Social and authentication
    fb_app_secret: str
    firebase_api_key: str
    
    # Mobile app settings
    android_package_name: str
    ios_bundle_id: str
    ios_app_store_id: str
    domain_uri_prefix: str
    
    # Communication settings
    sendgrid_from_email: str
    sendgrid_api_key: str
    sms_sender_id: str
    sms_access_token: str
    hash_sms: str
    
    class Config:
        """
        Configuration for the settings class
        """
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

@lru_cache()
def get_settings() -> AppConfig:
    """
    Get application settings as a cached singleton
    """
    return AppConfig()

# Create a singleton instance of the settings
settings = get_settings()

