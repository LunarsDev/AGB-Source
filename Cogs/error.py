from __future__ import annotations
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Union

from asyncio import TimeoutError
from random import randint

from discord import Message, TextChannel
from discord.errors import HTTPException, InteractionResponded, NotFound
from discord.ext import commands
from discord.ext.commands.cooldowns import CooldownMapping
from discord.ext.commands.errors import (
    BotMissingPermissions,
    # CheckFailure,
    CommandError,
    CommandInvokeError,
    CommandNotFound,
    CommandOnCooldown,
)
from discord.ext.commands.errors import DisabledCommand as DisabledCommandError
from discord.ext.commands.errors import (
    ExtensionError,
    HybridCommandError,
    MaxConcurrencyReached,
    MissingPermissions,
    MissingRequiredArgument,
    NotOwner,
    NSFWChannelRequired,
    UserInputError,
)
from index import config
from Manager.logger import formatColor
from sentry_sdk import capture_exception, last_event_id

from utils.embeds import EmbedMaker as Embed
from utils.checks import MusicGone, NotVoted
from utils.default import log
from utils.errors import BlacklistedUser, DatabaseError, DisabledCommand

# from re import compile, IGNORECASE
# from typing import Pattern


if TYPE_CHECKING:
    from discord import Message
    from discord.app_commands.checks import Cooldown
    from index import Bot


