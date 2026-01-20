import json
import asyncio
import os
import uuid
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# ═══════════════════════════════════════════
# ⚙️ НАСТРОЙКИ
# ═══════════════════════════════════════════

BOT_TOKEN = "8261897648:AAE1P80ALDJQD9xtJv3nTNA_GLdZlalaVb8"
OWNER_ID = 6057537422  # ID ГЛАВНОГО ЛИСА

# Привилегии
RANK_PLAYER = "Игрок"
RANK_VIP = "VIP 💎"
RANK_ADMIN = "Администратор 👑"
RANK_OWNER = "Главный Лис 🦊"

# Доступ
ACCESS_PUBLIC = "public"
ACCESS_VIP = "vip"
ACCESS_BETA = "beta"

# ═══════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
temp_games = {} 
admin_states = {} 

# ═══════════════════════════════════════════
# 🌍 ФЕЙКОВЫЙ СЕРВЕР
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
# 📂 БАЗА ДАННЫХ И УТИЛИТЫ
# ═══════════════════════════════════════════
def load_data(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_log(admin_name, text):
    logs = load_data("logs.json", [])
    timestamp = datetime.now().strftime("%d.%m %H:%M")
    logs.insert(0, f"[{timestamp}] 👤 {admin_name}: {text}")
    if len(logs) > 200: logs.pop()
    save_data("logs.json", logs)

# --- ПРОВЕРКА ТЕХНИЧЕСКИХ РАБОТ (ТИХИЙ РЕЖИМ) ---
async def check_maintenance(event, user_id):
    settings = load_data("settings.json", {"maintenance": False})
    
    # 1. Если тех. работы выключены - разрешаем
    if not settings.get("maintenance", False):
        return True
        
    # 2. Если это Главный Лис - разрешаем всегда
    if user_id == OWNER_ID:
        return True
        
    # 3. Иначе - МОЛЧИМ (Блокируем выполнение, ничего не отправляем)
    # Пользователь подумает, что бот выключен
    if isinstance(event, types.CallbackQuery):
        # Для кнопок можно отправить пустой ответ, чтобы убрать "часики", 
        # но чтобы выглядело совсем как "выключен", можно даже это не делать.
        # Но лучше сбросить ожидание, чтобы клиент телеграма не висел.
        try: await event.answer() 
        except: pass
        
    return False

# --- ПОЛЬЗОВАТЕЛИ ---
def get_user(user_id):
    users = load_data("users.json", {})
    uid = str(user_id)
    default_user = {
        "name": "Неизвестный",
        "username": "None",
        "privilege": RANK_PLAYER,
        "has_beta": False,
        "unlocked_prefixes": [],
        "active_prefix": None
    }
    user = users.get(uid, default_user)
    
    if "role" in user:
        user["privilege"] = RANK_PLAYER
        user["has_beta"] = False
        del user["role"]
        
    if user_id == OWNER_ID:
        user["privilege"] = RANK_OWNER
        user["has_beta"] = True
        
    return user

def update_user_info(user_tg):
    users = load_data("users.json", {})
    uid = str(user_tg.id)
    user_data = users.get(uid, {
        "privilege": RANK_PLAYER,
        "has_beta": False,
        "unlocked_prefixes": [],
        "active_prefix": None
    })
    
    if user_tg.id == OWNER_ID: 
        user_data["privilege"] = RANK_OWNER
        user_data["has_beta"] = True

    user_data["name"] = user_tg.full_name
    user_data["username"] = user_tg.username
    users[uid] = user_data
    save_data("users.json", users)

def find_user_in_db(query):
    users = load_data("users.json", {})
    query = query.replace("@", "").lower().strip()
    for uid, data in users.items():
        if data.get("username", "").lower() == query: return uid, data
    return None, None

def is_admin_or_owner(user_id):
    user = get_user(user_id)
    return user["privilege"] in [RANK_ADMIN, RANK_OWNER]

def get_user_display_name(user_id):
    user = get_user(user_id)
    prefix_text = ""
    prefixes = load_data("prefixes.json", {"list": []})["list"]
    
    if user.get("active_prefix"):
        for p in prefixes:
            if p["id"] == user["active_prefix"]:
                prefix_text = f"<b>{p['text']}</b> "
                break
                
    return f"{prefix_text}{user['name']}"

# ═══════════════════════════════════════════
# 🏠 ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════
def main_menu(user_id):
    buttons = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🎮 Список игр", callback_data="games_list")]
    ]
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
    beta_status = "✅ Есть" if user["has_beta"] else "❌ Нет"
    
    text = (f"👤 <b>Твой профиль:</b>\n\n"
            f"🏷 <b>Ник:</b> {display_name}\n"
            f"🔰 <b>Привилегия:</b> {user['privilege']}\n"
            f"🧪 <b>Бета-тест:</b> {beta_status}")

    buttons = []
    if user["unlocked_prefixes"]:
        buttons.append([InlineKeyboardButton(text="🏷 Выбрать префикс", callback_data="profile_prefixes")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "profile_prefixes")
async def choose_prefix_menu(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    
    user = get_user(callback.from_user.id)
    prefixes_db = load_data("prefixes.json", {"list": []})["list"]
    
    buttons = []
    active = "✅ " if user["active_prefix"] is None else ""
    buttons.append([InlineKeyboardButton(text=f"{active}Без префикса", callback_data="set_my_prefix_none")])
    
    for pid in user["unlocked_prefixes"]:
        p_text = next((p["text"] for p in prefixes_db if p["id"] == pid), "???")
        is_active = "✅ " if user["active_prefix"] == pid else ""
        buttons.append([InlineKeyboardButton(text=f"{is_active}{p_text}", callback_data=f"set_my_prefix_{pid}")])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="profile")])
    await callback.message.edit_text("🏷 <b>Выбери префикс:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("set_my_prefix_"))
async def set_own_prefix(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    
    prefix_id = callback.data.split("_", 3)[3]
    if prefix_id == "none": prefix_id = None
    
    users = load_data("users.json", {})
    uid = str(callback.from_user.id)
    if uid in users:
        users[uid]["active_prefix"] = prefix_id
        save_data("users.json", users)
    
    await callback.answer("Префикс обновлен!")
    await show_profile(callback)

@dp.callback_query(F.data == "back_home")
async def back_home(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    await callback.answer()
    await callback.message.edit_text("🦊 <b>FoxyZiHub</b>\nМеню:", parse_mode="HTML", reply_markup=main_menu(callback.from_user.id))

# ═══════════════════════════════════════════
# 🎮 КЛИЕНТ (Игры)
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "games_list")
async def show_games_list(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    await callback.answer()
    
    games = load_data("games.json", {"games": []})["games"]
    user = get_user(callback.from_user.id)
    
    is_beta_tester = user["has_beta"] or user["privilege"] in [RANK_ADMIN, RANK_OWNER]
    
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
    games = load_data("games.json", {"games": []})["games"]
    if idx >= len(games): return
    
    game = games[idx]
    user = get_user(callback.from_user.id)
    access = game.get("access_type", ACCESS_PUBLIC)
    
    if access == ACCESS_BETA:
        if not (user["has_beta"] or user["privilege"] in [RANK_ADMIN, RANK_OWNER]):
            await callback.answer("⛔ Только для Бета-тестеров!", show_alert=True)
            return
            
    if access == ACCESS_VIP:
        if not user["privilege"] in [RANK_VIP, RANK_ADMIN, RANK_OWNER]:
            await callback.answer("⛔ Только для VIP игроков!", show_alert=True)
            return

    await callback.answer("📤 Загрузка файла...")
    await bot.send_document(callback.message.chat.id, document=game["file_id"], caption=f"🦊 <b>{game['name']}</b>\n\n📝 {game['description']}", parse_mode="HTML")

# ═══════════════════════════════════════════
# 👑 АДМИН-ПАНЕЛЬ
# ═══════════════════════════════════════════
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin_or_owner(message.from_user.id): return
    await open_admin_panel(message)

@dp.callback_query(F.data == "admin_open_menu")
async def callback_admin(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
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
        buttons.append([InlineKeyboardButton(text="💾 Настройки бота", callback_data="admin_core")])
        
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])
    
    text = "👑 <b>Админ-панель</b>"
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

# ═══════════════════════════════════════════
# 🏷 УПРАВЛЕНИЕ ПРЕФИКСАМИ
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "admin_prefixes_menu")
async def admin_prefixes_menu(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    data = load_data("prefixes.json", {"list": []})
    buttons = []
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
    await callback.message.edit_text("⌨️ <b>Введи новый префикс</b>:", parse_mode="HTML", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_prefixes_menu")]]))

@dp.callback_query(F.data.startswith("del_prefix_"))
async def delete_prefix(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    pid = callback.data.split("_")[2]
    data = load_data("prefixes.json", {"list": []})
    data["list"] = [p for p in data["list"] if p["id"] != pid]
    save_data("prefixes.json", data)
    await callback.answer("Префикс удален")
    await admin_prefixes_menu(callback)

# ═══════════════════════════════════════════
# 👥 УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "admin_users_menu")
async def admin_users_menu(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    text = "👥 <b>Управление пользователями</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Поиск пользователя", callback_data="admin_users_search")],
        [InlineKeyboardButton(text="📋 Список всех", callback_data="admin_userlist_0")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "admin_users_search")
async def admin_users_search(callback: types.CallbackQuery):
    await callback.answer()
    admin_states[callback.from_user.id] = {"type": "user_search", "msg_id": callback.message.message_id}
    await callback.message.edit_text("🔎 <b>Отправь @username:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_users_menu")]]))

