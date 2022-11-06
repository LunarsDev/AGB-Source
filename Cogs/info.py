from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import random
from typing import Optional, TYPE_CHECKING

from discord.ext import commands
import discord
import os
import inspect

import secrets
from typing import TYPE_CHECKING, List, Optional

import discord
import psutil
import requests
from discord.ext import commands
from discord.ui import Button, View
from index import colors, config
from utils import default, imports, permissions
from utils.common_filters import filter_mass_mentions
from utils.embeds import EmbedMaker as Embed


def list_items_in_english(l: List[str], oxford_comma: bool = True) -> str:
    """
    Produce a list of the items formatted as they would be in an English sentence.
    So one item returns just the item, passing two items returns "item1 and item2" and
    three returns "item1, item2, and item3" with an optional Oxford comma.
    """
    return ", ".join(l[:-2] + [((oxford_comma and len(l) != 2) * "," + " and ").join(l[-2:])])


if TYPE_CHECKING:
    from index import AGB


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


class Information(commands.Cog, name="info"):
    """Info commands for info related things"""

    def __init__(self, bot: AGB):
        """Info commands for info related things"""
        self.bot: AGB = bot
        self.config = imports.get("config.json")
        self.lunar_headers = {f"{config.lunarapi.header}": f"{config.lunarapi.token}"}
        self.process = psutil.Process(os.getpid())

    async def cog_unload(self):
        self.process.stop()

    async def get_or_fetch_user(self, user_id: int):
        user = self.bot.get_user(user_id)
        if user is None:
            user = await self.bot.fetch_user(user_id)

        return user

    def parse_weather_data(self, data):
        data = data["main"]
        del data["humidity"]
        del data["pressure"]
        return data

    def weather_message(self, data, location):
        location = location.title()
        embed = Embed(
            title=f"{location} Weather",
            description=f"Here is the weather data for {location}.",
            color=colors.prim,
        )
        embed.add_field(name="Temperature", value=f"{str(data['temp'])}° F", inline=False)
        embed.add_field(
            name="Minimum temperature",
            value=f"{str(data['temp_min'])}° F",
            inline=False,
        )
        embed.add_field(
            name="Maximum temperature",
            value=f"{str(data['temp_max'])}° F",
            inline=False,
        )
        embed.add_field(name="Feels like", value=f"{str(data['feels_like'])}° F", inline=False)

        return embed

    def error_message(self, location):
        location = location.title()
        return Embed(
            title="Error caught!",
            description=f"There was an error finding weather data for {location}.",
            color=colors.prim,
        )

    async def create_embed(self, ctx, error):
        embed = Embed(title="Error Caught!", color=0xFF0000, description=f"{error}")

        embed.set_thumbnail(url=self.bot.user.avatar)
        await ctx.send(
            embed=embed,
        )

    def generate_embed(self, step: int, results_dict):
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
        embed = Embed(title=title, color=color)
        embed.add_field(name="Ping", value=message_ping)
        embed.add_field(name="Download", value=message_down)
        embed.add_field(name="Upload", value=message_up)
        return embed

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def weather(self, ctx, *, location: str = None):
        """Get weather data for a location
        You can use your zip code or your city name.
        Ex; `/weather City / Zip Code` or `/weather City,Town`"""
        if location is None:
            await ctx.send("Please send a valid location.")
            return

        URL = (
            f"http://api.openweathermap.org/data/2.5/weather?q={location.lower()}&appid={config.Weather}&units=imperial"
        )
        try:
            data = json.loads(requests.get(URL).content)
            data = self.parse_weather_data(data)
            await ctx.send(embed=self.weather_message(data, location))
        except KeyError:
            await ctx.send(embed=self.error_message(location))

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def f2c(self, ctx, *, temp: float, ephemeral: bool = False):
        """Convert Fahrenheit to Celsius

        Args:
            temp (str): The temperature to convert
            ephemeral (optional): make the command visible to you or others. Defaults to False.
        """
        if temp is None:
            await ctx.send("Please send a valid temperature.", ephemeral=True)
            return
        cel = (temp - 32) * (5 / 9)
        await ctx.send(f"{temp}°F is {round(cel, 2)}°C", ephemeral=ephemeral)

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def c2f(self, ctx, *, temp: float, ephemeral: bool = False):
        """Convert Celsius to Fahrenheit

        Args:
            temp (str): the temperature to convert
            ephemeral (optional): make the command visible to you or others. Defaults to False.
        """
        if temp is None:
            await ctx.send("Please send a valid temperature.", ephemeral=True)
            return
        fah = temp * (9 / 5) + 32
        await ctx.send(f"{temp}°C is {round(fah, 2)}°F", ephemeral=ephemeral)

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def vote(self, ctx):
        """Vote for the bot"""
        vote_btn = Button(
            label="Vote",
            style=discord.ButtonStyle.link,
            url=config.Vote,
        )
        support_btn = Button(label="Support server", style=discord.ButtonStyle.link, url=config.Server)
        view = View()
        view.add_item(vote_btn)
        view.add_item(support_btn)

        embed = Embed(title="Thank you!", color=colors.prim, timestamp=ctx.message.created_at)
        embed.set_author(
            name=ctx.bot.user.name,
            icon_url=ctx.bot.user.avatar,
        )
        embed.set_thumbnail(url=ctx.bot.user.avatar)
        embed.add_field(
            name=f"{ctx.bot.user.name} was made with love by: {'' if len(self.config.owners) == 1 else ''}",
            value=", ".join([str(await self.get_or_fetch_user(x)) for x in self.config.owners]),
            inline=False,
        )
        embed.set_thumbnail(url=ctx.author.avatar)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def ping(self, ctx, ephemeral: bool = False):
        """Ping the bot

        Args:
            ephemeral (optional): make the command visible to you or others. Defaults to False.
        """
        await ctx.typing(ephemeral=ephemeral)
        try:
            await Embed(
                title="Ping :ping_pong:",
                description=f"{round(self.bot.latency * 1000)}ms",
                author=(ctx.author.name, ctx.author.avatar),
                thumbnail=None,
            ).send(ctx, ephemeral=ephemeral)
        except Exception:
            await Embed(
                title="Ping",
                description="Ping cannot be calculated right now.",
                author=(ctx.author.name, ctx.author.avatar),
                thumbnail=None,
            ).send(ctx, ephemeral=ephemeral)

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def invite(self, ctx, ephemeral: bool = False):
        """Get an invite to the bot"""
        invite_btn = Button(
            label="Click here to invite me!",
            style=discord.ButtonStyle.link,
            url=config.Invite,
        )
        support_btn = Button(label="Support server", style=discord.ButtonStyle.link, url=config.Server)
        view = View()
        view.add_item(invite_btn)
        view.add_item(support_btn)
        await ctx.send(view=view, ephemeral=ephemeral)

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def password(self, ctx, nbytes: int = 40):
        """Generates a random password string for you
        This returns a random URL-safe text string, containing nbytes random bytes.
        The text is Base64 encoded, so on average each byte results in approximately 1.3 characters.
        """
        if nbytes not in range(3, 1001):
            return await ctx.send("I only accept any numbers between 3-1000")
        if hasattr(ctx, "guild") and ctx.guild is not None:
            await ctx.send(f"Alright, lemme send you this randomly generated password {ctx.author.mention}.")
        await ctx.author.send(
            f"🎁 **Here is your password:**\n{secrets.token_urlsafe(nbytes)}\n\n**You could actually use this password for things too since this was completely randomly generated.**"
        )

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def stats(self, ctx, ephemeral: bool = False):
        """Get some information about the bot"""
        await ctx.channel.typing()
        fetching = await ctx.send("Fetching stats...", ephemeral=ephemeral)
        num = 0
        for guild in self.bot.guilds:
            for channel in guild.channels:
                num += 1
        discord_version = discord.__version__
        chunked = []
        for guild in self.bot.guilds:
            if guild.chunked:
                chunked.append(guild)
        ramUsage = self.process.memory_full_info().rss / 1024**2
        intervals = (
            ("w", 604800),  # 60 * 60 * 24 * 7
            ("d", 86400),  # 60 * 60 * 24
            ("h", 3600),  # 60 * 60
            ("m", 60),
            ("s", 1),
        )

        def display_time(seconds, granularity=2):
            result = []

            for name, count in intervals:
                if value := seconds // count:
                    seconds -= value * count
                    if value == 1:
                        name = name.rstrip("s")
                    result.append(f"{value}{name}")
            return " ".join(result[:granularity])

        #                 # str(await lunar_api_stats(self)).partition(".")

        #                 if r.status == 200:
        #                     return display_time(int(str(seconds).partition(".")[0]), 4)
        #                 else:
        #                     return "❌ API Error"
        #         except Exception as e:
        #             capture_exception(e)
        #             return "❌ API Error"

        #                 # str(await lunar_api_stats(self)).partition(".")

        #                 return cores if r.status == 200 else "❌ API Error"
        #         except Exception as e:
        #             capture_exception(e)
        #             return "❌ API Error"

        #                 # str(await lunar_api_stats(self)).partition(".")

        #                 return f"{int(files):,}" if r.status == 200 else "❌ API Error"
        #         except Exception as e:
        #             capture_exception(e)
        #             return "❌ API Error"

        #                 # str(await lunar_api_stats(self)).partition(".")

        #                 if r.status == 200:
        #                     return display_time(int(str(uptime).partition(".")[0]), 4)
        #                 else:
        #                     return "❌ API Error"
        #         except Exception as e:
        #             capture_exception(e)
        #             return "❌ API Error"

        async def line_count(self):
            await ctx.channel.typing()
            total = 0
            file_amount = 0
            ENV = "env"

            for path, _, files in os.walk("."):
                for name in files:
                    file_dir = str(pathlib.PurePath(path, name))
                    # ignore env folder and not python files.
                    if not name.endswith(".py") or ENV in file_dir:
                        continue
                    if "__pycache__" in file_dir:
                        continue
                    if ".git" in file_dir:
                        continue
                    if ".local" in file_dir:
                        continue
                    if ".config" in file_dir:
                        continue
                    if "?" in file_dir:
                        continue
                    if ".cache" in file_dir:
                        continue
                    file_amount += 1
                    with open(file_dir, "r", encoding="utf-8") as file:
                        for line in file:
                            if not line.strip().startswith("#") or not line.strip():
                                total += 1
            return f"{total:,} lines, {file_amount:,} files"

        if len(chunked) == len(self.bot.guilds):
            all_chunked = "All servers are cached!"
        else:
            all_chunked = f"{len(chunked)} / {len(self.bot.guilds)} servers are cached"
        if self.bot.shard_count == 1:
            shards = "1 shard"
        else:
            shards = f"{self.bot.shard_count:,} shards"
        made = discord.utils.format_dt(self.bot.user.created_at, style="R")
        total_used_cmds = f"{sum(x.used_commands for x in await self.bot.db.fetch_users()):,}"
        uptime = discord.utils.format_dt(self.bot.launch_time, style="R")
        cpu = psutil.cpu_percent()
        cpu_box = default.draw_box(round(cpu), ":blue_square:", ":black_large_square:")
        ramlol = round(ramUsage) // 10
        ram_box = default.draw_box(ramlol, ":blue_square:", ":black_large_square:")
        GUILD_MODAL = f"""{len(self.bot.guilds)} Guilds are seen,\n{default.commify(num)} channels,\nand {default.commify(len(self.bot.users))} users."""
        PERFORMANCE_MODAL = f"""
        `RAM Usage: {ramUsage:.2f}MB / 1GB scale`
        {ram_box}
        `CPU Usage: {cpu}%`
        {cpu_box}"""
        BOT_INFO = f"""{all_chunked}\nLatency: {round(self.bot.latency * 1000, 2)}ms\nShard count: {shards}\nLoaded CMDs: {len(set(self.bot.walk_commands()))}\nTotal used commands: {total_used_cmds}\nMade: {made}\n{await line_count(self)}\nLaunched {uptime}"""
        # API_INFO = f"""API Uptime: {API_UPTIME}\nCPU Cores: {await lunar_api_cores(self)}\nTotal Images: {await lunar_api_files(self)}"""
        # SYS_INFO = f"""System Uptime: {await lunar_system_uptime(self)}\nCPU Cores: {await lunar_api_cores(self)}"""

        embed = Embed(
            color=colors.prim,
            description=f"[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate})",
        )
        embed.set_thumbnail(url=self.bot.user.avatar)
        embed.add_field(name="Performance Overview", value=PERFORMANCE_MODAL, inline=False)
        embed.add_field(
            name="Guild Information",
            value=GUILD_MODAL,
            inline=False,
        )

        embed.add_field(name="AGB Information", value=BOT_INFO, inline=False)
        embed.set_image(url="https://media.discordapp.net/attachments/940897271120273428/954507474394808451/group.gif")
        embed.set_footer(text=f"Made with ❤️ by the Lunar Development team.\nLibrary used: Discord.py{discord_version}")
        await fetching.edit(content="Almost done...")
        await fetching.edit(
            content=f"Stats about **{self.bot.user}** | **{self.config.version}**",
            embed=embed,
        )

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    async def say(self, ctx, *, message: str):
        """Speak through the bot uwu"""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await ctx.send(filter_mass_mentions(message))
        # if random.seed(1, 5) == 1:
        #     await ctx.send(
        #         "You can also say an embed with `/embed_say`!",
        #         files=[
        #             discord.File("imgs/withimage.gif"),
        #             discord.File("imgs/withoutimage.gif"),
        #         ],
        #     )

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    async def embedsay(self, ctx, title, desc, colorhex: str = None, thumbnail=None):
        """Embedded say command
        To make a new line, type `\\n` in the description."""
        if "\\n" in desc:
            desc = desc.replace("\\n", "\n")
        if "\\n " in desc:
            desc = desc.replace("\\n ", "\n")
        colorhex = int(colorhex, 16) if colorhex is not None else 0
        if colorhex is None:
            colorhex = colors.prim
        if thumbnail is None:
            thumbnail = (
                "https://cdn.discordapp.com/icons/755722576445046806/822bafdc8285f1729af731b4d320c5e5.png?size=1024"
            )
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await Embed(title=title, description=desc, color=colorhex, thumbnail=thumbnail).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    async def policy(self, ctx):
        """Privacy Policy"""
        embed = Embed(color=colors.prim, timestamp=ctx.message.created_at)
        embed.set_author(
            name=ctx.bot.user.name,
            icon_url=ctx.bot.user.avatar,
        )
        embed.set_thumbnail(url=ctx.bot.user.avatar)
        embed.add_field(
            name="Direct Link To The Privacy Policy ",
            value="[Click Here](https://gist.github.com/Motzumoto/2f25e114533a35d86078018fdc2dd283)",
            inline=True,
        )

        embed.add_field(
            name="Backup To The Policy ",
            value="[Click Here](https://pastebin.com/J5Zj8U1q)",
            inline=False,
        )

        embed.add_field(
            name="Support If You Have More Questions",
            value=f"[Click Here To Join]({config.Server})",
            inline=True,
        )

        embed.add_field(
            name=f"{ctx.bot.user.name} was made with love by: {'' if len(self.config.owners) == 1 else ''}",
            value=", ".join([str(await self.bot.fetch_user(x)) for x in self.config.owners]),
            inline=False,
        )
        embed.add_field(
            name="Look at these",
            value=f"[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate}) ",
            inline=False,
        )
        await ctx.send(
            embed=embed,
        )

    # taken from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/meta.py#L402-L443
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    async def source(self, ctx, *, command: str = None):
        """Displays the code to commands and the source of this bot."""
        source_url = "https://github.com/LunarsDev/AGB-Source"
        branch = "master"
        if command is None:
            return await ctx.send(source_url)

        if command == "help":
            src = type(self.bot.help_command)
            filename = inspect.getsourcefile(src)
        else:
            obj = self.bot.get_command(command.replace(".", " "))
            if obj is None:
                return await ctx.send("Could not find command.")

            # since we found the command we're looking for, presumably anyway, let's
            # try to access the code itself
            src = obj.callback.__code__
            filename = src.co_filename

        lines, firstlineno = inspect.getsourcelines(src)
        if filename is None:
            return await ctx.send("Could not find source for command.")

        else:
            location = os.path.relpath(filename).replace("\\", "/")
        final_url = f"<{source_url}/blob/{branch}/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1}>"
        await ctx.send(final_url)

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    async def profile(
        self,
        ctx: commands.Context,
        user: MemberConverter = None,
    ):
        """Show your user profile"""
        user = user or ctx.author

        msg = await ctx.send("Fetching...")

        usereco = await self.bot.db.getch("usereco", user.id)
        if not usereco:
            await msg.edit(content=f"~~{msg.content}~~ User has no profile.")
            return

        user_balance = f"${usereco.balance:,}"
        user_bank = f"${usereco.bank:,}"

        # TODO: will do later... like when needed....
        badges = ""
        # cached_badges = self.bot.db._badges
        # fetched_badges = (
        #    list(cached_badges.values())
        #    if cached_badges
        #    else await self.bot.db.fetch_badges()
        # )

        #    badges_list = [
        #    badge for badge in fetched_badges if badge.has_badge(user.id) is True
        # ]
        # badges = " ".join(b.name for b in badges_list)

        db_user = self.bot.db.get_user(user.id) or await self.bot.db.fetch_user(user.id)
        if db_user:
            used_commands = db_user.used_commands + 1
            bio = db_user.bio
        else:
            used_commands = 1
            bio = None

        # **Profile Info**\nBadges: {badges}\n\n
        description = f"""{badges}\n\n**💰 Economy Info**
		`Balance`: **{user_balance}**
		`Bank`: **{user_bank}**
		
		**📜 Misc Info**
		`Commands Used`: **{used_commands}**
		
		**<:users:770650885705302036> Overview**
		`User Bio`\n{bio}"""

        embed = Embed(title=str(user), color=colors.prim, description=description)
        embed.set_thumbnail(url=user.display_avatar)
        await msg.edit(content=None, embed=embed)

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    async def bio(self, ctx, *, bio: Optional[str] = None):
        """Set your profile bio"""
        if bio is None:
            return await ctx.send_help(ctx.command)

        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(ctx.author.id)
        if not db_user:
            await ctx.send("You have no profile..?")
            return

        db_user = await db_user.edit(bio=bio)
        embed = Embed(
            title="User Bio",
            color=colors.prim,
            description=f"Your bio has been set to: `{db_user.bio}`",
        )
        await ctx.send(
            embed=embed,
        )

    @commands.hybrid_group()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def opt(self, ctx):
        """Opt in or out of bots message history fetching"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))
            return
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @opt.command(name="out")
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def _out(self, ctx):
        """Opt out of the bot's message history fetching"""
        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(ctx.author.id)
        if not db_user or not db_user.message_tracking:
            await ctx.send("You are already opted out of message tracking!")
            return
        await db_user.modify(msgtracking=False)
        await Embed(description="You have opted out of message tracking!", thumbnail=None).send(ctx, ephemeral=True)

    @opt.command(name="in")
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def _in(self, ctx):
        """Opt in to the bot's message history fetching"""
        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(ctx.author.id)
        if not db_user:
            db_user = await self.bot.db.add_user(ctx.author.id)
        if db_user.message_tracking:
            await ctx.send("You are already opted into message tracking!")
            return
        await db_user.edit(msgtracking=True)
        await Embed(description="You have opted into message tracking", thumbnail=None).send(ctx, ephemeral=True)

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def timestamp(self, ctx, date: str, time: str = None):
        """
        Displays given time in all Discord timestamp formats.
        Example: 12/22/2005 02:20:00
        You don't need to specify time. It will automatically round it to midnight.
        """
        if time is None:
            time = "00:00:00"
        hint = (
            "\nRemember you do not have to provide a time, it automatically sets to 12:00:00"
            if random.randint(1, 10) == 5
            else ""
        )
        try:
            datetime_object = datetime.datetime.strptime(f"{date} {time}", "%m/%d/%Y %H:%M:%S")
            uts = str(datetime_object.timestamp())[:-2]
        except ValueError as e:
            await Embed(
                title="Try again.",
                description=f"{date} {time} doesn't match format `month/day/year hour/minute/second`. Example: `/timestamp 10/03/2004 03:50:02`{hint}",
            ).send(ctx)
            return
        await Embed(
            title="Here's the timestamp you asked for",
            color=colors.prim,
            description=f"""
				Short Time: <t:{uts}:t> | \\<t:{uts}:t>
				Long Time: <t:{uts}:T> | \\<t:{uts}:T>
				Short Date: <t:{uts}:d> | \\<t:{uts}:d>
				Long Date: <t:{uts}:D> | \\<t:{uts}:D>
				Short Date/Time: <t:{uts}:f> | \\<t:{uts}:f>
				Long Date/Time: <t:{uts}:F> | \\<t:{uts}:F>
				Relative Time: <t:{uts}:R> | \\<t:{uts}:R>
				""",
        ).send(ctx)


async def setup(bot: AGB) -> None:
    await bot.add_cog(Information(bot))
