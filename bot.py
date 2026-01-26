import json
import asyncio
import os
import sys
import logging
import uuid
import zipfile
import importlib.util
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# 🔥 FIREBASE IMPORTS
import firebase_admin
from firebase_admin import credentials, db

# ═══════════════════════════════════════════
# ⚙️ НАСТРОЙКИ
# ═══════════════════════════════════════════
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Получаем настройки из Render
BOT_TOKEN = os.getenv("BOT_TOKEN", "8261897648:AAE1P80ALDJQD9xtJv3nTNA_GLdZlalaVb8")
OWNER_ID = 6057537422
FIREBASE_KEY_JSON = os.getenv("FIREBASE_KEY")

RANK_PLAYER = "Игрок"
RANK_VIP = "VIP 💎"
RANK_ADMIN = "Администратор 👑"
RANK_OWNER = "Главный Лис 🦊"

ACCESS_PUBLIC = "public"
ACCESS_VIP = "vip"
ACCESS_BETA = "beta"

# 🔥 ПОДКЛЮЧЕНИЕ К FIREBASE
try:
    if not firebase_admin._apps:
        if FIREBASE_KEY_JSON:
            cred_dict = json.loads(FIREBASE_KEY_JSON)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': f'https://foxyzihub-527c4-default-rtdb.europe-west1.firebasedatabase.app/' 
            })
            logger.info("✅ Подключение к Firebase успешно (через ENV)!")
        else:
            # Аварийный вариант (локальный тест)
            if os.path.exists("firebase_key.json"):
                cred = credentials.Certificate("firebase_key.json")
                firebase_admin.initialize_app(cred, {
                    'databaseURL': f'https://foxyzihub-527c4-default-rtdb.europe-west1.firebasedatabase.app/' 
                })
                logger.info("✅ Подключение к Firebase успешно (через файл)!")
            else:
                logger.warning("⚠️ FIREBASE_KEY не найден! Бот будет работать без базы данных.")
