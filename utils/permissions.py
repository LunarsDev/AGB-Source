import contextlib

import discord
from discord import app_commands
from discord.ext import commands
from index import Website, colors

from utils import imports
from utils.embeds import EmbedMaker as Embed

owners = imports.config()["owners"]
mcstaff = imports.config()["mcstaff"]


def is_owner(ctx):
    """Checks if the author is one of the owners"""

    return ctx.author.id in owners


def is_mcstaff(ctx):
    return ctx.author.id in mcstaff


async def is_owner_slash(interaction: discord.Interaction):
    """Checks if the interaction user is one of the owners"""

    await interaction.response.defer(ephemeral=True, thinking=True)
    if interaction.user.id in owners:
        return True
    await interaction.followup.send(
        "You are not one of the owners of this bot. You can't use this command.",
        ephemeral=True,
    )
    return False


async def check_permissions(ctx, perms, *, check=all):
    """Checks if author has permissions to a permission"""

    if ctx.author.id in owners:
        return True

    resolved = ctx.channel.permissions_for(ctx.author)
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


async def slash_check_permissions(interaction: discord.Interaction, perms, *, check=all):
    """Checks if author has permissions to a permission"""

    if interaction.user.id in owners:
        return True
    resolved = interaction.channel.permissions_for(interaction.user)
    check(getattr(resolved, name, None) == value for name, value in perms.items())
    return


def dynamic_ownerbypass_cooldown(rate: int, per: float, type):
    def actual_func(message):
        return None if message.author.id in owners else commands.Cooldown(rate, per)

    return commands.dynamic_cooldown(actual_func, type)


def has_permissions(*, check=all, **perms):
    """discord.Commands method to check if author has permissions"""

    async def pred(ctx):
        if ctx.author.id in owners:
            return True

        return await commands.has_permissions(**perms).predicate(ctx)

    return commands.check(pred)


def slash_has_permissions(*, check=all, **perms):
    """discord.app_commands method to check if author has permissions"""

    async def pred(interaction):
        if interaction.user.id in owners:
            return True

        return await app_commands.checks.has_permissions(**perms).predicate(interaction)

    return app_commands.check(pred)


async def make_embed(
    ctx,
    title: str = None,
    description: str = None,
    url=Website,
    author: str = None,
    author_icon: str = None,
    footer: str = None,
    thumbnail: str = None,
    image: str = None,
    color: discord.Color = colors.prim,
) -> discord.Embed:
    embed = Embed(title=title, description=description, color=color, url=url)
    if author is not None:
        embed.set_author(name=author, icon_url=author_icon)
    if footer is not None:
        embed.set_footer(text=footer)
    if thumbnail is not None:
        embed.set_thumbnail(url=thumbnail)
    if image is not None:
        embed.set_image(url=image)
    await ctx.send(embed=embed)


def return_embed(
    title: str = None,
    description: str = None,
    url=Website,
    author: str = None,
    author_icon: str = None,
    footer: str = None,
    thumbnail: str = None,
    image: str = None,
    color: discord.Color = colors.prim,
) -> discord.Embed:
    embed = Embed(title=title, description=description, color=color, url=url)
    if author is not None:
        embed.set_author(name=author, icon_url=author_icon)
    if footer is not None:
        embed.set_footer(text=footer)
    if thumbnail is not None:
        embed.set_thumbnail(url=thumbnail)
    if image is not None:
        embed.set_image(url=image)
    return embed


async def slash_check_priv(interaction: discord.Interaction, member: discord.Member):
    """Custom (weird) way to check permissions when handling moderation commands"""

    embed = Embed(title="Permission Denied", color=0xFF0000, description="No lol.")
    embed2 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {interaction.command.name} yourself.",
    )
    embed3 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"I'm not going to let you {interaction.command.name} my owner.",
    )
    embed4 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {interaction.command.name} the owner of this server.",
    )
    embed5 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {interaction.command.name} someone who has the same permissions as you.",
    )
    embed6 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {interaction.command.name} due to the role hierarchy.",
    )
    # Self checks
    if member.id == interaction.client.user.id:
        return await interaction.followup.send(embed=embed)
    if member == interaction.user:
        return await interaction.followup.send(embed=embed2)

    # Check if user bypasses
    if interaction.user.id == interaction.guild.owner.id:
        return False

    # Now permission check
    if member.id in owners and interaction.user.id not in owners:
        return await interaction.followup.send(embed=embed3)
    if member.id == interaction.guild.owner.id:
        return await interaction.followup.send(embed=embed4)
    if interaction.user.top_role == member.top_role:
        return await interaction.followup.send(embed=embed5)
    if interaction.user.top_role < member.top_role:
        return await interaction.followup.send(embed=embed6)


async def check_priv(ctx, member, ephemeral=bool):
    """Custom (weird) way to check permissions when handling moderation commands"""

    embed = Embed(title="Permission Denied", color=0xFF0000, description="No lol.")
    embed2 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {ctx.command.name} yourself.",
    )
    embed3 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"I'm not going to let you {ctx.command.name} my owner.",
    )
    embed4 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {ctx.command.name} the owner of this server.",
    )
    embed5 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {ctx.command.name} someone who has the same permissions as you.",
    )
    embed6 = Embed(
        title="Permission Denied",
        color=0xFF0000,
        description=f"You can't {ctx.command.name} due to the role hierarchy.",
    )
    with contextlib.suppress(Exception):
        # Self checks
        if member.id == ctx.bot.user.id:
            return await ctx.send(embed=embed, ephmeral=ephemeral)
        if member == ctx.author:
            return await ctx.send(embed=embed2, ephmeral=ephemeral)

        # Check if user bypasses
        if ctx.author.id == ctx.guild.owner.id:
            return False

        # Now permission check
        if member.id in owners and ctx.author.id not in owners:
            return await ctx.send(embed=embed3, ephmeral=ephemeral)
        if member.id == ctx.guild.owner.id:
            return await ctx.send(embed=embed4, ephmeral=ephemeral)
        if ctx.author.top_role == member.top_role:
            return await ctx.send(embed=embed5, ephmeral=ephemeral)
        if ctx.author.top_role < member.top_role:
            return await ctx.send(embed=embed6, ephmeral=ephemeral)


def can_send(ctx):
    return isinstance(ctx.channel, discord.DMChannel) or ctx.channel.permissions_for(ctx.guild.me).send_messages


def can_embed(ctx):
    return isinstance(ctx.channel, discord.DMChannel) or ctx.channel.permissions_for(ctx.guild.me).embed_links


def can_upload(ctx):
    return isinstance(ctx.channel, discord.DMChannel) or ctx.channel.permissions_for(ctx.guild.me).attach_files


def can_react(ctx):
    return isinstance(ctx.channel, discord.DMChannel) or ctx.channel.permissions_for(ctx.guild.me).add_reactions


def is_nsfw(ctx):
    return isinstance(ctx.channel, discord.DMChannel) or ctx.channel.is_nsfw()


def can_handle(ctx, permission: str):
    """Checks if bot has permissions or is in DMs right now"""

    return isinstance(ctx.channel, discord.DMChannel) or getattr(ctx.channel.permissions_for(ctx.guild.me), permission)
