# stats_store.py
# ------------------------------------------------------------
# Render無料枠など「再起動でファイルが消える」環境向けの保存層。
#
#   ・作業用DB(SQLite)は毎回作り直す。消えてもよい。
#   ・永続化は「日別集計 + チャンネルごとの取得済み位置(ウォーターマーク)」を
#     1つのgzip JSONにして、Discordの保存用チャンネルに添付投稿する。
#   ・起動時はスナップショットを読み込み、ウォーターマーク以降の
#     メッセージだけをDiscordから取得して足す(=差分だけ)。
#   ・スナップショットが消えても、Discord自体が正なので再スキャンで復元できる。
# ------------------------------------------------------------
import asyncio
import gzip
import io
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import discord

from config import DB_PATH, STORE_CHANNEL_ID

JST = timezone(timedelta(hours=9))

SNAPSHOT_NAME = "stats_snapshot.json.gz"
KEEP_SNAPSHOTS = 3          # 保存用チャンネルに残す世代数
SNAPSHOT_INTERVAL = 600     # 秒。変更があれば10分おきに保存

# 集計対象外
EXCLUDED_CHANNEL_IDS = {
    1276087091280871546,
    1399620581766463639,
    STORE_CHANNEL_ID,        # 保存用チャンネル自体は数えない
}
EXCLUDED_ROLE_IDS = {1473498996159942812}

# ------------------------------------------------------------
# 状態
# ------------------------------------------------------------
_lock = asyncio.Lock()
_wm: dict[int, int] = {}     # channel_id -> 最後に処理したメッセージID
_failed: set[int] = set()    # 同期に失敗したチャンネル(ライブ加算を止める)
_buffer: list = []           # 追いつき中に届いたライブメッセージ
_catching_up = True
_dirty = False
_running = False             # catch_up_all の多重起動防止
_disabled = False            # 保存先が使えないとき True(バッファを溜めない)


def is_ready() -> bool:
    """追いつき完了後 True。ランキングコマンド側で「集計中」表示に使える"""
    return not _catching_up


def is_running() -> bool:
    return _running


def disable():
    """保存用チャンネルが使えないとき。ライブ分のバッファを止める。"""
    global _disabled
    _disabled = True
    _buffer.clear()


async def reset_all():
    """集計とウォーターマークを全消去(/first_scan 用)。実行中に呼ばないこと。"""
    async with _lock:
        _wm.clear()
        _failed.clear()
        await asyncio.to_thread(init_store)


