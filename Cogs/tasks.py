from __future__ import annotations

from typing import TYPE_CHECKING

import discordlists
from discord.ext import commands, tasks
from utils import imports

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
        # self.fear_apiUrl = "https://fearvps.tk/api/users/edit"
        # self.fear_api.start()
        self.config = imports.get("config.json")
        self.api = discordlists.Client(self.bot)
        self.api.set_auth("top.gg", self.config.topgg)
        self.api.set_auth("fateslist.xyz", self.config.fates)
        self.api.set_auth("blist.xyz", self.config.blist)
        self.api.set_auth("discordlist.space", self.config.discordlist)
        self.api.set_auth("discord.bots.gg", self.config.discordbots)
        self.api.set_auth("bots.discordlabs.org", self.config.discordlabs)
        self.api.start_loop()
        self.start_chunking.start()

    @tasks.loop(count=None, minutes=20)
    async def start_chunking(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            if not guild.chunked:
                await guild.chunk()

    # async def post_fear(self):
    #     headers = {"Content-Type": "application/json"}
    #     data = {
    #         "pass": "Motz$Fear11",
    #         "user": "motz",
    #         "bot_users": len(self.bot.users),
    #         "bot_servers": len(self.bot.guilds),
    #         "bot_shards": len(self.bot.shards),
    #     }
    #     async with aiohttp.ClientSession() as f:
    #         async with f.post(self.fear_apiUrl, json=data, headers=headers) as r:
    #             if r.status == 200:
    #                 # Successful Post
    #                 # print(f"{await r.json()}")
    #                 pass
    #             elif r.status == 400:
    #                 logger.error(f"{await r.json()}")
    #                 # pass
    #             elif r.status == 201:
    #                 # Successful Post
    #                 # print(f"{await r.json()}")
    #                 pass
    #             pass

    # @tasks.loop(minutes=1)
    # async def fear_api(self):
    #     await self.bot.wait_until_ready()
    #     # await self.post_fear()

    async def cog_unload(self):
        # self.fear_api.stop()
        self.api.stop()
        self.start_chunking.stop()


async def setup(bot: Bot) -> None:
    await bot.add_cog(Tasks(bot))
