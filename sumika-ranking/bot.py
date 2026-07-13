import discord
from discord.ext import commands
import asyncio
from message_count import full_scan,init_db
from log_control import api_worker,db_worker,history_worker
from config import APP_ID, LOG_CHANNEL_ID,DB_PATH,GUILD_ID

import message_count
# Bot設定
intents = discord.Intents.all()

class RANK(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.api_queue = asyncio.Queue()
        self.history_queue = asyncio.Queue()
        self.db_queue = asyncio.Queue()

    async def setup_hook(self):

        if not hasattr(self, "_api_worker_started"):
            self.api_worker_task = asyncio.create_task(api_worker(self))
            self._api_worker_started = True

        if not hasattr(self, "_history_worker_started"):
            self.history_worker_task = asyncio.create_task(history_worker(self))
            self._history_worker_started = True
        
        if not hasattr(self, "_db_worker_started"):
            self.db_worker_task = asyncio.create_task(db_worker(self))
            self._db_worker_started = True

        
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
        await bot.tree.sync()
#        init_db() 
        guild = bot.get_guild(GUILD_ID)
        db_path = DB_PATH
        #フルスキャンを開始
        ctx = bot.get_channel(1276087091280871546)
        if message_count.is_updating:
            return 
        if message_count.is_scanning:
            return 
        asyncio.create_task(full_scan(bot,guild))
        
        if channel:
            await channel.send(f"🎉 {self.user} 起動完了")

 

#コマンド実行時のキーの決定
bot = RANK(intents=intents,application_id = APP_ID)
#helpコマンド独自実装のため規定コマンドを削除
bot.remove_command("help")
