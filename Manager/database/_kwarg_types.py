from __future__ import annotations

from typing import TYPE_CHECKING, List, Literal, NamedTuple, Optional, TypedDict

if TYPE_CHECKING:
    from datetime import datetime

    from typing_extensions import NotRequired

__all__: tuple[str, ...] = (
    "DBConfig",
    "UserEco",
    "Users",
    "Guilds",
    "AutoMod",
    "AutoRoles",
    "Badges",
    "Reminders",
    "Status",
    "Blacklist",
    "Commands",
    "GuildBlacklist",
    "ValidBadge",
)

ValidBadge = Literal["owner", "admin", "mod", "partner", "support", "friend"]


class DBConfig(NamedTuple):
    host: str
    user: str
    password: str
    database: str
    port: str


class UserEco(TypedDict):
    balance: NotRequired[Optional[int]]  # defaults to 500
    bank: NotRequired[Optional[int]]  # defaults to 500
    lastdaily: NotRequired[Optional[datetime]]  # defaults to None
    isbot: NotRequired[bool]  # defaults to False


class Users(TypedDict):
    # blacklisted: bool  # defaults to False
    isbot: NotRequired[bool]  # defaults to False
    # blacklisteduntil: NotRequired[datetime]  # defaults to None
    # blacklistedreason: NotRequired[str]  # defaults to None
    usedcmds: NotRequired[int]  # defaults to 0
    bio: NotRequired[Optional[str]]  # defaults to 'Mysterious User.'
    msgtracking: NotRequired[bool]  # defaults to True
    todos: NotRequired[Optional[List[str]]]  # defaults to None


class Guilds(TypedDict):
    hentaichannel: NotRequired[Optional[int]]  # defaults to None
    prefix: NotRequired[str]  # defaults to '/'
    welcomer: NotRequired[Optional[int]]  # defaults to None


class AutoMod(TypedDict):
    logchannelid: NotRequired[Optional[int]]  # defaults to None


class AutoRoles(TypedDict):
    roleids: NotRequired[Optional[List[int]]]  # defaults to None


class Badges(TypedDict):
    owner: NotRequired[List[int]]  # defaults to None
    admin: NotRequired[Optional[List[int]]]  # defaults to None
    mod: NotRequired[Optional[List[int]]]  # defaults to None
    partner: NotRequired[Optional[List[int]]]  # defaults to None
    support: NotRequired[List[int]]  # defaults to None
    friend: NotRequired[Optional[List[int]]]  # defaults to None


class Reminders(TypedDict):
    time: NotRequired[Optional[datetime]]  # defaults to None
    message: NotRequired[Optional[str]]  # defaults to None


class Status(TypedDict):
    id: int  # primary key, serial
    status: NotRequired[Optional[str]]  # defaults to None


class Blacklist(TypedDict):
    blacklisted: NotRequired[bool]  # defaults to False
    blacklistedtill: NotRequired[Optional[str]]  # defaults to None
    reason: NotRequired[Optional[str]]  # defaults to 'Unspecified'


class Commands(TypedDict):
    guild: int  # primary key
    disabled: NotRequired[Optional[List[str]]]  # defaults to None


class GuildBlacklist(TypedDict):
    name: NotRequired[Optional[str]]  # defaults to 'Unknown''
    blacklisted: NotRequired[bool]  # defaults to False