@dp.callback_query(F.data.startswith("admin_userlist_"))
async def admin_user_list_paged(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    users = load_data("users.json", {})
    user_list = list(users.items())
    items_per_page = 5
    start = page * items_per_page
    end = start + items_per_page
    current = user_list[start:end]
    buttons = []
    for uid, data in current:
        buttons.append([InlineKeyboardButton(text=f"{data['name']} ({data['privilege']})", callback_data=f"edituser_{uid}")])
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
    beta_txt = "✅ ВКЛ" if u['has_beta'] else "❌ ВЫКЛ"
    text = (f"👤 <b>Настройка:</b> {u['name']}\n🔰 Привилегия: {u['privilege']}\n🧪 Бета-доступ: {beta_txt}\n🏷 Префикс ID: {u['active_prefix']}")
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
    uid, role_code = parts[1], parts[2]
    users = load_data("users.json", {})
    if role_code == "player": new = RANK_PLAYER
    elif role_code == "vip": new = RANK_VIP
    elif role_code == "admin": new = RANK_ADMIN
    users[uid]["privilege"] = new
    save_data("users.json", users)
    add_log(callback.from_user.full_name, f"Привилегия {users[uid]['name']} -> {new}")
    await callback.answer("Сохранено!")
    try: await bot.send_message(uid, f"🔔 <b>Уведомление!</b>\n\nВаша привилегия изменена на: {new}", parse_mode="HTML")
    except: pass
    await edit_user_menu(callback)

@dp.callback_query(F.data.startswith("togglebeta_"))
async def toggle_beta(callback: types.CallbackQuery):
    uid = callback.data.split("_")[1]
    users = load_data("users.json", {})
    new_beta = not users[uid]["has_beta"]
    users[uid]["has_beta"] = new_beta
    save_data("users.json", users)
    await callback.answer("Бета-доступ изменен")
    
    status = "✅ ВКЛ" if new_beta else "❌ ВЫКЛ"
    try: await bot.send_message(uid, f"🔔 <b>Уведомление!</b>\n\nБета-доступ: {status}", parse_mode="HTML")
    except: pass
    
    callback.data = f"edituser_{uid}" 
    await edit_user_menu(callback)

@dp.callback_query(F.data.startswith("manageprefixes_"))
async def manage_user_prefixes(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только Главный Лис управляет префиксами", show_alert=True)
        return
    uid = callback.data.split("_")[1]
    users = load_data("users.json", {})
    prefixes_db = load_data("prefixes.json", {"list": []})["list"]
    user_prefixes = users[uid]["unlocked_prefixes"]
    buttons = []
    for p in prefixes_db:
        icon = "✅" if p["id"] in user_prefixes else "❌"
        buttons.append([InlineKeyboardButton(text=f"{icon} {p['text']}", callback_data=f"toggleuprefix_{uid}_{p['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"edituser_{uid}")])
    await callback.message.edit_text(f"🏷 <b>Префиксы:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("toggleuprefix_"))
async def toggle_user_prefix(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    uid, pid = parts[1], parts[2]
    users = load_data("users.json", {})
    if pid in users[uid]["unlocked_prefixes"]:
        users[uid]["unlocked_prefixes"].remove(pid)
        if users[uid]["active_prefix"] == pid: users[uid]["active_prefix"] = None
    else: users[uid]["unlocked_prefixes"].append(pid)
    save_data("users.json", users)
    callback.data = f"manageprefixes_{uid}"
    await manage_user_prefixes(callback)

# ═══════════════════════════════════════════
# 💾 НАСТРОЙКИ БОТА (ЯДРО + ТЕХ РАБОТЫ)
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "admin_core")
async def admin_core_menu(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    
    settings = load_data("settings.json", {"maintenance": False})
    m_text = "🟢 Выключить Тех. работы" if settings["maintenance"] else "🔴 Включить Тех. работы"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=m_text, callback_data="toggle_maintenance")],
        [InlineKeyboardButton(text="📥 Скачать Бэкап (Все)", callback_data="core_backup_download")],
        [InlineKeyboardButton(text="📥 Скачать logs.json", callback_data="core_download_logs")],
        [InlineKeyboardButton(text="📤 Загрузить users.json", callback_data="core_upload_users")],
        [InlineKeyboardButton(text="📤 Загрузить games.json", callback_data="core_upload_games")],
        [InlineKeyboardButton(text="📤 Загрузить settings.json", callback_data="core_upload_settings")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]
    ])
    await callback.message.edit_text("🦊 <b>Настройки бота</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "toggle_maintenance")
async def toggle_maintenance_callback(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    settings = load_data("settings.json", {"maintenance": False})
    settings["maintenance"] = not settings["maintenance"]
    save_data("settings.json", settings)
    await callback.answer("Режим изменен!")
    await admin_core_menu(callback)

@dp.callback_query(F.data == "core_backup_download")
async def download_backup(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer("Отправляю...")
    for f in ["users.json", "games.json", "logs.json", "prefixes.json", "settings.json"]:
        if os.path.exists(f): 
            try: await bot.send_document(callback.message.chat.id, FSInputFile(f))
            except: pass

@dp.callback_query(F.data == "core_download_logs")
async def download_logs_only(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer("Отправляю...")
    if os.path.exists("logs.json"): await bot.send_document(callback.message.chat.id, FSInputFile("logs.json"))

@dp.callback_query(F.data.startswith("core_upload_"))
async def wait_for_upload(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    file_type = callback.data.split("_")[2]
    target_file = f"{file_type}.json"
    admin_states[OWNER_ID] = {"type": "upload_db", "file": target_file, "msg_id": callback.message.message_id}
    await callback.message.edit_text(f"📤 <b>Загрузка {target_file}</b>\nКидай файл.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌", callback_data="admin_core")]]))

# ═══════════════════════════════════════════
# 📢 ОПОВЕЩЕНИЯ
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "admin_broadcast_start")
async def broadcast_start(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    admin_states[callback.from_user.id] = {"type": "broadcast", "msg_id": callback.message.message_id}
    await callback.message.edit_text("📢 <b>Напиши текст рассылки:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌", callback_data="admin_back")]]))

