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
        [InlineKeyboardButton(text="🔍 Поиск по SteamID", callback_data="search_steam")]
    ])
    await message.answer("👾 <b>Rust Player Tracker</b>\n\nВыбери способ поиска:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "search_nick")
async def ask_nick(callback: types.CallbackQuery):
    await callback.message.answer("Напиши никнейм игрока:")
    await callback.answer()

@dp.callback_query(F.data == "search_steam")
async def ask_steam(callback: types.CallbackQuery):
    await callback.message.answer("Напиши SteamID64:")
    await callback.answer()

@dp.message()
async def handle_search(message: types.Message):
    text = message.text.strip()
    if not text or text.startswith('/'):
        return

    await message.answer("🔎 Ищу...")

    if text.isdigit() and len(text) > 15:
        steam_info = await get_steam_info(text)
        bm_data = await search_battlemetrics(steamid=text)
    else:
        steam_info = None
        bm_data = await search_battlemetrics(player_name=text)

    response = "📊 <b>Результат:</b>\n\n"

    if steam_info:
        response += f"👤 Ник: <b>{steam_info.get('personaname', 'Неизвестно')}</b>\n"
        status = "🟢 Онлайн" if steam_info.get('personastate') == 1 else "🔴 Оффлайн"
        response += f"Статус: {status}\n"
        if 'gameextrainfo' in steam_info:
            response += f"🎮 Игра: <b>{steam_info['gameextrainfo']}</b>\n"

    if bm_data and bm_data.get("data"):
        attr = bm_data["data"][0].get("attributes", {})
        response += f"\n🖥️ Сервер: <b>{attr.get('server', 'Неизвестно')}</b>"

    await message.answer(response, parse_mode="HTML")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
