from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class BotSettings(Base):
    __tablename__ = 'bot_settings'
    id = Column(Integer, primary_key=True)
    greeting_text = Column(Text, default="👋 Добро пожаловать! Выберите, что вас интересует:")
    greeting_photo = Column(String, nullable=True)  # file_id или URL

class Button(Base):
    __tablename__ = 'buttons'
    id = Column(Integer, primary_key=True)
    text = Column(String(64), nullable=False)
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    response_type = Column(String(20), default='text')  # text, file, link, form
    response_content = Column(Text, nullable=True)  # текст/ссылка/file_id
    form_questions = Column(Text, nullable=True)  # JSON: ["Имя", "Задача", "Контакт"]

class FormResponse(Base):
    __tablename__ = 'form_responses'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    button_id = Column(Integer, ForeignKey('buttons.id'))
    answers = Column(Text, nullable=False)  # JSON
    created_at = Column(String, nullable=False)  # ISO строка

class AdminSettings(Base):
    __tablename__ = 'admin_settings'
    id = Column(Integer, primary_key=True)
    requests_chat_id = Column(Integer, nullable=True)  # ID группы для заявок
    requests_template = Column(Text, default="📋 НОВАЯ ЗАЯВКА\nИмя: {answers[0]}\nЗадача: {answers[1]}\nКонтакт: {answers[2]}\nВремя: {time}")