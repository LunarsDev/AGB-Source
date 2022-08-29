from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional, Union

from datetime import datetime

from discord.ext.commands.errors import CheckFailure


if TYPE_CHECKING:
    from discord import User, Member
    from Manager.objects import Blacklist


class DatabaseError(Exception):
    def __init__(self, error: Any):
        self.original: Any = error
        self.message: str = str(error)
        super().__init__(self.message)


class DisabledCommand(CheckFailure):
    def __init__(self):
        super().__init__(":x: This command has been disabled!")


class BlacklistedUser(CheckFailure):
    def __init__(
        self,
        obj: Blacklist,
        user: Union[Member, User],
        message: Optional[str] = None,
    ) -> None:
        self.obj: Blacklist = obj
        self.user: Union[Member, User] = user
        self.custom_message: Optional[str] = message

        reason = obj.reason
        if reason and reason.strip() == "No reason":
            reason = None

        DEFAULT_MESSAGE = ":x: You're blacklisted."

        if obj.blacklistedtill:
            until = obj.blacklistedtill
            try:
                blacklist_date = datetime.strptime(until, "%Y-%m-%d %H:%M:%S.%f")
            except Exception:
                blacklist_date = datetime.strptime(until, "%Y-%m-%d %H:%M:%S.%f+00")

            timestamp = f"<t:{int(blacklist_date.timestamp())}:R>"
            DEFAULT_MESSAGE = f":x: You're temporary blacklisted till {timestamp}."

        if reason is not None:
            # [:-1] removes the "." at the end
            DEFAULT_MESSAGE = (
                f"{DEFAULT_MESSAGE[:-1]} for the following reason:\n{reason}."
            )

        super().__init__(self.custom_message or DEFAULT_MESSAGE)


class GlobalDisabledCommand(CheckFailure):
    def __init__(self):
        super().__init__(":x: This command has been disabled!")
