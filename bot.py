import asyncio
import json
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import get_db, init_db
from models import BotSettings, Button, FormResponse, AdminSettings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserForm(StatesGroup):
    in_progress = State()


class AdminPanel(StatesGroup):
    greeting_text = State()
    greeting_photo = State()
    new_button_text = State()
    button_response_type = State()
    button_response_content = State()
    button_questions = State()
    requests_chat = State()


user_router = Router()
admin_router = Router()


@user_router.message.middleware()
@user_router.callback_query.middleware()
@admin_router.message.middleware()
@admin_router.callback_query.middleware()
async def db_session_middleware(handler, event, data):
    with get_db() as session:
        data["session"] = session
        return await handler(event, data)


def get_main_keyboard(session):
    buttons = session.query(Button).filter(Button.is_active == True).order_by(Button.order).all()
    if not buttons:
        return None
    kb = []
    row = []
    for btn in buttons:
        row.append(KeyboardButton(text=btn.text))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


@user_router.message(UserForm.in_progress)
async def handle_form_input(message: Message, session, state: FSMContext, bot: Bot):
    data = await state.get_data()
    answers = data.get("answers", [])
    questions = data["questions"]
    answers.append(message.text)

    if len(answers) < len(questions):
        await state.update_data(answers=answers)
        await message.answer(questions[len(answers)])
    else:
        button_id = data["form_button_id"]
        json_answers = json.dumps(answers, ensure_ascii=False)
        current_time = datetime.now().strftime("%H:%M")

        try:
            resp = FormResponse(
                user_id=message.from_user.id,
                button_id=button_id,
                answers=json_answers,
                created_at=current_time
            )
            session.add(resp)
            session.commit()
            logger.info(f"Заявка сохранена: user={message.from_user.id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка БД: {e}")
            await message.answer("Ошибка при отправке заявки. Попробуйте позже.")
            await state.clear()
            return

        try:
            admin_settings = session.query(AdminSettings).first()
            if admin_settings and admin_settings.requests_chat_id:
                name = answers[0] if len(answers) > 0 else "—"
                task = answers[1] if len(answers) > 1 else "—"
                contact = answers[2] if len(answers) > 2 else "—"

                text = (
                    "📋 НОВАЯ ЗАЯВКА\n"
                    f"Имя: {name}\n"
                    f"Задача: {task}\n"
                    f"Контакт: {contact}\n"
                    f"Время: {current_time}\n"
                    f"Пользователь: @{message.from_user.username or '—'} (ID: {message.from_user.id})"
                )
                await bot.send_message(chat_id=admin_settings.requests_chat_id, text=text)
                logger.info("Заявка отправлена в группу")
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")

        await message.answer("✅ Спасибо! Заявка передана, свяжемся в течение 2 часов.")
        await state.clear()


@user_router.message(F.text & ~F.text.startswith("/"), StateFilter(None))
async def handle_menu_click(message: Message, session, state: FSMContext):
    button = session.query(Button).filter(
        Button.text == message.text,
        Button.is_active == True
    ).first()

    if not button:
        await message.answer("Пожалуйста, используйте кнопки из меню 👇")
        return

    if button.response_type == "text":
        await message.answer(button.response_content or "Информация скоро появится")
    elif button.response_type == "file":
        if button.response_content and os.path.exists(button.response_content):
            from aiogram.types import FSInputFile
            await message.answer_document(document=FSInputFile(button.response_content))
        else:
            await message.answer("Файл не найден.")
    elif button.response_type == "link":
        await message.answer(f"🔗 {button.response_content}")
    elif button.response_type == "form":
        questions = json.loads(button.form_questions) if button.form_questions else ["Ваше имя?"]
        await state.update_data(form_button_id=button.id, questions=questions, answers=[])
        await state.set_state(UserForm.in_progress)
        await message.answer(questions[0])


@user_router.message(Command("start"))
async def cmd_start(message: Message, session):
    settings = session.query(BotSettings).first()
    reply_markup = get_main_keyboard(session)
    if settings.greeting_photo:
        await message.answer_photo(photo=settings.greeting_photo, caption=settings.greeting_text,
                                   reply_markup=reply_markup)
    else:
        await message.answer(settings.greeting_text, reply_markup=reply_markup)


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@admin_router.message(Command("panel"))
async def cmd_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Эта команда доступна только администраторам.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👋 Приветствие", callback_data="admin:greeting")],
        [InlineKeyboardButton(text="🔘 Кнопки", callback_data="admin:buttons_list")],
        [InlineKeyboardButton(text="📮 Группа заявок", callback_data="admin:requests")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👁️ Предпросмотр (/test)", callback_data="admin:test")]
    ])
    await message.answer("🛠 Панель управления:", reply_markup=kb)


