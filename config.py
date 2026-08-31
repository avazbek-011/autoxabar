"""Loyiha konfiguratsiyasi — barcha sozlamalar .env faylidan o'qiladi."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(key, default):
    try:
        return int(str(os.getenv(key, default)).strip())
    except (TypeError, ValueError):
        return int(default)


def _float(key, default):
    try:
        return float(str(os.getenv(key, default)).strip())
    except (TypeError, ValueError):
        return float(default)


def _str(key, default=""):
    return (os.getenv(key) or default).strip()


class Config:
    # --- Umumiy ---
    SECRET_KEY = _str("SECRET_KEY", "vipadsuz-dev-secret-change-me")
    DEBUG = _str("FLASK_DEBUG", "0") in ("1", "true", "True")
    HOST = _str("HOST", "0.0.0.0")
    PORT = _int("PORT", 5000)
    BASE_URL = _str("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    TIMEZONE = _str("TIMEZONE", "Asia/Tashkent")
    # Fon vazifalari (yuborish sikli, avto-to'lov) shu jarayonda ishlasinmi
    RUN_SCHEDULER = _str("RUN_SCHEDULER", "1") not in ("0", "false", "False")

    BASE_DIR = BASE_DIR
    # DATA_DIR ni muhit o'zgaruvchisi orqali ko'rsatish mumkin —
    # Render'da doimiy disk ulanganda o'sha yo'lni beriladi.
    DATA_DIR = _str("DATA_DIR") or str(BASE_DIR / "data")
    DB_PATH = os.path.join(DATA_DIR, "autoxabar.db")
    SESSION_DIR = _str("SESSION_DIR") or str(BASE_DIR / "sessions")
    UPLOAD_DIR = str(BASE_DIR / "static" / "uploads")

    # --- Sessiya cookie ---
    SESSION_COOKIE_NAME = "vipadsuz_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # --- Birinchi admin ---
    ADMIN_PHONE = _str("ADMIN_PHONE", "+998900000000")
    # Parol .env da ko'rsatilmasa, birinchi ishga tushishda tasodifiy
    # parol yaratiladi va konsolga chiqariladi (standart parol xavfli).
    ADMIN_PASSWORD = _str("ADMIN_PASSWORD") or ("ax-" + secrets.token_urlsafe(9))
    ADMIN_NAME = _str("ADMIN_NAME", "Administrator")

    # --- Narxlar ---
    PRICE_PER_PROFILE = _int("PRICE_PER_PROFILE", 5000)   # so'm / oy
    TRIAL_DAYS = _int("TRIAL_DAYS", 3)

    # --- Moliya ---
    TAX_PERCENT = _float("TAX_PERCENT", 10.0)
    ACQUIRING_PERCENT = _float("ACQUIRING_PERCENT", 1.0)

    # --- Payme Merchant API ---
    PAYME_MERCHANT_ID = _str("PAYME_MERCHANT_ID")
    PAYME_KEY = _str("PAYME_KEY")
    PAYME_TEST_KEY = _str("PAYME_TEST_KEY")
    PAYME_CHECKOUT_URL = _str("PAYME_CHECKOUT_URL", "https://checkout.paycom.uz").rstrip("/")

    # --- Payme Subscribe API (avto-to'lov) ---
    PAYME_SUBSCRIBE_URL = _str("PAYME_SUBSCRIBE_URL", "https://checkout.paycom.uz/api")
    PAYME_SUBSCRIBE_ID = _str("PAYME_SUBSCRIBE_ID")
    PAYME_SUBSCRIBE_KEY = _str("PAYME_SUBSCRIBE_KEY")

    # --- Telegram ---
    TELEGRAM_API_ID = _int("TELEGRAM_API_ID", 0)
    TELEGRAM_API_HASH = _str("TELEGRAM_API_HASH")
    TELEGRAM_ENGINE = _str("TELEGRAM_ENGINE", "auto")   # auto | real | demo

    # --- Bildirishnoma ---
    NOTIFY_BOT_TOKEN = _str("NOTIFY_BOT_TOKEN")
    NOTIFY_ADMIN_CHAT_ID = _str("NOTIFY_ADMIN_CHAT_ID")

    # --- Brend ---
    BRAND_NAME = "VIPADSUZ"
    PRODUCT_NAME = "AutoXabar"
    # Aloqa ma'lumotlari admin panelidan to'ldiriladi (Sozlamalar bo'limi).
    # Bo'sh bo'lsa saytda umuman ko'rsatilmaydi.
    TELEGRAM_CHANNEL = _str("TELEGRAM_CHANNEL")
    TELEGRAM_BOT = _str("TELEGRAM_BOT")
    SUPPORT_CONTACT = _str("SUPPORT_CONTACT")

    # Ruxsat etilgan yuborish intervallari (daqiqa)
    INTERVALS = [2, 5, 7, 10, 15, 20, 25, 30]


config = Config()
