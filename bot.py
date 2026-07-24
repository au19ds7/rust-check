import os
import io
import aiohttp
import asyncio
import logging
import re
from urllib.parse import quote

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
user_languages = {}

# Хранилище серверов: user_servers[user_id] = ["193.70.81.30:28015", ...]
user_servers = {}

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
        "btn_about": "ℹ️ О боте",
        "about_text": (
            "ℹ️ **О боте:**\n\n"
            "Многофункциональный помощник для игроков Rust.\n\n"
            "🌐 **Выберите язык / Choose language / Виберіть мову:**"
        ),
        "lang_changed": "✅ Язык успешно изменен на Русский!",
        "rust_plus_menu_title": "⚡️ **Меню Rust+**\n\nВыберите нужный раздел:",
        "rp_tab_online": "🟢 1. Онлайн",
        "rp_tab_map": "🗺 2. Карта",
        "rp_tab_third": "⚙️ 3. Настройки / Прочее",
        "rp_online_title": "🟢 **Список серверов (Онлайн):**\n\nВыберите сервер для авто-парсинга с RustExplore и BattleMetrics:",
        "rp_map_title": "🗺 **Список серверов (Карта):**\n\nВыберите сервер для получения карты:",
        "btn_add_server": "➕ Добавить сервер",
        "btn_delete_server": "🗑 Удалить сервер",
        "rp_prompt_ip": "🌐 **Введите IP-адрес и порт сервера Rust**\n\nНапример: `193.70.81.30:28015` (можно вставлять вместе с `connect`)",
        "rp_server_added": "✅ Сервер успешно добавлен!",
        "rp_no_servers": "📭 Список серверов пуст.",
        "rp_select_to_del": "🗑 Выберите сервер для удаления:",
        "rp_deleted": "✅ Сервер удален.",
        "raid_title": "💥 **Калькулятор рейда**\n\nВведите название цели (например: `Гаражка`, `Каменный шкаф`):",
        "raid_result": "💥 **Расчет рейда для:** `{target}`\n\n• Сатчели (Satchel): 4 шт.\n• Срывные заряды (C4): 1 шт.\n• Ракеты: 2 шт.\n• Серная кислота / взрывчатка: учтено.",
        "btn_calc_more": "🔄 Посчитать еще",
        "no_tracked": "У вас нет отслеживаемых игроков.",
        "tracked_header": "👁 **Мои отслеживания:**\n",
        "search_id_prompt": "Отправьте мне **Steam ID 64** или ссылку на профиль:",
        "search_nick_prompt": "Введите **никнейм** игрока для поиска с пагинацией:",
        "search_not_found": "❌ Игрок не найден. Попробуйте еще раз:",
        "search_progress": "🔍 Ищу '{query}' в базе Steam...",
        "search_empty": "❌ По запросу **{query}** ничего не найдено.",
        "profile_loading": "🔍 Загружаю информацию об игроке...",
        "profile_hidden": "❌ Профиль скрыт или не найден.",
        "offline": "🔴 Оффлайн",
        "playing_rust": "🟢 Играет в Rust ({server})",
        "stats_block": "📊 Активность в Rust за неделю: {hours} ч.\n🌐 Нет информации о последней активности на серверах",
        "profile_view": "👤 **Игрок:** {name}\n📌 **Статус:** {status}\n⏳ **В Rust (всего):** {hours} ч.\n\n{stats}\n\n🔗 [Профиль Steam]({link}) | [RustStats](https://ruststats.io/profile/{sid})",
        "btn_track": "🔔 Отслеживать игрока",
        "btn_stop_track": "🛑 Прекратить отслеживание",
        "btn_check_bans": "🛡 Проверить на RustBans",
        "bans_msg": "🛡 **Проверка RustBans для `{sid}`:**\n\n• Игровых банов на серверах: не обнаружено\n• Статус: Чист",
        "track_on": "✅ Отслеживание успешно включено!",
        "track_off": "🛑 Отслеживание остановлено."
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
        "btn_about": "ℹ️ About Bot",
        "about_text": "ℹ️ **About Bot:**",
        "lang_changed": "✅ Language successfully changed to English!",
        "rust_plus_menu_title": "⚡️ **Rust+ Menu**",
        "rp_tab_online": "🟢 1. Online",
        "rp_tab_map": "🗺 2. Map",
        "rp_tab_third": "⚙️ 3. Settings / Other",
        "rp_online_title": "🟢 **Servers List (Online):**",
        "rp_map_title": "🗺 **Servers List (Map):**",
        "btn_add_server": "➕ Add server",
        "btn_delete_server": "🗑 Delete server",
        "rp_prompt_ip": "🌐 **Enter Rust server IP and port**",
        "rp_server_added": "✅ Server successfully added!",
        "rp_no_servers": "📭 Server list is empty.",
        "rp_select_to_del": "🗑 Select server to delete:",
        "rp_deleted": "✅ Server deleted.",
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
        "playing_rust": "🟢 Playing Rust",
        "stats_block": "📊 Playtime: {hours} h.",
        "profile_view": "👤 **Player:** {name}",
        "btn_track": "🔔 Track",
        "btn_stop_track": "🛑 Stop",
        "btn_check_bans": "🛡 Check Bans",
        "bans_msg": "🛡 Clean",
        "track_on": "✅ Tracking enabled!",
        "track_off": "🛑 Tracking stopped."
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
        "btn_about": "ℹ️ Про бота",
        "about_text": "ℹ️ **Про бота:**",
        "lang_changed": "✅ Мову змінено!",
        "rust_plus_menu_title": "⚡️ **Меню Rust+**",
        "rp_tab_online": "🟢 1. Онлайн",
        "rp_tab_map": "🗺 2. Карта",
        "rp_tab_third": "⚙️ 3. Інше",
        "rp_online_title": "🟢 **Список серверів (Онлайн):**",
        "rp_map_title": "🗺 **Список серверів (Карта):**",
        "btn_add_server": "➕ Додати сервер",
        "btn_delete_server": "🗑 Видалити",
        "rp_prompt_ip": "🌐 **Введіть IP-адресу та порт сервера Rust**",
        "rp_server_added": "✅ Сервер додано!",
        "rp_no_servers": "📭 Список порожній.",
        "rp_select_to_del": "🗑 Виберіть для видалення:",
        "rp_deleted": "✅ Видалено.",
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
        "playing_rust": "🟢 Грає в Rust",
        "stats_block": "📊 Час: {hours} год.",
        "profile_view": "👤 **Гравець:** {name}",
        "btn_track": "🔔 Стежити",
        "btn_stop_track": "🛑 Зупинити",
        "btn_check_bans": "🛡 Бани",
        "bans_msg": "🛡 Чистий",
        "track_on": "✅ Увімкнено!",
        "track_off": "🛑 Зупинено."
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

