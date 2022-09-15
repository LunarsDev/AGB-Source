from __future__ import annotations

import asyncio
import contextlib
import os
import re
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from index import DEV
from Manager.logger import formatColor
from sentry_sdk import capture_exception
from utils import imports
from utils.default import add_one, log
from utils.embeds import EmbedMaker as Embed

if TYPE_CHECKING:
    from index import Bot

# Regex below for listeners
USER_ID_REG = re.compile("[0-9]{15,19}")
URL_RE = re.compile(
    "http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


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

    @staticmethod
    async def try_to_send_msg_in_a_channel(guild, msg):
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

    @commands.Cog.listener(name="on_message")
    async def add(self, message):
        if message.guild is None:
            return
        if message.author.bot:
            return
        if message.author == self.bot.user:
            return
        if message.channel.id == 929741070777069608:
            if message.content.isdigit():
                new_number = add_one(int(message.content))
                await message.channel.send(new_number)
            else:
                await message.channel.send("Please enter a number")

    @commands.Cog.listener(name="on_message")
    async def agb_support_responder(self, message):
        if message.guild is None:
            return
        if message.guild.id != 975810661709922334:
            return
        if (
            message.channel.id == 986079167944749057
            and message.reference
            and message.reference.resolved.author.bot
        ):
            _message = message.content
            for embed in message.reference.resolved.embeds:
                user_id = USER_ID_REG.findall(embed.footer.text)
            user = self.bot.get_user(user_id[0])
            if user is None:
                user = await self.bot.fetch_user(user_id[0])
            em = Embed(
                title=f"New message From {message.author.name} | {self.bot.user.name} DEV",
                footer="To contact me, just DM the bot",
            )
            with contextlib.suppress(Exception):
                em.set_image(url=message.attachments[0].url)
            if message.attachments is None:
                image_formats = (".jpeg", ".jpg", ".png", ".gif", ".webm", ".webp")
                links = URL_RE.findall(_message)
                for i in links:
                    if i.endswith(image_formats):
                        em.set_image(url=i)
                        _message.replace(i, "")
            em.description = _message
            try:
                await user.send(embed=em)
                await message.add_reaction("✅")
            except discord.Forbidden:
                await message.reply("I could not DM that user.")
                await message.add_reaction("❌")

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
            embed = Embed(title="Invite Created", color=0x00FF00)
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

    #     if ctx.author.bot:
    #         return
    #     # check the command to see if it comes from admin.py
    #     if ctx.command.cog_name == "admin":
    #         with contextlib.suppress(Exception):
    #             await ctx.message.delete()

    @commands.Cog.listener(name="on_command")
    async def logger_shit(self, ctx):

        if not ctx.guild or ctx.author.bot:
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
        used_command = f"{ctx.prefix}{ctx.command.qualified_name}"
        args = tuple(ctx.args) + tuple(ctx.kwargs.values())
        formatted_text = f"{used_command} {args}"

        if await self.bot.is_owner(ctx.author):
            log(
                f"{formatColor('[DEV]', 'bold_red')} {formatColor(ctx.author, 'red')} used command {formatColor(formatted_text, 'grey')}"
            )
        else:
            log(
                f"{formatColor(ctx.author.id, 'grey')} used command {formatColor(formatted_text, 'grey')}"
            )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):

        embed = Embed(title="Removed from a server.", colour=0xFF0000)
        try:
            embed.add_field(
                name=":( forced to leave a server, heres their info:",
                value=f"Server name: `{guild.name}`\n ID `{guild.id}`\n Member Count: `{guild.member_count}`.",
            )

        except Exception as e:
            capture_exception(e)
            return
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        channel = self.bot.get_channel(1012922058591707186)
        if guild.name is None:
            return
        if guild.member_count is None:
            return
        await channel.send(embed=embed)
        # Remove server from database
        db_guild = await self.bot.db.fetch_guild(guild.id)
        if not db_guild:
            log(f"Removed from: {guild.id}")
            return
        await self.bot.db.remove_guild(guild.id)
        log(f"Removed from: {guild.id} | Deleting database entry!")

    @commands.Cog.listener(name="on_guild_join")
    async def MessageSentOnGuildJoin(self, guild):

        nick = f"[/] {self.bot.user.name}"
        try:
            await guild.me.edit(nick=nick)
        except discord.errors.Forbidden:
            return log(f"Unable to change nickname in {guild.id}")
        else:
            log(f"Changed nickname to {nick} in {guild.id}")
        embed = Embed(
            title="Oi cunt, Just got invited to another server.",
            colour=discord.Colour.green(),
        )
        embed.add_field(
            name="Here's the servers' info.",
            value=f"Server name: `{guild.name}`\n ID `{guild.id}`\n Member Count: `{guild.member_count}`.",
        )
        embed.set_thumbnail(url=self.bot.user.avatar)
        channel = self.bot.get_channel(1012922047380344894)
        await channel.send(embed=embed)
        # Add server to database

        db_guild = await self.bot.db.fetch_guild(guild.id)
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

    # from index import EmbedMaker, EmbedMaker, cursor_n, mydb_n
    # for guild in self.guilds:
    #     cursor_n.execute(f"SELECT * FROM public.guilds WHERE guildId = '{guild.id}'")
    #     row_count = cursor_n.rowcount
    #     if row_count == 0:
    #         cursor_n.execute(
    #             f"INSERT INTO public.guilds (guildId) VALUES ('{guild.id}')"
    #         )
    #         mydb_n.commit()
    #         print(f"{guild.id} | Added to database!")
    # testing, ignore this


async def setup(bot: Bot) -> None:
    await bot.add_cog(events(bot))
