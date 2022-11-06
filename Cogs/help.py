from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands, menus
from index import colors, config
from Manager.emoji import Emoji
from utils.embeds import EmbedMaker as Embed

if TYPE_CHECKING:
    from index import AGB


class Help(commands.Cog):
    def __init__(self, bot: AGB):
        self.bot: AGB = bot
        bot.help_command = FormattedHelp()
        self.bot._original_help_command = bot.help_command


async def cog_unload(self):
    self.bot.help_command = self.bot._original_help_command


async def cog_check(self, ctx):
    """A local check which applies to all commands in this cog."""
    if not ctx.guild:
        raise commands.NoPrivateMessage
    return True


class HelpMenu(menus.ListPageSource):
    def __init__(self, data, per_page):
        super().__init__(data, per_page=per_page)

    async def format_page(self, menu, entries):
        return entries


class FormattedHelp(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={"usage": "`/help (command/category)`", "hidden": True})

    async def cog_check(ctx):
        """A local check which applies to all commands in this cog."""
        if not ctx.guild:
            return await ctx.send("This command can only be used in a server.")

    def get_command_signature(self, command):
        return f"{self.context.clean_prefix}{command.qualified_name} {command.signature}"

    def rem_lead_space(self, strict=False):
        if self and not strict and self[0] == "\n":
            self = self[1:]
        lines = self.splitlines(True)
        max_spaces = -1
        for line in lines:
            if line != "\n":
                for idx, c in enumerate(lines[:max_spaces]):
                    if c != " ":
                        break
                max_spaces = idx + 1
        return "".join([l if l == "\n" else l[max_spaces - 1 :] for l in lines])

    async def send_command_help(self, command):
        e = Embed(
            title=f"Help - {command.qualified_name} {await Emoji.rand_rainbow()}",
            description=f"{command.help}\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate}) ",
            color=colors.prim,
        )
        e.add_field(name="Usage", value=self.get_command_signature(command).replace("*", ""))
        e.set_footer(
            text=f"mc.lunardev.group 1.19.2 | {self.context.bot.user.name} by Motzumoto, iPlay G, WinterFe, and Soheab"
        )
        await self.get_destination().send(embed=e)

    async def send_group_help(self, group):
        ctx = self.context
        e = Embed(
            title=f"Help - {group.qualified_name} {await Emoji.rand_rainbow()}",
            description=f"{group.help}\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate}) ",
            color=colors.prim,
        )
        e.set_footer(
            text=f"mc.lunardev.group 1.19.2 | {self.context.bot.user.name} by Motzumoto, iPlay G, WinterFe, and Soheab"
        )
        embeds = [e]
        for command in group.commands:
            e = Embed(
                title=f"Help - {command.qualified_name} {await Emoji.rand_rainbow()}",
                description=f"{command.help}\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate}) ",
                color=colors.prim,
            )
            e.add_field(name="Usage", value=self.get_command_signature(command).replace("*", ""))
            e.set_footer(
                text=f"mc.lunardev.group 1.19.2 | {self.context.bot.user.name} by Motzumoto, iPlay G, WinterFe, and Soheab"
            )
            embeds.append(e)
        menu = menus.MenuPages(source=HelpMenu(embeds, per_page=1))
        await menu.start(ctx)

    async def send_cog_help(self, cog):
        ctx = self.context
        e = Embed(
            title=f"Help - {cog.qualified_name} {await Emoji.rand_rainbow()}",
            description=getattr(cog, "__doc__", None),
            color=colors.prim,
        )
        e.set_footer(
            text=f"mc.lunardev.group 1.19.2 | {self.context.bot.user.name} by Motzumoto, iPlay G, WinterFe, and Soheab"
        )
        embeds = [e]
        for command in cog.walk_commands():
            if isinstance(command, commands.Group) or getattr(command, "hidden"):
                continue
            e = Embed(
                title=f"Help - {command.qualified_name} {await Emoji.rand_rainbow()}",
                description=f"{command.help}\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate})  ",
                color=colors.prim,
            )
            if command.usage:
                e.add_field(
                    name="Usage",
                    value=self.get_command_signature(command).replace("*", ""),
                )
                e.add_field(name="Support Server", value=f"[Click Me]({config.Server})")
            e.set_footer(
                text=f"mc.lunardev.group 1.19.2 | {self.context.bot.user.name} by Motzumoto, iPlay G, WinterFe, and Soheab"
            )
            embeds.append(e)
        menu = menus.MenuPages(source=HelpMenu(embeds, per_page=1))
        await menu.start(ctx)

    async def send_bot_help(self, mapping):
        # check if we're in a DM
        if self.context.guild is None:
            fuck_off = "This command can only be used in a server."
            await self.get_destination().send(fuck_off)
            return
        nsfw_channels = (
            ", ".join([c.mention for c in self.context.guild.text_channels if c.is_nsfw()])
            or "No NSFW channels found. Make one to be able to use these commands."
        )
        async with self.context.typing():
            nsfw_cog = self.context.bot.get_cog("nsfw")
            nsfw_commands = nsfw_cog.get_commands()
            nsfw_q = [c.name for c in nsfw_commands if not c.hidden]
            nsfw_names = "".join(f"`{name}`, " for name in nsfw_q)

            info_cog = self.context.bot.get_cog("info")
            info_commands = info_cog.get_commands()
            info_q = [c.name for c in info_commands if not c.hidden]
            info_names = "".join(f"`{name}`, " for name in info_q)

            fun_cog = self.context.bot.get_cog("fun")
            fun_commands = fun_cog.get_commands()
            fun_q = [c.name for c in fun_commands if not c.hidden]
            fun_names = "".join(f"`{name}`, " for name in fun_q)

            guild_cog = self.context.bot.get_cog("discord")
            guild_commands = guild_cog.get_commands()
            guild_q = [c.name for c in guild_commands if not c.hidden]
            guild_names = "".join(f"`{name}`, " for name in guild_q)

            mod_cog = self.context.bot.get_cog("mod")
            mod_commands = mod_cog.get_commands()
            mod_q = [c.name for c in mod_commands if not c.hidden]
            mod_names = "".join(f"`{name}`, " for name in mod_q)

            if self.context.channel.is_nsfw():
                description = f"""For help on individual commands, use `/help <command>`.\n\n**{await Emoji.rand_rainbow()} {info_cog.qualified_name.capitalize()}**\n{info_names}\n\n**{await Emoji.rand_rainbow()} {fun_cog.qualified_name.capitalize()}**\n{fun_names}\n\n**{await Emoji.rand_rainbow()} {guild_cog.qualified_name.capitalize()}**
				{guild_names}\n\n**{await Emoji.rand_rainbow()} {mod_cog.qualified_name.capitalize()}**\n{mod_names}\n\n**{await Emoji.rand_rainbow()} **{nsfw_cog.qualified_name.capitalize()}**\n{nsfw_names}\nalso, there are nsfw slash commands. make sure AGB has permission to register them in your server."""

                embed = Embed(
                    color=colors.prim,
                    description=f"{description}\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate}) ",
                )
                embed.set_footer(
                    text="If there is anything that you would like to see / changed, run /𝐬𝐮𝐠𝐠𝐞𝐬𝐭 with your suggestion!\nAlso check out our server host!"
                )
            else:
                description = f"""**{await Emoji.rand_rainbow()} {info_cog.qualified_name.capitalize()}**\n{info_names}\n\n**{await Emoji.rand_rainbow()} {fun_cog.qualified_name.capitalize()}**\n{fun_names}\n\n**{await Emoji.rand_rainbow()} {guild_cog.qualified_name.capitalize()}**\n{guild_names}\n\n**{await Emoji.rand_rainbow()} {mod_cog.qualified_name.capitalize()}**\n{mod_names}\n\n**{nsfw_cog.qualified_name.capitalize()}**\nNsfw commands are hidden. To see them run /help in any of these NSFW channels.\n{nsfw_channels}"""

                embed = Embed(
                    color=colors.prim,
                    description=f"{description}\n[Add me]({config.Invite}) | [Support]({config.Server}) | [Vote]({config.Vote}) | [Donate]({config.Donate}) ",
                )
                embed.set_footer(
                    text="If there is anything that you would like to see / changed, run /𝐬𝐮𝐠𝐠𝐞𝐬𝐭 with your suggestion!"
                )

            embed.set_thumbnail(url=self.context.bot.user.avatar)
            await self.get_destination().send(embed=embed)
            return

        #     # nsfw_cog = self.bot.get_cog('nsfw')
        #     # nsfw_commands = nsfw_cog.get_commands()

        #     for cog, commands in mapping.items():
        #         qualified_names = [c.name for c in commands if not c.hidden]
        #         if not qualified_names or getattr(cog, 'hidden', None) or not cog:
        #             continue
        #         qualified_names = ''.join(
        # f'`{name}`, ' for index, name in enumerate(qualified_names))

        #         embed_description += f"**{await Emoji.rand_rainbow()} {cog.qualified_name.capitalize() or 'No Category'}**\n{qualified_names[:-2]}\n\n"

        # embed = Embed(color=colors.prim, description=f"For help on individual commands, use `/help <command>`.\n\n{embed_description}")
        # embed.add_field(name='Support Server', value=f"[Click Me]({config.Server})")
        # embed.set_footer(text="If there is anything that you would like to see / changed, run /𝐬𝐮𝐠𝐠𝐞𝐬𝐭 with your suggestion!")
        # embed.set_thumbnail(url=self.context.bot.user.avatar)
        # await self.get_destination().send(embed=embed)


async def setup(bot: AGB) -> None:
    await bot.add_cog(Help(bot))
    bot.get_command("help").hidden = True


#         embed = Embed(title=f"AGB Commands{await Emoji.rand_rainbow()}",
#                     description="AGB can offer you a ton of useful and fun commands to use!", color=colors.prim)
#         embed.set_image(
#             url='https://cdn.discordapp.com/avatars/723726581864071178/5e7d167dbf17ebc4137b2ed3fa2a698f.png?size=1024')
#         await self.context.send(embed=embed, view=Paginator(self.context, *units))
