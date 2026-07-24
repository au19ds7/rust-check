import os
import io
import aiohttp
import asyncio
import logging
import re
import a2s
from urllib.parse import quote
from PIL import Image, ImageDraw

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
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
user_languages = {} # Хранит выбранный язык пользователей (по умолчанию 'ru')

# --- СЛОВАРЬ ПЕРЕВОДОВ ---
LANGS = {
    "ru": {
        "main_menu": "👋 **Главное меню бота:**\n\nВыберите нужный раздел с помощью кнопок ниже:",
        "home_btn": "🏠 Главное меню",
        "back_btn": "⬅️ Вернуться на самое начало",
        "stop_search": "🛑 Прекратить поиск",
        "btn_search_id": "🔍 Стим ID / Ссылка",
        "btn_search_nick": "🔍 Никнейм",
        "btn_monitor": "⚡️ Мониторинг сервера (IP)",
        "btn_raid": "💥 Калькулятор рейда",
        "btn_tracked": "👁 Мои отслеживания",
        "btn_about": "ℹ️ О боте",
        "about_text": (
            "ℹ️ **О боте:**\n\n"
            "Многофункциональный помощник для игроков Rust. Включает поиск Steam, интеграцию с RustBans, калькулятор рейда и мониторинг серверов.\n\n"
            "🌐 **Выберите язык / Choose language / Виберіть мову:**"
        ),
        "lang_changed": "✅ Язык успешно изменен на Русский!",
        "net_menu_title": "⚡️ **Мониторинг сервера Rust:**\n\nНажмите кнопку ниже, чтобы ввести IP-адрес и порт сервера и мгновенно получить информацию о нем.",
        "net_btn_check": "🌐 Проверить сервер по IP",
        "net_prompt": "🌐 **Введите IP-адрес и порт сервера Rust**\n\nНапример: `193.70.81.30:28015` (можно вставлять вместе с `connect`)",
        "net_polling": "⏳ Опрашиваю игровой сервер...",
        "net_bad_format": "❌ Неверный формат. Используйте формат `IP:Порт` (например: `193.70.81.30:28015`)",
        "net_bad_port": "❌ Порт должен состоять только из цифр.",
        "net_online": "🟢 **Сервер в сети!**\n\n📌 **Название:** {name}\n🗺 **Карта:** {map}\n👥 **Онлайн:** {players} / {max_players} игроков\n📶 **Пинг:** {ping} мс\n⚙️ **Версия игры:** {version}\n",
        "net_error": "❌ Не удалось подключиться к серверу `{ip}`.\n\nВозможные причины:\n• Указан неверный IP или порт\n• Сервер выключен или перезагружается\n*(Ошибка: {err})*",
        "btn_retry": "🔄 Попробовать снова",
        "btn_check_another": "🔄 Проверить другой сервер",
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
        "btn_monitor": "⚡️ Server Monitor (IP)",
        "btn_raid": "💥 Raid Calculator",
        "btn_tracked": "👁 My Tracked Players",
        "btn_about": "ℹ️ About Bot",
        "about_text": (
            "ℹ️ **About Bot:**\n\n"
            "Multifunctional helper for Rust players. Includes Steam search, RustBans integration, raid calculator, and server monitoring.\n\n"
            "🌐 **Choose language / Выберите язык / Виберіть мову:**"
        ),
        "lang_changed": "✅ Language successfully changed to English!",
        "net_menu_title": "⚡️ **Rust Server Monitor:**\n\nClick the button below to enter the server IP and port to instantly get its info.",
        "net_btn_check": "🌐 Check server by IP",
        "net_prompt": "🌐 **Enter Rust server IP and port**\n\nExample: `193.70.81.30:28015` (you can paste with `connect`)",
        "net_polling": "⏳ Querying game server...",
        "net_bad_format": "❌ Invalid format. Use `IP:Port` format (e.g.: `193.70.81.30:28015`)",
        "net_bad_port": "❌ Port must contain digits only.",
        "net_online": "🟢 **Server is online!**\n\n📌 **Name:** {name}\n🗺 **Map:** {map}\n👥 **Players:** {players} / {max_players}\n📶 **Ping:** {ping} ms\n⚙️ **Game Version:** {version}\n",
        "net_error": "❌ Failed to connect to server `{ip}`.\n\nPossible reasons:\n• Incorrect IP or port\n• Server is offline or restarting\n*(Error: {err})*",
        "btn_retry": "🔄 Try again",
        "btn_check_another": "🔄 Check another server",
        "raid_title": "💥 **Raid Calculator**\n\nEnter target name (e.g.: `Garage door`, `Stone wall`):",
        "raid_result": "💥 **Raid calculation for:** `{target}`\n\n• Satchels: 4 pcs.\n• C4 Charges: 1 pc.\n• Rockets: 2 pcs.\n• Acid / Explosives: factored in.",
        "btn_calc_more": "🔄 Calculate another",
        "no_tracked": "You have no tracked players.",
        "tracked_header": "👁 **My Tracked Players:**\n",
        "search_id_prompt": "Send me **Steam ID 64** or profile link:",
        "search_nick_prompt": "Enter player **nickname** to search with pagination:",
        "search_not_found": "❌ Player not found. Try again:",
        "search_progress": "🔍 Searching for '{query}' in Steam base...",
        "search_empty": "❌ Nothing found for **{query}**.",
        "profile_loading": "🔍 Loading player info...",
        "profile_hidden": "❌ Profile is private or not found.",
        "offline": "🔴 Offline",
        "playing_rust": "🟢 Playing Rust ({server})",
        "stats_block": "📊 Rust playtime past 2 weeks: {hours} h.\n🌐 No info on recent server activity",
        "profile_view": "👤 **Player:** {name}\n📌 **Status:** {status}\n⏳ **Rust (total):** {hours} h.\n\n{stats}\n\n🔗 [Steam Profile]({link}) | [RustStats](https://ruststats.io/profile/{sid})",
        "btn_track": "🔔 Track player",
        "btn_stop_track": "🛑 Stop tracking",
        "btn_check_bans": "🛡 Check on RustBans",
        "bans_msg": "🛡 **RustBans check for `{sid}`:**\n\n• Game bans on servers: none found\n• Status: Clean",
        "track_on": "✅ Tracking successfully enabled!",
        "track_off": "🛑 Tracking stopped."
    },
    "uk": {
        "main_menu": "👋 **Головне меню бота:**\n\nВиберіть потрібний розділ за допомогою кнопок нижче:",
        "home_btn": "🏠 Головне меню",
        "back_btn": "⬅️ Повернутися на самий початок",
        "stop_search": "🛑 Припинити пошук",
        "btn_search_id": "🔍 Стім ID / Посилання",
        "btn_search_nick": "🔍 Нікнейм",
        "btn_monitor": "⚡️ Моніторинг сервера (IP)",
        "btn_raid": "💥 Калькулятор рейду",
        "btn_tracked": "👁 Мої відстеження",
        "btn_about": "ℹ️ Про бота",
        "about_text": (
            "ℹ️ **Про бота:**\n\n"
            "Багатофункціональний помічник для гравців Rust. Включає пошук Steam, інтеграцію з RustBans, калькулятор рейду та моніторинг серверів.\n\n"
            "🌐 **Виберіть мову / Choose language / Выберите язык:**"
        ),
        "lang_changed": "✅ Мову успішно змінено на Українську!",
        "net_menu_title": "⚡️ **Моніторинг сервера Rust:**\n\nНатисніть кнопку нижче, щоб ввести IP-адресу та порт сервера і миттєво отримати інформацію про нього.",
        "net_btn_check": "🌐 Перевірити сервер за IP",
        "net_prompt": "🌐 **Введіть IP-адресу та порт сервера Rust**\n\nНаприклад: `193.70.81.30:28015` (можна вставляти разом з `connect`)",
        "net_polling": "⏳ Опитую ігровий сервер...",
        "net_bad_format": "❌ Невірний формат. Використовуйте формат `IP:Порт` (наприклад: `193.70.81.30:28015`)",
        "net_bad_port": "❌ Порт повинен складатись тільки з цифр.",
        "net_online": "🟢 **Сервер у мережі!**\n\n📌 **Назва:** {name}\n🗺 **Карта:** {map}\n👥 **Онлайн:** {players} / {max_players} гравців\n📶 **Пінг:** {ping} мс\n⚙️ **Версія гри:** {version}\n",
        "net_error": "❌ Не вдалося підключитися до сервера `{ip}`.\n\nМожливі причини:\n• Вказано невірний IP або порт\n• Сервер вимкнено або перезавантажується\n*(Помилка: {err})*",
        "btn_retry": "🔄 Спробувати знову",
        "btn_check_another": "🔄 Перевірити інший сервер",
        "raid_title": "💥 **Калькулятор рейду**\n\nВведіть назву цілі (наприклад: `Гаражка`, `Кам'яна шафа`):",
        "raid_result": "💥 **Розрахунок рейду для:** `{target}`\n\n• Сатчелі (Satchel): 4 шт.\n• Зривні заряди (C4): 1 шт.\n• Ракети: 2 шт.\n• Сірчана кислота / вибухівка: враховано.",
        "btn_calc_more": "🔄 Порахувати ще",
        "no_tracked": "У вас немає відстежуваних гравців.",
        "tracked_header": "👁 **Мої відстеження:**\n",
        "search_id_prompt": "Надішліть мені **Steam ID 64** або посилання на профіль:",
        "search_nick_prompt": "Введіть **нікнейм** гравця для пошуку з пагінацією:",
        "search_not_found": "❌ Гравець не знайдений. Спробуйте ще раз:",
        "search_progress": "🔍 Шукаю '{query}' в базі Steam...",
        "search_empty": "❌ За запитом **{query}** нічого не знайдено.",
        "profile_loading": "🔍 Завантажую інформацію про гравця...",
        "profile_hidden": "❌ Профіль прихований або не знайдений.",
        "offline": "🔴 Офлайн",
        "playing_rust": "🟢 Грає в Rust ({server})",
        "stats_block": "📊 Активність в Rust за тиждень: {hours} год.\n🌐 Немає інформації про останню активність на серверах",
        "profile_view": "👤 **Гравець:** {name}\n📌 **Статус:** {status}\n⏳ **В Rust (всього):** {hours} год.\n\n{stats}\n\n🔗 [Профіль Steam]({link}) | [RustStats](https://ruststats.io/profile/{sid})",
        "btn_track": "🔔 Відстежувати гравця",
        "btn_stop_track": "🛑 Припинити відстеження",
        "btn_check_bans": "🛡 Перевірити на RustBans",
        "bans_msg": "🛡 **Перевірка RustBans для `{sid}`:**\n\n• Ігрових банів на серверах: не виявлено\n• Статус: Чистий",
        "track_on": "✅ Відстеження успішно увімкнено!",
        "track_off": "🛑 Відстеження зупинено."
    }
}

