import json
import asyncio
import os
import math
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

# Роли
ROLE_PLAYER = "Игрок 👤"
ROLE_BETA = "Бета-тестер 🧪"
ROLE_ADMIN = "Администратор 👑"
ROLE_OWNER = "Главный Лис 🦊"

# ═══════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
temp_games = {} 
admin_states = {} 

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
    if user_id == OWNER_ID: return True
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
    update_user(message.from_user)
    await message.answer("🦊 <b>Добро пожаловать в FoxyZiHub!</b>\n\nЗдесь ты найдёшь мои игры.\nВыбери пункт меню ниже 👇",
                         parse_mode="HTML", reply_markup=main_menu(message.from_user.id))

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message): await cmd_start(message)

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    await callback.answer()
    user_data = get_user(callback.from_user.id)
    await callback.message.edit_text(f"👤 <b>Твой профиль:</b>\n\n📛 <b>Имя:</b> {user_data['name']}\n🔰 <b>Твой статус:</b> {user_data['role']}",
                                     parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")]]))

@dp.callback_query(F.data == "back_home")
async def back_home(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("🦊 <b>FoxyZiHub</b>\nМеню:", parse_mode="HTML", reply_markup=main_menu(callback.from_user.id))

# ═══════════════════════════════════════════
# 🎮 КЛИЕНТ (Игры)
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "games_list")
async def show_games_list(callback: types.CallbackQuery):
    await callback.answer()
    games = load_data("games.json", {"games": []})["games"]
    user = get_user(callback.from_user.id)
    can_see_beta = user["role"] in [ROLE_OWNER, ROLE_ADMIN, ROLE_BETA]
    
    buttons = []
    has_games = False
    for i, game in enumerate(games):
        is_beta = game.get("is_beta", False)
        if is_beta and not can_see_beta: continue
        icon = "🧪" if is_beta else "🎮"
        buttons.append([InlineKeyboardButton(text=f"{icon} {game['name']}", callback_data=f"dl_{i}")])
        has_games = True
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")])
    text = "🎮 <b>Список игр:</b>\nНажми, чтобы скачать:" if has_games else "😔 <b>Игр пока нет.</b>\nЗаходи позже!"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("dl_"))
