import os
import io
import aiohttp
import asyncio
import logging
import re
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

# Хранилища данных в памяти
tracked_players_list = {}     # {user_id: set(steam_ids)}
search_cache = {}             # Кеш поиска по никнеймам
last_search_message = {}      # ID последнего сообщения для обновления интерфейса
user_languages = {}           # {user_id: "ru"/"en"/"uk"}
user_servers = {}             # {user_id: [list of server names]}
player_last_status = {}       # {user_id: {steam_id: bool}}

LANGS = {
    "ru": {
        "main_menu": "👋 **Главное меню бота:**\n\nВыберите нужный раздел с помощью кнопок ниже:",
        "home_btn": "🏠 Главное меню",
        "back_btn": "⬅️ Вернуться на самое начало",
        "stop_search": "🛑 Прекратить поиск",
        "btn_search_id": "🔍 Стим ID / Ссылка",
        "btn_search_nick": "🔍 Никнейм",
        "btn_rust_plus": "⚡️ Rust+",
        "btn_raid": "💥 Калькулятор рейда",
        "btn_tracked": "👁 Мои отслеживания",
        "btn_zayats": "🐰 Заяц",
        "btn_about": "ℹ️ О боте / Язык",
        "zayats_prompt": "🐰 **Режим Заяц**\n\nОтправьте мне **Steam ID 64** или **кастомный URL/ник (буквенный)** игрока, чтобы получить ссылку на ruststats.io:",
        "zayats_not_found": "❌ Не удалось найти игрока на ruststats.io.",
        "about_text": (
            "ℹ️ **О боте:**\n\n"
            "Многофункциональный помощник для игроков Rust.\n\n"
            "🌐 **Выберите язык / Choose language / Виберіть мову:**"
        ),
        "lang_changed": "✅ Язык успешно изменен на Русский!",
        "rust_plus_menu_title": "⚡️ **Меню Rust+**[cite: 1]\n\nВыберите нужный раздел[cite: 1]:",
        "rp_tab_online": "🟢 1. Онлайн[cite: 1]",
        "rp_tab_map": "🗺 2. Карта[cite: 1]",
        "rp_tab_third": "⚙️ 3. Настройки / Прочее[cite: 1]",
        "rp_online_title": "🟢 **Список серверов (Онлайн):**\n\nВыберите сервер или добавьте его по точному названию[cite: 1]:",
        "rp_map_title": "🗺 **Список серверов (Карта):**\n\nВыберите сервер для получения карты[cite: 1]:",
        "btn_add_server": "➕ Добавить сервер[cite: 1]",
        "btn_delete_server": "🗑 Удалить сервер[cite: 1]",
        "rp_prompt_ip": "🌐 **Введите точное название сервера Rust**[cite: 1]\n\nНапример: `Official Server #1`[cite: 1]",
        "rp_server_added": "✅ Сервер успешно добавлен в список![cite: 1]",
        "rp_no_servers": "📭 Список серверов пуст[cite: 1].",
        "rp_select_to_del": "🗑 Выберите сервер для удаления[cite: 1]:",
        "rp_deleted": "✅ Сервер удален[cite: 1].",
        "raid_title": "💥 **Калькулятор рейда**\n\nВведите название цели (например: `Гаражка`, `Каменный шкаф`, `Каменный дом`):",
        "raid_result": "💥 **Расчет рейда для:** `{target}`\n\n• Сатчели (Satchel): 4 шт.\n• Срывные заряды (C4): 1 шт.\n• Ракеты: 2 шт.\n• Взрывчатка: учтено.",
        "btn_calc_more": "🔄 Посчитать еще",
        "no_tracked": "У вас нет отслеживаемых игроков.",
        "tracked_header": "👁 **Мои отслеживания:**\n",
        "search_id_prompt": "Отправьте мне **Steam ID 64**, ссылку или ник профиля:",
        "search_nick_prompt": "Введите **никнейм** игрока для поиска с пагинацией:",
        "search_not_found": "❌ Игрок не найден. Попробуйте еще раз:",
        "search_progress": "🔍 Ищу '{query}' в базе Steam...",
        "search_empty": "❌ По запросу **{query}** ничего не найдено.",
        "profile_loading": "🔍 Загружаю информацию об игроке...",
        "profile_hidden": "❌ Профиль скрыт или не найден.",
        "offline": "🔴 Оффлайн",
        "playing_rust": "🟢 Играет в Rust на сервере: **{server}**",
        "not_in_rust": "⚪️ В сети, но **не играет в Rust** (игра: {game})",
        "stats_block": "📊 Активность в Rust за неделю: {hours} ч.\n🌐 Информация о серверах обновлена",
        "profile_view": "👤 **Игрок:** {name}\n📌 **Статус:** {status}\n⏳ **В Rust (всего):** {total_hours} ч.\n⏳ **За последнюю неделю:** {two_weeks_hours} ч.\n\n🔗 [Профиль Steam]({link}) | [BattleMetrics]({bm_link}) | [RustStats]({ruststats_link})",
        "btn_track": "🔔 Отслеживать игрока",
        "btn_stop_track": "🛑 Прекратить отслеживание",
        "btn_check_bans": "🛡 Проверить баны",
        "bans_msg": "🛡 **Проверка банов для `{sid}`:**\n\n• Игровых/VAC банов: не обнаружено\n• Статус: Чист",
        "track_on": "✅ Отслеживание успешно включено! Я буду присылать уведомления, когда игрок заходит или выходит из Rust.",
        "track_off": "🛑 Отслеживание остановлено.",
        "notif_entered": "🔔 **Внимание!** Отслеживаемый игрок `{name}` зашел в Rust!",
        "notif_server": "🌐 **Игрок зашел на сервер:** `{server}`",
        "notif_left": "🔕 Игрок `{name}` вышел из Rust."
    },
    "en": {
        "main_menu": "👋 **Bot Main Menu:**\n\nSelect a section using the buttons below:",
        "home_btn": "🏠 Main Menu",
        "back_btn": "⬅️ Back to start",
        "stop_search": "🛑 Stop search",
        "btn_search_id": "🔍 Steam ID / URL",
        "btn_search_nick": "🔍 Nickname",
        "btn_rust_plus": "⚡️ Rust+",
        "btn_raid": "💥 Raid Calculator",
        "btn_tracked": "👁 My Tracked Players",
        "btn_zayats": "🐰 Zayats",
        "btn_about": "ℹ️ About Bot / Language",
        "zayats_prompt": "🐰 **Zayats Mode**\n\nSend me Steam ID 64:",
        "zayats_not_found": "❌ Player not found.",
        "about_text": "ℹ️ **About Bot / Language Selection:**",
        "lang_changed": "✅ Language successfully changed to English!",
        "rust_plus_menu_title": "⚡️ **Rust+ Menu**[cite: 1]",
        "rp_tab_online": "🟢 1. Online[cite: 1]",
        "rp_tab_map": "🗺 2. Map[cite: 1]",
        "rp_tab_third": "⚙️ 3. Settings / Other[cite: 1]",
        "rp_online_title": "🟢 **Servers List (Online):**[cite: 1]",
        "rp_map_title": "🗺 **Servers List (Map):**[cite: 1]",
        "btn_add_server": "➕ Add server[cite: 1]",
        "btn_delete_server": "🗑 Delete server[cite: 1]",
        "rp_prompt_ip": "🌐 **Enter exact server name**[cite: 1]",
        "rp_server_added": "✅ Server successfully added![cite: 1]",
        "rp_no_servers": "📭 Server list is empty[cite: 1].",
        "rp_select_to_del": "🗑 Select server to delete[cite: 1]:",
        "rp_deleted": "✅ Server deleted[cite: 1].",
        "raid_title": "💥 **Raid Calculator**",
        "raid_result": "💥 **Raid calculation for:** `{target}`",
        "btn_calc_more": "🔄 Calculate another",
        "no_tracked": "You have no tracked players.",
        "tracked_header": "👁 **My Tracked Players:**\n",
        "search_id_prompt": "Send me **Steam ID 64** or profile link:",
        "search_nick_prompt": "Enter player **nickname**:",
        "search_not_found": "❌ Player not found.",
        "search_progress": "🔍 Searching...",
        "search_empty": "❌ Nothing found.",
        "profile_loading": "🔍 Loading...",
        "profile_hidden": "❌ Profile is private.",
        "offline": "🔴 Offline",
        "playing_rust": "🟢 Playing Rust on server: **{server}**",
        "not_in_rust": "⚪️ Online, but not playing Rust",
        "stats_block": "📊 Playtime info updated",
        "profile_view": "👤 **Player:** {name}\n📌 **Status:** {status}\n⏳ **Rust Hours:** {total_hours}h (2 weeks: {two_weeks_hours}h)\n\n🔗 [Steam]({link}) | [BattleMetrics]({bm_link}) | [RustStats]({ruststats_link})",
        "btn_track": "🔔 Track",
        "btn_stop_track": "🛑 Stop",
        "btn_check_bans": "🛡 Check Bans",
        "bans_msg": "🛡 Clean",
        "track_on": "✅ Tracking enabled!",
        "track_off": "🛑 Tracking stopped.",
        "notif_entered": "🔔 Tracked player `{name}` joined Rust!",
        "notif_server": "🌐 **Player joined server:** `{server}`",
        "notif_left": "🔕 Player `{name}` left Rust."
    },
    "uk": {
        "main_menu": "👋 **Головне меню бота:**\n\nВиберіть потрібний розділ:",
        "home_btn": "🏠 Головне меню",
        "back_btn": "⬅️ Назад",
        "stop_search": "🛑 Зупинити",
        "btn_search_id": "🔍 Стім ID",
        "btn_search_nick": "🔍 Нікнейм",
        "btn_rust_plus": "⚡️ Rust+",
        "btn_raid": "💥 Рейд",
        "btn_tracked": "👁 Відстеження",
        "btn_zayats": "🐰 Заєць",
        "btn_about": "ℹ️ Про бота / Мова",
        "zayats_prompt": "🐰 **Режим Заєць**\n\nНадішліть Steam ID або нікнейм:",
        "zayats_not_found": "❌ Не вдалося знайти гравця.",
        "about_text": "ℹ️ **Про бота / Вибір мови:**",
        "lang_changed": "✅ Мову змінено!",
        "rust_plus_menu_title": "⚡️ **Меню Rust+**[cite: 1]",
        "rp_tab_online": "🟢 1. Онлайн[cite: 1]",
        "rp_tab_map": "🗺 2. Карта[cite: 1]",
        "rp_tab_third": "⚙️ 3. Інше[cite: 1]",
        "rp_online_title": "🟢 **Список серверів (Онлайн):**[cite: 1]",
        "rp_map_title": "🗺 **Список серверів (Карта):**[cite: 1]",
        "btn_add_server": "➕ Додати сервер[cite: 1]",
        "btn_delete_server": "🗑 Видалити[cite: 1]",
        "rp_prompt_ip": "🌐 **Введіть назву сервера**[cite: 1]",
        "rp_server_added": "✅ Сервер додано![cite: 1]",
        "rp_no_servers": "📭 Список порожній[cite: 1].",
        "rp_select_to_del": "🗑 Виберіть для видалення[cite: 1]:",
        "rp_deleted": "✅ Видалено[cite: 1].",
        "raid_title": "💥 **Калькулятор рейду**",
        "raid_result": "💥 **Розрахунок:** `{target}`",
        "btn_calc_more": "🔄 Ще",
        "no_tracked": "Немає відстежень.",
        "tracked_header": "👁 **Відстеження:**\n",
        "search_id_prompt": "Надішліть Steam ID:",
        "search_nick_prompt": "Введіть нік:",
        "search_not_found": "❌ Не знайдено.",
        "search_progress": "🔍 Шукаю...",
        "search_empty": "❌ Порожньо.",
        "profile_loading": "🔍 Завантаження...",
        "profile_hidden": "❌ Приховано.",
        "offline": "🔴 Офлайн",
        "playing_rust": "🟢 Грає в Rust: **{server}**",
        "not_in_rust": "⚪️ Не в Rust",
        "stats_block": "📊 Актуально",
        "profile_view": "👤 **Гравець:** {name}\n📌 **Статус:** {status}\n⏳ **Годин у Rust:** {total_hours} год (за 2 тижні: {two_weeks_hours} год)\n\n🔗 [Steam]({link}) | [BattleMetrics]({bm_link}) | [RustStats]({ruststats_link})",
        "btn_track": "🔔 Стежити",
        "btn_stop_track": "🛑 Зупинити",
        "btn_check_bans": "🛡 Бани",
        "bans_msg": "🛡 Чистий",
        "track_on": "✅ Увімкнено!",
        "track_off": "🛑 Зупинено.",
        "notif_entered": "🔔 Гравець `{name}` зайшов у Rust!",
        "notif_server": "🌐 **Гравець зайшов на сервер:** `{server}`",
        "notif_left": "🔕 Гравець `{name}` вийшов з Rust."
    }
}

