from __future__ import annotations

import asyncio
import contextlib
import json
import platform
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, List, Union

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from index import Website, colors, config
from Manager.emoji import Emoji
from sentry_sdk import capture_exception
from utils import default, imports, permissions
from utils.embeds import EmbedMaker as Embed

if TYPE_CHECKING:
    from index import Bot


class Creamy(commands.RoleConverter):
    async def convert(self, ctx, argument):
        return await super().convert(ctx, argument.lower())


class DiscordCmds(commands.Cog, name="discord"):
    """Server related things :D"""

    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.config = imports.get("config.json")
        self.bot.sniped_messages = {}
        self.session = aiohttp.ClientSession()
        self.bot.edit_sniped_messages = {}
        self.halloween_re = re.compile(r"h(a|4)(l|1)(l|1)(o|0)w(e|3)(e|3)n", re.I)
        self.spooky_re = re.compile(r"(s|5)(p|7)(o|0)(o|0)(k|9)(y|1)", re.I)
        self.nword_re = r"\b(n|m|и|й){1,32}(i|1|l|!|ᴉ|¡){1,32}((g|ƃ|6|б{2,32}|q){1,32}|[gqgƃ6б]{2,32})(a|e|3|з|u)(r|Я|s|5|$){1,32}\b"
        self.nword_re_comp = re.compile(self.nword_re, re.IGNORECASE | re.UNICODE)
        self.message_cooldown = commands.CooldownMapping.from_cooldown(
            1.0, 3.0, commands.BucketType.user
        )

    async def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

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

    @commands.Cog.listener(name="on_message")
    async def spooky(self, message):
        bucket = self.message_cooldown.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if datetime.now().month == 10:  # and datetime.today().day == 31:
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
            if self.halloween_re.search(message.content.lower()):
                if retry_after:
                    return
                if message.guild.id in BotList_Servers:
                    return
                with contextlib.suppress(Exception):
                    await message.add_reaction("🎃")
                    await asyncio.sleep(1)
            if self.spooky_re.search(message.content.lower()):
                if retry_after:
                    return
                if message.guild.id in BotList_Servers:
                    return
                with contextlib.suppress(Exception):
                    await message.add_reaction("👻")
                    await asyncio.sleep(1)

    @commands.hybrid_command(aliases=["s"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def snipe(self, ctx):
        """Snipe recently deleted messages to see what someone said."""
        await ctx.send(
            embed=Embed(
                title="Snipe is no more", description="Snipe is no longer available"
            )
        )

    @commands.hybrid_command(aliases=["es"])
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def editsnipe(self, ctx):
        """Snipe edited messages to see what the message said before."""
        await ctx.send(
            embed=Embed(
                title="Edit Snipe is no more",
                description="Edit Snipe is no longer available",
            )
        )

    @commands.hybrid_command()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.has_permissions(manage_roles=True)
    async def listemoji(self, ctx, ids: bool = False):
        """Lists all available emojis in a server, perfect for an emoji channel"""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        description = f"Emojis for {ctx.guild.name}"
        if not ids:
            #  `:{emoji.name}:` <- looks ugly
            text = ", ".join([f"{emoji}" for emoji in ctx.guild.emojis])

            # truncate text to 5750 characters
            if len(text) > 3900:
                text = f"{text[:3900]}..."
            embed_no_id = Embed(title=description, description=text, color=colors.prim)
            embed_no_id.set_author(
                name=f"{ctx.message.author.name}#{ctx.message.author.discriminator}",
                icon_url=ctx.message.author.avatar,
            )
            await ctx.send(embed=embed_no_id)
        else:
            #  `:{emoji.name}:` <- looks ugly
            text = "\n".join(
                [
                    f"{emoji} (`<{'a' if emoji.animated else ''}:{emoji.name}:{emoji.id}>`)"
                    for emoji in ctx.guild.emojis
                ]
            )
            if len(text) > 3900:
                text = f"{text[:3900]}..."
            embed_id = Embed(title=description, description=text, color=colors.prim)
            embed_id.set_author(
                name=f"{ctx.message.author.name}#{ctx.message.author.discriminator}",
                icon_url=ctx.message.author.avatar,
            )
            await ctx.send(embed=embed_id)
        # for page in pagify(text):
        #     await ctx.send(page)

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def avatar(
        self,
        ctx,
        *,
        user: Union[discord.User, discord.Member] = None,
        ephemeral: bool = False,
    ):
        """Get anyones avatar within Discord.
        Args:
            ephemeral (optional): make the command visible to you or others. Defaults to False.
        """
        user = user or ctx.author
        embed = Embed(
            title="User Icon", colour=colors.prim, description=f"{user}'s avatar is:"
        )
        embed.set_image(url=user.avatar)
        await ctx.send(embed=embed, ephemeral=ephemeral)

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @permissions.has_permissions(manage_roles=True)
    @commands.hybrid_command()
    @commands.bot_has_permissions(attach_files=True)
    @commands.guild_only()
    async def roles(self, ctx):
        """Get all roles in current server"""
        allroles = "".join(
            f"[{str(num).zfill(2)}] {role.id}\t{role.name}\t[ Users: {len(role.members)} ]\r\n"
            for num, role in enumerate(sorted(ctx.guild.roles, reverse=True), start=1)
        )

        data = BytesIO(allroles.encode("utf-8"))
        await ctx.send(
            content=f"Roles in **{ctx.guild.name}**",
            file=discord.File(data, filename=f"{default.timetext('Roles')}"),
        )

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def joinedat(self, ctx, *, user: discord.Member = None):
        """Check when a user joined the current server."""
        user = user or ctx.author
        embed = Embed(
            title=f"{self.bot.user.name}",
            url=Website,
            color=user.top_role.colour.value,
            description=f"**{user}** joined **`{user.joined_at:%b %d, %Y - %H:%M:%S}`**\nThat was **{discord.utils.format_dt(user.joined_at, style='R')}**!",
            thumbnail=user.avatar,
        )
        await ctx.send(
            embed=embed,
        )

    @commands.hybrid_command()
    @commands.guild_only()
    async def mods(self, ctx):
        """Check which mods are in current guild"""
        mods = []
        for member in ctx.guild.members:
            if member.bot:
                continue
            if (
                member.guild_permissions.manage_guild
                or member.guild_permissions.administrator
                or member.guild_permissions.ban_members
                or member.guild_permissions.kick_members
            ):
                mods.append(member)
        if mods:
            mod_list = "".join(
                f"[{num}] {mod.name}#{mod.discriminator} [{mod.id}]\n"
                for num, mod in enumerate(mods, start=1)
            )

            await ctx.send(f"\n{default.pycode(mod_list)}")
        else:
            await ctx.send("There are no mods online.")

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def firstmessage(self, ctx, channel: discord.TextChannel = None):
        """Provide a link to the first message in current or provided channel."""
        channel = channel or ctx.channel
        async for message in channel.history(limit=1, oldest_first=True):
            await Embed(
                description=f"[First Message in {channel.mention}]({message.jump_url})",
                author=(message.author.display_name, message.author.avatar),
            ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def channelstats(self, ctx, channel: discord.TextChannel = None):
        """Gets stats for the current channel you're in."""
        await ctx.typing()
        if channel is None:
            channel = ctx.channel
        if not ctx.guild.chunked:
            await ctx.guild.chunk()
        yes = await ctx.send("Fetching info...")
        embed = Embed(
            title=f"Stats for **{channel.name}**",
            description=f"{f'Category: {channel.category.name}' if channel.category else 'This channel is not in a category'}",
            color=colors.prim,
        )

        embed.add_field(name="Channel Guild", value=ctx.guild.name)
        embed.add_field(name="Channel Id", value=channel.id)
        embed.add_field(name="Channel Topic", value=f"{channel.topic or 'No topic.'}")
        embed.add_field(name="Channel Position", value=channel.position)
        embed.add_field(
            name="Amount of pinned messages?", value=(len(await channel.pins()))
        )
        embed.add_field(name="Channel Slowmode Delay", value=channel.slowmode_delay)
        embed.add_field(name="Channel is nsfw?", value=channel.is_nsfw())
        embed.add_field(name="Channel is news?", value=channel.is_news())
        embed.add_field(
            name="Channel Creation Time",
            value=f"{channel.created_at:%x\n%b %d (%a), %Y - %H:%M:%S}",
        )
        embed.add_field(
            name="Channel Permissions Synced", value=channel.permissions_synced
        )
        embed.add_field(name="Channel Hash", value=hash(channel))
        await yes.edit(
            content=None,
            embed=embed,
        )

    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 10, commands.BucketType.user)
    async def suggest(self, ctx, *, suggestion: str):
        """Suggest things this bot should or not have."""
        thanks = Embed(
            title=f"Thank you for contributing to the community {ctx.author.name}.",
            description="**Warning**: This command is not for spamming / abusing or for advertising. You will be blacklisted from this bot if you do so.",
            colour=colors.prim,
        )

        suggestion_channel = self.bot.get_channel(773904927579701310)
        embed = Embed(
            title=f"New suggestion by {ctx.author}.",
            description=suggestion,
            colour=colors.prim,
        )
        embed.set_footer(text=f"ID: {ctx.author.id}", icon_url=ctx.author.avatar)
        message = await suggestion_channel.send(embed=embed)
        await ctx.send(embed=thanks)
        await message.add_reaction(Emoji.yes)
        await message.add_reaction(Emoji.no)

    #     embed = Embed(
    #         title=f"New Bug Submitted By {ctx.author.name}.",
    #         description=f"```py\n{bug}```",
    #         colour=colors.prim,
    #     )
    #     embed.set_footer(
    #         text=f"User *({ctx.author.id})* in {ctx.channel.id} {ctx.message.id}",
    #         icon_url=ctx.author.avatar,
    #     )
    #     await bug_channel.send(embed=embed)
    #     await ctx.send(embed=thanks)

    # # make a command to reply to a message used by the bug command

    #     try:
    #         channel = self.bot.get_channel(channel_id)
    #     except Exception:
    #         failed1 = "Could not find the channel. "
    #     try:
    #         message = await channel.fetch_message(reported_bug_id)
    #     except Exception:
    #         failed2 = "Could not find the message. "
    #     try:
    #         await message.reply(
    #             f"**This is a reply to the bug you reported**\n\nThe bug in question: {message.content}\n\nThe reply: {reply}",
    #             allowed_mentions=discord.AllowedMentions(
    #                 users=False, roles=False, everyone=False, replied_user=True
    #             ),
    #         )
    #     except Exception:
    #         try:
    #             await message.channel.send(
    #                 f"**This is a reply to the bug you reported {ctx.author.mention}**\n\nThe bug in question: {message.content}\n\nThe reply: {reply}"
    #             )
    #         except Exception:
    #             return await ctx.send(
    #                 f"I can't reply to this message because: {failed1}{failed2}"
    #             )
    #     await ctx.send("Reply sent.")

    @permissions.dynamic_ownerbypass_cooldown(1, 10, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def colors(self, ctx):
        """Tells you all the colors this bot can make"""
        with open("colors.json", "r") as f:
            data = json.load(f)
        colors = "\n".join(data.keys())
        embed = Embed(
            title="I can give / make the following colours...",
        )
        embed.add_field(
            name="\u200b",
            value=f"""**{colors}**\nIf you feel there should be more, DM me, our devs will see what you say.
You can give yourself the colors by doing `/colorme <color>`. \nExample: `/colorme red` \nIf you want to remove a color from yourself, do `/colorme` with no arguments.

**If theres no colors at all to begin with, run `/rainbow` and follow its instructions.**""",
        )
        await ctx.send(
            embed=embed,
        )

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    @commands.hybrid_command()
    @commands.guild_only()
    async def colorme(self, ctx, *, role: Creamy = None):
        """Allows uesrs to give themselves a color

        Args:
            role (optional): The color to give yourself, if you don't specify a role, your color will be removed.
        """
        with open("colors.json", "r") as f:
            data = json.load(f)
            color_roles = [discord.utils.get(ctx.guild.roles, name=x) for x in data]
            if role is None:
                for x in color_roles:
                    if x in ctx.author.roles:
                        await ctx.author.remove_roles(x)
                await Embed(
                    description="Your color has been removed.",
                    thumbnail=None,
                    color=0x2F3136,
                ).send(ctx)
            elif role in color_roles:
                for x in color_roles:
                    if x in ctx.author.roles:
                        await ctx.author.remove_roles(x)
                        await ctx.author.add_roles(role)
                        await Embed(
                            description=f"Alright, **{role}** was given.",
                            thumbnail=None,
                            color=role.color,
                        ).send(ctx)
                        return
                # check if the role has permissions
                if role.permissions != discord.Permissions.none():
                    return await ctx.send(
                        f"**{role}** has permissions that are not given regularly when making color roles. Please run {ctx.prefix}rainbow."
                    )
                try:
                    await ctx.author.add_roles(role)
                except Exception:
                    return await Embed(
                        description=f"That color doesn't exist. Please run the `{ctx.prefix}rainbow` command to make the color roles!",
                        thumbnail=None,
                    ).send(ctx)
                await Embed(
                    description=f"Alright, **{role}** was given.",
                    thumbnail=None,
                    color=role.color,
                ).send(ctx)

    @colorme.autocomplete(name="role")
    async def colorme_autocomplete(
        self, interaction, role: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for the colorme command"""
        with open("colors.json", "r") as f:
            data = json.load(f)
            # iterate through the json file and list all the color roles
            colors = list(data)
            return [
                app_commands.Choice(name=x, value=x)
                for x in colors
                if x.startswith(role)
            ]

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def icon(self, ctx):
        """Get the current server icon"""
        if not ctx.guild.icon:
            return await Embed(
                description="This server does not have a icon...", thumbnail=None
            ).send(ctx)
        await Embed(
            title="Server Icon",
            description=f"{ctx.guild.name}'s icon is:",
            image=ctx.guild.icon,
        ).send(ctx)

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def banner(self, ctx):
        """Get the current banner image"""
        if not ctx.guild.banner:
            return await Embed(
                description="This server does not have a banner...", thumbnail=None
            ).send(ctx)
        await Embed(
            description=f"{ctx.guild.name}'s banner", image=ctx.guild.banner.url
        ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def roleinfo(self, ctx, *, role: discord.Role):
        """Get information about a role"""
        list_members_with_the_role = [
            member.mention for member in ctx.guild.members if role in member.roles
        ]
        if not list_members_with_the_role:
            list_members_with_the_role = "None"
        if len(list_members_with_the_role) > 40:
            list_members_with_the_role = "Too many members to list"
        else:
            list_members_with_the_role = ", ".join(list_members_with_the_role)
        perms = ", ".join(
            [
                f"{p.capitalize()}".replace("_", " ")
                for p, value in role.permissions
                if value is True
            ]
        )
        if "administrator" in perms:
            perms = "All of them lol"
        embed = Embed(title=f"**{role.name}**", color=role.colour)
        embed.add_field(
            name="Created",
            value=role.created_at.strftime("%d %b %Y %H:%M"),
            inline=True,
        )
        embed.add_field(name="Color", value=str(role.colour), inline=True)
        embed.add_field(name="Members", value=f"{len(role.members)}", inline=True)
        embed.add_field(name="Who all has this role", value=list_members_with_the_role)
        if int(role.permissions.value) == 0:
            embed.add_field(
                name="Permissions", value="No permissions granted.", inline=False
            )
        else:
            embed.add_field(name="Permissions", value=f"{perms}", inline=False)
        embed.add_field(name="Mentionable", value=role.mentionable, inline=True)
        embed.add_field(name="Hoist", value=role.hoist, inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Managed", value=role.managed, inline=True)
        embed.add_field(name="Mention", value=f"{role.mention}", inline=True)
        embed.add_field(
            name="Created",
            value=role.created_at.strftime("%d %b %Y %H:%M"),
            inline=True,
        )
        embed.set_footer(text=f"{role.__hash__()}")
        await ctx.send(
            embed=embed,
        )

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_command(alias=["ms"], hidden=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    async def massrole(self, ctx, *, role: discord.Role):
        """Mass give a role to all users in the server (Ignores bots)"""
        added = 0
        if role.is_default():
            await Embed(
                title="Massrole",
                description=f"Cant give a default role to users! {role.mention}",
                thumbnail=None,
            ).send(ctx)
        if role.position > ctx.author.top_role.position:
            await Embed(
                title="Massrole",
                description=f"You cant give a role that is higher than your top role! {role.mention}",
                thumbnail=None,
            ).send(ctx)
        async with ctx.channel.typing():
            msg_1 = await ctx.send("Working...")
            for member in ctx.guild.members:
                if not member.bot and role not in member.roles:
                    await member.add_roles(role)
                    added += 1
            await msg_1.delete()
            await Embed(
                title="Massrole",
                description=f"**{role.name}** role was given to {added} users in the server!",
                thumbnail=None,
            ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_command(alias=["msr"], hidden=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    async def massrole_remove(self, ctx, *, role: discord.Role):
        """Mass removes a role from everyone in the server (Doesn't ignore bots)"""
        removed = 0
        if role.is_default():
            await Embed(description="Cant remove a default role from all users!").send(
                ctx
            )
        if role.position > ctx.author.top_role.position:
            await Embed(
                description="You cant remove a role that is higher than your top role!",
            ).send(ctx)

        async with ctx.channel.typing():
            msg_1 = await ctx.send("Working...")
            for member in ctx.guild.members:
                if role in member.roles:
                    await member.remove_roles(role)
                    removed += 1
            await msg_1.delete
            await Embed(
                ctx,
                description=f"**{role.name}** role was removed from {removed} users in the server!",
            ).send(ctx)

    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    async def serverinfo(self, ctx, guild: discord.Guild = None):  # type: ignore
        """Check info about current server"""
        fetching = await ctx.send("Fetching info...")
        if guild is None:
            guild = ctx.guild
        if not guild.chunked:
            try:
                await guild.chunk()
            except discord.ClientException:
                await ctx.send(
                    "Failed to gather information on the server. Make sure I'm in the server."
                )
                return await fetching.delete()

        await asyncio.sleep(1)
        embed = Embed(
            title=f"{self.bot.user.name}",
            url=Website,
            color=ctx.author.color,
            timestamp=ctx.message.created_at,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon)
        if guild.banner:
            embed.set_image(url=guild.banner)

        embed.add_field(name="Server Name", value=f"`{guild.name}`", inline=True)
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(
            name="Bots", value=f"`{len([bot for bot in guild.members if bot.bot])}`"
        )
        if len(guild.text_channels) == 69:
            embed.add_field(
                name="Text channels",
                value=f"`{len(guild.text_channels)}` Nice",
                inline=True,
            )
        else:
            embed.add_field(
                name="Text channels",
                value=f"`{len(guild.text_channels)}`",
                inline=True,
            )
        embed.add_field(
            name="Voice channels",
            value=f"`{len(guild.voice_channels)}`",
            inline=True,
        )
        embed.add_field(
            name="Server on shard", value=f"`{guild.shard_id}`", inline=True
        )
        embed.add_field(name="Members", value=f"`{guild.member_count}`", inline=True)
        if len(guild.roles) == 69:
            embed.add_field(
                name="Roles", value=(f"`{len(guild.roles)}` Nice"), inline=True
            )
        else:
            embed.add_field(name="Roles", value=(f"`{len(guild.roles)}`"), inline=True)
        embed.add_field(name="Emoji Count", value=f"`{len(guild.emojis)}`", inline=True)
        embed.add_field(
            name="Emoji Limit", value=f"`{guild.emoji_limit}` Emojis", inline=True
        )
        embed.add_field(
            name="Filesize Limit",
            value=f"`{str(default.bytesto(guild.filesize_limit, 'm'))}` mb",
        )
        embed.add_field(
            name="Bitrate Limit",
            value=f"`{str(guild.bitrate_limit / 1000).split('.', 1)[0]}` Kbps",
        )
        embed.add_field(
            name="Security Level",
            value=f"`{guild.verification_level}`",
            inline=True,
        )
        try:
            embed.add_field(
                name="Owner/ID",
                value=f"**Name**:`{guild.owner}`\n**ID**:`{guild.owner.id}`",
                inline=False,
            )
        except Exception:
            embed.add_field(
                name="Owner/ID",
                value=f"**Name**:`Unable to fetch.`\n**ID**:`Unable to fetch.`",
                inline=False,
            )
        time_guild_existed = discord.utils.utcnow() - guild.created_at
        time_created = int(guild.created_at.timestamp())
        embed.add_field(
            name="Created",
            value=f"`{guild.created_at:%b %d, %Y - %H:%M:%S}`\nThat was `{default.commify(time_guild_existed.days)}` days ago or <t:{time_created}:R>",
            inline=True,
        )
        embed.set_footer(text=f" {ctx.author}", icon_url=ctx.author.avatar)
        await fetching.edit(
            content=None,
            embed=embed,
        )

    @commands.hybrid_command(aliases=["whois", "info", "ui"])
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    @commands.bot_has_permissions(embed_links=True)
    async def userinfo(
        self,
        ctx,
        user: Union[discord.User, discord.Member] = None,
        ephemeral: bool = False,
    ):
        """Get user info on anyone in Discord"""
        await ctx.typing(ephemeral=ephemeral)
        user = user or ctx.author
        if user.bot:
            return await ctx.send(
                "Bots don't have any *useful* information!", ephemeral=True
            )
        chunked = [guild for guild in self.bot.guilds if guild.chunked]
        db_user = await self.bot.db.fetch_blacklist(user.id)
        discord_version = discord.__version__
        python_version = platform.python_version()
        banner = await self.bot.fetch_user(user.id)
        embed = Embed()
        embed.title = f"{self.bot.user.name}"
        embed.description = f"[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate}) "
        embed.url = f"{Website}"
        embed.add_field(
            name="User",
            value=f"`{user}` | Blacklisted: `{db_user.is_blacklisted}`",
            inline=True,
        )
        with contextlib.suppress(Exception):
            embed.set_image(url=banner.banner)
        if isinstance(user, discord.Member) and user.nick is not None:
            embed.add_field(name="Nickname", value=f"`{user.nick}`", inline=True)
        # create a unix timestamp for the user's account creation
        embed.add_field(
            name="Account created",
            # show how long the user joined ago in years and round to 2 decimal places
            value=f"`{user.created_at:%x\n%b %d (%a), %Y - %H:%M:%S}`\nThat was `{(discord.utils.utcnow() - user.created_at).days}` days ago or {discord.utils.format_dt(user.created_at, style='R')}",
            inline=False,
        )
        if len(chunked) == len(self.bot.guilds):
            embed.add_field(
                name="Mutual Servers",
                value=f"`{len(user.mutual_guilds)} Servers`",
                inline=False,
            )
        elif len(user.mutual_guilds) == 1:
            embed.add_field(name="Mutual Servers", value="`1 Server`", inline=True)
        else:
            embed.add_field(
                name="Mutual Servers",
                value=f"`{len(user.mutual_guilds)} Servers`\n`(Can be innacurate, requires all servers to be cached)`",
                inline=True,
            )

        embed.set_thumbnail(url=user.avatar)
        if isinstance(user, discord.Member):
            perms = ", ".join(
                [
                    f"{p}".replace("_", " ")
                    for p, value in user.guild_permissions
                    if value is True
                ]
            )
            if "administrator" in perms:
                perms = "Administrator (All permissions)"
            embed.colour = user.color
            embed.add_field(
                name="Joined Server",
                value=f"`{user.joined_at:%b %d, %Y - %H:%M:%S}`\nThat was `{default.commify((discord.utils.utcnow() - user.joined_at).days)}` days ago or {discord.utils.format_dt(user.joined_at, style='R')}",
                inline=False,
            )

            roles = [x.name for x in user.roles if x.name != "@everyone"]
            if len(user.roles) > 20:
                roles = roles[:20]
                print(roles)
                roles.append("...")
                embed.add_field(
                    name=f"Roles[{len(roles)}]",
                    value=f"{', '.join(roles)}",
                    inline=True,
                )
            embed.add_field(name="Permissions", value=perms)
        embed.set_footer(
            text=f"mc.lunardev.group 1.19.2 | Discord.py {discord_version} | Python {python_version}"
        )
        await ctx.send(
            content=f"Basic info about **`{user.id} / {user.name}`**",
            embed=embed,
            ephemeral=ephemeral,
        )

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_group(case_insensitive=True)
    @commands.guild_only()
    async def wolfram(self, ctx):
        """Interactively calculate things with Wolfram Alpha."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))
            return

    @wolfram.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def ask(self, ctx, *, question: str):
        """Ask a general question"""
        await ctx.typing(ephemeral=True)
        api_key = config.WolframAlpha
        url = "http://api.wolframalpha.com/v2/query?"
        query = question
        payload = {"input": query, "appid": api_key}
        headers = {"user-agent": "AGB"}
        async with self.session.get(url, params=payload, headers=headers) as r:
            result = await r.text()
        root = ET.fromstring(result)
        if a := [
            pt.text.capitalize() for pt in root.findall(".//plaintext") if pt.text
        ]:
            message = "\n".join(a[:3])
            if "Current geoip location" in message:
                message = "Wolfram|Alpha did not understand your input"

        else:
            message = "Wolfram|Alpha did not understand your input"
        await Embed(description=message).send(ctx)

    @wolfram.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def image(self, ctx, *, thing: str):
        """Get an image from wolfram Alpha"""
        await ctx.typing(ephemeral=True)
        api_key = config.WolframAlpha
        if not api_key:
            await Embed(
                description="No API key set for Wolfram Alpha. Get one at http://products.wolframalpha.com/api/",
                thumbnail=None,
            ).send(ctx)
        width = 500
        font_size = 15
        layout = "divider"
        background = "193555"
        foreground = "white"
        units = "metric"
        query = " ".join(thing)
        query = urllib.parse.quote(query)
        url = f"http://api.wolframalpha.com/v1/simple?appid={api_key}&i={query}%3F&width={width}&fontsize={font_size}&layout={layout}&background={background}&foreground={foreground}&units={units}&ip=127.0.0.1"

        async with self.session.request("GET", url) as r:
            img = await r.content.read()
            if len(img) == 43:
                await Embed(
                    description="Wolfram|Alpha did not understand your input",
                    thumbnail=None,
                ).send(ctx)
            wolfram_img = BytesIO(img)
            try:
                await ctx.send(
                    file=discord.File(wolfram_img, f"wolfram{ctx.author.id}.gif")
                )
            except Exception as e:
                capture_exception(e)
                await Embed(description=f"Oops, there was a problem: {e}").send(ctx)

    @wolfram.command()
    @permissions.dynamic_ownerbypass_cooldown(1, 3, commands.BucketType.user)
    async def solve(self, ctx, *, mathquestion: str):
        """Solve any math problem"""
        await ctx.typing(ephemeral=True)
        api_key = config.WolframAlpha
        url = "http://api.wolframalpha.com/v2/query"
        params = {
            "appid": api_key,
            "input": mathquestion,
            "podstate": "Step-by-step solution",
            "format": "plaintext",
        }
        msg = ""
        async with self.session.request("GET", url, params=params) as r:
            text = await r.content.read()
            root = ET.fromstring(text)
            for pod in root.findall(".//pod"):
                if pod.attrib["title"] == "Number line":
                    continue
                msg += f"{pod.attrib['title']}\n"
                for pt in pod.findall(".//plaintext"):
                    if pt.text:
                        strip = pt.text.replace(" | ", " ").replace("| ", " ")
                        msg += f"- {strip}\n\n"
            if len(msg) < 1:
                msg = "Wolfram|Alpha did not understand your input"
            for text in default.pagify(msg):
                await Embed(description=text).send(ctx)

    # LD Media Only Channel

    @commands.Cog.listener(name="on_message")
    async def onlymedia(self, message):
        if message.channel.id in [986082876640591952] and not message.attachments:
            await message.delete()


async def setup(bot: Bot) -> None:
    await bot.add_cog(DiscordCmds(bot))
