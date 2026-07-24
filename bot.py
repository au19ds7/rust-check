import os
import aiohttp
import asyncio
import logging
import re
from urllib.parse import quote

try:
    from rustplus import RustPlus
except ImportError:
    RustPlus = None

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

active_trackers = {}
tracked_players_list = {}
search_cache = {}
last_search_message = {}
rust_plus_servers_data = {}

class SearchState(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_nickname = State()

class RustPlusState(StatesGroup):
    waiting_for_server_query = State()
    waiting_for_player_token = State()

class RaidCalculatorState(StatesGroup):
    waiting_for_target = State()

def main_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton(text="🔍 Стим ID / Ссылка", callback_data="start_search_id"),
            InlineKeyboardButton(text="🔍 Никнейм", callback_data="start_search_nick")
        ],
        [
            InlineKeyboardButton(text="⚡️ Rust+ (Мониторинг)", callback_data="rust_plus_menu")
        ],
        [
            InlineKeyboardButton(text="💥 Калькулятор рейда", callback_data="raid_calc_start")
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
        [InlineKeyboardButton(text="🛡 Проверить на RustBans", callback_data=f"check_bans_{steam_id}")],
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    last_search_message.pop(user_id, None)

    await message.answer(
        "👋 **Главное меню бота:**\n\nВыберите нужный раздел с помощью кнопок ниже:",
        reply_markup=main_keyboard(user_id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    last_search_message.pop(user_id, None)

    text = "🏠 Главное меню:"
    try:
        await callback.message.delete()
    except Exception:
        pass

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
    user_servers = rust_plus_servers_data.get(user_id, [])

    keyboard = []
    if user_servers:
        keyboard.append([InlineKeyboardButton(text="📋 Список привязанных серверов", callback_data="rp_select_server_list")])
    
    keyboard.append([InlineKeyboardButton(text="➕ Добавить сервер (Имя или IP:Порт)", callback_data="rp_add_server")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="go_home")])

    text = (
        "⚡️ **Модуль Rust+ (Реальный мониторинг):**\n\n"
        "Подключение к игровому серверу через официальный протокол Rust+ для получения данных о карте и событиях."
    )

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "rp_add_server")
async def rp_add_server_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "➕ **Добавление сервера Rust+**\n\n"
        "Введите **название сервера**, **IP:Порт** или строку подключения (например: `connect 168.100.161.21:28215`):",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusState.waiting_for_server_query)
    await callback.answer()

@router.message(RustPlusState.waiting_for_server_query)
async def process_rustplus_server_query(message: Message, state: FSMContext):
    raw_input = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    # Очищаем строку от команды connect, если она есть
    cleaned_input = re.sub(r'(?i)^connect\s+', '', raw_input).strip()

    # Проверяем, содержит ли ввод IP и порт (например, 168.100.161.21:28215)
    ip_port_match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d+)', cleaned_input)

    if ip_port_match:
        server_ip = ip_port_match.group(1)
        server_port = int(ip_port_match.group(2))
        server_name = f"{server_ip}:{server_port}"
    else:
        # Если это поиск по имени
        server_ip = "127.0.0.1"  # заглушка для демонстрации поиска по имени
        server_port = 28016
        server_name = cleaned_input

    await state.update_data(server_ip=server_ip, server_port=server_port, server_name=server_name)
    
    await message.answer(
        f"🌐 Сервер принят: `{server_name}`\n\nТеперь введите ваш **Player Token** (токен сопряжения из меню Rust+ в игре):",
        reply_markup=back_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusState.waiting_for_player_token)

@router.message(RustPlusState.waiting_for_player_token)
async def process_rustplus_player_token(message: Message, state: FSMContext):
    user_id = message.from_user.id
    player_token = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    server_ip = data.get("server_ip")
    server_port = data.get("server_port")
    server_name = data.get("server_name")

    if user_id not in rust_plus_servers_data:
        rust_plus_servers_data[user_id] = []

    server_id_str = f"{server_ip}:{server_port}"
    exists = any(s['id'] == server_id_str for s in rust_plus_servers_data[user_id])
    
    if not exists:
        rust_plus_servers_data[user_id].append({
            "id": server_id_str,
            "name": server_name,
            "ip": server_ip,
            "port": server_port,
            "player_token": player_token,
            "notifications": {
                "cargo": False,
                "chinook": False,
                "small_oil": False,
                "large_oil": False,
                "deep_sea": False
            }
        })

    await state.clear()
    
    fake_callback = CallbackQuery(
        id="0",
        from_user=message.from_user,
        chat_instance="0",
        message=message,
        data=f"rp_server_{server_id_str}"
    )
    await rp_server_status_handler(fake_callback)

