import sys, logging, queue
import asyncio
import discord
from discord.ext import commands

class Discord_client():
    def __init__(self, main, bot):
        self.bot = bot
        self.logger = logging.getLogger("Discord")
        self.main = main

    async def start(self):
        self.logger.debug("Connecting to Discord...")
        await self.bot.start(self.settings.getSetting('Discordclient', 'token'))

        await asyncio.sleep(2)

class Cg_Cmd(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_member = None

    @commands.command()
    async def pm(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def say(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def shutdown(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def detach(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def attach(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def ping(self, ctx):
        await ctx.send('Pong!')

    @commands.command()
    async def kick(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def ban(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def bans(self, ctx, *, member: discord.Member = None):
        pass
    
    @commands.command()
    async def list(self, ctx, *, member: discord.Member = None):
        pass

    @commands.command()
    async def info(self, ctx, *, member: discord.Member = None):
        pass

if __name__ == '__main__':
    print("Don't start this directly! Start services_start.py")    