# message_count.py
# ランキングの集計クエリと表示用Embed。
# データは stats_store が管理する daily_stats テーブル(日別・ユーザー別)から読む。
import sqlite3

import discord

from config import LOG_CHANNEL_ID, DB_PATH


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
# 📊 ランキング取得共通
# ===============================
# 日付は JST の YYYY-MM-DD(ゼロ埋め)で比較する。start/end ともその日を含む。
def _make_date_where(
    start_date: str | None = None,
    end_date: str | None = None,
):
    conditions = []
    params = []

    if start_date:
        conditions.append("day >= ?")
        params.append(start_date)

    if end_date:
        conditions.append("day <= ?")
        params.append(end_date)

    if not conditions:
        return "", []

    return "AND " + " AND ".join(conditions), params


def _query(sql: str, params: list):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


# ===============================
# 💬 メッセージ数ランキング
# ===============================
def get_message_ranking_slice(
    offset=0,
    limit=10,
    start_date=None,
    end_date=None,
):
    where, params = _make_date_where(start_date, end_date)

    return _query(f"""
        SELECT author_id,
               SUM(msgs) AS count
        FROM daily_stats
        WHERE 1=1
        {where}
        GROUP BY author_id
        ORDER BY count DESC, author_id
        LIMIT ? OFFSET ?
    """, params + [limit, offset])


# ===============================
# 📝 文字数ランキング
# ===============================
def get_message_length_ranking_slice(
    offset=0,
    limit=10,
    start_date=None,
    end_date=None,
):
    where, params = _make_date_where(start_date, end_date)

    return _query(f"""
        SELECT author_id,
               SUM(chars) AS total_length
        FROM daily_stats
        WHERE 1=1
        {where}
        GROUP BY author_id
        HAVING SUM(chars) > 0
        ORDER BY total_length DESC, author_id
        LIMIT ? OFFSET ?
    """, params + [limit, offset])


# ===============================
# 👤 個人ランキング取得共通
# ===============================
def _rank_and_value(member_id, column, start_date, end_date):
    where, params = _make_date_where(start_date, end_date)

    all_rows = _query(f"""
        SELECT author_id,
               SUM({column}) AS v
        FROM daily_stats
        WHERE 1=1
        {where}
        GROUP BY author_id
        HAVING SUM({column}) > 0
        ORDER BY v DESC, author_id
    """, params)

    rank = len(all_rows) + 1
    value = 0

    for i, (aid, v) in enumerate(all_rows, start=1):
        if aid == member_id:
            rank, value = i, v
            break

    return rank, value


def get_member_rank_and_count(
    member_id,
    start_date=None,
    end_date=None,
):
    return _rank_and_value(member_id, "msgs", start_date, end_date)


def get_member_length_rank_and_total(
    member_id,
    start_date=None,
    end_date=None,
):
    return _rank_and_value(member_id, "chars", start_date, end_date)


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
    rows = _query(
        "SELECT COALESCE(SUM(msgs), 0), COUNT(DISTINCT author_id) FROM daily_stats",
        [],
    )
    total, authors = rows[0]
    return {"db_path": DB_PATH, "total_messages": total, "distinct_authors": authors}