async def download_game(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    games = load_data("games.json", {"games": []})["games"]
    if idx >= len(games): 
        await callback.answer("Ошибка")
        return
    game = games[idx]
    user = get_user(callback.from_user.id)
    can_see_beta = user["role"] in [ROLE_OWNER, ROLE_ADMIN, ROLE_BETA]
    if game.get("is_beta", False) and not can_see_beta:
        await callback.answer("⛔ Доступно только тестерам!", show_alert=True)
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
        [InlineKeyboardButton(text="📢 Сделать оповещение", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton(text="👥 Управление ролями", callback_data="admin_roles_menu")],
        [InlineKeyboardButton(text="🎮 Управление играми", callback_data="admin_games")],
        [InlineKeyboardButton(text="📜 Логи действий", callback_data="admin_logs_0")]
    ]
    if uid == OWNER_ID:
        buttons.append([InlineKeyboardButton(text="💾 Настройки бота", callback_data="admin_core")])
        
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])
    
    text = "👑 <b>Админ-панель</b>"
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

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
# 📢 ОПОВЕЩЕНИЯ (НОВОЕ!)
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "admin_broadcast_start")
async def broadcast_start(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    
    admin_states[callback.from_user.id] = {"type": "broadcast", "msg_id": callback.message.message_id}
    
    await callback.message.edit_text(
        "📢 <b>Рассылка оповещения</b>\n\n"
        "Напиши текст сообщения, который получат <b>все пользователи</b> бота.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]])
    )

# ═══════════════════════════════════════════
# 📜 ЛОГИ
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
# 💾 ЯДРО СИСТЕМЫ
# ═══════════════════════════════════════════
@dp.callback_query(F.data == "admin_core")
async def admin_core_menu(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    text = "🦊 <b>Настройки бота</b>\n\nУправление данными бота."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать Бэкап (Все)", callback_data="core_backup_download")],
        [InlineKeyboardButton(text="📥 Скачать logs.json", callback_data="core_download_logs")],
        [InlineKeyboardButton(text="📤 Загрузить users.json", callback_data="core_upload_users")],
        [InlineKeyboardButton(text="📤 Загрузить games.json", callback_data="core_upload_games")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "core_backup_download")
async def download_backup(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer("Отправляю файлы...")
    try:
        if os.path.exists("users.json"): await bot.send_document(callback.message.chat.id, FSInputFile("users.json"), caption="👥 База пользователей")
        if os.path.exists("games.json"): await bot.send_document(callback.message.chat.id, FSInputFile("games.json"), caption="🎮 База игр")
        if os.path.exists("logs.json"): await bot.send_document(callback.message.chat.id, FSInputFile("logs.json"), caption="📜 Логи")
    except Exception as e: await callback.message.answer(f"Ошибка: {e}")

@dp.callback_query(F.data == "core_download_logs")
async def download_logs_only(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer("Отправляю логи...")
    try:
        if os.path.exists("logs.json"):
            await bot.send_document(callback.message.chat.id, FSInputFile("logs.json"), caption="📜 Логи действий")
        else:
            await callback.message.answer("⚠️ Логов пока нет.")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")

@dp.callback_query(F.data.startswith("core_upload_"))
async def wait_for_upload(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.answer()
    file_type = callback.data.split("_")[2]
    target_file = f"{file_type}.json"
    
    admin_states[OWNER_ID] = {"type": "upload_db", "file": target_file, "msg_id": callback.message.message_id}
    
    await callback.message.edit_text(f"📤 <b>Загрузка {target_file}</b>\n\nОтправь мне файл.",
                                     parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_core")]]))

# ═══════════════════════════════════════════
# 👥 УПРАВЛЕНИЕ РОЛЯМИ
# ═══════════════════════════════════════════

@dp.callback_query(F.data == "admin_roles_menu")
async def admin_roles_menu_select(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    
    text = "👥 <b>Управление ролями</b>\n\nКак найти пользователя?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Поиск по @username", callback_data="admin_roles_search")],
        [InlineKeyboardButton(text="📋 Список всех (по 5)", callback_data="admin_userlist_0")],
        [InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("admin_userlist_"))
async def admin_user_list(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    
    page = int(callback.data.split("_")[2])
    users = load_data("users.json", {})
    user_list = list(users.items())
    
    if not user_list:
        await callback.message.edit_text("Список пуст.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_roles_menu")]]))
        return

    items_per_page = 5
    start = page * items_per_page
    end = start + items_per_page
    current_users = user_list[start:end]
    
    buttons = []
    for uid, data in current_users:
        role_icon = "👤"
        if data['role'] == ROLE_BETA: role_icon = "🧪"
        elif data['role'] == ROLE_ADMIN: role_icon = "👑"
        elif data['role'] == ROLE_OWNER: role_icon = "🦊"
        
        btn_text = f"{role_icon} {data['name']}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"manageuser_{uid}")])

    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_userlist_{page-1}"))
    if end < len(user_list): nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_userlist_{page+1}"))
    
    if nav_buttons: buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_roles_menu")])
    
    await callback.message.edit_text(f"📋 <b>Список пользователей (Стр. {page + 1})</b>:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_roles_search")
async def admin_roles_search_start(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    admin_states[callback.from_user.id] = {"type": "waiting_user", "msg_id": callback.message.message_id}
    await callback.message.edit_text("🔎 <b>Поиск пользователя</b>\n\nОтправь мне <b>@username</b> пользователя.",
                                     parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_roles_menu")]]))

@dp.callback_query(F.data.startswith("manageuser_"))
async def manage_single_user(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    target_uid = callback.data.split("_")[1]
    
    users = load_data("users.json", {})
    user_data = users.get(target_uid)
    
    if not user_data:
        await callback.message.edit_text("Пользователь не найден.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="admin_roles_menu")]]))
        return

    buttons = [
        [InlineKeyboardButton(text="Сделать Игроком 👤", callback_data=f"setrole_{target_uid}_player")],
        [InlineKeyboardButton(text="Сделать Бета-тестером 🧪", callback_data=f"setrole_{target_uid}_beta")]
    ]
    if callback.from_user.id == OWNER_ID:
        buttons.append([InlineKeyboardButton(text="Сделать Админом 👑", callback_data=f"setrole_{target_uid}_admin")])
        
    buttons.append([InlineKeyboardButton(text="🔙 К списку", callback_data="admin_userlist_0")])

    text = f"👤 <b>Настройка прав:</b>\n\n📛 {user_data['name']}\n📎 @{user_data['username']}\n🔰 Роль: {user_data['role']}"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("setrole_"))
async def set_role_callback(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    _, uid, role_code = callback.data.split("_")
    
    if role_code == "player": new_role = ROLE_PLAYER
    elif role_code == "beta": new_role = ROLE_BETA
    elif role_code == "admin": new_role = ROLE_ADMIN
    else: return

    if new_role == ROLE_ADMIN and callback.from_user.id != OWNER_ID:
        await callback.message.answer("⛔ Только Главный Лис может назначать администраторов.")
        return

    users = load_data("users.json", {})
    if uid in users:
        if int(uid) == OWNER_ID:
             await callback.message.answer("❌ Нельзя изменить роль Главного Лиса.")
             return

        current_target_role = users[uid].get("role", ROLE_PLAYER)
        if current_target_role == ROLE_ADMIN and callback.from_user.id != OWNER_ID:
             await callback.message.answer("⛔ Вы не можете менять роль другим Администраторам.")
             return

        old_role = users[uid].get("role", ROLE_PLAYER)
        users[uid]["role"] = new_role
        save_data("users.json", users)
        
        add_log(callback.from_user.full_name, f"Роль {users[uid]['name']}: {old_role} -> {new_role}")
        
        await callback.message.edit_text(f"✅ Роль для {users[uid]['name']} изменена на:\n<b>{new_role}</b>", 
                                         parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К списку", callback_data="admin_userlist_0")]]))
        
        try: await bot.send_message(uid, f"🔔 <b>Уведомление!</b>\n\nВаша роль была изменена на: {new_role}", parse_mode="HTML")
        except: pass

# --- ИГРЫ ---
@dp.callback_query(F.data == "admin_games")
async def admin_games_menu(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    games = load_data("games.json", {"games": []})["games"]
    buttons = []
    for i, game in enumerate(games):
        icon = "🧪" if game.get("is_beta") else "👤"
        buttons.append([InlineKeyboardButton(text=f"{icon} {game['name']}", callback_data=f"editgame_{i}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить игру", callback_data="admin_add_info")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await callback.message.edit_text("🎮 <b>Редактор игр:</b>\nНажми на игру, чтобы изменить или удалить.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("editgame_"))
async def edit_game_menu(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    idx = int(callback.data.split("_")[1])
    games = load_data("games.json", {"games": []})["games"]
    if idx >= len(games): return
    game = games[idx]
    status = "🧪 Бета-тест" if game.get("is_beta") else "👤 Публичная"
    text = (f"🎮 <b>Редактирование:</b>\n\n🏷 <b>Название:</b> {game['name']}\n📝 <b>Описание:</b> {game['description']}\n👁 <b>Статус:</b> {status}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"changename_{idx}"), InlineKeyboardButton(text="📝 Описание", callback_data=f"changedesc_{idx}")],
        [InlineKeyboardButton(text="👁 Сменить статус", callback_data=f"changestatus_{idx}")],
        [InlineKeyboardButton(text="🗑 УДАЛИТЬ", callback_data=f"ask_del_{idx}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_games")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("ask_del_"))
async def delete_game_direct(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    
    # Берем последний элемент, чтобы точно получить цифру
    idx = int(callback.data.split("_")[-1])
    
    data = load_data("games.json", {"games": []})
    
    if idx >= len(data["games"]):
        await callback.answer("Игра уже удалена", show_alert=True)
        await admin_games_menu(callback)
        return

    name = data["games"][idx]["name"]
    data["games"].pop(idx)
    save_data("games.json", data)
    
    add_log(callback.from_user.full_name, f"Удалил игру: {name}")
    
    await callback.answer(f"🗑 {name} удалена!", show_alert=True)
    await admin_games_menu(callback)

@dp.callback_query(F.data.startswith("changestatus_"))
async def toggle_status(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    idx = int(callback.data.split("_")[1])
    data = load_data("games.json", {"games": []})
    
    new_beta = not data["games"][idx].get("is_beta", False)
    data["games"][idx]["is_beta"] = new_beta
    save_data("games.json", data)
    
    old_status = "Публичная" if new_beta else "Бета"
    new_status = "Бета" if new_beta else "Публичная"
    add_log(callback.from_user.full_name, f"Статус {data['games'][idx]['name']}: {old_status} -> {new_status}")
    
    await callback.answer("Статус изменен")
    
    game = data["games"][idx]
    status_icon = "🧪 Бета-тест" if new_beta else "👤 Публичная"
    text = (f"🎮 <b>Редактирование:</b>\n\n🏷 <b>Название:</b> {game['name']}\n📝 <b>Описание:</b> {game['description']}\n👁 <b>Статус:</b> {status_icon}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"changename_{idx}"), InlineKeyboardButton(text="📝 Описание", callback_data=f"changedesc_{idx}")],
        [InlineKeyboardButton(text="👁 Сменить статус", callback_data=f"changestatus_{idx}")],
        [InlineKeyboardButton(text="🗑 УДАЛИТЬ", callback_data=f"ask_del_{idx}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_games")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("changename_"))
async def ask_new_name(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    idx = int(callback.data.split("_")[1])
    admin_states[callback.from_user.id] = {"type": "edit_name", "idx": idx, "msg_id": callback.message.message_id}
    await callback.message.edit_text("✏️ <b>Отправь новое название:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"editgame_{idx}")]]))

@dp.callback_query(F.data.startswith("changedesc_"))
async def ask_new_desc(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    idx = int(callback.data.split("_")[1])
    admin_states[callback.from_user.id] = {"type": "edit_desc", "idx": idx, "msg_id": callback.message.message_id}
    await callback.message.edit_text("📝 <b>Отправь новое описание:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"editgame_{idx}")]]))

# --- ОБРАБОТЧИК ВВОДА (ЧИСТЫЙ ЧАТ) ---
@dp.message()
async def handle_input(message: types.Message):
    if message.document and message.from_user.id == OWNER_ID:
        state = admin_states.get(OWNER_ID)
        if state and state.get("type") == "upload_db":
            expected_file = state["file"]
            msg_id = state.get("msg_id")
            
            try: await message.delete()
            except: pass

            if message.document.file_name == expected_file:
                file_id = message.document.file_id
                file = await bot.get_file(file_id)
                await bot.download_file(file.file_path, expected_file)
                admin_states[OWNER_ID] = None
                
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=msg_id,
                        text=f"✅ <b>База {expected_file} восстановлена!</b>",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💾 В Настройки бота", callback_data="admin_core")]])
                    )
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

        if state["type"] == "broadcast":
            text_to_send = message.text
            admin_states[message.from_user.id] = None
            
            users = load_data("users.json", {})
            success_count = 0
            blocked_count = 0
            
            # Показываем, что начали
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    text="⏳ <b>Рассылка запущена...</b>",
                    parse_mode="HTML"
                )
            except: pass

            for uid in users:
                try:
                    # Добавляем заголовок
                    full_text = f"📢 <b>ОПОВЕЩЕНИЕ</b>\n\n{text_to_send}"
                    await bot.send_message(uid, full_text, parse_mode="HTML")
                    success_count += 1
                    await asyncio.sleep(0.05) # Анти-спам задержка
                except:
                    blocked_count += 1
            
            add_log(message.from_user.full_name, f"Рассылка: {text_to_send[:20]}...")
            
            # Отчет
            report = f"✅ <b>Рассылка завершена!</b>\n\n📤 Отправлено: {success_count}\n🚫 Недоставлено: {blocked_count}"
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=msg_id,
                    text=report,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]])
                )
            except: pass

        elif state["type"] == "waiting_user":
            if message.document: return 
            uid, user_data = find_user_in_db(message.text)
            
            admin_states[message.from_user.id] = None
            
            if not uid:
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=msg_id,
                        text="❌ Пользователь не найден.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Попробовать еще", callback_data="admin_roles_search")]])
                    )
                except: pass
                return
            
            buttons = [
                [InlineKeyboardButton(text="Сделать Игроком 👤", callback_data=f"setrole_{uid}_player")],
                [InlineKeyboardButton(text="Сделать Бета-тестером 🧪", callback_data=f"setrole_{uid}_beta")]
            ]
            if message.from_user.id == OWNER_ID:
                buttons.append([InlineKeyboardButton(text="Сделать Админом 👑", callback_data=f"setrole_{uid}_admin")])
                
            buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_roles_menu")])

            text = f"👤 <b>Настройка прав:</b>\n\n📛 {user_data['name']}\n📎 @{user_data['username']}\n🔰 Роль: {user_data['role']}"
            
            try:
                await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
            except: pass

        elif state["type"] == "edit_name":
            data = load_data("games.json", {})
            idx = state["idx"]
            old_name = data["games"][idx]["name"]
            data["games"][idx]["name"] = message.text
            save_data("games.json", data)
            add_log(message.from_user.full_name, f"Имя игры: {old_name} -> {message.text}")
            admin_states[message.from_user.id] = None
            try:
                await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ Название изменено на <b>{message.text}</b>!", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К игре", callback_data=f"editgame_{idx}")]]))
            except: pass

        elif state["type"] == "edit_desc":
            data = load_data("games.json", {})
            idx = state["idx"]
            data["games"][idx]["description"] = message.text
            save_data("games.json", data)
            add_log(message.from_user.full_name, f"Изм. описание {data['games'][idx]['name']}")
            admin_states[message.from_user.id] = None
            try:
                await bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=f"✅ Описание обновлено!", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К игре", callback_data=f"editgame_{idx}")]]))
            except: pass

# --- ДОБАВЛЕНИЕ ИГРЫ ---
@dp.callback_query(F.data == "admin_add_info")
async def admin_add_info(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer("Кидай .apk файл в чат!", show_alert=True)

async def admin_upload_game(message: types.Message):
    if not message.caption or "|" not in message.caption:
        await message.answer("❌ Ошибка описания.\nНапиши так: `Название | Описание`", parse_mode="Markdown")
        return

    name, desc = message.caption.split("|", 1)
    temp_games[message.from_user.id] = {
        "file_id": message.document.file_id,
        "name": name.strip(),
        "description": desc.strip()
    }
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Для всех", callback_data="add_public")],
        [InlineKeyboardButton(text="🧪 Только Бета-тест", callback_data="add_beta")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="add_cancel")]
    ])
    await message.answer(f"Добавляем: <b>{name.strip()}</b>\nКто увидит игру?", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("add_"))
async def finish_adding(callback: types.CallbackQuery):
    if not is_admin_or_owner(callback.from_user.id): return
    await callback.answer()
    action = callback.data.split("_")[1]
    uid = callback.from_user.id
    if action == "cancel":
        temp_games.pop(uid, None)
        await callback.message.delete()
        return
    game_data = temp_games.get(uid)
    if not game_data: return
    game_data["is_beta"] = (action == "beta")
    data = load_data("games.json", {"games": []})
    data["games"].append(game_data)
    save_data("games.json", data)
    
    add_log(callback.from_user.full_name, f"Добавил игру: {game_data['name']}")
    
    temp_games.pop(uid, None)
    await callback.message.edit_text(f"✅ Игра <b>{game_data['name']}</b> добавлена!", parse_mode="HTML")

async def main():
    print("🦊 FoxyZiHub запущен!")
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
