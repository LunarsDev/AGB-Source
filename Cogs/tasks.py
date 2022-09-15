from __future__ import annotations

import asyncio
import contextlib
import datetime
import random
from typing import TYPE_CHECKING

import aiohttp
import discord
import discordlists
from discord.ext import commands, tasks
from index import DEV, colors
from Manager.emoji import Emoji
from utils import imports
from utils.default import log
from utils.embeds import EmbedMaker as Embed

if TYPE_CHECKING:
    from index import Bot


class Tasks(commands.Cog, name="task"):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.modules = [
            "nsfw_neko_gif",
            "anal",
            "les",
            "hentai",
            "bj",
            "cum_jpg",
            "tits",
            "pussy_jpg",
            "pwankg",
            "classic",
            "spank",
            "boobs",
            "random_hentai_gif",
        ]
        self.config = imports.get("config.json")
        self.db_config = imports.get("db_config.json")
        self.loop = asyncio.get_event_loop()
        self.last_guild_count = 0
        self.last_user_count = 0
        self.config = imports.get("config.json")
        with contextlib.suppress(Exception):
            if not DEV:
                self.api = discordlists.Client(self.bot)
                self.api.set_auth("top.gg", self.config.topgg)
                self.api.set_auth("fateslist.xyz", self.config.fates)
                self.api.set_auth("blist.xyz", self.config.blist)
                self.api.set_auth("discordlist.space", self.config.discordlist)
                self.api.set_auth("discord.bots.gg", self.config.discordbots)
                self.api.set_auth("bots.discordlabs.org",
                                  self.config.discordlabs)
                self.api.start_loop()
        self.get_guilds.start()

    @tasks.loop(count=1)
    async def get_guilds(self):
        for guild in self.bot.guilds:
            guild_commands = await self.bot.db.execute(
                "SELECT * FROM commands WHERE guild = $1", str(guild.id)
            )
            if not guild_commands:
                await self.bot.db.execute(
                    "INSERT INTO commands (guild) VALUES ($1)", str(guild.id)
                )
                log(f"New guild detected: {guild.id} | Added to commands database!")

            db_guild = self.bot.db.get_guild(guild.id) or await self.bot.db.fetch_guild(
                guild.id
            )
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

    @tasks.loop(count=None, time=[datetime.time(hour=h, minute=0) for h in range(24)])
    async def blacklist_sweep(self):
        changes = 0
        checked = 0
        total_users = 0
        channel = await self.bot.fetch_channel(1004423443833442335)
        start_embed = Embed(
            title=f"{Emoji.loading} Blackist checks started",
            color=colors.prim,
            thumbnail=None,
        )
        cum = await channel.send(embed=start_embed)

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
                # clear_embed = Embed(
                #     title=f"{Emoji.pencil} Blacklist cleared",
                #     description=f"*Cleared blacklist on user: `{db_user.user_id}`*",
                #     color=colors.green,
                # )
                # await channel.send(embed=clear_embed) # Don't send this. It'll cause problems

        await asyncio.sleep(3)
        comp_embed = Embed(
            title=f"{Emoji.yes} Blacklist checks completed",
            description=f"*Checked: `{checked}/{total_users}`*\n*Cleared: `{changes}`*",
            color=colors.green,
            thumbnail=None,
        )

        comp_embed.set_footer(text=f"Scanned {total_users} total entries!")
        await cum.edit(embed=comp_embed)

    @tasks.loop(count=None, time=[datetime.time(hour=h, minute=0) for h in range(24)])
    async def presence_loop(self):
        if datetime.datetime.now().month == 10 and datetime.datetime.now().day == 3:
            await self.bot.change_presence(
                activity=discord.Game(name="Happy birthday Motz! | $motzumoto")
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
        server_count = db_status.replace(
            "{server_count}", str(len(self.bot.guilds)))
        status = server_count.replace(
            "{command_count}", str(len(self.bot.commands)))

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
            async with aiohttp.ClientSession() as s, s.get(
                f"https://status.lunardev.group/api/push/8Km8kzfUfH?status=up&msg=OK&ping={round(self.bot.latency * 1000)}"
            ) as r:
                await r.json()

    @status_page.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

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
    await bot.add_cog(Tasks(bot))
