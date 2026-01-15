import json
import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ═══════════════════════════════════════════
# ⚙️ НАСТРОЙКИ
# ═══════════════════════════════════════════

BOT_TOKEN = "8261897648:AAE1P80ALDJQD9xtJv3nTNA_GLdZlalaVb8"
ADMIN_ID = 6057537422

# Роли
ROLE_PLAYER = "Игрок 👤"
ROLE_BETA = "Бета-тестер 🧪"
ROLE_ADMIN = "Администратор 👑"

# ═══════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Временные хранилища
temp_games = {} 
admin_states = {} 

# ═══════════════════════════════════════════
# 🌍 ФЕЙКОВЫЙ СЕРВЕР ДЛЯ RENDER
# ═══════════════════════════════════════════

async def health_check(request):
    return web.Response(text="🦊 FoxyZiHub is running!")

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', health_check)])
    runner = web.AppRunner(app)
    await runner.setup()
    # Render выдает порт через переменную окружения, или используем 8080
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ═══════════════════════════════════════════
# 📂 БАЗА ДАННЫХ
# ═══════════════════════════════════════════

def load_data(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_data(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    users = load_data("users.json", {})
    return users.get(str(user_id), {
        "role": ROLE_PLAYER, 
        "name": "Неизвестный", 
        "username": "None"
    })

def update_user(user):
    users = load_data("users.json", {})
    user_id = str(user.id)
    current_role = users.get(user_id, {}).get("role", ROLE_PLAYER)
    
    if user.id == ADMIN_ID:
        current_role = ROLE_ADMIN

    users[user_id] = {
        "name": user.full_name,
        "username": user.username,
        "role": current_role
    }
    save_data("users.json", users)

def find_user_in_db(query):
    users = load_data("users.json", {})
    query = query.replace("@", "").lower().strip()
    for uid, data in users.items():
        if data.get("username", "").lower() == query:
            return uid, data
    return None, None

# ═══════════════════════════════════════════
# 🏠 ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════

def main_menu(user_id):
    buttons = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🎮 Список игр", callback_data="games_list")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_open_menu")])

    buttons.append([InlineKeyboardButton(text="📢 Канал", url="https://t.me/FoxyZiHub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    update_user(message.from_user)
    await message.answer(
        "🦊 <b>Добро пожаловать в FoxyZiHub!</b>\n\n"
        "Здесь ты найдёшь мои игры.\n"
        "Выбери пункт меню ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu(message.from_user.id)
    )

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await cmd_start(message)

@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user_data = get_user(callback.from_user.id)
    await callback.message.edit_text(
        f"👤 <b>Твой профиль:</b>\n\n"
        f"📛 <b>Имя:</b> {user_data['name']}\n"
        f"🔰 <b>Твой статус:</b> {user_data['role']}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_home")]
        ])
    )

@dp.callback_query(F.data == "back_home")
async def back_home(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🦊 <b>FoxyZiHub</b>\nМеню:", 
        parse_mode="HTML", 
        reply_markup=main_menu(callback.from_user.id)
    )

# ═══════════════════════════════════════════
# 🎮 ИГРЫ (КЛИЕНТ)
# ═══════════════════════════════════════════

