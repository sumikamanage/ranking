import discord
from discord.ext import commands
import asyncio

from log_control import api_worker,db_worker,api_queue,db_queue
from config import APP_ID, LOG_CHANNEL_ID

from message_count import init_db
# Bot設定
intents = discord.Intents.all()

class RANK(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.api_queue = asyncio.Queue()
        self.db_queue = asyncio.Queue()

    async def setup_hook(self):



        # --- APIキュー ---
        if not hasattr(self, "_api_worker_started"):
            self.api_worker_task = asyncio.create_task(api_worker())
            self._api_worker_started = True

    
        # --- DBキュー---
        if not hasattr(self, "_db_worker_started"):
            self.db_worker_task = asyncio.create_task(db_worker())
            self._db_worker_started = True

        # --- 拡張 ---
        if not self.extensions.get("ranking_update"):
            await self.load_extension("ranking_update")    

    async def on_ready(self):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True

        await asyncio.sleep(30)  # ← 重要：Gateway安定待ち
        print("✅ on_ready 開始")

        channel = self.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send("🔧 初期化開始")


        if channel:
            await channel.send(f"🎉 {self.user} 起動完了")

 

#コマンド実行時のキーの決定
bot = RANK(command_prefix="&", intents=intents,application_id = APP_ID)
#helpコマンド独自実装のため規定コマンドを削除
bot.remove_command("help")