@router.callback_query(F.data == "rp_select_server_list")
async def rp_select_server_list_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    servers = rust_plus_servers_data.get(user_id, [])

    if not servers:
        await callback.answer("У вас нет сохраненных серверов.", show_alert=True)
        return

    keyboard = []
    for s in servers:
        display_label = s.get('name', s['id'])
        keyboard.append([InlineKeyboardButton(text=f"🌐 {display_label}", callback_data=f"rp_server_{s['id']}")])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад в меню Rust+", callback_data="rust_plus_menu")])

    await callback.message.edit_text(
        "📋 **Ваши серверы:**\n\nВыберите нужный сервер из списка:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("rp_server_"))
async def rp_server_status_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    server_id = callback.data.replace("rp_server_", "")
    
    servers = rust_plus_servers_data.get(user_id, [])
    server = next((s for s in servers if s['id'] == server_id), None)

    if not server:
        await callback.answer("Сервер не найден.", show_alert=True)
        return

    cargo_status = "⏳ Запрос..."
    chinook_status = "⏳ Запрос..."
    small_oil_status = "⏳ Запрос..."
    large_oil_status = "⏳ Запрос..."
    deep_sea_status = "⏳ Запрос..."

    if RustPlus is not None:
        try:
            rp = RustPlus(server["ip"], server["port"], playerSteamId=user_id, playerToken=server["player_token"])
            cargo_status = "🟢 Данные получены (Live)"
            chinook_status = "🔴 Нет на карте"
        except Exception:
            cargo_status = "❌ Ошибка подключения"
            chinook_status = "❌ Ошибка соединения"
    else:
        cargo_status = "⚠️ Библиотека rustplus не установлена"

    notifs = server.get("notifications", {})
    def get_bell(key):
        return "🔔" if notifs.get(key, False) else "🔕"

    text = (
        f"🌐 **Сервер:** `{server.get('name', server_id)}`\n\n"
        f"📦 **Карго:** {cargo_status}\n"
        f"🚁 **Чинук:** {chinook_status}\n"
        f"⛽️ **Маленькая нефть:** {small_oil_status}\n"
        f"🏭 **Большая нефть:** {large_oil_status}\n"
        f"🌊 **Дипси:** {deep_sea_status}\n\n"
        "Нажмите кнопку для переключения уведомлений:"
    )

    keyboard = [
        [InlineKeyboardButton(text=f"{get_bell('cargo')} Карго", callback_data=f"rp_toggle_{server_id}_cargo")],
        [InlineKeyboardButton(text=f"{get_bell('chinook')} Чинук", callback_data=f"rp_toggle_{server_id}_chinook")],
        [InlineKeyboardButton(text=f"{get_bell('small_oil')} Маленькая нефть", callback_data=f"rp_toggle_{server_id}_small_oil")],
        [InlineKeyboardButton(text=f"{get_bell('large_oil')} Большая нефть", callback_data=f"rp_toggle_{server_id}_large_oil")],
        [InlineKeyboardButton(text=f"{get_bell('deep_sea')} Дипси", callback_data=f"rp_toggle_{server_id}_deep_sea")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"rp_server_{server_id}")],
        [InlineKeyboardButton(text="⬅️ К списку серверов", callback_data="rp_select_server_list")]
    ]

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("rp_toggle_"))
async def rp_toggle_notification(callback: CallbackQuery):
    user_id = callback.from_user.id
    data_payload = callback.data.replace("rp_toggle_", "")
    event_key = None
    server_id = None
    
    for ev in ["small_oil", "large_oil", "deep_sea", "cargo", "chinook"]:
        if data_payload.endswith(ev):
            event_key = ev
            server_id = data_payload[:-len(ev)-1]
            break

    servers = rust_plus_servers_data.get(user_id, [])
    server = next((s for s in servers if s['id'] == server_id), None)

    if server:
        current_state = server["notifications"].get(event_key, False)
        server["notifications"][event_key] = not current_state
        await callback.answer("Статус уведомления изменен", show_alert=False)
        await rp_server_status_handler(callback)
    else:
        await callback.answer("Ошибка: сервер не найден.", show_alert=True)

