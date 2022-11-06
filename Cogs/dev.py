from __future__ import annotations

import datetime
import random
from io import BytesIO
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord import Member
from discord.ext import commands, tasks
from lunarapi import Client, endpoints

from index import config
from utils import imports, permissions
from utils.default import log
from utils.embeds import EmbedMaker as Embed

if TYPE_CHECKING:
    from index import AGB

OS = discord.Object(id=975810661709922334)


class MemberConverter(commands.MemberConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except commands.BadArgument as e:
            members = [
                member for member in ctx.guild.members if member.display_name.lower().startswith(argument.lower())
            ]
            if len(members) == 1:
                return members[0]
            raise commands.BadArgument(f"{len(members)} members found, please be more specific.") from e


class Dev(commands.Cog, name="dev"):
    """Developer only testing"""

    def __init__(self, bot: AGB):
        """Developer only testing"""
        self.bot: AGB = bot
        self.config = imports.get("config.json")

    async def cog_unload(self):
        self.testtime.stop()

    @commands.hybrid_group(name="dev")
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def dev(self, ctx: commands.Context):
        """Owner-only commands."""
        await ctx.send("Owner-only commands.", ephemeral=True, delete_after=10)

    @dev.command(name="welcome")
    @commands.check(permissions.is_owner)
    async def welcome(self, ctx, *, user: Member):
        async with aiohttp.ClientSession() as session:
            client = Client(
                session=session,
                token=config.lunarapi.token,
            )
            image = await client.request(
                endpoints.generate_welcome,
                avatar=user.avatar.url,
                username=user.name,
                members=f"{ctx.guild.member_count}",
            )
            byts = BytesIO(await image.bytes())
            file = discord.File(byts, f"{user.id}.png")

            print(dir(image))
            embed = Embed(title="welcome")
            embed.set_image(url=f"attachment://{user.id}.png")
            await ctx.send(embed=embed, file=file)

    @dev.command(name="htest")
    @commands.check(permissions.is_owner)
    async def htest(self, ctx):
        async def get_img() -> str:
            cats = ["neko", "jpg"]
            async with aiohttp.ClientSession() as s:
                client = Client(session=s, token=config.lunarapi.token)
                img = await client.request(endpoints.nsfw(random.choice(cats)))
                return img

        for _ in range(5):
            x = await get_img()
            print(await x.to_dict())

    @dev.command()
    @commands.check(permissions.is_owner)
    async def btest(self, ctx, *, user: Member, days: int = None):
        db_user = await self.bot.db.fetch_blacklist(user.id)

        if not db_user or db_user is None:
            await self.bot.db.add_temp_blacklist(user.id, blacklisted=True, days=days)
            await Embed(
                title="Temporary Blacklist",
                description=f"{user.id} was not in the database!\nThey have been added and blacklisted for {days} days.",
            )
        else:
            # await self.bot.db.update_temp_blacklist(
            #     user.id, blacklisted=True, days=days
            # ) # Exchanged for modify, leaving it for archival and reverting purposes

            await db_user.modify(blacklisted=True, blacklistedtill=days)
            await Embed(
                title="Temporary Blacklist",
                description=f"{user.id} has been blacklisted for {days} days.",
            ).send(ctx)
        try:
            await user.send(
                (
                    "You have been temporarily blacklisted from using the bot.\n\n"
                    f"This blacklist lasts for {days} days unless you can email us a good reason "
                    "why you should be whitelisted - `contact@lunardev.group`"
                )
            )
            await Embed(
                title="Blacklist DM",
                description="The user has been notified of their blacklist.",
            ).send(ctx)
        except discord.Forbidden:
            await Embed(
                title="Blacklist DM",
                description="I was unable to DM the user, they have still been blacklisted.",
            ).send(ctx)

    @tasks.loop(time=[datetime.time(minute=h) for h in range(60)])
    async def testtime(self):
        log("5 minute task ran")
        # bruh = await self.bot.fetch_channel(976866146391306260)
        # await bruh.send("Sent every 5 minutes on the minute. This is a test, please ignore.")


async def setup(bot: AGB) -> None:
    await bot.add_cog(Dev(bot))