class SearchState(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_nickname = State()

class RustPlusFlowState(StatesGroup):
    waiting_for_ip = State()
    waiting_for_map_input = State()

class RaidCalculatorState(StatesGroup):
    waiting_for_target = State()

class ZayatsState(StatesGroup):
    waiting_for_steam_id = State()

def get_lang(user_id: int) -> str:
    return user_languages.get(user_id, "ru")

def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_lang(user_id)
    text = LANGS.get(lang, LANGS["ru"]).get(key, LANGS["ru"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text

def main_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton(text=t(user_id, "btn_search_id"), callback_data="start_search_id"),
            InlineKeyboardButton(text=t(user_id, "btn_search_nick"), callback_data="start_search_nick")
        ],
        [InlineKeyboardButton(text=t(user_id, "btn_rust_plus"), callback_data="rust_plus_menu")],
        [InlineKeyboardButton(text=t(user_id, "btn_raid"), callback_data="raid_calc_start")],
        [InlineKeyboardButton(text=t(user_id, "btn_tracked"), callback_data="show_tracked_list")],
        [InlineKeyboardButton(text=t(user_id, "btn_zayats"), callback_data="zayats_menu_start")],
        [InlineKeyboardButton(text=t(user_id, "btn_about"), callback_data="about_bot")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def stop_search_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "stop_search"), callback_data="go_home")]
    ])

