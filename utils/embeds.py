from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, Optional, Union

from discord import Embed as DpyEmbed, Interaction
from discord.utils import MISSING
from discord.ext.commands.context import Context

# avoid circular imports
# need to move these too, soon?
prim_color = 0x2F3136
website = "https://lunardev.group"
logo = "https://lunardev.group/assets/logo.png"
partners = ["dash.lunardev.group", "connect.twisea.net"]


if TYPE_CHECKING:
    from datetime import datetime

    from discord import Colour, Message as _Message, InteractionMessage, WebhookMessage
    from discord.abc import Messageable

    TwoValues = Union[
        Optional[str],  # name/text = str or None
        tuple[Optional[str]],  # name/text = (str or None, )
        tuple[Optional[str], Optional[str]],  # (str or None (name/text), str or None (icon_url))
    ]

    CtxOrInteraction = Union[Context, Interaction]
    Message = Union[_Message, InteractionMessage, WebhookMessage]


def _parse_tuple_values(value: TwoValues) -> tuple[Optional[str], Optional[str]]:
    """Parses either a tuple with two values into the values or None if the value is None or not provided
        or :class:`str` into a tuple with the value and None.

    E.g.
    >>> __parse_values(('name', 'icon_url'))
    ('name', 'icon_url')
    >>> __parse_values(('name',))
    ('name', None)
    >>> __parse_values(('name', 'icon_url', 'extra'))
    ('name', 'icon_url')
    >>> __parse_values(None)
    (None, None)
    >>> __parse_values('name')
    ('name', None)

    Is this func neccessary? no. does it make our code more readable? yes.

    Parameters
    ----------
    value : Union[Optional[str], tuple[Optional[str]], tuple[Optional[str], Optional[str]]]
        The value to parse.

    Returns
    -------
    tuple[Optional[str], Optional[str]]
        The parsed values.
    """

    if isinstance(value, str):
        return value, None
    if isinstance(value, tuple):
        if len(value) == 1:
            return value[0], None
        return (value[0], value[1]) if len(value) == 2 else (None, None)
    return None, None


class EmbedMaker(DpyEmbed):
    def __init__(
        self,
        title: Optional[Any] = None,
        description: Optional[Any] = None,
        *,
        ctx: Optional[Context] = None,
        interaction: Optional[Interaction] = None,
        url: Optional[Any] = MISSING,
        color: Optional[Union[int, Colour]] = MISSING,
        colour: Optional[Union[int, Colour]] = MISSING,
        timestamp: Optional[datetime] = None,
        author: Optional[TwoValues] = MISSING,
        footer: Optional[TwoValues] = MISSING,
        thumbnail: Optional[str] = MISSING,
        image: Optional[str] = None,
    ) -> None:
        _color = colour if colour is not MISSING else color

        if url is MISSING:
            url = website
        if _color is MISSING:
            color = prim_color
        elif _color is None:
            color = 0x2F3136
        else:
            color = _color

        super().__init__(
            title=title,
            url=url,
            description=description,
            timestamp=timestamp,
            color=color,
        )
        if thumbnail is MISSING:
            self.set_thumbnail(url=logo)
        elif thumbnail is not None:
            self.set_thumbnail(url=thumbnail)

        if footer is MISSING:
            footer = random.choice(partners)

        if image is not None:
            self.set_image(url=image)

        self.ctx_or_interaction: Optional[CtxOrInteraction] = ctx or interaction
        self.ctx: Optional[Context] = ctx
        self.interaction: Optional[Interaction] = interaction

        self._provided_footer: Optional[TwoValues] = footer
        self._provided_author: Optional[TwoValues] = author
        self._maybe_footer(footer)
        self._maybe_author(author)

    async def __call__(
        self,
        destination: Optional[Messageable] = None,
        content: Optional[str] = None,
        **kwargs,
    ) -> Optional[Message]:
        return await self.send(content=content, destination=destination, **kwargs)

    async def send(
        self,
        destination: Optional[Messageable] = None,
        content: Optional[str] = None,
        **kwargs,
    ) -> Optional[Message]:
        send_method = None
        if destination:
            send_method = destination.send
            if isinstance(destination, (Context, Interaction)) and not self.ctx_or_interaction:
                self.ctx_or_interaction = destination
                setattr(self, "ctx" if isinstance(destination, Context) else "interaction", destination)
                self._maybe_author((None,))
        elif self.ctx_or_interaction:
            if self.ctx:
                send_method = self.ctx.send
            elif self.interaction:
                send_method = self.interaction.response.send_message
                if self.interaction.response.is_done():
                    send_method = self.interaction.followup.send

        if not send_method:
            raise ValueError("No destination, context or interaction provided.")

        return await send_method(content=content, embed=self, **kwargs)  # type: ignore

    def _maybe_footer(self, value: TwoValues) -> None:
        text, icon_url = _parse_tuple_values(value)
        self.set_footer(text=text, icon_url=icon_url)

    def _maybe_author(self, value: TwoValues) -> None:
        name, icon_url = _parse_tuple_values(value)
        if name:
            self.set_author(name=name, icon_url=icon_url)
        elif self.ctx_or_interaction and self._provided_author is not None:
            user = (
                self.ctx_or_interaction.author
                if isinstance(self.ctx_or_interaction, Context)
                else self.ctx_or_interaction.user
            )
            self.set_author(name=user.name, icon_url=user.display_avatar.url)
