from __future__ import annotations

import asyncio
import contextlib
import datetime
import gc
import random
from typing import TYPE_CHECKING

import discord
import discordlists
from statcord import StatcordClient
from discord.ext import commands, tasks
from index import DEV, colors
from Manager.emoji import Emoji
from utils import imports
from utils.default import log
from utils.embeds import EmbedMaker as Embed

if TYPE_CHECKING:
    from index import AGB


class Tasks(commands.Cog, name="task"):
    def __init__(self, bot: AGB):
        self.bot: AGB = bot
        self.config = imports.get("config.json")
        self.loop = asyncio.get_event_loop()
        self.last_guild_count = 0
        self.last_user_count = 0
        with contextlib.suppress(Exception):
            if not DEV:
                self.api = discordlists.Client(self.bot)
                self.api.set_auth("top.gg", self.config.topgg)
                # self.api.set_auth("fateslist.xyz", self.config.fates)
                self.api.set_auth("blist.xyz", self.config.blist)
                self.api.set_auth("discordlist.space", self.config.discordlist)
                self.api.set_auth("discord.bots.gg", self.config.discordbots)
                self.api.set_auth("bots.discordlabs.org", self.config.discordlabs)
                self.api.start_loop()
                self.key = self.config.statcord
                self.statcord_client = StatcordClient(bot, self.key)
                self.get_guilds.start()

    @tasks.loop(count=1)
    async def get_guilds(self):
        for guild in self.bot.guilds:
            guild_commands = await self.bot.db.execute("SELECT * FROM commands WHERE guild = $1", guild.id)
            if not guild_commands:
                await self.bot.db.execute("INSERT INTO commands (guild) VALUES ($1)", guild.id)
                log(f"New guild detected: {guild.id} | Added to commands database!")

            db_guild = self.bot.db.get_guild(guild.id) or await self.bot.db.fetch_guild(guild.id)
            if not db_guild:
                await self.bot.db.add_guild(guild.id)

                log(f"New guild detected: {guild.id} | Added to guilds database!")

    @get_guilds.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    async def cog_unload(self):
        self.api.stop()
        self.get_guilds.stop()
        self.statcord_client.stop()

    @tasks.loop(time=[datetime.time(hour=h, minute=0) for h in range(24)])
    async def blacklist_sweep(self):
        changes = 0
        checked = 0
        total_users = 0
        start_embed = Embed(
            title=f"{Emoji.loading} Blackist checks started",
            color=colors.prim,
            thumbnail=None,
        )
        sembed = await self.bot.fetch_channel(1004423443833442335)
        await sembed.send(embed=start_embed)

        blacklisted_users = await self.bot.db.fetch_blacklists(blacklisted=True)
        total_users = len(blacklisted_users)
        for user in blacklisted_users:
            checked += 1
            if not user:
                continue

            if not user.blacklistedtill:
                continue

            if not user.blacklisted:
                continue

            now = datetime.datetime.now()
            try:
                blacklist_date = datetime.datetime.strptime(str(user.blacklistedtill), "%Y-%m-%d %H:%M:%S.%f")
            except Exception:
                blacklist_date = datetime.datetime.strptime(str(user.blacklistedtill), "%Y-%m-%d %H:%M:%S.%f+00")
            if blacklist_date < now:
                await user.edit(blacklisted=False, blacklistedtill=None)
                changes += 1

        await asyncio.sleep(3)
        comp_embed = Embed(
            title=f"{Emoji.yes} Blacklist checks completed",
            description=f"*Checked: `{checked}/{total_users}`*\n*Cleared: `{changes}`*",
            color=colors.green,
            thumbnail=None,
        ).set_footer(text=f"Scanned {total_users} total entries!")

        await sembed.edit(embed=comp_embed)

    @tasks.loop(time=[datetime.time(hour=h, minute=0) for h in range(24)])
    async def presence_loop(self):
        if datetime.datetime.now().month == 10 and datetime.datetime.now().day == 3:
            await self.bot.change_presence(activity=discord.Game(name="Happy birthday Motz! | $motzumoto"))
            return

        if datetime.datetime.now().month == 10 and datetime.datetime.now().day == 31:
            await self.bot.change_presence(activity=discord.Game(name="Happy Halloween! 🎃"))
            return

        if datetime.datetime.now().month == 11 and datetime.datetime.now().day == 10:
            await self.bot.change_presence(activity=discord.Game(name="Happy birthday Zoe! | $gothicceyrie"))
            return

        statues = await self.bot.db.fetch_statuses()
        status = random.choice(statues)

        server_count = status.status.replace("{server_count}", str(len(self.bot.guilds)))
        status = server_count.replace("{command_count}", str(len(self.bot.commands)))

        if DEV:
            await self.bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.playing, name="AGB Beta <3")
            )
        else:
            await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=status))

    @presence_loop.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()

    @blacklist_sweep.before_loop
    async def delay_task_until_bot_ready(self):
        await asyncio.sleep(5)

    # make an event to update channels with the bots server count
    @tasks.loop(minutes=30)  # Updated to 30 mins with larger scale in mind
    async def update_stats(self):
        if not DEV:
            if len(self.bot.guilds) != self.last_guild_count:
                await self.bot.get_channel(968617760756203531).edit(name=f"Server Count: {len(self.bot.guilds)}")
                self.last_guild_count = len(self.bot.guilds)
            if len(self.bot.users) != self.last_user_count:
                await self.bot.get_channel(968617853886550056).edit(name=f"Cached Users: {len(self.bot.users)}")
                self.last_user_count = len(self.bot.users)

    @update_stats.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    # @tasks.loop(seconds=58)
    # async def status_page(self):
    #     # Post AGB status to status page
    #     if not DEV:
    #         async with aiohttp.ClientSession() as s, s.get(
    #             f"https://status.lunardev.group/api/push/8Km8kzfUfH?status=up&msg=OK&ping={round(self.bot.latency * 1000)}"
    #         ) as r:
    #             await r.json()

    @tasks.loop(minutes=2)
    async def garbage(self):
        gc.collect()

    @garbage.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    # @status_page.before_loop
    # async def delay_task_until_bot_ready(self):
    #     await self.bot.wait_until_ready()
    #     await asyncio.sleep(5)

    @blacklist_sweep.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

    async def cog_unload(self) -> None:
        if self.api and hasattr(self.api, "close"):
            self.api.close()

        self.blacklist_sweep.stop()
        self.presence_loop.stop()
        self.update_stats.stop()
        self.garbage.stop()

        log("Blacklist Sweep - Stopped")
        log("Presence Loop - Stopped")
        log("Stat updater - Stopped")
        log("Garbage Collector - Stopped")

    async def cog_reload(self) -> None:
        self.blacklist_sweep.stop()
        self.garbage.start()

        log("Blacklist Sweep - Reloaded")

    async def cog_load(self) -> None:
        if not self.config.dev:
            self.presence_loop.start()
            # self.status_page.start()
            self.blacklist_sweep.start()
            self.update_stats.start()
            self.garbage.start()

            log("Presence Loop - Started")
            # log("Status page - Started")
            log("Blacklist Sweep - Started")
            log("Stat updater - Started")
            log("Garbage Collector - Started")


async def setup(bot: AGB) -> None:
    await bot.add_cog(Tasks(bot))
