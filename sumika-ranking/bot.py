import discord
from discord.ext import commands
import asyncio

from log_control import api_worker
from config import APP_ID, LOG_CHANNEL_ID, GUILD_ID

import message_count
import stats_store

# Bot設定
intents = discord.Intents.all()


class RANK(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ログ送信用(send_log が使う)
        self.api_queue = asyncio.Queue()
        # 起動時の追いつきタスク(/stop_scan で止められるように保持)
        self.scan_task = None

    async def setup_hook(self):

        # 作業用DBを作り直す(永続データはDiscord上のスナップショットが正)
        if not hasattr(self, "_store_ready"):
            stats_store.init_store()
            self._store_ready = True

        if not hasattr(self, "_api_worker_started"):
            self.api_worker_task = asyncio.create_task(api_worker(self))
            self._api_worker_started = True

        if not self.extensions.get("ranking_update"):
            await self.load_extension("ranking_update")
            print("ranking_update loaded")

        # tree.sync() は起動のたびに実行しない(リクエスト削減)。
        # コマンドを追加・変更したときだけ、管理者が !sync を実行する。

        print(self.cogs)

    async def on_ready(self):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        print("✅ on_ready 開始")

        channel = self.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send("🔧 初期化開始")

        guild = self.get_guild(GUILD_ID)

        # 保存済みスナップショットを読み込む(なければ初回=全件取得になる)
        try:
            loaded = await stats_store.load_snapshot(self)
        except Exception as e:
            # 保存先が使えない状態で追いつくと、毎回全件取得になり429の原因になる。
            stats_store.disable()
            msg = (
                "❌ STORE_CHANNEL_ID のチャンネルにアクセスできません。"
                f"集計を停止しました: {e}"
            )
            print(msg)
            if channel:
                await channel.send(msg)
            return

        if channel:
            await channel.send(
                "📦 スナップショットを読み込みました。差分のみ取得します。"
                if loaded
                else "📦 スナップショットなし。初回の全件取得を行います。"
            )

        asyncio.create_task(stats_store.snapshot_loop(self))
        self.scan_task = asyncio.create_task(
            stats_store.catch_up_all(
                self, guild, log=lambda t: message_count.send_log(self, t)
            )
        )

        if channel:
            await channel.send(f"🎉 {self.user} 起動完了")


# コマンド実行時のキーの決定
bot = RANK(command_prefix="!", intents=intents, application_id=APP_ID)
# helpコマンド独自実装のため規定コマンドを削除
bot.remove_command("help")
