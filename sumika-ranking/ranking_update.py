import discord
from discord.ext import commands

EXCLUDED_ROLE = [
    1473498996159942812,
]

EXEMPT_CHANNELS = [
    1276087091280871546,
    1399620581766463639,
]


class Update(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    def is_exempt(
        self,
        member: discord.Member,
        channel: discord.abc.GuildChannel,
    ):
        return (
            channel.id in EXEMPT_CHANNELS
            or any(role.id in EXCLUDED_ROLE for role in member.roles)
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        # Bot・DMは無視
        if message.author.bot or message.guild is None:
            return

        member = message.guild.get_member(message.author.id)

        if member is None:
            return

        # コマンドは保存しない
        ctx = await self.bot.get_context(message)

        if ctx.command is not None:
            return

        # 除外対象
        if self.is_exempt(member, message.channel):
            return

        try:
            await self.bot.db_queue.put(message)

        except Exception as e:

            log_channel = self.bot.get_channel(
                1276087091280871546
            )

            if log_channel is not None:
                await self.bot.api_queue.put(
                    log_channel.send(
                        f"❌ on_message 保存エラー\n```{e}```"
                    )
                )


async def setup(bot):
    await bot.add_cog(Update(bot))
