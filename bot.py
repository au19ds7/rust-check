import os
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Хранилище активных задач отслеживания: {user_id: {steam_id: task}}
active_trackers = {}
# Список отслеживаемых игроков для меню: {user_id: {steam_id: player_name}}
tracked_players_list = {}

class SearchState(StatesGroup):
    waiting_for_steam_id = State()

def main_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton(text="🔍 Найти игрока Rust", callback_data="start_search")]
    ]
    
    # Добавляем список отслеживаемых игроков в главное меню, если они есть
    if user_id in tracked_players_list and tracked_players_list[user_id]:
        keyboard.append([InlineKeyboardButton(text="📋 Список отслеживаемых игроков", callback_data="show_tracked_list")])
        
    keyboard.append([InlineKeyboardButton(text="ℹ️ О боте", callback_data="about_bot")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def back_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

def result_keyboard(steam_id, is_tracking=False):
    if is_tracking:
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
    await message.answer(
        "Привет! Я бот для поиска и отслеживания игроков **Rust** по Steam ID или кастомной ссылке.\n\n"
        "Нажми кнопку ниже, чтобы начать поиск:",
        reply_markup=main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(
            "Главное меню. Выберите действие:",
            reply_markup=main_keyboard(callback.from_user.id)
        )
    except Exception:
        await callback.message.answer(
            "Главное меню. Выберите действие:",
            reply_markup=main_keyboard(callback.from_user.id)
        )
    await callback.answer()

@router.callback_query(F.data == "show_tracked_list")
async def show_tracked_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    players = tracked_players_list.get(user_id, {})
    
    if not players:
        await callback.answer("У вас нет отслеживаемых игроков.", show_alert=True)
        return
        
    text = "📋 **Список отслеживаемых игроков:**\n\n"
    keyboard = []
    for s_id, name in players.items():
        text += f"• {name} (ID: `{s_id}`)\n"
        keyboard.append([InlineKeyboardButton(text=f"❌ Удалить {name}", callback_data=f"stop_track_{s_id}")])
        
    keyboard.append([InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "about_bot")
async def about_bot(callback: CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ **О боте:**\n\n"
        "Этот бот создан для проверки игроков в **Rust** по Steam ID, кастомным ссылкам, статуса и отслеживания в реальном времени.\n\n"
        "👨‍💻 **Создатель:** Telegram: @allfytiq",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "start_search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Отправьте мне **Steam ID** (например, `76561198000000000`) или **кастомный ник/ссылку** (например, `numberonerust`):",
        reply_markup=back_keyboard(callback.from_user.id),
        parse_mode="Markdown"
    )
    await state.set_state(SearchState.waiting_for_steam_id)
    await callback.answer()

@router.message(SearchState.waiting_for_steam_id)
async def process_steam_id(message: Message, state: FSMContext):
    user_input = message.text.strip()
    
    if "steamcommunity.com/id/" in user_input:
        user_input = user_input.rstrip("/").split("/")[-1]
    elif "steamcommunity.com/profiles/" in user_input:
        user_input = user_input.rstrip("/").split("/")[-1]

    msg = await message.answer("🔍 Ищу информацию об игроке в Steam...")

    async with aiohttp.ClientSession() as session:
        steam_id = None

        if user_input.isdigit() and len(user_input) == 17:
            steam_id = user_input
        else:
            vanity_url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={user_input}"
            async with session.get(vanity_url) as resp:
                vanity_data = await resp.json()
                response_block = vanity_data.get("response", {})
                if response_block.get("success") == 1:
                    steam_id = response_block.get("steamid")

        if not steam_id:
            await msg.edit_text(
                "❌ Игрок не найден. Проверьте правильность введенного Steam ID или кастомного имени:",
                reply_markup=back_keyboard(message.from_user.id)
            )
            await state.clear()
            return

        profile_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        async with session.get(profile_url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            
            if not players:
                await msg.edit_text("❌ Профиль игрока скрыт или не найден.", reply_markup=back_keyboard(message.from_user.id))
                await state.clear()
                return
            
            player = players[0]
            name = player.get("personaname", "Неизвестно")
            profile_link = player.get("profileurl", "")
            gameid = player.get("gameid")
            game_ext_info = player.get("gameextrainfo", "")
            
            time_created = player.get("timecreated")
            if time_created:
                import datetime
                reg_date = datetime.datetime.utcfromtimestamp(time_created).strftime('%Y-%m-%d %H:%M:%S (UTC)')
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

        response_text = (
            f"👤 **Игрок:** {name}\n"
            f"📌 **Статус:** {status_text}\n"
            f"📅 **Дата создания аккаунта:** {reg_date}\n"
            f"⏳ **Всего наиграно в Rust:** {rust_hours} ч.\n\n"
            f"🖥 **Последняя активность в Rust:**\n"
            f"{rust_servers_text}\n\n"
            f"🔗 **Ссылки:**\n"
            f"• [Профиль Steam]({profile_link})\n"
            f"• [RustStats.io]({ruststats_link})"
        )

        user_id = message.from_user.id
        is_tracked = user_id in active_trackers and steam_id in active_trackers[user_id]

        await msg.delete()
        await message.answer(
            response_text,
            reply_markup=result_keyboard(steam_id, is_tracking=is_tracked),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    await state.clear()

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

    # Получим ник игрока для красивого списка
    player_name = steam_id
    async with aiohttp.ClientSession() as session:
        url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        async with session.get(url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            if players:
                player_name = players.get("personaname", steam_id)

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
                            p = players
                            p_name = p.get("personaname", "Игрок")
                            gameid = p.get("gameid")
                            game_ext_info = p.get("gameextrainfo", "")
                            
                            is_in_rust = (gameid == "252490" or "Rust" in game_ext_info)
                            current_server = game_ext_info if game_ext_info else "Официальный сервер Rust"
                            
                            if is_in_rust and not last_in_rust:
                                last_in_rust = True
                                last_server = current_server
                                await bot.send_message(user_id, f"🚨 Игрок **{p_name}** зашел на сервер: `{current_server}`!", parse_mode="Markdown")
                            elif not is_in_rust and last_in_rust:
                                last_in_rust = False
                                await bot.send_message(user_id, f"💤 Игрок **{p_name}** вышел из игры Rust (сервер: `{last_server}`)", parse_mode="Markdown")
                except Exception:
                    pass
                await asyncio.sleep(60)

    task = asyncio.create_task(background_tracker())
    active_trackers[user_id][steam_id] = task

    await callback.answer("✅ Отслеживание успешно включено!", show_alert=True)
    
    # Обновляем клавиатуру на сообщение
    try:
        await callback.message.edit_reply_markup(reply_markup=result_keyboard(steam_id, is_tracking=True))
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
    
    # Если это было из меню списков, возвращаем в главное меню или обновляем
    if callback.message.text and "Список отслеживаемых" in callback.message.text:
        await go_home(callback, None)
    else:
        try:
            await callback.message.edit_reply_markup(reply_markup=result_keyboard(steam_id, is_tracking=False))
        except Exception:
            pass

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
