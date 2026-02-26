import discord
import asyncio
import os
from discord.ext import commands
from bot import bot
import message_count
from message_count import full_scan, log_worker
from config import GUILD_ID,DB_PATH
#カウントコマンド
from discord.ext import commands
from collections import Counter

@bot.command("first_scan")
@commands.has_permissions(administrator=True)
async def first_scan(ctx):
    # --- DBリセット＆初回スキャン（同期実行） ---
    guild = bot.get_guild(GUILD_ID)
    db_path = DB_PATH
    if os.path.exists(db_path):
        os.remove(db_path)
        await channel.send("🧹 既存のDB削除完了")
    #フルスキャンを開始
    ctx = bot.get_channel(1276087091280871546)
    if message_count.is_updating:
        return await ctx.send("⚠️ 現在、更新処理が実行中です。スキャンできません。")
    if message_count.is_scanning:
        return await ctx.send("⚠️ すでにスキャン実行中です。")
    await ctx.send("🔍 サーバー全体のスキャンを開始します…")
    asyncio.create_task(full_scan(bot,guild))


    #asyncio.create_task(log_worker(bot, 1276087091280871546))



# ---- アップデートメッセージカウント ----
@bot.command(name="update_messages")
@commands.has_permissions(administrator=True)
async def update_messages(ctx):
    guild = bot.get_guild(GUILD_ID)
    channel = bot.get_channel(1276087091280871546)

    """増分更新を開始"""
    if message_count.is_scanning:
        return await ctx.send("⚠️ 現在スキャン中のため更新できません。")
    if message_count.is_updating:
        return await ctx.send("⚠️ すでに更新処理が実行中です。")
    await ctx.send("🔄 メッセージの増分更新を開始します…")
    asyncio.create_task(message_count.incremental_update(bot,guild))
    await ctx.send("✅メッセージの増分更新が完了しました！")
