from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime
import json
import os
import random
import re
from collections import Counter
from typing import TYPE_CHECKING, Any, List, Optional, Union

import discord
from discord.app_commands import Choice, Transform, Transformer
from discord.ext import commands
from index import Website, colors, config, delay
from sentry_sdk import capture_exception
from utils import checks, default, imports, permissions
from utils.embeds import EmbedMaker as Embed
from utils.errors import DisabledCommand

if TYPE_CHECKING:
    from index import AGB


def can_execute_action(ctx, user, target):
    return user.id == ctx.bot.owner_id or user == ctx.guild.owner or user.top_role > target.top_role


class MemberNotFound(Exception):
    pass


# edited from RoboDanny (i had a plan to use this but i just don't remember
# for what)


class ToggleCommandArgument(Transformer):
    async def get_command(
        self,
        ctx_interaction: Union[discord.Interaction, commands.Context[AGB]],
        name: str,
    ) -> Optional[commands.Command[None, ..., Any]]:
        bot: AGB = (
            ctx_interaction.client if isinstance(ctx_interaction, discord.Interaction) else ctx_interaction.bot
        )  # type: ignore
        return bot.get_command(name)

    # called when command is invoked via a prefix
    convert = get_command
    # called when invoked via slash
    transform = get_command

    async def autocomplete(self, interaction: discord.Interaction, current: str, /) -> List[Choice[str]]:
        bot: AGB = interaction.client  # type: ignore
        all_choices = [
            Choice(name=command.qualified_name, value=command.qualified_name) for command in bot.walk_commands()
        ]
        startswith_choices = [c for c in all_choices if c.name.startswith(current)]
        return ((startswith_choices or all_choices) if current else all_choices)[:25]


class Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeError(message)


# URL_REG = re.compile(r'https?://(?:www\.)?.+')


async def resolve_member(guild, member_id):
    member = guild.get_member(member_id)
    if member is None:
        if guild.chunked:
            raise MemberNotFound()
        try:
            member = await guild.fetch_member(member_id)
        except discord.NotFound:
            raise MemberNotFound() from None
    return member


# Edited from robo danny