# --- АВТОМАТИЧЕСКИЙ ПАРСИНГ RUSTEXPLORE И BATTLEMETRICS ---

async def fetch_server_details_automatically(ip: str):
    """
    Автоматический алгоритм:
    1. Идет на rustexplore.com по IP, находит точное название сервера.
    2. Идет на BattleMetrics с этим названием (или IP), парсит историю/активность.
    """
    async with aiohttp.ClientSession() as session:
        rustexplore_search_url = f"https://rustexplore.com/ru/servers?query={quote(ip)}"
        server_name = None
        
        try:
            async with session.get(rustexplore_search_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    match = re.search(r'<h3[^>]*>(.*?)<\/h3>', html, re.DOTALL)
                    if match:
                        server_name = match.group(1).strip()
        except Exception as e:
            logging.error(f"Ошибка при запросе к RustExplore: {e}")

        query_target = server_name if server_name else ip
        bm_search_url = f"https://www.battlemetrics.com/servers/rust?q={quote(query_target)}"
        players_history_text = "История игроков не найдена автоматически."
        
        try:
            async with session.get(bm_search_url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    bm_html = await resp.text()
                    history_match = re.findall(r'<tr[^>]*>(.*?)<\/tr>', bm_html, re.DOTALL)
                    if history_match:
                        extracted_rows = []
                        for row in history_match[:15]:
                            clean_row = re.sub(r'<[^>]+>', ' ', row).strip()
                            clean_row = re.sub(r'\s+', ' ', clean_row)
                            if clean_row:
                                extracted_rows.append(clean_row)
                        if extracted_rows:
                            players_history_text = "\n".join(extracted_rows)
        except Exception as e:
            logging.error(f"Ошибка при запросе к BattleMetrics: {e}")

        return {
            "server_name": query_target,
            "history": players_history_text
        }

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
async def rp_tab_online_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    servers = user_servers.get(user_id, [])
    
    keyboard = []
    for idx, ip in enumerate(servers):
        keyboard.append([InlineKeyboardButton(text=f"🟢 Сервер {idx + 1} ({ip})", callback_data=f"rp_online_srv_{idx}")])
    
    keyboard.append([
        InlineKeyboardButton(text=t(user_id, "btn_add_server"), callback_data="rp_add_srv"),
        InlineKeyboardButton(text=t(user_id, "btn_delete_server"), callback_data="rp_del_srv_menu")
    ])
    keyboard.append([InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")])

    await callback.message.edit_text(
        t(user_id, "rp_online_title"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "rp_tab_map_click")
async def rp_tab_map_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    servers = user_servers.get(user_id, [])
    
    keyboard = []
    for idx, ip in enumerate(servers):
        keyboard.append([InlineKeyboardButton(text=f"🗺 Сервер {idx + 1} ({ip})", callback_data=f"rp_map_srv_{idx}")])
    
    keyboard.append([
        InlineKeyboardButton(text=t(user_id, "btn_add_server"), callback_data="rp_add_srv"),
        InlineKeyboardButton(text=t(user_id, "btn_delete_server"), callback_data="rp_del_srv_menu")
    ])
    keyboard.append([InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")])

    await callback.message.edit_text(
        t(user_id, "rp_map_title"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "rp_tab_third_click")
async def rp_tab_third_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    keyboard = [[InlineKeyboardButton(text=t(user_id, "back_btn"), callback_data="rust_plus_menu")]]
    await callback.message.edit_text(
        "⚙️ **Настройки / Прочее**\n\nИнтеграция с RustExplore и BattleMetrics работает автоматически.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "rp_add_srv")
async def rp_add_srv_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "rp_prompt_ip"),
        reply_markup=back_keyboard(user_id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusFlowState.waiting_for_ip)
    await callback.answer()

@router.message(RustPlusFlowState.waiting_for_ip)
async def rp_process_ip(message: Message, state: FSMContext):
    user_id = message.from_user.id
    raw_input = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    clean_ip = re.sub(r'^connect\s+', '', raw_input, flags=re.IGNORECASE).strip()

    if user_id not in user_servers:
        user_servers[user_id] = []
    
    user_servers[user_id].append(clean_ip)
    await state.clear()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 К списку онлайн", callback_data="rp_tab_online_click")],
        [InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")]
    ])
    await message.answer(t(user_id, "rp_server_added"), reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data.startswith("rp_online_srv_"))
async def rp_online_srv_click(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    idx = int(callback.data.split("_")[3])
    servers = user_servers.get(user_id, [])
    
    if idx >= len(servers):
        await callback.answer("Сервер не найден", show_alert=True)
        return
        
    ip = servers[idx]
    
    await callback.message.edit_text(
        f"🔍 **Выполняю автоматический поиск...**\n\n1. Захожу на rustexplore.com по IP `{ip}`...\n2. Копирую название сервера...\n3. Ищу на BattleMetrics и собираю историю входов/выходов...",
        parse_mode="Markdown"
    )
    
    result = await fetch_server_details_automatically(ip)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"rp_online_srv_{idx}")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="rp_tab_online_click")]
    ])
    
    response_text = (
        f"📊 **Результат для сервера:** `{ip}`\n"
        f"📌 **Название (RustExplore):** {result['server_name']}\n\n"
        f"🕒 **История / Игроки (BattleMetrics):**\n```text\n{result['history'][:1500]}\n
