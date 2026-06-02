from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    # ===== TELEGRAM =====
    BOT_TOKEN: str
    ADMIN_IDS: List[int] = []

    # ===== DATABASE =====
    DATABASE_URL: str

    # ===== 3X-UI =====
    XUI_HOST: str
    XUI_USERNAME: str
    XUI_PASSWORD: str
    XUI_TOKEN: str = ""
    XUI_INBOUND_IDS: List[int] = [1]

    # ===== YOOKASSA =====
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    YOOKASSA_RETURN_URL: str = ""

    # ===== CRYPTOBOT =====
    CRYPTOBOT_API_TOKEN: str = ""
    CRYPTOBOT_NETWORK: str = "mainnet"

    # ===== PRICES =====
    PRICE_1_MONTH: int = 299
    TRIAL_DAYS: int = 7
    SUBSCRIPTION_DAYS: int = 30

    # ===== REFERRAL =====
    REFERRAL_REWARD_RUB: int = 50
    REFERRAL_DISCOUNT_PERCENT: int = 50

    # ===== NOTIFICATIONS =====
    NOTIFY_BEFORE_DAYS: int = 3

    # ===== PARSERS =====
    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("XUI_INBOUND_IDS", mode="before")
    @classmethod
    def parse_inbound_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()