except Exception as e:
    logger.error(f"❌ Ошибка Firebase: {e}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BASE_EVENT_ROUTER = Router()
dp.include_router(BASE_EVENT_ROUTER)

temp_games = {} 
admin_states = {} 

CURRENT_EVENT_NAME = None
CURRENT_EVENT_MODULE = None

# ═══════════════════════════════════════════
# 🌍 ФЕЙКОВЫЙ СЕРВЕР (Для Render)
# ═══════════════════════════════════════════
async def health_check(request): return web.Response(text="🦊 FoxyZiHub Core is active!")
async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', health_check)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ═══════════════════════════════════════════
# 📂 СИСТЕМА ДАННЫХ (FIREBASE ADAPTER)
# ═══════════════════════════════════════════

def load_data(filename, default):
    try:
        # Firebase не любит точки в ключах, меняем . на _
        clean_name = filename.replace(".", "_") 
        ref = db.reference(f'storage/{clean_name}')
        data = ref.get()
        if data is None:
            return default
        return data
    except Exception as e:
        logger.error(f"Ошибка чтения {filename} из Firebase: {e}")
        return default

def save_data(filename, data):
    try:
        clean_name = filename.replace(".", "_")
        ref = db.reference(f'storage/{clean_name}')
        ref.set(data)
    except Exception as e:
        logger.error(f"Ошибка записи {filename} в Firebase: {e}")

# Сохранение скриптов ивентов
def save_script_to_db(filename, content):
    try:
        clean_name = filename.replace(".", "_")
        ref = db.reference(f'scripts/{clean_name}')
        ref.set({"filename": filename, "content": content})
    except Exception as e:
        logger.error(f"Ошибка сохранения скрипта: {e}")

def restore_scripts_from_db():
    try:
        if not os.path.exists("events"): os.makedirs("events")
        ref = db.reference('scripts')
        scripts = ref.get()
        if scripts:
            count = 0
            for key, val in scripts.items():
                fname = val.get("filename")
                content = val.get("content")
                if fname and content:
                    with open(f"events/{fname}", "w", encoding="utf-8") as f:
                        f.write(content)
                    count += 1
            if count > 0:
                logger.info(f"♻️ Восстановлено ивентов из Firebase: {count}")
    except Exception as e:
        logger.error(f"Ошибка восстановления скриптов: {e}")

def add_log(admin_name, text):
    logs = load_data("logs.json", [])
    if not isinstance(logs, list): logs = []
    timestamp = datetime.now().strftime("%d.%m %H:%M")
    logs.insert(0, f"[{timestamp}] 👤 {admin_name}: {text}")
    if len(logs) > 200: logs.pop()
    save_data("logs.json", logs)

def get_events_db():
    return load_data("events_db.json", {"files": {}})

def save_events_db(data):
    save_data("events_db.json", data)

async def check_maintenance(event, user_id):
    settings = load_data("settings.json", {"maintenance": False})
    if not settings.get("maintenance", False): return True
    if user_id == OWNER_ID: return True
    if isinstance(event, types.CallbackQuery):
        try: await event.answer() 
        except: pass
    return False

# --- ПОЛЬЗОВАТЕЛИ ---
def get_user(user_id):
    users = load_data("users.json", {})
    if not isinstance(users, dict): users = {}
    uid = str(user_id)
    default_user = {"name": "Unknown", "username": "None", "privilege": RANK_PLAYER, "has_beta": False, "unlocked_prefixes": [], "active_prefix": None}
    user = users.get(uid, default_user)
    if user_id == OWNER_ID:
        user["privilege"] = RANK_OWNER
        user["has_beta"] = True
    return user

def update_user_info(user_tg):
    users = load_data("users.json", {})
    if not isinstance(users, dict): users = {}
    uid = str(user_tg.id)
    user_data = users.get(uid, {"privilege": RANK_PLAYER, "has_beta": False, "unlocked_prefixes": [], "active_prefix": None})
    if user_tg.id == OWNER_ID: 
        user_data["privilege"] = RANK_OWNER
        user_data["has_beta"] = True
    user_data["name"] = user_tg.full_name
    user_data["username"] = user_tg.username
    users[uid] = user_data
    save_data("users.json", users)

def find_user_in_db(query):
    users = load_data("users.json", {})
    if not isinstance(users, dict): users = {}
    query = query.replace("@", "").lower().strip()
    for uid, data in users.items():
        if str(data.get("username", "")).lower() == query: return uid, data
    return None, None

def is_admin_or_owner(user_id):
    user = get_user(user_id)
    return user["privilege"] in [RANK_ADMIN, RANK_OWNER]

def get_user_display_name(user_id):
    user = get_user(user_id)
    prefix_text = ""
    prefixes_data = load_data("prefixes.json", {"list": []})
    plist = prefixes_data.get("list", []) if isinstance(prefixes_data, dict) else []
    
    if user.get("active_prefix"):
        found = False
        for p in plist:
            if p["id"] == user["active_prefix"]:
                prefix_text = f"<b>{p['text']}</b> "
                found = True
                break
        if not found:
            users = load_data("users.json", {})
            if str(user_id) in users:
                users[str(user_id)]["active_prefix"] = None
                save_data("users.json", users)
    return f"{prefix_text}{user['name']}"

# ═══════════════════════════════════════════
# 🧩 ИВЕНТ МЕНЕДЖЕР
# ═══════════════════════════════════════════
async def activate_event(filename):
    global CURRENT_EVENT_NAME, CURRENT_EVENT_MODULE
    
    BASE_EVENT_ROUTER.sub_routers.clear()
    CURRENT_EVENT_NAME = None
    CURRENT_EVENT_MODULE = None
    
    if not filename:
        logger.info("ℹ️ Ивенты отключены.")
        return True

    file_path = f"events/{filename}"
    if not os.path.exists(file_path):
        restore_scripts_from_db()
        if not os.path.exists(file_path):
            logger.error(f"❌ Файл {filename} не найден!")
            return False

    try:
        spec = importlib.util.spec_from_file_location(f"event_{uuid.uuid4().hex}", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, "router"):
            BASE_EVENT_ROUTER.include_router(module.router)
            CURRENT_EVENT_NAME = getattr(module, "BUTTON_NAME", "🎉 ИВЕНТ")
            CURRENT_EVENT_MODULE = module
            logger.info(f"✅ Ивент '{CURRENT_EVENT_NAME}' ({filename}) активирован!")
            
            settings = load_data("settings.json", {})
            settings["active_event_file"] = filename
            save_data("settings.json", settings)
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return False

# ═══════════════════════════════════════════
# 🏠 ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════
def main_menu(user_id):
    buttons = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🎮 Список игр", callback_data="games_list")]
    ]
    if CURRENT_EVENT_NAME:
        show = True
        if CURRENT_EVENT_MODULE and hasattr(CURRENT_EVENT_MODULE, "should_show_button"):
            try: show = CURRENT_EVENT_MODULE.should_show_button(user_id)
            except: pass
        if show:
            buttons.insert(1, [InlineKeyboardButton(text=CURRENT_EVENT_NAME, callback_data="event_start")])

    if is_admin_or_owner(user_id):
        buttons.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_open_menu")])
    buttons.append([InlineKeyboardButton(text="📢 Канал", url="https://t.me/FoxyZiHub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not await check_maintenance(message, message.from_user.id): return
    update_user_info(message.from_user)
    await message.answer("🦊 <b>Добро пожаловать в FoxyZiHub!</b>\n\nЗдесь ты найдёшь мои игры.\nВыбери пункт меню ниже 👇",
                         parse_mode="HTML", reply_markup=main_menu(message.from_user.id))

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message): 
    if not await check_maintenance(message, message.from_user.id): return
    await cmd_start(message)

# --- ПРОФИЛЬ ---
@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    await callback.answer()
    user = get_user(callback.from_user.id)
    display_name = get_user_display_name(callback.from_user.id)
    beta_status = "✅ Есть" if user.get("has_beta") else "❌ Нет"
    text = (f"👤 <b>Твой профиль:</b>\n\n🏷 <b>Ник:</b> {display_name}\n🔰 <b>Привилегия:</b> {user.get('privilege', RANK_PLAYER)}\n🧪 <b>Бета-тест:</b> {beta_status}")
    buttons = []
    if user.get("unlocked_prefixes"): buttons.append([InlineKeyboardButton(text="🏷 Выбрать префикс", callback_data="profile_prefixes")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "profile_prefixes")
async def choose_prefix_menu(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    await callback.answer()
    user = get_user(callback.from_user.id)
    prefixes_data = load_data("prefixes.json", {"list": []})
    plist = prefixes_data.get("list", [])
    buttons = []
    active = "✅ " if user.get("active_prefix") is None else ""
    buttons.append([InlineKeyboardButton(text=f"{active}Без префикса", callback_data="set_my_prefix_none")])
    for pid in user.get("unlocked_prefixes", []):
        p_text = next((p["text"] for p in plist if p["id"] == pid), None)
        if not p_text: continue 
        is_active = "✅ " if user.get("active_prefix") == pid else ""
        buttons.append([InlineKeyboardButton(text=f"{is_active}{p_text}", callback_data=f"set_my_prefix_{pid}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="profile")])
    await callback.message.edit_text("🏷 <b>Выбери префикс:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("set_my_prefix_"))
async def set_own_prefix(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    await callback.answer()
    prefix_id = callback.data.split("_", 3)[3]
    if prefix_id == "none": prefix_id = None
    users = load_data("users.json", {})
    uid = str(callback.from_user.id)
    if uid in users:
        users[uid]["active_prefix"] = prefix_id
        save_data("users.json", users)
    await show_profile(callback)

@dp.callback_query(F.data == "back_home")
async def back_home(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    await callback.answer()
    await callback.message.edit_text("🦊 <b>FoxyZiHub</b>\nМеню:", parse_mode="HTML", reply_markup=main_menu(callback.from_user.id))

# --- ИГРЫ ---
@dp.callback_query(F.data == "games_list")
async def show_games_list(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    await callback.answer()
    games_data = load_data("games.json", {"games": []})
    games = games_data.get("games", [])
    user = get_user(callback.from_user.id)
    is_beta_tester = user.get("has_beta") or user.get("privilege") in [RANK_ADMIN, RANK_OWNER]
    buttons = []
    has_games = False
    for i, game in enumerate(games):
        access = game.get("access_type", ACCESS_PUBLIC)
        if access == ACCESS_BETA and not is_beta_tester: continue
        icon = "🎮"
        if access == ACCESS_BETA: icon = "🧪"
        elif access == ACCESS_VIP: icon = "💎"
        buttons.append([InlineKeyboardButton(text=f"{icon} {game['name']}", callback_data=f"dl_{i}")])
        has_games = True
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")])
    text = "🎮 <b>Список игр:</b>" if has_games else "😔 <b>Игр пока нет.</b>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("dl_"))
async def download_game(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    idx = int(callback.data.split("_")[1])
    games_data = load_data("games.json", {"games": []})
    games = games_data.get("games", [])
    if idx >= len(games): return
    game = games[idx]
    user = get_user(callback.from_user.id)
    access = game.get("access_type", ACCESS_PUBLIC)
    if access == ACCESS_BETA and not (user.get("has_beta") or user.get("privilege") in [RANK_ADMIN, RANK_OWNER]):
        await callback.answer("⛔ Только для Бета-тестеров!", show_alert=True)
        return
    if access == ACCESS_VIP and not user.get("privilege") in [RANK_VIP, RANK_ADMIN, RANK_OWNER]:
        await callback.answer("⛔ Только для VIP игроков!", show_alert=True)
        return
    await callback.answer("📤 Загрузка файла...")
    await bot.send_document(callback.message.chat.id, document=game["file_id"], caption=f"🦊 <b>{game['name']}</b>\n\n📝 {game['description']}", parse_mode="HTML")

# --- АДМИНКА ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin_or_owner(message.from_user.id): return
    await open_admin_panel(message)

@dp.callback_query(F.data == "admin_open_menu")
async def callback_admin(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    await open_admin_panel(callback.message, edit=True)

async def open_admin_panel(message: types.Message, edit=False):
    uid = message.chat.id
    admin_states[uid] = None
    buttons = [
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users_menu")],
        [InlineKeyboardButton(text="🎮 Управление играми", callback_data="admin_games")],
        [InlineKeyboardButton(text="📢 Сделать оповещение", callback_data="admin_broadcast_start")]
    ]
    if uid == OWNER_ID:
        buttons.insert(1, [InlineKeyboardButton(text="🏷 Настройка Префиксов", callback_data="admin_prefixes_menu")])
        buttons.insert(2, [InlineKeyboardButton(text="🎉 Управление Ивентом", callback_data="admin_event_mgr")])
        buttons.append([InlineKeyboardButton(text="💾 Настройки бота", callback_data="admin_core")])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])
    text = "👑 <b>Админ-панель (FIREBASE ONLINE)</b>"
    if edit: await message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else: await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_close")
async def close_admin(callback: types.CallbackQuery):
    await callback.answer()
    admin_states[callback.from_user.id] = None
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu(callback.from_user.id))

@dp.callback_query(F.data == "admin_back")
async def admin_back_main(callback: types.CallbackQuery):
    await callback.answer()
    admin_states[callback.from_user.id] = None
    await open_admin_panel(callback.message, edit=True)

# --- ИВЕНТ МЕНЕДЖЕР ---
@dp.callback_query(F.data == "admin_event_mgr")
async def admin_event_manager(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    settings = load_data("settings.json", {})
    active_file = settings.get("active_event_file", None)
    events_db = get_events_db()["files"]
    active_name = events_db.get(active_file, "Неизвестный") if active_file else "🔴 Выключен"
    text = (f"🎉 <b>Управление Ивентами</b>\n\n"
            f"Текущий статус: <b>{active_name}</b>\n\n"
            f"Загрузи скрипт с подписью, чтобы добавить в библиотеку.")
    buttons = [
        [InlineKeyboardButton(text="📂 Выбрать из библиотеки", callback_data="event_library")],
        [InlineKeyboardButton(text="🔴 Остановить ивент", callback_data="event_stop")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "event_library")
async def event_library_list(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    events_db = get_events_db()["files"]
    if not events_db:
        await callback.message.edit_text("📂 <b>Библиотека пуста.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_event_mgr")]]))
        return
    buttons = []
    restore_scripts_from_db()
    for filename, display_name in events_db.items():
        if os.path.exists(f"events/{filename}"):
            buttons.append([InlineKeyboardButton(text=f"▶️ {display_name}", callback_data=f"event_preview_{filename}")])
        else:
            buttons.append([InlineKeyboardButton(text=f"⚠️ {display_name} (Файл утерян)", callback_data=f"event_preview_{filename}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_event_mgr")])
    await callback.message.edit_text("📂 <b>Библиотека Ивентов:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("event_preview_"))
async def event_preview_handler(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    filename = callback.data.split("event_preview_")[1]
    events_db = get_events_db()["files"]
    name = events_db.get(filename, "Неизвестный")
    exists = os.path.exists(f"events/{filename}")
    status = "✅ Файл на месте" if exists else "❌ Файл отсутствует"
    text = f"📂 <b>Предпросмотр:</b>\n\nИмя: {name}\nФайл: {filename}\nСтатус: {status}"
    kb = []
    if exists: kb.append([InlineKeyboardButton(text="🚀 ЗАПУСТИТЬ", callback_data=f"event_launch_{filename}")])
    kb.append([InlineKeyboardButton(text="🗑 УДАЛИТЬ ИЗ БИБЛИОТЕКИ", callback_data=f"event_delete_{filename}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="event_library")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("event_launch_"))
async def event_launch_handler(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    filename = callback.data.split("event_launch_")[1]
    if await activate_event(filename):
        await callback.answer("✅ Ивент запущен!")
        await admin_event_manager(callback)
    else:
        await callback.answer("❌ Ошибка запуска!", show_alert=True)

@dp.callback_query(F.data.startswith("event_delete_"))
async def event_delete_handler(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    filename = callback.data.split("event_delete_")[1]
    path = f"events/{filename}"
    if os.path.exists(path): os.remove(path)
    clean_name = filename.replace(".", "_")
    try: db.reference(f'scripts/{clean_name}').delete()
    except: pass
    db_events = get_events_db()
    if filename in db_events["files"]:
        del db_events["files"][filename]
        save_events_db(db_events)
    await callback.answer("🗑 Ивент удален")
    await event_library_list(callback)

@dp.callback_query(F.data == "event_stop")
async def event_stop_handler(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await activate_event(None)
    settings = load_data("settings.json", {})
    if "active_event_file" in settings:
        del settings["active_event_file"]
        save_data("settings.json", settings)
    await callback.answer("🛑 Ивент остановлен")
    await admin_event_manager(callback)

# --- CORE SETTINGS ---
@dp.callback_query(F.data == "admin_core")
async def admin_core_menu(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    settings = load_data("settings.json", {"maintenance": False})
    m_text = "🟢 Выключить Тех. работы" if settings["maintenance"] else "🔴 Включить Тех. работы"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m_text, callback_data="toggle_maintenance")],
        [InlineKeyboardButton(text="📥 Скачать Бэкап (Firebase)", callback_data="core_backup_zip")],
        [InlineKeyboardButton(text="📤 Загрузить Бэкап (В Firebase)", callback_data="core_upload_backup")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]
    ])
    await callback.message.edit_text("🦊 <b>Настройки бота (FIREBASE)</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "toggle_maintenance")
async def toggle_maintenance_callback(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    settings = load_data("settings.json", {"maintenance": False})
    settings["maintenance"] = not settings["maintenance"]
    save_data("settings.json", settings)
    await callback.answer("Режим изменен!")
    await admin_core_menu(callback)

@dp.callback_query(F.data == "core_backup_zip")
async def download_backup_zip(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer("Скачиваю данные из Firebase...")
    files_to_sync = ["users.json", "games.json", "logs.json", "prefixes.json", "settings.json", "events_db.json", "event_quiz_data.json"]
    for fname in files_to_sync:
        data = load_data(fname, None)
        if data is not None:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    restore_scripts_from_db()
    zip_name = "foxyzihub_firebase_backup.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in files_to_sync:
            if os.path.exists(fname): zf.write(fname, arcname=fname)
        if os.path.exists("events"):
            for root, dirs, files_in_dir in os.walk("events"):
                for file in files_in_dir:
                    if file.endswith(".py") and file != "__init__.py":
                        zf.write(os.path.join(root, file), arcname=os.path.join("events", file))
    await bot.send_document(callback.message.chat.id, FSInputFile(zip_name), caption="💾 Полный бэкап (из Firebase)")
    if os.path.exists(zip_name): os.remove(zip_name)

@dp.callback_query(F.data == "core_upload_backup")
async def wait_for_backup_upload(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    admin_states[OWNER_ID] = {"type": "upload_backup", "msg_id": callback.message.message_id}
    await callback.message.edit_text("📤 <b>Загрузка backup.zip в Облако</b>\n\nОтправь мне архив.",
                                     parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_core")]]))

# --- ОСТАЛЬНЫЕ АДМИН ХЕНДЛЕРЫ ---
@dp.callback_query(F.data == "admin_users_menu")
async def admin_users_menu(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Поиск пользователя", callback_data="admin_users_search")],
        [InlineKeyboardButton(text="📋 Список всех", callback_data="admin_userlist_0")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]
    ])
    await callback.message.edit_text("👥 <b>Управление пользователями</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "admin_users_search")
async def admin_users_search(callback: types.CallbackQuery):
    await callback.answer()
    admin_states[callback.from_user.id] = {"type": "user_search", "msg_id": callback.message.message_id}
    await callback.message.edit_text("🔎 <b>Отправь @username пользователя:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_users_menu")]]))

@dp.callback_query(F.data.startswith("admin_userlist_"))
async def admin_user_list_paged(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    users = load_data("users.json", {})
    if not isinstance(users, dict): users = {}
    user_list = list(users.items())
    items_per_page = 5
    start = page * items_per_page
    end = start + items_per_page
    current = user_list[start:end]
    buttons = []
    for uid, data in current:
        buttons.append([InlineKeyboardButton(text=f"{data['name']} ({data.get('privilege', 'User')})", callback_data=f"edituser_{uid}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_userlist_{page-1}"))
    if end < len(user_list): nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_userlist_{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users_menu")])
    await callback.message.edit_text(f"📋 <b>Список (Стр {page+1})</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("edituser_"))
async def edit_user_menu(callback: types.CallbackQuery):
    uid = callback.data.split("_")[1]
    users = load_data("users.json", {})
    u = users.get(uid)
    if not u: return
    beta_txt = "✅ ВКЛ" if u.get('has_beta') else "❌ ВЫКЛ"
    text = (f"👤 <b>Настройка:</b> {u['name']}\n🔰 Привилегия: {u.get('privilege')}\n🧪 Бета-доступ: {beta_txt}\n🏷 Префикс ID: {u.get('active_prefix')}")
    kb = [
        [InlineKeyboardButton(text="🔰 Изменить Привилегию", callback_data=f"setpriv_{uid}")],
        [InlineKeyboardButton(text=f"🧪 Бета-тест: {beta_txt}", callback_data=f"togglebeta_{uid}")],
        [InlineKeyboardButton(text="🏷 Выдать префиксы", callback_data=f"manageprefixes_{uid}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_userlist_0")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("setpriv_"))
async def set_privilege_menu(callback: types.CallbackQuery):
    uid = callback.data.split("_")[1]
    if int(uid) == OWNER_ID: return
    buttons = [
        [InlineKeyboardButton(text=f"{RANK_PLAYER}", callback_data=f"savepriv_{uid}_player")],
        [InlineKeyboardButton(text=f"{RANK_VIP}", callback_data=f"savepriv_{uid}_vip")]
    ]
    if callback.from_user.id == OWNER_ID: buttons.append([InlineKeyboardButton(text=f"{RANK_ADMIN}", callback_data=f"savepriv_{uid}_admin")])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data=f"edituser_{uid}")])
    await callback.message.edit_text("🔰 <b>Выберите привилегию:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("savepriv_"))
async def save_privilege(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    uid, code = parts[1], parts[2]
    users = load_data("users.json", {})
    if code == "player": new = RANK_PLAYER
    elif code == "vip": new = RANK_VIP
    elif code == "admin": new = RANK_ADMIN
    users[uid]["privilege"] = new
    save_data("users.json", users)
    add_log(callback.from_user.full_name, f"Привилегия {users[uid]['name']} -> {new}")
    await callback.answer("Сохранено!")
    await edit_user_menu(callback)

@dp.callback_query(F.data.startswith("togglebeta_"))
async def toggle_beta(callback: types.CallbackQuery):
    uid = callback.data.split("_")[1]
    users = load_data("users.json", {})
    new_beta = not users[uid].get("has_beta", False)
    users[uid]["has_beta"] = new_beta
    save_data("users.json", users)
    await callback.answer("Бета-доступ изменен")
    callback.data = f"edituser_{uid}" 
    await edit_user_menu(callback)

@dp.callback_query(F.data.startswith("manageprefixes_"))
async def manage_user_prefixes(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    uid = callback.data.split("_")[1]
    users = load_data("users.json", {})
    prefixes_data = load_data("prefixes.json", {"list": []})
    plist = prefixes_data.get("list", []) if isinstance(prefixes_data, dict) else []
    user_prefixes = users[uid].get("unlocked_prefixes", [])
    buttons = []
    for p in plist:
        icon = "✅" if p["id"] in user_prefixes else "❌"
        buttons.append([InlineKeyboardButton(text=f"{icon} {p['text']}", callback_data=f"toggleuprefix_{uid}_{p['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"edituser_{uid}")])
    await callback.message.edit_text(f"🏷 <b>Префиксы:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("toggleuprefix_"))
async def toggle_user_prefix(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    uid, pid = parts[1], parts[2]
    users = load_data("users.json", {})
    if "unlocked_prefixes" not in users[uid]: users[uid]["unlocked_prefixes"] = []
    if pid in users[uid]["unlocked_prefixes"]:
        users[uid]["unlocked_prefixes"].remove(pid)
        if users[uid].get("active_prefix") == pid: users[uid]["active_prefix"] = None
    else: users[uid]["unlocked_prefixes"].append(pid)
    save_data("users.json", users)
    callback.data = f"manageprefixes_{uid}"
    await manage_user_prefixes(callback)

# --- АДМИНКА ПРЕФИКСЫ ---
@dp.callback_query(F.data == "admin_prefixes_menu")
async def admin_prefixes_menu(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    data = load_data("prefixes.json", {"list": []})
    buttons = []
    if isinstance(data, dict) and "list" in data:
        for p in data["list"]:
            buttons.append([InlineKeyboardButton(text=f"❌ {p['text']}", callback_data=f"del_prefix_{p['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Создать префикс", callback_data="add_prefix_start")])
    buttons.append([InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")])
    await callback.message.edit_text("🏷 <b>Управление префиксами</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "add_prefix_start")
async def add_prefix_start(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    admin_states[OWNER_ID] = {"type": "new_prefix", "msg_id": callback.message.message_id}
    await callback.message.edit_text("⌨️ <b>Введи новый префикс</b>:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_prefixes_menu")]]))

@dp.callback_query(F.data.startswith("del_prefix_"))
async def delete_prefix(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    pid = callback.data.split("_")[2]
    data = load_data("prefixes.json", {"list": []})
    if isinstance(data, dict) and "list" in data:
        data["list"] = [p for p in data["list"] if p["id"] != pid]
        save_data("prefixes.json", data)
    await callback.answer("Префикс удален")
    await admin_prefixes_menu(callback)

@dp.callback_query(F.data == "admin_broadcast_start")
async def broadcast_start(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    admin_states[callback.from_user.id] = {"type": "broadcast", "msg_id": callback.message.message_id}
    await callback.message.edit_text("📢 <b>Напиши текст рассылки:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌", callback_data="admin_back")]]))

# --- ИГРЫ ---
@dp.callback_query(F.data == "admin_games")
async def admin_games_menu(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    games_data = load_data("games.json", {"games": []})
    games = games_data.get("games", [])
    buttons = []
    for i, game in enumerate(games):
        icon = "🎮"
        if game.get("access_type") == ACCESS_BETA: icon = "🧪"
        if game.get("access_type") == ACCESS_VIP: icon = "💎"
        buttons.append([InlineKeyboardButton(text=f"{icon} {game['name']}", callback_data=f"editgame_{i}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить игру", callback_data="admin_add_info")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await callback.message.edit_text("🎮 <b>Редактор игр:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("editgame_"))
async def edit_game_menu(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    games = load_data("games.json", {"games": []})["games"]
    game = games[idx]
    access = game.get("access_type", ACCESS_PUBLIC)
    status_text = "👤 Публичная"
    if access == ACCESS_BETA: status_text = "🧪 Бета-тест"
    if access == ACCESS_VIP: status_text = "💎 VIP"
    text = (f"🎮 <b>Редактирование:</b>\n\n🏷 <b>Название:</b> {game['name']}\n📝 <b>Описание:</b> {game['description']}\n👁 <b>{status_text}</b>")
    kb = [
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"changename_{idx}"), InlineKeyboardButton(text="📝 Описание", callback_data=f"changedesc_{idx}")],
        [InlineKeyboardButton(text="👁 Сменить доступ", callback_data=f"cycleaccess_{idx}")],
        [InlineKeyboardButton(text="🗑 УДАЛИТЬ", callback_data=f"ask_del_{idx}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_games")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("cycleaccess_"))
async def cycle_game_access(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    data = load_data("games.json", {"games": []})
    current = data["games"][idx].get("access_type", ACCESS_PUBLIC)
    if current == ACCESS_PUBLIC: new = ACCESS_BETA
    elif current == ACCESS_BETA: new = ACCESS_VIP
    else: new = ACCESS_PUBLIC
    data["games"][idx]["access_type"] = new
    save_data("games.json", data)
    await callback.answer("Изменено")
    callback.data = f"editgame_{idx}"
    await edit_game_menu(callback)

@dp.callback_query(F.data == "admin_add_info")
async def admin_add_info(callback: types.CallbackQuery):
    await callback.answer("Кидай .apk файл!", show_alert=True)

async def admin_upload_game(message: types.Message):
    if not message.caption or "|" not in message.caption:
        await message.answer("❌ Формат: `Название | Описание`", parse_mode="Markdown")
        return
    name, desc = message.caption.split("|", 1)
    temp_games[message.from_user.id] = {"file_id": message.document.file_id, "name": name.strip(), "description": desc.strip()}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Публичная", callback_data="add_public")],
        [InlineKeyboardButton(text="🧪 Бета-тест", callback_data="add_beta")],
        [InlineKeyboardButton(text="💎 VIP", callback_data="add_vip")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="add_cancel")]
    ])
    await message.answer(f"Добавляем: <b>{name.strip()}</b>\nДоступ?", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("add_"))
async def finish_adding(callback: types.CallbackQuery):
    action = callback.data.split("_")[1]
    uid = callback.from_user.id
    if action == "cancel": 
        temp_games.pop(uid, None)
        await callback.message.delete()
        return
    game_data = temp_games.get(uid)
    game_data["access_type"] = action
    data = load_data("games.json", {"games": []})
    data["games"].append(game_data)
    save_data("games.json", data)
    add_log(callback.from_user.full_name, f"Добавил игру ({action}): {game_data['name']}")
    temp_games.pop(uid, None)
    await callback.message.edit_text(f"✅ Игра добавлена!", parse_mode="HTML")

@dp.message()
async def handle_input(message: types.Message):
    if not await check_maintenance(message, message.from_user.id): return
    # ЗАГРУЗКА ИВЕНТА
    if message.document and message.from_user.id == OWNER_ID:
        if message.document.file_name.endswith(".py") and message.caption and "|" in message.caption:
            event_title = message.caption.split("|")[0].strip()
            if not os.path.exists("events"): os.makedirs("events")
            file_name = f"event_{uuid.uuid4().hex[:6]}.py"
            file = await bot.get_file(message.document.file_id)
            # Скачиваем файл в память
            file_bytes = await bot.download_file(file.file_path)
            content = file_bytes.read().decode("utf-8")
            
            # 1. Сохраняем физически
            with open(f"events/{file_name}", "w", encoding="utf-8") as f:
                f.write(content)
            # 2. Сохраняем в FIREBASE
            save_script_to_db(file_name, content)
            
            db_ev = get_events_db()
            db_ev["files"][file_name] = event_title
            save_events_db(db_ev)
            
            await message.delete()
            await message.answer(f"🎉 Ивент <b>{event_title}</b> загружен в облако Firebase!", parse_mode="HTML")
            return

    if is_admin_or_owner(message.from_user.id):
        state = admin_states.get(message.from_user.id)
        if message.document and (not state):
            await admin_upload_game(message)
            return
        
        # ЗАГРУЗКА БЭКАПА ZIP
        if state and state.get("type") == "upload_backup":
            try: await message.delete() 
            except: pass
            msg_id = state.get("msg_id")
            
            if not message.document.file_name.endswith(".zip"): return
            file = await bot.get_file(message.document.file_id)
            await bot.download_file(file.file_path, "import_backup.zip")
            try:
                await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="♻️ Распаковка и заливка в Firebase...", parse_mode="HTML")
                with zipfile.ZipFile("import_backup.zip", "r") as zf:
                    zf.extractall(".")
                    
                # 1. Заливаем JSON файлы в Firebase
                json_files = ["users.json", "games.json", "logs.json", "prefixes.json", "settings.json", "events_db.json", "event_quiz_data.json"]
                for fname in json_files:
                    if os.path.exists(fname):
                        with open(fname, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            save_data(fname, data) 
                
                # 2. Заливаем скрипты ивентов в Firebase
                if os.path.exists("events"):
                    for root, dirs, files_in_dir in os.walk("events"):
                        for file in files_in_dir:
                            if file.endswith(".py"):
                                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                                    content = f.read()
                                    save_script_to_db(file, content)

                admin_states[OWNER_ID] = None
                await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="✅ Бэкап успешно загружен в облако!", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💾 Настройки", callback_data="admin_core")]]))
            except Exception as e:
                await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"❌ Ошибка: {e}", parse_mode="HTML")
            return

        if not state: return
        try: await message.delete()
        except: pass
        msg_id = state.get("msg_id")

        if state["type"] == "new_prefix":
            text = message.text
            new_id = str(uuid.uuid4())[:8]
            data = load_data("prefixes.json", {"list": []})
            if not isinstance(data, dict): data = {"list": []}
            if "list" not in data: data["list"] = []
            data["list"].append({"id": new_id, "text": text})
            save_data("prefixes.json", data)
            admin_states[message.from_user.id] = None
            try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ Префикс <b>{text}</b> создан!", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_prefixes_menu")]]))
            except: pass
        elif state["type"] == "user_search":
            uid, _ = find_user_in_db(message.text)
            admin_states[message.from_user.id] = None
            if uid:
                try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ Нашел: {message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚙️ Управлять", callback_data=f"edituser_{uid}")]]))
                except: pass
            else:
                try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="❌ Не найден", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_users_menu")]]))
                except: pass
        elif state["type"] == "broadcast":
            text_to_send = message.text
            admin_states[message.from_user.id] = None
            users = load_data("users.json", {})
            count = 0
            if isinstance(users, dict):
                for u in users:
                    try:
                        await bot.send_message(u, f"📢 <b>ОПОВЕЩЕНИЕ</b>\n\n{text_to_send}", parse_mode="HTML")
                        count += 1
                        await asyncio.sleep(0.05)
                    except: pass
            add_log(message.from_user.full_name, f"Рассылка: {text_to_send[:30]}...")
            try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ Разослано: {count}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_back")]]))
            except: pass
        elif state["type"] == "edit_name":
            data = load_data("games.json", {})
            data["games"][state["idx"]]["name"] = message.text
            save_data("games.json", data)
            admin_states[message.from_user.id] = None
            try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="✅ Имя изменено", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data=f"editgame_{state['idx']}")]]))
            except: pass
        elif state["type"] == "edit_desc":
            data = load_data("games.json", {})
            data["games"][state["idx"]]["description"] = message.text
            save_data("games.json", data)
            admin_states[message.from_user.id] = None
            try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text="✅ Описание изменено", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data=f"editgame_{state['idx']}")]]))
            except: pass

@dp.callback_query(F.data.startswith("ask_del_"))
async def delete_game_direct(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    idx = int(callback.data.split("_")[-1])
    data = load_data("games.json", {"games": []})
    if idx < len(data["games"]):
        data["games"].pop(idx)
        save_data("games.json", data)
        await callback.answer("🗑 Удалено", show_alert=True)
    await admin_games_menu(callback)

async def main():
    # При запуске восстанавливаем все скрипты из базы!
    restore_scripts_from_db()
    
    logger.info("🦊 FoxyZiHub v12.1 (FIREBASE CORE + BRIDGE) запущен!")
    
    settings = load_data("settings.json", {})
    active_file = settings.get("active_event_file")
    if active_file:
        await activate_event(active_file)

    try:
        await start_web_server()
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())

