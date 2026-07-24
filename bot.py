import os
import aiohttp
import asyncio
import logging
from urllib.parse import quote, urlencode

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
BOT_DOMAIN = os.getenv("BOT_DOMAIN", "https://your-bot-domain.com")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

active_trackers = {}
tracked_players_list = {}
search_cache = {}
last_search_message = {}
rust_plus_auth_data = {}

class SearchState(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_nickname = State()

class RustPlusState(StatesGroup):
    waiting_for_server_ip = State()
    waiting_for_server_port = State()

def main_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton(text="🔍 Стим", callback_data="start_search_id"),
            InlineKeyboardButton(text="🔍 Ник", callback_data="start_search_nick")
        ],
        [
            InlineKeyboardButton(text="⚡️ Rust+", callback_data="rust_plus_menu")
        ],
        [
            InlineKeyboardButton(text="👁 Мои отслеживания", callback_data="show_tracked_list")
        ],
        [
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about_bot")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def stop_search_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 Прекратить поиск", callback_data="go_home")]
    ])

def back_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

def result_keyboard(steam_id, is_tracked=False):
    if is_tracked:
        track_btn = InlineKeyboardButton(text="🛑 Прекратить отслеживание", callback_data=f"stop_track_{steam_id}")
    else:
        track_btn = InlineKeyboardButton(text="🔔 Отслеживать игрока", callback_data=f"start_track_{steam_id}")
        
    return InlineKeyboardMarkup(inline_keyboard=[
        [track_btn],
        [InlineKeyboardButton(text="⬅️ К списку результатов", callback_data="back_to_search_list")],
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    last_search_message.pop(user_id, None)

    await message.answer(
        "Привет! Выберите действие:",
        reply_markup=main_keyboard(user_id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    last_search_message.pop(user_id, None)

    text = "Главное меню:"
    
    # Удаляем старое компактное сообщение, чтобы интерфейс не ломался и не сжимался
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Отправляем полноценное новое сообщение с главным меню
    await callback.message.answer(
        text,
        reply_markup=main_keyboard(user_id),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- МОДУЛЬ RUST+ ---

@router.callback_query(F.data == "rust_plus_menu")
async def rust_plus_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_session = rust_plus_auth_data.get(user_id)

    if user_session and user_session.get("authenticated"):
        steam_id = user_session.get("steam_id")
        servers = user_session.get("servers", [])
        servers_list = "\n".join([f"• `{s['ip']}:{s['port']}`" for s in servers]) if servers else "• Нет подключенных серверов"

        text = (
            "⚡️ **Модуль Rust+ (Авторизован через Steam):**\n\n"
            f"👤 **Ваш Steam ID:** `{steam_id}`\n\n"
            "🌐 **Ваши серверы Rust+:**\n"
            f"{servers_list}\n\n"
            "Выберите действие:"
        )
        keyboard = [
            [InlineKeyboardButton(text="➕ Добавить сервер", callback_data="rp_add_server")],
            [InlineKeyboardButton(text="🚪 Выйти из аккаунта Steam", callback_data="rp_logout")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="go_home")]
        ]
    else:
        openid_params = {
            "openid.ns": "http://specs.openid.net/auth/2.0",
            "openid.mode": "checkid_setup",
            "openid.return_to": f"{BOT_DOMAIN}/steam_auth_callback?user_id={user_id}",
            "openid.realm": BOT_DOMAIN,
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select"
        }
        steam_login_url = f"https://steamcommunity.com/login/loginredirect/?{urlencode(openid_params)}"

        text = (
            "⚡️ **Модуль Rust+ (Авторизация через Steam):**\n\n"
            "Для использования Rust+ требуется авторизоваться через **настоящий Steam**. "
            "Нажмите кнопку ниже, чтобы войти через официальную безопасную страницу Steam OpenID:"
        )
        keyboard = [
            [InlineKeyboardButton(text="🔑 Войти через Steam", url=steam_login_url)],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="go_home")]
        ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "rp_logout")
async def rp_logout_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    rust_plus_auth_data.pop(user_id, None)
    await callback.answer("🚪 Вы успешно вышли из Steam аккаунта в Rust+.", show_alert=True)
    await rust_plus_menu_handler(callback, state)

@router.callback_query(F.data == "rp_add_server")
async def rp_add_server_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "➕ **Добавление сервера Rust+**\n\nВведите IP адрес сервера:",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusState.waiting_for_server_ip)
    await callback.answer()

@router.message(RustPlusState.waiting_for_server_ip)
async def process_rustplus_server_ip(message: Message, state: FSMContext):
    server_ip = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(server_ip=server_ip)
    await message.answer(
        "🌐 Введите **Companion Порт** сервера (например, `28082`):",
        reply_markup=back_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusState.waiting_for_server_port)

@router.message(RustPlusState.waiting_for_server_port)
async def process_rustplus_server_port(message: Message, state: FSMContext):
    user_id = message.from_user.id
    server_port = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    if not server_port.isdigit():
        await message.answer("❌ Порт должен состоять только из цифр:", reply_markup=back_keyboard(user_id))
        return

    data = await state.get_data()
    server_ip = data.get("server_ip")
    port = int(server_port)

    if user_id not in rust_plus_auth_data:
        rust_plus_auth_data[user_id] = {"authenticated": True, "steam_id": "76561198xxxxxxxxx", "servers": []}

    rust_plus_auth_data[user_id]["servers"].append({
        "ip": server_ip,
        "port": port
    })

    await state.clear()
    await message.answer(
        f"✅ Сервер `{server_ip}:{port}` успешно добавлен!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ В меню Rust+", callback_data="rust_plus_menu")]
        ]),
        parse_mode="Markdown"
    )

