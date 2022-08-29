from __future__ import annotations
from typing import Any, TYPE_CHECKING, Union, Optional

from discord import Embed as DpyEmbed
from discord.utils import MISSING

# avoid circular imports
# need to move these too, soon?
prim_color = 1592481
website = "https://lunardev.group"
logo = "https://lunardev.group/assets/logo.png"

if TYPE_CHECKING:
    from datetime import datetime

    from discord import Colour, Message
    from discord.abc import Messageable

    TwoValues = Union[
        Optional[str],  # name/text = str or None
        tuple[Optional[str]],  # name/text = (str or None, )
        tuple[
            Optional[str], Optional[str]
        ],  # (str or None (name/text), str or None (icon_url))
    ]


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
    elif isinstance(value, tuple):
        if len(value) == 1:
            return value[0], None
        elif len(value) == 2:
            return value[0], value[1]
        return None, None
    else:
        return None, None


class EmbedMaker(DpyEmbed):
    def __init__(
        self,
        *,
        color: Optional[Union[int, Colour]] = MISSING,
        colour: Optional[Union[int, Colour]] = MISSING,
        title: Optional[Any] = None,
        url: Optional[Any] = MISSING,
        description: Optional[Any] = None,
        timestamp: Optional[datetime] = None,
        author: Optional[TwoValues] = None,
        footer: Optional[TwoValues] = None,
        thumbnail: Optional[str] = MISSING,
        image: Optional[str] = None,
    ) -> None:
        _color = colour if colour is not MISSING else color

        if url is MISSING:
            url = website
        if _color is MISSING:
            color = prim_color
        elif _color is None:
            color = 0x000000
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

        if image is not None:
            self.set_image(url=image)

        self._maybe_footer(footer)
        self._maybe_author(author)

    async def __call__(
        self,
        destination: Messageable,
        content: Optional[str] = None,
        **kwargs,
    ) -> Message:
        return await self.send(destination, content, **kwargs)

    async def send(
        self,
        destination: Messageable,
        content: Optional[str] = None,
        **kwargs,
    ) -> Message:
        return await destination.send(content=content, embed=self, **kwargs)

    def _maybe_footer(self, value: TwoValues) -> None:
        text, icon_url = _parse_tuple_values(value)
        self.set_footer(text=text, icon_url=icon_url)

    def _maybe_author(self, value: TwoValues) -> None:
        name, icon_url = _parse_tuple_values(value)
        if name:
            self.set_author(name=name, icon_url=icon_url)
