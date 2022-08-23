from __future__ import annotations

import asyncio
import concurrent
import datetime
import importlib
import inspect
import io
import os
import random
import re
import subprocess
import textwrap
import time
import traceback
from contextlib import redirect_stdout, suppress
from subprocess import check_output
from typing import TYPE_CHECKING, Literal, Optional

import aiohttp
import discord
import httpx
import speedtest
from discord.ext import commands
from index import colors, delay, logger, EmbedMaker
from Manager.database import Connection
from Manager.logger import formatColor
from Manager.objects import Table
from sentry_sdk import capture_exception
from utils import default, imports, permissions
from utils.default import log
from utils.errors import BlacklistedUser

from .Utils import random

# from utils.checks import InteractiveMenu
OS = discord.Object(id=975810661709922334)

if TYPE_CHECKING:
    from index import Bot


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
    body = discord.ui.TextInput(
        label="Code", style=discord.TextStyle.paragraph)

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
            return await interaction.response.send_message(
                "You can't do this!", ephemeral=True
            )
        await interaction.response.send_modal(self.modal)
        self.stop()


class PersistentView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(
        label="Report to Developers",
        style=discord.ButtonStyle.blurple,
        custom_id="AGBCustomID",
    )
    async def report(self, i: discord.Interaction, b: discord.ui.Button):
        guild = await i.client.fetch_guild(975810661709922334)
        bruh = await guild.fetch_channel(990187200656322601)
        # get the embeds image url
        embed_image = i.message.embeds[0].image.url
        async with aiohttp.ClientSession() as session:
            async with session.get(embed_image) as resp:
                if resp.status == 200:
                    await bruh.send(f"{embed_image} reported by {i.user.id}")
                    # disable the button once its been used
                    b.disabled = True
                    await i.response.edit_message(view=self)
                    await i.followup.send(
                        "Thank you for reporting this image, we trust that you reported it correctly; by following our rules, we will take action against any image that is deemed to be in violation of our rules.\nImages are eligible for reporting if they are in violation of our following rules:\n__*__ Not porn(not actual porn, lewd / suggestive positions and actions, etc)\n__*__ Gross(scat, gore, rape, etc)\n__*__ Breaks ToS(shota, loli, etc)",
                        ephemeral=True,
                    )
                else:
                    await i.response.edit_message(view=self)
                    await i.followup.send(
                        "Report failed.\nThe image you sent was not found in the api.",
                        ephemeral=True,
                    )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        db = interaction.client.db
        user_id = interaction.user.id
        blacklisted_user = await db.fetch_blacklist(user_id)

        if blacklisted_user and blacklisted_user.is_blacklisted:
            await interaction.response.send_message(
                f"You are blacklisted from using this bot for the following reason\n`{blacklisted_user.reason}`",
                ephemeral=True,
            )
            return False

        return True


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


