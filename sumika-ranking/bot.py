import discord
from discord.ext import commands
import asyncio


from config import APP_ID, LOG_CHANNEL_ID

from bot_core.start.start_log import send_startup_log

from message_count import init_db
# Bot設定
intents = discord.Intents.all()


from log_control import api_worker

from log_control import db_queue, db_worker

class RANK(commands.Bot):

    async def setup_hook(self):
        # --- 拡張 ---
        if not self.extensions.get("Automod"):
            await self.load_extension("Automod")

        # --- APIキュー ---
        if not hasattr(self, "_api_worker_started"):
            self.api_worker_task = asyncio.create_task(api_worker())
            self._api_worker_started = True

    
        # --- DBキュー---
        if not hasattr(self, "_db_worker_started"):
            self.db_worker_task = asyncio.create_task(db_worker())
            self._db_worker_started = True

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