class MemberID(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            m = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                member_id = int(argument, base=10)
                m = await resolve_member(ctx.guild, member_id)
            except ValueError:
                raise commands.BadArgument(f"{argument} is not a valid member or member ID.") from None
            except MemberNotFound:
                # hackban case
                return type(
                    "_Hackban",
                    (),
                    {"id": member_id, "__str__": lambda s: f"Member ID {s.id}"},
                )()

        if not can_execute_action(ctx, ctx.author, m):
            raise commands.BadArgument("You cannot do this action on this user due to role hierarchy.")
        return m


# class taken from robo danny. Hackbanning is really nice


class BannedMember(commands.Converter):
    async def convert(self, ctx, argument):
        if argument.isdigit():
            member_id = int(argument, base=10)
            try:
                return await ctx.guild.fetch_ban(discord.Object(id=member_id))
            except discord.NotFound:
                raise commands.BadArgument("This member has not been banned before.") from None

        ban_list = await ctx.guild.bans()
        entity = discord.utils.find(lambda u: str(u.user) == argument, ban_list)

        if entity is None:
            raise commands.BadArgument("This member has not been banned before.")
        return entity


# edited from robo danny


class MemberConverter(commands.MemberConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except commands.BadArgument as e:
            members = [
                member for member in ctx.guild.members if member.display_name.lower().startswith(argument.lower())
            ]
            if len(members) == 1:
                return members[0]
            else:
                raise commands.BadArgument(f"{len(members)} members found, please be more specific.") from e


class ActionReason(commands.Converter):
    async def convert(self, ctx, argument):
        ret = f"{ctx.author} (ID: {ctx.author.id}): {argument}"

        if len(ret) > 512:
            reason_max = 512 - len(ret) + len(argument)
            raise commands.BadArgument(f"Reason is too long ({len(argument)}/{reason_max})")
        return ret


def safe_reason_append(base, to_append):
    appended = f"{base}({to_append})"
    return base if len(appended) > 512 else appended


# i also had a plan to use this but i don't remember for what


class CooldownByContent(commands.CooldownMapping):
    def _bucket_key(self, message):
        return (message.channel.id, message.content)


class NoMuteRole(commands.CommandError):
    def __init__(self):
        super().__init__("This server does not have a mute role set up.")


def can_mute():
    async def predicate(ctx):
        is_owner = await ctx.bot.is_owner(ctx.author)
        if ctx.guild is None:
            return False

        if not ctx.author.guild_permissions.manage_roles and not is_owner:
            return False

        # This will only be used within this cog.
        ctx.guild_config = config = await ctx.cog.get_guild_config(ctx.guild.id)
        role = config and config.mute_role
        if role is None:
            raise NoMuteRole()
        return ctx.author.top_role > role

    return commands.check(predicate)


class Moderator(commands.Cog, name="mod"):
    """Commands for moderators to keep your server safe"""

    def __init__(self, bot: AGB):
        self.bot: AGB = bot
        self.last_messages = {}
        self.config = imports.get("config.json")
        blist = []
        self.blacklist = blist

    async def create_embed(self, ctx, error):
        embed = Embed(title="Error Caught!", color=0xFF0000, description=f"{error}")

        embed.set_thumbnail(url=self.bot.user.avatar)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        db_user = await self.bot.db.getch("users", message.author.id)
        guild = self.bot.get_guild(975810661709922334)
        if message.guild is None:
            if db_user and not db_user.message_tracking:
                return
            if message.author == self.bot.user:
                return
            if message.author.id in self.blacklist:
                return
            # if message.author.id in self.config.owners:
            #     return
            if message.author.id != self.bot.user:
                if message.content.startswith("/"):
                    return
                embed = Embed(colour=colors.prim)
                embed.add_field(
                    name=f"DM - From {message.author} ({message.author.id})",
                    value=f"{message.content}",
                )
                embed.set_footer(
                    text=f"/owner dm {message.author.id} ",
                    icon_url=message.author.avatar,
                )
                channel = self.bot.get_channel(986079167944749057)
                if message.author.bot:
                    return
                files = []
                for attachment in message.attachments:
                    files.append(await attachment.to_file())
                if files:
                    await channel.send(
                        content=f"File - from {message.author} ({message.author.id})",
                        files=files,
                    )
                with contextlib.suppress(Exception):
                    await channel.send(
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(roles=True),
                    )

    # TODO: fix
    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @permissions.has_permissions(manage_guild=True)
    async def toggle(
        self,
        ctx: commands.Context,
        *,
        command: Transform[Optional[commands.Command], ToggleCommandArgument],
    ):
        """Toggle commands in your server to be enabled/disabled"""
        if command is None:
            await ctx.send("I can't find a command with that name!", ephemeral=True)
            return

        assert ctx.command is not None, "ctx.command is None?!"
        if not ctx.guild:
            raise AssertionError("ctx.guild is None?!")

        if command.name in (ctx.command.name, "help"):
            await ctx.send("You cannot disable this command.", ephemeral=True)
            return

        await ctx.typing()
        try:
            await command.can_run(ctx)
        except Exception as e:
            if not isinstance(e, DisabledCommand):
                await ctx.send(f"command: {ctx.command}\n\ncommand: {command}\n\nexception: {e}")
                return

        db_command_guild = self.bot.db.get_command(ctx.guild.id) or await self.bot.db.fetch_command_guild(ctx.guild.id)
        if not db_command_guild:
            db_command_guild = await self.bot.db.add_command_guild(ctx.guild.id)

        command_state: bool = db_command_guild.is_disabled(command.name)

        ternary = "enabled" if command_state else "disabled"
        await db_command_guild.edit(command.name, not command_state)

        embed = Embed(
            title="Command Toggled",
            colour=discord.Colour.green(),
            timestamp=ctx.message.created_at,
        )
        embed.add_field(name="Success", value=f"The `{command}` command has been **{ternary}**")
        embed.set_thumbnail(url=None)
        embed.set_author(name=ctx.message.author.name, icon_url=ctx.message.author.avatar)
        await ctx.send(embed=embed)

    # @commands.hybrid_command()

    #     no_prefix = Embed(title="Please put a prefix you want.", colour=colors.prim)

    #             await db_guild.modify(prefix=new)
    #         except discord.errors.Forbidden:
    #             await ctx.send(
    #                 "I couldn't update my nickname, the prefix has changed though."
    #             )

    # @commands.hybrid_command(usage="`/slashremove yes/no`")

    # @commands.hybrid_command(usage="`/slashsetup yes/no`")

    #             payload2 = {

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload2)
    #             payload3 = {
    #                 "name": "blow",
    #                 "type": 1,
    #                 "description": "blow job"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload3)
    #             payload4 = {
    #                 "name": "pwg",
    #                 "type": 1,
    #                 "description": "pussy wank gif"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload4)
    #             payload5 = {
    #                 "name": "kemo",
    #                 "type": 1,
    #                 "description": "lewd kemo"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload5)
    #             payload6 = {
    #                 "name": "holo",
    #                 "type": 1,
    #                 "description": "Lewd Holo live avatars"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload6)
    #             payload7 = {
    #                 "name": "feet",
    #                 "type": 1,
    #                 "description": "Feet."}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload7)
    #             payload8 = {
    #                 "name": "anal",
    #                 "type": 1,
    #                 "description": "Anal"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload8)
    #             payload9 = {
    #                 "name": "wallpaper",
    #                 "type": 1,
    #                 "description": "Nsfw wallpaper"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload9)
    #             payload10 = {
    #                 "name": "tits",
    #                 "type": 1,
    #                 "description": "Titties"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload10)
    #             payload11 = {
    #                 "name": "lesbian",
    #                 "type": 1,
    #                 "description": "Lesbian"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload11)
    #             payload12 = {
    #                 "name": "neko",
    #                 "type": 1,
    #                 "description": "Neko"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload12)
    #             payload13 = {
    #                 "name": "hentai",
    #                 "type": 1,
    #                 "description": "Hentai"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload13)
    #             payload14 = {
    #                 "name": "pussy",
    #                 "type": 1,
    #                 "description": "Pussy"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload14)
    #             payload15 = {
    #                 "name": "trap",
    #                 "type": 1,
    #                 "description": "Trap"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload15)
    #             payload16 = {
    #                 "name": "slashclassic",
    #                 "type": 1,
    #                 "description": "Classic hentai"}

    #             await self.bot.http.upsert_global_command(
    #                 self.bot.user.id, payload16)
    #         except Exception:
    #             pass

    #     await wait.edit(
    #         content=f"Registered the following slash commands:\n{payload1['name']}, {payload2['name']}, {payload3['name']}, {payload4['name']}, {payload5['name']}, {payload6['name']}, {payload7['name']}, {payload8['name']}, {payload9['name']}, {payload10['name']}, {payload11['name']}, {payload12['name']}, {payload13['name']}, {payload14['name']}, {payload15['name']}, {payload16['name']}"
    #     )

    # @slashsetup.error

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    async def addrole(self, ctx, user: discord.Member, *, role: discord.Role):
        """Adds a role to a user"""
        try:
            await user.add_roles(role)
        except Exception:
            await ctx.send("I couldn't add that role to that user.")
            return
        await ctx.send(
            f"Aight, gave {role.name} to {user.mention}",
            allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False),
        )

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    async def removerole(self, ctx, user: discord.Member, *, role: discord.Role):
        """Removes a role from a user"""

        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await user.remove_roles(role)
        await ctx.send(
            f"Aight, removed {role.name} from {user.mention}",
            allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False),
        )

    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    @commands.hybrid_command()
    async def deleterole(self, ctx, *, role: str):
        """Delete a role from the server."""

        role = discord.utils.get(ctx.guild.roles, name=role)
        if role is None:
            await ctx.send(f"**{role}** does not exist!")
        else:
            await role.delete()
            await ctx.send(f"**{role}** deleted!")

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.guild_only()
    async def perms(self, ctx):
        """Tells you what permissions the bot has."""

        perms = ", ".join([f"{p}".replace("_", " ") for p, value in ctx.guild.me.guild_permissions if value is True])
        if "administrator" in perms:
            perms = "Administrator (All permissions)"

        embed = Embed(
            title=f"{self.bot.user.name} has the following permissions:",
            description=f"[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate})\n**{perms}**",
            url=Website,
            color=ctx.author.color,
            timestamp=ctx.message.created_at,
        )
        await ctx.send(embed=embed)

    @permissions.dynamic_ownerbypass_cooldown(1, 500, commands.BucketType.guild)
    @permissions.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    @commands.hybrid_command()
    @commands.guild_only()
    async def rainbow(self, ctx):
        """Creates a bunch of color roles for your server."""

        def check(m):
            return m.author.id == ctx.author.id

        with open("colors.json", "r") as f:
            data = json.load(f)
            message = await ctx.send(
                "***READ THIS BEFORE YOU DO ANYTHING!!!***\nTo STOP making roles send `cancel`! If you say anything before this prompt changes the process will also stop. If you for some reason want to remove the color roles after I get done, please run `/removerainbow`."
            )
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=20)
            if msg.content == "cancel":
                return await message.edit(content="Okay, cancled.")
        except asyncio.TimeoutError:
            await message.edit(content="Okay, 20 seconds has passed. Time to make roles!")
            await asyncio.sleep(3)
            for role in ctx.guild.roles:
                if role.name == "red":
                    return await message.edit(
                        content="Seems as though the color roles have already been made in this server, or there are already color roles present. Please remove those roles. \nSpecifically, I saw that there was a role named `red` in this server, therefor I cannot tell if thats a color role or some other type of role, please either rename it or remove it."
                    )
            for color, hexcode in data.items():
                await ctx.guild.create_role(
                    name=color,
                    colour=discord.Colour(int(hexcode, 0)),
                    permissions=discord.Permissions.none(),
                )
                await message.edit(content=f"Created {color}.")
                await asyncio.sleep(0.5)
            await message.edit(
                content="Alright, I've made all the colors, have fun.\nTo give yourself a color role, run `/colorme` and follow its instructions."
            )

    @permissions.dynamic_ownerbypass_cooldown(1, 500, commands.BucketType.guild)
    @permissions.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    @commands.hybrid_command()
    @commands.guild_only()
    async def removerainbow(self, ctx):
        """Remove all the rainbow roles in your server so you don't have to do it manually."""

        def check(m):
            return m.author.id == ctx.author.id and ctx.message.content

        with open("colors.json", "r") as f:
            data = json.load(f)
        async with ctx.channel.typing():
            m = await ctx.send(
                "Alright, I'm about to delete all the color roles. You have 10 seconds to send `cancel` to stop me."
            )
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=10)
                if msg.content == "cancel":
                    return await m.edit(content="Okay, cancled.")
            except asyncio.TimeoutError:
                await m.edit(content="Alright, 10 seconds has passed, time to start deleting roles!")
                await asyncio.sleep(3)
                await m.edit(content="Alright, deleting roles...")
                await asyncio.sleep(0.5)
                try:
                    for color, hexcode in data.items():
                        role: Optional[discord.Role] = discord.utils.get(ctx.guild.roles, name=color)  # type: ignore
                        if not role:
                            # just to be sure
                            continue

                        if role.permissions != discord.Permissions.none():
                            return await m.edit(
                                content=(
                                    "The roles I was about to delete have permissions that are not typically given when color roles are made. "
                                    "Please verify that these roles are color roles that *I* have made and remove the permissions from them."
                                )
                            )
                        reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"
                        await role.delete(reason=reason)
                        await m.edit(content=f"Deleted {color}.")
                        await asyncio.sleep(1.1)

                    await m.edit(content="Alright, all rainbow roles have been deleted.")
                except Exception as e:
                    return await m.edit(
                        content=f"I was unable to delete color roles, did you add them?\nDirect Error: {e}"
                    )

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.has_permissions(administrator=True)
    async def fuckoff(self, ctx):
        """Makes the bot fuck off. (leave the server)"""
        await ctx.send("Aight <a:LD_PeaceOut:1017017390086770748>")
        await ctx.guild.leave()

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(embed_links=True, manage_nicknames=True)
    async def nickname(self, ctx, member: discord.Member, *, name: str = None):
        """Nicknames a user from the current server."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()

        try:
            await member.edit(nick=name, reason=default.responsible(ctx.author, "Changed by command"))
            message = f"Changed **{member.name}'s** nickname to **{name}**"
            if name is None:
                message = f"Reset **{member.name}'s** nickname"
            await ctx.send(message)
        except Exception as e:
            capture_exception(e)
            await ctx.send("I don't have the permission to change that user's nickname.")

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    @commands.guild_only()
    @commands.hybrid_command()
    async def toggleslow(self, ctx, time: str, reason=None):
        """Slow the chat."""
        # with contextlib.suppress(Exception):
        #     await ctx.message.delete()
        valid_time_units = ("s", "m", "h")
        if not time.endswith(valid_time_units):
            await ctx.send("Invalid time unit! Please use s, m, or h.", ephemeral=True)
            return
        if reason is None:
            reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        if time.endswith("s"):
            time = int(time[:-1])
        elif time.endswith("m"):
            time = int(time[:-1]) * 60
        elif time.endswith("h"):
            time = int(time[:-1]) * 3600
        else:
            time = int(time)
        if time < 0 or time > 21600:
            await Embed(
                description="Invalid time specified! Time must be between 0 and 21600 (inclusive)",
                thumbnail=None,
            ).send(ctx, ephemeral=True)
            return
        try:
            await ctx.channel.edit(slowmode_delay=datetime.timedelta(seconds=time))
        except discord.errors.Forbidden:
            await ctx.send("I don't have manage channel permissions.")
            return
        if time > 0:
            await ctx.send(
                (f"{ctx.channel.mention} is now in slow mode. You may send 1 message " f"every {time} seconds")
            )
        else:
            await ctx.send((f"Slow mode has been disabled for {ctx.channel.mention}"))

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(rate=1, per=10, type=commands.BucketType.user)
    @commands.guild_only()
    @permissions.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(embed_links=True, manage_nicknames=True)
    async def hoist(self, ctx):
        """Changes users names that are hoisting themselves (Ignores Bots)"""
        await ctx.typing()
        chars = [
            "!",
            ".",
            "-",
            "_",
            "*",
            "(",
            ")",
            "=",
            "+",
            "^",
            "&",
            "~",
            "#",
            "$",
            ":",
            ";",
            "?",
            "<",
            ">",
            "{",
            "}",
            "[",
            "]",
            "|",
        ]
        temp = {}
        failed = 0

        initial = await ctx.send("Kk, changing peoples names. This'll take some time so please be patient!")
        for member in ctx.guild.members:
            if not member.bot:
                for char in chars:
                    if member.display_name.startswith(char):
                        try:
                            await member.edit(nick="No Hoisting")
                            await asyncio.sleep(random.randint(1, 5))
                        except discord.HTTPException:
                            failed += 1
                        temp[char] = temp.get(char, 0) + 1
                    if member.display_name[0].isdigit():
                        try:
                            await member.edit(nick="No Hoisting")
                            await asyncio.sleep(random.randint(1, 5))
                            temp["numbers"] = temp.get("numbers", 0) + 1
                        except Exception as e:
                            failed += 1
        if not (stats := "\n".join([f"`{char}` - `{amount}`" for char, amount in temp.items()])):
            stats = "Nothing"
        await initial.edit(
            content=f"I have unhoisted `{sum(temp.values())}` nicks and failed to edit `{failed}` nicks.\nHere are some stats:\n\n{stats}"
        )

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(rate=1, per=10, type=commands.BucketType.user)
    @commands.guild_only()
    @permissions.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(embed_links=True, manage_nicknames=True)
    async def reset_names(self, ctx):
        """Tries to reset all members nicknames in the current server (Ignores bots)"""
        inital = await ctx.send("Reseting all nicknames. This'll take some time so please be patient!")
        count = 0
        for member in ctx.guild.members:
            if member.nick is None:
                continue
            if not member.bot:
                try:
                    await member.edit(nick=None)
                    await asyncio.sleep(random.randint(1, 5))
                    count += 1
                except Exception as e:
                    capture_exception(e)
        await inital.edit(content=f"{count} nicknames have been reset.")

    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def bans(self, ctx):
        """Shows the servers bans with the ban reason"""

        filename = f"{ctx.guild.id}"
        with open(f"{str(filename)}.txt", "a", encoding="utf-8") as f:
            async for entry in ctx.guild.bans():
                data = f"{entry.user.id}: {entry.reason}"
                f.write(data + "\n")
                continue
        try:
            await ctx.send(
                content="Sorry if this took a while to send, but here is all of this servers bans!",
                file=discord.File(f"{str(filename)}.txt"),
            )
        except Exception as e:
            capture_exception(e)
            await ctx.send("I couldn't send the file of this servers bans for whatever reason")
        os.remove(f"{filename}.txt")

    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    @permissions.dynamic_ownerbypass_cooldown(rate=1, per=3, type=commands.BucketType.user)
    async def banreason(self, ctx, user: discord.User):
        """Shows the ban reason for a user in the current server"""
        # itterate through the bans and find the one that matches the user
        async for entry in ctx.guild.bans():
            if entry.user.id == user.id:
                await ctx.send(f"{user.mention} has been banned for: `{entry.reason}`")
                return
        else:
            await ctx.send(f"{user.mention} is not banned in this server.")

    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.bot_has_permissions(embed_links=True)
    async def fban(self, ctx, member: discord.Member, *, reason: ActionReason = None):
        """*totally* Bans a member from the server."""

        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if reason is None:
            reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        ban_msg = await ctx.send(f"<:LD_banHammer:875376602651959357> {ctx.author.mention} banned {member}")
        with contextlib.suppress(Exception):
            await member.send(f"You were *totally* banned in **{ctx.guild.name}**(not really)\n**{reason}**.")
        await ban_msg.edit(
            content=None,
            embed=Embed(
                color=colors.prim,
                description=f"<a:LD_Banned1:872972866092662794><a:LD_Banned2:872972848354983947><a:LD_Banned3:872972787877314601> **{member}** has been banned: reason {reason}",
            ),
        )

    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @permissions.has_permissions(ban_members=True)
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def sban(
        self,
        ctx,
        member: MemberID,
        *,
        reason: ActionReason = None,
        ephemeral: bool = False,
    ):
        """Silently bans a member from the server, the user will not get a dm."""

        with contextlib.suppress(Exception):
            await ctx.message.delete()
        # check if the command was used as a slash command
        if ctx.interaction is None:
            if await permissions.check_priv(ctx, member):
                return
        elif await permissions.check_priv(ctx, member, ephemeral=True):
            return
        if reason is None:
            reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        ban_msg = await ctx.author.send(f"<:LD_banHammer:875376602651959357> {ctx.author.mention} banned {member}")
        try:
            await ctx.guild.ban(member, reason=reason)
        except Exception as e:
            capture_exception(e)
            await ban_msg.edit(content=f"Couldn't ban {member}, Error\n{e}")
            return
        await ban_msg.edit(content="Done.")

    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @permissions.has_permissions(ban_members=True)
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def massban(self, ctx, members: commands.Greedy[MemberID], *, reason: ActionReason = None):
        """Ban multiple members at once."""

        banned_members = 0
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if not members:
            if len(members) >= 1:
                return await ctx.send("Please either put a user mention or multiple user ID's to ban!")
            await ctx.send("this command can only be used on multiple people\neg: `/ban userID\nuserID2\nuserID3`")
            return
        m = await ctx.send("Working...")
        async with ctx.channel.typing():
            if len(members) > 1:
                for member in members:
                    if await permissions.check_priv(ctx, member):
                        return
                    with contextlib.suppress(Exception):
                        if reason is None:
                            reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"
                    await ctx.guild.ban(member, reason=reason)
                    banned_members += 1
                await m.edit(content=f"I successfully banned {banned_members} people!")
            else:
                await m.edit(content=default.actionmessage("banned"))

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def unban(self, ctx, member: BannedMember, *, reason: ActionReason = None):
        """Unbans a member from the server.
        You can pass either the ID of the banned member or the Name#Discrim
        combination of the member. Typically the ID is easiest to use.
        """
        if await permissions.check_priv(ctx, member):
            return

        if reason is None:
            reason = f"reason: {ctx.author} (ID: {ctx.author.id})"

        await ctx.guild.unban(member.user, reason=reason)
        if member.reason:
            await ctx.send(f"Unbanned {member.user}\n(ID: {member.user.id}) {member.reason}.")
        else:
            await ctx.send(f"Unbanned {member.user} (ID: {member.user.id}).")

    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    @commands.hybrid_command()
    async def unbanall(self, ctx, *, reason: ActionReason = None):
        """Unbans everyone from the server.
        You can pass an optional reason to be shown in the audit log.
        You must have Ban Members permissions.
        """
        unbanned = 0
        if reason is None:
            reason = f"reason: {ctx.author} (ID: {ctx.author.id})"
        async for member in ctx.guild.bans():
            await ctx.guild.unban(member.user, reason=reason)
            unbanned += 1
        await ctx.send(f"Unbanned {unbanned} users.")

    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @permissions.has_permissions(kick_members=True, ban_members=True)
    @commands.bot_has_permissions(embed_links=True, kick_members=True, ban_members=True)
    async def softban(self, ctx, member: MemberID, *, reason: ActionReason = None):
        """Soft bans a member from the server.
        To use this command you must have Kick and Ban Members permissions.
        """
        if await permissions.check_priv(ctx, member):
            return

        if reason is None:
            reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"

        await ctx.guild.ban(member, reason=reason)
        await ctx.guild.unban(member, reason=reason)
        await ctx.send(f"Alright, softbanned em, reason: {reason}")

    @commands.hybrid_command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @permissions.has_permissions(manage_emojis=True, manage_guild=True)
    @commands.bot_has_permissions(embed_links=True, manage_emojis=True)
    async def stealemoji(self, ctx, emote: discord.PartialEmoji):
        """Clones any emote to the current server"""
        await ctx.guild.create_custom_emoji(
            name=emote.name,
            image=await emote.read(),
            reason=f"{ctx.author} used steal_emote",
        )
        await ctx.send(f"I successfully cloned {emote.name} to {ctx.guild.name}!")

    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_group(case_insensitive=True)
    @commands.guild_only()
    async def find(self, ctx):
        """Finds a user within your search term"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))
            return
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @find.command(name="username", aliases=["name"])
    async def find_name(self, ctx, *, search: str):
        """Find a user by their name

        Args:
            search (str): The name of the user you are searching for
        """
        loop = [f"{i} ({i.id})" for i in ctx.guild.members if search.lower() in i.name.lower() and not i.bot]
        await default.prettyResults(ctx, "name", f"Found **{len(loop)}** on your search for **{search}**", loop)

    @find.command(name="nickname", aliases=["nick"])
    async def find_nickname(self, ctx, *, search: str):
        """Find a user by their nickname

        Args:
            search (str): The nickname to search for
        """
        loop = [
            f"{i.nick} | {i} ({i.id})"
            for i in ctx.guild.members
            if i.nick
            if (search.lower() in i.nick.lower()) and not i.bot
        ]
        await default.prettyResults(ctx, "name", f"Found **{len(loop)}** on your search for **{search}**", loop)

    @find.command(name="id")
    async def find_id(self, ctx, *, search: int):
        """Find a user by their ID

        Args:
            search (int): The ID of the user you are searching for
        """
        loop = [f"{i} | {i} ({i.id})" for i in ctx.guild.members if (str(search) in str(i.id)) and not i.bot]
        await default.prettyResults(ctx, "name", f"Found **{len(loop)}** on your search for **{search}**", loop)

    @find.command(name="discrim")
    async def find_discrim(self, ctx, *, search: str):
        """Find a user by their discriminator

        Args:
            search (str): The discriminator to search for
        """
        loop = [f"{i} | {i} ({i.id})" for i in ctx.guild.members if (search.lower() in i.discriminator) and not i.bot]
        await default.prettyResults(ctx, "name", f"Found **{len(loop)}** on your search for **{search}**", loop)

    @commands.guild_only()
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True, manage_channels=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_group()
    async def channel(self, ctx):
        """Group command for channel related things"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))
            return

    @channel.command(name="create")
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def create(self, ctx, channel: str):
        """Create a channel

        Args:
            channel (str): channel name
        """
        if channel in [i.name for i in ctx.guild.channels]:
            return await ctx.send(f"{channel} already exists!", ephemeral=True)
        # check if the channel name is below 100 characters
        if len(channel) > 100:
            return await ctx.send(
                "Channel name is too long! Please make it under 100 characters.",
                ephemeral=True,
            )
        bruh = await ctx.guild.create_text_channel(channel)
        await ctx.send(f"{bruh.mention} has been created!", ephemeral=True)

    @channel.command(name="delete")
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def delete(self, ctx, channel: Union[discord.TextChannel, discord.VoiceChannel]):
        """Delete a channel

        Args:
            channel: the channel to delete
        """
        fetch_channel = await self.bot.fetch_channel(channel.id)
        try:
            await fetch_channel.delete()
            await ctx.send("Channel deleted!", ephemeral=True)
        except Exception:
            try:
                await ctx.send(
                    "I was unable to perform this action! Please check my permissions.",
                    ephemeral=True,
                )
            except Exception:
                pass

    @channel.command()
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def rename(
        self,
        ctx,
        channel: Union[discord.TextChannel, discord.VoiceChannel],
        new_name: str,
    ):
        """Rename a channel

        Args:
            channel (str): the channel to rename
            new_name (str): the new name for the channel
        """
        if channel.name not in [i.name for i in ctx.guild.channels]:
            return await ctx.send(f"{channel.name} doesn't exist!", ephemeral=True)
        if len(new_name) > 100:
            return await ctx.send("Channel name is too long!", ephemeral=True)
        await channel.edit(name=new_name)
        await ctx.send(f"{channel.name} has been renamed to: `{new_name}`!", ephemeral=True)

    @channel.group()
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def edit(self, ctx):
        """Edit a channel

        Args:
            channel (discord.TextChannel): the channel to edit
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))
            return

    @edit.command(name="userlimit")
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def userlimit(self, ctx, channel: discord.VoiceChannel, limit: str):
        """Set the user limit of a voice channel

        Args:
            channel (discord.VoiceChannel): the channel to edit
            limit (int/str): the new user limit
        """
        if limit.isdigit():
            if int(limit) > 99:
                return await ctx.send("User limit cannot be over 99!", ephemeral=True)
            if channel.user_limit == limit:
                return await ctx.send("User limit is already set to that!", ephemeral=True)
            try:
                await channel.edit(user_limit=limit)
                await ctx.send(f"User limit has been set to: `{limit}`!", ephemeral=True)
            except Exception as e:
                await ctx.send(
                    f"I was unable to perform this action! Please check my permissions and look at the error below!\n{default.pycode(e)}",
                    ephemeral=True,
                )

        else:
            no_user_limit = ["0", "none", "no", "n", "off", "false"]
            if limit in no_user_limit:
                try:
                    await channel.edit(user_limit=None)
                    await ctx.send("User limit has been set to: `None`!", ephemeral=True)
                except Exception as e:
                    return await ctx.send(
                        f"I was unable to perform this action! Please check my permissions and look at the error below!\n{default.pycode(e)}",
                        ephemeral=True,
                    )

    @edit.command()
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def topic(self, ctx, channel: discord.TextChannel, *, topic: str):
        """edit the topic of a channel

        Args:
            channel (discord.TextChannel): the channel to edit
            topic (str): the new topic for the channel
        """
        if channel.name not in [i.name for i in ctx.guild.channels]:
            return await ctx.send(f"{channel.name} doesn't exist!", ephemeral=True)
        if len(topic) > 1024:
            return await ctx.send("Topic is too long!")
        await channel.edit(topic=topic)
        await ctx.send(f"{channel.name}'s topic has been changed to: `{topic}`!", ephemeral=True)

    @edit.command()
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def description(self, ctx, channel: discord.TextChannel, *, description: str):
        """edit the description of a channel

        Args:
            channel (discord.TextChannel): the channel to edit
            description (str): the new description for the channel

        """
        if channel.name not in [i.name for i in ctx.guild.channels]:
            return await ctx.send(f"{channel.name} doesn't exist!", ephemeral=True)
        if len(description) > 1024:
            return await ctx.send("Description is too long!", ephemeral=True)
        await channel.edit(description=description)
        await ctx.send(
            f"{channel.name}'s description has been changed to: `{description}`!",
            ephemeral=True,
        )

    @edit.command()
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_channels=True)
    async def nsfw(self, ctx, channel: Union[discord.TextChannel, discord.VoiceChannel], nsfw: bool):
        """Make a channel NSFW or not

        Args:
            ctx (_type_): _description_
            channel (discord.TextChannel): the channel to edit
            nsfw (bool): set the channel to be NSFW or not. True/False
        """
        if channel is None:
            return await ctx.send("Specify a channel!", ephemeral=True)
        if channel.name not in [i.name for i in ctx.guild.channels]:
            return await ctx.send(f"{channel.name} doesn't exist!", ephemeral=True)
        await channel.edit(nsfw=nsfw)
        await ctx.send(
            f"{channel.name}'s NSFW status has been changed to: `{nsfw}`!",
            ephemeral=True,
        )

    # !!!!Dont uncomment!!!
    # !!!!!
    # This is not only blacklisted users, this is every user in the blacklist table. This will be fixed soon
    #
    #
    # @commands.guild_only()
    # @permissions.has_permissions(ban_members=True)
    # @commands.bot_has_permissions(embed_links=True, ban_members=True)
    # @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    # async def banblacklistedusers(self, ctx):
    #     """Ban all blacklisted users from the server"""
    #     user = self.bot.db.fetch_blacklists()

    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.hybrid_group()
    async def role(self, ctx):
        """A group command for role related commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))
            return

    @role.command(name="make")
    @permissions.has_permissions(manage_roles=True)
    async def make(
        self,
        ctx,
        name: str,
        permissions: str or int = None,
        hoist: bool = False,
        mentionable: bool = False,
        hex: str = None,
    ):
        # sourcery skip: avoid-builtin-shadow
        """Creates a role with any name, permissions, hoistable, mentionable, and color
        Example: `/role create bruh 8 True True ff0000`
        Look at a permission calculator for more info on permissions: https://finitereality.github.io/permissions-calculator/
        Args:
            name (str): the name of the role
            permissions (str or int): the permissions for the role
            hoist (bool, optional): set the role to be hoisted. Defaults to False.
            mentionable (bool, optional): set the role to be mentionable. Defaults to False.
            hex (int, optional): the color to set the role. Defaults to None.
        """
        none_list = ["none", "0", "no", "false", "f", "n", "nothing", "null", "nil"]
        if name is None:
            await ctx.send(":x: You need to give a name for the role!")
            return
        if permissions in none_list:
            permissions = None
        if permissions is None:
            permissions = discord.Permissions.none()

        elif permissions is not int:
            permissions = discord.Permissions.all() if permissions == "all" else discord.Permissions(int(permissions))

        else:
            await ctx.send(
                "Look at a permission calculator for more info on permissions: https://finitereality.github.io/permissions-calculator/\nWhen you get the permissions that you want, copy the number on the very top of the page. Should look something like this",
                file=discord.File("imgs/permissions.png"),
            )
        hex = int(hex, 16) if hex is not None else 0
        await ctx.guild.create_role(
            name=name,
            permissions=permissions,
            color=discord.Color(value=hex),
            hoist=hoist,
            mentionable=mentionable,
            reason=f"{ctx.author} used role create",
        )
        await ctx.send(
            f"Alright, I've created {name} with the following overrides: Permission Value:{permissions.value} Hex:{hex} Hoist:{hoist} Mentionable:{mentionable}",
            ephemeral=True,
        )

    @role.command()
    @permissions.has_permissions(manage_roles=True)
    async def remove(self, ctx, role: discord.Role):
        """Deletes a role

        Args:
            role (str): the role to delete
        """
        if role is None:
            return await ctx.send(":x: You need to give a role!")
        # check if a role with the name exists
        if role.name in [i.name for i in ctx.guild.roles]:
            if len([i for i in ctx.guild.roles if i.name == role.name]) > 1:
                return await ctx.send("There are roles with the same name!", ephemeral=True)
            await role.delete()
            await ctx.send("Role deleted!", ephemeral=True)

    @role.command()
    @permissions.has_permissions(manage_roles=True)
    async def forcedel(self, ctx, role: discord.Role):
        await role.delete(reason=f"{ctx.author} used role forcedel")
        await ctx.send(f"I've successfully deleted {role.name}!", ephemeral=True)

    @role.command()
    @permissions.has_permissions(manage_roles=True)
    async def change(
        self,
        ctx,
        role: discord.Role,
        name: str = None,
        permissions: str or int = None,
        hoist: bool = None,
        mentionable: bool = None,
        hex: str or int or hex = None,
    ):
        # sourcery skip: avoid-builtin-shadow
        """Edit any role to add new permissions, make it hoisted, mentionable, and a new color
        Example: `/role edit role_name new_name permission_value hoist:True/False mentionable:True/False hex:number`
        **Hint** True and False are case sensitive.
        Args:
            role (str): the role to edit
            name (str, optional): the new name for the role. Defaults to the current name.
            permissions (int, optional): permission value to give the role. Defaults to the roles current permissions.
            hoist (bool, optional): set the role to be hoisted. Defaults to the roles current hoist value.
            mentionable (bool, optional): set the role to be mentionable. Defaults to the roles current mentionable value.
            hex (int, optional): color hex to set the role. Defaults to roles current hex value.
        """
        if role is None:
            await ctx.send(":x: Specify a role that you want me to edit!")
            return

        if name is None:
            name = role.name

        if hex is not None:
            with contextlib.suppress(Exception):
                hex = int(hex, 16)
        else:
            # get the current color hex int
            hex = role.color.value

        if permissions is None:
            permissions = role.permissions

        elif permissions is not int:
            if permissions == "all":
                permissions = discord.Permissions.all()
            else:
                try:
                    permissions = discord.Permissions(int(permissions))
                except Exception:
                    await ctx.send(
                        "Look at a permission calculator for more info on permissions: https://finitereality.github.io/permissions-calculator/\nWhen you get the permissions that you want, copy the number on the very top of the page. Should look something like this",
                        file=discord.File("imgs/permissions.png"),
                    )
                    return
        hoist = role.hoist if hoist is None else hoist
        mentionable = role.mentionable if mentionable is None else mentionable
        try:
            await role.edit(
                name=name,
                permissions=permissions,
                hoist=hoist,
                mentionable=mentionable,
                color=discord.Color(value=hex),
                reason=f"{ctx.author} used role edit",
            )
            await ctx.send(
                f"Alright, I've edited {role.name} with the following overrides: Permission Value:{permissions.value} Hex:{hex} Hoist:{hoist} Mentionable:{mentionable}",
                ephemeral=True,
            )
        except Exception as e:
            capture_exception(e)
            await ctx.send(f"I couldn't edit the role because of this error!:\n{e}", ephemeral=True)

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @permissions.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(
        embed_links=True,
        manage_channels=True,
        manage_guild=True,
        manage_messages=True,
        attach_files=True,
        add_reactions=True,
        read_message_history=True,
        send_messages=True,
        use_external_emojis=True,
        mention_everyone=True,
        external_emojis=True,
        manage_webhooks=True,
        manage_permissions=True,
        manage_nicknames=True,
        change_nickname=True,
        manage_threads=True,
    )
    async def nuke(self, ctx, channel: discord.TextChannel = None, ephemeral: bool = False):
        """Deletes a channel and clones it for you to quickly delete all the messages inside of it"""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        embed = Embed(title="Channel Nuked", color=0x00FF00)
        embed.set_image(url="https://media.giphy.com/media/HhTXt43pk1I1W/giphy.gif")
        if channel is None:
            await ctx.send("Please specify a channel to delete!")
            return

        confirmation = await ctx.send("Are you sure you want to do this? This action cannot be undone!")

        await confirmation.add_reaction("✅")
        await confirmation.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in {"✅", "❌"}

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30, check=check)
        except asyncio.TimeoutError:
            await confirmation.delete(delay=0)
            return await ctx.send("You took to long to react.", delete_after=10)
        if str(reaction.emoji) == "❌":
            await confirmation.delete()
            await ctx.send("Task cancelled!", ephemeral=True)
            return

        await confirmation.delete(delay=0)
        deleted_channel = self.bot.get_channel(channel.id)
        new_channel = await ctx.guild.create_text_channel(
            name=deleted_channel.name,
            reason=f"{ctx.author} used nuke",
            overwrites=deleted_channel.overwrites,
            position=deleted_channel.position,
            topic=deleted_channel.topic,
            slowmode_delay=deleted_channel.slowmode_delay,
            nsfw=deleted_channel.nsfw,
            category=deleted_channel.category,
        )
        try:
            await deleted_channel.delete(reason=f"{ctx.author} used nuke")
        except Exception:
            return await ctx.send(f"Couldn't delete {deleted_channel.name}. Give me the permissions to do so.")
        with contextlib.suppress(Exception):
            await new_channel.send(embed=embed, delete_after=30)
        with contextlib.suppress(Exception):
            await ctx.send("Channel nuked!", delete_after=5)

    @commands.hybrid_command()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True, manage_channels=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True, manage_channels=True)
    async def mutesetup(self, ctx):
        """Sets up the muted role for the server"""
        init = await ctx.send("Setting up the muted role...")
        await asyncio.sleep(1.5)
        if muted_role := next((g for g in ctx.guild.roles if g.name.lower() == "muted"), None):
            await init.edit(
                content="Appears as though there's already a muted role in this server. Please remove this role and run this command again."
            )
        else:
            await init.edit(
                content="I couldn't find a muted role!\nI'll create one for you and assign the correct permissions for you!"
            )
            await asyncio.sleep(3)
            muted_role = await ctx.guild.create_role(
                name="muted",
                color=discord.Colour.dark_grey(),
                hoist=False,
                mentionable=False,
            )
            try:
                for channel in ctx.guild.channels:
                    if (
                        channel.type == discord.ChannelType.text
                        and channel.permissions_for(muted_role).send_messages is not False
                    ):
                        await channel.set_permissions(muted_role, send_messages=False)
            except Exception as e:
                await init.edit(
                    content=f"I couldn't edit this servers' channel permissions to correctly setup the muted role because of this error:\n{e}\n\nRegardless, I've made the role and setup the role permissions."
                )
            await init.edit(content="I've set up the muted role and permissions for you!")

    @commands.hybrid_command()
    @permissions.slash_has_permissions(moderate_members=True)
    @commands.bot_has_permissions(embed_links=True, moderate_members=True)
    @commands.guild_only()
    async def mute(
        self,
        ctx,
        member: discord.Member,
        time: str,
        reason: Optional[str] = None,
        ephemeral: bool = False,
    ):
        """Mute someone for a certain amount of time, from 10 seconds to 28 days."""
        if reason is None:
            reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        # make a tuple of valid time unit strings
        valid_time_units = ("s", "m", "h", "d", "w")
        if not time.endswith(valid_time_units):
            await ctx.send("Invalid time unit! Please use s, m, h, d, or w.", ephemeral=True)
            return
        if reason is None:
            reason = f"Action done by {ctx.author} (ID: {ctx.author.id})"
        if time.endswith("s"):
            time = int(time[:-1])
        elif time.endswith("m"):
            time = int(time[:-1]) * 60
        elif time.endswith("h"):
            time = int(time[:-1]) * 3600
        elif time.endswith("d"):
            time = int(time[:-1]) * 86400
        elif time.endswith("w"):
            time = int(time[:-1]) * 604800
        else:
            time = int(time)
        if time > 2419200:
            await Embed(
                description="You can't mute someone for more than 28 days! Please use a shorter time.",
            ).send(ctx, ephemeral=True)
            return
        if await permissions.check_priv(ctx, member=member):
            return
        try:
            await member.timeout(datetime.timedelta(seconds=time), reason=reason)
        except Exception as e:
            # say that the bot needs moderate_members permissions
            await Embed(
                title="Error",
                description=f"I need the `Moderate Members` permission to do this.\nTrue Error:{e}",
            ).send(ctx, ephemeral=True)
            return

        if time > 86400:
            await Embed(
                description=f"{member.mention} has been muted for {time // 86400} days.",
            ).send(ctx, ephemeral=ephemeral)
        elif time > 3600:
            await Embed(
                description=f"{member.mention} has been muted for {time // 3600} hours.",
            ).send(ctx, ephemeral=ephemeral)
        elif time > 60:
            await Embed(
                description=f"{member.mention} has been muted for {time // 60} minutes.",
            ).send(ctx, ephemeral=ephemeral)
        else:
            await Embed(
                description=f"{member.mention} has been muted for {time} seconds.",
            ).send(ctx, ephemeral=ephemeral)

    @commands.hybrid_command()
    @permissions.slash_has_permissions(moderate_members=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    @commands.guild_only()
    async def unmute(self, ctx, member: discord.Member, *, reason: str = None):
        """Unmute someone"""
        # check if the member is timed out

        if member.is_timed_out:
            try:
                await member.timeout(None, reason=reason)
                await ctx.send(f"{member.mention} has been unmuted.")
            except Exception as e:
                capture_exception(e)
                await ctx.send(
                    f"I couldn't unmute {member.mention}! Please make sure I have the `Timeout Members` permission!\nHere's the error: {e}",
                    ephemeral=True,
                )
        else:
            await ctx.send(f"{member.mention} is not timed out!", ephemeral=True)

    # Forked from and edited
    # https://github.com/Rapptz/RoboDanny/blob/715a5cf8545b94d61823f62db484be4fac1c95b1/cogs/mod.py#L1163

    @commands.hybrid_group()
    @commands.guild_only()
    @checks.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(embed_links=True, manage_roles=True)
    @permissions.dynamic_ownerbypass_cooldown(1, 8, commands.BucketType.user)
    async def purge(self, ctx, num: Optional[Union[int, str]] = None):
        """Removes messages that meet a criteria.
        In order to use this command, you must have Manage Messages permissions.
        Note that the bot needs Manage Messages as well. These commands cannot
        be used in a private message.
        When the command is done doing its work, you will get a message
        detailing which users got removed and how many messages got removed.
        `/purge all` removes 30 messages.
        """
        if ctx.invoked_subcommand is None:
            # assume we're purging all messages and invoke purge all
            num = int(num) if num is not None else 30
            if num == 0:
                return await ctx.send(":x: You cannot purge 0 messages.", delete_after=10)
            await ctx.invoke(self.bot.get_command("purge all"), num)

    async def do_removal(self, ctx, limit, predicate, *, before=None, after=None):
        await ctx.typing()
        if limit > 2000:
            return await ctx.send(f"Too many messages to search given ({limit}/2000)")

        before = ctx.message if before is None else discord.Object(id=before)
        if after is not None:
            after = discord.Object(id=after)

        try:
            deleted = await ctx.channel.purge(limit=limit, before=before, after=after, check=predicate)
        except discord.errors.Forbidden as e:
            return await ctx.send("I do not have permissions to delete messages.")
        except discord.HTTPException as e:
            return await ctx.send(f"Error: {e} (try a smaller search?)")

        spammers = Counter(m.author.display_name for m in deleted)
        deleted = len(deleted)
        messages = [f'{deleted} message{" was" if deleted == 1 else "s were"} removed.']
        if deleted:
            messages.append("")
            spammers = sorted(spammers.items(), key=lambda t: t[1], reverse=True)
            messages.extend(f"**{name}**: {count}" for name, count in spammers)

        to_send = "\n".join(messages)

        if len(to_send) > 2000:
            await ctx.send(f"Successfully removed {deleted} messages.", delete_after=delay)
        else:
            await ctx.send(to_send, delete_after=3)

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def all(self, ctx, search=30):
        """Removes all messages."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await self.do_removal(ctx, search, lambda e: True)

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def embeds(self, ctx, search=100):
        """Removes messages that have embeds in them."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await self.do_removal(ctx, search, lambda e: len(e.embeds))

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def files(self, ctx, search=100):
        """Removes messages that have attachments in them."""
        await self.do_removal(ctx, search, lambda e: len(e.attachments))

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def images(self, ctx, search=100):
        """Removes messages that have embeds or attachments."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()

        await self.do_removal(ctx, search, lambda e: len(e.embeds) or len(e.attachments))

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def mentions(self, ctx, search=30):
        """Removes messages that have user mentions."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await self.do_removal(ctx, search, lambda e: len(e.mentions))

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def user(self, ctx, member: MemberConverter, search=100):
        """Removes all messages by the member."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await self.do_removal(ctx, search, lambda e: e.author == member)

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def startswith(self, ctx, *, substr: str):
        """Removes all messages that start with a keyword"""
        with contextlib.suppress(Exception):
            await ctx.message.delete()

        await self.do_removal(ctx, 100, lambda e: e.content.startswith(substr))

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def contains(self, ctx, *, substr: str):
        """Removes all messages containing a substring.
        The substring must be at least 2 characters long.
        """
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await self.do_removal(ctx, 100, lambda e: substr in e.content)

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def bots(self, ctx, prefix=None, search=300):
        """Removes a bot user's messages and messages with their optional prefix.
        Example: `/purge bots <the bots prefix[this is optional]> <amount[this is also optional]>`"""
        with contextlib.suppress(Exception):
            await ctx.message.delete()

        getprefix = prefix or self.config.prefix

        def predicate(m):
            return m.author.bot if m.webhook_id is None else m.content.startswith(tuple(getprefix))

        await self.do_removal(ctx, search, predicate)

    @purge.command(aliases=["emojis", "emote", "emotes"])
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def emoji(self, ctx, search=100):
        """Removes all messages containing custom emoji."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        custom_emoji = re.compile(r"<a?:[a-zA-Z0-9\_]+:([0-9]+)>")

        def predicate(m):
            return custom_emoji.search(m.content)

        await self.do_removal(ctx, search, predicate)

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def reactions(self, ctx, search=100):
        """Removes all reactions from messages that have them."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        if search > 2000:
            return await ctx.send(f"Too many messages to search for ({search}/2000)")

        total_reactions = 0
        async for message in ctx.history(limit=search, before=ctx.message):
            if len(message.reactions):
                total_reactions += sum(r.count for r in message.reactions)
                await message.clear_reactions()

        await ctx.send(f"Successfully removed {total_reactions} reactions.")

    @purge.command()
    @commands.guild_only()
    @permissions.dynamic_ownerbypass_cooldown(1, 5, commands.BucketType.user)
    async def annoying(self, ctx, search=250, prefix=None):
        """Removes annoying messages.
        This command purges mentions, embeds, files / attachments, and role mentions."""
        with contextlib.suppress(Exception):
            await ctx.message.delete()
        await self.do_removal(
            ctx,
            search,
            lambda e: len(e.mentions) and len(e.embeds) and len(e.attachments) and len(e.role_mentions),
        )


async def setup(bot: AGB) -> None:
    await bot.add_cog(Moderator(bot))
