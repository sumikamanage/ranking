import asyncio
import os

from discord.ext import commands

from bot import bot
import message_count
from message_count import full_scan, DB_PATH
from config import GUILD_ID


# ===============================
# 初回フルスキャン
# ===============================
@bot.tree.command(name="first_scan")
@commands.has_permissions(administrator=True)
async def first_scan(ctx):
    """
    DBを初期化してサーバー全体をスキャン
    """

    guild = bot.get_guild(GUILD_ID)

    if guild is None:
        return await ctx.send("❌ サーバーが取得できませんでした。")

    if message_count.is_updating:
        return await ctx.send("⚠️ 現在、更新処理が実行中です。")

    if message_count.is_scanning:
        return await ctx.send("⚠️ すでにスキャン実行中です。")

    await ctx.send("🔍 サーバー全体のスキャンを開始します…")

    asyncio.create_task(
        full_scan(bot, guild)
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
