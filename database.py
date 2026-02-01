from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from models import Base
from config import config

# Настройка движка
if config.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        config.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )


    # Включаем внешние ключи для SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)

# Создание таблиц
Base.metadata.create_all(bind=engine)

# Фабрика сессий
session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
SessionLocal = scoped_session(session_factory)


@contextmanager
def get_db():
    """Контекстный менеджер для безопасной работы с сессией"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Инициализация начальных данных"""
    from models import BotSettings, AdminSettings, Button

    with get_db() as db:
        # Настройки бота
        if not db.query(BotSettings).first():
            db.add(BotSettings(
                greeting_text="👋 Добро пожаловать! Выберите, что вас интересует:",
                greeting_photo=None
            ))

        # Админ-настройки
        if not db.query(AdminSettings).first():
            db.add(AdminSettings(
                requests_chat_id=config.REQUESTS_CHAT_ID,
                requests_template=(
                    "📋 НОВАЯ ЗАЯВКА\n"
                    "Имя: {answers[0]}\n"
                    "Задача: {answers[1]}\n"
                    "Контакт: {answers[2]}\n"
                    "Время: {time}\n"
                    "Пользователь: @{username} (ID: {user_id})"
                )
            ))

        # Кнопки по умолчанию
        if not db.query(Button).first():
            db.add(Button(
                text="Узнать цены",
                order=1,
                is_active=True,
                response_type="text",
                response_content="Цены от 5000 руб. Подробнее на сайте: https://example.com/prices"
            ))
            db.add(Button(
                text="Заказать",
                order=2,
                is_active=True,
                response_type="form",
                form_questions='["Как вас зовут?", "Что нужно сделать?", "Оставьте контакт (телефон или email)"]'
            ))
            db.add(Button(
                text="Контакты",
                order=3,
                is_active=True,
                response_type="text",
                response_content="📞 +7 (999) 123-45-67\n📧 info@example.com\n🌐 https://example.com"
            ))
            db.add(Button(
                text="FAQ",
                order=4,
                is_active=True,
                response_type="text",
                response_content="❓ Частые вопросы:\n— Сроки: от 3 дней\n— Предоплата: 50%\n— Гарантия: 30 дней"
            ))
        db.commit()