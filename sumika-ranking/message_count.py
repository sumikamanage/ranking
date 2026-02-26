# functions/message_logger.py
import sqlite3
import discord
from datetime import datetime, timezone, timedelta
import os
import time
from discord.errors import HTTPException
import asyncio
from log_control import api_queue,db_queue
from config import GUILD_ID,LOG_CHANNEL_ID,DB_PATH
import aiosqlite


EXCLUDED_CHANNELS = [1399620581766463639]

# 状態フラグ
is_scanning = False
is_updating = False




#保存時の時刻を日本時間で保存
JST = timezone(timedelta(hours=9))


# ===============================
# 🔧 ログ送信関数
# ===============================

log_queue = asyncio.Queue()
async def queue_send_log(bot, message: str = None, embed=None):
    await log_queue.put((message, embed))

async def log_worker(bot, channel_id: int):
    await bot.wait_until_ready()  # Bot が完全に起動するまで待つ

    channel = bot.get_channel(channel_id)

    # もし None ならリトライする（起動直後に None になる場合がある）
    while channel is None:
        print("ログチャンネル取得できず、再試行中…")
        await asyncio.sleep(1)
        channel = bot.get_channel(channel_id)

    print(f"ログチャンネル取得成功: {channel.name}")

    buffer = []
    
async def send_log(bot: discord.Client, text: str):
    """指定チャンネルにDiscordログを送信（チャンネル未設定時はprint）"""
    if LOG_CHANNEL_ID == 0:
        print(f"[LOG] {text}")
        return

    try:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel is None:
            print(f"[WARN] ログチャンネルが見つかりません: {LOG_CHANNEL_ID}")
            return
        await api_queue.put(channel.send(f"🪵 {text}"))
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

# ===============================
# 🧹 初回フルスキャン（スレッド限定チャンネル対応）
# ===============================
async def full_scan(bot: discord.Client, guild: discord.Guild, limit_per_channel: int | None = None):
    global is_scanning
    if is_scanning:
        await send_log(bot, "⚠️ フルスキャンはすでに実行中です。")
        return
    is_scanning = True
    init_db()
    total = 0
    await send_log(bot, "📥 全メッセージスキャン開始")

    # --- 全チャンネルを対象（テキスト・フォーラム・ボイス） ---
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

    channel = None 
    for channel in all_channels:
        try:
            await send_log(bot, f"📊 {channel.name}: 読み込み開始")
            count = 0
            # チャンネル読み取り権限チェック
            if not channel.permissions_for(guild.me).read_message_history:
                continue

            # --- 通常・VCテキストチャンネルの履歴 ---
            if channel.type in (discord.ChannelType.text, discord.ChannelType.voice):
                async for message in channel.history(limit=limit_per_channel, oldest_first=True):
                    await db_queue.put(message)
                    total += 1
                    count += 1
                    if count % 1000 == 0:
                        await send_log(bot, f"📊 {channel.name}: {count} 件読み込み済み")
                    await asyncio.sleep(0.5)

            # --- フォーラムチャンネル（投稿はすべてスレッド扱い） ---
            elif channel.type == discord.ChannelType.forum:
                threads = list(channel.threads)
                async for archived in channel.archived_threads(limit=None):
                    threads.append(archived)

                for thread in threads:
                    if not thread.permissions_for(guild.me).read_message_history:
                        continue

                    async for message in thread.history(limit=limit_per_channel, oldest_first=True):
                        await db_queue.put(message)
                        total += 1
                        count += 1
                        if count % 300 == 0:
                            await send_log(bot, f"🧵 {thread.name}: {count} 件読み込み済み")
                        await asyncio.sleep(0.5)
                        
            await send_log(bot, f"📊 {channel.name}: {total} 件読み込み済み")
            
        except discord.errors.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 30)
                await send_log(bot, f"⏳ レート制限: {retry_after:.1f}秒待機")
                await asyncio.sleep(retry_after)
        except Exception as e:
            await send_log(bot, f"⚠️ {channel.name} の処理中にエラー: {e}")

        await asyncio.sleep(0.6)
    
    await send_log(bot, f"🎉 初回スキャン完了！合計 {total} 件保存")
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
    start_time = time.time()
    updated_total = 0

    await send_log(bot, "🔁 増分更新開始")


    # --- 全チャンネルを対象（テキスト・フォーラム・ボイス） ---
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

    channel = None 
    for channel in all_channels:
        try:
            await send_log(bot, f"📊 {channel.name}: 読み込み開始")
            count = 0
            # チャンネル読み取り権限チェック
            if not channel.permissions_for(guild.me).read_message_history:
                continue

            # --- 通常・VCテキストチャンネルの履歴 ---
            if channel.type in (discord.ChannelType.text, discord.ChannelType.voice):
                async for message in channel.history(limit=limit_per_channel, oldest_first=True):
                    await db_queue.put(message)
                    updated_total += 1
                    count += 1
                    if count % 1000 == 0:
                        await send_log(bot, f"📊 {channel.name}: {count} 件読み込み済み")
                    await asyncio.sleep(0.5)

            # --- フォーラムチャンネル（投稿はすべてスレッド扱い） ---
            elif channel.type == discord.ChannelType.forum:
                threads = list(channel.threads)
                async for archived in channel.archived_threads(limit=None):
                    threads.append(archived)

                for thread in threads:
                    if not thread.permissions_for(guild.me).read_message_history:
                        continue

                    async for message in thread.history(limit=limit_per_channel, oldest_first=True):
                        await db_queue.put(message)
                        updated_total += 1
                        count += 1
                        if count % 300 == 0:
                            await send_log(bot, f"🧵 {thread.name}: {count} 件読み込み済み")
                        await asyncio.sleep(0.5)

        except discord.errors.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 30)
                await send_log(bot, f"⏳ レート制限: {retry_after:.1f}秒待機")
                await asyncio.sleep(retry_after)
        except Exception as e:
            await send_log(bot, f"⚠️ {channel.name} の処理中にエラー: {e}")

        await asyncio.sleep(0.5)

    end_time = time.time()
    await send_log(bot, f"✅ 増分更新完了: {updated_total} 件, 処理時間: {end_time - start_time:.1f}秒")
    is_updating = False


