import discord
import asyncio
from discord.ext import commands
from discord import app_commands

from datetime import datetime

from message_count import (
    get_message_ranking_slice,
    get_message_length_ranking_slice,
    create_member_rank_embed,
    create_member_length_rank_embed,
)

from config import FOOTER

from bot import bot

footer=FOOTER
# ===============================
# 共通ランキング表示
# ===============================

async def _send_ranking(
    interaction,
    rows,
    start,
    title,
    unit,
    color=discord.Color.blue(),
):
    if not rows:
        return await interaction.response.send_message("ランキングが見つかりませんでした。")

    lines = []

    for i, (author_id, value) in enumerate(rows, start=start):
        lines.append(
            f"🏅{i}位: <@{author_id}> — {value:,}{unit}"
        )

    embed = discord.Embed(
        title=title,
        description="\n".join(lines),
        color=color,
    )

    embed.set_footer(text=footer)

    await interaction.response.send_message(embed=embed)


# ===============================
# メッセージ数ランキング
# ranking [開始順位] [表示数]
# ===============================
@bot.tree.command(name="ranking")
async def ranking(
    interaction: discord.Interaction,
    start: int = 1,
    length: int = 10,
):

    if start < 1:
        return await interaction.response.send_message("開始順位は1以上です。")

    if length < 1:
        return await interaction.response.send_message("表示件数は1以上です。")

    length = min(length, 200)

    rows = get_message_ranking_slice(
        offset=start - 1,
        limit=length,
    )

    await _send_ranking(
        interaction,
        rows,
        start,
        f"📈 メッセージ数ランキング ({start}位～)",
        "件",
    )


# ===============================
# 期間指定メッセージランキング
#
# ranking_period 2026-01-01 2026-01-31
# ===============================
@bot.tree.command(name="ranking_period")
async def ranking_period(
    interaction: discord.Interaction,
    start_date: str,
    end_date: str,
    start: int = 1,
    length: int = 10,
):

    rows = get_message_ranking_slice(
        offset=start - 1,
        limit=min(length, 200),
        start_date=start_date,
        end_date=end_date,
    )

    await _send_ranking(
        interaction,
        rows,
        start,
        f"📈 メッセージ数ランキング\n({start_date} ～ {end_date})",
        "件",
        discord.Color.green(),
    )


# ===============================
# 文字数ランキング
# ===============================
@bot.tree.command(name="ranking_length")
async def ranking_length(
    interaction: discord.Interaction,
    start: int = 1,
    length: int = 10,
):

    if start < 1:
        return await interaction.response.send_message("開始順位は1以上です。")

    if length < 1:
        return await interaction.response.send_message("表示件数は1以上です。")

    rows = get_message_length_ranking_slice(
        offset=start - 1,
        limit=min(length, 200),
    )

    await _send_ranking(
        interaction,
        rows,
        start,
        f"📝 文字数ランキング ({start}位～)",
        "文字",
    )


# ===============================
# 期間指定文字数ランキング
#
# ranking_length_period
# ===============================
@bot.tree.command(name="ranking_length_period")
async def ranking_length_period(
    interaction: discord.Interaction,
    start_date: str,
    end_date: str,
    start: int = 1,
    length: int = 10,
):

    rows = get_message_length_ranking_slice(
        offset=start - 1,
        limit=min(length, 200),
        start_date=start_date,
        end_date=end_date,
    )

    await _send_ranking(
        interaction,
        rows,
        start,
        f"📝 文字数ランキング\n({start_date} ～ {end_date})",
        "文字",
        discord.Color.green(),
    )



# ===============================
# 個人ランキング（メッセージ数）
# ===============================
@bot.tree.command(name="myrank")
async def myrank(
    interaction: discord.Interaction,
    member: discord.Member = None,
):
    target = member or interaction.user

    embed = await create_member_rank_embed(
        target,
    )

    embed.set_footer(text=footer)

    await interaction.response.send_message(embed=embed)


# ===============================
# 個人ランキング（期間指定）
#
# 例
# &myrank_period 2026-06-01 2026-06-30
# ===============================
@bot.tree.command(name="myrank_period")
async def myrank_period(
    interaction: discord.Interaction,
    start_date: str,
    end_date: str,
    member: discord.Member = None,
):
    target = member or interaction.user

    embed = await create_member_rank_embed(
        target,
        start_date=start_date,
        end_date=end_date,
    )

    embed.set_footer(
        text=f"{footer} | {start_date} ～ {end_date}"
    )

    await interaction.response.send_message(embed=embed)


# ===============================
# 個人文字数ランキング
# ===============================
@bot.tree.command(name="myrank_length")
async def myrank_length(
    interaction: discord.Interaction,
    member: discord.Member = None,
):
    target = member or interaction.user

    embed = await create_member_length_rank_embed(
        target,
    )

    embed.set_footer(text=footer)

    await interaction.response.send_message(embed=embed)


# ===============================
# 個人文字数ランキング（期間指定）
#
# 例
# &myrank_length_period 2026-06-01 2026-06-30
# ===============================
@bot.tree.command(name="myrank_length_period")
async def myrank_length_period(
    interaction: discord.Interaction,
    start_date: str,
    end_date: str,
    member: discord.Member = None,
):
    target = member or interaction.user

    embed = await create_member_length_rank_embed(
        target,
        start_date=start_date,
        end_date=end_date,
    )

    embed.set_footer(
        text=f"{footer} | {start_date} ～ {end_date}"
    )

    await interaction.response.send_message(embed=embed)


print("✅ ranking.py loaded")
