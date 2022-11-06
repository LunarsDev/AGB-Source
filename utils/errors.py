from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Union

from discord.ext.commands.errors import CheckFailure, CommandError

if TYPE_CHECKING:
    from discord import Member, User
    from Manager.database import Blacklist


class DatabaseError(Exception):
    def __init__(self, error: Any):
        self.original: Any = error
        self.message: str = str(error)
        super().__init__(self.message)


class DisabledCommand(CheckFailure):
    def __init__(
        self,
        *,
        is_group: bool,
        qualified_name: str,
        group_disabled: bool = False,
        disabled: Optional[list[str]] = None,
    ) -> None:
        self.is_group: bool = is_group
        self.qualified_name: str = qualified_name
        self.group_disabled: bool = group_disabled
        self.disabled: list[str] = disabled or []

        to_raise: str = "This command is disabled"
        if is_group and group_disabled:
            to_raise = "This command's parent group is disabled"
        elif is_group:
            disabled_commands = ", ".join(self.disabled)
            to_raise = f"Parts of this command ({disabled_commands}) are disabled"

        super().__init__(f"{to_raise} in this server.")


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
            DEFAULT_MESSAGE = f"{DEFAULT_MESSAGE[:-1]} for the following reason:\n{reason}."

        super().__init__(self.custom_message or DEFAULT_MESSAGE)


class GlobalDisabledCommand(CheckFailure):
    def __init__(self):
        super().__init__(":x: This command has been disabled!")


class ChatbotFailure(CommandError):
    pass