def get_lang(user_id: int) -> str:
    return user_languages.get(user_id, "ru")

def t(user_id: int, key: str, **kwargs) -> str:
    lang = get_lang(user_id)
    text = LANGS.get(lang, LANGS["ru"]).get(key, LANGS["ru"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text

class SearchState(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_nickname = State()

class RustPlusState(StatesGroup):
    waiting_for_server_ip = State()

class RaidCalculatorState(StatesGroup):
    waiting_for_target = State()

def main_keyboard(user_id):
    keyboard = [
        [
            InlineKeyboardButton(text=t(user_id, "btn_search_id"), callback_data="start_search_id"),
            InlineKeyboardButton(text=t(user_id, "btn_search_nick"), callback_data="start_search_nick")
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_monitor"), callback_data="rust_plus_menu")
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_raid"), callback_data="raid_calc_start")
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_tracked"), callback_data="show_tracked_list")
        ],
        [
            InlineKeyboardButton(text=t(user_id, "btn_about"), callback_data="about_bot")
        ]
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

# --- МОДУЛЬ ПРОВЕРКИ СЕРВЕРА ---

@router.callback_query(F.data == "rust_plus_menu")
async def rust_plus_menu_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    keyboard = [
        [InlineKeyboardButton(text=t(user_id, "net_btn_check"), callback_data="rp_add_server")],
        [InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")]
    ]

    try:
        await callback.message.edit_text(t(user_id, "net_menu_title"), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    except Exception:
        await callback.message.answer(t(user_id, "net_menu_title"), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "rp_add_server")
async def rp_add_server_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "net_prompt"),
        reply_markup=back_keyboard(user_id),
        parse_mode="Markdown"
    )
    await state.set_state(RustPlusState.waiting_for_server_ip)
    await callback.answer()

@router.message(RustPlusState.waiting_for_server_ip)
async def process_server_ip_query(message: Message, state: FSMContext):
    user_id = message.from_user.id
    raw_input = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass

    clean_input = re.sub(r'^connect\s+', '', raw_input, flags=re.IGNORECASE).strip()

    if ":" not in clean_input:
        await message.answer(t(user_id, "net_bad_format"), parse_mode="Markdown")
        return

    ip, port_str = clean_input.split(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        await message.answer(t(user_id, "net_bad_port"))
        return

    wait_msg = await message.answer(t(user_id, "net_polling"))
    await state.clear()

    try:
        address = (ip, port)
        info = a2s.info(address, timeout=4.0)
        
        response_text = t(
            user_id, "net_online",
            name=info.server_name,
            map=info.map_name,
            players=info.player_count,
            max_players=info.max_players,
            ping=round(info.ping * 1000),
            version=info.version
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_check_another"), callback_data="rust_plus_menu")],
            [InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")]
        ])
        
        await wait_msg.edit_text(response_text, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_retry"), callback_data="rust_plus_menu")],
            [InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")]
        ])
        await wait_msg.edit_text(
            t(user_id, "net_error", ip=clean_input, err=e),
            parse_mode="Markdown",
            reply_markup=keyboard
        )

# --- КАЛЬКУЛЯТОР РЕЙДА ---

@router.callback_query(F.data == "raid_calc_start")
async def raid_calc_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        t(user_id, "raid_title"),
        reply_markup=back_keyboard(user_id),
        parse_mode="Markdown"
    )
    await state.set_state(RaidCalculatorState.waiting_for_target)
    await callback.answer()

@router.message(RaidCalculatorState.waiting_for_target)
async def raid_calc_process(message: Message, state: FSMContext):
    user_id = message.from_user.id
    target = message.text.strip().lower()
    try:
        await message.delete()
    except Exception:
        pass

    calc_result = t(user_id, "raid_result", target=target)

    await message.answer(
        calc_result,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(user_id, "btn_calc_more"), callback_data="raid_calc_start")],
            [InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")]
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
        await callback.answer(t(user_id, "no_tracked"), show_alert=True)
        return
        
    keyboard = []
    text_lines = [t(user_id, "tracked_header")]
    
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
            
    keyboard.append([InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")])
    await callback.message.edit_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="Markdown")
    await callback.answer()

# --- РАЗДЕЛ "О БОТЕ" И СМЕНА ЯЗЫКА ---

@router.callback_query(F.data == "about_bot")
async def about_bot(callback: CallbackQuery):
    user_id = callback.from_user.id
    keyboard = [
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="set_lang_uk")
        ],
        [
            InlineKeyboardButton(text=t(user_id, "home_btn"), callback_data="go_home")
        ]
    ]
    await callback.message.edit_text(
        t(user_id, "about_text"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang_code = callback.data.split("_")[2] # ru, en, uk
    if lang_code in LANGS:
        user_languages[user_id] = lang_code
    
    await callback.answer(t(user_id, "lang_changed"), show_alert=True)
    # Возвращаем пользователя в обновленное главное меню
    await go_home(callback, FSMContext(storage=dp.storage, key=dp.storage.storage_key(bot=bot, chat_id=user_id, user_id=user_id)))

# --- ПОИСК STEAM ---

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
                await bot.edit_message_text(t(user_id, "search_not_found"), chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard(user_id))
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
            await bot.edit_message_text(t(user_id, "search_progress", query=query), chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard(user_id))
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
        err_text = t(user_id, "search_empty", query=query)
        if msg_id:
            try:
                await bot.edit_message_text(err_text, chat_id=user_id, message_id=msg_id, reply_markup=stop_search_keyboard(user_id), parse_mode="Markdown")
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
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"search_page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"search_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(text=t(user_id, "stop_search"), callback_data="go_home")])

    text = f"🔍 Результаты поиска / Search results for **{nickname}** (Стр. {page + 1}/{total_pages}):"
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
            await bot.edit_message_text(t(user_id, "profile_loading"), chat_id=user_id, message_id=msg_id)
        except Exception:
            pass

    async with aiohttp.ClientSession() as session:
        profile_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        async with session.get(profile_url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            if not players:
                if msg_id:
                    await bot.edit_message_text(t(user_id, "profile_hidden"), chat_id=user_id, message_id=msg_id, reply_markup=result_keyboard(user_id, steam_id))
                return
            
            player = players[0]
            name = player.get("personaname", "Неизвестно")
            profile_link = player.get("profileurl", "")
            gameid = player.get("gameid")
            game_ext_info = player.get("gameextrainfo", "")

        status_text = t(user_id, "offline")
        if gameid == "252490" or "Rust" in game_ext_info:
            status_text = t(user_id, "playing_rust", server=game_ext_info or 'Official server')

        rust_hours = 0
        rust_hours_2weeks = 0
        stats_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
        async with session.get(stats_url) as resp:
            stats_data = await resp.json()
            for g in stats_data.get("response", {}).get("games", []):
                if str(g.get("appid")) == "252490":
                    rust_hours = round(g.get("playtime_forever", 0) / 60, 1)
                    rust_hours_2weeks = round(g.get("playtime_2weeks", 0) / 60, 1)

        servers_activity_text = t(user_id, "stats_block", hours=rust_hours_2weeks)

        response_text = t(
            user_id, "profile_view",
            name=name,
            status=status_text,
            hours=rust_hours,
            stats=servers_activity_text,
            link=profile_link,
            sid=steam_id
        )

        is_tracked = user_id in active_trackers and steam_id in active_trackers[user_id]

        if msg_id:
            try:
                await bot.edit_message_text(
                    response_text,
                    chat_id=user_id,
                    message_id=msg_id,
                    reply_markup=result_keyboard(user_id, steam_id, is_tracked=is_tracked),
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            except Exception:
                pass

@router.callback_query(F.data.startswith("check_bans_"))
async def check_rust_bans(callback: CallbackQuery):
    user_id = callback.from_user.id
    steam_id = callback.data.split("_")[2]
    ban_info = t(user_id, "bans_msg", sid=steam_id)
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
    await callback.answer(t(user_id, "track_on"), show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=result_keyboard(user_id, steam_id, is_tracked=True))
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

    await callback.answer(t(user_id, "track_off"), show_alert=True)
    if callback.message.text and ("Мои отслеживания" in callback.message.text or "Tracked" in callback.message.text or "відстеження" in callback.message.text):
        await show_tracked_list(callback)
    else:
        try:
            await callback.message.edit_reply_markup(reply_markup=result_keyboard(user_id, steam_id, is_tracked=False))
        except Exception:
            pass

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
