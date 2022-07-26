from __future__ import annotations

import asyncio
import concurrent
import contextlib
import datetime
import importlib
import inspect
import io
import os
import pathlib
import random
import re
import shlex
import subprocess
import textwrap
import time
import traceback
from contextlib import redirect_stdout, suppress
from io import BytesIO
from subprocess import check_output
from typing import TYPE_CHECKING, Any, Literal, Optional

import aiohttp
import discord
import httpx
import speedtest
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from lunarapi import Client, endpoints
from sentry_sdk import capture_exception


from index import colors, config, delay
from Manager.database import Connection, Table
from Manager.logger import formatColor
from utils import default, imports, permissions
from utils.default import log
from utils.embeds import EmbedMaker as Embed
from utils.errors import BlacklistedUser
from utils.flags import BlacklistUserArguments

from .Utils import random

OS = discord.Object(id=975810661709922334)

if TYPE_CHECKING:
    from index import AGB


class EvalContext:
    def __init__(self, interaction):
        self.interaction = interaction
        self.message = interaction.message
        self.bot = interaction.client
        self.author = interaction.user
        self.config = imports.get("config.json")

    async def send(self, *args, **kwargs):
        await self.interaction.followup.send(*args, **kwargs)


class EvalModal(discord.ui.Modal, title="Evaluate Code"):
    body = discord.ui.TextInput(label="Code", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        start = time.time()

        startTime = datetime.datetime.now()

        ectx = EvalContext(interaction)

        env = {
            "ctx": ectx,
            "interaction": interaction,
            "bot": interaction.client,
            "channel": interaction.channel,
            "author": interaction.user,
            "guild": interaction.guild,
            "message": interaction.message,
            "source": inspect.getsource,
        }

        body = str(self.body)

        env.update(globals())

        stdout = io.StringIO()

        await interaction.followup.send(f"**Code:**\n```py\n{body}```")

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        async def paginate_send(ctx, text: str):
            """Paginates arbatrary length text & sends."""

            last = 0
            pages = []
            for curr in range(0, len(text), 1980):
                pages.append(text[last:curr])
                last = curr
            pages.append(text[last:])
            pages = list(filter(lambda a: a != "", pages))
            for page in pages:
                await ctx.send(f"```py\n{page}```")

        try:
            exec(to_compile, env)
            datetime.datetime.now() - startTime
            end = time.time()
            end - start
        except Exception as e:
            await paginate_send(ectx, f"{e.__class__.__name__}: {e}")
            return await interaction.message.add_reaction("\u2049")  # x

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await paginate_send(ectx, f"{value}{traceback.format_exc()}")
            return await interaction.message.add_reaction("\u2049")  # x
        value = stdout.getvalue()
        if ret is None:
            if value:
                await paginate_send(ectx, str(value))
        else:
            await paginate_send(ectx, f"{value}{ret}")


class EvalView(discord.ui.View):
    def __init__(self, author: int, *args, **kwargs):
        self.modal = EvalModal()
        self.author = author
        super().__init__(timeout=120)

    @discord.ui.button(
        label="Click Here",
        style=discord.ButtonStyle.blurple,
        custom_id="AGBEvalCustomID",
    )
    async def click_here(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.author != interaction.user.id:
            return await interaction.response.send_message("You can't do this!", ephemeral=True)
        await interaction.response.send_modal(self.modal)


class InteractiveMenu(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=30)
        self.ctx = ctx

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.errors.NotFound:
            return

    @discord.ui.button(label="Report to Developers", style=discord.ButtonStyle.blurple)
    async def report(self, i, b: discord.ui.Button):
        guild = await i.client.fetch_guild(975810661709922334)
        bruh = await guild.fetch_channel(990187200656322601)
        # get the embeds image url
        await bruh.send(f"{i.message.embeds[0].image.url}")
        # disable the button once its been used
        await i.response.send_message("Report sent successfully", ephemeral=True)
        b.disabled = True
        await i.message.edit(view=self)

    @discord.ui.button(emoji="❌", style=discord.ButtonStyle.blurple)
    async def close(self, i, b: discord.ui.Button):
        await i.message.delete()

    async def interaction_check(self, interaction):
        if interaction.user == self.ctx.author:
            return True
        await interaction.response.send_message("Not your command", ephemeral=True)


class Admin(commands.Cog, name="admin", command_attrs={}):
    """Commands that arent for you lol"""

    def __init__(self, bot: AGB) -> None:
        self.bot: AGB = bot
        self.config = imports.get("config.json")
        os.environ.setdefault("JISHAKU_HIDE", "1")
        self._last_result = None
        self.last_change = None
        self.tax_rate = 0
        self.tax_collector = None
        self.lunar_headers = {f"{self.config.lunarapi.header}": f"{self.config.lunarapi.token}"}
        self.yes_responses = {
            "yes": True,
            "yea": True,
            "y": True,
            "ye": True,
            "no": False,
            "n": False,
            "na": False,
            "naw": False,
            "nah": False,
        }
        self.email_re = r"^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$"
        self.blacklisted = False

        bot.add_check(self.blacklist_check)
        self.nword_re = r"\b(n|m|и|й){1,32}(i|1|l|!|ᴉ|¡){1,32}((g|ƃ|6|б{2,32}|q){1,32}|[gqgƃ6б]{2,32})(a|e|3|з|u)(r|Я|s|5|$){1,32}\b"
        self.nword_re_comp = re.compile(self.nword_re, re.IGNORECASE | re.UNICODE)
        self.afks = {}

        self.CONTAINERS = {
            "AGB": "f3624f10a30fad7d2b98914dd47a5035ab66dc9cbae8347b50937a232ae0b8b6",
            "PgAdmin": "3f4c0f8fcaf6cd557c4a5fe23c0ecd214fa37eeeaee24f16433397a5aa7cca17",
            "Status Page": "5f2c8d1b1b8e7909bae2024586c67bc0693585d0faf12845beff62fbc7a6ed9e",
            "Minecraft Server": "62c60c804abff8443d02b471a15e8b9e31236e6fded5b79842ed5269b94b1953",
            "Website": "7655ad002f43a9f268cd3bc38c8c2b2d49d30ab9fc36b620eecd84918d829a0d",
        }

        self.errors = (
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
            commands.BadBoolArgument,
        )

    async def get_or_fetch_user(self, user_id: int):
        user = await self.get_or_fetch_user(user_id)
        if user is None:
            user = await self.bot.fetch_user(user_id)

    async def remove_images(self, rmcode: str) -> None:
        payload = {"password": self.config.lunarapi.adminPass, "rmcode": rmcode}
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.config.lunarapi.token}"}
        ) as session, session.post("https://api.lunardev.group/admin/apirm", json=payload) as resp:
            if resp.status == 200:
                return

    async def blacklist_check(self, ctx: commands.Context):
        bl = await self.bot.db.fetch_blacklist(ctx.author.id)
        if bl and bl.is_blacklisted:
            raise BlacklistedUser(
                obj=bl,
                user=ctx.author,
            )

        return True

    async def run_process(self, command):
        try:
            process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await process.communicate()
        except NotImplementedError:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            result = await self.bot.loop.run_in_executor(None, process.communicate)
        return [output.decode() for output in result]

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])
        return content.strip("` \n")

    async def try_to_send_msg_in_a_channel(self, guild, msg):
        for channel in guild.channels:
            with suppress(Exception):
                await channel.send(msg)
                break

    async def add_fail_reaction(self):
        emoji = "❌"
        with suppress(Exception):
            await self.add_reaction(emoji)

    async def add_success_reaction(self):
        emoji = "✅"
        with suppress(Exception):
            await self.add_reaction(emoji)

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

    async def get_or_remove_users_from_database(
        self,
        action: Literal["GET", "REMOVE"],
        user_ids: Optional[list[int]] = None,
        /,
        *,
        exclude: Optional[list[Table]] = None,
    ) -> Optional[list[int]]:
        if user_ids is None:
            user_ids = []
        if exclude is None:
            exclude = []
        remove_from = [
            Table.BADGES,
            Table.BLACKLIST,
            # Table.REMINDERS,
            Table.USERECO,
            Table.USERS,
        ]
        entries: list[int] = []
        for table in remove_from:
            if table in exclude:
                continue
            user_id_key, cache = self.bot.db._table_to_cache[table]
            if action == "GET":
                query = f"SELECT {user_id_key} FROM {table}"
                res = await self.bot.db.fetch(query)
                entries.extend(int(entry[user_id_key]) for entry in res)
            elif action == "REMOVE":
                for user_id in user_ids:
                    cache.pop(int(user_id), None)

                query = f"DELETE FROM {table} WHERE {user_id_key} = $1"
                await self.bot.db.executemany(
                    query,
                    table,
                    user_id_key,
                    *[tuple(str(user_id)) for user_id in user_ids],
                )

        if action == "GET":
            return entries

    @commands.hybrid_group(name="owner")
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def owner(self, ctx: commands.Context):
        """Owner-only commands."""
        await ctx.send("Owner-only commands.", ephemeral=True)

    @commands.hybrid_command()
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def checkdbusers(self, ctx: commands.Context, view: bool = False):
        """
        Check the database for users and remove them if they don't share a server with the bot

        If `view` is set to `True`, it will only show the users that are missing, not remove them.
        Default is `False`.
        """
        await ctx.typing()
        # type: ignore
        db_users: list[int] = await self.get_or_remove_users_from_database("GET")
        set_db_users = set(db_users)
        set_discord_users = {x.id for x in self.bot.users}
        extra_users = list(set_db_users - set_discord_users)
        if view:
            await ctx.send(
                (
                    f"Unqiue users in the database: {len(set_db_users)}\n"
                    f"Unique users for the bot: {len(set_discord_users)}\n"
                    f"{len(extra_users)} users are in the database but not sharing a server with the bot.\n"
                    "set `view` to False to remove them from the database."
                )
            )
            return

        msg = await ctx.send(
            f"{ctx.author.mention}, found {len(extra_users)} extra users in the database.... removing..."
        )
        try:
            await self.get_or_remove_users_from_database("REMOVE", extra_users)
        except Exception as e:
            await msg.reply(f"Error: {e}")
            return

        await msg.reply("Done! ✅")

    # @commands.Cog.listener(name="on_message")
    # async def AutoBanNWord(self, message):
    #     if message.guild is None:
    #         return
    #     if message.author == self.bot.user:
    #         return
    #     if message.author.bot:
    #         return
    #     if message.guild.id == 755722576445046806 and self.nword_re_comp.search(message.content.lower()):
    #         if message.author.id in self.config.owners:
    #             return await message.channel.send("Racist...", delete_after=5)
    #         if message.content.lower() == "snigger":
    #             return await message.channel.send(
    #                 f"{message.author.mention} be careful what you say, `snigger` is really close to a blacklisted word.",
    #                 delete_after=5,
    #             )
    #         reason = "[AutoBan] Racism / Hard R"
    #         me = await self.get_or_fetch_user(101118549958877184)
    #         other = self.bot.get_channel(755722577485365370)
    #         try:
    #             await message.author.send(
    #                 f"You have been banned from {message.guild.name} because you said this: {message.content}"
    #             )
    #         except Exception as e:
    #             capture_exception(e)
    #         try:
    #             await message.author.guild.ban(user=message.author, reason=reason)
    #         except Exception as e:
    #             await me.send(
    #                 f"I could not ban {message.author.name} / {message.author.id} for racism, please go look into this."
    #             )
    #             capture_exception(e)
    #             return
    #         logger.warning(f"{message.author} has been banned from {message.guild.name} for being a racist.")
    #         try:
    #             await message.channel.send(
    #                 f"**{message.author}** has been banned from {message.guild.name} for being a racist."
    #             )
    #         except Exception as e:
    #             capture_exception(e)
    #         await me.send(
    #             f"{message.author.name} was just banned in {message.guild.name}\n**Message Content**{message.content}"
    #         )
    #         await other.send(f"{message.author.name} was just banned from this server for being racist {me.mention}.")

    # @commands.Cog.listener(name="on_message")
    # async def AutoBanNWord_ForAous_Server(self, message):
    #     if message.guild is None:
    #         return
    #     if message.author == self.bot.user:
    #         return
    #     if message.author.bot:
    #         return
    #     aou_guild = self.bot.get_guild(707211170897068032)
    #     if not aou_guild:
    #         return

    #     if message.guild.id == aou_guild.id:
    #         if message.content.lower() == "snigger":
    #             return
    #         if self.nword_re_comp.search(message.content.lower()):
    #             if message.author.id in self.config.owners:
    #                 return await message.channel.send("Racist...", delete_after=5)
    #             reason = "[AutoBan] Racism / Hard R"
    #             aou = await self.get_or_fetch_user(516551416064770059)
    #             other = self.bot.get_channel(911585809986101278)
    #             try:
    #                 await message.author.send(
    #                     f"You have been banned from {message.guild.name} because you said this: {message.content}"
    #                 )
    #             except Exception as e:
    #                 capture_exception(e)
    #             try:
    #                 await message.author.guild.ban(user=message.author, reason=reason)
    #             except Exception as e:
    #                 capture_exception(e)
    #                 await aou.send(
    #                     f"I could not ban {message.author.name} / {message.author.id} for racism, please go look into this."
    #                 )
    #                 return
    #             logger.warning(
    #                 f"{message.author} has been banned from {message.guild.name} / {message.guild.id} for being a racist."
    #             )
    #             try:
    #                 await message.channel.send(
    #                     f"**{message.author}** has been banned from {message.guild.name} for being a racist."
    #                 )
    #             except Exception as e:
    #                 capture_exception(e)
    #             await aou.send(
    #                 f"{message.author} was just banned in {message.guild.name}(Your Server)\n**Message Content**{message.content}"
    #             )
    #             await other.send(
    #                 f"{message.author} was just banned from this server for being racist.\nEveryone shame them!!"
    #             )

    # @commands.Cog.listener(name="on_message")
    # async def AutoBanNWord_ForMMFac_server(self, message):
    #     if message.guild is None:
    #         return
    #     if message.author == self.bot.user:
    #         return
    #     if message.author.bot:
    #         return
    #     fac_guild = self.bot.get_guild(974738558210420827)
    #     if not fac_guild:
    #         return
    #     if message.guild.id == fac_guild.id:
    #         if message.content.lower() == "snigger":
    #             return
    #         if self.nword_re_comp.search(message.content.lower()):
    #             if message.author.id in self.config.owners:
    #                 return await message.channel.send("Racist...", delete_after=5)
    #             other = self.bot.get_channel(974738559170936863)
    #             await message.delete()
    #             await message.channel.send(
    #                 f"{message.author.mention} **Racism is not allowed here.**",
    #                 delete_after=5,
    #             )
    #             await other.send(
    #                 f"{message.author} / {message.author.id} is a racist. Here is what they said:\n{message.content}"
    #             )
    #             # time the user out for an hour using date time
    #             user = message.author
    #             await user.timeout(datetime.timedelta(hours=1), reason="Racism")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if self.nword_re_comp.search(guild.name.lower()):
            await self.try_to_send_msg_in_a_channel(guild, "im gonna leave cuz of the server name")
            return await guild.leave()
        for channel in guild.channels:
            if self.nword_re_comp.search(guild.name.lower()):
                await self.try_to_send_msg_in_a_channel(
                    guild, f"im gonna leave cuz of the channel name {channel.mention}"
                )
                log(f"{guild.name} / {guild.id} is a racist server.")
                return await guild.leave()

    @commands.Cog.listener(name="on_member_join")
    async def CustomizedJoinEventForGuilds(self, member: discord.Member, guild=None):
        return
        guild = member.guild
        channel = ""  # insert db shit here owo
        embed = Embed()
        async with aiohttp.ClientSession() as session:
            client = Client(
                session=session,
                token=config.lunarapi.token,
            )
            image = await client.request(
                endpoints.generate_welcome,
                avatar=member.avatar.url,
                username=member.name,
                members=f"{guild.member_count}",
            )
            byts = BytesIO(await image.bytes())
            file = discord.File(byts, f"{member.id}.png")
            embed.set_image(url=f"attachment://{member.id}.png")
        embed.add_field(
            name=f"Welcome {member}",
            # value="", # more db stuff
        )
        embed.set_thumbnail(url=member.avatar)
        await channel.send(embed=embed, file=file)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member, guild=None):
        guild = member.guild
        if member.guild.id == 755722576445046806:
            if member.bot:
                return
            channel = self.bot.get_channel(755722577049026567)
            await channel.send(
                f"{member.name} left. Guild member count: {guild.member_count}",
                delete_after=5,
            )

    ###
    #
    # Attempted AFK Feature : Head hurts might fix later
    #
    ###
    # @commands.Cog.listener(name="on_message")
    # async def afk_check(self, message):
    #     def afk_remove(afk):
    #         if "[AFK]" in afk.split():
    #             return " ".join(afk.split()[1])
    #         else:
    #             return afk

    #     if message.author.id in afks.keys():
    #         afks.pop(message.author.id)
    #         try:
    #             await message.author.edit(nick = afk_remove(message.author.display_name))
    #             await message.channel.send(f"Welcome back, {message.author.mention}! I have removed your nickname")
    #         except Exception:
    #             pass
    #         await message.channel.send(f"Welcome back, {message.author.mention}!")

    #     for id, reason in afks.items():
    #         member = get(message.guild.members, id = id)
    #         if (message.reference and member == (await message.channel.fetch_message(message.reference.message_id)).author) or member.id in message.raw_mentions:
    #             await message.send(f"{member.name} is AFK: `{reason}`")

    #     afks[member.id] = reason
    #     embed = Embed(title = ":zzz: AFK", description = f"{member.display_name} is AFK", color = member.color)
    #     embed.set_thumbnail(url = member.avatar)
    #     embed.set_author(name = self.bot.user.name, icon_url = self.bot.user.avatar)
    #     embed.add_field(name = "Note", value = reason)
    #     await ctx.send(embed = embed)

    @owner.command(name="apigen")
    @commands.check(permissions.is_owner)
    async def api_gen(self, ctx, *, email: str):
        def check(e):
            return True if re.search(self.email_re, email) else "agb-dev.xyz" in email

        embed = Embed(title="API Token Gen", colour=discord.Colour.green(), thumbnail=None)

        async def api_send_email(email, username, token):
            async with aiohttp.ClientSession(headers={"Content-Type": "application/json"}) as s:
                async with s.post(
                    "https://api.emailjs.com/api/v1.0/email/send",
                    json={
                        "service_id": "service_lunarapi",
                        "template_id": "template_l08wv0d",
                        "user_id": "JbFTDHDsfREYjwbJe",
                        "accessToken": "11izhUPQGL_xrrkD9TYFV",
                        "template_params": {
                            "user_email": f"{email}",
                            "user_name": f"{username}",
                            "api_key": f"{token}",
                        },
                    },
                ) as r:
                    pass

        if check(email):
            config = imports.get("apidb_config.json")
            api_db = Connection(self.bot, config)
            await api_db.create_connection()

            username = email.partition("@")[0]
            p = check_output(["node", "../lunar-api/genToken.js", f"--u={email}"])
            token = str(p, "utf-8")

            await api_db.execute(f"SELECT * FROM users WHERE email = '{email}'")
            await api_db.execute(
                "UPDATE users SET apiverified = True, token = '$1' WHERE email = '$2'",
                token,
                email,
            )
            await api_db.close()

            embed.add_field(name=f"Token for `{email}`", value=f"```{token}```")
            embed.add_field(
                name=f"User Created [{username}]",
                value="Successfully created and added the user to the API Database!",
            )
            await ctx.send(embed=embed)

            # Send Email VIA http POST Request
            await api_send_email(email, username, token)
        else:
            embed.add_field(name="Error", value="Invalid email. `Expected: *@*.*`")
            await ctx.send(embed=embed)
            return

    @owner.command()
    async def testing(self, ctx):
        """Error raiser"""
        # Raise an exception if the server is not allowed to accessToken
        raise discord.errors.NotOwner(ctx.author)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def addstatus(self, ctx, *, status: str):
        """Add status to the bots status list

        Args:
            status (string, optional): The status to add

        Opts:
            {server_count} -> The amount of servers the bot is in
            {command_count} -> The amount of commands the bot has
            * Pass these as is in your string

        Ex:
            /addstatus Servers: {server_count} | Commands: {command_count}
        """
        # row_count = len(self.bot.db._statuses)
        status = status.strip().replace("'", "")
        new_status = await self.bot.db.add_status(status)
        embed = Embed(color=colors.prim, thumbnail=None)
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar)
        embed.add_field(
            name="Status",
            value=f"Added status to db:\n```\n{new_status.status}```",
            inline=True,
        )
        embed.set_thumbnail(url=ctx.author.avatar)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.check(permissions.is_owner)
    async def findmutuals(self, ctx, user: discord.User = None):
        user = ctx.author if user is None else user
        mutuals = [f"{guild.id}: {guild.name}" for guild in self.bot.guilds if user in guild.members]
        mutuals = "\n".join(mutuals)
        await ctx.send(f"```{mutuals}```")
        return

    @owner.command()
    @commands.check(permissions.is_owner)
    async def globalblacklist(self, ctx, user: str):
        await ctx.typing(ephemeral=True)
        yes = await ctx.send("Working...", ephemeral=True)
        id = user
        for guild in self.bot.guilds:
            user = await ctx.bot.fetch_user(id)
            try:
                user = await ctx.bot.fetch_user(id)
                try:
                    await guild.fetch_ban(user)
                    log(f"{user.name} is already banned from {guild.name}")
                except discord.NotFound:
                    await guild.ban(user, reason="AGB Global Blacklist")
                    await yes.edit(content=f"Banned {user.name} from {guild.name}")
                    log(f"Banned {user.name} from {guild.name}")
            except discord.Forbidden:
                log(f"Could not ban {user.name} from {guild.name}")
        await asyncio.sleep(random.randint(0, 6))
        await yes.edit("Done!")

    @owner.command(name="dbfetch")
    @commands.check(permissions.is_owner)
    async def db_fetch(self, ctx):
        message = await ctx.send(
            "⚠️ This command only chunks guilds now. The bot no longer stores db entries other than commands."
        )
        log("Chunking servers, please be patient..")
        chunked = 0
        for guild in self.bot.guilds:
            if not guild.chunked:
                await guild.chunk()
                chunked += 1
                await asyncio.sleep(0.5)

        await message.edit(content=f"Done! Chunked {chunked} guilds.")

    async def get_commit(self, ctx):
        COMMAND = "git branch -vv"
        proc = await asyncio.create_subprocess_shell(
            COMMAND, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()
        stdout = stdout.decode().split("\n")
        for branch in stdout:
            if branch.startswith("*"):
                return branch
        raise ValueError()

    @commands.hybrid_group()
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def pull(self, ctx):
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(str(ctx.command))
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @pull.command()
    @commands.check(permissions.is_owner)
    async def changes(self, ctx):
        COMMAND = "git pull"
        addendum = ""
        proc = await asyncio.create_subprocess_shell(
            COMMAND, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()
        stdout = stdout.decode()
        if "no tracking information" in stderr.decode():
            COMMAND = "git pull"
            proc = await asyncio.create_subprocess_shell(
                COMMAND, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()
            stdout = stdout.decode()
            addendum = "\n\n**Warning: no upstream branch is set.  I automatically pulled from origin/main but this may be wrong.  To remove this message and make it dynamic, please run `git branch --set-upstream-to=origin/<branch> <branch>`**"

        embed = Embed(title="Git pull", description="", color=colors.prim, thumbnail=None)
        if "Fast-forward" not in stdout:
            if "Already up to date." in stdout:
                embed.description = "Code is up to date."
            else:
                embed.description = "Pull failed: Fast-forward strategy failed.  Look at logs for more details."

                log(stdout)
            embed.description += addendum
            embed.description += f"```py\n{stdout}```"
            await ctx.send(embed=embed)
            return
        try:
            current = await self.get_commit(ctx)
        except ValueError:
            pass
        else:
            embed.description += f"`{current[2:]}`\n"
        embed.description += addendum
        embed.description += f"```py\n{stdout}```"
        await ctx.send(embed=embed)

    @pull.command()
    @commands.check(permissions.is_owner)
    async def fix(self, ctx):
        COMMAND = "./git-fix.sh"
        os.system(shlex.quote("chmod +x ./git-fix.sh"))
        proc = await asyncio.create_subprocess_shell(
            COMMAND, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        stdout = stdout.decode()
        log(stdout)
        await Embed(title="Git fix", description=f"```py\n{stdout}```").send(ctx)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def checkbanperm(self, ctx, member: discord.Member):
        # make a command to check if a user can be banned from a server
        # check if the bot has ban members permission
        await ctx.typing(ephemeral=True)
        try:
            if ctx.guild.me.guild_permissions.ban_members is True:
                # check the role hierarchy
                if ctx.guild.me.top_role > member.top_role:
                    return await ctx.author.send("I can ban this user!")
                if ctx.guild.me.top_role == member.top_role:
                    return await ctx.author.send("That user has the same role as me, i cant ban them")
                if ctx.guild.me.top_role < member.top_role:
                    await ctx.author.send(
                        "User has a higher role than me, I can't ban them! but i do have the permission to ban members"
                    )
            else:
                await ctx.author.send("I don't have the permission to ban members")

            await ctx.send("Check DMs", ephemeral=True)
        except Exception:
            await ctx.send("Something happened", ephemeral=True)

    @owner.command(name="chunk")
    @commands.check(permissions.is_owner)
    async def chunk_guilds(self, ctx):
        bruh = await ctx.send("Chunking guilds...")
        # chunk db because why not
        await self.bot.db.chunk(guilds=True)
        chunked_guilds = 0
        chunked = []

        # appends the current count of chunked guilds to a list then adds 1 to the chunked guilds count
        for guild in self.bot.guilds:
            if guild.chunked:
                chunked.append(guild)
                chunked_guilds += 1
        # takes the appended list and starts adding the newly chunked guilds to it
        async with ctx.channel.typing():
            for guild in self.bot.guilds:
                if not guild.chunked:
                    await guild.chunk()
                    chunked_guilds += 1
                    if chunked_guilds % random.randint(1, 15) == 0:
                        await bruh.edit(content=f"Chunked {chunked_guilds}/{len(self.bot.guilds)} guilds")
                        await asyncio.sleep(random.randint(1, 3))

            log(
                f"Chunked {formatColor(str(chunked_guilds), 'green')} / {formatColor(str(len(self.bot.guilds)), 'green')} guilds"
            )
            await bruh.edit(content=f"Done chunking guilds! {chunked_guilds}/{len(self.bot.guilds)} guilds chunked!")

    @owner.command(aliases=["speedtest"])
    @commands.check(permissions.is_owner)
    async def netspeed(self, ctx):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        speed_test = speedtest.Speedtest(secure=True)
        the_embed = await ctx.send(embed=self.generate_embed(0, speed_test.results.dict()))
        await loop.run_in_executor(executor, speed_test.get_servers)
        await loop.run_in_executor(executor, speed_test.get_best_server)
        await the_embed.edit(embed=self.generate_embed(1, speed_test.results.dict()))
        await loop.run_in_executor(executor, speed_test.download)
        await the_embed.edit(embed=self.generate_embed(2, speed_test.results.dict()))
        await loop.run_in_executor(executor, speed_test.upload)
        await the_embed.edit(embed=self.generate_embed(3, speed_test.results.dict()))

    @staticmethod
    def generate_embed(step: int, results_dict):
        """Generate the embed."""
        measuring = ":mag: Measuring..."
        waiting = ":hourglass: Waiting..."

        color = discord.Color.red()
        title = "Measuring internet speed..."
        message_ping = measuring
        message_down = waiting
        message_up = waiting
        if step > 0:
            message_ping = f"**{results_dict['ping']}** ms"
            message_down = measuring
        if step > 1:
            message_down = f"**{results_dict['download'] / 1_000_000:.2f}** mbps"
            message_up = measuring
        if step > 2:
            message_up = f"**{results_dict['upload'] / 1_000_000:.2f}** mbps"
            title = "NetSpeed Results"
            color = discord.Color.green()
        embed = Embed(title=title, color=color, thumbnail=None)
        embed.add_field(name="Ping", value=message_ping)
        embed.add_field(name="Download", value=message_down)
        embed.add_field(name="Upload", value=message_up)
        return embed

    @commands.hybrid_group(name="blacklist")
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def blacklist(self, ctx: commands.Context):
        """Blacklist commands"""
        await ctx.send_help(ctx.command)

    @blacklist.command(
        name="user",
        description="Blacklist a user from using the bot",
    )
    @app_commands.describe(
        user_id="ID of the user you want to blacklist",
        user="For if the user is in the server",
        reason="Reason for blacklisting the user",
        days="For how many days to blacklist the user",
        blacklist="Whether or not to blacklisted the user. Defaults to true",
        silent="Whether or not to send a message to the user",
    )
    @commands.check(permissions.is_owner)
    async def blacklist_user(self, ctx, *, options: BlacklistUserArguments):
        if not options.user and not options.user_id:
            return await ctx.send(
                (
                    "You need to provide a user via one of the two arguments... "
                    "user: {actual user in the server or sharing a server with the bot} OR user_id: {user id of the user you want to blacklist, can be anyone}"
                )
            )

        user_id = int(options.user_id) if options.user_id else int(options.user.id)  # type: ignore

        to_dm = options.user or await self.bot.fetch_user(user_id)

        db_user = await self.bot.db.fetch_blacklist(user_id, blacklisted=None)
        if not db_user:
            if not options.blacklist:
                return await Embed(
                    title="Blacklist User",
                    description=f"{user_id} is not blacklisted",
                ).send(ctx)

            db_user = await self.bot.db.add_blacklist(user_id)

        kwargs: dict[str, Any] = {"blacklisted": options.blacklist}
        if options.reason:
            kwargs["reason"] = options.reason
        if options.days:
            kwargs["blacklistedtill"] = options.days

        await db_user.edit(**kwargs)

        temp = " temporarily" if options.blacklist and options.days else ""
        what = "blacklisted" if options.blacklist else "unblacklisted"
        title = f"User{temp} {what.title()}"

        description = f"{user_id} was {what} from using the bot"
        if options.days:
            description += f" for {options.days} days"
        if options.reason:
            description += f" with reason: {options.reason}"

        await Embed(
            title=title,
            description=description,
            color=discord.Color.red() if options.blacklist else discord.Color.green(),
        ).send(ctx)

        if options.silent:
            return

        cant_dm = f"Could not DM {user_id} about the blacklist change, they have still been {what}."
        dm_embed = Embed(
            title=f"{title} DM",
        )
        if not to_dm:
            dm_embed.description = cant_dm
            await dm_embed.send(ctx)
            return

        reason = options.reason or "No reason provided"
        lasts = f"{options.days} days" if options.days else "forever"
        dm_description = (
            f"You have been{temp} {what} from using the bot for the following reason: {reason}\n."
            f"\n\nThis blacklist lasts for {lasts} unless you can email us a good reason why you should be whitelisted - `contact@lunardev.group`"
        )
        emb = Embed(
            title=f"{temp.strip()} {what.title()} DM",
            description=dm_description,
        )
        try:
            await emb.send(to_dm)
        except discord.HTTPException:
            dm_embed.description = cant_dm
            await dm_embed.send(ctx)
        else:
            dm_embed.description = f"DMed {user_id} about the blacklist change."
            await dm_embed.send(ctx)

    @blacklist.command(
        name="server",
        description="Blacklist a server from using the bot",
    )
    @app_commands.describe(
        server_id="ID of the server you want to blacklist",
        blacklist="Whether or not to blacklisted the server",
    )
    @commands.check(permissions.is_owner)
    async def blacklist_server(self, ctx, server_id: str, blacklist: bool = True):
        guild_id = int(server_id)
        db_guild = await self.bot.db.fetch_guild_blacklist(guild_id, blacklisted=None)
        if not db_guild:
            if not blacklist:
                return await Embed(
                    title="Blacklist Server",
                    description=f"{guild_id} is not blacklisted",
                ).send(ctx)

            db_guild = await self.bot.db.add_guild_blacklist(guild_id)

        await db_guild.edit(blacklisted=blacklist)
        await Embed(
            title="Blacklist Server",
            description=f"{guild_id} was {'blacklisted' if blacklist else 'unblacklisted'} from using the bot.",
        ).send(ctx)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def massblacklist(self, ctx, *, user_ids: str):
        await ctx.typing()
        if not ctx.interaction:
            return await ctx.send(
                "This command is only available in slash commands. Its easier to use that way.",
                delete_after=3,
            )
        user_ids = user_ids.split(",")
        for user_id in user_ids:
            user_id = user_id.strip()
            if not user_id.isdigit():
                await ctx.send(f"{user_id} is not a valid user ID.")
                continue
            user = await self.get_or_fetch_user(int(user_id))
            if not user:
                await ctx.send(f"{user_id} is not a valid user ID.")
                continue
            user_blacklist = await self.bot.db.getch("blacklist", int(user_id))
            if not user_blacklist:
                await self.bot.db.add_blacklist(user.id, blacklisted=True)
            elif user_blacklist.is_blacklisted is False:
                await user_blacklist.edit(blacklisted=True)
        await ctx.send("Done.")
        await self.add_success_reaction()
        return

    @commands.check(permissions.is_owner)
    @owner.command()
    async def eval(self, ctx):
        await ctx.typing(ephemeral=True)
        await ctx.send(
            "Please click the below button to evaluate your code.",
            view=EvalView(ctx.author.id),
        )

        # try:
        #     exec(to_compile, env)
        # except Exception as e:
        #     capture_exception(e)
        #     await self.add_fail_reaction()
        #     embed.add_field(
        #         name="Error",
        #         value=f"```py\n{e.__class__.__name__}: {e}\n```",
        #         inline=True,
        #     )
        #     try:
        #         await ctx.send(embed=embed, ephemeral=True)
        #     except Exception:
        #         await ctx.send("Done and returned no output.")
        #     return

        # func = env["func"]
        # try:
        #     with redirect_stdout(stdout):
        #         ret = await func()
        # except Exception:
        #     _value_p1 = await filter_eval(stdout.getvalue(), config.token)
        #     value = await filter_eval(_value_p1, config.lunarapi.token)
        #     embed.add_field(
        #         name="Output",
        #         value=f"```py\n{value}{traceback.format_exc()}\n```",
        #         inline=True,
        #     )
        #     try:
        #         await ctx.send(embed=embed, ephemeral=True)
        #     except Exception:
        #         await ctx.send("Done and returned no output.")

        # else:
        #     _value_p1 = await filter_eval(stdout.getvalue(), config.token)
        #     value = await filter_eval(_value_p1, config.lunarapi.token)
        #     await self.add_success_reaction()
        #     if ret is None:
        #         if value:
        #             embed.add_field(
        #                 name="Result", value=f"```py\n{value}\n```", inline=True
        #             )
        #             try:
        #                 await ctx.send(embed=embed, ephemeral=True)
        #             except Exception:
        #                 await ctx.send("Done and returned no output.")
        #     else:
        #         self._last_result = ret
        #         embed.add_field(
        #             name="Result", value=f"```py\n{value}{ret}\n```", inline=True
        #         )
        #         try:
        #             await ctx.send(embed=embed, ephemeral=True)
        #         except Exception:
        #             await ctx.send("Done and returned no output.")

    @commands.check(permissions.is_owner)
    @owner.command()
    async def spokemost(self, ctx):
        # iterate through the servers channels and messages and collect the messages
        channel_messages = []
        what_channel_we_are_in = await ctx.send("Getting messages...")
        for channel in ctx.guild.text_channels:
            async for message in channel.history(limit=None):
                if not message.author.bot:
                    channel_messages.append(message)
                    if len(channel_messages) % 50 == 0:
                        await what_channel_we_are_in.edit(
                            content=f"We're in {channel.name} now, we've gathered {len(channel_messages)} messages"
                        )

        # iterate through the messages and count the number of times each user has spoken
        speaker_count = {}
        for message in channel_messages:
            if message.author.id in speaker_count:
                speaker_count[message.author.id] += 1
            else:
                speaker_count[message.author.id] = 1

        # find the user with the most messages
        most_messages = max(speaker_count.values())
        most_messages_users = [user for user, value in speaker_count.items() if value == most_messages]

        # find the user with the most messages
        most_messages_user = most_messages_users[0]
        for user in most_messages_users:
            if ctx.guild.get_member(user).display_name > ctx.guild.get_member(most_messages_user).display_name:
                most_messages_user = user

        # find the user with the most messages
        most_messages_user = ctx.guild.get_member(most_messages_user)

        # send the message
        await ctx.send(f"{most_messages_user.mention} has spoken the most in the server! ({most_messages} messages)")

    @commands.check(permissions.is_owner)
    @owner.command()
    async def whatcanyousee(self, ctx):
        channel_list = "".join(f"{channel.mention}\n" for channel in ctx.guild.text_channels)

        await ctx.send(f"Here are the channels I can see:\n{channel_list}")

    @owner.command()
    @commands.check(permissions.is_owner)
    async def sync(
        self,
        ctx,
        guilds: commands.Greedy[discord.Object] = None,
        spec: Optional[Literal["~", "*", "."]] = None,
    ) -> None:
        """Syncs commands
        sync -> global sync
        sync ~ or . -> sync current guild
        sync * -> copies all global app commands to current guild and syncs
        sync id_1 id_2 -> syncs guilds with id 1 and 2
        """
        if not guilds:
            if spec in ["~", "."]:
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}")
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @app_commands.command(name="cog", description="Reload, unload or load cogs!")
    @app_commands.choices(
        options=[
            Choice(name="load", value="load"),
            Choice(name="unload", value="unload"),
            Choice(name="reload", value="reload"),
            Choice(name="load all", value="loadall"),
            Choice(name="reload all", value="reloadall"),
        ]
    )
    @app_commands.guilds(OS)
    @app_commands.check(permissions.is_owner_slash)
    async def cog(
        self,
        interaction: discord.Interaction,
        options: Choice[str],
        extension: str = None,
    ):
        if options.value == "load":
            try:
                await self.bot.load_extension(extension)
            except commands.errors.ExtensionAlreadyLoaded:
                await interaction.followup.send(f"The cog `{extension}` is already loaded!")
            await interaction.followup.send(f"The extension `{extension}` has been loaded!")

        elif options.value == "unload":
            try:
                await self.bot.unload_extension(extension)
            except commands.errors.ExtensionNotLoaded:
                await interaction.followup.send(f"The cog `{extension}` wasn't loaded!")
            await interaction.followup.send(f"The extension `{extension}` has been unloaded!")

        elif options.value == "reload":
            await self.bot.reload_extension(extension)
            await interaction.followup.send(f"The extension `{extension}` has been reloaded!")

        elif options.value == "loadall":
            for file in sorted(pathlib.Path("Cogs").glob("**/[!_]*.py")):
                cog = ".".join(file.parts).removesuffix(".py")
                with suppress(commands.errors.ExtensionAlreadyLoaded):
                    await self.bot.load_extension(cog)
            await interaction.followup.send("All unloaded extensions have been loaded!")
        elif options.value == "reloadall":
            for file in sorted(pathlib.Path("Cogs").glob("**/[!_]*.py")):
                cog = ".".join(file.parts).removesuffix(".py")
                await self.bot.reload_extension(cog)
            await interaction.followup.send("Reloaded all extensions!")

    @cog.autocomplete("extension")
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        extensions = []
        for file in sorted(pathlib.Path("Cogs").glob("**/[!_]*.py")):
            cog = ".".join(file.parts).removesuffix(".py")
            extensions.append(cog)

        return [
            Choice(name=extension.split(".")[1], value=extension)
            for extension in extensions
            if current.lower() in extension.lower()
        ][:25]

    @owner.command()
    @commands.check(permissions.is_owner)
    async def reloadutils(self, ctx, *, names: str):
        names = names.split(" ")
        for name in names:
            try:
                module_name = importlib.import_module(f"utils.{name}")
                importlib.reload(module_name)
            except Exception as e:
                capture_exception(e)
                await ctx.send(default.traceback_maker(e))
                await self.add_fail_reaction()
                return
            await self.add_success_reaction()
        if len(names) == 1:
            await ctx.send(
                f"Reloaded extension **{name}.py** {ctx.author.mention}",
                delete_after=delay,
            )
        else:
            await ctx.send(
                "Reloaded the following extensions\n" + "\n".join(f"**{name}.py**" for name in names),
                delete_after=delay,
            )

    # @owner.command()
    # @commands.check(permissions.is_owner)
    # async def apirm(self, ctx, *, rmcodes: str):
    #     with contextlib.suppress(Exception):
    #         await ctx.message.delete()
    #     rmcodes = rmcodes.split(" ")
    #     apiUrlReg = "https://api.lunardev.group/"
    #     imgId = (elem.replace(apiUrlReg, "") for elem in rmcodes)
    #     for rmcode in imgId:
    #         await self.remove_images(rmcode)
    #     if len(rmcodes) == 1:
    #         await ctx.send(f"Removed `{rmcodes[0]}` from the API.", delete_after=delay)
    #         return
    #     await ctx.send(
    #         (
    #             "removed the following\n"
    #             + "\n".join(f"**{rmcode}**" for rmcode in rmcodes)
    #         ),
    #         delete_after=delay,
    #     )

    @owner.command()
    @commands.check(permissions.is_owner)
    async def apiadd(self, ctx):
        for attachment in ctx.message.attachments:
            attachment.save(attachment.filename)

    async def restart_container_autocomplete(self, _: discord.Interaction, current: str) -> list[Choice[str]]:
        all_choices = [Choice(name=name, value=_id) for name, _id in self.CONTAINERS.items()]
        startswiths_choices = [c for c in all_choices if c.name.startswith(current) or c.value.startswith(current)]
        return (startswiths_choices or all_choices) if current else all_choices

    @owner.command()
    @commands.check(permissions.is_owner)
    async def restart(self, ctx: commands.Context):
        # AUTOCOMPLETE IDS:
        # , container_id: Optional[str] = None):
        # if not container_id:
        #   container_id = self.CONTAINERS["AGB"]
        # restart_what = discord.utils.find(lambda name, value: value == container_id, self.CONTAINERS.items())
        # await ctx.send(f"Restarting {restart_what[0]}...")
        # uncomment when used i guess
        await ctx.send("Restarting AGB")
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.config.lunarapi.token}"}
        ) as session, session.get(
            f"https://api.lunardev.group/admin/restart/agb?password={self.config.lunarapi.adminPass}"
        ) as resp:
            if resp.status == 200:
                return

    @owner.command()
    @commands.check(permissions.is_owner)
    async def dm(self, ctx, user: discord.User, *, message: str):
        if user.bot:
            return await ctx.send("I can't DM bots.\nI mean I can, I just don't want to...")
        with suppress(Exception):
            await ctx.message.delete()
        e = Embed(
            title=f"New message From {ctx.author.name} | {self.bot.user.name} DEV",
            description=message,
            footer="To contact me, just DM the bot",
        )
        e2 = Embed(
            title=f"New message to {user}",
            description=message,
            footer=f"/owner dm {user.id}",
        )
        # check if the command was ran in the log channel
        log_dm = self.bot.get_channel(986079167944749057)
        if ctx.channel.id == log_dm.id:
            try:
                await user.send(embed=e)
                await log_dm.send(embed=e2)
            except Exception:
                await ctx.send("Cannot DM user.")
                return
        else:
            try:
                await user.send(embed=e)
                await log_dm.send(embed=e2)
            except Exception as e:
                await ctx.send(f"Cannot dm user. | {e}")

    @commands.hybrid_group(case_insensitive=True)
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def change(self, ctx):

        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @change.command(name="username")
    @commands.check(permissions.is_owner)
    async def change_username(self, ctx, *, name: str):
        try:
            await self.bot.user.edit(username=name)
            await ctx.send(
                f"Successfully changed username to **{name}** {ctx.author.mention}. Lets hope I wasn't named something retarded",
                delete_after=delay,
            )
        except discord.HTTPException as err:
            await ctx.send(err)

    @change.command(name="nickname")
    @commands.check(permissions.is_owner)
    async def change_nickname(self, ctx, *, name: str = None):
        try:
            await ctx.guild.me.edit(nick=name)
            if name:
                await ctx.send(f"Successfully changed nickname to **{name}**", delete_after=delay)
            else:
                await ctx.send("Successfully removed nickname", delete_after=delay)
        except Exception as err:
            capture_exception(err)
            await ctx.send(err)

    @change.command(name="avatar")
    @commands.check(permissions.is_owner)
    async def change_avatar_url(self, ctx, url: str = None):
        if url is None and len(ctx.message.attachments) == 1:
            url = ctx.message.attachments[0].url
        else:
            url = url.strip("<>") if url else None
        try:
            bio = await httpx.get(url, res_method="read")
            await self.bot.user.edit(avatar=bio)
            await ctx.send(
                f"Successfully changed the avatar. Currently using:\n{url}",
                delete_after=delay,
            )
        except aiohttp.InvalidURL:
            await ctx.send("The URL is invalid...", delete_after=delay)
        except ValueError:
            await ctx.send(
                "ValueError, this shouldn't happen. Try a different image.",
                delete_after=delay,
            )
        except discord.HTTPException as err:
            await ctx.send(err)
        except TypeError:
            await ctx.send(
                "You need to either provide an image URL or upload one with the command",
                delete_after=delay,
            )


#         if interaction.user != self.user:
#             await interaction.response.send_message("You can't use this button!", ephemeral=True)
#             return False


#         return True


async def setup(bot: AGB) -> None:
    await bot.add_cog(Admin(bot))
