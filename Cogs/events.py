from __future__ import annotations

import asyncio
import contextlib
import datetime
import os
import random
from typing import TYPE_CHECKING

from Manager.emoji import Emoji
import aiohttp

# import cronitor
import discord
from discord.ext import commands, tasks
from index import DEV, colors
from Manager.logger import formatColor
from sentry_sdk import capture_exception
from utils import imports
from utils.default import add_one, log

if TYPE_CHECKING:
    from index import Bot


class events(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.config = imports.get("config.json")
        self.db_config = imports.get("db_config.json")
        self.message_cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, commands.BucketType.guild
        )
        self.loop = asyncio.get_event_loop()
        self.last_guild_count = 0
        self.last_user_count = 0

    async def try_to_send_msg_in_a_channel(self, guild, msg):
        for channel in guild.channels:
            with contextlib.suppress(Exception):
                await channel.send(msg)
                break

    @commands.Cog.listener()
    async def on_ready(self):
        discord_version = discord.__version__
        os.system("git pull")
        log(f"Logged in as: {formatColor(str(self.bot.user), 'bold_red')}")
        log(f"Client ID: {formatColor(str(self.bot.user.id), 'bold_red')}")
        log(
            f"Client Server Count: {formatColor(str(len(self.bot.guilds)), 'bold_red')}"
        )
        log(f"Client User Count: {formatColor(str(len(self.bot.users)), 'bold_red')}")
        if len(self.bot.shards) > 1:
            log(
                f"{formatColor(str(self.bot.user), 'bold_red')} is using {formatColor(str(len(self.bot.shards)), 'green')} shards."
            )
        else:
            log(
                f"{formatColor(str(self.bot.user), 'bold_red')} is using {formatColor(str(len(self.bot.shards)), 'green')} shard."
            )
        log(f"Discord Python Version: {formatColor(f'{discord_version}', 'green')}")

    # Check for expired Blacklists
    # @tasks.loop(count=None, minutes=1)
    # @tasks.loop(count=None, minutes=15)
    @tasks.loop(count=None, time=[datetime.time(hour=h, minute=0) for h in range(24)])
    async def blacklist_sweep(self):
        changes = 0
        checked = 0
        total_users = 0
        channel = await self.bot.fetch_channel(1004423443833442335)
        start_embed = discord.Embed(
            title=f"{Emoji.loading} Blackist checks started",
            color=colors.prim,
        )
        await channel.send(embed=start_embed)

        # blacklisted_users = await self.bot.db.fetch_blacklists()
        rows = await self.bot.db.fetch(
            "SELECT * FROM blacklist WHERE blacklisted = 'true'"
        )
        total_users = len(rows)
        data = [dict(row) for row in rows]
        for user in data:
            checked += 1
            db_user = await self.bot.db.fetch_blacklist(user["userid"])

            if not user:
                continue

            if not db_user:
                continue

            if not db_user.blacklistedtill:
                continue

            if not db_user.blacklisted:
                continue

            now = datetime.datetime.now()
            try:
                blacklist_date = datetime.datetime.strptime(
                    str(db_user.blacklistedtill), "%Y-%m-%d %H:%M:%S.%f"
                )
            except Exception:
                blacklist_date = datetime.datetime.strptime(
                    str(db_user.blacklistedtill), "%Y-%m-%d %H:%M:%S.%f+00"
                )
            if blacklist_date < now:
                await self.bot.db.execute(
                    f"UPDATE blacklist SET blacklisted = 'false', blacklistedtill = NULL WHERE userid = '{db_user.user_id}'"
                )
                changes += 1
                clear_embed = discord.Embed(
                    title=f"{Emoji.pencil} Blacklist cleared",
                    description=f"*Cleared blacklist on user: `{db_user.user_id}`*",
                    color=colors.green,
                )

                # await channel.send(embed=clear_embed) # Don't send this. It'll cause problems

        await asyncio.sleep(3)
        comp_embed = discord.Embed(
            title=f"{Emoji.yes} Blacklist checks completed",
            description=f"*Checked: `{checked}/{total_users}`*\n*Cleared: `{changes}`*",
            color=colors.green,
        )

        comp_embed.set_footer(text=f"Scanned {total_users} total entries!")
        await channel.send(embed=comp_embed)

    @tasks.loop(count=None, time=[datetime.time(hour=h, minute=0) for h in range(24)])
    async def presence_loop(self):
        if datetime.datetime.now().month == 10 and datetime.datetime.now().day == 3:
            await self.bot.change_presence(
                activity=discord.Game(name="Happy birthday Motz!")
            )
            return

        statues = self.bot.db._statuses or await self.bot.db.fetch_statuses()
        status_id = random.randint(0, len(statues) - 1)

        status_from_id = self.bot.db.get_status(
            status_id
        ) or await self.bot.db.fetch_status(status_id, cache=True)
        if not status_from_id:
            # should never happen but handling it for linter purposes
            log(f"Status {status_id} not found in database!")
            self.presence_loop.restart()
            return

        db_status = status_from_id.status
        server_count = db_status.replace("{server_count}", str(len(self.bot.guilds)))
        status = server_count.replace("{command_count}", str(len(self.bot.commands)))

        if DEV:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.playing, name="AGB Beta <3"
                )
            )
        else:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.playing, name=status
                )
            )

    @presence_loop.before_loop
    async def delay_task_until_bot_ready(self):
        await asyncio.sleep(5)

    @blacklist_sweep.before_loop
    async def delay_task_until_bot_ready(self):
        await asyncio.sleep(5)

    @commands.Cog.listener(name="on_message")
    async def add(self, message):
        if message.guild is None:
            return
        if message.author.bot:
            return
        if message.author == self.bot.user:
            return
        if message.channel.id == 929741070777069608:
            # check if the message is a number
            if message.content.isdigit():
                number = int(message.content)
                new_number = add_one(number)
                await message.channel.send(new_number)
            else:
                await message.channel.send("Please enter a number")

    # make an event to update channels with the bots server count
    @tasks.loop(count=None, minutes=15)
    async def update_stats(self):
        if not DEV:
            update_guild_count = self.bot.get_channel(968617760756203531)
            update_user_count = self.bot.get_channel(968617853886550056)
            if len(self.bot.guilds) != self.last_guild_count:
                await update_guild_count.edit(
                    name=f"Server Count: {len(self.bot.guilds)}"
                )
                self.last_guild_count = len(self.bot.guilds)
            if len(self.bot.users) != self.last_user_count:
                await update_user_count.edit(
                    name=f"Cached Users: {len(self.bot.users)}"
                )
                self.last_user_count = len(self.bot.users)

    @update_stats.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    @tasks.loop(count=None, seconds=30)
    async def status_page(self):
        # Post AGB status to status page
        if not DEV:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://status.lunardev.group/api/push/8Km8kzfUfH?status=up&msg=OK&ping={round(self.bot.latency * 1000)}"
                ) as r:
                    await r.json()

    @status_page.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    # @commands.Cog.listener(name="on_message")
    # async def add_server_to_db(self, ctx):
    #
    #     # Add server to database
    #     try:
    #         cursor_n.execute(
    #             f"SELECT * FROM public.guilds WHERE guildId = '{ctx.guild.id}'"
    #         )
    #     except Exception:
    #         pass
    #     row_count = cursor_n.rowcount
    #     if row_count == 0:
    #         cursor_n.execute(
    #             f"INSERT INTO guilds (guildId) VALUES ('{ctx.guild.id}')")
    #         mydb_n.commit()
    #         log(
    #             f"New guild detected: {ctx.guild.id} | Added to database!")
    #     else:
    #         return

    # DO NOT PUT THIS IN MERGED EVENT, IT WILL ONLY WORK IN ITS OWN SEPERATE EVENT. **I DO NOT KNOW WHY :D**
    # DO NOT PUT THIS IN MERGED EVENT, IT WILL ONLY WORK IN ITS OWN SEPERATE EVENT. **I DO NOT KNOW WHY :D**
    # XOXOXO, KISSES ~ WinterFe
    @commands.Cog.listener(name="on_command")
    async def command_usage_updater(self, ctx):
        if not DEV:
            bot: Bot = ctx.bot
            db_user = bot.db.get_user(ctx.author.id) or await bot.db.fetch_user(
                ctx.author.id
            )

            if not db_user:
                return
            if not db_user.message_tracking:
                return
            await db_user.modify(usedcmds=db_user.usedcmds + 1)

    # @commands.Cog.listener(name="on_command")
    # async def owner_check(self, ctx):
    #

    #     if ctx.author.id in self.config.owners:
    #         await
    #     else:
    #         pass

    @commands.Cog.listener(name="on_message")
    async def user_check(self, ctx):

        # cursor_n.execute(f"SELECT blacklisted FROM blacklist WHERE userID = {ctx.author.id}")
        # res = cursor_n.fetch()
        # for x in res():
        #     if x[0] == "true":
        #         return print("blacklisted")
        #     else:
        # pass
        if ctx.author.bot:
            return

        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(
            ctx.author.id
        )
        if not db_user:
            await self.bot.db.add_user(ctx.author.id)
            log(
                f"New user detected: {formatColor(str(ctx.author.id), 'green')} | Added to database!"
            )

    @commands.Cog.listener(name="on_message")
    async def guildblacklist(self, message):
        if message.guild is None:
            return
        db_guild_blacklist = self.bot.db.get_guild_blacklist(
            message.guild.id
        ) or await self.bot.db.fetch_guild_blacklist(message.guild.id)
        if not db_guild_blacklist:
            await self.bot.db.add_guild_blacklist(message.guild.id, message.guild.name)
            log(
                f"{formatColor(message.guild.id, 'green')} | Didn't have a blacklist entry, added one!"
            )
        elif db_guild_blacklist.is_blacklisted:
            await self.try_to_send_msg_in_a_channel(
                message.guild,
                f"{message.guild.owner.mention}, This server is blacklisted from using this bot. To understand why and how to remove this blacklist, contact us @ `contact@lunardev.group`.",
            )
            log(
                f"{formatColor(message.guild.name, 'red')} tried to add AGB to a blacklisted server. I have left."
            )
            await message.guild.leave()
            return

    @commands.Cog.listener(name="on_invite_create")
    async def log_invites(self, invite):

        log_channel = self.bot.get_channel(938936724535509012)
        log_server = self.bot.get_guild(755722576445046806)
        if invite.guild.id == log_server.id:
            embed = discord.Embed(title="Invite Created", color=0x00FF00)
            embed.add_field(
                name="Invite Details",
                value=f"Url:{invite.url}, Created:{invite.created_at}, Expires:{invite.expires_at},\nMax Age:{invite.max_age}, Max Uses:{invite.max_uses}, Temporary(?){invite.temporary},\nInviter:{invite.inviter}, Uses:{invite.uses}",
            )
            await log_channel.send(embed=embed)

    @commands.Cog.listener(name="on_command")
    async def blacklist_check(self, ctx):

        if ctx.author.bot:
            return
        db_blacklist_user = self.bot.db.get_blacklist(
            ctx.author.id
        ) or await self.bot.db.fetch_blacklist(ctx.author.id)
        if not db_blacklist_user:
            await self.bot.db.add_blacklist(ctx.author.id, False)
            log(
                f"No blacklist entry detected for: {ctx.author.id} / {ctx.author} | Added to database!"
            )

    @commands.Cog.listener(name="on_command")
    async def badge(self, ctx):

        if ctx.author.bot:
            return

        badge_user = await self.bot.db.fetchrow(
            "SELECT * FROM public.badges WHERE userid = $1", str(ctx.author.id)
        )
        if not badge_user:
            await self.bot.db.execute(
                "INSERT INTO badges (userid) VALUES ($1)", str(ctx.author.id)
            )
            log(
                f"No badge entry detected for: {ctx.author.id} / {ctx.author} | Added to database!"
            )

    @commands.Cog.listener(name="on_command")
    async def eco(self, ctx):

        if ctx.author.bot:
            return

        db_eco_user = self.bot.db.get_economy_user(
            ctx.author.id
        ) or await self.bot.db.fetch_economy_user(ctx.author.id)
        if not db_eco_user:
            await self.bot.db.add_economy_user(ctx.author.id, balance=1000, bank=500)
            log(
                f"No economy entry detected for: {ctx.author.id} / {ctx.author} | Added to database!"
            )

    # @commands.Cog.listener(name="on_command")
    # async def remove_admin_command_uses(self, ctx):
    #     """Deletes the invoked command that comes from admin.py"""

    #     if ctx.author.bot:
    #         return
    #     # check the command to see if it comes from admin.py
    #     if ctx.command.cog_name == "admin":
    #         with contextlib.suppress(Exception):
    #             await ctx.message.delete()

    # @commands.Cog.listener(name="on_member_join")
    # async def autorole(self, member):
    #     log_channel = ()# get the log channel / welcome channel
    #     # . . .
    #     #get the roles they want to give the member
    #     # . . .
    #     await member.add_roles()
    #     await log_channel.send()

    @commands.Cog.listener(name="on_command")
    async def logger_shit(self, ctx):

        if not ctx.guild or ctx.author.bot or ctx.interaction:
            return

        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(
            ctx.author.id
        )
        if db_user and not db_user.message_tracking:
            return

        # if not ctx.guild.chunked:
        #     with contextlib.suppress(Exception):
        #         await ctx.guild.chunk()
        #         log(
        #             f"{formatColor('[CHUNK]', 'bold_red')} Chunked server {formatColor(f'{ctx.guild.id}', 'grey')}"
        #         )

        if await self.bot.is_owner(ctx.author):
            log(
                f"{formatColor('[DEV]', 'bold_red')} {formatColor(ctx.author, 'red')} used command {formatColor(ctx.message.clean_content, 'grey')}"
            )
        else:
            log(
                f"{formatColor(ctx.author.id, 'grey')} used command {formatColor(ctx.message.clean_content, 'grey')}"
            )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):

        embed = discord.Embed(title="Removed from a server.", colour=0xFF0000)
        try:
            embed.add_field(
                name=":( forced to leave a server, heres their info:",
                value=f"Server name: `{guild.name}`\n ID `{guild.id}`\n Member Count: `{guild.member_count}`.",
            )

        except Exception as e:
            capture_exception(e)
            return
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        channel = self.bot.get_channel(769080397669072939)
        if guild.name is None:
            return
        if guild.member_count is None:
            return
        await channel.send(embed=embed)
        # Remove server from database
        db_guild = self.bot.db.get_guild(
            str(guild.id)
        ) or await self.bot.db.fetch_guild(str(guild.id))
        if not db_guild:
            log(f"Removed from: {guild.id}")
            return
        else:
            await self.bot.db.remove_guild(str(guild.id))
            log(f"Removed from: {guild.id} | Deleting database entry!")

    @commands.Cog.listener(name="on_guild_join")
    async def MessageSentOnGuildJoin(self, guild):

        nick = f"[tp!] {self.bot.user.name}"
        try:
            await guild.me.edit(nick=nick)
        except discord.errors.Forbidden:
            return log(f"Unable to change nickname in {guild.id}")
        else:
            log(f"Changed nickname to {nick} in {guild.id}")
        embed = discord.Embed(
            title="Oi cunt, Just got invited to another server.",
            colour=discord.Colour.green(),
        )
        embed.add_field(
            name="Here's the servers' info.",
            value=f"Server name: `{guild.name}`\n ID `{guild.id}`\n Member Count: `{guild.member_count}`.",
        )
        embed.set_thumbnail(url=self.bot.user.avatar)
        channel = self.bot.get_channel(769075552736641115)
        await channel.send(embed=embed)
        # Add server to database

        db_guild = self.bot.db.get_guild(guild.id) or await self.bot.db.fetch_guild(
            guild.id
        )
        if db_guild:
            log(f"New guild joined: {guild.id} | But it was already in the DB")
        else:
            await self.bot.db.add_guild(guild.id)
            log(f"New guild joined: {guild.id} | Added to database!")

        guild_commands = await self.bot.db.fetchrow(
            "SELECT * FROM commands WHERE guild = $1", str(guild.id)
        )
        if not guild_commands:
            await self.bot.db.execute(
                "INSERT INTO commands (guild) VALUES ($1)", str(guild.id)
            )

        # add to blacklist and handle if blacklisted
        db_guild_blacklist = self.bot.db.get_guild_blacklist(
            guild.id
        ) or await self.bot.db.fetch_guild_blacklist(guild.id)
        if not db_guild_blacklist:
            await self.bot.db.add_guild_blacklist(guild.id)
        elif db_guild_blacklist.is_blacklisted:
            await guild.leave()
            log(f"Left {guild.id} / {guild.name} because it was blacklisted")

    @commands.Cog.listener(name="on_guild_join")
    async def add_ppl_on_join(self, guild):
        # check to see if the servers member count is over x people, and if it is, wait to add them until the next hour
        if len(guild.members) > 300:
            await asyncio.sleep(3600)
        # check to see if the guild still exists, if it doesn't, return
        if guild is None:
            return

        # add the users to the database
        for member in guild.members:
            if member.bot:
                return

            db_user = self.bot.db.get_user(member.id) or await self.bot.db.fetch_user(
                member.id
            )
            if not db_user:
                await self.bot.db.add_user(member.id)
                log(
                    f"New user detected: {formatColor(member.id, 'green')} | Added to database!"
                )

    @blacklist_sweep.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    async def cog_unload(self) -> None:
        self.blacklist_sweep.stop()
        log("Blacklist Sweep - Stopped")
        self.presence_loop.stop()
        self.update_stats.stop()

    async def cog_reload(self) -> None:
        self.blacklist_sweep.stop()
        log("Blacklist Sweep - Reloaded")

    async def cog_load(self) -> None:
        self.presence_loop.start()
        self.blacklist_sweep.start()
        self.update_stats.start()
        self.status_page.start()
        log("Blacklist Sweep - Started")


async def setup(bot: Bot) -> None:
    await bot.add_cog(events(bot))
