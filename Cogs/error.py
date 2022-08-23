from __future__ import annotations
import asyncio

import contextlib
import json
import os
import random
import re
import traceback
from typing import TYPE_CHECKING

import discord
import psutil
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import errors
from Manager.logger import formatColor
from sentry_sdk import capture_exception
from utils.checks import MusicGone, NotVoted
from utils.default import log
from utils.errors import DatabaseError, DisabledCommand

if TYPE_CHECKING:
    from index import Bot


class Error(commands.Cog, name="error"):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.process = psutil.Process(os.getpid())
        with open("blacklist.json") as f:
            self.blacklist = json.load(f)
        self.default_prefix = "tp!"
        self.message_cooldown = commands.CooldownMapping.from_cooldown(
            1.0, random.randint(5, 45), commands.BucketType.user
        )
        self.nword_re = re.compile(
            r"(n|m|и|й)(i|1|l|!|ᴉ|¡)(g|ƃ|6|б)(g|ƃ|6|б)(e|3|з|u)(r|Я)", re.I
        )

        self.errors = (
            NotVoted,
            MusicGone,
            DisabledCommand,
            # commands.HybridCommandError,
            app_commands.MissingPermissions,
            app_commands.BotMissingPermissions,
            errors.BotMissingPermissions,
            errors.MissingPermissions,
            errors.MissingRequiredArgument,
            errors.BadArgument,
            errors.CommandOnCooldown,
            errors.BadUnionArgument,
            errors.NoPrivateMessage,
            errors.NotOwner,
            errors.CommandError,
            errors.ExtensionError,
            discord.HTTPException,
            commands.NoPrivateMessage,
            commands.MissingPermissions,
            commands.BadArgument,
            commands.ChannelNotReadable,
            commands.MaxConcurrencyReached,
            commands.BotMissingPermissions,
            commands.NotOwner,
            commands.TooManyArguments,
            commands.MessageNotFound,
            commands.UserInputError,
            discord.errors.Forbidden,
            discord.HTTPException,
            errors.DisabledCommand,
            commands.BadBoolArgument,
            DatabaseError,
            asyncio.exceptions.TimeoutError,
            commands.GuildNotFound,
        )

        self.dont_catch = (
            commands.CommandNotFound,
            discord.HTTPException,
            discord.errors.NotFound,
            discord.errors.InteractionResponded,
        )

    async def create_embed(self, ctx, error):
        embed = discord.Embed(title="Error", description=error, colour=0xFF0000)
        bucket = self.message_cooldown.get_bucket(ctx.message)
        if retry_after := bucket.update_rate_limit():
            return
        try:
            await ctx.send(embed=embed)
        except Exception as e:
            capture_exception(e)
            await ctx.send(
                f"`{error}`\n***Enable embed permissions please.***",
            )

    def tracebackfunc(self, ctx):
        public = True

        def paginate(text: str):
            """Simple generator that paginates text."""
            last = 0
            pages = []
            for curr in range(len(text)):
                if curr % 1980 == 0:
                    pages.append(text[last:curr])
                    last = curr
                    appd_index = curr
            if appd_index != len(text) - 1:
                pages.append(text[last:curr])
            return list(filter(lambda a: a != "", pages))

        destination = ctx.channel if public else ctx.author
        for page in paginate(ctx.bot.traceback):
            embed = discord.Embed(
                title="Error Traceback", description=f"```py\n{page}```"
            )
            return embed

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, self.dont_catch):
            return
        elif isinstance(error, self.errors):
            await self.create_embed(ctx, error)
            return
        # if error not in self.errors:
        self.bot.traceback = (
            f"Exception in command '{ctx.command.qualified_name}'\n"
            + "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        )
        bruh = await self.bot.fetch_channel(1008520820332695582)
        caller = self.tracebackfunc(ctx)
        await bruh.send(embed=caller)

        if isinstance(error, commands.MissingRequiredArgument):
            bucket = self.message_cooldown.get_bucket(ctx.message)
            retry_after = bucket.update_rate_limit()
            embed = discord.Embed(
                title="Hey now...",
                color=16711680,
                description=f"You're missing a required argument.\ntry again by doing `{ctx.command.signature}`\nif you still don't understand, type `{ctx.prefix}help {ctx.command}`",
            )

            embed.set_thumbnail(url=ctx.author.avatar)
            if retry_after:
                return
            else:
                await ctx.send(embed=embed)

        elif isinstance(error, app_commands.BotMissingPermissions):
            bucket = self.message_cooldown.get_bucket(ctx.message)
            retry_after = bucket.update_rate_limit()
            embed = discord.Embed(
                title="Hey now...",
                color=16711680,
                description=f"I'm missing permissions.\nPlease enable the following permissions:\n{error.missing_permissions}",
            )
            embed.set_thumbnail(url=ctx.author.avatar)
            if retry_after:
                return
            else:
                await ctx.send(embed=embed)
        elif isinstance(error, ValueError):
            bucket = self.message_cooldown.get_bucket(ctx.message)
            retry_after = bucket.update_rate_limit()
            embed = discord.Embed(
                title="Hey now...",
                color=16711680,
                description=f"This command requires a number as an argument.\nTry again by doing `{ctx.command.signature}`\nif you still don't understand, type `{ctx.prefix}help {ctx.command}`",
            )

            embed.set_thumbnail(url=self.bot.user.avatar)
            bucket = self.message_cooldown.get_bucket(ctx.message)
            if retry_after := bucket.update_rate_limit():
                return
            try:
                await ctx.send(embed=embed)
            except discord.errors.Forbidden:
                await ctx.send(f"`{error}`\n***Enable embed permissions please.***")
                return
        elif isinstance(error, commands.CommandOnCooldown):
            bucket = self.message_cooldown.get_bucket(ctx.message)
            retry_after = bucket.update_rate_limit()
            log(
                f"{formatColor(ctx.author.name, 'gray')} tried to use {ctx.command.name} but it was on cooldown for {error.retry_after:.2f} seconds."
            )

            day = round(error.retry_after / 86400)
            hour = round(error.retry_after / 3600)
            minute = round(error.retry_after / 60)
            if retry_after:
                return
            if day > 0:
                await ctx.send(f"This command has a cooldown for {str(day)}day(s)")
            elif hour > 0:
                await ctx.send(f"This command has a cooldown for {str(hour)} hour(s)")
            elif minute > 0:
                await ctx.send(
                    f"This command has a cooldown for {str(minute)} minute(s)"
                )
            else:
                await ctx.send(
                    f"This command has a cooldown for {error.retry_after:.2f} second(s)"
                )

                return
        elif isinstance(error, commands.NSFWChannelRequired):
            embed = discord.Embed(
                title="Error",
                description="This command is for NSFW channels only!",
                colour=16711680,
                timestamp=ctx.message.created_at,
            )

            embed.set_image(url="https://i.hep.gg/hdlOo67BI.gif")
            embed.set_thumbnail(url=ctx.message.author.avatar)
            embed.set_author(
                name=ctx.message.author.name, icon_url=ctx.message.author.avatar
            )

            bucket = self.message_cooldown.get_bucket(ctx.message)
            if retry_after := bucket.update_rate_limit():
                return
            try:
                await ctx.send(embed=embed)
            except discord.errors.Forbidden:
                await ctx.send()
                return
        elif isinstance(error, commands.CheckFailure):
            me1 = self.bot.get_user(101118549958877184)
            me2 = self.bot.get_user(683530527239962627)
            blacklisted_user = await self.bot.db.fetch_blacklist(ctx.author.id)
            if blacklisted_user and blacklisted_user.is_blacklisted:
                embed = discord.Embed(
                    title="Error", colour=16711680, timestamp=ctx.message.created_at
                )

                embed.add_field(name="Author", value=ctx.message.author.mention)
                embed.add_field(
                    name="Error",
                    value=f"You've been blacklisted from using this bot for the following reason\n`{blacklisted_user.reason}`\nTo get the blacklist removed, send us an email - `contact@lunardev.group` or contact the owners directly - {me1}, {me2}",
                )

                embed.set_thumbnail(url=ctx.message.author.avatar)
                embed.set_footer(
                    text="If you believe this is a mistake, contact the bot owner or the server owner."
                )

                embed.set_author(
                    name=ctx.message.author.name, icon_url=ctx.message.author.avatar
                )

                bucket = self.message_cooldown.get_bucket(ctx.message)
                if retry_after := bucket.update_rate_limit():
                    return
                with contextlib.suppress(Exception):
                    await ctx.message.add_reaction("\u274C")
                try:
                    await ctx.send(embed=embed)
                except discord.errors.Forbidden:
                    await ctx.send(
                        f"You don't have permission to run this command.\n***Enable embed permissions please.***"
                    )

                    with contextlib.suppress(Exception):
                        await ctx.message.add_reaction("\u274C")
                    return
            elif self.nword_re.search(ctx.message.content.lower()):
                await me1.send(
                    f"{ctx.author} is trying to get AGB to say racist things"
                )
                await me2.send(
                    f"{ctx.author} is trying to get AGB to say racist things"
                )
                return
            else:
                embed = discord.Embed(
                    title="Error", colour=16711680, timestamp=ctx.message.created_at
                )

                embed.add_field(name="Author", value=ctx.message.author.mention)
                embed.add_field(
                    name="Error", value="You don't have permission to run this command."
                )

                embed.set_thumbnail(url=ctx.message.author.avatar)
                embed.set_footer(
                    text="If you believe this is a mistake, contact the bot owner or the server owner."
                )

                embed.set_author(
                    name=ctx.message.author.name, icon_url=ctx.message.author.avatar
                )

                bucket = self.message_cooldown.get_bucket(ctx.message)
                if retry_after := bucket.update_rate_limit():
                    return
                try:
                    await ctx.send(embed=embed)
                except Exception as e:
                    capture_exception(e)
                    await ctx.send("You don't have permission to run this command.")
                    return
            return
        bucket = self.message_cooldown.get_bucket(ctx.message)
        if retry_after := bucket.update_rate_limit():
            return

        # else:
        #     capture_exception(error)
        #     eventId = sentry_sdk.last_event_id()
        #     errorResEmbed = discord.Embed(
        #         title=f"❌ Error!",
        #         colour=colors.red,
        #         description=f"*An unknown error occurred!*\n\n**Join the server with your Error ID for support: {config.Server}.**",
        #     )
        #     errorResEmbed.set_footer(text="This error has been automatically logged.")
        #     await ctx.send(content=f"**Error ID:** `{eventId}`", embed=errorResEmbed)
        #     # await ctx.send(
        #     #     f"An error has occured. The error has automatically been reported and logged. Please wait until the developers work on a fix.\nJoin the support server for updates: {config.Server}",
        #     # )
        #     bug_channel = self.bot.get_channel(791265212429762561)

        #     embed = discord.Embed(
        #         title=f"New Bug Submitted By {ctx.author.name}.",
        #         color=colors.red,
        #     )
        #     embed.add_field(name="Error", value=f"Bug ID: `{eventId}`")
        #     embed.add_field(name="Command", value=ctx.command.name)
        #     # check if the error was raised in DMS
        #     if ctx.guild is None:
        #         embed.set_footer(text="Error raised in DMS")
        #     else:
        #         embed.set_footer(
        #             text=f"User *({ctx.author.id})* in {ctx.channel.id} {ctx.message.id}",
        #             icon_url=ctx.author.avatar,
        #         )
        #     # check if the error is already being handled in self.errors list

        #     if error in self.errors:
        #         return
        #     else:
        #         await bug_channel.send(embed=embed)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Error(bot))
