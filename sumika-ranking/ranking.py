import discord
import asyncio
from discord.ext import commands

from datetime import datetime

from message_count import (
    get_message_ranking_slice,
    get_monthly_message_ranking_slice,
    get_message_length_ranking_slice,
    get_monthly_message_length_ranking_slice,
    create_member_rank_embed,
    create_member_monthly_rank_embed,
    create_member_length_rank_embed,
    create_member_monthly_length_rank_embed,
)

from config import FOOTER

from bot_core.bot import bot

footer=FOOTER

# ---- コマンド：ランキング表示 ----
@bot.command()
async def らんきんぐ(ctx, start: int = 1, length: int = 10):
    """
    使い方:
      !ranking       -> 1位〜10位
      !ranking 20    -> 20位〜29位
    start は表示したい「開始順位」(1始まり)
    """

    try:
        start = int(start)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return
    try:
        length = int(length)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return
    
    # バリデーション
    if start < 1:
        await ctx.send("開始順位は1以上を指定してください。")
        return

    if length < 1:
        await ctx.send("長さは1以上を指定してください。")
        return

    PAGE_SIZE = length
    # SQL の OFFSET は 0 始まりなので start-1 を渡す
    offset = start - 1

    # 上限を設けておく（念のため）
    MAX_LIMIT = 200
    if PAGE_SIZE > MAX_LIMIT:
        PAGE_SIZE = MAX_LIMIT

    rows = get_message_ranking_slice(offset=offset, limit=PAGE_SIZE)

    if not rows:
        await ctx.send(f"{start}位からのランキングは見つかりませんでした。")
        return

    lines = []
    for i, (author_id, count) in enumerate(rows, start=start):
        # guild にメンバーが残っていれば表示名とメンションを出す
        member = ctx.guild.get_member(int(author_id))
        if member:
            display = f"(<@{author_id}>)"
        else:
            # メンバーがいなければ ID と DB に保存してある文字列を代わりに使う場合は、messages テーブルに author 値を追加取得する工夫が必要
            display = f"(<@{author_id}>)"
        lines.append(f"🏅{i}位: {display} — {count}件")

    embed = discord.Embed(
        title=f"📈 メッセージ数ランキング：{start}位〜{start+len(rows)-1}位",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    embed.set_footer(text=footer)
    await ctx.send(embed=embed)

@bot.command()
async def つきらんきんぐ(ctx,  start: int = 1, length: int = 10):
    """
    使い方:
      !ranking       -> 1位〜10位
      !ranking 20    -> 20位〜29位
    start は表示したい「開始順位」(1始まり)
    ただし今月分のみが表示される
    """

    try:
        start = int(start)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return
    try:
        length = int(length)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return

    # --- start / length バリデーション ---
    if start < 1:
        await ctx.send("開始順位は1以上を指定してください。")
        return
    if length < 1:
        await ctx.send("長さは1以上を指定してください。")
        return

    PAGE_SIZE = length
    offset = start - 1

    MAX_LIMIT = 200
    if PAGE_SIZE > MAX_LIMIT:
        PAGE_SIZE = MAX_LIMIT

    # --- DBから月間ランキング取得 ---
    rows = get_monthly_message_ranking_slice(
        offset=offset,
        limit=PAGE_SIZE
    )

    if not rows:
        await ctx.send(f"📭 直近1ヶ月の{start}位 以降のデータはありません。")
        return

    # --- メッセージ構築 ---
    lines = []
    for i, (author_id, count) in enumerate(rows, start=start):
        member = ctx.guild.get_member(int(author_id))
        if member:
            display = f"<@{author_id}>"
        else:
            display = f"<@{author_id}>"
        lines.append(f"🏅{i}位: {display} — {count} 件")

    embed = discord.Embed(
        title=f"📅 メッセージ数ランキング",
        description="\n".join(lines),
        color=discord.Color.green()
    )

    embed.set_footer(text=f"{start}位〜{start + len(rows) - 1}位")

    embed.set_footer(text=footer)
    await ctx.send(embed=embed)



@bot.command()
async def もじらんきんぐ(ctx, start: int = 1, length: int = 10):
    """
    使い方:
      !ranking       -> 1位〜10位
      !ranking 20    -> 20位〜29位
    start は表示したい「開始順位」(1始まり)
    """

    try:
        start = int(start)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return
    try:
        length = int(length)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return
    
    # バリデーション
    if start < 1:
        await ctx.send("開始順位は1以上を指定してください。")
        return

    if length < 1:
        await ctx.send("長さは1以上を指定してください。")
        return

    PAGE_SIZE = length
    # SQL の OFFSET は 0 始まりなので start-1 を渡す
    offset = start - 1

    # 上限を設けておく（念のため）
    MAX_LIMIT = 200
    if PAGE_SIZE > MAX_LIMIT:
        PAGE_SIZE = MAX_LIMIT

    rows = get_message_length_ranking_slice(offset=offset, limit=PAGE_SIZE)

    if not rows:
        await ctx.send(f"{start}位からのランキングは見つかりませんでした。")
        return

    lines = []
    for i, (author_id, count) in enumerate(rows, start=start):
        # guild にメンバーが残っていれば表示名とメンションを出す
        member = ctx.guild.get_member(int(author_id))
        if member:
            display = f"(<@{author_id}>)"
        else:
            # メンバーがいなければ ID と DB に保存してある文字列を代わりに使う場合は、messages テーブルに author 値を追加取得する工夫が必要
            display = f"(<@{author_id}>)"
        lines.append(f"🏅{i}位: {display} — {count}字")

    embed = discord.Embed(
        title=f"📈 メッセージ文字数ランキング：{start}位〜{start+len(rows)-1}位",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    embed.set_footer(text=footer)
    await ctx.send(embed=embed)

@bot.command()
async def つきもじらんきんぐ(ctx,  start: int = 1, length: int = 10):
    """
    使い方:
      !ranking       -> 1位〜10位
      !ranking 20    -> 20位〜29位
    start は表示したい「開始順位」(1始まり)
    ただし今月分のみが表示される
    """

    try:
        start = int(start)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return
    try:
        length = int(length)
    except ValueError:
        await ctx.send("❌ 数字を指定してください（例: !ranking 10）")
        return

    # --- start / length バリデーション ---
    if start < 1:
        await ctx.send("開始順位は1以上を指定してください。")
        return
    if length < 1:
        await ctx.send("長さは1以上を指定してください。")
        return

    PAGE_SIZE = length
    offset = start - 1

    MAX_LIMIT = 200
    if PAGE_SIZE > MAX_LIMIT:
        PAGE_SIZE = MAX_LIMIT

    # --- DBから月間ランキング取得 ---
    rows = get_monthly_message_length_ranking_slice(
        offset=offset,
        limit=PAGE_SIZE
    )

    if not rows:
        await ctx.send(f"📭 直近1ヶ月の {start}位 以降のデータはありません。")
        return

    # --- メッセージ構築 ---
    lines = []
    for i, (author_id, count) in enumerate(rows, start=start):
        member = ctx.guild.get_member(int(author_id))
        if member:
            display = f"<@{author_id}>"
        else:
            display = f"<@{author_id}>"
        lines.append(f"🏅{i}位: {display} — {count} 字")

    embed = discord.Embed(
        title=f"📅 直近1ヶ月のメッセージ文字数ランキング",
        description="\n".join(lines),
        color=discord.Color.green()
    )

    embed.set_footer(text=f"{start}位〜{start + len(rows) - 1}位")

    embed.set_footer(text=footer)
    await ctx.send(embed=embed)


#通常マイランク
@bot.command(name="myrank")
async def myrank(ctx, member: discord.Member = None):
    """メンバーの順位とメッセージ数を表示"""
    target = member or ctx.author
    embed = await create_member_rank_embed(target)
    embed.set_footer(text=footer)
    await ctx.send(embed=embed)

#月間マイランク
@bot.command(name="monthlymyrank")
async def monthlymyrank(ctx, member: discord.Member = None):
    """メンバーの順位とメッセージ数を表示"""
    target = member or ctx.author
    # --- 年月に今月を使用 ---
    
    embed = await create_member_monthly_rank_embed(target)
    embed.set_footer(text=footer)
    await ctx.send(embed=embed)

#通常マイ文字数ランク
@bot.command(name="mozimyrank")
async def mozimyrank(ctx, member: discord.Member = None):
    """メンバーの順位とメッセージ数を表示"""
    target = member or ctx.author
    embed = await create_member_length_rank_embed(target)
    embed.set_footer(text=footer)
    await ctx.send(embed=embed)

#月間マイ文字数ランク
@bot.command(name="monthlymozimyrank")
async def monthlymozimyrank(ctx, member: discord.Member = None):
    """メンバーの順位とメッセージ数を表示"""
    target = member or ctx.author
    
    embed = await create_member_monthly_length_rank_embed(target)
    embed.set_footer(text=footer)
    await ctx.send(embed=embed)