# ═══════════════════════════════════════════
# 🎮 УПРАВЛЕНИЕ ИГРАМИ (АДМИНКА)
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "admin_games")
async def admin_games_menu(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    games = load_data("games.json", {"games": []})["games"]
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
    
    text = (f"🎮 <b>Редактирование:</b>\n\n🏷 {game['name']}\n📝 {game['description']}\n👁 <b>{status_text}</b>")
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

# --- ДОБАВЛЕНИЕ ИГРЫ ---
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

# ═══════════════════════════════════════════
# 📜 ЛОГИ (Только просмотр)
# ═══════════════════════════════════════════
@dp.callback_query(F.data.startswith("admin_logs_"))
async def show_logs(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    
    page = int(callback.data.split("_")[2])
    logs = load_data("logs.json", [])
    
    if not logs:
        await callback.message.edit_text("📜 <b>Логи пусты.</b>", parse_mode="HTML", 
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]]))
        return

    items_per_page = 10
    start = page * items_per_page
    end = start + items_per_page
    current_logs = logs[start:end]
    
    text = f"📜 <b>Логи действий (Стр. {page + 1}):</b>\n\n"
    text += "\n\n".join(current_logs)
    
    buttons = []
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton(text="⬅️ Туда", callback_data=f"admin_logs_{page-1}"))
    if end < len(logs): nav_buttons.append(InlineKeyboardButton(text="Сюда ➡️", callback_data=f"admin_logs_{page+1}"))
        
    if nav_buttons: buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# ═══════════════════════════════════════════