# --- ПОИСК И ОТСЛЕЖИВАНИЕ ---

@router.callback_query(F.data == "show_tracked_list")
async def show_tracked_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    players = tracked_players_list.get(user_id, {})
    
    if not players:
        await callback.answer("У вас нет отслеживаемых игроков.", show_alert=True)
        return
        
    keyboard = []
    text_lines = ["👁 **Мои отслеживания:**\n"]
    
    async with aiohttp.ClientSession() as session:
        for s_id, base_name in players.items():
            url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={s_id}"
            status_icon = "🔴"
            name = base_name
            try:
                async with session.get(url) as resp:
                    data = await resp.json()
                    pl_list = data.get("response", {}).get("players", [])
                    if pl_list:
                        p = pl_list[0]
                        name = p.get("personaname", base_name)
                        if p.get("gameid") == "252490" or "Rust" in p.get("gameextrainfo", ""):
                            status_icon = "🟢"
            except Exception:
                pass
            
            text_lines.append(f"• {name} {status_icon} (ID: `{s_id}`)")
            keyboard.append([InlineKeyboardButton(text=f"❌ Удалить {name}", callback_data=f"stop_track_{s_id}")])
            
    keyboard.append([InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")])
    await callback.message.edit_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "about_bot")
async def about_bot(callback: CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ **О боте:**\n\nПоиск профилей Steam по точному никнейму или Steam ID.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="go_home")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "start_search_id")
async def start_search_id(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        "Отправьте мне **Steam ID 64** или ссылку на профиль:",
        reply_markup=stop_search_keyboard(),
        parse_mode="Markdown"
    )
    last_search_message[user_id] = callback.message.message_id
    await state.set_state(SearchState.waiting_for_steam_id)
    await callback.answer()

@router.callback_query(F.data == "start_search_nick")
async def start_search_nick(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        "Введите **точное имя (ник)** игрока (например, `aVudi`):",
        reply_markup=stop_search_keyboard(),
        parse_mode="Markdown"
    )
    last_search_message[user_id] = callback.message.message_id
    await state.set_state(SearchState.waiting_for_nickname)
    await callback.answer()

@router.message(SearchState.waiting_for_steam_id)
async def process_steam_id_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_input = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    if "steamcommunity.com/id/" in user_input:
        user_input = user_input.rstrip("/").split("/")[-1]
    elif "steamcommunity.com/profiles/" in user_input:
        user_input = user_input.rstrip("/").split("/")[-1]

    steam_id = None
    if user_input.isdigit() and len(user_input) == 17:
        steam_id = user_input
    else:
        async with aiohttp.ClientSession() as session:
            vanity_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={user_input}"
            async with session.get(vanity_url) as resp:
                data = await resp.json()
                if data.get("response", {}).get("success") == 1:
                    steam_id = data.get("response", {}).get("steamid")

    if not steam_id:
        msg_id = last_search_message.get(user_id)
        if msg_id:
            try:
                await bot.edit_message_text("❌ Игрок не найден. Попробуйте еще раз:", chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard())
            except Exception:
                pass
        return

    await show_player_profile(message, steam_id, state)

@router.message(SearchState.waiting_for_nickname)
async def process_nickname_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    query = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    msg_id = last_search_message.get(user_id)
    if msg_id:
        try:
            await bot.edit_message_text(f"🔍 Ищу '{query}' в базе Steam...", chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard())
        except Exception:
            pass

    found_players = []
    async with aiohttp.ClientSession() as session:
        community_search_url = f"https://steamcommunity.com/search/suggestext/?text={quote(query)}&category=users&l=russian"
        async with session.get(community_search_url) as resp:
            if resp.status == 200:
                try:
                    items = await resp.json()
                    for item in items:
                        s_id = item.get("steamID")
                        name = item.get("name")
                        if s_id and name:
                            found_players.append({"steamid": s_id, "name": name})
                except Exception:
                    pass

    if not found_players:
        err_text = f"❌ По точному запросу **{query}** ничего не найдено.\n\nПопробуйте ввести другой ник:"
        if msg_id:
            try:
                await bot.edit_message_text(err_text, chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard(), parse_mode="Markdown")
            except Exception:
                pass
        return

    if len(found_players) == 1:
        await show_player_profile(message, found_players[0]["steamid"], state)
        return

    search_cache[user_id] = {"players": found_players, "query": query}
    await send_search_page(user_id, page=0)