# ------------------------------------------------------------
# 作業用DB
# ------------------------------------------------------------
def init_store():
    """作業用DBを作り直す。永続データの正はDiscord側のスナップショット。"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE daily_stats (
                day       TEXT    NOT NULL,   -- JSTの日付 YYYY-MM-DD
                author_id INTEGER NOT NULL,
                msgs      INTEGER NOT NULL DEFAULT 0,
                chars     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, author_id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_batch(rows: dict):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executemany(
            """
            INSERT INTO daily_stats (day, author_id, msgs, chars)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(day, author_id) DO UPDATE SET
                msgs  = msgs  + excluded.msgs,
                chars = chars + excluded.chars
            """,
            [(d, a, v[0], v[1]) for (d, a), v in rows.items()],
        )
        conn.commit()
    finally:
        conn.close()


def _import_rows(daily: list):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_stats (day, author_id, msgs, chars) "
            "VALUES (?, ?, ?, ?)",
            daily,
        )
        conn.commit()
    finally:
        conn.close()


def _export(wm: dict) -> bytes:
    conn = sqlite3.connect(DB_PATH)
    try:
        daily = conn.execute(
            "SELECT day, author_id, msgs, chars FROM daily_stats"
        ).fetchall()
    finally:
        conn.close()

    payload = {
        "version": 1,
        "saved_at": datetime.now(JST).isoformat(),
        "watermarks": {str(k): v for k, v in wm.items()},
        "daily": daily,
    }
    return gzip.compress(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )


# ------------------------------------------------------------
# 加算
# ------------------------------------------------------------
def _counts(m):
    """加算対象なら (day, author_id, chars)、対象外なら None"""
    if m.author.bot or m.channel.id in EXCLUDED_CHANNEL_IDS:
        return None

    roles = getattr(m.author, "roles", ())
    if any(r.id in EXCLUDED_ROLE_IDS for r in roles):
        return None

    text = m.content or ""
    if not (text.strip() or m.attachments or m.stickers):
        return None

    day = m.created_at.astimezone(JST).strftime("%Y-%m-%d")
    return day, m.author.id, len(text)


async def _apply(messages):
    """
    メッセージを集計に加算する。
    チャンネルごとに古い順で渡すこと。ウォーターマーク以下は二重加算防止で無視する。
    対象外のメッセージ(bot・空など)でもウォーターマークは進める。
    """
    global _dirty
    rows: dict = {}

    async with _lock:
        for m in messages:
            cid = m.channel.id
            if m.id <= _wm.get(cid, 0):
                continue
            _wm[cid] = m.id

            r = _counts(m)
            if r:
                day, aid, n = r
                v = rows.setdefault((day, aid), [0, 0])
                v[0] += 1
                v[1] += n

        if rows:
            await asyncio.to_thread(_write_batch, rows)
        _dirty = True


async def ingest_live(message):
    """on_messageから呼ぶ。追いつき中はバッファし、完了後にまとめて加算する。"""
    if message.guild is None:
        return
    if _catching_up:
        if not _disabled:
            _buffer.append(message)
        return
    if message.channel.id in _failed:
        return  # 次回起動時の追いつきで取得される
    await _apply([message])


# ------------------------------------------------------------
# スナップショット(Discordに保存 / から復元)
# ------------------------------------------------------------
async def save_snapshot(bot):
    global _dirty

    # 集計とウォーターマークの整合を保つため、ロック中に書き出す
    async with _lock:
        data = await asyncio.to_thread(_export, dict(_wm))
        _dirty = False

    ch = bot.get_channel(STORE_CHANNEL_ID) or await bot.fetch_channel(STORE_CHANNEL_ID)

    await ch.send(
        content=f"snapshot {datetime.now(JST):%Y-%m-%d %H:%M:%S}",
        file=discord.File(io.BytesIO(data), filename=SNAPSHOT_NAME),
    )

    # 新しいものを送ったあとで古い世代を消す(常に1つ以上残る)
    mine = [
        m
        async for m in ch.history(limit=30)
        if m.author.id == bot.user.id
        and any(a.filename == SNAPSHOT_NAME for a in m.attachments)
    ]
    for old in mine[KEEP_SNAPSHOTS:]:
        try:
            await old.delete()
        except discord.HTTPException as e:
            print(f"[store] 古いスナップショット削除失敗: {e}")


async def load_snapshot(bot) -> bool:
    """最新のスナップショットを読み込む。壊れていれば1つ前へ。なければ False。"""
    ch = bot.get_channel(STORE_CHANNEL_ID) or await bot.fetch_channel(STORE_CHANNEL_ID)

    async for m in ch.history(limit=30):
        if m.author.id != bot.user.id:
            continue
        for a in m.attachments:
            if a.filename != SNAPSHOT_NAME:
                continue
            try:
                payload = json.loads(gzip.decompress(await a.read()))
                if payload.get("version") != 1:
                    continue
                await asyncio.to_thread(_import_rows, payload["daily"])
                _wm.update({int(k): v for k, v in payload["watermarks"].items()})
                print(f"[store] スナップショット読込: {payload['saved_at']}")
                return True
            except Exception as e:
                print(f"[store] スナップショット読込失敗、1つ前を試す: {e}")
    return False


async def snapshot_loop(bot):
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL)
        if _dirty:
            try:
                await save_snapshot(bot)
            except Exception as e:
                print(f"[store] 定期保存失敗: {e}")


# ------------------------------------------------------------
# 追いつき(ウォーターマーク以降だけ取得)
# ------------------------------------------------------------
async def catch_up_channel(channel) -> int:
    last = _wm.get(channel.id)
    after = discord.Object(id=last) if last else None

    total, batch = 0, []
    try:
        async for m in channel.history(limit=None, after=after, oldest_first=True):
            batch.append(m)
            if len(batch) >= 500:
                await _apply(batch)
                total += len(batch)
                batch = []
        if batch:
            await _apply(batch)
            total += len(batch)
    except Exception:
        _failed.add(channel.id)
        raise
    return total


async def catch_up_all(bot, guild, log=None):
    """
    全チャンネルをウォーターマーク以降だけ取得する(起動時 / /update_messages 用)。
    log は async 関数 (text) -> None。省略可。
    途中で止まっても(429中断・キャンセル・例外)、それまでの進捗は保存される。
    """
    global _catching_up, _running

    if _running:
        return None
    _running = True
    _catching_up = True      # 再実行時も、ライブ分を一旦バッファして順序を守る
    _failed.clear()

    async def _log(text):
        print(text)
        if log:
            try:
                await log(text)
            except Exception:
                pass

    targets, done = [], set()
    total, completed = 0, False

    try:
        await _log("🔁 追いつき開始")
        me = guild.me or guild.get_member(bot.user.id)

        for ch in guild.channels:
            if ch.id in EXCLUDED_CHANNEL_IDS:
                continue
            if ch.type in (discord.ChannelType.text, discord.ChannelType.voice):
                targets.append(ch)
            elif ch.type == discord.ChannelType.forum:
                threads = {t.id: t for t in ch.threads}
                try:
                    async for t in ch.archived_threads(limit=None):
                        threads.setdefault(t.id, t)
                except Exception as e:
                    await _log(f"⚠️ {ch.name} のアーカイブスレッド取得失敗: {e}")
                targets.extend(threads.values())

        for ch in targets:
            if not ch.permissions_for(me).read_message_history:
                done.add(ch.id)
                continue
            try:
                total += await catch_up_channel(ch)
                done.add(ch.id)
            except Exception as e:
                await _log(f"⚠️ {ch.name} の処理中にエラー: {e}")
                # 429(Cloudflare制限を含む)なら、追い打ちを避けて全体を中断する
                if isinstance(e, discord.HTTPException) and getattr(e, "status", None) == 429:
                    await _log("🚨 429を検知したため追いつきを中断します")
                    break
        else:
            completed = True

    finally:
        # 未完了のチャンネルはライブ加算を止める(ウォーターマークが飛ぶのを防ぐ)
        for ch in targets:
            if ch.id not in done:
                _failed.add(ch.id)

        _catching_up = False
        buffered = sorted(_buffer, key=lambda m: m.id)
        _buffer.clear()
        try:
            await _apply([m for m in buffered if m.channel.id not in _failed])
            await save_snapshot(bot)
        except Exception as e:
            print(f"[store] 追いつき後の保存でエラー: {e}")
        _running = False

    await _log(
        f"✅ 追いつき完了: {total} 件取得" if completed
        else f"⚠️ 追いつきは途中で終了: {total} 件取得(次回の追いつきで続きから再開)"
    )
    return total
