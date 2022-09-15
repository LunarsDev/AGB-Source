from __future__ import annotations

import asyncio
import contextlib
import functools
import heapq
import io
import random
import unicodedata
from io import BytesIO
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

import aiohttp
import asyncpraw
import discord
import lunarapi
import matplotlib
import matplotlib.pyplot as plt
import nekos
from discord.ext import commands
from index import BID, CHAT_API_KEY, Website, colors, config
from sentry_sdk import capture_exception
from utils import imports, permissions
from utils.checks import voter_only
from utils.common_filters import filter_mass_mentions
from utils.default import log
from utils.embeds import EmbedMaker as Embed
from utils.errors import ChatbotFailure

try:
    import cairosvg
except Exception as e:
    capture_exception(e)

svg_convert = "cairo"

matplotlib.use("agg")

plt.switch_backend("agg")

if TYPE_CHECKING:
    from index import Bot


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
            raise commands.BadArgument(
                f"{len(members)} members found, please be more specific."
            ) from e


class Fun(commands.Cog, name="fun"):
    """Fun / Game commands"""

    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.channels = {}
        global Utils
        Utils = self.bot.get_cog("Utils")
        self.session = aiohttp.ClientSession()
        if svg_convert == "cairo":
            log("enlarge: Using CairoSVG for svg conversion.")
        elif svg_convert == "wand":
            log("enlarge: Using wand for svg conversion.")
        else:
            log(
                "enlarge: Failed to import svg converter. Standard emoji will be limited to 72x72 png."
            )
        self.config = imports.get("config.json")
        self.ttt_games = {}
        self.params = {
            "mode": "random",
        }
        self.reddit = asyncpraw.Reddit(
            client_id=self.config.rID,
            client_secret=self.config.rSecret,
            password=self.config.rPass,
            user_agent="asyncprawpython",
            username=self.config.rUser,
        )
        self.ballresponse = [
            "It is certain.",
            "It is decidedly so.",
            "Without a doubt.",
            "Yes definitely.",
            "You may rely on it.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            "send hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don't count on it.",
            "My send is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful.",
            "Up to you, but I guess.",
            "No.",
            "Absolutely not.",
            "Nahh.",
            "Nope.",
            "No way.",
            "Not a chance.",
            "Not in a million years.",
            "Probably",
            "Maybe",
            "Maybe not",
            "Not sure",
            "Ask again later",
            r"¯\_(ツ)_/¯",
        ]

    # async def cog_load(self):
    #     # self.autochatbot_channel_existence.start()

    async def cog_unload(self):
        self.session.stop()
        self.reddit.stop()
        self.ttt_games.stop()
        self.params.stop()
        self.bot.loop.create_task(self.session.close())

    def format_help_for_context(self, ctx):
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    @staticmethod
    async def cap_change(message: str) -> str:
        return "".join(
            char.upper() if (value := random.choice([True, False])) else char.lower()
            for char in message
        )

    @staticmethod
    def get_actors(bot, offender, target):
        return (
            {"id": bot.id, "nick": bot.display_name, "formatted": bot.mention},
            {
                "id": offender.id,
                "nick": offender.display_name,
                "formatted": f"<@{offender.id}>",
            },
            {"id": target.id, "nick": target.display_name, "formatted": target.mention},
        )

    @staticmethod
    async def fetch_channel_history(
        channel: discord.TextChannel,
        animation_message: discord.Message,
        messages: int,
    ) -> List[discord.Message]:
        """Fetch the history of a channel while displaying an status message with it"""
        animation_message_deleted = False
        history = []
        history_counter = 0
        async for msg in channel.history(limit=messages):
            # check if the msg author is a bot
            if msg.author.bot:
                continue
            history.append(msg)
            history_counter += 1
            if history_counter % 250 == 0:
                new_embed = Embed(
                    title=f"Fetching messages from #{channel.name}",
                    description=f"This might take a while...\n{history_counter}/{messages} messages gathered",
                    colour=colors.prim,
                )
                if channel.permissions_for(channel.guild.me).send_messages:
                    await channel.typing()
                if animation_message_deleted is False:
                    try:
                        await animation_message.edit(embed=new_embed)
                    except discord.NotFound:
                        animation_message_deleted = True
        return history

    @staticmethod
    def calculate_member_perc(history: List[discord.Message]) -> dict:
        """Calculate the member count from the message history"""
        msg_data = {"total_count": 0, "users": {}}
        for msg in history:
            # Name formatting
            if len(msg.author.display_name) >= 20:
                short_name = f"{msg.author.display_name[:20]}...".replace("$", "\\$")
            else:
                short_name = (
                    msg.author.display_name.replace("$", "\\$")
                    .replace("_", "\\_ ")
                    .replace("*", "\\*")
                )
            whole_name = f"{short_name}#{msg.author.discriminator}"
            if msg.author.bot:
                pass
            elif whole_name in msg_data["users"]:
                msg_data["users"][whole_name]["msgcount"] += 1
                msg_data["total_count"] += 1
            else:
                msg_data["users"][whole_name] = {"msgcount": 1}
                msg_data["total_count"] += 1
        return msg_data

    @staticmethod
    def calculate_top(msg_data: dict) -> Tuple[list, int]:
        """Calculate the top 20 from the message data package"""
        for usr in msg_data["users"]:
            pd = float(msg_data["users"][usr]["msgcount"]) / float(
                msg_data["total_count"]
            )
            msg_data["users"][usr]["percent"] = round(pd * 100, 1)
        top_twenty = heapq.nlargest(
            20,
            [
                (x, msg_data["users"][x][y])
                for x in msg_data["users"]
                for y in msg_data["users"][x]
                if (y == "percent" and msg_data["users"][x][y] > 0)
            ],
            key=lambda x: x[1],
        )
        others = 100 - sum(x[1] for x in top_twenty)
        return top_twenty, others

    @staticmethod
    async def create_chart(
        top, others, channel_or_guild: Union[discord.Guild, discord.TextChannel]
    ):
        plt.clf()
        sizes = [x[1] for x in top]
        labels = [f"{x[0]} {x[1]:g}%" for x in top]
        if len(top) >= 20:
            sizes += [others]
            labels += [f"Others {others:g}%"]
        if len(channel_or_guild.name) >= 19:
            if isinstance(channel_or_guild, discord.Guild):
                channel_or_guild_name = f"{channel_or_guild.name[:19]}..."
            else:
                channel_or_guild_name = f"#{channel_or_guild.name[:19]}..."
        else:
            channel_or_guild_name = channel_or_guild.name
        title = plt.title(f"Stats in {channel_or_guild_name}", color="white")
        title.set_va("top")
        title.set_ha("center")
        plt.gca().axis("equal")
        colors = [
            "r",
            "darkorange",
            "gold",
            "y",
            "olivedrab",
            "green",
            "darkcyan",
            "mediumblue",
            "darkblue",
            "blueviolet",
            "indigo",
            "orchid",
            "mediumvioletred",
            "crimson",
            "chocolate",
            "yellow",
            "limegreen",
            "forestgreen",
            "dodgerblue",
            "slateblue",
            "gray",
        ]
        pie = plt.pie(sizes, colors=colors, startangle=0)
        plt.legend(
            pie[0],
            labels,
            bbox_to_anchor=(0.7, 0.5),
            loc="center",
            fontsize=10,
            bbox_transform=plt.gcf().transFigure,
            facecolor="#ffffff",
        )
        plt.subplots_adjust(left=0.0, bottom=0.1, right=0.45)
        image_object = BytesIO()
        plt.savefig(image_object, format="PNG", facecolor="#36393E")
        image_object.seek(0)
        return image_object

    @staticmethod
    async def get_kitties() -> str:
        if random.randint(1, 3) == 1:
            url = nekos.cat()
        else:
            async with aiohttp.ClientSession() as session, session.get(
                "https://api.thecatapi.com/v1/images/search"
            ) as r:
                data = await r.json()
                url = data[0]["url"]
        return url

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
        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(
            ctx.author.id
        )
        if not db_user or not db_user.message_tracking:
            await ctx.send("You are already opted out of message tracking!")
            return
        await db_user.modify(msgtracking=False)
        await ctx.send("You have opted out of message tracking!")

    @opt.command(name="in")
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def _in(self, ctx):
        """Opt in to the bot's message history fetching"""
        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(
            ctx.author.id
        )
        if not db_user:
            db_user = await self.bot.db.add_user(ctx.author.id)
        if db_user.message_tracking:
            await ctx.send("You are already opted into message tracking!")
            return
        await db_user.modify(msgtracking=True)
        await ctx.send("You have opted into message tracking")

    @commands.guild_only()
    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 300, commands.BucketType.guild)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def chatchart(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
        messages: int = 10000,
    ):
        """
        Generates a pie chart, representing the last 10000 messages in the specified channel.
        This command has a server wide cooldown of 300 seconds.
        """
        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(
            ctx.author.id
        )
        if not db_user or not db_user.message_tracking:
            await ctx.send(
                "You are opted out of message tracking!\nTo opt back in, use `/optin`"
            )
            return
        channel = channel or ctx.channel  # type: ignore
        # --- Early terminations
        if channel.permissions_for(ctx.message.author).read_messages is False:
            return await ctx.send("You're not allowed to access that channel.")
        if channel.permissions_for(ctx.guild.me).read_messages is False:
            return await ctx.send("I cannot read the history of that channel.")
        if messages < 5:
            return await ctx.send("Theres not enough messages to show dummy")
        message_limit = 10000
        messages = message_limit
        embed = Embed(
            title=f"Fetching messages from #{channel.name}",
            description="This might take a while...",
            colour=colors.prim,
        )
        loading_message = await ctx.send(
            embed=embed,
        )
        try:
            history = await self.fetch_channel_history(
                channel, loading_message, messages
            )
        except discord.errors.Forbidden:
            with contextlib.suppress(discord.NotFound):
                await loading_message.delete()
            return await ctx.send("No permissions to read that channel.")
        msg_data = self.calculate_member_perc(history)
        # If no members are found.
        if len(msg_data["users"]) == 0:
            with contextlib.suppress(discord.NotFound):
                await loading_message.delete()
            return await ctx.send(
                f"Only bots have sent messages in {channel.mention} or I can't read message history."
            )
        top_twenty, others = self.calculate_top(msg_data)
        chart = await self.create_chart(top_twenty, others, channel)
        with contextlib.suppress(discord.NotFound):
            await loading_message.delete()
        await ctx.send(file=discord.File(chart, "chart.png"))

    @commands.guild_only()
    @commands.hybrid_command(aliases=["guildchart"])
    @permissions.dynamic_ownerbypass_cooldown(1, 3600, commands.BucketType.guild)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def serverchart(self, ctx, messages: int = 1000):
        """
        Generates a pie chart, representing the last 1000 messages from every allowed channel in the server.
        As example:
        For each channel that the bot is allowed to scan. It will take the last 1000 messages from each channel.
        And proceed to build a chart out of that.
        This command has a global serverwide cooldown of 3600 seconds.
        """
        db_user = self.bot.db.get_user(ctx.author.id) or await self.bot.db.fetch_user(
            ctx.author.id
        )
        if not db_user or not db_user.message_tracking:
            await ctx.send(
                "You are opted out of message tracking!\nTo opt back in, use `/optin`"
            )
            return
        if messages < 5:
            return await ctx.send("Don't be silly.")
        channel_list = []
        for channel in ctx.guild.text_channels:
            channel: discord.TextChannel
            if channel.permissions_for(ctx.message.author).read_messages is False:
                continue
            if channel.permissions_for(ctx.guild.me).read_messages is False:
                continue
            channel_list.append(channel)
        if not channel_list:
            return await ctx.send(
                "There are no channels to read... How did this happen?"
            )
        embed = Embed(
            description="Fetching messages from the entire server this **will** take a while.",
            colour=colors.prim,
        )
        global_fetch_message = await ctx.send(
            embed=embed,
        )
        global_history = []
        for channel in channel_list:
            embed = Embed(
                title=f"Fetching messages from #{channel.name}",
                description="This might take a while...",
                colour=colors.prim,
            )
            loading_message = await ctx.send(
                embed=embed,
            )
            try:
                history = await self.fetch_channel_history(
                    channel, loading_message, messages
                )
                global_history += history
                await loading_message.delete()
            except discord.errors.Forbidden:
                try:
                    await loading_message.delete()
                except discord.NotFound:
                    continue
            except discord.NotFound:
                try:
                    await loading_message.delete()
                except discord.NotFound:
                    continue
        msg_data = self.calculate_member_perc(global_history)
        # If no members are found.
        if len(msg_data["users"]) == 0:
            with contextlib.suppress(discord.NotFound):
                await global_fetch_message.delete()
            return await ctx.send(
                "Only bots have sent messages in this server... hgseiughsuighes..."
            )
        top_twenty, others = self.calculate_top(msg_data)
        chart = await self.create_chart(top_twenty, others, ctx.guild)
        with contextlib.suppress(discord.NotFound):
            await global_fetch_message.delete()
        await ctx.send(file=discord.File(chart, "chart.png"))

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def enlarge(self, ctx, emoji: str = None):
        """Post a large .png of an emoji"""
        if emoji is None:
            await ctx.send("Please provide an emoji.")
        else:
            convert = False
            if emoji[0] == "<":
                # custom Emoji
                try:
                    name = emoji.split(":")[1]
                except IndexError:
                    await ctx.send("thats not even an emote bruh")
                    return
                emoji_name = emoji.split(":")[2][:-1]
                if emoji.split(":")[0] == "<a":
                    # animated custom emoji
                    url = f"https://cdn.discordapp.com/emojis/{emoji_name}.gif"
                    name += ".gif"
                else:
                    url = f"https://cdn.discordapp.com/emojis/{emoji_name}.png"
                    name += ".png"
            else:
                chars = []
                name = []
                for char in emoji:
                    chars.append(hex(ord(char))[2:])
                    try:
                        name.append(unicodedata.name(char))
                    except ValueError:
                        # Sometimes occurs when the unicodedata library cannot
                        # resolve the name, however the image still exists
                        name.append("none")
                name = "_".join(name) + ".png"
                if len(chars) == 2 and "fe0f" in chars:
                    # remove variation-selector-16 so that the appropriate url can be built without it
                    chars.remove("fe0f")
                if "20e3" in chars:
                    # COMBINING ENCLOSING KEYCAP doesn't want to play nice either
                    chars.remove("fe0f")
                if svg_convert is not None:
                    url = "https://twemoji.maxcdn.com/2/svg/" + "-".join(chars) + ".svg"
                    convert = True
                else:
                    url = (
                        "https://twemoji.maxcdn.com/2/72x72/" + "-".join(chars) + ".png"
                    )
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    await ctx.send("Emoji not found.")
                    return
                img = await resp.read()
            if convert:
                task = functools.partial(Fun.generate, img)
                task = self.bot.loop.run_in_executor(None, task)
                try:
                    img = await asyncio.wait_for(task, timeout=15)
                except asyncio.TimeoutError:
                    await ctx.send("Image creation timed out.")
                    return
            else:
                img = io.BytesIO(img)
            await ctx.send(file=discord.File(img, name))

    @staticmethod
    def generate(img):
        if svg_convert != "cairo":
            return io.BytesIO(img)
        kwargs = {"parent_width": 1024, "parent_height": 1024}
        return io.BytesIO(cairosvg.svg2png(bytestring=img, **kwargs))

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def chatrevive(self, ctx):
        responces = [
            "Who is your favorite superhero? ",
            "Who is the most powerful superhero and why?",
            "Who created me?",
            "You don't WHAT at night? (minecraft reference)",
            "Whats your favorite song?",
            "What would the perfect weekend be? ",
            "What is your favorite video game? ",
            "What is your favorite food? ",
            "If you could have any car in the world what would it be? ",
            "What's better, tiktok or vine? ",
            "What's better, console or PC? ",
            "What do you prefer: online school or being in school? ",
            "What is your favorite sport? ",
            "Who is your favorite pro player?",
            f"Dyno, Mee6, or me? ({self.bot.user.name})",
            "Who is the best staff in this server? ",
            "iPhone or Android and why? ",
            "Xbox or Playstation? ",
            "What is your dream job? ",
            "Would you rather live by the beach or the mountains? ",
            "Which is better: cookies or ice cream? ",
            "Minecraft or Roblox? ",
            "TV show or movies? ",
            "Book or movie? ",
            "What is your favorite way to pass time? ",
            "Whats the most addicting app? ",
            "What is the funniest joke you know? ",
            "Who is your favorite actor? ",
            "What is the strangest dream you have had? ",
            "Where is the most beautiful place you have been? ",
            "What animal or insect do you wish humans could eradicate and why? ",
            "What is the most disgusting habit some people have? ",
            "What is the silliest fear you have? ",
            "Who has the smallest pp in this server?",
            "Who is the funniest person you've met? ",
            "What weird or useless talent do you have? ",
            "What's the most underrated (or overrated) TV show? ",
        ]
        say = random.choice(responces)
        await Embed(
            title="Chat Revive",
            description=say,
            thumbnail=None,
        ).send(ctx)

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def coinflip(self, ctx):
        sides = ["**Heads**", "**Tails**"]
        randomcoin = random.choice(sides)
        if random.randint(1, 6000) == 1:
            await Embed(
                title="Coinflip",
                description="**The coin landed on its side!**",
                footer="You got a 1/6000 chance of getting this!",
            )
        else:
            await Embed(
                title="Coinflip",
                description=randomcoin,
                thumbnail=None,
            ).send(ctx)

    #     if len(text) > 25:
    #         return await ctx.send(
    #             "The file you tried to render was over 25 characters! Please try again!"
    #         )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    #     ).set_image(url="attachment://supreme.png")
    #     image = discord.File(
    #         await (await self.alex_api.supreme(text=text)).read(), "supreme.png"
    #     )
    #     await ctx.send(embed=embed, file=image)

    #     if len(text) > 40:
    #         return await ctx.send(
    #             "The file you tried to render was over 40 characters! Please try again!"
    # )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    # ).set_image(url="attachment://fact.png")
    #     image = discord.File(
    #         await (await self.alex_api.facts(text=text)).read(), "fact.png"
    # )
    #     await ctx.send(embed=embed, file=image)

    #     if len(text) > 40:
    #         return await ctx.send(
    #             "The file you tried to render was over 40 characters! Please try again!"
    # )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    # ).set_image(url="attachment://scroll.png")
    #     image = discord.File(
    #         await (await self.alex_api.scroll(text=text)).read(), "scroll.png"
    # )
    #     await ctx.send(embed=embed, file=image)

    #     if len(text) > 70:
    #         return await ctx.send(
    #             "The file you tried to render was over 70 characters! Please try again!"
    # )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    # ).set_image(url="attachment://call.png")
    #     image = discord.File(
    #         await (await self.alex_api.calling(text=text)).read(), "call.png"
    # )
    #     await ctx.send(embed=embed, file=image)

    #     embed = Embed(colour=colors.prim, title=f"{':salt:'*7}").set_image(
    #         url="attachment://salty.png"
    # )
    #     embed.set_footer(
    #         text=f"{ctx.author.name} > {user.name}"
    # )
    #     image = discord.File(
    #         await (await self.alex_api.salty(image=user.avatar)).read(), "salty.png"
    # )
    #     await ctx.send(embed=embed, file=image)

    #     embed = Embed(colour=colors.prim, title=f"Dock of shame.").set_image(
    #         url="attachment://shame.png"
    # )
    #     embed.set_footer(
    #         text=f"{ctx.author.name} > {user.name}"
    # )
    #     image = discord.File(
    #         await (await self.alex_api.shame(image=user.avatar)).read(), "shame.png"
    # )
    #     await ctx.send(embed=embed, file=image)

    #     if len(text) > 25:
    #         return await ctx.send(
    #             "The file you tried to render was over 25 characters! Please try again!"
    # )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    # ).set_image(url="attachment://captcha.png")
    #     image = discord.File(
    #         await (await self.alex_api.captcha(text=text)).read(), "captcha.png"
    # )
    #     await ctx.send(embed=embed, file=image)

    #     try:
    #         if len(hex) == 6:
    #             colorinf = await self.alex_api.colour(colour=hex)
    #             embed = Embed(colour=colors.prim, title=f"{colorinf.name}")
    #             embed.set_image(url=colorinf.image)
    #             embed.set_footer(
    #                 text=f"Rendered by {ctx.author}"
    # )
    #             await ctx.send(content="This command will be converted to slash commands before April 30th.", embed=embed)
    #         else:
    #             await ctx.send(
    #                 "A hex color code without transparency is composed of 6 characters, no more, no less."
    # )
    #     except Exception:
    #         await ctx.send(
    #             f"Failed to obtain color information. Maybe {hex} isn't a valid code."
    # )

    #     if len(text1) > 10 or len(text2) > 10:
    #         return await ctx.send(
    #             "One or both words for the file you tried to render were over 10 characters! Please try again."
    # )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    # ).set_image(url="attachment://hub.png")
    #     image = discord.File(
    #         await (await self.alex_api.pornhub(text=text1, text2=text2)).read(),
    #         "hub.png",
    # )
    #     await ctx.send(embed=embed, file=image)

    #     if len(text) > 30:
    #         return await ctx.send(
    #             "The file you tried to render was over 30 characters! Please try again!"
    # )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    # ).set_image(url="attachment://achievment.png")
    #     image = discord.File(
    #         await (await self.alex_api.achievement(text=text, icon=46)).read(),
    #         "achievment.png",
    # )
    #     await ctx.send(embed=embed, file=image)

    #     if len(text) > 40:
    #         return await ctx.send(
    #             "The file you tried to render was over 40 characters! Please try again!"
    # )
    #     embed = Embed(
    #         colour=colors.prim, title=f"Rendered by {ctx.author}"
    # ).set_image(url="attachment://challenge.png")
    #     image = discord.File(
    #         await (await self.alex_api.challenge(text=text, icon=46)).read(),
    #         "challenge.png",
    # )
    #     await ctx.send(embed=embed, file=image)

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def pp(self, ctx, *, user: MemberConverter = None):
        """See how much someone is packing :flushed:"""
        user = user or ctx.author
        final = "=" * random.randrange(15)
        value = f"8{final}D"
        if final == "":
            value = "Doesn't exist."
        await Embed(
            title="pp size",
            description=f"{user.name}'s pp size\n{value}",
            thumbnail=None,
        ).send(ctx)

    @commands.command(aliases=["bm"], hidden=True)
    @commands.check(permissions.is_owner)
    async def beemovie(self, ctx):
        """
        Sends the entire beemovie script.
        Has an 83 minute cooldown for a reason
        """
        async with ctx.channel.typing():
            with open("beemovie_script.txt", "r") as f:
                for line in f:
                    try:
                        await ctx.send(line)
                        await asyncio.sleep(1.5)
                    except Exception as e:
                        capture_exception(e)

    #     if secs == 0:
    #         return ctx.send("Hmm. Looks like you didn't provide a valid time. Please try again.")
    #     embed = Embed(
    #         colour=ctx.author.color,
    #         timestamp=ctx.message.created_at,
    #         title=f'You will be reminded in {str(secs_as_timedelta)}',
    #         url=Website,
    #         description=reminder
    # )
    #     await ctx.send(content="This command will be converted to slash commands before April 30th.", embed=embed)
    #     await asyncio.sleep(secs)

    #     remind_message = Embed(
    #         colour=ctx.author.color,
    #         title=f'Reminder{remind_str}!'
    # )
    #     try:
    #         await ctx.author.send(embed=remind_message)
    #     except discord.errors.Forbidden:
    #         await ctx.send(f'{ctx.author.mention}', embed=remind_message)

    @staticmethod
    async def handle_chatbot(author_id: int, content: str) -> Embed:
        BASE_URL = f"http://api.brainshop.ai/get?bid={BID}&key={CHAT_API_KEY}"
        url = f"{BASE_URL}&uid={author_id}&msg={content}"

        ERROR = ChatbotFailure("An error occured while accessing the chat API!")
        async with aiohttp.ClientSession() as s, s.get(url) as r:
            if r.status != 200 or r.content_type != "application/json":
                raise ERROR

            res = await r.json()
            if "cnt" not in res:
                raise ERROR

            em = Embed(
                title="Chat Bot",
                description=res["cnt"],
                thumbnail=None,
            )
            await s.close()
            return em

    #     async with ctx.channel.typing():
    #         if channel_or_content is None:
    #             return await ctx.send(
    #                 (
    #                     f"Hello! In order to chat with me use: `{ctx.prefix}chat <content>` "
    #                     f"or to add or change a channel for auto chatting use: `{ctx.prefix}chat <textorvoice_channel>`. "
    #                     f"For unlinking use: `{ctx.prefix}chat <currently_linked_channel>`."
    #                 )
    #             )

    #         db_guild = await self.bot.db.fetch_guild(ctx.guild.id)
    #         if not db_guild:
    #             db_guild = await self.bot.db.add_guild(ctx.guild.id)

    #         if isinstance(channel_or_content, str):
    #             emb = await self.handle_chatbot(ctx.author.id, channel_or_content)
    #             return await ctx.message.reply(embed=emb, mention_author=True)

    #         if not ctx.author.guild_permissions.manage_channels:
    #             return await ctx.send(
    #                 "You don't have the permissions to manage channels!"
    #             )

    #         if chat_channel_id and channel_or_content.id == chat_channel_id:
    #             await db_guild.modify(chatbot_channel_id=None)
    #             return await ctx.send(
    #                 "That's the currently linked channel.. unlinked it."
    #             )

    #         # check channel perms
    #         needed_perms = ("send_messages", "read_messages", "embed_links")
    #         channel_perms = [
    #             perm
    #             for perm, value in channel_or_content.permissions_for(ctx.guild.me)
    #             if value
    #         ]
    #         if missing_perms := [
    #             perm.replace("_", " ").title()
    #             for perm in needed_perms
    #             if perm not in channel_perms
    #         ]:
    #             return await ctx.send(
    #                 f"I'm missing the following permissions to use {channel_or_content.mention} as an auto chatting channel:\n`{', '.join(missing_perms)}`\n"
    #                 "*Please grant me all of those permissions and try again.*"
    #             )
    #         what = "updated" if chat_channel_id else "set"
    #         await db_guild.modify(chatbot_channel_id=channel_or_content.id)
    #         await ctx.send(
    #             f"Successfully {what} the auto chatting channel to {channel_or_content.mention}! Start chatting in the designated channel..."
    #         )
    #         return

    #     # ignore if valid command
    #     if (await self.bot.get_context(message)).valid:
    #         return

    #     db_guild = self.bot.db.get_guild(
    #         message.guild.id
    #     ) or await self.bot.db.fetch_guild(message.guild.id)
    #     if not db_guild:
    #         return

    #     chatbotchannel = db_guild.chatbot_channel_id
    #     if not chatbotchannel:
    #         return

    #     if message.channel.id != chatbotchannel:
    #         return

    #     db_user = self.bot.db.get_user(
    #         message.author.id
    #     ) or await self.bot.db.fetch_user(message.author.id)
    #     if not db_user or not db_user.message_tracking:
    #         return
    #     try:
    #         emb = await self.handle_chatbot(message.author.id, message.content)
    #         await message.reply(embed=emb, mention_author=True)
    #     except ChatbotFailure:
    #         return

    #     for entry in all_chat_bot_channels:
    #         cid = entry["chatbotchannel"]
    #         if cid := int(cid):
    #             try:
    #                 await self.bot.fetch_channel(cid)
    #             except (discord.HTTPException, discord.NotFound):
    #                 await self.bot.db.execute(
    #                     "UPDATE guilds SET chatbotchannel=NULL WHERE chatbotchannel=$1",
    #                     str(cid),
    #                 )

    @commands.hybrid_group()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def ship(self, ctx):
        """Ship anything from people to things"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))
            return
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @ship.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def user(self, ctx, user1: discord.Member, user2: discord.Member):
        """Combine usernames of 2 people"""
        user1_name = user1.name
        user2_name = user2.name
        user1_name_first = user1_name[: len(user1_name) // 2]
        user2_name_last = user2_name[len(user2_name) // 2 :]
        ship_name = user1_name_first + user2_name_last
        await Embed(
            title=f"{user1} ❤ {user2}",
            description=ship_name,
        ).send(ctx)

    @ship.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def thing(self, ctx, thing1, thing2):
        """Combine usernames of 2 people"""
        user1_name_first = thing1[: len(thing1) // 2]
        user2_name_last = thing2[len(thing2) // 2 :]
        ship_name = user1_name_first + user2_name_last
        await Embed(
            title=f"{thing1} ❤ {thing2}",
            description=ship_name,
        ).send(ctx)

    @commands.hybrid_group()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def actions(self, ctx):
        """A bunch of fun actions to mess around with"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(str(ctx.command))
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @actions.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def eightball(self, ctx, *, question: commands.clean_content):
        """Ask 8ball"""
        await Embed(
            title=f"{ctx.message.author.display_name} asked:",
            description=question,
            image=nekos.img("8ball"),
        ).send(ctx)

    @actions.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def owoify(self, ctx, *, text: commands.clean_content):
        """Owoify any message"""
        owoified = nekos.owoify(text)
        embed = Embed(description=owoified, thumbnail=None)
        await ctx.send(embed=embed)

    @actions.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def why(self, ctx):
        """why"""
        why = nekos.why()
        embed = Embed(description=why, thumbnail=None)
        await ctx.send(embed=embed)

    @actions.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def fact(self, ctx):
        """Get a random fact"""
        async with aiohttp.ClientSession() as session:
            resp = await session.get("https://useless-facts.sameerkumar.website/api")
            fact = (await resp.json())["data"]
        embed = Embed(description=fact, thumbnail=None)
        await ctx.send(embed=embed)

    @actions.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def insult(self, ctx):
        """Get a random insult"""
        async with aiohttp.ClientSession() as session:
            resp = await session.get(
                "https://evilinsult.com/generate_insult.php?lang=en&type=json"
            )
            insult = (await resp.json())["insult"]
        embed = Embed(description=insult)
        await ctx.send(embed=embed)

    @actions.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def bonk(self, ctx, user: discord.Member = None):
        user = user or ctx.author
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if user != ctx.author:
            async with aiohttp.ClientSession() as session, session.get(
                "https://api.waifu.pics/sfw/bonk"
            ) as r:
                if r.status == 200:
                    img = await r.json()
                    img = img["url"]
                    emoji = "<a:BONK:825511960741150751>"
                    embed = Embed(
                        title="Bonky bonk.",
                        color=colors.prim,
                        description=f"**{user}** gets bonked {emoji}",
                    )
                    embed.set_image(url=img)
                    await ctx.send(
                        embed=embed,
                    )
        else:
            await ctx.send("bonk <a:BONK:825511960741150751>")

    @actions.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def slap(self, ctx, *, user: MemberConverter):
        """Slap people"""
        user = user or ctx.author
        if user == ctx.author:
            await Embed(
                title="You slapped yourself",
                image=nekos.img("slap"),
            ).send(ctx)
        else:
            await Embed(
                title=f"{ctx.message.author.display_name} slapped {user.display_name}",
                image=nekos.img("slap"),
            ).send(ctx)

    @actions.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def hug(self, ctx, *, user: MemberConverter):
        """Hug people"""
        user = user or ctx.author
        if user == ctx.author:
            await Embed(
                title="You hugged yourself, kinda sad lol",
                image=nekos.img("hug"),
            ).send(ctx)
        else:
            await Embed(
                title=f"{ctx.message.author.display_name} hugged {user.display_name}",
                image=nekos.img("hug"),
            ).send(ctx)

    @actions.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def kiss(self, ctx, *, user: MemberConverter):
        """Kiss people"""
        user = user or ctx.author
        if user == ctx.author:
            weird = [
                "how lonely they must be",
                "weirdo...",
                "god thats sad",
                "get a gf",
            ]
            await Embed(
                title=f"You kissed yourself... {random.choice(weird)}",
                image=nekos.img("kiss"),
            ).send(ctx)
        else:
            cute = ["awww", "adorable", "cute", "how sweet", "how cute"]
            await Embed(
                title=f"{ctx.message.author.display_name} kissed {user.display_name}... {random.choice(cute)}",
                image=nekos.img("kiss"),
            ).send(ctx)

    @actions.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def smug(self, ctx, *, user: MemberConverter = None):
        """Look smug"""
        user = user or ctx.author
        await Embed(
            title=f"{user} is smug",
            image=nekos.img("smug"),
        ).send(ctx)

    @actions.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def pat(self, ctx, *, user: MemberConverter):
        """Pat people"""
        user = user or ctx.author
        if user == ctx.author:
            await Embed(
                title="You gave yourself a pat... kinda weird ngl",
                image=nekos.img("pat"),
            ).send(ctx)
        else:
            await Embed(
                title=f"{ctx.author.name} gave {user.display_name} a pat",
                image=nekos.img("pat"),
            ).send(ctx)

    @actions.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def tickle(self, ctx, *, user: MemberConverter):
        """Tickle people"""
        user = user or ctx.author
        if user == ctx.author:
            await Embed(
                title="You tickled yourself... kinda weird ngl",
                image=nekos.img("tickle"),
            ).send(ctx)
        else:
            await Embed(
                title=f"{ctx.author.name} tickled {user.name}",
            ).send(ctx)

    @actions.command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def kill(self, ctx, *, user: MemberConverter):
        """Kill someone"""
        user = user or ctx.author
        if user == ctx.author:
            await Embed(
                title="You killed yourself, hope it was worth it! Now tag someone to kill them!",
            ).send(ctx)

        else:
            kill_msg = [
                f"{user.name} gets stabbed by a knife from {ctx.author.name}",
                f"{user.name} gets shot by {ctx.author.name}",
                f"{user.name} gets executed by {ctx.author.name}",
                f"{user.name} gets impaled by {ctx.author.name}",
                f"{user.name} gets burned by {ctx.author.name}",
                f"{user.name} gets crucified by {ctx.author.name}",
                f"{user.name} was eaten by {ctx.author.name}",
                f"{user.name} died from {ctx.author.name}'s awful puns",
                f"{user.name} was cut in half by {ctx.author.name}",
                f"{user.name} was hanged by {ctx.author.name}",
                f"{user.name} was strangled by {ctx.author.name}",
                f"{user.name} died from a poorly made cupcake by {ctx.author.name}",
                f"{user.name} died within a couple seconds of getting jumped by {ctx.author.name}",
                f"{ctx.author.name} 'accidentally' killed {user.name}",
                f"{ctx.author.name} tried to kill {user.name}, but just missed",
                f"{ctx.author.name} tried to strangle {user.name}, but it didn't work",
                f"{ctx.author.name} tripped over their own knife trying to kill {user.name} but killed themselves instead!",
                f"{ctx.author.name} tried to kill {user.name}, but they didn't have a knife!",
                f"{ctx.author.name} tried to kill {user.name}, but they were too scared to kill them!",
                f"{ctx.author.name} absolutely demolished {user.name}'s head with a frying pan!",
                f"{ctx.author.name} got ratioed so hard {user.name} fucking died 💀",
                f"{user.name} kicked {ctx.author.name}'s ass so bad they died",
                f"{user.name} breathed {ctx.author.name}'s air so hard they died",
                f"{ctx.author.name} inhaled a fart from {user.name} and died",
                f"{user.name} inhaled a fart from {ctx.author.name} and died",
            ]

            await Embed(title=random.choice(kill_msg)).send(ctx)

    @actions.command()
    @voter_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def meme(self, ctx):
        """Sends you the dankest memes"""
        subs = ["dankmemes", "memes", "ComedyCemetery"]
        subreddit = await self.reddit.subreddit(random.choice(subs))
        all_subs = []
        top = subreddit.hot(limit=50)
        async for submission in top:
            all_subs.append(submission)
        random_sub = random.choice(all_subs)
        name = random_sub.title
        url = random_sub.url
        if "https://v" in url:
            return await ctx.send(url)
        if "https://streamable.com/" in url:
            return
        if "https://i.imgur.com/" in url:
            return await ctx.send(url)
        if "https://gfycat.com/" in url:
            return await ctx.send(url)
        if "https://imgflip.com/gif/" in url:
            return await ctx.send(url)
        if "https://youtu.be/" in url:
            return await ctx.send(url)
        if "https://youtube.com/" in url:
            return await ctx.send(url)
        await Embed(title=name, image=url).send(ctx)

    @actions.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 15, commands.BucketType.user)
    async def hack(self, ctx, user: MemberConverter = None):
        """Hack a user, totally real and legit"""
        await ctx.typing()
        if user is None:
            await ctx.send("I can't hack air, mention someone.")
        elif user == ctx.author:
            await ctx.send("Lol what would hacking yourself get you lmao")
        else:
            email_fun = [
                "69420",
                "8008135",
                "eatsA$$",
                "PeekABoo",
                "TheShire",
                "isFAT",
                "Dumb_man",
                "Ruthless_gamer",
                "Sexygirl69",
                "Loyalboy69",
                "likesButts",
                "isastupidfuck",
                "milfsmasher",
                "dumbwhore",
                "am_dumbass",
                "is_assholesniffer",
                "is_stupid",
            ]
            addresses = ["@gmail.com", "@protonmail.com", "@lunardev.group"]
            email_address = f"{user.name.lower()}{random.choice(email_fun).lower()}{random.choice(addresses)}"
            passwords = [
                "animeislife69420",
                "big_awoogas",
                "red_sus_ngl",
                "IamACompleteIdiot",
                "YouWontGuessThisOne",
                "yetanotherpassword",
                "iamnottellingyoumypw",
                "SayHelloToMyLittleFriend",
                "ImUnderYourBed",
                "TellMyWifeILoveHer",
                "P@$$w0rd",
                "iLike8008135",
                "IKnewYouWouldHackIntoMyAccount",
                "BestPasswordEver",
                "JustARandomPassword",
                "softnipples",
            ]
            password = f"{random.choice(passwords)}"
            DMs = [
                "nudes?",
                "https://lunardev.group/home is a pretty cool website",
                "im kinda gay tbh",
                "bro don't make fun of my small penis",
                "https://youtu.be/iik25wqIuFo",
                "lmfao you kinda ugly",
                "pls no, stay out of my ass",
                "i use discord in light mode",
                "some animals give me boners..",
                "no bitches?",
                "I am a exquisite virgin",
                "dick fart",
                "i got diabetes from rats",
                "Gib robux pls",
                "Dick pic or not pro",
                "Can i sniff?",
                "Lick the inside of my mouth pls",
                "*sniffs your asshole cutely uwu*",
                "Inject herion into my veins",
                "*performs butt sex*",
                "your dads pretty fat for a meth head",
                "hewwwoooo mommy?",
            ]
            latest_DM = f"{random.choice(DMs)}"
            # generate a random IP address
            ip_address = f"{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
            Discord_Servers = [
                "Virgins Only",
                "No friends gang",
                "Gaymers Together",
                "FuckShit",
                "Lunar Development",
                "Join this server if ur gay",
                "Egirls palace",
                "single people only",
                "Join if ur gay",
                "gacha heat 🥵🥵",
                "retards only",
                "furry pride",
                "subway surfers fan club (18+)",
                "racists only",
                "cocklovers only",
                "kitchen dwellers(women)",
                "WinterFe fanclub",
                "motz fanclub",
                "Please cancel us. Email: contact@lunardev.group",
            ]
            Most_Used_Discord_Server = f"{random.choice(Discord_Servers)}"
            async with ctx.channel.typing():
                msg1 = await ctx.send(
                    embed=Embed(
                        description="Initializing Hack.exe... <a:discord_loading:816846352075456512>",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description=f"Successfully initialized Hack.exe, beginning hack on {user.name}... <a:discord_loading:816846352075456512>",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description=f"Logging into {user.name}'s Discord Account... <a:discord_loading:816846352075456512>",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description=f"<:discord:816846362267090954> Logged into {user.name}'s Discord:\nEmail Address: `{email_address}`\nPassword: `{password}`",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description="Fetching DMs from their friends(if there are any)... <a:discord_loading:816846352075456512>",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description=f"Latest DM from {user.name}: `{latest_DM}`",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description="Getting IP address... <a:discord_loading:816846352075456512>",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description=f"IP address found: `{ip_address}`", thumbnail=None
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description="Fetching the Most Used Discord Server... <a:discord_loading:816846352075456512>",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description=f"Most used Discord Server in {user.name}'s Account: `{Most_Used_Discord_Server}`",
                        thumbnail=None,
                    )
                )
                await asyncio.sleep(1)
                await msg1.edit(
                    embed=Embed(
                        description="Selling data to the dark web... <a:discord_loading:816846352075456512>",
                        thumbnail=None,
                    )
                )

                await asyncio.sleep(1)
                await msg1.edit(embed=Embed(description="Hacking complete."))
                await asyncio.sleep(1.5)
                await msg1.edit(
                    embed=Embed(
                        description=f"{user.name} has successfully been hacked. <a:EpicTik:816846395302477824>\n\n**{user.name}**'s Data:\nDiscord Email: `{email_address}`\nDiscord Password: `{password}`\nMost used Discord Server: `{Most_Used_Discord_Server}`\nIP Address: `{ip_address}`\nLatest DM: `{latest_DM}`",
                        footer=f"Something missing? Suggest it with {ctx.prefix}suggest! ",
                    )
                )

    @commands.hybrid_group()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def animals(self, ctx):
        """A bunch of fun actions to mess around with"""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help(str(ctx.command))
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @animals.command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def dog(self, ctx):
        """Puppers"""
        async with aiohttp.ClientSession() as data, data.get(
            "https://api.thedogapi.com/v1/images/search"
        ) as r:
            data = await r.json()
            await Embed(
                title="Enjoy this doggo <3",
                url="https://lunardev.group/",
                image=data[0]["url"],
                thumbnail=None,
            ).send(ctx)

    @animals.command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def cat(self, ctx):
        """Kitties!!"""
        await Embed(
            title="Enjoy this kitty <3",
            url=Website,
            image=await self.get_kitties(),
            thumbnail=None,
        ).send(ctx)

    @animals.command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def birb(self, ctx):
        """Its really just geese"""
        await Embed(
            title="Enjoy this birb <3",
            url=Website,
            image=nekos.img("goose"),
            thumbnail=None,
        ).send(ctx)

    @commands.hybrid_command()
    @commands.bot_has_permissions(add_reactions=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def pressf(self, ctx, *, user: discord.User = None):
        """Pay respects by pressing F"""
        if str(ctx.channel.id) in self.channels:
            return await ctx.send(
                "Oops! I'm still paying respects in this channel, you'll have to wait until I'm done."
            )
        if user:
            await self.bot.fetch_user(user.id)
            answer = user.display_name
        else:
            await ctx.send("What do you want to pay respects to?")

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                pressf = await ctx.bot.wait_for("message", timeout=120.0, check=check)
            except asyncio.TimeoutError:
                return await ctx.send("You took too long to reply.")
            answer = pressf.content[:1900]
        message = await ctx.send(
            f"Everyone, let's pay respects to **{filter_mass_mentions(answer)}**! Press the f reaction on this message to pay respects."
        )
        await message.add_reaction("\U0001f1eb")
        self.channels[str(ctx.channel.id)] = {"msg_id": message.id, "reacted": []}
        await asyncio.sleep(120)
        with contextlib.suppress(discord.errors.NotFound, discord.errors.Forbidden):
            await message.delete()
        amount = len(self.channels[str(ctx.channel.id)]["reacted"])
        word = "person has" if amount == 1 else "people have"
        await Embed(
            description=f"**{amount}** {word} paid respects to **{filter_mass_mentions(answer)}**.",
        ).send(ctx)
        del self.channels[str(ctx.channel.id)]

    @commands.Cog.listener(name="on_reaction_add")
    async def PressF(self, reaction, user):
        if str(reaction.message.channel.id) not in self.channels:
            return
        if (
            self.channels[str(reaction.message.channel.id)]["msg_id"]
            != reaction.message.id
        ):
            return
        if user.id == self.bot.user.id:
            return
        if (
            user.id not in self.channels[str(reaction.message.channel.id)]["reacted"]
            and str(reaction.emoji) == "\U0001f1eb"
        ):
            await reaction.message.channel.send(
                f"**{user.name}** has paid their respects."
            )
            self.channels[str(reaction.message.channel.id)]["reacted"].append(user.id)

    #     @commands.command(hidden=True)
    #     @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    #     async def chad(self, ctx):
    #         await ctx.send(
    #             """
    # ⣿⣿⣿⣿⣿⣿⣿⣿⡿⠿⠛⠛⠛⠋⠉⠈⠉⠉⠉⠉⠛⠻⢿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣿⡿⠋⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⢿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⡏⣀⠀⠀⠀⠀⠀⠀⠀⣀⣤⣤⣤⣄⡀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣿
    # ⣿⣿⣿⢏⣴⣿⣷⠀⠀⠀⠀⠀⢾⣿⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀⠀⠈⣿⣿
    # ⣿⣿⣟⣾⣿⡟⠁⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⣿⣿⣷⢢⠀⠀⠀⠀⠀⠀⠀⢸⣿
    # ⣿⣿⣿⣿⣟⠀⡴⠄⠀⠀⠀⠀⠀⠀⠙⠻⣿⣿⣿⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⣿
    # ⣿⣿⣿⠟⠻⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠶⢴⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⣿
    # ⣿⣁⡀⠀⠀⢰⢠⣦⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⣿⣿⣿⣿⣿⡄⠀⣴⣶⣿⡄⣿
    # ⣿⡋⠀⠀⠀⠎⢸⣿⡆⠀⠀⠀⠀⠀⠀⣴⣿⣿⣿⣿⣿⣿⣿⠗⢘⣿⣟⠛⠿⣼
    # ⣿⣿⠋⢀⡌⢰⣿⡿⢿⡀⠀⠀⠀⠀⠀⠙⠿⣿⣿⣿⣿⣿⡇⠀⢸⣿⣿⣧⢀⣼
    # ⣿⣿⣷⢻⠄⠘⠛⠋⠛⠃⠀⠀⠀⠀⠀⢿⣧⠈⠉⠙⠛⠋⠀⠀⠀⣿⣿⣿⣿⣿
    # ⣿⣿⣧⠀⠈⢸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠟⠀⠀⠀⠀⢀⢃⠀⠀⢸⣿⣿⣿⣿
    # ⣿⣿⡿⠀⠴⢗⣠⣤⣴⡶⠶⠖⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡸⠀⣿⣿⣿⣿
    # ⣿⣿⣿⡀⢠⣾⣿⠏⠀⠠⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠛⠉⠀⣿⣿⣿⣿
    # ⣿⣿⣿⣧⠈⢹⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⣿⣿⣿⣿
    # ⣿⣿⣿⣿⡄⠈⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⣴⣾⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣿⣦⣄⣀⣀⣀⣀⠀⠀⠀⠀⠘⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡄⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠀⠀⠀⠙⣿⣿⡟⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠇⠀⠁⠀⠀⠹⣿⠃⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⣿⣿⣿⣿⡿⠛⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⢐⣿⣿⣿⣿⣿⣿⣿⣿⣿
    # ⣿⣿⣿⣿⠿⠛⠉⠉⠁⠀⢻⣿⡇⠀⠀⠀⠀⠀⠀⢀⠈⣿⣿⡿⠉⠛⠛⠛⠉⠉
    # ⣿⡿⠋⠁⠀⠀⢀⣀⣠⡴⣸⣿⣇⡄⠀⠀⠀⠀⢀⡿⠄⠙⠛⠀⣀⣠⣤⣤⠄
    # 					"""
    #         )

    #     @commands.command(hidden=True)
    #     @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    #     async def sussy(self, ctx):
    #         if random.randint(1, 2) == 1:
    #             await ctx.send(
    #                 """
    # ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣤⣤⣤⣤⣤⣶⣦⣤⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣿⡿⠛⠉⠙⠛⠛⠛⠛⠻⢿⣿⣷⣤⡀⠀⠀⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⠀⣼⣿⠋⠀⠀⠀⠀⠀⠀⠀⢀⣀⣀⠈⢻⣿⣿⡄⠀⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⣸⣿⡏⠀⠀⠀⣠⣶⣾⣿⣿⣿⠿⠿⠿⢿⣿⣿⣿⣄⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⣿⣿⠁⠀⠀⢰⣿⣿⣯⠁⠀⠀⠀⠀⠀⠀⠀⠈⠙⢿⣷⡄⠀
    # ⠀⠀⣀⣤⣴⣶⣶⣿⡟⠀⠀⠀⢸⣿⣿⣿⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣷⠀
    # ⠀⢰⣿⡟⠋⠉⣹⣿⡇⠀⠀⠀⠘⣿⣿⣿⣿⣷⣦⣤⣤⣤⣶⣶⣶⣶⣿⣿⣿⠀
    # ⠀⢸⣿⡇⠀⠀⣿⣿⡇⠀⠀⠀⠀⠹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠃⠀
    # ⠀⣸⣿⡇⠀⠀⣿⣿⡇⠀⠀⠀⠀⠀⠉⠻⠿⣿⣿⣿⣿⡿⠿⠿⠛⢻⣿⡇⠀⠀
    # ⠀⣿⣿⠁⠀⠀⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣧⠀⠀
    # ⠀⣿⣿⠀⠀⠀⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠀⠀
    # ⠀⣿⣿⠀⠀⠀⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⠀⠀
    # ⠀⢿⣿⡆⠀⠀⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⡇⠀⠀
    # ⠀⠸⣿⣧⡀⠀⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠃⠀⠀
    # ⠀⠀⠛⢿⣿⣿⣿⣿⣇⠀⠀⠀⠀⠀⣰⣿⣿⣷⣶⣶⣶⣶⠶⠀⢠⣿⣿⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⣿⣿⡇⠀⣽⣿⡏⠁⠀⠀⢸⣿⡇⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⣿⣿⡇⠀⢹⣿⡆⠀⠀⠀⣸⣿⠇⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⢿⣿⣦⣄⣀⣠⣴⣿⣿⠁⠀⠈⠻⣿⣿⣿⣿⡿⠏⠀⠀⠀⠀
    # ⠀⠀⠀⠀⠀⠀⠀⠈⠛⠻⠿⠿⠿⠿⠋⠁⠀
    # 						   """
    #             )
    #         else:
    #             await ctx.send(
    #                 """
    # ⠀       ⠀⠀⠀⣠⠤⠖⠚⠛⠉⠛⠒⠒⠦⢤
    # ⠀⠀⠀⠀⣠⠞⠁⠀⠀⠠⠒⠂⠀⠀⠀⠀⠀⠉⠳⡄
    # ⠀⠀⠀⢸⠇⠀⠀⠀⢀⡄⠤⢤⣤⣤⡀⢀⣀⣀⣀⣹⡄
    # ⠀⠀⠀⠘⢧⠀⠀⠀⠀⣙⣒⠚⠛⠋⠁⡈⠓⠴⢿⡿⠁
    # ⠀⠀⠀⠀⠀⠙⠒⠤⢀⠛⠻⠿⠿⣖⣒⣁⠤⠒⠋
    # ⠀⠀⠀⠀⠀⢀⣀⣀⠼⠀⠈⣻⠋⠉⠁ A M O G U S
    # ⠀⠀⠀⡴⠚⠉⠀⠀⠀⠀⠀⠈⠀⠐⢦
    # ⠀⠀⣸⠃⠀⡴⠋⠉⠀⢄⣀⠤⢴⠄⠀⡇
    # ⠀⢀⡏⠀⠀⠹⠶⢀⡔⠉⠀⠀⣼⠀⠀⡇
    # ⠀⣼⠁⠀⠙⠦⣄⡀⣀⡤⠶⣉⣁⣀⠘
    # ⢀⡟⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⣽
    # ⢸⠇⠀⠀⠀⢀⡤⠦⢤⡄⠀⠀⡟
    # ⢸⠀⠀⠀⠀⡾⠀⠀⠀⡿⠀⠀⣇⣀⣀
    # ⢸⠀⠀⠈⠉⠓⢦⡀⢰⣇⡀⠀⠉⠀⠀⣉⠇
    # ⠈⠓⠒⠒⠀⠐⠚⠃⠀⠈⠉⠉⠉⠉⠉⠁
    # """
    #             )

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 2, type=commands.BucketType.user)
    async def rate(self, ctx, *, thing: commands.clean_content):
        """Rates what you want"""
        rate_amount = random.uniform(0.0, 100.0)
        await Embed(
            description=f"I'd rate `{thing}` a **{round(rate_amount, 4)} / 100**",
            thumbnail=None,
        ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 2.5, type=commands.BucketType.user)
    @commands.hybrid_command()
    async def hotcalc(self, ctx, *, user: MemberConverter = None):
        """Returns a random percent for how hot is a discord user"""
        user = user or ctx.author
        if user.id == 318483487231574016:
            return await ctx.send(f"**{user.name}** is fucking dumb")
        r = random.randint(1, 100)
        hot = r / 1.17
        emoji = "💔"
        if hot > 25:
            emoji = "❤"
        if hot > 50:
            emoji = "💖"
        if hot > 75:
            emoji = "💞"
        await Embed(
            description=f"**{user.name}** is **{hot:.2f}%** hot {emoji}",
            thumbnail=None,
        ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 2.5, type=commands.BucketType.user)
    @commands.hybrid_command()
    async def howgay(self, ctx, *, user: MemberConverter = None):
        """Tells you how gay a user is lol."""
        user = user or ctx.author
        # if user.id == 101118549958877184:
        #    return await ctx.send(f"**{user.name}** cant be gay, homo.")
        # if user.id == 503963293497425920:
        # return await ctx.send(f"**{user.name}** is not gay and he is a cool
        # kid")
        if user.id == 723726581864071178:
            return await ctx.send("I'm a bot lmao.")
        r = random.randint(1, 100)
        gay = r / 1.17
        emoji = "<:LMAO:838988129431191582>"
        if gay > 25:
            emoji = "<:kek:838988145550557244>"
        if gay > 50:
            emoji = "<:yikes:838988155947319337>"
        if gay > 75:
            emoji = "<:stop_pls:838988169251782666>"
        await Embed(
            description=f"**{user.name}** is **{gay:.2f}%** gay {emoji}",
            thumbnail=None,
        ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 2.5, type=commands.BucketType.user)
    @commands.hybrid_command()
    async def sus(self, ctx, *, user: MemberConverter = None):
        """Tells you how sus someone is"""
        user = user or ctx.author
        if user.id == self.bot.user.id:
            return await ctx.send("I'm a bot lmao.")
        r = random.randint(1, 100)
        sus = r / 1.17
        emoji = "<:troll1:1014268415365623860>"
        if sus > 25:
            emoji = "<:troll2:1014268439096991836>"
        if sus > 50:
            emoji = "<:troll3:1014268459951063162>"
        if sus > 75:
            emoji = "<:troll4:1014268464946479156>"
        await Embed(
            description=f"**{user.name}** is **{sus:.2f}%** sus {emoji}",
            thumbnail=None,
        ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 2.5, type=commands.BucketType.user)
    @commands.hybrid_command()
    async def simp(self, ctx, *, user: MemberConverter = None):
        """Tells you if a user is a simp lol."""
        user = user or ctx.author
        if user.id == 503963293497425920:
            return await ctx.send(f"**{user.name}** is not a simp and he is a cool kid")
        if user.id == 723726581864071178:
            return await ctx.send("I'm a bot lmao.")
        r = random.randint(1, 100)
        simp = r / 1.17
        emoji = "<:LMAO:838988129431191582>"
        if simp > 25:
            emoji = "<:kek:838988145550557244>"
        if simp > 50:
            emoji = "<:yikes:838988155947319337>"
        if simp > 75:
            emoji = "<:stop_pls:838988169251782666>"
        await Embed(
            description=f"**{user.name}** is **{simp:.2f}%** simp {emoji}",
            thumbnail=None,
        ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 2.5, type=commands.BucketType.user)
    @commands.hybrid_command()
    async def horny(self, ctx, *, user: MemberConverter = None):
        """Tells you how horny someone is :flushed:"""
        user = user or ctx.author
        if user.id == 101118549958877184:
            return await ctx.send(
                f"**{user.name}** is super fucking horny, like constantly."
            )
        if user.id == 503963293497425920:
            return await ctx.send(f"**{user.name}** ***Horny.***")
        if user.id == 723726581864071178:
            return await ctx.send("I'm a bot lmao.")
        r = random.randint(0, 200)
        horny = r / 1.17
        emoji = "<:swagcat:843525938952404993>"
        if horny > 0:
            emoji = "<:swagcat:843525938952404993>"
        if horny > 55:
            emoji = "<:kek:838988145550557244>"
        if horny > 75:
            emoji = "<:yikes:838988155947319337>"
        if horny > 150:
            emoji = "<:stop_pls:838988169251782666>"
        await Embed(
            description=f"**{user.name}** is **{horny:.2f}%** horny {emoji}",
            thumbnail=None,
        ).send(ctx)

    @commands.hybrid_group(name="gen")
    async def gen(self, ctx: commands.Context):
        """Image generation commands"""
        await Embed(
            "Image Generation Commands",
            description="Looking for `/gen`? Well, these are slash commands!\nType `/gen` to get started with a list of these ones :eyes:",
        ).send(ctx)

    @gen.command()
    async def achievement(self, ctx, *, text: str):
        async with aiohttp.ClientSession() as session:
            client = lunarapi.Client(
                session=session,
                token=config.lunarapi.tokenNew,
            )
            image = await client.request(
                lunarapi.endpoints.generate_achievement, text=text
            )

            await ctx.send(file=await image.file(discord))

    @gen.command()
    async def amiajoke(self, ctx, *, user: discord.User):
        async with aiohttp.ClientSession() as session:
            client = lunarapi.Client(
                session=session,
                token=config.lunarapi.tokenNew,
            )
            image = await client.request(
                lunarapi.endpoints.generate_amiajoke, image=user.avatar.url
            )

            await ctx.send(file=await image.file(discord))

    @gen.command()
    async def bad(self, ctx, *, user: discord.User):
        async with aiohttp.ClientSession() as session:
            client = lunarapi.Client(
                session=session,
                token=config.lunarapi.tokenNew,
            )
            image = await client.request(
                lunarapi.endpoints.generate_bad, image=user.avatar.url
            )

            await ctx.send(file=await image.file(discord))

    @gen.command()
    async def calling(self, ctx, *, text: str):
        async with aiohttp.ClientSession() as session:
            client = lunarapi.Client(
                session=session,
                token=config.lunarapi.tokenNew,
            )
            image = await client.request(lunarapi.endpoints.generate_calling, text=text)

            await ctx.send(file=await image.file(discord))

    @gen.command()
    async def challenge(self, ctx, *, text: str):
        async with aiohttp.ClientSession() as session:
            client = lunarapi.Client(
                session=session,
                token=config.lunarapi.tokenNew,
            )
            image = await client.request(
                lunarapi.endpoints.generate_challenge, text=text
            )

            await ctx.send(file=await image.file(discord))


async def setup(bot: Bot) -> None:
    await bot.add_cog(Fun(bot))