# ===============================
# 📊 ランキング関連
# ===============================

#通常のランキングで使用するもの
def get_message_ranking_slice(offset: int = 0, limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT author_id, COUNT(*) AS count
        FROM messages
        GROUP BY author_id
        ORDER BY count DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = c.fetchall()
    conn.close()
    return rows



#月間ランキング
def get_monthly_message_ranking_slice(offset: int = 0, limit: int = 10):
    """指定した年・月のメッセージを author_id ごとに集計して返す"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT author_id, COUNT(*) AS count
        FROM messages
        WHERE datetime(created_at, '-9 hours') >= datetime('now', '-1 month')
        GROUP BY author_id
        ORDER BY count DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    rows = c.fetchall()
    conn.close()
    return rows

#文字数ランキング
def get_message_length_ranking_slice(offset: int = 0, limit: int = 10):
    """全期間：ユーザーごとのメッセージ文字数合計ランキング"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT author_id, SUM(LENGTH(content)) AS total_length
        FROM messages
        WHERE content IS NOT NULL AND content != ''
        GROUP BY author_id
        ORDER BY total_length DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    rows = c.fetchall()
    conn.close()
    return rows


#月間文字数ランキング
def get_monthly_message_length_ranking_slice(
    offset: int = 0,
    limit: int = 10
):
    """指定した年・月の文字数ランキング"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT author_id, SUM(LENGTH(content)) AS total_length
        FROM messages
        WHERE content IS NOT NULL
          AND content != ''
          AND datetime(created_at, '-9 hours') >= datetime('now', '-1 month')
        GROUP BY author_id
        ORDER BY total_length DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))

    rows = c.fetchall()
    conn.close()
    return rows


#個人のランキングカウント用
def get_member_rank_and_count(member_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM messages WHERE author_id = ?", (member_id,))
    count_result = c.fetchone()
    count = count_result[0] if count_result else 0

    c.execute("""
        SELECT author_id, COUNT(*) AS cnt
        FROM messages
        GROUP BY author_id
        ORDER BY cnt DESC
    """)
    all_rows = c.fetchall()
    conn.close()

    rank = None
    for i, (aid, cnt) in enumerate(all_rows, start=1):
        if aid == member_id:
            rank = i
            break
    if rank is None:
        rank = len(all_rows) + 1
    return rank, count

#個人のランキング表示用
async def create_member_rank_embed(member: discord.Member):
    rank, count = get_member_rank_and_count(member.id)
    embed = discord.Embed(
        title=f"📊 {member.display_name} のメッセージランキング",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🎖順位", value=f"{rank} 位", inline=True)
    embed.add_field(name="💬 メッセージ数", value=f"{count} 件", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else "")
    return embed

# 個人の月間ランキングカウント用
def get_member_monthly_rank_and_count(
    member_id: int,
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()


    # 自分の月間メッセージ数
    c.execute("""
        SELECT COUNT(*)
        FROM messages
        WHERE author_id = ?
          AND datetime(created_at) >= datetime('now', '-1 month')
    """, (member_id,))
    result = c.fetchone()
    count = result[0] if result else 0

    # 全体ランキング用
    c.execute("""
        SELECT author_id, COUNT(*) AS cnt
        FROM messages
        WHERE datetime(created_at, '-9 hours') >= datetime('now', '-1 month')
        GROUP BY author_id
        ORDER BY cnt DESC
    """)
    all_rows = c.fetchall()
    conn.close()

    rank = None
    for i, (aid, cnt) in enumerate(all_rows, start=1):
        if aid == member_id:
            rank = i
            break

    if rank is None:
        rank = len(all_rows) + 1

    return rank, count

# 個人の月間メッセージ数ランキング表示用
async def create_member_monthly_rank_embed(
    member: discord.Member,
):
    rank, count = get_member_monthly_rank_and_count(
        member.id
    )

    embed = discord.Embed(
        title=f"📊 {member.display_name} の直近1ヶ月のメッセージランキング",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🎖順位", value=f"{rank} 位", inline=True)
    embed.add_field(name="💬 メッセージ数", value=f"{count} 件", inline=True)
    embed.set_thumbnail(
        url=member.display_avatar.url if member.display_avatar else ""
    )
    return embed


# 個人の文字数ランキング用
def get_member_length_rank_and_total(member_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 自分の合計文字数
    c.execute("""
        SELECT COALESCE(SUM(LENGTH(content)), 0)
        FROM messages
        WHERE author_id = ?
          AND content IS NOT NULL
          AND content != ''
    """, (member_id,))
    result = c.fetchone()
    total_length = result[0] if result else 0

    # 全ユーザーの文字数合計（順位計算用）
    c.execute("""
        SELECT author_id, SUM(LENGTH(content)) AS total
        FROM messages
        WHERE content IS NOT NULL
          AND content != ''
        GROUP BY author_id
        ORDER BY total DESC
    """)
    all_rows = c.fetchall()
    conn.close()

    rank = None
    for i, (aid, total) in enumerate(all_rows, start=1):
        if aid == member_id:
            rank = i
            break

    # 一度も文字を書いていない人
    if rank is None:
        rank = len(all_rows) + 1

    return rank, total_length

# 個人の文字数ランキング表示用
async def create_member_length_rank_embed(member: discord.Member):
    rank, total_length = get_member_length_rank_and_total(member.id)

    embed = discord.Embed(
        title=f"📊 {member.display_name} の文字数ランキング",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🎖順位", value=f"{rank} 位", inline=True)
    embed.add_field(
        name="📝 合計文字数",
        value=f"{total_length:,} 文字",
        inline=True
    )
    embed.set_thumbnail(
        url=member.display_avatar.url if member.display_avatar else ""
    )
    return embed

# 個人の月間文字数ランキング用
def get_member_monthly_length_rank_and_total(
    member_id: int,
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 自分の月間合計文字数
    c.execute("""
        SELECT COALESCE(SUM(LENGTH(content)), 0)
        FROM messages
        WHERE author_id = ?
          AND content IS NOT NULL
          AND content != ''
          AND datetime(created_at, '-9 hours') >= datetime('now', '-1 month')
    """, (member_id,))
    result = c.fetchone()
    total_length = result[0] if result else 0

    # 全体ランキング用
    c.execute("""
        SELECT author_id, SUM(LENGTH(content)) AS total
        FROM messages
        WHERE content IS NOT NULL
          AND content != ''
          AND datetime(created_at, '-9 hours') >= datetime('now', '-1 month')
        GROUP BY author_id
        ORDER BY total DESC
    """)
    all_rows = c.fetchall()
    conn.close()

    rank = None
    for i, (aid, total) in enumerate(all_rows, start=1):
        if aid == member_id:
            rank = i
            break

    if rank is None:
        rank = len(all_rows) + 1

    return rank, total_length

# 個人の月間文字数ランキング表示用
async def create_member_monthly_length_rank_embed(
    member: discord.Member,
):
    rank, total_length = get_member_monthly_length_rank_and_total(
        member.id
    )

    embed = discord.Embed(
        title=f"📊 {member.display_name} の直近一ヶ月文字数ランキング",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🎖順位", value=f"{rank} 位", inline=True)
    embed.add_field(
        name="📝 合計文字数",
        value=f"{total_length:,} 文字",
        inline=True
    )
    embed.set_thumbnail(
        url=member.display_avatar.url if member.display_avatar else ""
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