@admin_router.message(Command("setgroup"))
async def set_group_from_chat(message: Message, session):
    if not is_admin(message.from_user.id):
        return
    if message.chat.type in ("group", "supergroup"):
        chat_id = message.chat.id
        settings = session.query(AdminSettings).first()
        settings.requests_chat_id = chat_id
        session.commit()
        await message.answer("✅ Эта группа установлена для заявок!")
    else:
        await message.answer("Отправьте /setgroup в нужной группе")


@admin_router.callback_query(F.data == "admin:greeting")
async def admin_greeting(callback: CallbackQuery, session):
    settings = session.query(BotSettings).first()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="admin:greeting_edit")],
        [InlineKeyboardButton(text="🖼️ Установить фото", callback_data="admin:greeting_photo")],
        [InlineKeyboardButton(text="🗑️ Удалить фото", callback_data="admin:greeting_photo_del")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")]
    ])
    preview = settings.greeting_text[:100] + "..." if len(settings.greeting_text) > 100 else settings.greeting_text
    await callback.message.edit_text(
        f"Текущий текст:\n{preview}\n\n📸 Фото: {'есть' if settings.greeting_photo else 'нет'}",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "admin:greeting_edit")
async def admin_greeting_edit(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новый текст приветствия:")
    await state.set_state(AdminPanel.greeting_text)


@admin_router.message(AdminPanel.greeting_text)
async def admin_greeting_save(message: Message, session, state: FSMContext):
    settings = session.query(BotSettings).first()
    settings.greeting_text = message.text
    session.commit()
    await message.answer("✅ Текст обновлён!")
    await state.clear()
    await cmd_panel(message)


@admin_router.callback_query(F.data == "admin:greeting_photo")
async def admin_greeting_photo(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Отправьте фото:")
    await state.set_state(AdminPanel.greeting_photo)


@admin_router.message(AdminPanel.greeting_photo, F.photo)
async def admin_greeting_photo_save(message: Message, session, state: FSMContext):
    file_id = message.photo[-1].file_id
    settings = session.query(BotSettings).first()
    settings.greeting_photo = file_id
    session.commit()
    await message.answer("✅ Фото установлено!")
    await state.clear()
    await cmd_panel(message)


@admin_router.callback_query(F.data == "admin:greeting_photo_del")
async def admin_greeting_photo_del(callback: CallbackQuery, session):
    settings = session.query(BotSettings).first()
    settings.greeting_photo = None
    session.commit()
    await callback.answer("✅ Фото удалено", show_alert=True)
    await admin_greeting(callback, session)


@admin_router.callback_query(F.data == "admin:buttons_list")
async def admin_buttons_list(callback: CallbackQuery, session):
    buttons = session.query(Button).order_by(Button.order).all()
    kb = []
    for btn in buttons:
        status = "✅" if btn.is_active else "❌"
        kb.append([InlineKeyboardButton(text=f"{status} {btn.text}", callback_data=f"admin:btn:{btn.id}")])
    kb.append([InlineKeyboardButton(text="➕ Добавить", callback_data="admin:btn_add")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")])
    await callback.message.edit_text("Управление кнопками:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@admin_router.callback_query(F.data == "admin:btn_add")
async def admin_btn_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите текст новой кнопки:")
    await state.set_state(AdminPanel.new_button_text)


@admin_router.message(AdminPanel.new_button_text)
async def admin_btn_add_text(message: Message, session, state: FSMContext):
    text = message.text.strip()
    max_order = session.query(Button.order).order_by(Button.order.desc()).first()
    new_order = (max_order[0] + 1) if max_order else 1
    btn = Button(text=text, order=new_order, is_active=True, response_type="text", response_content="")
    session.add(btn)
    session.commit()
    await message.answer(f"✅ Кнопка '{text}' создана.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"admin:btn_set_type:{btn.id}:text")],
        [InlineKeyboardButton(text="📎 Файл", callback_data=f"admin:btn_set_type:{btn.id}:file")],
        [InlineKeyboardButton(text="🌐 Ссылка", callback_data=f"admin:btn_set_type:{btn.id}:link")],
        [InlineKeyboardButton(text="❓ Опрос", callback_data=f"admin:btn_set_type:{btn.id}:form")]
    ]))
    await state.clear()


@admin_router.callback_query(F.data.startswith("admin:btn_set_type:"))
async def admin_btn_set_type(callback: CallbackQuery, session, state: FSMContext):
    _, _, btn_id, resp_type = callback.data.split(":")
    btn_id = int(btn_id)
    btn = session.query(Button).filter(Button.id == btn_id).first()
    if not btn:
        await callback.answer("Кнопка не найдена", show_alert=True)
        return

    btn.response_type = resp_type
    session.commit()

    prompts = {
        "text": "Введите текст ответа:",
        "link": "Введите URL:",
        "file": "Отправьте PDF или укажите путь (static/prices.pdf):",
        "form": 'Введите вопросы в формате JSON:\nПример: ["Имя", "Задача", "Контакт"]'
    }

    await callback.message.answer(prompts[resp_type])
    await state.update_data(editing_button_id=btn_id)
    if resp_type == "form":
        await state.set_state(AdminPanel.button_questions)
    else:
        await state.set_state(AdminPanel.button_response_content)


@admin_router.message(AdminPanel.button_response_content)
async def admin_btn_save_content(message: Message, session, state: FSMContext):
    data = await state.get_data()
    btn_id = data["editing_button_id"]
    btn = session.query(Button).filter(Button.id == btn_id).first()
    if btn:
        if btn.response_type == "file" and message.document:
            btn.response_content = message.document.file_id
        else:
            btn.response_content = message.text
        session.commit()
        await message.answer("✅ Ответ сохранён!")
    await state.clear()
    await cmd_panel(message)


@admin_router.message(AdminPanel.button_questions)
async def admin_btn_save_questions(message: Message, session, state: FSMContext):
    try:
        questions = json.loads(message.text)
        if not isinstance(questions, list):
            raise ValueError
    except Exception:
        await message.answer("Неверный формат. Используйте JSON-массив строк.")
        return

    data = await state.get_data()
    btn_id = data["editing_button_id"]
    btn = session.query(Button).filter(Button.id == btn_id).first()
    if btn:
        btn.form_questions = json.dumps(questions, ensure_ascii=False)
        session.commit()
        await message.answer("✅ Вопросы сохранены!")
    await state.clear()
    await cmd_panel(message)


@admin_router.callback_query(F.data == "admin:requests")
async def admin_requests(callback: CallbackQuery, session):
    settings = session.query(AdminSettings).first()
    chat_info = f"ID: {settings.requests_chat_id}" if settings.requests_chat_id else "не задана"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Установить группу", callback_data="admin:req_set")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")]
    ])
    await callback.message.edit_text(f"Группа заявок: {chat_info}", reply_markup=kb)


@admin_router.callback_query(F.data == "admin:req_set")
async def admin_req_set(callback: CallbackQuery):
    await callback.message.answer("Добавьте бота в группу и отправьте там /setgroup")


@admin_router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, session):
    total = session.query(FormResponse).count()
    await callback.message.edit_text(
        f"📊 Статистика:\nВсего заявок: {total}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:main")]])
    )


@admin_router.callback_query(F.data == "admin:test")
async def admin_test(callback: CallbackQuery, session):
    await cmd_start(callback.message, session)
    await callback.answer("👁️ Предпросмотр отправлен", show_alert=True)


@admin_router.callback_query(F.data == "admin:main")
async def admin_main(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👋 Приветствие", callback_data="admin:greeting")],
        [InlineKeyboardButton(text="🔘 Кнопки", callback_data="admin:buttons_list")],
        [InlineKeyboardButton(text="📮 Группа заявок", callback_data="admin:requests")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="👁️ Предпросмотр (/test)", callback_data="admin:test")]
    ])
    await callback.message.edit_text("🛠 Панель управления:", reply_markup=kb)
    await callback.answer()


async def main():
    logger.info("Инициализация...")
    init_db()
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(user_router)
    dp.include_router(admin_router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())