@dp.callback_query(F.data == "games_list")
async def show_games_list(callback: types.CallbackQuery):
    games = load_data("games.json", {"games": []})["games"]
    user_role = get_user(callback.from_user.id)["role"]
    
    buttons = []
    has_games = False

    for i, game in enumerate(games):
        is_beta = game.get("is_beta", False)
        if is_beta and user_role == ROLE_PLAYER:
            continue
            
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
    
    if idx >= len(games): return
    game = games[idx]
    user_role = get_user(callback.from_user.id)["role"]
    
    if game.get("is_beta", False) and user_role == ROLE_PLAYER:
        await callback.answer("⛔ Доступно только тестерам!", show_alert=True)
        return

    await callback.answer("📤 Загрузка файла...")
    await bot.send_document(
        callback.message.chat.id,
        document=game["file_id"],
        caption=f"🦊 <b>{game['name']}</b>\n\n📝 {game['description']}",
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════
# 👑 АДМИН-ПАНЕЛЬ
# ═══════════════════════════════════════════

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await open_admin_panel(message)

@dp.callback_query(F.data == "admin_open_menu")
async def callback_admin(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    await callback.message.delete()
    await open_admin_panel(callback.message)

async def open_admin_panel(message: types.Message):
    admin_states[ADMIN_ID] = None
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление ролями", callback_data="admin_roles_search")],
        [InlineKeyboardButton(text="🎮 Управление играми", callback_data="admin_games")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])
    await message.answer("👑 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "admin_close")
async def close_admin(callback: types.CallbackQuery):
    admin_states[ADMIN_ID] = None
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu(callback.from_user.id))

@dp.callback_query(F.data == "admin_back")
async def admin_back_main(callback: types.CallbackQuery):
    admin_states[ADMIN_ID] = None
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Управление ролями", callback_data="admin_roles_search")],
        [InlineKeyboardButton(text="🎮 Управление играми", callback_data="admin_games")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])
    await callback.message.edit_text("👑 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=kb)

# --- 1. РОЛИ ---
@dp.callback_query(F.data == "admin_roles_search")
async def admin_ask_user(callback: types.CallbackQuery):
    admin_states[ADMIN_ID] = {"type": "waiting_user"}
    await callback.message.edit_text(
        "👥 <b>Поиск пользователя</b>\nОтправь мне <b>@username</b> пользователя.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_back")]])
    )

@dp.callback_query(F.data.startswith("setrole_"))
async def set_role_callback(callback: types.CallbackQuery):
    _, uid, role_code = callback.data.split("_")
    users = load_data("users.json", {})
    new_role = ROLE_PLAYER if role_code == "player" else ROLE_BETA
    
    if uid in users:
        users[uid]["role"] = new_role
        save_data("users.json", users)
        await callback.message.edit_text(f"✅ Роль для {users[uid]['name']} изменена на:\n<b>{new_role}</b>", 
                                         parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админку", callback_data="admin_back")]]))
        try: await bot.send_message(uid, f"🎉 <b>Твой статус изменен!</b>\nТеперь ты: {new_role}", parse_mode="HTML")
        except: pass

# --- 2. ИГРЫ (Список) ---
@dp.callback_query(F.data == "admin_games")
async def admin_games_menu(callback: types.CallbackQuery):
    games = load_data("games.json", {"games": []})["games"]
    buttons = []
    
    for i, game in enumerate(games):
        icon = "🧪" if game.get("is_beta") else "👤"
        buttons.append([InlineKeyboardButton(text=f"{icon} {game['name']}", callback_data=f"editgame_{i}")])
    
    buttons.append([InlineKeyboardButton(text="➕ Добавить игру", callback_data="admin_add_info")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    await callback.message.edit_text("🎮 <b>Редактор игр:</b>\nНажми на игру, чтобы изменить или удалить.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# --- 2.1 ИГРЫ (Меню игры) ---
@dp.callback_query(F.data.startswith("editgame_"))
async def edit_game_menu(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    games = load_data("games.json", {"games": []})["games"]
    
    if idx >= len(games):
        await callback.answer("Игра не найдена")
        await admin_games_menu(callback)
        return

    game = games[idx]
    status = "🧪 Бета-тест" if game.get("is_beta") else "👤 Публичная"
    
    text = (f"🎮 <b>Редактирование:</b>\n\n"
            f"🏷 <b>Название:</b> {game['name']}\n"
            f"📝 <b>Описание:</b> {game['description']}\n"
            f"👁 <b>Статус:</b> {status}")
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"changename_{idx}"), 
         InlineKeyboardButton(text="📝 Описание", callback_data=f"changedesc_{idx}")],
        [InlineKeyboardButton(text="👁 Сменить статус", callback_data=f"changestatus_{idx}")],
        [InlineKeyboardButton(text="🗑 УДАЛИТЬ", callback_data=f"ask_del_{idx}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_games")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# --- 2.2 ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ ---
@dp.callback_query(F.data.startswith("ask_del_"))
async def ask_delete_game(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_del_{idx}")],
        [InlineKeyboardButton(text="❌ Нет, назад", callback_data=f"editgame_{idx}")]
    ])
    await callback.message.edit_text("❓ <b>Вы уверены, что хотите удалить игру?</b>\nЭто действие нельзя отменить.", 
                                     parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith("confirm_del_"))
async def confirm_delete_game(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    data = load_data("games.json", {"games": []})
    
    name = data["games"][idx]["name"]
    data["games"].pop(idx)
    save_data("games.json", data)
    
    await callback.answer(f"🗑 {name} удалена")
    await admin_games_menu(callback)

# --- 2.3 ЛОГИКА ИЗМЕНЕНИЙ ---
@dp.callback_query(F.data.startswith("changestatus_"))
async def toggle_status(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    data = load_data("games.json", {"games": []})
    
    data["games"][idx]["is_beta"] = not data["games"][idx].get("is_beta", False)
    save_data("games.json", data)
    
    await callback.data.replace("changestatus", "editgame") 
    await edit_game_menu(callback)

@dp.callback_query(F.data.startswith("changename_"))
async def ask_new_name(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    admin_states[ADMIN_ID] = {"type": "edit_name", "idx": idx}
    await callback.message.edit_text("✏️ <b>Отправь новое название:</b>", parse_mode="HTML", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"editgame_{idx}")]]))

@dp.callback_query(F.data.startswith("changedesc_"))
async def ask_new_desc(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    admin_states[ADMIN_ID] = {"type": "edit_desc", "idx": idx}
    await callback.message.edit_text("📝 <b>Отправь новое описание:</b>", parse_mode="HTML",
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=f"editgame_{idx}")]]))