class Error(commands.Cog, name="error"):
    DEFAULT_COLOR: ClassVar[int] = 0xFF0000

    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.message_cooldown: CooldownMapping[Message] = CooldownMapping.from_cooldown(
            rate=1.0, per=randint(5, 45), type=commands.BucketType.user
        )
        # self.nword_re: Pattern[str] = compile(
        #   r"(n|m|и|й)(i|1|l|!|ᴉ|¡)(g|ƃ|6|б)(g|ƃ|6|б)(e|3|з|u)(r|Я)",
        #   IGNORECASE
        # )
        self.to_ignore = (
            CommandNotFound,
            HTTPException,
            NotFound,
            InteractionResponded,
            # CheckFailure,
        )
        self.send_embed = (
            # custom errors
            NotVoted,
            MusicGone,
            DisabledCommand,
            BlacklistedUser,
            DatabaseError,
            # user input errors
            UserInputError,
            # extensions
            ExtensionError,
            # owner
            NotOwner,
            # others command errors
            MaxConcurrencyReached,
            DisabledCommandError,
            # python error
            TimeoutError,
        )

    def is_on_cooldown(self, message: Message) -> bool:
        bucket: Optional[Cooldown] = self.message_cooldown.get_bucket(message)
        retry_after = bucket and bucket.update_rate_limit()
        return retry_after is not None

    async def create_embed(
        self,
        ctx: commands.Context,
        error: Union[CommandError, HybridCommandError, Exception],
    ):
        assert ctx.command
        emb = Embed(title="📣 Error!", description=str(error), color=self.DEFAULT_COLOR)
        emb.set_author(
            name=f"{ctx.author.name} | Command: {ctx.command.qualified_name}",
            icon_url=ctx.author.display_avatar.url,
        )
        await self.try_send(ctx, error, emb)

    def _handle_args(self, *contents: Union[Embed, Message, str]) -> dict[str, Any]:
        kwargs = {}
        for content in contents:
            if isinstance(content, Embed):
                if "embeds" in kwargs:
                    kwargs["embeds"].append(content)
                else:
                    kwargs.update(embeds=[content])
            elif isinstance(content, Message):
                kwargs.update(content=content.content, embeds=content.embeds)
            elif isinstance(content, str):
                kwargs.update(content=content)

        return kwargs

    async def try_send(
        self,
        ctx: commands.Context,
        error: Union[CommandError, HybridCommandError, Exception],
        *args: Union[Embed, Message, str],
        **kwargs,
    ):
        if args:
            kwargs |= self._handle_args(*args)

        try:
            await ctx.send(**kwargs)
        except Exception as e:
            capture_exception(e)
            if any(k in ["embed", "embeds"] for k in kwargs):
                embed_perms = (
                    ctx.channel.permissions_for(ctx.guild.me).embed_links
                    if ctx.guild
                    else False
                )
                if not embed_perms:
                    await ctx.send(f"`{error}`\n***Enable embed permissions please.***")

    @commands.Cog.listener()
    async def on_command_error(
        self,
        ctx: commands.Context,
        error: Union[CommandError, HybridCommandError, Exception],
    ) -> Any:
        if isinstance(error, CommandInvokeError):
            error = error.original

        if isinstance(error, self.to_ignore):
            return

        assert ctx.command, "ctx.command was None!"
        if isinstance(error, self.send_embed):
            await self.create_embed(ctx, error)
            return

        if self.is_on_cooldown(ctx.message):
            return

        if isinstance(error, (MissingPermissions, BotMissingPermissions)):
            bot_or_user = "I'm" if isinstance(error, BotMissingPermissions) else "You"
            missing_permissions = ", ".join(error.missing_permissions)
            emb = Embed(
                title="👮‍♂️ Permissions Error",
                description=f"{bot_or_user} missing the following permissions:\n{missing_permissions}",
                color=self.DEFAULT_COLOR,
            )
            emb.set_author(
                name=f"{ctx.author.name} | Command: {ctx.command.qualified_name}",
                icon_url=ctx.author.display_avatar.url,
            )
            await self.try_send(ctx, error, emb)
        elif isinstance(error, MissingRequiredArgument):
            assert (
                ctx.command
            ), "Command is None but MissingRequiredArgument was raised."
            emb = Embed(
                title="💬 Missing required argument!",
                color=self.DEFAULT_COLOR,
                description=(
                    f"You're missing the following required argument: {error.param.name}\n"
                    f"try again by doing `{ctx.command.signature}`\n"
                    f"if you still don't understand, type `{ctx.prefix}help {ctx.command}`",
                ),
            )

            emb.set_author(
                name=f"{ctx.author.name} | Command: {ctx.command.qualified_name}",
                icon_url=ctx.author.display_avatar.url,
            )
            await self.try_send(ctx, error, emb)
        elif isinstance(error, CommandOnCooldown):
            assert ctx.command, "Command is None but CommandOnCooldown was raised."
            log(
                f"{formatColor(ctx.author.name, 'gray')} tried to use {ctx.command.name} but it was on cooldown for {error.retry_after:.2f} seconds."
            )
            day = round(error.retry_after / 86400)
            hour = round(error.retry_after / 3600)
            minute = round(error.retry_after / 60)

            emb = Embed(
                title="⏱️ Cooldown!",
                description="This command has a cooldown for ",
                color=self.DEFAULT_COLOR,
            )
            assert emb.description is not None
            emb.set_author(
                name=f"{ctx.author.name} | Command: {ctx.command.qualified_name}",
                icon_url=ctx.author.display_avatar.url,
            )
            if day > 0:
                emb.description += f"{str(day)}day(s)"
            elif hour > 0:
                emb.description += f"{str(hour)} hour(s)"
            elif minute > 0:
                emb.description += f"{str(minute)} minute(s)"
            else:
                emb.description += f"{error.retry_after:.2f} second(s)"

            await self.try_send(ctx, error, emb, delete_after=error.retry_after)
        elif isinstance(error, NSFWChannelRequired):
            emb = Embed(
                title="🔞 NSFW Only!",
                description="This command is for NSFW channels only!",
                color=self.DEFAULT_COLOR,
                timestamp=ctx.message.created_at,
            )
            emb.set_image(url="https://i.hep.gg/hdlOo67BI.gif")
            emb.set_author(
                name=f"{ctx.author.name} | Command: {ctx.command.qualified_name}",
                icon_url=ctx.author.display_avatar.url,
            )
            await self.try_send(ctx, error, emb)
        else:
            capture_exception(error)
            error_collection_channel: TextChannel = self.bot.get_channel(
                1012190141709828237
            )  # type: ignore
            event_id: Optional[str] = last_event_id()
            issue_url: Optional[str] = (
                f"https://sentry.hep.gg/organizations/lunar-development/issues/?query={event_id}"
                if event_id
                else None
            )
            errorResEmbed = Embed(
                title="❌ Error!",
                color=self.DEFAULT_COLOR,
                description=f"*An unknown error occurred!*\n\n**Join the server with your Error ID for support: {config.Server}.**",
            )

            errorResEmbed.set_footer(text="This error has been automatically logged.")
            await self.try_send(
                ctx, error, content=f"**Error ID:** `{event_id}`", embed=errorResEmbed
            )
            embed = Embed(
                title=f"New Bug Submitted By {ctx.author.name}.",
                color=self.DEFAULT_COLOR,
            )
            if issue_url:
                embed.url = issue_url
            embed.add_field(name="Event ID", value=f"`{event_id}`", inline=False)
            embed.add_field(
                name="Issue URL", value=f"[Click here]({issue_url})", inline=False
            )

            embed.add_field(
                name="ℹ️ More info:",
                value=(
                    f"`Command:` {ctx.command.qualified_name if ctx.command else 'N/A'}\n"
                    f"`User ID:` {ctx.author.id}\n"
                    f"`Channel ID:` {ctx.channel.id}\n"
                    f"`Message ID:` {ctx.message.id}\n"
                    f"`Guild ID:` {ctx.guild.id if ctx.guild else 'N/A'}\n"
                ),
            )
            await error_collection_channel.send(embed=embed)

        return


async def setup(bot: Bot) -> None:
    await bot.add_cog(Error(bot))
