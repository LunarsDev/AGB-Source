from __future__ import annotations

from typing import TYPE_CHECKING, List, Literal, NamedTuple, Optional, TypedDict

if TYPE_CHECKING:
    from datetime import datetime

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
    userid: int  # primary key
    balance: int  # defaults to 500
    bank: int  # defaults to 500
    lastdaily: Optional[datetime]  # defaults to None
    isbot: bool  # defaults to False


class Users(TypedDict):
    userid: int  # primary key
    # blacklisted: bool  # defaults to False
    isbot: bool  # defaults to False
    # blacklisteduntil: Optional[datetime]  # defaults to None
    # blacklistedreason: Optional[str]  # defaults to None
    usedcmds: int  # defaults to 0
    bio: str  # defaults to 'Mysterious User.'
    msgtracking: bool  # defaults to True
    todos: Optional[List[str]]  # defaults to None


class Guilds(TypedDict):
    guildid: int  # primary key
    hentaichannel: Optional[int]  # defaults to None
    prefix: str  # defaults to '/'
    welcomer: Optional[int]  # defaults to None


class AutoMod(TypedDict):
    guildid: int  # primary key
    logchannelid: Optional[int]  # defaults to None


class AutoRoles(TypedDict):
    guildid: int  # primary key
    roleids: Optional[List[int]]  # defaults to None


class Badges(TypedDict):
    userid: int  # primary key
    owner: Optional[List[int]]  # defaults to None
    admin: Optional[List[int]]  # defaults to None
    mod: Optional[List[int]]  # defaults to None
    partner: Optional[List[int]]  # defaults to None
    support: Optional[List[int]]  # defaults to None
    friend: Optional[List[int]]  # defaults to None


class Reminders(TypedDict):
    userid: int  # primary key
    time: Optional[datetime]  # defaults to None
    message: Optional[str]  # defaults to None


class Status(TypedDict):
    id: int  # primary key, serial
    status: Optional[str]  # defaults to None


class Blacklist(TypedDict):
    userid: int  # primary key
    blacklisted: bool  # defaults to False
    blacklistedtill: Optional[str]  # defaults to None
    reason: Optional[str]  # defaults to 'Unspecified'


class Commands(TypedDict):
    guild: int  # primary key
    disabled: Optional[List[str]]  # defaults to None


class GuildBlacklist(TypedDict):
    id: int  # primary key
    name: str  # defaults to 'Unknown''
    blacklisted: bool  # defaults to False
