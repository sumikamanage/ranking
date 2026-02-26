import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import time
from pathlib import Path
from config import FOOTER,DB_PATH
import asyncio


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

api_queue = asyncio.Queue()

async def api_worker():
    while True:
        coro = await api_queue.get()
        try:
            await coro
            await asyncio.sleep(0.9)  # 少し余裕を持たせる
        except discord.HTTPException as e:
            if e.status == 429:
                if e.status == 429:
                    print("🚨 429検知（再投入しない）")
                    await asyncio.sleep(10)
            else:
                await asyncio.sleep(10)
        finally:
            api_queue.task_done()

db_queue = asyncio.Queue()


async def db_worker():
    while True:
        message = await db_queue.get()
        try:
            await save_message_to_db(message)
        except Exception as e:
            print(f"DB worker error: {e}")
        finally:
            db_queue.task_done()


