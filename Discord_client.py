import sys, logging, queue
import asyncio
import discord
from discord.ext import commands

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
    