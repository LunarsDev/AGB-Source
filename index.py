import logging
import os
import gc
import random
from datetime import datetime, timezone

import aiohttp
import discord
from lunarapi import Client
import sentry_sdk
from colorama import Fore, Style, init
from discord import Interaction, app_commands
from discord.ext import commands
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.modules import ModulesIntegration
from sentry_sdk.integrations.threading import ThreadingIntegration

from Manager.database import Database
from Manager.logger import formatColor
from utils import imports, permissions
from utils.errors import DisabledCommand
from utils.views import APIImageDevReport, APIImageReporter

gc.enable()

# Set timezone
os.environ["TZ"] = "America/New_York"

init()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format=f"{f'{Fore.MAGENTA}%(asctime)s{Style.RESET_ALL}'} | {Fore.LIGHTYELLOW_EX}%(funcName)s(){Style.RESET_ALL} | {Fore.MAGENTA}%(levelname)s{Style.RESET_ALL} {Fore.WHITE}>>>{Style.RESET_ALL} {Style.DIM}%(message)s{Style.RESET_ALL}",
    datefmt="%m-%e %T %p",
)


config = imports.get("config.json")
emojis = imports.get("emojis.json")
db_config = imports.get("db_config.json")

EMBED_COLOUR = 0x2F3136
embed_space = "\u200b "
yes = "<:checked:825049250110767114>"
no = "<:zzz_playroomx:825049236802240563>"
delay = 10
Error = 0xE20000
TOP_GG_TOKEN = config.topgg
DEV = config.dev
Website = "https://lunardev.group"
Logo = "https://lunardev.group/assets/logo.png"
Server = "https://discord.gg/cNRNeaX"
Vote = "https://top.gg/bot/723726581864071178/vote"
Invite = "https://discord.com/api/oauth2/authorize?client_id=723726581864071178&permissions=2083908950&scope=bot"
BID = "157421"
CHAT_API_KEY = "nbgYpq2Wh3MRVEm0"

slash_errors = (
    app_commands.CommandOnCooldown,
    app_commands.BotMissingPermissions,
    app_commands.CommandInvokeError,
    app_commands.MissingPermissions,
)


# async def create_slash_embed(self, interaction, error):
#     await interaction.response.defer(ephemeral=True, thinking=True)
#     embed = Embed(title="Error", colour=0xFF0000)
#     embed.add_field(name="Author", value=interaction.user.mention)True
async def update_command_usages(interaction: Interaction) -> bool:
    bot: AGB = interaction.client  # type: ignore # shut

    db_user = bot.db.get_user(interaction.user.id) or await bot.db.fetch_user(interaction.user.id)
    if not db_user:
        return False

    await db_user.modify(usedcmds=db_user.usedcmds + 1)
    return True


class AGBTree(app_commands.CommandTree):
    async def call(self, interaction):
        from utils.default import log

        await super()._call(interaction)
        if interaction.user.id in config.owners:
            log(
                f"{formatColor('[DEV]', 'bold_red')} {formatColor(interaction.user, 'red')} used command {formatColor(interaction.command.name, 'grey')}"
            )
            return
        log(
            f"{formatColor(interaction.user.id, 'grey')} used command {formatColor(interaction.command.name, 'grey')} in {formatColor(interaction.guild.id, 'grey')}"
        )


# Don't touch this.
sentry_logging = LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
sentry_sdk.init(
    config.sentryDSN,
    integrations=[
        sentry_logging,
        AioHttpIntegration(),
        ThreadingIntegration(propagate_hub=True),
        ModulesIntegration(),
    ],
    traces_sample_rate=1.0,
)

partners = ["dash.lunardev.group", "connect.twisea.net", "user.lunardev.group"]