async def send_search_page(user_id: int, page: int = 0):
    data = search_cache.get(user_id)
    msg_id = last_search_message.get(user_id)
    if not data or not msg_id:
        return

    players = data["players"]
    nickname = data["query"]
    
    per_page = 5
    total_pages = (len(players) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))

    current_slice = players[page * per_page : (page + 1) * per_page]

    keyboard = []
    for p in current_slice:
        keyboard.append([InlineKeyboardButton(text=p["name"], callback_data=f"select_player_{p['steamid']}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"search_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"search_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(text="🛑 Прекратить поиск", callback_data="go_home")])

    text = f"🔍 Найдено несколько игроков по запросу **{nickname}** (Страница {page + 1} из {total_pages}):\n\nВыберите нужного:"
    try:
        await bot.edit_message_text(text, chat_id=user_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        pass

@router.callback_query(F.data.startswith("search_page_"))
async def search_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    await send_search_page(callback.from_user.id, page=page)
    await callback.answer()

@router.callback_query(F.data == "back_to_search_list")
async def back_to_search_list_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in search_cache:
        await send_search_page(user_id, page=0)
    else:
        await go_home(callback, None)
    await callback.answer()

@router.callback_query(F.data.startswith("select_player_"))
async def select_player_callback(callback: CallbackQuery, state: FSMContext):
    steam_id = callback.data.split("_")[2]
    await show_player_profile(callback.message, steam_id, state)
    await callback.answer()

async def show_player_profile(message_or_callback, steam_id: str, state: FSMContext):
    chat_id = message_or_callback.chat.id if hasattr(message_or_callback, "chat") else message_or_callback.message.chat.id
    user_id = chat_id
    msg_id = last_search_message.get(user_id)

    if msg_id:
        try:
            await bot.edit_message_text("🔍 Загружаю профиль...", chat_id=user_id, message_id=msg_id)
        except Exception:
            pass

    async with aiohttp.ClientSession() as session:
        profile_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        async with session.get(profile_url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            if not players:
                if msg_id:
                    await bot.edit_message_text("❌ Профиль скрыт или не найден.", chat_id=user_id, message_id=msg_id, reply_markup=result_keyboard(steam_id))
                return
            
            player = players[0]
            name = player.get("personaname", "Неизвестно")
            profile_link = player.get("profileurl", "")
            gameid = player.get("gameid")
            game_ext_info = player.get("gameextrainfo", "")

        status_text = "🔴 Оффлайн"
        if gameid == "252490" or "Rust" in game_ext_info:
            status_text = f"🟢 Играет в Rust ({game_ext_info or 'Официальный сервер'})"

        rust_hours = 0
        stats_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
        async with session.get(stats_url) as resp:
            stats_data = await resp.json()
            for g in stats_data.get("response", {}).get("games", []):
                if str(g.get("appid")) == "252490":
                    rust_hours = round(g.get("playtime_forever", 0) / 60, 1)

        response_text = (
            f"👤 **Игрок:** {name}\n"
            f"📌 **Статус:** {status_text}\n"
            f"⏳ **В Rust:** {rust_hours} ч.\n\n"
            f"🔗 [Открыть профиль в Steam]({profile_link})"
        )

        is_tracked = user_id in active_trackers and steam_id in active_trackers[user_id]

        if msg_id:
            try:
                await bot.edit_message_text(
                    response_text,
                    chat_id=user_id,
                    message_id=msg_id,
                    reply_markup=result_keyboard(steam_id, is_tracked=is_tracked),
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            except Exception:
                pass

@router.callback_query(F.data.startswith("start_track_"))
async def start_track_player(callback: CallbackQuery):
    steam_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    if user_id not in active_trackers:
        active_trackers[user_id] = {}
    if user_id not in tracked_players_list:
        tracked_players_list[user_id] = {}

    tracked_players_list[user_id][steam_id] = steam_id
    await callback.answer("✅ Отслеживание включено!", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=result_keyboard(steam_id, is_tracked=True))
    except Exception:
        pass

@router.callback_query(F.data.startswith("stop_track_"))
async def stop_track_player(callback: CallbackQuery):
    steam_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    if user_id in active_trackers and steam_id in active_trackers[user_id]:
        active_trackers[user_id][steam_id].cancel()
        del active_trackers[user_id][steam_id]
    if user_id in tracked_players_list and steam_id in tracked_players_list[user_id]:
        del tracked_players_list[user_id][steam_id]

    await callback.answer("🛑 Отслеживание прекращено.", show_alert=True)
    if callback.message.text and "Мои отслеживания" in callback.message.text:
        await show_tracked_list(callback)
    else:
        try:
            await callback.message.edit_reply_markup(reply_markup=result_keyboard(steam_id, is_tracked=False))
        except Exception:
            pass

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
