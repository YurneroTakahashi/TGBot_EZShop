import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")
    REQUESTS_CHAT_ID = int(os.getenv("REQUESTS_CHAT_ID", "0")) if os.getenv("REQUESTS_CHAT_ID", "0").strip() else None

    # Валидация
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не указан в .env файле!")
    if not ADMIN_IDS:
        raise ValueError("ADMIN_IDS не указаны в .env файле!")

config = Config()