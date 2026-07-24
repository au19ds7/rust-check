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

class SearchState(StatesGroup):
    waiting_for_steam_id = State()

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Найти игрока Rust", callback_data="start_search")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about_bot")]
    ])

def back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

def result_keyboard(steam_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Отслеживать игрока", callback_data=f"track_{steam_id}")],
        [InlineKeyboardButton(text="⬅️ Вернуться на самое начало", callback_data="go_home")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я бот для поиска и отслеживания игроков **Rust** по Steam ID или кастомной ссылке.\n\n"
        "Нажми кнопку ниже, чтобы начать поиск:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(
            "Главное меню. Выберите действие:",
            reply_markup=main_keyboard()
        )
    except Exception:
        await callback.message.answer(
            "Главное меню. Выберите действие:",
            reply_markup=main_keyboard()
        )
    await callback.answer()

@router.callback_query(F.data == "about_bot")
async def about_bot(callback: CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ **О боте:**\n\n"
        "Этот бот создан для проверки игроков в **Rust** по Steam ID, кастомным ссылкам, статуса и даты создания профиля.\n\n"
        "👨‍💻 **Создатель:** Telegram: @allfytiq",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "start_search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Отправьте мне **Steam ID** (например, `76561198000000000`) или **кастомный ник/ссылку** (например, `numberonerust`):",
        reply_markup=back_keyboard(),
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
                reply_markup=back_keyboard()
            )
            await state.clear()
            return

        # 1. Профиль игрока (включая дату создания аккаунта timecreated)
        profile_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        async with session.get(profile_url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            
            if not players:
                await msg.edit_text("❌ Профиль игрока скрыт или не найден.", reply_markup=back_keyboard())
                await state.clear()
                return
            
            player = players[0]
            name = player.get("personaname", "Неизвестно")
            profile_link = player.get("profileurl", "")
            gameid = player.get("gameid")
            game_ext_info = player.get("gameextrainfo", "")
            
            # Дата создания аккаунта
            time_created = player.get("timecreated")
            if time_created:
                import datetime
                reg_date = datetime.datetime.utcfromtimestamp(time_created).strftime('%Y-%m-%d %H:%M:%S (UTC)')
            else:
                reg_date = "Скрыта или неизвестна"

        status_text = "🔴 Оффлайн / Не в игре"
        if gameid == "252490" or "Rust" in game_ext_info:
            status_text = "🟢 Играет в Rust прямо сейчас!"
        elif gameid:
            status_text = f"🎮 Играет в другую игру: {game_ext_info}"

        # 2. Общая статистика Rust (сколько наиграл)
        rust_hours = 0
        stats_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
        async with session.get(stats_url) as resp:
            stats_data = await resp.json()
            owned_games = stats_data.get("response", {}).get("games", [])
            for g in owned_games:
                if str(g.get("appid")) == "252490":
                    rust_hours = round(g.get("playtime_forever", 0) / 60, 1)

        # 3. Активность в Rust за последние 2 недели
        rust_sessions = []
        recent_url = f"https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id}&format=json"
        async with session.get(recent_url) as resp:
            recent_data = await resp.json()
            games = recent_data.get("response", {}).get("games", [])
            for g in games:
                if str(g.get("appid")) == "252490":
                    mins_2weeks = g.get("playtime_2weeks", 0)
                    hours_2weeks = round(mins_2weeks / 60, 1)
                    rust_sessions.append(f"• Официальный клиент Rust (за 2 недели) — {hours_2weeks} ч.")

        rust_servers_text = "\n".join(rust_sessions[:3]) if rust_sessions else "⚠️ Нет данных о недавних сессиях в Rust."

        # Ссылка на ruststats.io
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

        await msg.delete()
        await message.answer(
            response_text,
            reply_markup=result_keyboard(steam_id),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    await state.clear()

@router.callback_query(F.data.startswith("track_"))
async def track_player(callback: CallbackQuery):
    steam_id = callback.data.split("_")[1]
    await callback.answer("✅ Вы подписались на уведомления об игроке!", show_alert=True)
    
    async def background_tracker():
        async with aiohttp.ClientSession() as session:
            last_status = None
            for _ in range(30):
                await asyncio.sleep(60)
                url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
                async with session.get(url) as resp:
                    data = await resp.json()
                    players = data.get("response", {}).get("players", [])
                    if players:
                        gameid = players[0].get("gameid")
                        is_in_rust = (gameid == "252490")
                        
                        if is_in_rust != last_status:
                            last_status = is_in_rust
                            if is_in_rust:
                                await bot.send_message(callback.from_user.id, f"🚨 ВНИМАНИЕ! Игрок (ID: `{steam_id}`) зашел в **Rust**!", parse_mode="Markdown")
                            else:
                                await bot.send_message(callback.from_user.id, f"💤 Игрок (ID: `{steam_id}`) вышел из игры **Rust**.", parse_mode="Markdown")

    asyncio.create_task(background_tracker())

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
