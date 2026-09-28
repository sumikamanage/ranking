import discord
import asyncio

from discord import app_commands
from discord.ext import commands

from bot import bot
import stats_store
import message_count
from config import GUILD_ID


def _start_catch_up(guild):
    """追いつき処理を開始(bot.scan_task に保持して !stop_scan で止められるようにする)"""
    bot.scan_task = asyncio.create_task(
        stats_store.catch_up_all(
            bot, guild, log=lambda t: message_count.send_log(bot, t)
        )
    )


# ===============================
# 初回フルスキャン(集計を消して、全履歴から作り直す)
# ===============================
@bot.tree.command(
    name="first_scan",
    description="DBを初期化してサーバー全体をスキャンします"
)
@app_commands.checks.has_permissions(administrator=True)
async def first_scan(interaction: discord.Interaction):

    guild = bot.get_guild(GUILD_ID)

    if guild is None:
        return await interaction.response.send_message(
            "❌ サーバーが取得できませんでした。"
        )

    if stats_store.is_running():
        return await interaction.response.send_message(
            "⚠️ すでにスキャン(更新)実行中です。"
        )

    await interaction.response.send_message(
        "🔍 集計をリセットして、サーバー全体を最初からスキャンします…"
    )

    await stats_store.reset_all()
    _start_catch_up(guild)


# ===============================
# スキャン停止(起動時の追いつきも止められる)
# ===============================
@bot.command(name="stop_scan")
@commands.has_permissions(administrator=True)
async def stop_scan(ctx):

    task = bot.scan_task

    if task is None or task.done():
        bot.scan_task = None
        return await ctx.send("⚠️ 実行中のスキャンはありません。")

    await ctx.send("🛑 スキャン停止要求を送信しました...")

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        bot.scan_task = None

    await ctx.send("✅ スキャンを停止しました。(進捗は保存済みで、次回は続きから再開します)")


# ===============================
# 差分更新(保存済み位置以降だけ取得)
# ===============================
@bot.tree.command(
    name="update_messages",
    description="メッセージの増分更新を実行します"
)
@app_commands.checks.has_permissions(administrator=True)
async def update_messages(interaction: discord.Interaction):

    guild = bot.get_guild(GUILD_ID)

    if guild is None:
        return await interaction.response.send_message(
            "❌ サーバーが取得できませんでした。"
        )

    if stats_store.is_running():
        return await interaction.response.send_message(
            "⚠️ すでにスキャン(更新)実行中です。"
        )

    await interaction.response.send_message(
        "🔄 メッセージの増分更新を開始します…"
    )

    _start_catch_up(guild)


# ===============================
# スラッシュコマンドの同期(コマンドを追加・変更したときだけ実行)
# ===============================
@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync(ctx):
    synced = await bot.tree.sync()
    await ctx.send(f"✅ {len(synced)} 件のコマンドを同期しました。")
