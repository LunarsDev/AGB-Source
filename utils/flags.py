from typing import Union, Optional

from discord import Member, User
from discord.ext.commands import FlagConverter

__all__: tuple[str, ...] = ("BlacklistUserArguments",)


class BlacklistUserArguments(FlagConverter):
    user: Optional[Union[Member, User]] = None
    user_id: Optional[str] = None  # str for slash commands
    reason: Optional[str] = None
    days: Optional[int] = None
    blacklist: bool = True
    silent: bool = False