class Admin(commands.Cog, name="admin", command_attrs=dict()):
    """Commands that arent for you lol"""

    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
        self.config = imports.get("config.json")
        os.environ.setdefault("JISHAKU_HIDE", "1")
        self._last_result = None
        self.last_change = None
        self.tax_rate = 0
        self.tax_collector = None
        self.lunar_headers = {
            f"{self.config.lunarapi.header}": f"{self.config.lunarapi.token}"
        }
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
        self.email_re = "^[a-z0-9]+[\._]?[a-z0-9]+[@]\w+[.]\w{2,3}$"
        self.blacklisted = False

        bot.add_check(self.blacklist_check)
        self.nword_re = r"\b(n|m|и|й){1,32}(i|1|l|!|ᴉ|¡){1,32}((g|ƃ|6|б{2,32}|q){1,32}|[gqgƃ6б]{2,32})(a|e|3|з|u)(r|Я|s|5|$){1,32}\b"
        self.nword_re_comp = re.compile(
            self.nword_re, re.IGNORECASE | re.UNICODE)
        self.afks = {}

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

    async def blacklist_check(self, ctx: commands.Context):
        bl = await self.bot.db.fetch_blacklist(ctx.author.id, cache=True)
        if bl and bl.is_blacklisted:
            raise BlacklistedUser(
                obj=bl,
                user=ctx.author,
            )

        return True

    async def run_process(self, command):
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            result = await process.communicate()
        except NotImplementedError:
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
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
        emoji = "\u2705"
        with suppress(Exception):
            await self.add_reaction(emoji)

    async def add_success_reaction(self):
        emoji = "\u2705"
        with suppress(Exception):
            await self.add_reaction(emoji)

    class MemberConverter(commands.MemberConverter):
        async def convert(self, ctx, argument):
            try:
                return await super().convert(ctx, argument)
            except commands.BadArgument as e:
                members = [
                    member
                    for member in ctx.guild.members
                    if member.display_name.lower().startswith(argument.lower())
                ]
                if len(members) == 1:
                    return members[0]
                else:
                    raise commands.BadArgument(
                        f"{len(members)} members found, please be more specific."
                    ) from e

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
            Table.REMINDERS,
            Table.USER_ECONOMY,
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
                await self.bot.db.executemany(query, [str(user_id) for user_id in user_ids])

        if action == "GET":
            return entries

    @commands.hybrid_group(name="owner")
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def owner(self, ctx: commands.Context):
        """
        Owner-only commands.
        """
        await ctx.send("Owner-only commands.", ephemeral=True)

    @commands.hybrid_group(name="blacklist")
    @discord.app_commands.guilds(OS)
    @commands.check(permissions.is_owner)
    async def blacklist(self, ctx: commands.Context):
        """
        Blacklist commands
        """
        await ctx.send("Blacklist commands.", ephemeral=True)

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

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if self.nword_re_comp.search(guild.name.lower()):
            await self.try_to_send_msg_in_a_channel(
                guild, "im gonna leave cuz of the server name"
            )
            return await guild.leave()
        for channel in guild.channels:
            if self.nword_re_comp.search(guild.name.lower()):
                await self.try_to_send_msg_in_a_channel(
                    guild, f"im gonna leave cuz of the channel name {channel.mention}"
                )
                log(f"{guild.name} / {guild.id} is a racist server.")
                return await guild.leave()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member, guild=None):
        info = self.bot.get_channel(755722577049026562)
        info2 = self.bot.get_channel(776514195465568257)
        info3 = self.bot.get_channel(755722908122349599)
        guild = member.guild
        embed = discord.Embed(title="User Joined",
                              colour=discord.Colour.green())
        embed.add_field(
            name=f"Welcome {member}",
            value=f"Welcome {member.mention} to {guild.name}!\nPlease read <#776514195465568257> to get color roles for yourself and common questions about AGB!",
        )
        embed.add_field(
            name="Account Created",
            value=member.created_at.strftime("%a, %#d %B %Y, %I:%M %p UTC"),
            inline=False,
        )
        embed.set_thumbnail(url=member.avatar)
        if member.guild.id == 755722576445046806:
            if member.bot:
                role = discord.utils.get(guild.roles, name="Bots")
                await member.add_roles(role)
                return
            else:
                role = discord.utils.get(guild.roles, name="Members")
                await member.add_roles(role)
                await info.send(f"{member.mention}", delete_after=0)
                await info2.send(f"{member.mention}", delete_after=0)
                await info3.send(f"{member.mention}", delete_after=0)
                channel = self.bot.get_channel(755722577049026567)
                await channel.send(
                    content=f"Guild member count: {guild.member_count}",
                    embed=embed,
                    delete_after=10,
                )

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

    ######
    #
    # Attempted AFK Feature : Head hurts might fix later
    #
    ######
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

    # @commands.command(name="afk")
    # @commands.check(permissions.is_owner)
    # async def afk(self, ctx, reason = "AFK"):
    #     member = ctx.author
    #     if member.id in afks.keys():
    #         afks.pop(member.id)
    #     else:
    #         try:
    #             member.edit(nick = f"[AFK] {member.display_name}")
    #         except Exception:
    #             pass

    #     afks[member.id] = reason
    #     embed = discord.Embed(title = ":zzz: AFK", description = f"{member.display_name} is AFK", color = member.color)
    #     embed.set_thumbnail(url = member.avatar)
    #     embed.set_author(name = self.bot.user.name, icon_url = self.bot.user.avatar)
    #     embed.add_field(name = "Note", value = reason)
    #     await ctx.send(embed = embed)

    @owner.command(name="apigen")
    @commands.check(permissions.is_owner)
    async def api_gen(self, ctx, *, email: str):
        def check(e):
            if re.search(self.email_re, email):
                return True
            elif "agb-dev.xyz" in email:
                return True
            else:
                return False

        embed = discord.Embed(title="API Token Gen",
                              colour=discord.Colour.green())

        async def api_send_email(email, username, token):
            async with aiohttp.ClientSession(
                headers={"Content-Type": "application/json"}
            ) as s:
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
            p = check_output(
                ["node", "../lunar-api/genToken.js", f"--u={email}"])
            token = str(p, "utf-8")

            await api_db.execute(f"SELECT * FROM users WHERE email = '{email}'")
            await api_db.execute(
                f"UPDATE users SET apiverified = True, token = '{token}' WHERE email = '{email}'"
            )
            await api_db.close()

            embed.add_field(
                name=f"Token for `{email}`", value=f"```{token}```")
            embed.add_field(
                name=f"User Created [{username}]",
                value="Successfully created and added the user to the API Database!",
            )
            await ctx.send(embed=embed)

            # Send Email VIA http POST Request
            await api_send_email(email, username, token)
        else:
            embed.add_field(
                name="Error", value="Invalid email. `Expected: *@*.*`")
            await ctx.send(embed=embed)
            return

    # @owner.command()
    # @commands.check(permissions.is_owner)
    # async def servers(self, ctx):
    #     filename = f"{ctx.guild.id}"
    #     with open(f"{str(filename)}.txt", "a", encoding="utf-8") as f:
    #         for guild in self.bot.guilds:
    #             data = f"{guild.id}: {guild}"
    #             f.write(data + "\n")
    #             continue
    #     try:
    #         await ctx.send(
    #             content="Sorry if this took a while to send, but here is all of the servers the bot is in!",
    #             file=discord.File(f"{str(filename)}.txt"),
    #         )
    #     except Exception as e:
    #         capture_exception(e)
    #         await ctx.send(
    #             "I couldn't send the file of this servers bans for whatever reason"
    #         )
    #     os.remove(f"{filename}.txt")

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
            tp!addstatus Servers: {server_count} | Commands: {command_count}
        """

        row_count = len(self.bot.db._statuses)
        status = status.strip().replace("'", "")
        new_status = await self.bot.db.add_status(row_count, status)
        embed = discord.Embed(color=colors.prim)
        embed.set_author(name=self.bot.user.name,
                         icon_url=self.bot.user.avatar)
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
        mutuals = [
            f"{guild.id}: {guild.name}"
            for guild in self.bot.guilds
            if user in guild.members
        ]
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
            "Fetching all servers and users, and adding them to the DB, please wait!"
        )
        log("Chunking servers, please be patient..")
        for guild in self.bot.guilds:
            if not guild.chunked:
                await guild.chunk()
                await asyncio.sleep(0.5)

            ### Server Table Check ###
            serverRows = await self.bot.db.fetch_guild(guild.id)
            if not serverRows:
                await self.bot.db.add_guild(guild.id)
                log(
                    f"{formatColor(ctx.guild.name, 'green')} ({formatColor(str(ctx.guild.id), 'gray')}) added to the database [{formatColor('servers', 'gray')}]"
                )

        for user in self.bot.users:
            if user.bot:
                continue

            ### User Table Check ###
            userRows = await self.bot.db.fetch_user(user.id)
            if not userRows:
                await self.bot.db.add_user(user.id)
                log(
                    f"{formatColor(user, 'green')} ({formatColor(str(user.id), 'gray')}) added to the database [{formatColor('users', 'gray')}]"
                )

            ### Economy Table Check ###
            economyRows = await self.bot.db.fetch_economy_user(user.id)
            if not economyRows:
                await self.bot.db.add_economy_user(user.id)
                log(
                    f"{formatColor(user, 'green')} ({formatColor(str(user.id), 'gray')}) added to the database [{formatColor('economy', 'gray')}]"
                )

            ### Blacklist Table Check ###
            blacklistRows = await self.bot.db.fetch_blacklist(user.id)
            if not blacklistRows:
                await self.bot.db.add_blacklist(user.id)
                log(
                    f"{formatColor(user, 'green')} ({formatColor(str(user.id), 'gray')}) added to the database [{formatColor('blacklist', 'gray')}]"
                )

        await message.edit(content="Done!")

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

    @commands.group()
    @commands.check(permissions.is_owner)
    async def pull(self, ctx):
        if ctx.invoked_subcommand is not None:
            return
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

        embed = discord.Embed(
            title="Git pull", description="", color=colors.prim)
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
        os.system("chmod +x ./git-fix.sh")
        proc = await asyncio.create_subprocess_shell(
            COMMAND, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        stdout = stdout.decode()
        log(stdout)
        await EmbedMaker(title="Git fix", description=f"```py\n{stdout}```").send(ctx)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def checkbanperm(self, ctx, member: discord.Member):
        # make a command to check if a user can be banned from a server
        # check if the bot has ban members permission
        await ctx.typing(ephemeral=True)
        try:
            if ctx.guild.me.guild_permissions.ban_members == True:
                # check the role hierarchy
                if ctx.guild.me.top_role > member.top_role:
                    return await ctx.author.send("I can ban this user!")
                if ctx.guild.me.top_role == member.top_role:
                    return await ctx.author.send(
                        "That user has the same role as me, i cant ban them"
                    )
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
                        await bruh.edit(
                            content=f"Chunked {chunked_guilds}/{len(self.bot.guilds)} guilds"
                        )
                        await asyncio.sleep(random.randint(1, 3))

            log(
                f"Chunked {formatColor(str(chunked_guilds), 'green')} / {formatColor(str(len(self.bot.guilds)), 'green')} guilds"
            )
            await bruh.edit(
                content=f"Done chunking guilds! {chunked_guilds}/{len(self.bot.guilds)} guilds chunked!"
            )

    @owner.command(aliases=["speedtest"])
    @commands.check(permissions.is_owner)
    async def netspeed(self, ctx):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        speed_test = speedtest.Speedtest(secure=True)
        the_embed = await ctx.send(
            embed=self.generate_embed(0, speed_test.results.dict())
        )
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
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Ping", value=message_ping)
        embed.add_field(name="Download", value=message_down)
        embed.add_field(name="Upload", value=message_up)
        return embed

    # @owner.command(name="sqlt")
    # @commands.check(permissions.is_owner)
    # async def sqlt(self, ctx, *, query: str):
    #     data = await self.bot.db.execute(f"{query}RETURNING *")
    #     await ctx.send(data)

    @blacklist.command(name="temp")
    @commands.check(permissions.is_owner)
    async def blacklist_add_temp(
        self,
        ctx,
        user: discord.User,
        *,
        days: int,
        silent: bool = False,
        reason: str = None,
    ):
        db_user = await self.bot.db.fetch_blacklist(user.id)
        if not db_user or db_user is None:
            await self.bot.db.add_temp_blacklist(user.id, blacklisted=True, days=days)
            await EmbedMaker(
                title="Temporary Blacklist",
                description=f"{user.id} was not in the database!\nThey have been added and blacklisted for {days} days.",
            ).send(ctx)
        else:
            # await self.bot.db.update_temp_blacklist(
            #     user.id, blacklisted=True, days=days
            # ) # Exchanged for modify, leaving it for archival and reverting purposes

            await db_user.modify(blacklisted=True, blacklistedtill=days, reason=reason)
            await EmbedMaker(
                title="Temporary Blacklist",
                description=f"{user.id} has been blacklisted for {days} days.",
            ).send(ctx)
        if not silent:
            try:
                if reason is not None:
                    e = EmbedMaker(
                        title="Temporary Blacklist",
                        description=f"You have been temporarily blacklisted from using the bot for the following reason\n{reason}.\n\nThis blacklist lasts for {days} days unless you can email us a good reason why you should be whitelisted - `contact@lunardev.group`",
                    )
                await user.send(embed=e)
                await EmbedMaker(
                    title="Blacklist DM",
                    description="The user has been notified of their blacklist.",
                ).send(ctx)
            except:
                await EmbedMaker(
                    title="Blacklist DM",
                    description="I was unable to DM the user, they have still been blacklisted.",
                ).send(ctx)

    @blacklist.command(name="add", invoke_without_command=True, pass_context=True)
    @commands.check(permissions.is_owner)
    async def blacklist_add(
        self,
        ctx,
        user: Optional[discord.User] = None,
        *,
        list=None,
        reason: str = "No reason",
    ):
        if not ctx.interaction:
            return await ctx.send(
                "This command is only available in slash commands. Its easier to use that way.",
                delete_after=3,
            )
        db_user = await self.bot.db.fetch_blacklist(user.id)

        if not db_user or db_user is None:
            await self.bot.db.add_blacklist(user.id, blacklisted=True)
            await EmbedMaker(
                title="Blacklist",
                description=f"{user.id} was not in the database!\nThey have been added and blacklisted.",
            )
        else:
            # await self.bot.db.update_temp_blacklist(
            #     user.id, blacklisted=True, days=days
            # ) # Exchanged for modify, leaving it for archival and reverting purposes

            await db_user.modify(blacklisted=True, reason=reason)
            await EmbedMaker(
                title="Permanent Blacklist",
                description=f"{user.id} has been blacklisted.",
            ).send(ctx)
        try:
            if reason is not None:
                await user.send(
                    embed=EmbedMaker(
                        title="Blacklist",
                        description=f"You have been blacklisted from using the bot for the following reason\n{reason}.\n\n If you believe this is a mistake, please email us - `contact@lunardev.group`",
                    )
                )
            await EmbedMaker(
                title="Blacklist DM",
                description="The user has been notified of their blacklist.",
            ).send(ctx)
        except:
            await EmbedMaker(
                title="Blacklist DM",
                description="I was unable to DM the user, they have still been blacklisted.",
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
            user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(
                int(user_id)
            )
            if not user:
                await ctx.send(f"{user_id} is not a valid user ID.")
                continue
            user_blacklist = self.bot.db._blacklists.get(user.id)
            if not user_blacklist:
                await self.bot.db.add_blacklist(user.id, blacklisted=True)
            elif user_blacklist.is_blacklisted is False:
                await user_blacklist.modify(blacklisted=True)
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

        # async def filter_eval(search: str, to_filter: str):
        #     if to_filter in search:
        #         return search.replace(to_filter, "[REDACTED]")
        #     else:
        #         return search

        # env = {
        #     "self": self.bot,
        #     "bot": self.bot,
        #     "db": self.bot.db,
        #     "ctx": ctx,
        #     "channel": ctx.channel,
        #     "author": ctx.author,
        #     "guild": ctx.guild,
        #     "message": ctx.message,
        #     "_": self._last_result,
        # }
        # env.update(globals())
        # body = self.cleanup_code(body)
        # stdout = io.StringIO()
        # to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        # embed = discord.Embed(title="Evaluation", colour=colors.prim)

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
        most_messages_users = [
            user for user, value in speaker_count.items() if value == most_messages
        ]

        # find the user with the most messages
        most_messages_user = most_messages_users[0]
        for user in most_messages_users:
            if (
                ctx.guild.get_member(user).display_name
                > ctx.guild.get_member(most_messages_user).display_name
            ):
                most_messages_user = user

        # find the user with the most messages
        most_messages_user = ctx.guild.get_member(most_messages_user)

        # send the message
        await ctx.send(
            f"{most_messages_user.mention} has spoken the most in the server! ({most_messages} messages)"
        )

    @commands.check(permissions.is_owner)
    @owner.command()
    async def whatcanyousee(self, ctx):
        channel_list = "".join(
            f"{channel.mention}\n" for channel in ctx.guild.text_channels
        )

        await ctx.send(f"Here are the channels I can see:\n{channel_list}")

    @owner.command()
    @commands.check(permissions.is_owner)
    async def load(self, ctx, *, names: str):
        for name in names:
            try:
                await self.bot.load_extension(f"Cogs.{name}")
            except Exception as e:
                capture_exception(e)
                await ctx.send(default.traceback_maker(e))
                await self.add_fail_reaction()
                return
            await self.add_success_reaction()
            await ctx.send(f"Loaded extension **{name}.py**", delete_after=delay)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def apidel(self, ctx):
        channel = self.bot.get_channel(932548255202545664)
        msg = await channel.fetch_message(932822132612808725)
        await ctx.send(msg.content)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def sync(self, ctx):
        arg = ctx.guild.id
        await ctx.invoke(self.bot.get_command("jsk sync"), command_string=arg)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def unload(self, ctx, *, names: str):
        for name in names:
            try:
                await self.bot.unload_extension(f"Cogs.{name}")
            except Exception as e:
                capture_exception(e)
                return await ctx.send(default.traceback_maker(e))
            await ctx.send(
                f"Unloaded extension **{name}.py** {ctx.author.mention}",
                delete_after=delay,
            )

    @owner.command()
    @commands.check(permissions.is_owner)
    async def reload(self, ctx, *, names: str):
        names = names.split(" ")
        for name in names:
            try:
                await self.bot.reload_extension(f"Cogs.{name}")
            except Exception as e:
                capture_exception(e)
                await ctx.send(default.traceback_maker(e))
                return
        if len(names) == 1:
            await ctx.send(
                f"Reloaded extension **{name}.py** {ctx.author.mention}",
                delete_after=delay,
            )
        else:
            await ctx.send(
                f"Reloaded the following extensions\n"
                + "\n".join(f"**{name}.py**" for name in names),
                delete_after=delay,
            )

    @owner.command()
    @commands.check(permissions.is_owner)
    async def loadall(self, ctx):
        error_collection = []
        for file in os.listdir("Cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                try:
                    await self.bot.load_extension(f"Cogs.{name}")
                except Exception as e:
                    capture_exception(e)
                    error_collection.append(
                        [file, default.traceback_maker(e, advance=False)]
                    )
        if error_collection:
            output = "\n".join(
                [f"**{g[0]}** ```diff\n- {g[1]}```" for g in error_collection]
            )
            await self.add_fail_reaction()
            return await ctx.send(
                f"Attempted to load all extensions, was able to but... "
                f"the following failed...\n\n{output}"
            )
        await self.add_success_reaction()
        await ctx.send(
            f"Successfully loaded all extensions {ctx.author.mention}",
            delete_after=delay,
        )

    @owner.command()
    @commands.check(permissions.is_owner)
    async def reloadall(self, ctx):
        error_collection = []
        for file in os.listdir("Cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                try:
                    await self.bot.reload_extension(f"Cogs.{name}")
                except Exception as e:
                    capture_exception(e)
                    error_collection.append(
                        [file, default.traceback_maker(e, advance=False)]
                    )
        if error_collection:
            output = "\n".join(
                [f"**{g[0]}** ```diff\n- {g[1]}```" for g in error_collection]
            )
            await self.add_fail_reaction()
            return await ctx.send(
                f"Attempted to reload all extensions, was able to reload, "
                f"however the following failed...\n\n{output}"
            )
        await self.add_success_reaction()
        await ctx.send(
            f"Successfully reloaded all extensions {ctx.author.mention}",
            delete_after=delay,
        )

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
                f"Reloaded the following extensions\n"
                + "\n".join(f"**{name}.py**" for name in names),
                delete_after=delay,
            )

    # @owner.command()
    # @commands.check(permissions.is_mcstaff)
    # async def afreboot(self, ctx):
    #     with suppress(Exception):
    #         bruh = await ctx.send("Rebooting AnimeForestMC...")
    #         await asyncio.create_subprocess_shell(
    #             "(cd /home/ubuntu/LunarGames/AnimeForestMC/ ; sh restart.sh)"
    #         )
    #     await bruh.edit(content="Server rebooted.")

    @owner.command()
    @commands.check(permissions.is_owner)
    async def apirm(self, ctx, *, rmcodes: str):
        rmcodes = rmcodes.split(" ")
        apiUrlReg = "https://api.lunardev.group/"
        imgId = (elem.replace(apiUrlReg, "") for elem in rmcodes)
        for rmcode in imgId:
            logger.info(
                f"{formatColor('[API]', 'yellow')} Removing {rmcode} from the API!"
            )
            # check if the rmcode is the hentai file
            os.system(
                f"cd ~/LunarDev/lunar-api/assets && sudo rm -rf hentai/{rmcode}")
        if len(rmcodes) == 1:
            await ctx.send(f"Removed `{rmcode}` from the API.", delete_after=delay)
            return
        await ctx.send(
            f"removed the following\n"
            + "\n".join(f"**{rmcode}**" for rmcode in rmcodes),
            delete_after=delay,
        )

    @owner.command()
    @commands.check(permissions.is_owner)
    async def apiadd(self, ctx):
        for attachment in ctx.message.attachments:
            attachment.save(attachment.filename)

    @owner.command()
    @commands.check(permissions.is_owner)
    async def restart(self, ctx, *, container: str):
        await ctx.send(f"Restarting container: {container}")
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.config.lunarapi.tokenNew}"}
        ) as session:
            async with session.get(
                f"https://api.lunardev.group/admin/restart?password={self.config.lunarapi.adminPass}&container={container}"
            ) as resp:
                if resp.status == 200:
                    return

    @owner.command()
    @commands.check(permissions.is_owner)
    async def dm(self, ctx, user: discord.User, *, message: str):
        if user.bot:
            return await ctx.send(
                "I can't DM bots.\nI mean I can, I just don't want to..."
            )
        with suppress(Exception):
            await ctx.message.delete()
        e = EmbedMaker(
            title=f"New message From {ctx.author.name} | {self.bot.user.name} DEV",
            description=message,
            footer="To contact me, just DM the bot",
        )
        e2 = EmbedMaker(
            title=f"New message to {user}",
            description=message,
            footer=f"tp!dm {user.id}",
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

    @commands.command()
    @commands.check(permissions.is_owner)
    async def traceback(self, ctx):
        if not ctx.bot.traceback:
            await ctx.send("No exception has occurred yet.")
            return
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
            await destination.send(embed=embed)

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
                await ctx.send(
                    f"Successfully changed nickname to **{name}**", delete_after=delay
                )
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
        except discord.InvalidArgument:
            await ctx.send(
                "This URL does not contain a useable image", delete_after=delay
            )
        except discord.HTTPException as err:
            await ctx.send(err)
        except TypeError:
            await ctx.send(
                "You need to either provide an image URL or upload one with the command",
                delete_after=delay,
            )


async def setup(bot: Bot) -> None:
    await bot.add_cog(Admin(bot))