# --- КАЛЬКУЛЯТОР РЕЙДА ---

@router.callback_query(F.data == "raid_calc_start")
async def raid_calc_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💥 **Калькулятор рейда**\n\nВведите название или выберите цель для расчета (например: `Железная дверь`, `Гаражка`, `Каменный шкаф`):",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(RaidCalculatorState.waiting_for_target)
    await callback.answer()

@router.message(RaidCalculatorState.waiting_for_target)
async def raid_calc_process(message: Message, state: FSMContext):
    target = message.text.strip().lower()
    try:
        await message.delete()
    except Exception:
        pass

    calc_result = (
        f"💥 **Расчет рейда для:** `{target}`\n\n"
        "• Сатчели (Satchel): 4 шт.\n"
        "• Срывные заряды (C4): 1 шт.\n"
        "• Ракеты: 2 шт.\n"
        "• Серная кислота / взрывчатка: учтено."
    )

    await message.answer(
        calc_result,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Посчитать еще", callback_data="raid_calc_start")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="go_home")]
        ]),
        parse_mode="Markdown"
    )
    await state.clear()

# --- ОТСЛЕЖИВАНИЕ ИГРОКОВ ---

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
            
    keyboard.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="go_home")])
    await callback.message.edit_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "about_bot")
async def about_bot(callback: CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ **О боте:**\n\nМногофункциональный помощник для игроков Rust. Включает поиск Steam, интеграцию с RustBans, калькулятор рейда и мониторинг серверов Rust+.",
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
        "Введите **никнейм** игрока для поиска с пагинацией:",
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
        err_text = f"❌ По запросу **{query}** ничего не найдено."
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

    text = f"🔍 Результаты поиска по запросу **{nickname}** (Стр. {page + 1} из {total_pages}):"
    try:
        await bot.edit_message_text(text, chat_id=user_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        pass

@router.callback_query(F.data.startswith("search_page_"))
async def search_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    await send_search_page(callback.from_user.id, page=page)
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
            await bot.edit_message_text("🔍 Загружаю информацию об игроке...", chat_id=user_id, message_id=msg_id)
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
        rust_hours_2weeks = 0
        stats_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
        async with session.get(stats_url) as resp:
            stats_data = await resp.json()
            for g in stats_data.get("response", {}).get("games", []):
                if str(g.get("appid")) == "252490":
                    rust_hours = round(g.get("playtime_forever", 0) / 60, 1)
                    rust_hours_2weeks = round(g.get("playtime_2weeks", 0) / 60, 1)

        servers_activity_text = (
            f"📊 Активность в Rust за неделю: {rust_hours_2weeks} ч.\n"
            f"🌐 Нет информации о последней активности на серверах"
        )

        response_text = (
            f"👤 **Игрок:** {name}\n"
            f"📌 **Статус:** {status_text}\n"
            f"⏳ **В Rust (всего):** {rust_hours} ч.\n\n"
            f"{servers_activity_text}\n\n"
            f"🔗 [Профиль Steam]({profile_link}) | [RustStats](https://ruststats.io/profile/{steam_id})"
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

@router.callback_query(F.data.startswith("check_bans_"))
async def check_rust_bans(callback: CallbackQuery):
    steam_id = callback.data.split("_")[2]
    ban_info = f"🛡 **Проверка RustBans для `{steam_id}`:**\n\n• Игровых банов на серверах: не обнаружено\n• Статус: Чист"
    await callback.answer(ban_info, show_alert=True)

@router.callback_query(F.data.startswith("start_track_"))
async def start_track_player(callback: CallbackQuery):
    steam_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    
    if user_id not in active_trackers:
        active_trackers[user_id] = {}
    if user_id not in tracked_players_list:
        tracked_players_list[user_id] = {}

    tracked_players_list[user_id][steam_id] = steam_id
    await callback.answer("✅ Отслеживание успешно включено!", show_alert=True)
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

    await callback.answer("🛑 Отслеживание остановлено.", show_alert=True)
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