# ОБРАБОТЧИК ВВОДА (ГЛАВНЫЙ)
# ═══════════════════════════════════════════
@dp.message()
async def handle_input(message: types.Message):
    # ПРОВЕРКА ТЕХ РАБОТ ДЛЯ ВСЕХ
    if not await check_maintenance(message, message.from_user.id): return

    # ЗАГРУЗКА БЭКАПОВ (Только Лис)
    if message.document and message.from_user.id == OWNER_ID:
        state = admin_states.get(OWNER_ID)
        if state and state.get("type") == "upload_db":
            expected_file = state["file"]
            msg_id = state.get("msg_id")
            try: await message.delete()
            except: pass
            if message.document.file_name == expected_file:
                file = await bot.get_file(message.document.file_id)
                await bot.download_file(file.file_path, expected_file)
                admin_states[OWNER_ID] = None
                try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ <b>{expected_file}</b> восстановлен!", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💾 Настройки", callback_data="admin_core")]]))
                except: pass
                return

    if is_admin_or_owner(message.from_user.id):
        state = admin_states.get(message.from_user.id)
        if message.document and (not state or state.get("type") != "upload_db"):
            await admin_upload_game(message)
            return
        if not state: return

        try: await message.delete()
        except: pass
        msg_id = state.get("msg_id")

        if state["type"] == "new_prefix":
            text = message.text
            new_id = str(uuid.uuid4())[:8]
            data = load_data("prefixes.json", {"list": []})
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
            for u in users:
                try:
                    await bot.send_message(u, f"📢 <b>ОПОВЕЩЕНИЕ</b>\n\n{text_to_send}", parse_mode="HTML")
                    count += 1
                    await asyncio.sleep(0.05)
                except: pass
            add_log(message.from_user.full_name, f"Рассылка: {text_to_send[:20]}...")
            try: await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ Разослано: {count}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_back")]]))
            except: pass

        # Обработчики имени и описания игры (оставлены как были, работают)
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

# ═══════════════════════════════════════════
# ЗАПУСК
# ═══════════════════════════════════════════
async def main():
    print("🦊 FoxyZiHub v4.0 (Maintenance Mode) запущен!")
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