class AGB(commands.AutoShardedBot):
    def __init__(self, intents: discord.Intents, *args, **kwargs) -> None:
        lunar_client: Client
        self.default_prefix = kwargs.get("default_prefix", config.prefix)
        default_status = "AAAAAAAAAA" if DEV else "my brain aint braining"
        self.embed_color = kwargs.get("embed_color", 3429595)
        super().__init__(
            command_prefix=commands.when_mentioned_or("tp!"),
            strip_after_prefix=True,
            case_insensitive=True,
            owner_ids=config.owners,
            help_command=None,
            reconnect=True,
            command_attrs=dict(hidden=True),
            status=discord.Status.online,
            activity=discord.Game(name=default_status),
            chunk_guilds_at_startup=False,
            max_messages=30,
            intents=intents,
            tree_cls=AGBTree,
            allowed_mentions=discord.AllowedMentions(roles=False, users=True, everyone=False, replied_user=False),
        )

        self.launch_time = datetime.now(timezone.utc)
        self.partners = random.choice(partners)
        self.message_cooldown = commands.CooldownMapping.from_cooldown(
            1.0, random.randint(1, 5), commands.BucketType.guild
        )
        self.config = imports.get("config.json")

        self.db: Database = Database(self, db_config)
        self.add_check(self.global_commands_check)

    async def setup_hook(self):
        await self.db.initate_database(chunk=DEV)
        self.session = aiohttp.ClientSession()
        self.lunar_client = Client(session=self.session, token=self.config.lunarapi.token)
        from utils.default import log

        self.add_view(APIImageReporter())
        self.add_view(APIImageDevReport())
        try:
            await self.load_extension("jishaku")
            log("Loaded JSK.")
        except Exception as e:
            log(f"Failed to load JSK: {e}")
        DISABLED_FOR_DEV = ()
        for file in os.listdir("Cogs"):
            if file.endswith(".py"):
                name = file[:-3]
                if DEV and name in DISABLED_FOR_DEV:
                    continue
                await self.load_extension(f"Cogs.{name}")
                log(f"Loaded Cog: {formatColor(name, 'green')}")

    async def close(self):
        await self.close_func()

    async def close_func(self):
        logger.info("Closing bot...")
        await super().close()
        await self.db.close()
        await self.session.close()

    async def on_message(self, msg) -> None:
        if not self.is_ready() or msg.author.bot or not permissions.can_send(msg):
            return
        await self.process_commands(msg)

        # if msg.content.lower().startswith("tp!"):
        #     msg.content = msg.content[: len("tp!")].lower() + msg.content[len("tp!") :]
        # if bot.user in msg.mentions:
        #     current_guild_info = self.db.get_guild(
        #         msg.guild.id
        #     ) or await self.db.fetch_guild(msg.guild.id)
        #     if current_guild_info:
        #         embed = Embed(
        #             title="Hi! My name is AGB!",
        #             url=Website,
        #             colour=colors.prim,
        #             description=f"If you like me, please take a look at the links below!\n[Add me]({config.Invite}) | [Support Server]({config.Server}) | [Vote]({config.Vote})",
        #             timestamp=msg.created_at,
        #         )
        #         embed.add_field(
        #             name="Prefix for this server:", value=f"{current_guild_info.prefix}"
        #         )
        #         embed.add_field(
        #             name="Help command", value=f"{current_guild_info.prefix}help"
        #         )
        #         embed.set_footer(
        #             text="lunardev.group",
        #             icon_url=msg.author.avatar,
        #         )
        #         bucket = self.message_cooldown.get_bucket(msg)
        #         if retry_after := bucket.update_rate_limit():
        #             return
        #         if (
        #             msg.reference is None
        #             and random.randint(1, 2) == 1
        #             or msg.reference is not None
        #         ):
        #             return
        #         try:
        #             await msg.channel.send(embed=embed)
        #             return
        #         except Exception:
        #             await msg.channel.send(
        #                 f"**Hi, My name is AGB!**\nIf you like me and want to know more information about me, please enable embed permissions in your server settings so I can show you more information!\nIf you don't know how, please join the support server and ask for help!\n{config.Server}"
        #             )

        # await self.process_commands(msg)

    async def on_message_edit(self, before, after):
        if before.content == after.content:
            return
        if before.author.bot:
            return
        self.dispatch("message", after)

    async def global_commands_check(self, ctx: commands.Context) -> bool:
        # commands can be disabled per guild, but should be allowed in dms.
        if not ctx.guild or not ctx.command:
            return True

        # allow jishaku and help to be used in all guilds
        # is there a better way to do this?
        WHITELISTED_COMMANDS = ("help", "jishaku", "jsk")
        if ctx.command.qualified_name.startswith(WHITELISTED_COMMANDS):
            if ctx.command.qualified_name.startswith(("jishaku", "jsk")):
                return await ctx.bot.is_owner(ctx.author)
            return True

        guild_command_entry = self.db.get_command(ctx.guild.id)
        if not guild_command_entry or not guild_command_entry.disabled:
            # no commands disabled...
            return True

        is_group: bool = isinstance(ctx.command, commands.Group) or ctx.command.parent is not None
        disabled_commands = []
        left_overs = []
        if not is_group and guild_command_entry.is_disabled(ctx.command.qualified_name):
            raise DisabledCommand(is_group=False, qualified_name=ctx.command.qualified_name)

        group_disabled = False
        for index, cmd in enumerate(ctx.command.qualified_name.split(" ")):
            if guild_command_entry.is_disabled(cmd):
                if index == 0:
                    group_disabled = True
                disabled_commands.append(cmd)
            else:
                left_overs.append(cmd)

        if disabled_commands:
            raise DisabledCommand(
                is_group=is_group,
                qualified_name=ctx.command.qualified_name,
                group_disabled=group_disabled,
                disabled=disabled_commands,
            )
        return True


intents = discord.Intents.default()
intents.members = True

bot = AGB(intents)

os.environ.setdefault("JISHAKU_HIDE", "1")
os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"


@bot.check
def no_badwords(ctx):
    return "n word" not in ctx.message.content.lower()


@bot.check
def no_nwords(ctx):
    return "reggin" not in ctx.message.content.lower()


class colors:
    default = 0
    prim = 0x2F3136
    teal = 0x1ABC9C
    dark_teal = 0x11806A
    green = 0x2ECC71
    dark_green = 0x1F8B4C
    blue = 0x3498DB
    dark_blue = 0x206694
    purple = 0x9B59B6
    dark_purple = 0x71368A
    magenta = 0xE91E63
    dark_magenta = 0xAD1457
    gold = 0xF1C40F
    dark_gold = 0xC27C0E
    orange = 0xE67E22
    dark_orange = 0xA84300
    red = 0xE74C3C
    dark_red = 0x992D22
    lighter_grey = 0x95A5A6
    dark_grey = 0x607D8B
    light_grey = 0x979C9F
    darker_grey = 0x546E7A
    blurple = 0x7289DA
    greyple = 0x99AAB5


if __name__ == "__main__":
    if DEV is True:
        bot.run(config.devtoken, log_handler=None)
    else:
        bot.run(config.token, log_handler=None)
