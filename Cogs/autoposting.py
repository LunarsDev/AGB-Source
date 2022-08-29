from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Union

import aiohttp
import discord
from discord.ext import commands, tasks
from Manager.emoji import Emoji
from index import colors, config
from Manager.logger import formatColor
from lunarapi import Client, endpoints
from sentry_sdk import capture_exception
from utils import imports
from utils.embeds import EmbedMaker as Embed
from utils.default import log

if TYPE_CHECKING:
    from index import Bot

BotList_Servers = [
    336642139381301249,
    716445624517656727,
    523523486719803403,
    658262945234681856,
    608711879858192479,
    446425626988249089,
    387812458661937152,
    414429834689773578,
    645281161949741064,
    527862771014959134,
    733135938347073576,
    766993740463603712,
    724571620676599838,
    568567800910839811,
    641574644578648068,
    532372609476591626,
    374071874222686211,
    789934742128558080,
    694140006138118144,
    743348125191897098,
    110373943822540800,
    491039338659053568,
    891226286347923506,
]


class autoposting(commands.Cog, name="ap"):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.config = imports.get("config.json")
        self.lunar_headers = {f"{config.lunarapi.header}": f"{config.lunarapi.token}"}

    async def send_from_webhook(
        self, webhook: discord.Webhook, embed: discord.Embed
    ) -> None:
        try:
            from Cogs.admin import PersistentView

            await webhook.send(
                embed=embed,
                avatar_url=self.bot.user.avatar.url,
                view=PersistentView(self),  # type: ignore
            )
        except Exception as e:
            capture_exception(e)
            log(f"AutoPosting - webhook error | {formatColor(e), 'red'}")
            return

    @tasks.loop(minutes=5)
    async def autoh(self):
        async def get_hentai_img() -> str:
            cats = [
                "ahegao",
                "ass",
                "boobs",
                "cum",
                "gif",
                "hololive",
                "jpg",
                "neko",
                "panties",
                "thighs",
                "yuri",
            ]

            async with aiohttp.ClientSession() as session:
                client = Client(session=session, token=config.lunarapi.tokenNew)
                img = await client.request(endpoints.nsfw(random.choice(cats)))
                data = await img.to_dict()
                return data["url"]

        from Cogs.admin import PersistentView

        posts = 0
        me = self.bot.get_user(101118549958877184) or await self.bot.fetch_user(
            101118549958877184
        )
        url = await get_hentai_img()
        cleaned_link = url.replace("https://api.lunardev.group/", "")
        if random.randint(1, 10) == 3:
            embed = Embed(
                title="Enjoy your poggers porn lmao",
                description=f"Posting can be slow, please take into consideration how many servers this bot is in and how many are using auto posting. Please be patient. If I completely stop posting, please rerun the command or join the support server.\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate})",
                colour=colors.prim,
            )
        else:
            embed = Embed(
                title="Enjoy your poggers porn lmao",
                description=f"[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate})",
                colour=colors.prim,
            )

        db_guilds = self.bot.db._guilds
        if not db_guilds:
            await self.bot.db.fetch_guilds(cache=True)
        db_guilds = list(db_guilds.values())
        hentai_channel_ids = [
            (x, x.hentai_channel_id)
            for x in db_guilds
            if x.hentai_channel_id is not None
        ]

        try:
            embed.set_image(url=url)
            embed.set_footer(
                text=f"mc.lunardev.group 1.19.2 | {cleaned_link}", icon_url=me.avatar
            )
        except Exception as e:
            capture_exception(e)
            log(f"AutoPosting - Error | {formatColor(e), 'red'}")
            try:
                embed.set_image(url=url)
                embed.set_footer(
                    text=f"mc.lunardev.group 1.19.2 | {cleaned_link}",
                    icon_url=me.avatar,
                )
            except Exception as e:
                capture_exception(e)
                log(f"AutoPosting - Error | {formatColor(e), 'red'}")
            if embed.image is None:
                try:
                    embed.set_image(url=url)
                    embed.set_footer(
                        text=f"mc.lunardev.group 1.19.2 | {cleaned_link}",
                        icon_url=me.avatar,
                    )
                except Exception as e:
                    capture_exception(e)
                    log(f"AutoPosting - Error | {formatColor(e), 'red'}")
        else:
            for (guild, channel_id) in hentai_channel_ids:
                channel = self.bot.get_channel(channel_id)
                # channel not found in cache, continue
                if not channel:
                    continue

                # channel is not a text channel, continue
                if not (hasattr(channel, "guild") and channel.guild):  # type: ignore
                    continue

                # shut the linter still complaining about this
                assert isinstance(channel, discord.TextChannel)

                # ignore bot lists.
                if channel.guild.id in BotList_Servers:
                    continue

                # chunk guilds if not chunked
                if not channel.guild.chunked:
                    await channel.guild.chunk()

                # remove channel from db if it's not a NSFW channel
                if not channel.is_nsfw():
                    await self.bot.db.remove_autoposting(channel.guild.id)
                    # await self.bot.db.execute(
                    #     "DELETE FROM guilds WHERE hentaichannel = $1", str(channel_id)
                    # )
                    # log it
                    log(
                        f"AutoPosting - {channel.guild.id} is no longer NSFW, so I have removed the channel from the database."
                    )
                    continue

                # handle every error that can happen
                try:
                    # get channel webhooks
                    webhooks = await channel.webhooks()

                    # found out custom webhook
                    webhook = discord.utils.get(
                        webhooks, name="AGB Autoposting", user=self.bot.user
                    )
                    # if not found, loop through all webhooks and check if there is a custom one
                    # and delete it if it is
                    if webhook is None:
                        # check all the channels webhooks for AGB Autoposting
                        for w in webhooks:
                            if w.name == "AGB Autoposting":
                                # check if there are more than one webhooks
                                await w.delete()

                        # create a new custom webhook
                        webhook = await channel.create_webhook(
                            name="AGB Autoposting",
                            avatar=await self.bot.user.avatar.read(),  # type: ignore
                        )
                except discord.errors.Forbidden:
                    webhook = None
                except Exception:
                    webhook = None

                final_messagable: Union[discord.Webhook, discord.TextChannel] = (
                    channel if webhook is None else webhook
                )
                posts += 1
                try:
                    # send our message
                    # try sending to the channel first
                    if isinstance(final_messagable, discord.TextChannel):
                        await final_messagable.send(
                            embed=embed, view=PersistentView(commands.Context)
                        )
                    else:
                        await self.send_from_webhook(final_messagable, embed)
                    await asyncio.sleep(0.5)
                except discord.Forbidden as e:
                    # error is more likely to be a 404, check the logs regardless
                    log(
                        f"AutoPosting - error | {channel.guild.id} / {channel.guild.name} / {channel.id}"
                    )
                    log(f"AutoPosting - error | {e}")
                    log(f"AutoPosting - error | {e.__traceback__}")
                    log("AutoPosting - Removing hentai channel from database")
                    # this is probably an awful idea but its the only way to remove the channel if the bot is not allowed to post in it
                    # lets hope discord doesnt fuck up and the webhook is actually there
                    await guild.modify(hentai_channel_id=None)

                    # subtarct 1 from the posts
                    posts -= 1

                except Exception as e:
                    capture_exception(e)
                    log("AutoPosting - Autoposting has failed. Reloading the cog...")
                    await self.bot.reload_extension("Cogs.autoposting")
                    return

            # log the number of posts
            comp_embed = Embed(
                title=f"{Emoji.yes} Autoposting batch completed",
                description=f"*Posted: `{posts}`*",
                color=colors.green,
                thumbnail=None,
            )
            comp_embed.set_footer(text=f"Scanned {len(self.bot.guilds)} total entries!")
            sys = await self.bot.fetch_channel(1004423443833442335)
            await sys.send(embed=comp_embed)
            log(f"Autoposting - Posted Batch: {formatColor(str(posts), 'green')}")
            if posts == 0:
                # reload the cog if there are no posts made
                log("Autoposting - No posts were made. Reloading the cog.")
                await self.bot.reload_extension("Cogs.autoposting")
                return

    @autoh.before_loop
    async def delay_task_until_bot_ready(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)
        start_embed = Embed(
            title=f"{Emoji.loading} Autoposting batch started",
            color=colors.prim,
            thumbnail=None,
        )
        sys = await self.bot.fetch_channel(1004423443833442335)
        await sys.send(embed=start_embed)

    @autoh.after_loop
    async def run_when_done(self):
        start_embed = Embed(
            title=f"{Emoji.yes} Autoposting batch finished",
            color=colors.green,
            thumbnail=None,
        )
        sys = await self.bot.fetch_channel(1004423443833442335)
        await sys.send(embed=start_embed)

    async def cog_unload(self) -> None:
        self.autoh.stop()
        log("Autoposting - Stopped")
        stop_embed = Embed(
            title=f"{Emoji.no} Autoposting stopped.", thumbnail=None, color=colors.red
        )
        sys = await self.bot.fetch_channel(1004423443833442335)
        await sys.send(embed=stop_embed)

    async def cog_reload(self) -> None:
        self.autoh.stop()
        log("Autoposting - Reloaded")
        reload_embed = Embed(
            title=f"{Emoji.loading} Autoposting reloaded.",
            thumbnail=None,
            color=colors.red,
        )
        sys = await self.bot.fetch_channel(1004423443833442335)
        await sys.send(embed=reload_embed)

    async def cog_load(self) -> None:
        self.autoh.start()


async def setup(bot: Bot) -> None:
    await bot.add_cog(autoposting(bot))
