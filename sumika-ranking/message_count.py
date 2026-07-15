# functions/message_logger.py
import sqlite3
import discord
from datetime import datetime, timezone, timedelta
import os
import time
from discord.errors import HTTPException
import asyncio
from log_control import save_message_to_db,history_worker,api_call,fetch_history,fetch_archived_threads
from config import GUILD_ID,LOG_CHANNEL_ID,DB_PATH
import aiosqlite

import os
print("RANKING DB PATH:", DB_PATH)
print("EXISTS:", os.path.exists(DB_PATH))
EXCLUDED_CHANNELS = [1399620581766463639]

# 状態フラグ
is_scanning = False
is_updating = False


#保存時の時刻を日本時間で保存
JST = timezone(timedelta(hours=9))


# ===============================
# 🔧 ログ送信関数
# ===============================

    
async def send_log(bot: discord.Client, text: str):
    """指定チャンネルにログを送信"""

    if LOG_CHANNEL_ID == 0:
        print(f"[LOG] {text}")
        return

    try:
        channel = bot.get_channel(LOG_CHANNEL_ID)

        if channel is None:
            print(f"[WARN] ログチャンネルが見つかりません: {LOG_CHANNEL_ID}")
            return

        await bot.api_queue.put(
            channel.send(f"🪵 {text}")
        )

    except Exception as e:
        print(f"[ERR] send_log失敗: {e}")
        
# ===============================
# 🧱 DB 初期化
# ===============================
def init_db(reset: bool = False):
    """SQLite初期化（存在しなければ作成）、reset=True ならDBを削除して再作成"""
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("🗑️ 既存DBを削除しました")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            author TEXT,
            author_id INTEGER,
            content TEXT,
            channel_id INTEGER,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("✅ messages.db 初期化完了")
    print(DB_PATH)



# ===============================
# 🧹 初回フルスキャン（スレッド限定チャンネル対応）
# ===============================
async def full_scan(bot: discord.Client, guild: discord.Guild, limit_per_channel: int | None = None):
    global is_scanning

    if is_scanning:
        await send_log(bot, "⚠️ フルスキャンはすでに実行中です。")
        return

    is_scanning = True

    try:
        init_db()
        total = 0

        await send_log(bot, "📥 全メッセージスキャン開始")

        EXCLUDED_CHANNEL_IDS = {
            1276087091280871546,
            1399620581766463639,
        }

        all_channels = [
            ch for ch in guild.channels
            if ch.type in (
                discord.ChannelType.text,
                discord.ChannelType.forum,
                discord.ChannelType.voice,
            )
            and ch.id not in EXCLUDED_CHANNEL_IDS
        ]

        me = guild.me or guild.get_member(bot.user.id)

        for channel in all_channels:
            try:
                await send_log(bot, f"📊 {channel.name}: 読み込み開始")

                count = 0

                if not channel.permissions_for(me).read_message_history:
                    continue

                # -------------------------------
                # 通常チャンネル
                # -------------------------------
                if channel.type in (
                    discord.ChannelType.text,
                    discord.ChannelType.voice,
                ):

                    messages = await fetch_history(
                        bot,
                        channel,
                        limit_per_channel,
                        True
                    )

                    for message in messages:
                        await bot.db_queue.put(message)

                        total += 1
                        count += 1

                        if count % 1000 == 0:
                            await send_log(
                                bot,
                                f"📊 {channel.name}: {count} 件読み込み済み"
                            )
                            
                        if count % 5000 == 0:
                            await bot.db_queue.join()

                # -------------------------------
                # フォーラム
                # -------------------------------
                elif channel.type == discord.ChannelType.forum:

                    threads = {
                        thread.id: thread
                        for thread in channel.threads
                    }

                    for thread in await fetch_archived_threads(bot, channel):
                        threads.setdefault(thread.id, thread)

                    threads = list(threads.values())

                    for thread in threads:

                        if not thread.permissions_for(me).read_message_history:
                            continue

                        messages = await fetch_history(
                            bot,
                            thread,
                            limit_per_channel,
                            True
                        )

                        for message in messages:
                            await bot.db_queue.put(message)

                            total += 1
                            count += 1

                            if count % 300 == 0:
                                await send_log(
                                    bot,
                                    f"🧵 {thread.name}: {count} 件読み込み済み"
                                )

                            if count % 5000 == 0:
                                await bot.db_queue.join()

                await send_log(
                    bot,
                    f"📊 {channel.name}: {count} 件読み込み完了"
                )

            except discord.HTTPException as e:

                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 30)

                    await send_log(
                        bot,
                        f"⏳ レート制限: {retry_after:.1f}秒待機"
                    )

                    await asyncio.sleep(retry_after)

            except Exception as e:
                await send_log(
                    bot,
                    f"⚠️ {channel.name} の処理中にエラー: {e}"
                )

            await asyncio.sleep(0.3)

        await send_log(
            bot,
            f"🎉 初回スキャン完了！合計 {total} 件保存"
        )

    finally:
        is_scanning = False
