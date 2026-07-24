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

# Клавиатуры
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
        "Привет! Я бот для поиска и отслеживания игроков **Rust** по Steam ID.\n\n"
        "Нажми кнопку ниже, чтобы начать поиск:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    # Используем edit_text или send_message в зависимости от того, откуда пришел вызов
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
        "Этот бот создан для проверки игроков в **Rust** по их Steam ID, просмотра статуса и ссылок.\n\n"
        "👨‍💻 **Создатель:** Telegram: @allfytiq",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "start_search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Отправьте мне **Steam ID** (в формате 64-bit, например: `76561198000000000`) игрока:",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(SearchState.waiting_for_steam_id)
    await callback.answer()

@router.message(SearchState.waiting_for_steam_id)
async def process_steam_id(message: Message, state: FSMContext):
    steam_id = message.text.strip()
    
    if not steam_id.isdigit() or len(steam_id) != 17:
        await message.answer(
            "❌ Неверный формат Steam ID. ID должен состоять из 17 цифр.\nПопробуйте еще раз или нажмите кнопку возврата:",
            reply_markup=back_keyboard()
        )
        return

    msg = await message.answer("🔍 Ищу информацию об игроке в Steam...")

    async with aiohttp.ClientSession() as session:
        profile_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id}"
        async with session.get(profile_url) as resp:
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            
            if not players:
                await msg.edit_text("❌ Игрок с таким Steam ID не найден.", reply_markup=back_keyboard())
                await state.clear()
                return
            
            player = players[0]
            name = player.get("personaname", "Неизвестно")
            profile_link = player.get("profileurl", "")
            gameid = player.get("gameid")
            game_ext_info = player.get("gameextrainfo", "")

        # Статус игрока
        status_text = "🔴 Оффлайн / Не в игре"
        if gameid == "252490" or "Rust" in game_ext_info:
            status_text = "🟢 Играет в Rust прямо сейчас!"
        elif gameid:
            status_text = f"🎮 Играет в другую игру: {game_ext_info}"

        steamrep_link = f"https://steamrep.com/profiles/{steam_id}"
        faceit_link = f"https://www.faceit.com/en/players/{name}"

        response_text = (
            f"👤 **Игрок:** {name}\n"
            f"📌 **Статус:** {status_text}\n\n"
            f"🔗 **Ссылки на площадки:**\n"
            f"• [Профиль Steam]({profile_link})\n"
            f"• [SteamRep (проверка банов)]({steamrep_link})\n"
            f"• [Faceit]({faceit_link})"
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
            for _ in range(30):  # Проверяем статус в течение некоторого времени
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
