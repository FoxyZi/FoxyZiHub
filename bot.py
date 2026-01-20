import json
import asyncio
import os
import sys
import logging # Добавлено логирование
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

# ═══════════════════════════════════════════
# ⚙️ НАСТРОЙКИ ЛОГИРОВАНИЯ (Чтобы видеть ошибки в Render)
# ═══════════════════════════════════════════
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# ⚙️ НАСТРОЙКИ БОТА
# ═══════════════════════════════════════════

BOT_TOKEN = "8261897648:AAE1P80ALDJQD9xtJv3nTNA_GLdZlalaVb8"
OWNER_ID = 6057537422

# Роли
ROLE_PLAYER = "Игрок 👤"
ROLE_BETA = "Бета-тестер 🧪"
ROLE_ADMIN = "Администратор 👑"
ROLE_OWNER = "Главный Лис 🦊"

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
# 🌍 ФЕЙКОВЫЙ СЕРВЕР (ИСПРАВЛЕННЫЙ)
# ═══════════════════════════════════════════
async def health_check(request):
    return web.Response(text="🦊 FoxyZiHub is alive!", status=200)

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', health_check)])
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Получаем порт от Render или используем 8080
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌍 Запускаю веб-сервер на порту: {port}")
    
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ═══════════════════════════════════════════
# 📂 БАЗА ДАННЫХ И ЛОГИ
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
    entry = f"[{timestamp}] 👤 {admin_name}: {text}"
    logs.insert(0, entry)
    if len(logs) > 200: logs.pop()
    save_data("logs.json", logs)

def get_user(user_id):
    users = load_data("users.json", {})
    user_data = users.get(str(user_id), {"role": ROLE_PLAYER, "name": "Неизвестный", "username": "None"})
    if user_id == OWNER_ID: user_data["role"] = ROLE_OWNER
    return user_data

def update_user(user):
    users = load_data("users.json", {})
    user_id = str(user.id)
    current_role = users.get(user_id, {}).get("role", ROLE_PLAYER)
    if user.id == OWNER_ID: current_role = ROLE_OWNER
    elif current_role == ROLE_OWNER: current_role = ROLE_PLAYER
    users[user_id] = {"name": user.full_name, "username": user.username, "role": current_role}
    save_data("users.json", users)

def find_user_in_db(query):
    users = load_data("users.json", {})
    query = query.replace("@", "").lower().strip()
    for uid, data in users.items():
        if data.get("username", "").lower() == query: return uid, data
    return None, None

def is_admin_or_owner(user_id):
    user = get_user(user_id)
    return user["role"] == ROLE_ADMIN

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
    
    update_user(message.from_user)
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
    # Исправляем получение имени для отображения (если функция отсутствовала)
    display_name = user['name']
    
    # Получаем префикс если есть
    prefix_text = ""
    prefixes = load_data("prefixes.json", {"list": []})["list"]
    if user.get("active_prefix"):
        for p in prefixes:
            if p["id"] == user["active_prefix"]:
                prefix_text = f"<b>{p['text']}</b> "
                break
    
    display_name = f"{prefix_text}{user['name']}"
    
    beta_status = "✅ Есть" if user.get("has_beta") else "❌ Нет"
    
    text = (f"👤 <b>Твой профиль:</b>\n\n"
            f"🏷 <b>Ник:</b> {display_name}\n"
            f"🔰 <b>Привилегия:</b> {user.get('privilege', ROLE_PLAYER)}\n"
            f"🧪 <b>Бета-тест:</b> {beta_status}")

    buttons = []
    if user.get("unlocked_prefixes"):
        buttons.append([InlineKeyboardButton(text="🏷 Выбрать префикс", callback_data="profile_prefixes")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "profile_prefixes")
async def choose_prefix_menu(callback: types.CallbackQuery):
    if not await check_maintenance(callback, callback.from_user.id): return
    
    user = get_user(callback.from_user.id)
    prefixes_db = load_data("prefixes.json", {"list": []})["list"]
    
    buttons = []
    active = "✅ " if user.get("active_prefix") is None else ""
    buttons.append([InlineKeyboardButton(text=f"{active}Без префикса", callback_data="set_my_prefix_none")])
    
    for pid in user.get("unlocked_prefixes", []):
        p_text = next((p["text"] for p in prefixes_db if p["id"] == pid), "???")
        is_active = "✅ " if user.get("active_prefix") == pid else ""
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
    games = load_data("games.json", {"games": []})["games"]
    if idx >= len(games): return
    
    game = games[idx]
    user = get_user(callback.from_user.id)
    access = game.get("access_type", ACCESS_PUBLIC)
    
    if access == ACCESS_BETA:
        if not (user.get("has_beta") or user.get("privilege") in [RANK_ADMIN, RANK_OWNER]):
            await callback.answer("⛔ Только для Бета-тестеров!", show_alert=True)
            return
            
    if access == ACCESS_VIP:
        if not user.get("privilege") in [RANK_VIP, RANK_ADMIN, RANK_OWNER]:
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
    new_beta = not users[uid].get("has_beta", False)
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
    uid 