# ===============================
# 🔄 増分更新（スレッド限定チャンネル対応）
# ===============================
async def incremental_update(bot: discord.Client, guild: discord.Guild):
    global is_updating, is_scanning

    limit_per_channel = None  # Noneで全件取得

    if is_updating:
        await send_log(bot, "⚠️ 増分更新はすでに実行中です。")
        return

    if is_scanning:
        await send_log(bot, "⚠️ フルスキャン中のため、更新できません。")
        return

    is_updating = True

    try:
        start_time = time.time()
        updated_total = 0

        await send_log(bot, "🔁 増分更新開始")

        EXCLUDED_CHANNEL_IDS = {
            1276087091280871546,
            1399620581766463639,
        }

        all_channels = [
            ch for ch in guild.channels
            if ch.type in (
                discord.ChannelType.text,
                discord.ChannelType.forum,
                discord.ChannelType.voice,
            )
            and ch.id not in EXCLUDED_CHANNEL_IDS
        ]

        me = guild.me or guild.get_member(bot.user.id)

        for channel in all_channels:

            try:
                await send_log(bot, f"📊 {channel.name}: 読み込み開始")

                count = 0

                if not channel.permissions_for(me).read_message_history:
                    continue

                # -------------------------------
                # 通常チャンネル
                # -------------------------------
                if channel.type in (
                    discord.ChannelType.text,
                    discord.ChannelType.voice,
                ):

                    messages = await fetch_history(
                        bot,
                        channel,
                        limit_per_channel,
                        True
                    )

                    for message in messages:

                        await bot.db_queue.put(message)

                        updated_total += 1
                        count += 1

                        if count % 1000 == 0:
                            await send_log(
                                bot,
                                f"📊 {channel.name}: {count} 件読み込み済み"
                            )

                        if count % 5000 == 0:
                            await bot.db_queue.join()

                # -------------------------------
                # フォーラム
                # -------------------------------
                elif channel.type == discord.ChannelType.forum:

                    threads = {
                        thread.id: thread
                        for thread in channel.threads
                    }

                    for thread in await fetch_archived_threads(bot, channel):
                        threads.setdefault(thread.id, thread)

                    threads = list(threads.values())

                    for thread in threads:

                        if not thread.permissions_for(me).read_message_history:
                            continue

                        messages = await fetch_history(
                            bot,
                            thread,
                            limit_per_channel,
                            True
                        )

                        for message in messages:

                            await bot.db_queue.put(message)

                            updated_total += 1
                            count += 1
                            
                            if count % 300 == 0:
                                await send_log(
                                    bot,
                                    f"🧵 {thread.name}: {count} 件読み込み済み"
                                )
                            if count % 5000 == 0:
                                await bot.db_queue.join()

                await send_log(
                    bot,
                    f"📊 {channel.name}: {count} 件読み込み完了"
                )

            except discord.HTTPException as e:

                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 30)
                    await send_log(
                        bot,
                        f"⏳ レート制限: {retry_after:.1f}秒待機"
                    )
                    await asyncio.sleep(retry_after)

            except Exception as e:
                await send_log(
                    bot,
                    f"⚠️ {channel.name} の処理中にエラー: {e}"
                )
            await asyncio.sleep(0.3)

        # DB保存が終わるまで待機
        await bot.db_queue.join()

        end_time = time.time()

        await send_log(
            bot,
            f"✅ 増分更新完了: {updated_total} 件, 処理時間: {end_time - start_time:.1f}秒"
        )
    finally:
        is_updating = False

        # キャンセル時のログ
        if asyncio.current_task().cancelled():
            await send_log(
                bot,
                "🛑 フルスキャンが停止されました。"
            )

# ===============================
# 📊 ランキング取得共通
# ===============================

def _make_date_where(
    start_date: str | None = None,
    end_date: str | None = None,
):
    conditions = []
    params = []

    if start_date:
        conditions.append(
            "datetime(created_at, '-9 hours') >= datetime(?)"
        )
        params.append(start_date)

    if end_date:
        conditions.append(
            "datetime(created_at, '-9 hours') <= datetime(?)"
        )
        params.append(end_date + " 23:59:59")

    if not conditions:
        return "", []

    return "AND " + " AND ".join(conditions), params


# ===============================
# 💬 メッセージ数ランキング
# ===============================