def back_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="go_home")]
    ])

def result_keyboard(user_id, steam_id, is_tracked=False):
    if is_tracked:
        track_btn = InlineKeyboardButton(text=t(user_id, "btn_stop_track"), callback_data=f"stop_track_{steam_id}")
    else:
        track_btn = InlineKeyboardButton(text=t(user_id, "btn_track"), callback_data=f"start_track_{steam_id}")
        
    return InlineKeyboardMarkup(inline_keyboard=[
        [track_btn],
        [InlineKeyboardButton(text=t(user_id, "btn_check_bans"), callback_data=f"check_bans_{steam_id}")],
        [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="go_home")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    last_search_message.pop(user_id, None)

    await message.answer(
        t(user_id, "main_menu"),
        reply_markup=main_keyboard(user_id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    last_search_message.pop(user_id, None)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        t(user_id, "main_menu"),
        reply_markup=main_keyboard(user_id),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "about_bot")
async def about_bot_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    keyboard = [
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")
        ],
        [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="go_home")]
    ]
    await callback.message.edit_text(
        t(user_id, "about_text"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[-1]
    user_languages[user_id] = lang
    
    await callback.answer(t(user_id, "lang_changed"), show_alert=True)
    await callback.message.edit_text(
        t(user_id, "main_menu"),
        reply_markup=main_keyboard(user_id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "start_search_id")
async def start_search_id(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "search_id_prompt"),
        reply_markup=stop_search_keyboard(user_id),
        parse_mode="Markdown"
    )
    last_search_message[user_id] = callback.message.message_id
    await state.set_state(SearchState.waiting_for_steam_id)
    await callback.answer()

@router.message(SearchState.waiting_for_steam_id)
async def process_steam_id_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    steam_id = text
    if "steamcommunity.com/id/" in text:
        vanity = text.rstrip("/").split("/")[-1]
        steam_id = await resolve_vanity_url(vanity)
    elif "steamcommunity.com/profiles/" in text:
        steam_id = text.rstrip("/").split("/")[-1]
    else:
        steam_id = await resolve_vanity_url(text)

    msg_id = last_search_message.get(user_id)
    if msg_id:
        try:
            await bot.edit_message_text(t(user_id, "profile_loading"), chat_id=user_id, message_id=msg_id)
        except Exception:
            pass

    await show_player_profile_by_id(user_id, steam_id, msg_id, state)

async def resolve_vanity_url(query: str) -> str:
    if query.isdigit() and len(query) == 17:
        return query

    url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={query}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if data.get("response", {}).get("success") == 1:
                return data["response"]["steamid"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://steamcommunity.com/search/suggesthandler/?text={quote(query)}&category=users&cc=US&l=english&json=1") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list) and "steamid" in data[0]:
                        return data[0]["steamid"]
    except Exception as e:
        logging.error(f"Fallback nick search error: {e}")

    return query

async def fetch_rust_playtime(steam_id: str) -> tuple:
    url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&include_appinfo=true&format=json"
    total_hours = 0.0
    two_weeks_hours = 0.0
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    games = data.get("response", {}).get("games", [])
                    for g in games:
                        if str(g.get("appid")) == "252490":
                            total_hours = round(g.get("playtime_forever", 0) / 60, 1)
                            two_weeks_hours = round(g.get("playtime_2weeks", 0) / 60, 1)
                            break
    except Exception as e:
        logging.error(f"Error fetching rust playtime: {e}")
    return total_hours, two_weeks_hours

async def show_player_profile_by_id(user_id: int, steam_id: str, msg_id: int, state: FSMContext):
    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            if not players:
                if msg_id:
                    await bot.edit_message_text(t(user_id, "profile_hidden"), chat_id=user_id, message_id=msg_id, reply_markup=back_keyboard(user_id))
                return
            
            p = players[0]
            name = p.get("personaname", "Unknown")
            profile_url = p.get("profileurl", "#")
            gameid = str(p.get("gameid", ""))
            game_extra = p.get("gameextrainfo", "")
            
            if gameid == "252490" or "Rust" in game_extra:
                status = t(user_id, "playing_rust", server=game_extra or "Rust Server")
            elif p.get("personastate", 0) > 0:
                status = t(user_id, "not_in_rust", game=game_extra or "Another game")
            else:
                status = t(user_id, "offline")

            total_hours, two_weeks_hours = await fetch_rust_playtime(steam_id)

            bm_link = f"https://www.battlemetrics.com/rcon/players?filter%5Bsearch%5D={steam_id}"
            ruststats_link = f"https://ruststats.io/profile/{steam_id}"

            is_tracked = user_id in tracked_players_list and steam_id in tracked_players_list[user_id]
            
            text = t(
                user_id, "profile_view", 
                name=name, 
                status=status, 
                total_hours=total_hours, 
                two_weeks_hours=two_weeks_hours, 
                link=profile_url, 
                bm_link=bm_link, 
                ruststats_link=ruststats_link,
                sid=steam_id
            )
            
            if msg_id:
                try:
                    await bot.edit_message_text(
                        text, 
                        chat_id=user_id, 
                        message_id=msg_id, 
                        reply_markup=result_keyboard(user_id, steam_id, is_tracked), 
                        parse_mode="Markdown", 
                        disable_web_page_preview=True
                    )
                except Exception:
                    sent = await bot.send_message(
                        user_id, 
                        text, 
                        reply_markup=result_keyboard(user_id, steam_id, is_tracked), 
                        parse_mode="Markdown", 
                        disable_web_page_preview=True
                    )
                    last_search_message[user_id] = sent.message_id
    await state.clear()

@router.callback_query(F.data == "start_search_nick")
async def start_search_nick(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "search_nick_prompt"),
        reply_markup=stop_search_keyboard(user_id),
        parse_mode="Markdown"
    )
    last_search_message[user_id] = callback.message.message_id
    await state.set_state(SearchState.waiting_for_nickname)
    await callback.answer()

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
            await bot.edit_message_text(t(user_id, "search_progress", query=query), chat_id=user_id, message_id=msg_id)
        except Exception:
            pass

    results = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://steamcommunity.com/search/suggesthandler/?text={quote(query)}&category=users&cc=US&l=english&json=1") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        results.append({
                            "steamid": item.get("steamid"),
                            "name": item.get("name"),
                            "avatar": item.get("icon")
                        })
    except Exception as e:
        logging.error(f"Steam suggest error: {e}")

    if not results:
        if msg_id:
            await bot.edit_message_text(t(user_id, "search_empty", query=query), chat_id=user_id, message_id=msg_id, reply_markup=back_keyboard(user_id))
        return

    search_cache[user_id] = results
    await show_search_page(user_id, msg_id, 0)
    await state.clear()

async def show_search_page(user_id: int, msg_id: int, page: int):
    results = search_cache.get(user_id, [])
    per_page = 5
    total_pages = (len(results) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    
    chunk = results[page * per_page : (page + 1) * per_page]
    keyboard = []
    for user in chunk:
        keyboard.append([InlineKeyboardButton(text=user["name"], callback_data=f"sel_id_{user['steamid']}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"search_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"search_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="go_home")])

    text = f"🔍 **Результаты поиска ({len(results)} найдено):**"
    try:
        await bot.edit_message_text(text, chat_id=user_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        pass

@router.callback_query(F.data.startswith("search_page_"))
async def pagination_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    page = int(callback.data.split("_")[-1])
    await show_search_page(user_id, callback.message.message_id, page)
    await callback.answer()

@router.callback_query(F.data.startswith("sel_id_"))
async def select_searched_id(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    steam_id = callback.data.split("_")[-1]
    await show_player_profile_by_id(user_id, steam_id, callback.message.message_id, state)
    await callback.answer()

@router.callback_query(F.data.startswith("check_bans_"))
async def check_bans_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    steam_id = callback.data.split("_")[-1]
    
    url = f"https://api.steampowered.com/ISteamUser/GetPlayerBans/v0001/?key={STEAM_API_KEY}&steamids={steam_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            players = data.get("players", [])
            if players:
                p = players[0]
                vac = p.get("NumberOfVACBans", 0)
                game = p.get("NumberOfGameBans", 0)
                economy = p.get("EconomyBan", "none")
                msg = (
                    f"🛡 **Проверка банов для `{steam_id}`:**\n\n"
                    f"• VAC банов: `{vac}`\n"
                    f"• Игровых банов: `{game}`\n"
                    f"• Торговый бан: `{economy}`\n"
                    f"• Статус: {'🚨 Обнаружены баны!' if (vac > 0 or game > 0) else '✅ Чист'}"
                )
            else:
                msg = t(user_id, "bans_msg", sid=steam_id)
                
    await callback.answer(msg, show_alert=True)

@router.callback_query(F.data.startswith("start_track_"))
async def start_track_player(callback: CallbackQuery):
    user_id = callback.from_user.id
    steam_id = callback.data.split("_")[-1]
    
    if user_id not in tracked_players_list:
        tracked_players_list[user_id] = set()
    tracked_players_list[user_id].add(steam_id)
    
    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                players = data.get("response", {}).get("players", [])
                if players:
                    p = players[0]
                    gameid = str(p.get("gameid", ""))
                    game_extra = p.get("gameextrainfo", "")
                    is_in_rust = (gameid == "252490" or "Rust" in game_extra)
                    
                    if user_id not in player_last_status:
                        player_last_status[user_id] = {}
                    player_last_status[user_id][steam_id] = is_in_rust
    except Exception as e:
        logging.error(f"Error initializing track status: {e}")

    await callback.answer(t(user_id, "track_on"), show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=result_keyboard(user_id, steam_id, is_tracked=True))
    except Exception:
        pass

@router.callback_query(F.data.startswith("stop_track_"))
async def stop_track_player(callback: CallbackQuery):
    user_id = callback.from_user.id
    steam_id = callback.data.split("_")[-1]
    
    if user_id in tracked_players_list:
        tracked_players_list[user_id].discard(steam_id)
        
    if user_id in player_last_status:
        player_last_status[user_id].pop(steam_id, None)
        
    await callback.answer(t(user_id, "track_off"), show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=result_keyboard(user_id, steam_id, is_tracked=False))
    except Exception:
        pass

@router.callback_query(F.data == "show_tracked_list")
async def show_tracked_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    tracked = tracked_players_list.get(user_id, set())
    
    if not tracked:
        await callback.answer(t(user_id, "no_tracked"), show_alert=True)
        return
        
    text = t(user_id, "tracked_header")
    keyboard = []
    for sid in tracked:
        keyboard.append([InlineKeyboardButton(text=f"ID: {sid}", callback_data=f"sel_id_{sid}")])
    keyboard.append([InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="go_home")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

async def background_player_monitor():
    while True:
        await asyncio.sleep(5)  # Интервал проверки
        if not tracked_players_list:
            continue
            
        all_sids = set()
        for s_set in tracked_players_list.values():
            all_sids.update(s_set)
            
        if not all_sids:
            continue
            
        sids_str = ",".join(all_sids)
        url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={sids_str}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    players = data.get("response", {}).get("players", [])
                    
                    found_sids = set()
                    for p in players:
                        sid = p.get("steamid")
                        found_sids.add(sid)
                        name = p.get("personaname", "Player")
                        gameid = str(p.get("gameid", ""))
                        game_extra = p.get("gameextrainfo", "")
                        
                        is_in_rust = (gameid == "252490" or "Rust" in game_extra)
                        
                        for user_id, user_sids in tracked_players_list.items():
                            if sid in user_sids:
                                if user_id not in player_last_status:
                                    player_last_status[user_id] = {}
                                
                                last_status = player_last_status[user_id].get(sid)
                                
                                if last_status is None:
                                    player_last_status[user_id][sid] = is_in_rust
                                    continue

                                if is_in_rust and not last_status:
                                    try:
                                        # 1. Первое уведомление: что игрок зашел в Rust
                                        await bot.send_message(
                                            user_id, 
                                            t(user_id, "notif_entered", name=name), 
                                            parse_mode="Markdown"
                                        )
                                        
                                        # 2. Второе уведомление отдельным сообщением снизу: на какой сервер
                                        server_name = game_extra if game_extra else "Неизвестный сервер"
                                        await asyncio.sleep(0.3)
                                        await bot.send_message(
                                            user_id, 
                                            t(user_id, "notif_server", server=server_name), 
                                            parse_mode="Markdown"
                                        )
                                    except Exception as e:
                                        logging.error(f"Failed to send enter notification: {e}")
                                
                                elif not is_in_rust and last_status:
                                    try:
                                        await bot.send_message(user_id, t(user_id, "notif_left", name=name), parse_mode="Markdown")
                                    except Exception as e:
                                        logging.error(f"Failed to send leave notification: {e}")
                                
                                player_last_status[user_id][sid] = is_in_rust

                    for user_id, user_sids in tracked_players_list.items():
                        for sid in user_sids:
                            if sid not in found_sids:
                                if user_id in player_last_status and player_last_status[user_id].get(sid) == True:
                                    player_last_status[user_id][sid] = False
                                    try:
                                        await bot.send_message(user_id, t(user_id, "notif_left", name=f"ID {sid}"), parse_mode="Markdown")
                                    except Exception as e:
                                        logging.error(f"Failed to send forced leave notification: {e}")

        except Exception as e:
            logging.error(f"Background monitor error: {e}")

@router.callback_query(F.data == "rust_plus_menu")
async def rust_plus_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    keyboard = [
        [InlineKeyboardButton(text=t(user_id, "rp_tab_online"), callback_data="rp_tab_online_click")],
        [InlineKeyboardButton(text=t(user_id, "rp_tab_map"), callback_data="rp_tab_map_click")],
        [InlineKeyboardButton(text=t(user_id, "rp_tab_third"), callback_data="rp_tab_third_click")],
        [InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")]
    ]

    try:
        await callback.message.edit_text(t(user_id, "rust_plus_menu_title"), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(t(user_id, "rust_plus_menu_title"), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "rp_tab_online_click")
async def rp_tab_online(callback: CallbackQuery):
    user_id = callback.from_user.id
    servers = user_servers.get(user_id, [])
    
    keyboard = []
    for srv in servers:
        keyboard.append([InlineKeyboardButton(text=f"🟢 {srv}", callback_data=f"rp_view_srv_{srv}")])
        
    keyboard.append([InlineKeyboardButton(text=t(user_id, "btn_add_server"), callback_data="rp_add_server_prompt")])
    if servers:
        keyboard.append([InlineKeyboardButton(text=t(user_id, "btn_delete_server"), callback_data="rp_del_server_menu")])
    keyboard.append([InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")])
    
    text = t(user_id, "rp_online_title")
    if not servers:
        text += f"\n\n{t(user_id, 'rp_no_servers')}"
        
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "rp_tab_map_click")
async def rp_tab_map(callback: CallbackQuery):
    user_id = callback.from_user.id
    servers = user_servers.get(user_id, [])
    
    keyboard = []
    for srv in servers:
        keyboard.append([InlineKeyboardButton(text=f"🗺 {srv}", callback_data=f"rp_map_srv_{srv}")])
    keyboard.append([InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")])
    
    text = t(user_id, "rp_map_title")
    if not servers:
        text += f"\n\n{t(user_id, 'rp_no_servers')}"
        
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "rp_tab_third_click")
async def rp_tab_third(callback: CallbackQuery):
    user_id = callback.from_user.id
    keyboard = [
        [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")]
    ]
    await callback.message.edit_text("⚙️ **Настройки Rust+ и уведомлений вайпа:**\n\nЗдесь вы можете настроить оповещения о выходе глобал/компонент вайпов.", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "rp_add_server_prompt")
async def rp_add_server_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "rp_prompt_ip"),
        reply_markup=back_keyboard(user_id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusFlowState.waiting_for_ip)
    await callback.answer()

@router.message(RustPlusFlowState.waiting_for_ip)
async def rp_save_server(message: Message, state: FSMContext):
    user_id = message.from_user.id
    srv_name = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
        
    if user_id not in user_servers:
        user_servers[user_id] = []
    if srv_name not in user_servers[user_id]:
        user_servers[user_id].append(srv_name)
        
    await message.answer(t(user_id, "rp_server_added"), reply_markup=back_keyboard(user_id))
    await state.clear()

@router.callback_query(F.data == "rp_del_server_menu")
async def rp_del_server_menu(callback: CallbackQuery):
    user_id = callback.from_user.id
    servers = user_servers.get(user_id, [])
    
    keyboard = []
    for srv in servers:
        keyboard.append([InlineKeyboardButton(text=f"❌ {srv}", callback_data=f"rp_del_srv_{srv}")])
    keyboard.append([InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")])
    
    await callback.message.edit_text(t(user_id, "rp_select_to_del"), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("rp_del_srv_"))
async def rp_delete_server_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    srv_name = callback.data.replace("rp_del_srv_", "")
    
    if user_id in user_servers and srv_name in user_servers[user_id]:
        user_servers[user_id].remove(srv_name)
        
    await callback.answer(t(user_id, "rp_deleted"), show_alert=True)
    await rp_tab_online(callback)

@router.callback_query(F.data.startswith("rp_view_srv_"))
async def rp_view_server_details(callback: CallbackQuery):
    user_id = callback.from_user.id
    srv_name = callback.data.replace("rp_view_srv_", "")
    
    await callback.answer("⏳ Загрузка информации о сервере...")
    info = await fetch_server_details_by_name(srv_name)
    
    history_snippet = info['history'][:600]
    server_title = info['server_name']
    
    b = chr(96) * 3
    code_block = f"{b}text\n{history_snippet}\n{b}"
    
    text = (
        f"🟢 **Сервер:** `{server_title}`\n\n"
        f"📋 **Последняя активность / История:**\n"
        f"{code_block}"
    )
    keyboard = [[InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")]]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")

@router.callback_query(F.data.startswith("rp_map_srv_"))
async def rp_view_server_map(callback: CallbackQuery):
    user_id = callback.from_user.id
    srv_name = callback.data.replace("rp_map_srv_", "")
    
    keyboard = [[InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")]]
    await callback.message.edit_text(f"🗺 **Карта сервера `{srv_name}`:**\n\n(Интеграция с генератором карт загружается)", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

async def fetch_server_details_by_name(server_name: str):
    async with aiohttp.ClientSession() as session:
        bm_history_text = "History not found."
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            bm_search_url = f"https://www.battlemetrics.com/servers/rust?q={quote(server_name)}"
            async with session.get(bm_search_url, headers=headers) as resp:
                if resp.status == 200:
                    bm_html = await resp.text()
                    server_link_match = re.search(r'href="(/servers/rust/\d+-[^"]+)"', bm_html)
                    if server_link_match:
                        server_profile_url = f"https://www.battlemetrics.com{server_link_match.group(1)}"
                        async with session.get(server_profile_url, headers=headers) as profile_resp:
                            if profile_resp.status == 200:
                                profile_html = await profile_resp.text()
                                history_rows = re.findall(r'<tr[^>]*>(.*?)<\/tr>', profile_html, re.DOTALL)
                                if history_rows:
                                    extracted = []
                                    for row in history_rows[:15]:
                                        clean_row = re.sub(r'<[^>]+>', ' ', row).strip()
                                        clean_row = re.sub(r'\s+', ' ', clean_row)
                                        if clean_row:
                                            extracted.append(clean_row)
                                    if extracted:
                                        bm_history_text = "\n".join(extracted)
        except Exception as e:
            logging.error(f"BattleMetrics request error: {e}")

        return {
            "server_name": server_name,
            "history": bm_history_text
        }

@router.callback_query(F.data == "raid_calc_start")
async def raid_calc_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "raid_title"),
        reply_markup=stop_search_keyboard(user_id),
        parse_mode="Markdown"
    )
    await state.set_state(RaidCalculatorState.waiting_for_target)
    await callback.answer()

@router.message(RaidCalculatorState.waiting_for_target)
async def process_raid_target(message: Message, state: FSMContext):
    user_id = message.from_user.id
    target = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
        
    text = t(user_id, "raid_result", target=target)
    keyboard = [
        [InlineKeyboardButton(text=t(user_id, "btn_calc_more"), callback_data="raid_calc_start")],
        [InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="go_home")]
    ]
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await state.clear()

@router.callback_query(F.data == "zayats_menu_start")
async def zayats_menu_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "zayats_prompt"),
        reply_markup=stop_search_keyboard(user_id),
        parse_mode="Markdown"
    )
    last_search_message[user_id] = callback.message.message_id
    await state.set_state(ZayatsState.waiting_for_steam_id)
    await callback.answer()

@router.message(ZayatsState.waiting_for_steam_id)
async def process_zayats_input(message: Message, state: FSMContext):
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

    steam_id = await resolve_vanity_url(user_input)
    ruststats_link = f"https://ruststats.io/profile/{steam_id}"

    keyboard = [[InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="go_home")]]
    await message.answer(
        f"🐰 **RustStats Профиль:**\n\n🔗 Ссылка на статистику игрока:\n{ruststats_link}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await state.clear()

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(background_player_monitor())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
