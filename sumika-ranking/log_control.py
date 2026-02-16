import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import time
from pathlib import Path
from config import FOOTER 
import asyncio

api_queue = asyncio.Queue()

async def api_worker():
    while True:
        coro = await api_queue.get()
        try:
            await coro
            await asyncio.sleep(0.9)  # 少し余裕を持たせる
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 5)
                print(f"⏳ 429検知: {retry_after}s 待機")
                await asyncio.sleep(retry_after)
                await api_queue.put(coro)  # ★再投入
            else:
                await asyncio.sleep(0.3)
                await api_queue.put(coro)
        finally:
            api_queue.task_done()

db_queue = asyncio.Queue()


async def db_worker():
    while True:
        coro = await db_queue.get()
        try:
            await coro
            await asyncio.sleep(0.3)  # 少し余裕を持たせる
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 5)
                print(f"⏳ 429検知: {retry_after}s 待機")
                await asyncio.sleep(retry_after)
                await db_queue.put(coro)  # ★再投入
            else:
                raise
        finally:
            db_queue.task_done()