def get_message_ranking_slice(
    offset=0,
    limit=10,
    start_date=None,
    end_date=None,
):



    where, params = _make_date_where(start_date,end_date,)

    print("READ DB:", DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(f"""
        SELECT author_id,
               COUNT(*) AS count
        FROM messages
        WHERE 1=1
        {where}
        GROUP BY author_id
        ORDER BY count DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    rows = c.fetchall()
    conn.close()

    return rows


# ===============================
# 📝 文字数ランキング
# ===============================

def get_message_length_ranking_slice(
    offset=0,
    limit=10,
    start_date=None,
    end_date=None,
):
    where, params = _make_date_where(start_date,end_date,)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(f"""
        SELECT author_id,
               SUM(LENGTH(content)) AS total_length
        FROM messages
        WHERE content IS NOT NULL
          AND content != ''
          {where}
        GROUP BY author_id
        ORDER BY total_length DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    rows = c.fetchall()
    conn.close()

    return rows


# ===============================
# 👤 個人ランキング取得共通
# ===============================

def get_member_rank_and_count(
    member_id,
    start_date=None,
    end_date=None,
):


    where, params = _make_date_where(start_date,end_date,)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 自分のメッセージ数
    c.execute(f"""
        SELECT COUNT(*)
        FROM messages
        WHERE author_id = ?
        {where}
    """, [member_id] + params)

    result = c.fetchone()
    count = result[0] if result else 0

    # 全体ランキング
    c.execute(f"""
        SELECT author_id,
               COUNT(*) AS cnt
        FROM messages
        WHERE 1=1
        {where}
        GROUP BY author_id
        ORDER BY cnt DESC
    """, params)

    all_rows = c.fetchall()

    conn.close()

    rank = len(all_rows) + 1

    for i, (aid, _) in enumerate(all_rows, start=1):
        if aid == member_id:
            rank = i
            break

    return rank, count


# ===============================
# 👤 個人文字数ランキング取得共通
# ===============================

def get_member_length_rank_and_total(
    member_id,
    start_date=None,
    end_date=None,
):


    where, params = _make_date_where(start_date,end_date,)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 自分の文字数
    c.execute(f"""
        SELECT COALESCE(
            SUM(LENGTH(content)),
            0
        )
        FROM messages
        WHERE author_id = ?
          AND content IS NOT NULL
          AND content != ''
          {where}
    """, [member_id] + params)

    result = c.fetchone()
    total = result[0] if result else 0

    # 全体ランキング
    c.execute(f"""
        SELECT author_id,
               SUM(LENGTH(content)) AS total_length
        FROM messages
        WHERE content IS NOT NULL
          AND content != ''
          {where}
        GROUP BY author_id
        ORDER BY total_length DESC
    """, params)

    all_rows = c.fetchall()

    conn.close()

    rank = len(all_rows) + 1

    for i, (aid, _) in enumerate(all_rows, start=1):
        if aid == member_id:
            rank = i
            break

    return rank, total



# ===============================
# 📊 個人メッセージランキングEmbed
# ===============================
async def create_member_rank_embed(
    member,
    start_date=None,
    end_date=None,
):
    rank, count = get_member_rank_and_count(
        member.id,
        start_date=start_date,
        end_date=end_date,
    )

    if start_date is None and end_date is None:
        title = f"📊 {member.display_name} のメッセージランキング"
    else:
        if start_date==None:
            start_text = "最初"
        else:
            start_text=start_date

        if end_date == None:
            end_text = "現在"
        else:
            end_text = end_date

        title = (
            f"📊 {member.display_name} のメッセージランキング\n"
            f"{start_text} ～ {end_text}"
        )

    embed = discord.Embed(
        title=title,
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🎖順位",
        value=f"{rank} 位",
        inline=True
    )

    embed.add_field(
        name="💬 メッセージ数",
        value=f"{count:,} 件",
        inline=True
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    return embed


# ===============================
# 📝 個人文字数ランキングEmbed
# ===============================
async def create_member_length_rank_embed(
    member,
    start_date=None,
    end_date=None,
):
    rank, total_length = get_member_length_rank_and_total(
        member.id,
        start_date=start_date,
        end_date=end_date,
    )

    if start_date is None and end_date is None:
        title = f"📊 {member.display_name} の文字数ランキング"
    else:
        if start_date == None:
            start_text = "最初"
        else:
            start_text=start_date

        if end_date == None:
            end_text = "現在"
        else:
            end_text = end_date
            
        title = (
            f"📊 {member.display_name} の文字数ランキング\n"
            f"{start_text} ～ {end_text}"
        )

    embed = discord.Embed(
        title=title,
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🎖順位",
        value=f"{rank} 位",
        inline=True
    )

    embed.add_field(
        name="📝 合計文字数",
        value=f"{total_length:,} 文字",
        inline=True
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    return embed


# ===============================
# 🧾 DB情報デバッグ用
# ===============================
def db_info():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT author_id) FROM messages")
    authors = c.fetchone()[0]
    conn.close()
    return {"db_path": DB_PATH, "total_messages": total, "distinct_authors": authors}
