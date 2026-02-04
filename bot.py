import asyncio
import logging
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8261897648:AAE1P80ALDJQD9xtJv3nTNA_GLdZlalaVb8"

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ID админа (замените на ваш реальный ID)
ADMIN_ID = 6082495203  # @foxyzi

# Состояния для FSM
class AdminStates(StatesGroup):
    waiting_for_reply = State()

# Контекстный менеджер для работы с БД
@contextmanager
def get_db_connection():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# Инициализация БД
def init_database():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица сообщений
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_id INTEGER,
            admin_message_id INTEGER,
            text TEXT,
            is_from_user BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        conn.commit()

# Функции для работы с БД
def save_user(user_id: int, username: str, first_name: str, last_name: str = None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        conn.commit()

def save_message(user_id: int, message_id: int, admin_message_id: int, text: str, is_from_user: bool):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO messages (user_id, message_id, admin_message_id, text, is_from_user)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, message_id, admin_message_id, text, is_from_user))
        conn.commit()

def get_all_users():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT DISTINCT u.user_id, u.username, u.first_name, u.last_name, 
               MAX(m.created_at) as last_activity
        FROM users u
        LEFT JOIN messages m ON u.user_id = m.user_id
        GROUP BY u.user_id
        ORDER BY last_activity DESC
        ''')
        return cursor.fetchall()

def get_user_messages(user_id: int, limit: int = 20):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM messages 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
        ''', (user_id, limit))
        return cursor.fetchall()

def get_user_info(user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    save_user(user_id, username, first_name, last_name)
    
    if user_id == ADMIN_ID:
        await message.answer(
            "👋 Привет, админ!\n\n"
            "Используйте команды:\n"
            "/users - список пользователей\n"
            "/stats - статистика\n\n"
            "Просто отвечайте на сообщения пользователей, чтобы отправить им ответ.",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer(
            "👋 Привет! Напишите ваше сообщение, и администратор ответит вам в ближайшее время."
        )

# Обработчик команды /users (только для админа)
@router.message(Command("users"))
async def cmd_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = get_all_users()
    
    if not users:
        await message.answer("📭 Пользователей пока нет")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for user in users:
        username = f"@{user['username']}" if user['username'] else "Нет username"
        name = f"{user['first_name']} {user['last_name'] or ''}".strip()
        button_text = f"{name} ({username})"
        
        # Обрезаем текст если слишком длинный
        if len(button_text) > 30:
            button_text = button_text[:27] + "..."
        
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"user_{user['user_id']}"
            )
        ])
    
    await message.answer("👥 Список пользователей:", reply_markup=keyboard)

# Обработчик команды /stats (только для админа)
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM messages WHERE is_from_user = 1")
        total_messages = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM messages WHERE is_from_user = 0")
        total_replies = cursor.fetchone()[0]
    
    await message.answer(
        f"📊 Статистика:\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"📨 Получено сообщений: {total_messages}\n"
        f"📤 Отправлено ответов: {total_replies}"
    )

# Обработчик нажатия на кнопку пользователя
@router.callback_query(F.data.startswith("user_"))
async def process_user_selection(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    
    user_info = get_user_info(user_id)
    if not user_info:
        await callback.answer("Пользователь не найден")
        return
    
    username = f"@{user_info['username']}" if user_info['username'] else "Нет username"
    name = f"{user_info['first_name']} {user_info['last_name'] or ''}".strip()
    
    messages = get_user_messages(user_id, 5)
    
    text = f"👤 Пользователь: {name}\n"
    text += f"📱 Username: {username}\n"
    text += f"🆔 ID: {user_id}\n\n"
    text += f"📨 Последние сообщения:\n"
    
    for msg in reversed(messages):  # В хронологическом порядке
        prefix = "👤" if msg['is_from_user'] else "👨‍💼"
        text += f"{prefix} {msg['text'][:100]}...\n" if len(msg['text']) > 100 else f"{prefix} {msg['text']}\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Написать сообщение", callback_data=f"write_{user_id}")],
        [InlineKeyboardButton(text="📨 Все сообщения", callback_data=f"all_msgs_{user_id}")],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="back_to_users")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

