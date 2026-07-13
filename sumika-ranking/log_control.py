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

        try:

            await save_message_to_db(message)

        except Exception as e:
            print("DB Worker Error:", e)

        finally:
            bot.db_queue.task_done()

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