# --- 3. ОБРАБОТЧИК ТЕКСТА ---
@dp.message()
async def handle_admin_input(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    state = admin_states.get(ADMIN_ID)
    if not state: 
        if message.document: await admin_upload_game(message)
        return

    if state["type"] == "waiting_user":
        if message.document: return 
        uid, user_data = find_user_in_db(message.text)
        if not uid:
            await message.answer("❌ Пользователь не найден.")
            return
        
        admin_states[ADMIN_ID] = None
        text = f"👤 <b>Настройка прав:</b>\n\n📛 {user_data['name']}\n📎 @{user_data['username']}\n🔰 Роль: {user_data['role']}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Сделать Игроком 👤", callback_data=f"setrole_{uid}_player")],
            [InlineKeyboardButton(text="Сделать Бета-тестером 🧪", callback_data=f"setrole_{uid}_beta")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

    elif state["type"] == "edit_name":
        data = load_data("games.json", {})
        idx = state["idx"]
        data["games"][idx]["name"] = message.text
        save_data("games.json", data)
        admin_states[ADMIN_ID] = None
        await message.answer(f"✅ Название изменено!", parse_mode="HTML")
        await message.answer("Вернуться в меню:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К игре", callback_data=f"editgame_{idx}")]]))

    elif state["type"] == "edit_desc":
        data = load_data("games.json", {})
        idx = state["idx"]
        data["games"][idx]["description"] = message.text
        save_data("games.json", data)
        admin_states[ADMIN_ID] = None
        await message.answer(f"✅ Описание обновлено!", parse_mode="HTML")
        await message.answer("Вернуться в меню:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 К игре", callback_data=f"editgame_{idx}")]]))

# --- 4. ДОБАВЛЕНИЕ ИГРЫ ---
@dp.callback_query(F.data == "admin_add_info")
async def admin_add_info(callback: types.CallbackQuery):
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
    
    temp_games.pop(uid, None)
    await callback.message.edit_text(f"✅ Игра <b>{game_data['name']}</b> добавлена!", parse_mode="HTML")

async def main():
    print("🦊 FoxyZiHub запущен!")
    # Запускаем и веб-сервер (чтобы Render не ругался), и бота
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
