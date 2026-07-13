import asyncio
import os

from discord.ext import commands

from bot import bot
import message_count
from message_count import full_scan, DB_PATH
from config import GUILD_ID

# ===============================
# タスク管理
# ===============================
scan_task = None
update_task = None

# ===============================
# 初回フルスキャン
# ===============================
@bot.command(name="first_scan")
@commands.has_permissions(administrator=True)
async def first_scan(ctx):
    """
    DBを初期化してサーバー全体をスキャン
    """

    global scan_task

    guild = bot.get_guild(GUILD_ID)

    if guild is None:
        return await ctx.send("❌ サーバーが取得できませんでした。")

    if message_count.is_updating:
        return await ctx.send("⚠️ 現在、更新処理が実行中です。")

    if message_count.is_scanning:
        return await ctx.send("⚠️ すでにスキャン実行中です。")

    if scan_task is not None and not scan_task.done():
        return await ctx.send("⚠️ スキャンタスクがすでに存在します。")

    await ctx.send("🔍 サーバー全体のスキャンを開始します…")

    scan_task = asyncio.create_task(
        full_scan(bot, guild)
    )


# ===============================
# フルスキャン停止
# ===============================
@bot.command(name="stop_scan")
@commands.has_permissions(administrator=True)
async def stop_scan(ctx):
    """
    実行中のフルスキャンを停止
    """

    global scan_task

    if scan_task is None:
        return await ctx.send(
            "⚠️ 実行中のスキャンはありません。"
        )

    if scan_task.done():
        scan_task = None
        return await ctx.send(
            "⚠️ スキャンはすでに終了しています。"
        )

    scan_task.cancel()

    try:
        await scan_task

    except asyncio.CancelledError:
        pass

    scan_task = None

    await ctx.send(
        "🛑 フルスキャンを停止しました。"
    )


# ===============================
# 増分更新
# ===============================
@bot.tree.command(name="update_messages")
@commands.has_permissions(administrator=True)
async def update_messages(ctx):

    guild = bot.get_guild(GUILD_ID)

    if guild is None:
        return await ctx.send("❌ サーバーが取得できませんでした。")

    if message_count.is_scanning:
        return await ctx.send("⚠️ 現在スキャン中のため更新できません。")

    if message_count.is_updating:
        return await ctx.send("⚠️ すでに更新処理が実行中です。")

    await ctx.send("🔄 メッセージの増分更新を開始します…")

    asyncio.create_task(
        message_count.incremental_update(
            bot,
            guild
        )
    )
