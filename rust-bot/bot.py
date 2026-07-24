import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

STEAM_API_KEY = os.getenv("STEAM_API_KEY")

async def get_steam_info(steamid: str):
    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steamid}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            players = data.get("response", {}).get("players", [])
            return players[0] if players else None

async def search_battlemetrics(player_name: str = None, steamid: str = None):
    url = "https://api.battlemetrics.com/players"
    params = {"page[size]": 10, "filter[game]": "rust"}
    if player_name:
        params["filter[search]"] = player_name
    if steamid:
        params["filter[steamID]"] = steamid

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
    return None

@dp.message(Command("start"))
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск по нику", callback_data="search_nick")],
        [InlineKeyboardButton(text="🔍 Поиск по SteamID64", callback_data="search_steam")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
    ])
    await message.answer(
        "🌲 <b>Rust Player Tracker</b>\n\n"
        "Отслеживаем игроков в Rust в реальном времени\n"
        "Steam + BattleMetrics\n\n"
        "Выбери действие:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "search_nick")
async def ask_nick(callback: types.CallbackQuery):
    await callback.message.edit_text("✍️ Введи **никнейм** игрока:")
    await callback.answer()

@dp.callback_query(F.data == "search_steam")
async def ask_steam(callback: types.CallbackQuery):
    await callback.message.edit_text("✍️ Введи **SteamID64** игрока:\n\nПример: `76561198000000000`")
    await callback.answer()

@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ <b>О боте</b>\n\n"
        "• Работает через Steam API и BattleMetrics\n"
        "• Показывает онлайн статус и текущий сервер\n"
        "• Быстрый поиск по нику или ID\n\n"
        "Разработано с ❤️ для Rust сообщества",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message()
async def handle_search(message: types.Message):
    text = message.text.strip()
    if not text or text.startswith('/'):
        return

    wait_msg = await message.answer("🔎 <b>Ищу игрока...</b>", parse_mode="HTML")

    if text.isdigit() and len(text) > 15:
        steam_info = await get_steam_info(text)
        bm_data = await search_battlemetrics(steamid=text)
    else:
        steam_info = None
        bm_data = await search_battlemetrics(player_name=text)

    response = "📊 <b>Результат поиска</b>\n\n"

    if steam_info:
        name = steam_info.get("personaname", "Неизвестно")
        status = "🟢 **Онлайн**" if steam_info.get("personastate") == 1 else "🔴 Оффлайн"
        response += f"👤 Ник: <b>{name}</b>\n"
        response += f"Статус: {status}\n"
        
        if "gameextrainfo" in steam_info:
            game = steam_info["gameextrainfo"]
            response += f"🎮 Играет в: <b>{game}</b>\n"

    if bm_data and bm_data.get("data"):
        player = bm_data["data"][0]
        attr = player.get("attributes", {})
        response += f"\n🖥️ Сервер: <b>{attr.get('server', 'Неизвестно')}</b>\n"
        response += f"⏱️ В игре: {attr.get('playtime', '—')}\n"

    if not steam_info and not (bm_data and bm_data.get("data")):
        response += "❌ Игрок не найден или профиль закрыт."

    await wait_msg.edit_text(response, parse_mode="HTML")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
