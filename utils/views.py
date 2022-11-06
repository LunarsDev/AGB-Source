from __future__ import annotations
from urllib import parse
from contextlib import suppress
from textwrap import dedent, indent
from typing import TYPE_CHECKING, Literal, Optional, Union

import discord
from aiohttp import ClientSession
from discord import ButtonStyle, Forbidden, HTTPException
from discord.ext import commands
from discord.ui import View, button
from utils import imports

if TYPE_CHECKING:
    from Cogs.admin import Admin
    from discord import (
        Interaction,
        InteractionMessage,
        Member,
        Message,
        TextChannel,
        User,
        WebhookMessage,
    )
    from discord.ui import Button
    from index import AGB

    UserT = Union[Member, User]
    MessageT = Union[Message, WebhookMessage, InteractionMessage]


__all__: tuple[str, ...] = ("APIImageReporter", "APIImageDevReport")


class APIImageReportView(View):
    # this is for easy editing reasons
    # like if we want to change it quickly instead of looking through the code
    ADMIN_COG_NAME: str = "admin"
    TEMP_BAN_DAYS: int = 3
    TEMP_BAN_REASON: str = "Reporting an image that does not follow our image report guidelines."
    REPORT_CHANNEL_ID: int = 990187200656322601

    GUIDELINE_PREFIX: str = "**__*__**"
    GUIDELINES: list[str] = [
        "Image is SFW (not actual porn, lewd / suggestive positions and actions, etc)",
        "Gross (scat, gore, rape, etc)",
        "Breaks ToS (shota, loli, etc)",
    ]
    REPORT_GUIDELINE_SCRIPT: str = dedent(
        """
    Hello user, the image you reported does not fall under our image report guidelines. \
You must only report an image if the image falls under these guidelines:
    {guidelines}
    
    If you continue to report images that are not eligible to be reported, you will get a 3 day blacklist. \
If you continue your blacklist will be permanent.

    The image(s) that do not follow our guidelines: ||{url}||
    """
    )

    INITIAL_REPORT_MESSAGE = dedent(
        """                    
    Thank you for reporting this image, we trust that you reported it correctly; by following our rules, \
we will take action against any image that is deemed to be in violation of our rules.
        
    Images are eligible for reporting if they are in violation of our following rules:
    {guidelines}
    """
    )

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @property
    def formatted_guidelines(self) -> dict[Literal["guidelines"], str]:
        space_before_prefix = "    "
        space_after_prefix = " "
        prefix = f"{space_before_prefix}{self.GUIDELINE_PREFIX}{space_after_prefix}"
        text = indent("\n".join(self.GUIDELINES), prefix)
        return {"guidelines": text}

    async def remove_image(self, interaction: Interaction, /, url: str) -> None:
        bot: AGB = interaction.client  # type: ignore
        cog: Admin = bot.get_cog(self.ADMIN_COG_NAME)  # type: ignore

        rmcode = parse.urlsplit(url)[2][1:].replace("moondust/", "")
        await cog.remove_images(rmcode)

    def get_image_url(self, message: Optional[MessageT], /) -> Optional[str]:
        # can happen i guess
        if not message or not message.embeds:
            return None

        first_embed = message.embeds[0]
        # this returns None if there was no image on the embed, so its safe to use.
        return first_embed.image.url

    async def temp_ban_user(self, interaction: Interaction, /, user_id: int) -> None:
        bot: AGB = interaction.client  # type: ignore
        base_kwargs = {
            "blacklisted": True,
            "blacklistedtill": self.TEMP_BAN_DAYS,
            "reason": self.TEMP_BAN_REASON,
        }

        is_blacklisted = await bot.db.fetch_blacklist(user_id)
        if is_blacklisted:
            await is_blacklisted.edit(**base_kwargs)
        else:
            await bot.db.add_blacklist(user_id=user_id, **base_kwargs)

    async def delete_message(self, message: Optional[MessageT], /, *, delay: Optional[int] = None) -> Optional[str]:
        # can happen i guess
        if not message:
            return

        with suppress(Forbidden, HTTPException):

            await message.delete(delay=delay)


