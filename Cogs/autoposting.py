from __future__ import annotations

import asyncio
import datetime
import random
from typing import TYPE_CHECKING, Union

import aiohttp
import discord
from discord.ext import commands, tasks
from index import DEV, colors, config
from lunarapi import Client, endpoints
from Manager.emoji import Emoji
from Manager.logger import formatColor
from sentry_sdk import capture_exception
from utils import imports
from utils.default import log
from utils.embeds import EmbedMaker as Embed
from utils.views import APIImageReporter

if TYPE_CHECKING:
    from index import AGB

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
    def __init__(self, bot: AGB):
        self.bot: AGB = bot
        self.config = imports.get("config.json")
        self.lunar_headers = {f"{config.lunarapi.header}": f"{config.lunarapi.token}"}

    async def get_hentai_img(self) -> str:
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
            client = Client(session=session, token=config.lunarapi.token)
            img = await client.request(endpoints.nsfw(random.choice(cats)))
            return await img.to_dict()

    async def send_from_webhook(self, webhook: discord.Webhook, embed: discord.Embed) -> None:
        try:
            await webhook.send(
                embed=embed,
                avatar_url=self.bot.user.display_avatar.url,  # type: ignore
                view=APIImageReporter(),  # type: ignore
            )
        except Exception as e:
            capture_exception(e)
            log(f"AutoPosting - webhook error | {formatColor(e), 'red'}")
            return

    async def get_or_fetch_user(self, user_id: int):
        user = self.bot.get_user(user_id)
        if user is None:
            user = await self.bot.fetch_user(user_id)
        return user

    async def get_or_fetch_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(channel_id)
        return channel

    @tasks.loop(minutes=5)
    async def autoh(self):
        posts = 0

        when = self.autoh.next_iteration or (discord.utils.utcnow() + datetime.timedelta(minutes=5))

        embed = Embed(
            title="Enjoy your poggers porn lmao",
            description=f"Posting again: {discord.utils.format_dt(when, style='R')}\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate})",
            colour=colors.prim,
        )

        db_guilds = await self.bot.db.fetch_guilds()
        hentai_channel_ids = [(x, x.hentai_channel_id) for x in db_guilds if x.hentai_channel_id is not None]

        # for _ in range(len(hentai_channel_ids)):
        #     data = await get_hentai_img()
        channel = ""
        for (guild, channel_id) in hentai_channel_ids:
            try:
                embed.set_image(url=(await self.get_hentai_img())["url"])
            except Exception:
                # try again
                try:
                    embed.set_image(url=(await self.get_hentai_img())["url"])
                except Exception as e:
                    log(f"Autoposting - Failure | {formatColor(e), 'red'}")
                    return
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                log(f"Autoposting - {channel.id} is invalid, removing the channel.")
                await guild.edit(hentaichannel=None)
                continue

            if not channel:
                continue

            # channel is not a text channel, continue
            if not (hasattr(channel, "guild") and channel.guild):  # type: ignore
                continue

            # shut the linter still complaining about this
            if not isinstance(channel, discord.TextChannel):
                raise AssertionError

            # ignore bot lists.
            if channel.guild.id in BotList_Servers:
                continue

            # chunk guilds if not chunked
            if not channel.guild.chunked:
                await channel.guild.chunk()

            # remove channel from db if it's not a NSFW channel
            if not channel.is_nsfw():
                await guild.edit(hentaichannel=None)
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
                webhook = discord.utils.get(webhooks, name="AGB Autoposting", user=self.bot.user)
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

            final_messagable: Union[discord.Webhook, discord.TextChannel] = channel if webhook is None else webhook
            posts += 1
            try:
                # send our message
                # try sending to the channel first
                if isinstance(final_messagable, discord.TextChannel):
                    await final_messagable.send(embed=embed, view=APIImageReporter())
                else:
                    await self.send_from_webhook(final_messagable, embed)
            except discord.Forbidden as e:
                # error is more likely to be a 404, check the logs regardless
                log(f"AutoPosting - error | {channel.guild.id} / {channel.guild.name} / {channel.id}")
                log(f"AutoPosting - error | {e}")
                log(f"AutoPosting - error | {e.__traceback__}")
                log("AutoPosting - Removing hentai channel from database")
                # this is probably an awful idea but its the only way to remove the channel if the bot is not allowed to post in it
                # lets hope discord doesnt fuck up and the webhook is actually there
                await guild.edit(hentaichannel=None)

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
        sys = await self.get_or_fetch_channel(1004423443833442335)
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
        sys = await self.get_or_fetch_channel(1004423443833442335)
        await sys.send(embed=start_embed)

    @autoh.after_loop
    async def run_when_done(self):
        start_embed = Embed(
            title=f"{Emoji.yes} Autoposting batch finished",
            color=colors.green,
            thumbnail=None,
        )
        sys = await self.get_or_fetch_channel(1004423443833442335)
        await sys.send(embed=start_embed)

    async def cog_unload(self) -> None:
        if not DEV:
            self.autoh.stop()
            log("Autoposting - Stopped")
            stop_embed = Embed(title=f"{Emoji.no} Autoposting stopped.", thumbnail=None, color=colors.red)
            sys = await self.get_or_fetch_channel(1004423443833442335)
            await sys.send(embed=stop_embed)

    async def cog_reload(self) -> None:
        if not DEV:
            self.autoh.stop()
            log("Autoposting - Reloaded")
            reload_embed = Embed(
                title=f"{Emoji.loading} Autoposting reloaded.",
                thumbnail=None,
                color=colors.red,
            )
            sys = await self.get_or_fetch_channel(1004423443833442335)
            await sys.send(embed=reload_embed)

    async def cog_load(self) -> None:
        if not DEV:
            self.autoh.start()


async def setup(bot: AGB) -> None:
    await bot.add_cog(autoposting(bot))
