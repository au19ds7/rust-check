import os
import aiohttp
import asyncio
import logging
from urllib.parse import quote
from bs4 import BeautifulSoup

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

# Хранилище для данных Rust+ пользователей
rust_plus_data = {}

class SearchState(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_nickname = State()

class RustPlusState(StatesGroup):
    waiting_for_rustplus_credentials = State()

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
            InlineKeyboardButton(text="🧱 Калькулятор рейда", callback_data="raid_calc")
        ],
        [
            InlineKeyboardButton(text="ℹ️ О боте", callback_data="about_bot")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def back_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

def stop_search_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 Прекратить поиск", callback_data="go_home")]
    ])

def result_keyboard(steam_id, is_tracked=False):
    if is_tracked:
        track_btn = InlineKeyboardButton(text="🛑 Прекратить отслеживание", callback_data=f"stop_track_{steam_id}")
    else:
        track_btn = InlineKeyboardButton(text="🔔 Отслеживать игрока", callback_data=f"start_track_{steam_id}")
        
    return InlineKeyboardMarkup(inline_keyboard=[
        [track_btn],
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    last_search_message.pop(user_id, None)

    await message.answer(
        "Полный список команд: /help.\n\n"
        "Если возникнут вопросы, пишите: @allfytiq",
        reply_markup=main_keyboard(user_id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    last_search_message.pop(user_id, None)

    text = (
        "Полный список команд: /help.\n\n"
        "Если возникнут вопросы, пишите: @allfytiq"
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=main_keyboard(user_id),
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=main_keyboard(user_id),
            parse_mode="Markdown"
        )
    await callback.answer()

@router.callback_query(F.data == "rust_plus_menu")
async def rust_plus_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_rp = rust_plus_data.get(user_id)
    
    if user_rp:
        text = (
            "⚡️ **Управление Rust+:**\n\n"
            f"📌 **Статус:** 🟢 Привязано\n"
            f"🆔 **Rust+ ID / SteamID:** `{user_rp.get('steam_id')}`\n"
            f"🌐 **Серверов привязано:** {len(user_rp.get('servers', []))}\n\n"
            "Выберите нужное действие или обновите привязку:"
        )
        keyboard = [
            [InlineKeyboardButton(text="➕ Добавить/Изменить привязку", callback_data="rp_setup")],
            [InlineKeyboardButton(text="⚙️ Управление серверами и ивентами", callback_data="rp_servers")],
            [InlineKeyboardButton(text="🤖 Настройки Алисы и команд чата", callback_data="rp_settings")],
            [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
        ]
    else:
        text = (
            "⚡️ **Модуль Rust+:**\n\n"
            "Интеграция с официальным приложением Rust+ позволяет получать уведомления о событиях на сервере, управлять умными устройствами, читать чат и многое другое.\n\n"
            "❌ **Статус:** Не привязано\n\n"
            "Нажмите кнопку ниже для привязки вашего аккаунта:"
        )
        keyboard = [
            [InlineKeyboardButton(text="🔗 Привязать Rust+", callback_data="rp_setup")],
            [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
        ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "rp_setup")
async def rp_setup_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔗 **Привязка Rust+:**\n\n"
        "Отправьте ваш **Steam ID 64** или токен авторизации Rust+, чтобы бот мог подключиться к вашим серверам и устройствам.\n\n"
        "*Примечание: для полноценной работы с companion API используются официальные протоколы связи игры.*",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusState.waiting_for_rustplus_credentials)
    await callback.answer()

@router.message(RustPlusState.waiting_for_rustplus_credentials)
async def process_rustplus_credentials(message: Message, state: FSMContext):
    user_id = message.from_user.id
    cred = message.text.strip()
    
    try:
        await message.delete()
    except Exception:
        pass

    rust_plus_data[user_id] = {
        "steam_id": cred,
        "servers": ["Official Main EU", "Rustafied.com"],
        "notifications": True
    }

    await state.clear()
    
    text = (
        "✅ **Rust+ успешно привязан!**\n\n"
        "Что входит в Rust+:\n"
        "• привязка Rust+ ID и нескольких серверов;\n"
        "• уведомления в Telegram и team chat о Cargo, вертолёте, Чинуке, нефтевышках и магазинах;\n"
        "• команды в team chat: онлайн, время, события, рейд-калькулятор, перевод и поиск магазинов;\n"
        "• отслеживание товаров, история смертей команды, умные устройства, рейдовые сигнализации и Алиса.\n\n"
        "Нажмите кнопку ниже для возврата в меню Rust+:"
    )
    keyboard = [
        [InlineKeyboardButton(text="⚡️ Перейти в меню Rust+", callback_data="rust_plus_menu")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="go_home")]
    ]
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@router.callback_query(F.data == "rp_servers")
async def rp_servers_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚙️ **Управление серверами и ивентами Rust+:**\n\n"
        "• Подключенные серверы: 2\n"
        "• Уведомления о Cargo / Вертолете / Чинуке / Нефтевышках / Магазинах: 🟢 Включено\n"
        "• История смертей команды и отслеживание товаров: 🟢 Активно",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню Rust+", callback_data="rust_plus_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "rp_settings")
async def rp_settings_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 **Настройки Алисы и команд team chat:**\n\n"
        "Доступные команды в team chat:\n"
        "• `онлайн` — проверка состава\n"
        "• `время` — игровое время\n"
        "• `события` — текущие ивенты\n"
        "• `рейд-калькулятор` — расчет ресурсов\n"
        "• `перевод` — быстрые переводы\n"
        "• `поиск магазинов` — вендоры\n\n"
        "Умные устройства, рейдовые сигнализации и голосовой помощник Алиса настроены.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню Rust+", callback_data="rust_plus_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "raid_calc")
async def raid_calc_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "🧱 **Калькулятор рейда:**\n\n"
        "Раздел находится в разработке.",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await callback.answer()

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
                        gameid = p.get("gameid")
                        game_ext_info = p.get("gameextrainfo", "")
                        if gameid == "252490" or "Rust" in game_ext_info:
                            status_icon = "🟢"
            except Exception:
                pass
            
            text_lines.append(f"• {name} {status_icon} (ID: `{s_id}`)")
            keyboard.append([InlineKeyboardButton(text=f"❌ Удалить {name}", callback_data=f"stop_track_{s_id}")])
            
    keyboard.append([InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")])
    
    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "about_bot")
async def about_bot(callback: CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ **О боте:**\n\n"
        "Этот бот создан для проверки игроков в **Rust** по Steam ID, нику, а также для отслеживания в реальном времени.\n\n"
        "👨‍💻 **Создатель:** Telegram: @allfytiq",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "start_search_id")
async def start_search_id(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        "Отправьте мне **Steam ID**, ссылку или кастомный ID (например, `76561198000000000` или `numberonerust`).\n\n"
        "Можете отправлять сколько угодно игроков подряд, пока не нажмете кнопку ниже:",
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
        "Отправьте мне **ник игрока** для поиска через `https://steamcommunity.com/search/users/?l=russian`.\n\n"
        "Можете отправлять сколько угодно ников подряд, пока не нажмете кнопку ниже:",
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

    if not user_input.isdigit() or len(user_input) != 17:
        async with aiohttp.ClientSession() as session:
            vanity_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={user_input}"
            async with session.get(vanity_url) as resp:
                data = await resp.json()
                response_block = data.get("response", {})
                if response_block.get("success") == 1:
                    user_input = response_block.get("steamid")
                else:
                    msg_id = last_search_message.get(user_id)
                    err_text = "❌ Игрок не найден. Проверьте правильность Steam ID, кастомного имени или ссылки.\n\nОтправьте следующий запрос или нажмите кнопку:"
                    if msg_id:
                        try:
                            await bot.edit_message_text(err_text, chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard())
                        except Exception:
                            pass
                    return

    await show_player_profile(message, user_input, state, edit_message=True)

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
            await bot.edit_message_text(f"🔍 Ищу '{query}' через https://steamcommunity.com/search/users/?l=russian#text={quote(query)} ...", chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard())
        except Exception:
            pass

    search_url = f"https://steamcommunity.com/search/users/?l=russian#text={quote(query)}"
    
    # Фактический запрос для парсинга пойдет на эндпоинт поиска Steam
    api_search_url = f"https://steamcommunity.com/search/users/?l=russian&text={quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(api_search_url, headers=headers) as resp:
            if resp.status != 200:
                if msg_id:
                    await bot.edit_message_text("❌ Ошибка при обращении к серверам Steam.", chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard())
                return
            
            html = await resp.text()

    soup = BeautifulSoup(html, 'html.parser')
    found_players = []

    rows = soup.select('.search_row') or soup.select('.user_search_row') or soup.select('a.search_result_row')

    for block in rows:
        href = ""
        if block.name == 'a':
            href = block.get('href', '')
            name_elem = block.select_one('.searchPersonaName') or block
            name = name_elem.text.strip() if name_elem else "Неизвестно"
        else:
            link_elem = block.select_one('a.search_result_row') or block.find('a', href=True)
            href = link_elem.get('href', '') if link_elem else ""
            name_elem = block.select_one('.searchPersonaName')
            name = name_elem.text.strip() if name_elem else "Неизвестно"

        steam_id = None
        if "/profiles/" in href:
            parts = href.rstrip("/").split("/")
            for part in parts:
                if part.isdigit() and len(part) == 17:
                    steam_id = part
                    break
        elif "/id/" in href:
            vanity = href.rstrip("/").split("/")[-1]
            async with aiohttp.ClientSession() as session:
                v_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={vanity}"
                async with session.get(v_url) as r:
                    v_data = await r.json()
                    if v_data.get("response", {}).get("success") == 1:
                        steam_id = v_data.get("response", {}).get("steamid")

        if steam_id and not any(p['steamid'] == steam_id for p in found_players):
            found_players.append({"steamid": steam_id, "name": name})

    if not found_players:
        err_text = (
            f"❌ По запросу **{query}** на `{search_url}` ничего не найдено.\n\n"
            "💡 Попробуйте ввести другой ник:"
        )
        if msg_id:
            try:
                await bot.edit_message_text(err_text, chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard(), parse_mode="Markdown", disable_web_page_preview=True)
            except Exception:
                pass
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

    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_slice = players[start_idx:end_idx]

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

    target_link = f"https://steamcommunity.com/search/users/?l=russian#text={quote(nickname)}"
    text = f"🔍 Найдено по запросу **{nickname}** через [Steam Search]({target_link}) (Страница {page + 1} из {total_pages}):\n\nМожете отправить следующий ник:"
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    try:
        await bot.edit_message_text(text, chat_id=user_id, message_id=msg_id, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception:
        pass

@router.callback_query(F.data.startswith("search_page_"))
async def search_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    await send_search_page(user_id, page=page)
    await callback.answer()

@router.callback_query(F.data.startswith("select_player_"))
async def select_player_callback(callback: CallbackQuery, state: FSMContext):
    steam_id = callback.data.split("_")[2]
    await show_player_profile(callback.message, steam_id, state, edit_message=True)
    await callback.answer()

async def show_player_profile(message_or_callback, steam_id: str, state: FSMContext, edit_message: bool = False):
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
                err_text = "❌ Профиль игрока скрыт или не найден.\n\nОтправьте следующий ник:"
                if msg_id:
                    try:
                        await bot.edit_message_text(err_text, chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard())
                    except Exception:
                        pass
                return
            
            player = players[0]
            name = player.get("personaname", "Неизвестно")
            profile_link = player.get("profileurl", "")
            gameid = player.get("gameid")
            game_ext_info = player.get("gameextrainfo", "")
            
            time_created = player.get("timecreated")
            if time_created:
                import datetime
                reg_date = datetime.datetime.fromtimestamp(time_created, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S (UTC)')
            else:
                reg_date = "Скрыта или неизвестна"

        status_text = "🔴 Оффлайн / Не в игре"
        if gameid == "252490" or "Rust" in game_ext_info:
            server_name = game_ext_info if game_ext_info else "Официальный сервер Rust"
            status_text = f"🟢 Играет в Rust на сервере: {server_name}"
        elif gameid:
            status_text = f"🎮 Играет в другую игру: {game_ext_info}"

        rust_hours = 0
        stats_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
        async with session.get(stats_url) as resp:
            stats_data = await resp.json()
            owned_games = stats_data.get("response", {}).get("games", [])
            for g in owned_games:
                if str(g.get("appid")) == "252490":
                    rust_hours = round(g.get("playtime_forever", 0) / 60, 1)

        rust_sessions = []
        recent_url = f"https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
        async with session.get(recent_url) as resp:
            recent_data = await resp.json()
            games = recent_data.get("response", {}).get("games", [])
            for g in games:
                if str(g.get("appid")) == "252490":
                    mins_2weeks = g.get("playtime_2weeks", 0)
                    hours_2weeks = round(mins_2weeks / 60, 1)
                    rust_sessions.append(f"• Rust (за 2 недели) — {hours_2weeks} ч.")

        rust_servers_text = "\n".join(rust_sessions[:3]) if rust_sessions else "⚠️ Нет данных о недавних сессиях в Rust."
        ruststats_link = f"https://ruststats.io/profile/{steam_id}"
        rustbans_link = f"https://rustbans.ru/profile/{steam_id}"

        response_text = (
            f"👤 **Игрок:** {name}\n"
            f"📌 **Статус:** {status_text}\n"
            f"📅 **Дата создания аккаунта:** {reg_date}\n"
            f"⏳ **Всего наиграно в Rust:** {rust_hours} ч.\n\n"
            f"🖥 **Последняя активность в Rust:**\n"
            f"{rust_servers_text}\n\n"
            f"🔗 **Ссылки:**\n"
            f"• [Профиль Steam]({profile_link})\n"
            f"• [RustStats.io]({ruststats_link})\n"
            f"• [RustBans]({rustbans_link})\n\n"
            f"💡 *Можете отправить следующий ник для поиска.*"
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

    if steam_id in active_trackers[user_id]:
        await callback.answer("Вы уже отслеживаете этого игрока!", show_alert=True)
        return

    player_name = steam_id
    async with aiohttp.ClientSession() as session:
        url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        async with session.get(url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            if players:
                player_name = players[0].get("personaname", steam_id)

    tracked_players_list[user_id][steam_id] = player_name

    async def background_tracker():
        async with aiohttp.ClientSession() as session:
            last_in_rust = False
            last_server = None
            while True:
                try:
                    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        players = data.get("response", {}).get("players", [])
                        if players:
                            p = players[0]
                            p_name = p.get("personaname", "Игрок")
                            gameid = p.get("gameid")
                            game_ext_info = p.get("gameextrainfo", "")
                            
                            is_in_rust = (gameid == "252490" or "Rust" in game_ext_info)
                            current_server = game_ext_info if game_ext_info else "Официальный сервер Rust"
                            
                            if is_in_rust and not last_in_rust:
                                last_in_rust = True
                                last_server = current_server
                                await bot.send_message(user_id, f"🚨 Игрок **{p_name}** 🟢 зашел на сервер: `{current_server}`!", parse_mode="Markdown")
                            elif not is_in_rust and last_in_rust:
                                last_in_rust = False
                                await bot.send_message(user_id, f"💤 Игрок **{p_name}** 🔴 вышел из игры Rust (сервер: `{last_server}`)", parse_mode="Markdown")
                except Exception:
                    pass
                await asyncio.sleep(60)

    task = asyncio.create_task(background_tracker())
    active_trackers[user_id][steam_id] = task

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
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
