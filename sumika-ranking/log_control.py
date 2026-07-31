import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import time
from pathlib import Path
from config import FOOTER,DB_PATH
import asyncio
import sqlite3
from datetime import datetime, timezone, timedelta
from discord.errors import HTTPException

JST = timezone(timedelta(hours=9))

print("RANKING DB PATH:", DB_PATH)
print("EXISTS:", os.path.exists(DB_PATH))
EXCLUDED_CHANNELS = [1399620581766463639]
# ===============================
# 💾 メッセージ保存（同期本体）
# ===============================

def _save_message_to_db_sync(
    message_id: int,
    author: str,
    author_id: int,
    content: str,
    channel_id: int,
    created_at: str,
):

    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO messages
        (id, author, author_id, content, channel_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        message_id,
        author,
        author_id,
        content,
        channel_id,
        created_at
    ))
    c.execute("SELECT COUNT(*) FROM messages")

    conn.commit()
    conn.close()


# ===============================
# 💾 メッセージ保存（非同期ラッパー）
# ===============================

async def save_message_to_db(message: discord.Message):
    try:
        if message.author.bot:
            return

        if message.channel.id in EXCLUDED_CHANNELS:
            return

        has_content = bool(message.content and message.content.strip())
        has_attachments = bool(message.attachments)
        has_stickers = bool(message.stickers)

        if not (has_content or has_attachments or has_stickers):
            return

        # JST正規化
        if message.created_at:
            created_at = (
                message.created_at
                .astimezone(JST)
                .strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            created_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")

        # 🚀 ここが最重要
        await asyncio.to_thread(
            _save_message_to_db_sync,
            message.id,
            str(message.author),
            message.author.id,
            message.content or "",
            message.channel.id,
            created_at
        )

    except Exception as e:
        print(f"❌ save_message_to_db error: {e}")


async def api_worker(bot):
    while True:
        coro = await bot.api_queue.get()

        try:
            await coro

        except discord.HTTPException as e:

            if e.status == 429:

                retry = getattr(e, "retry_after", 10)

                print(f"🚨 429検知 {retry:.2f}秒待機")

                await asyncio.sleep(retry)

            else:
                print(e)
                await asyncio.sleep(5)

        except Exception as e:
            print("API Worker Error:", e)

        finally:

            bot.api_queue.task_done()

            # Discordへ少し余裕を与える
            await asyncio.sleep(0.3)


async def db_worker(bot):

    while True:

        message = await bot.db_queue.get()
        print("DB Worker:", message.id)

        try:

            await save_message_to_db(message)
            print("SAVE:", message.id)

        except Exception as e:
            print("DB Worker Error:", e)

        finally:
            bot.db_queue.task_done()


async def history_worker(bot):
    while True:
        func, future = await bot.history_queue.get()
        
        try:
            result = await func()
            future.set_result(result)
            
        except discord.HTTPException as e:
            if e.status == 429:
                retry = getattr(e, "retry_after", 10)
                print(f"429(HISTORY) {retry:.2f}s")
                await asyncio.sleep(retry)
                future.set_exception(e)
            else:
                future.set_exception(e)
                
        except Exception as e:
            future.set_exception(e)
            
        finally:
            bot.history_queue.task_done()
            await asyncio.sleep(0.25)



async def api_call(bot, func):
    """
    Discord APIをapi_queue経由で実行する
    戻り値が必要なAPIにも対応
    """
    future = asyncio.get_running_loop().create_future()

    async def runner():
        try:
            result = await func()
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)

    await bot.api_queue.put(runner())

    return await future


async def fetch_history(
    bot,
    channel,
    limit=None,
    oldest_first=True,
):
    future = asyncio.get_running_loop().create_future()
    async def runner():
        return [
            message
            async for message in channel.history(
                limit=limit,
                oldest_first=oldest_first,
            )
        ]

    await bot.history_queue.put(
        (runner, future)
    )

    return await future


async def fetch_archived_threads(bot, forum):
    future = asyncio.get_running_loop().create_future()
    async def runner():
        return [
            thread
            async for thread in forum.archived_threads(limit=None)
        ]

    await bot.history_queue.put(
        (runner, future)
    )
    return await future
