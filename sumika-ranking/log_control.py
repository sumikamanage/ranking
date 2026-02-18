import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import time
from pathlib import Path
from config import FOOTER 
import asyncio
from bot import bot


async def api_worker(bot):
    while True:
        coro = await bot.api_queue.get()
        try:
            await coro
            await asyncio.sleep(0.9)  # 少し余裕を持たせる
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 5)
                print(f"⏳ 429検知: {retry_after}s 待機")
                await asyncio.sleep(retry_after)
                await bot.api_queue.put(coro)  # ★再投入
            else:
                await asyncio.sleep(0.3)
                await bot.api_queue.put(coro)
        finally:
            bot.api_queue.task_done()




async def db_worker():
    while True:
        coro = await bot.db_queue.get()
        try:
            await coro
            await asyncio.sleep(0.3)  # 少し余裕を持たせる
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 5)
                print(f"⏳ 429検知: {retry_after}s 待機")
                await asyncio.sleep(retry_after)
                await bot.db_queue.put(coro)  # ★再投入
            else:
                raise
        finally:
            bot.db_queue.task_done()
