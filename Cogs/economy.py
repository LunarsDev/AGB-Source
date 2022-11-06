from __future__ import annotations

from typing import TYPE_CHECKING

from discord import Member
from discord.ext import commands
from Manager.emoji import Emoji
from utils import imports, permissions
from utils.embeds import EmbedMaker as Embed

if TYPE_CHECKING:
    from index import AGB


class Creamy(commands.RoleConverter):
    async def convert(self, ctx, argument):
        return await super().convert(ctx, argument.lower())


class Economy(commands.Cog, name="economy"):
    """All things economy"""

    def __init__(self, bot: AGB):
        self.bot: AGB = bot
        self.config = imports.get("config.json")
        self.message_cooldown = commands.CooldownMapping.from_cooldown(1.0, 3.0, commands.BucketType.user)

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
                raise commands.BadArgument(f"{len(members)} members found, please be more specific.") from e

    @commands.hybrid_group(name="eco")
    @commands.check(permissions.is_owner)
    async def eco(self, ctx: commands.Context):
        """Economy commands."""
        await ctx.send("Economy commands.", ephemeral=True)

    @eco.command()
    @commands.check(permissions.is_owner)
    async def profile(self, ctx, *, user: Member):
        data = await self.bot.db.fetch_economy_user(user.id)
        # userdata = await self.bot.db.fetch_badge_user(user.id) # Plan to add badge fetching and dev emojis next to devs
        # ^^ Fix Objects.py (Class Badge(Base)) to match more like Class UserEconomy(Base)
        # embed = Embed(
        #     title="Economy Profile",
        #     description=f"**{user.name}#{user.discriminator}**",
        #     color=0x7CEE7E,
        # )
        # embed.set_thumbnail(url=user.avatar.url)
        # embed.add_field(
        #     name="Balance",
        #     value=f"Pocket: `{data.balance}` \nBank: `{data.bank}`",
        #     inline=True,
        # )
        # embed.add_field(
        #     name="Inventory", value="*Inventory is currently N/A*", inline=False
        # )
        # await ctx.send(embed=embed)

        await Embed(title="Economy Profile", description=f"**{user.name}#{user.discriminator}**",).add_field(
            name=f"{Emoji.money} Balance",
            value=f"Pocket: `{data.balance}` \nBank: `{data.bank}`",
            inline=True,
        ).add_field(name=f"{Emoji.pencil} Inventory", value="*Inventory is currently N/A*", inline=False,).send(ctx)


async def setup(self) -> None:
    await self.add_cog(Economy(self))