# Обработчик кнопки "Написать сообщение"
@router.callback_query(F.data.startswith("write_"))
async def process_write_message(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    
    await state.update_data(recipient_id=user_id)
    await state.set_state(AdminStates.waiting_for_reply)
    
    user_info = get_user_info(user_id)
    username = f"@{user_info['username']}" if user_info['username'] else "Нет username"
    
    await callback.message.answer(
        f"✏️ Введите сообщение для пользователя {username} (ID: {user_id}):\n"
        f"Для отмены отправьте /cancel"
    )
    await callback.answer()

# Обработчик кнопки "Все сообщения"
@router.callback_query(F.data.startswith("all_msgs_"))
async def process_all_messages(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    
    messages = get_user_messages(user_id, 50)
    
    if not messages:
        await callback.answer("Нет сообщений")
        return
    
    text = "📨 История сообщений:\n\n"
    for msg in reversed(messages):  # В хронологическом порядке
        prefix = "👤 Пользователь:" if msg['is_from_user'] else "👨‍💼 Вы:"
        timestamp = datetime.strptime(msg['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m %H:%M')
        text += f"{prefix} {msg['text'][:200]}\n[{timestamp}]\n\n"
    
    # Разбиваем на части если сообщение слишком длинное
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await callback.message.answer(part)
    else:
        await callback.message.answer(text)
    
    await callback.answer()

# Обработчик кнопки "Назад"
@router.callback_query(F.data == "back_to_users")
async def process_back(callback: CallbackQuery):
    await cmd_users(callback.message)
    await callback.answer()

# Обработчик отмены
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.answer("❌ Действие отменено")

# Обработчик сообщений от пользователей (не админа)
@router.message(F.chat.type == "private")
async def handle_user_message(message: Message):
    user_id = message.from_user.id
    
    # Игнорируем команды
    if message.text and message.text.startswith('/'):
        return
    
    # Если это не админ - пересылаем сообщение админу
    if user_id != ADMIN_ID:
        save_user(
            user_id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name
        )
        
        # Формируем текст с информацией о пользователе
        username = f"@{message.from_user.username}" if message.from_user.username else "Нет username"
        name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
        
        caption = f"👤 От: {name}\n"
        caption += f"📱 {username}\n"
        caption += f"🆔 ID: {user_id}\n\n"
        
        try:
            # Пересылаем сообщение админу
            if message.text:
                text = caption + message.text
                sent_msg = await bot.send_message(ADMIN_ID, text)
                save_message(user_id, message.message_id, sent_msg.message_id, message.text, True)
            
            elif message.photo:
                text = caption + (message.caption or "")
                sent_msg = await bot.send_photo(
                    ADMIN_ID, 
                    message.photo[-1].file_id, 
                    caption=text
                )
                save_message(user_id, message.message_id, sent_msg.message_id, message.caption or "", True)
            
            elif message.document:
                text = caption + (message.caption or "")
                sent_msg = await bot.send_document(
                    ADMIN_ID,
                    message.document.file_id,
                    caption=text
                )
                save_message(user_id, message.message_id, sent_msg.message_id, message.caption or "", True)
            
            elif message.voice:
                text = caption + "🎤 Голосовое сообщение"
                sent_msg = await bot.send_voice(
                    ADMIN_ID,
                    message.voice.file_id,
                    caption=text
                )
                save_message(user_id, message.message_id, sent_msg.message_id, "Голосовое сообщение", True)
            
            else:
                text = caption + "📎 Медиафайл"
                sent_msg = await bot.send_message(ADMIN_ID, text)
                save_message(user_id, message.message_id, sent_msg.message_id, "Медиафайл", True)
            
            # Создаем клавиатуру для быстрого ответа
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💌 Ответить", callback_data=f"write_{user_id}")]
            ])
            
            try:
                await bot.edit_message_reply_markup(
                    chat_id=ADMIN_ID,
                    message_id=sent_msg.message_id,
                    reply_markup=keyboard
                )
            except:
                pass  # Если не удалось добавить клавиатуру - не страшно
        
        except Exception as e:
            logger.error(f"Ошибка при пересылке сообщения: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте позже.")

# Обработчик ответов админа (reply на сообщение)
@router.message(F.reply_to_message)
async def handle_admin_reply(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    reply_msg = message.reply_to_message
    
    # Проверяем, является ли это ответом на пересланное сообщение
    if reply_msg.text and "ID:" in reply_msg.text:
        try:
            # Извлекаем ID пользователя из текста сообщения
            lines = reply_msg.text.split('\n')
            for line in lines:
                if "ID:" in line:
                    user_id = int(line.split("ID:")[1].strip())
                    break
            else:
                return
            
            # Отправляем сообщение пользователю
            if message.text:
                await bot.send_message(user_id, f"👨‍💼 Ответ администратора:\n\n{message.text}")
                save_message(user_id, message.message_id, None, message.text, False)
                await message.answer("✅ Ответ отправлен")
            
            elif message.photo:
                await bot.send_photo(
                    user_id,
                    message.photo[-1].file_id,
                    caption=f"👨‍💼 Ответ администратора:\n\n{message.caption or ''}"
                )
                save_message(user_id, message.message_id, None, message.caption or "", False)
                await message.answer("✅ Фото отправлено")
            
            elif message.document:
                await bot.send_document(
                    user_id,
                    message.document.file_id,
                    caption=f"👨‍💼 Ответ администратора:\n\n{message.caption or ''}"
                )
                save_message(user_id, message.message_id, None, message.caption or "", False)
                await message.answer("✅ Документ отправлен")
            
            else:
                await message.answer("❌ Этот тип сообщения не поддерживается для ответа")
        
        except Exception as e:
            logger.error(f"Ошибка при отправке ответа: {e}")
            await message.answer("❌ Ошибка при отправке ответа")

# Обработчик сообщения в состоянии ожидания ответа
@router.message(AdminStates.waiting_for_reply)
async def handle_direct_message(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    recipient_id = data.get('recipient_id')
    
    if not recipient_id:
        await state.clear()
        return
    
    try:
        if message.text:
            await bot.send_message(recipient_id, f"👨‍💼 Ответ администратора:\n\n{message.text}")
            save_message(recipient_id, message.message_id, None, message.text, False)
            await message.answer("✅ Сообщение отправлено")
        
        elif message.photo:
            await bot.send_photo(
                recipient_id,
                message.photo[-1].file_id,
                caption=f"👨‍💼 Ответ администратора:\n\n{message.caption or ''}"
            )
            save_message(recipient_id, message.message_id, None, message.caption or "", False)
            await message.answer("✅ Фото отправлено")
        
        else:
            await message.answer("❌ Этот тип сообщения не поддерживается")
    
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        await message.answer("❌ Ошибка при отправке сообщения. Возможно, пользователь заблокировал бота.")
    
    await state.clear()

# Главная функция
async def main():
    # Инициализация БД
    init_database()
    
    logger.info("Бот запущен")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
