import discord
from discord.ext import commands
import asyncio
from message_count import save_message_to_db
from log_control.py import api_queue

EXCLUDED_ROLE = [1376867886525714464,1398231916171493480]
EXEMPT_CHANNELS = [1276087091280871546, 1399620581766463639]  # 除外チャンネルID

class update(commands.Cog):

    def __init__(self,bot):
        self.bot=bot


    def is_exempt(self, member: discord.Member,
                  channel: discord.TextChannel):  #無敵のロールを持っているかどうか
        return (channel.id in EXEMPT_CHANNELS
                or any(role.id in EXCLUDED_ROLE for role in member.roles))
  
    @commands.Cog.listener()  #メッセージが送信されたとき
    async def on_message(self, message):  #メッセージが送信されたとき

        if message.author.bot:
            return
        print(f"🟡 on_message 発火: {message.content}")
        
        # メッセージの送信者とチャンネルを取得
        if message.guild is None:
        
            return  # DMなら無視

        member = message.guild.get_member(message.author.id)
        if member is None: 
            return  # サーバーにいないユーザーなら無視

        if message.author.bot:
            return

        ctx = await self.bot.get_context(message)
        if ctx.command is not None:
            return
        
        channel = message.channel

          #ランキング処理
        try:
            await db_queue.put(save_message_to_db(message))
        except Exception as e:
            channel= self.bot.get_channel(1276087091280871546)
            await api_queue.put(channel.send(f"on_message 保存エラー: {e}"))

async def setup(bot):
    await bot.add_cog(update(bot))
