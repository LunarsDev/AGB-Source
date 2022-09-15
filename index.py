import asyncio
import logging
import os
import random
from datetime import datetime, timezone

import discord
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
from utils.errors import DatabaseError, DisabledCommand
from utils.views import APIImageReporter, APIImageDevReport

# Set timezone
os.environ["TZ"] = "America/New_York"

try:
    import uvloop  # type: ignore
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

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
BID = "notforyou"
CHAT_API_KEY = "notforyou"

slash_errors = (
    app_commands.CommandOnCooldown,
    app_commands.BotMissingPermissions,
    app_commands.CommandInvokeError,
    app_commands.MissingPermissions,
)


#


# async def create_slash_embed(self, interaction, error):
#     await interaction.response.defer(ephemeral=True, thinking=True)
#     embed = Embed(title="Error", colour=0xFF0000)
#     embed.add_field(name="Author", value=interaction.user.mention)True
async def update_command_usages(interaction: Interaction) -> bool:
    bot: Bot = interaction.client  # type: ignore # shut

    db_user = bot.db.get_user(interaction.user.id) or await bot.db.fetch_user(
        interaction.user.id
    )
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
sentry_logging = LoggingIntegration(
    level=logging.INFO, event_level=logging.ERROR)
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

partners = ["melonbot.io", "Play with us: mc.lunardev.group"]


class Bot(commands.AutoShardedBot):
    def __init__(self, intents: discord.Intents, *args, **kwargs) -> None:
        self.default_prefix = kwargs.get("default_prefix", config.prefix)
        default_status = "AGB Beta <3" if DEV else "Hi <3"
        self.embed_color = kwargs.get("embed_color", 3429595)
        super().__init__(
            command_prefix=commands.when_mentioned_or("tp!"),
            strip_after_prefix=True,
            case_insensitive=True,
            owner_ids=config.owners,
            help_command=None,
            reconnect=True,
            command_attrs=dict(hidden=True),
            status=discord.Status.dnd,
            activity=discord.Game(name=default_status),
            chunk_guilds_at_startup=False,
            intents=intents,
            tree_cls=AGBTree,
            allowed_mentions=discord.AllowedMentions(
                roles=False, users=True, everyone=False, replied_user=False
            ),
        )

        self.launch_time = datetime.now(timezone.utc)
        self.partners = random.choice(partners)
        self.message_cooldown = commands.CooldownMapping.from_cooldown(
            1.0, random.randint(1, 5), commands.BucketType.guild
        )

        self.db: Database = Database(self, db_config)
        self.add_check(self.global_commands_check)

    async def setup_hook(self):
        await self.db.initate_database(chunk=True)
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

    async def on_message(self, msg) -> None:
        if not self.is_ready() or msg.author.bot or not permissions.can_send(msg):
            return
        await self.process_commands(msg)

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

        try:
            command = self.db.get_command(
                ctx.command.name
            ) or await self.db.fetch_command(ctx.command.name, cache=True)
            if command is None:
                command = await self.db.add_command(ctx.command.name)
                return True
        except DatabaseError as e:
            sentry_sdk.capture_exception(e)
            return True

        command_state = command.state_in(ctx.guild.id)
        if command_state is True:
            raise DisabledCommand()
        return True


intents = discord.Intents.default()
intents.members = True

bot = Bot(intents)

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
    prim = 1592481
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