class APIImageReporter(APIImageReportView):
    def __init__(self):
        super().__init__()
        self.config = imports.get("config.json")
        self._report_channel: TextChannel = None  # type: ignore

    async def report_channel(self, interaction: Interaction, /) -> TextChannel:
        if self._report_channel is not None:
            return self._report_channel

        # type: ignore
        self._report_channel = await interaction.client.fetch_channel(self.REPORT_CHANNEL_ID)
        return self._report_channel  # type: ignore

    @button(
        label="Report to Developers",
        style=ButtonStyle.blurple,
        custom_id="APIImageReporter_report_to_devs",
    )
    async def report(self, interaction: Interaction, button: Button) -> None:
        # get the embeds image url
        embed_image = self.get_image_url(interaction.message)
        url = self.get_image_url(interaction.message)
        if not embed_image:
            await interaction.response.send_message("Something went wrong...", ephemeral=True)
            return

        # req below is slow sometimes
        await interaction.response.defer()

        async def edit_view() -> None:
            if not interaction.message:
                return

            with suppress(Forbidden, HTTPException):
                await interaction.message.edit(view=self)

        async with ClientSession() as session:
            async with session.get(embed_image) as resp:
                if resp.status == 200:
                    channel = await self.report_channel(interaction)
                    dev_view = APIImageDevReport(
                        original_message=interaction.message,
                        original_author=interaction.user,
                    )
                    if interaction.user.id in self.config.owners:
                        await channel.send(
                            f"**{embed_image} reported by a Developer, delete immediately!**", view=dev_view
                        )
                    else:
                        await channel.send(
                            f"{embed_image} reported by {interaction.user.id}",
                            view=dev_view,
                        )
                    # disable the button once its been used
                    button.disabled = True
                    await edit_view()
                    await interaction.followup.send(
                        self.INITIAL_REPORT_MESSAGE.format(**self.formatted_guidelines),
                        ephemeral=True,
                    )
                else:
                    await edit_view()
                    await interaction.followup.send(
                        "Report failed.\nThe image you sent was not found in the api.",
                        ephemeral=True,
                    )

    async def interaction_check(self, interaction: Interaction) -> bool:
        bot: AGB = interaction.client  # type: ignore
        user_id = interaction.user.id
        blacklisted_user = await bot.db.fetch_blacklist(user_id)

        if blacklisted_user and blacklisted_user.is_blacklisted:
            await interaction.response.send_message(
                f"You are blacklisted from using this bot for the following reason\n`{blacklisted_user.reason}`",
                ephemeral=True,
            )
            return False

        return True


class APIImageDevReport(APIImageReportView):
    # optional for persistent reasons.
    def __init__(
        self,
        *,
        original_message: Optional[MessageT] = None,
        original_author: Optional[UserT] = None,
    ) -> None:
        super().__init__()

        # this will be the message with the embed with the image
        self.original_message: Optional[MessageT] = original_message
        self.original_author: Optional[UserT] = original_author
        self.config = imports.get("config.json")

    @button(
        label="Approve",
        style=ButtonStyle.green,
        custom_id="AutopostingReport_approve",
    )
    async def approve_button(
        self,
        interaction: Interaction,
        button: Button,
    ) -> None:
        url = self.get_image_url(self.original_message)
        # can this happen? and should it just do nothing?
        if not url:
            return await interaction.response.send_message("No image found", ephemeral=True)

        # gotta respond
        await interaction.response.send_message("Removing image...", ephemeral=True)
        await self.remove_image(interaction, url)
        await self.delete_message(self.original_message)
        await interaction.edit_original_response(
            content="Deleted the message and removed the image from the api.",
            view=None,
        )

        await self.delete_message(interaction.message, delay=5)

    @button(
        label="Deny",
        style=ButtonStyle.red,
        custom_id="AutopostingReport_deny",
    )
    async def deny_button(
        self,
        interaction: Interaction,
        button: Button,
    ) -> None:
        url = self.get_image_url(self.original_message)
        # can this happen? and should it just do nothing?
        if not url:
            return await interaction.response.send_message("No image found", ephemeral=True)

        button.disabled = True
        await interaction.response.edit_message(view=self)

        have_dmed: Optional[bool] = False
        message = ""

        if self.original_author:
            # dm the user or temp ban them
            try:
                await self.original_author.send(
                    self.REPORT_GUIDELINE_SCRIPT.format(
                        url=url,
                        **self.formatted_guidelines,
                    )
                )
            except (HTTPException, Forbidden):
                # if we cant dm them, we temp ban them
                await self.temp_ban_user(interaction, self.original_author.id)
            else:
                have_dmed = True

            base_content = f"The image reporter ({self.original_author} ({self.original_author.id})) "
            if have_dmed:
                base_content += "has been DM'd."
            else:
                base_content += f"could not be DM'd and has been temporarily banned for {self.TEMP_BAN_DAYS} days."

        else:
            base_content = "The original author could not be found."
            if self.original_message:
                base_content += (
                    f"\nHere is the GUILD ID and CHANNEL ID of the original message:\n"
                    f"Guild ID: {self.original_message.guild.id if self.original_message.guild else 'N/A'}\n"
                    f"Channel ID: {self.original_message.channel.id}"
                )
        message = base_content
        await interaction.followup.send(message, ephemeral=True)
        await self.delete_message(interaction.message, delay=5)


class FreeNitroView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.value = None

    @discord.ui.button(label="Claim", custom_id="claim", style=discord.ButtonStyle.green)
    async def claim(self, interaction: discord.Interaction, _):
        await interaction.response.send_message(content="https://imgur.com/NQinKJB", embed=None, ephemeral=True)


class UserinfoPermissionView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.value = None

    @discord.ui.button(
        label="Permissions",
        custom_id="userinfoperms",
        style=discord.ButtonStyle.blurple,
    )
    async def userperm(self, interaction: discord.Interaction, _):
        perms = ", ".join(
            [f"`{p}`".replace("_", " ") for p, value in interaction.user.guild_permissions if value is True]
        )
        if "administrator" in perms:
            perms = "`Administrator` (All permissions)"
        await interaction.response.edit_message(content=perms, embed=None, view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message("This isn't your command!", ephemeral=True)
        return False
