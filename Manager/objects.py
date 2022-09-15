from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from discord.utils import MISSING

if TYPE_CHECKING:
    from datetime import date

    from typing_extensions import Self

    from ._types import AutoMod as AutoModData
    from ._types import AutoPosting as AutoPostingData
    from ._types import AutoRoles as AutoRolesData
    from ._types import Blacklist as BlacklistData
    from ._types import GlobalVars as GlobalVarsData
    from ._types import Guild as GuildData
    from ._types import GuildBlacklist as GuildBlacklistData

    from ._types import Status as StatusData
    from ._types import User as UserData
    from ._types import UserEconomy as UserEconomyData
    from .database import Database


__all__: tuple[str, ...] = (
    "Table",
    "Badges",
    "table_to_cls",
    "AutoMod",
    "AutoPosting",
    "AutoRole",
    "Badge",
    "Blacklist",
    "Command",
    "Guild",
    "GuildBlacklist",
    "GlobalVar",
    # "Reminder",
    "Status",
    "User",
    "UserEconomy",
)


def _handle_varchar(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        return int(value) if value.isdigit() else value
    return value


def _handle_null_or_int(value: Any) -> Optional[int]:
    return int(value) if value else None


class Table(Enum):
    AUTOMOD = "automod"
    AUTOPOSTING = "autoposting"
    AUTOROLES = "autoroles"
    BADGES = "badges"
    BLACKLIST = "blacklist"
    COMMANDS = "commands"
    GLOBALVARS = "globalvars"
    GUILDBLACKLIST = "guildblacklist"
    GUILDS = "guilds"
    STATUS = "status"
    USER_ECONOMY = "usereco"
    USERS = "users"

    def __str__(self) -> str:
        return self.value


class Badges(Enum):
    owner = "owner"
    admin = "admin"
    mod = "mod"
    partner = "partner"
    support = "support"
    friend = "friend"
    user = "user"


class Base:
    table: Table
    columns: tuple[str, ...]
    database: Database
    data: Any

    if TYPE_CHECKING:

        def __init__(self, database: Database, /, *, data: Any) -> None:
            ...

    def __getitem__(self, key: str) -> Any:
        data = object.__getattribute__(self, "data")
        return data[key] if key in data else NotImplemented

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "data")
        if name in data:
            return data[name]
        raise AttributeError

    def __int__(self) -> int:
        possible_int_keys = ("id", "user_id", "guild_id")
        # type: ignore
        return int(
            getattr(
                self, next(
                    (key for key in possible_int_keys if key in self.data), 0)
            )
        )

    def __repr__(self) -> str:
        values = ", ".join(f"{key}={value!r}" for key,
                           value in self.data.items())
        return f"{self.__class__.__name__}({values})"

    def _handle_query_inputs(
        self, *, where: dict[str, Any], **kwargs
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        if any(key not in self.columns for key in kwargs):
            raise ValueError(
                f"Invalid column name, must be one of: {', '.join(self.columns)}"
            )
        inputs = {}
        index = 1

        values: list[Any] = []
        for key, value in where.items():
            where[key] = f"${index}"
            values.insert(index, value)
            index += 1

        for key, value in kwargs.items():
            inputs[key] = f"${index}"
            values.insert(index, value)
            index += 1

        return where, inputs, values

    async def handle_execute(self, *, where: dict[str, Any], **kwargs) -> Any:
        _where, _inputs, _values = self._handle_query_inputs(
            where=where, **kwargs)
        where = where or _where
        query = f"UPDATE {self.table} SET {', '.join(f'{key} = {value}' for key, value in _inputs.items())}"
        if _where:
            query += " WHERE " + " AND ".join(
                f"{key} = {value}" for key, value in _where.items()
            )
        query += " RETURNING *"
        data = await self.database.fetchrow(query, *_values)
        inst = self.__class__(self.database, data=dict(data))  # type: ignore
        self.database._add_to_cache(self.table, inst)
        return inst


class UserEconomy(Base):
    table = Table.USER_ECONOMY
    columns: tuple[str, ...] = ("balance", "bank", "lastdaily", "isbot")

    def __init__(self, database: Database, /, data: UserEconomyData) -> None:
        self.database = database
        self.data = data

        self.user_id: int = _handle_varchar(data["userid"])
        self.balance: int = _handle_varchar(data["balance"])
        self.bank: int = _handle_varchar(data["bank"])
        self.last_daily: date = data["lastdaily"]
        self.is_bot = _handle_varchar(data["isbot"])

    async def modify(
        self,
        *,
        balance: Optional[int] = None,
        bank: Optional[int] = None,
        last_daily: Optional[date] = None,
        is_bot: Optional[bool] = MISSING,
    ) -> User:
        kwargs = {}
        if balance is not None:
            kwargs["balance"] = balance
        if bank is not None:
            kwargs["bank"] = bank
        if last_daily is not None:
            kwargs["lastdaily"] = last_daily
        if is_bot is not MISSING:
            kwargs["isbot"] = str(is_bot).lower(
            ) if is_bot is not None else None
        return await Base.handle_execute(
            self, where={"userid": str(self.user_id)}, **kwargs
        )


class User(Base):
    table = Table.USERS
    columns: tuple[str, ...] = (
        "userid",
        "usedcmds",
        "bio",
        "blacklisted",
        "msgtracking",
    )

    def __init__(self, database: Database, /, data: UserData) -> None:
        self.data: UserData = data
        self.database: Database = database

        self.user_id: int = _handle_null_or_int(data["userid"])  # type: ignore
        self.used_commands: int = _handle_varchar(data["usedcmds"])
        self.bio: Optional[str] = _handle_varchar(data["bio"])
        self.is_blacklisted: bool = _handle_varchar(data["blacklisted"])
        self.message_tracking: bool = _handle_varchar(data["msgtracking"])

    async def modify(
        self,
        *,
        usedcmds: Optional[int] = None,
        bio: Optional[str] = None,
        blacklisted: Optional[bool] = None,
        msgtracking: Optional[bool] = None,
    ) -> User:
        kwargs = {}
        if usedcmds is not None:
            kwargs["usedcmds"] = usedcmds
        if bio is not None:
            kwargs["bio"] = bio
        if blacklisted is not None:
            kwargs["blacklisted"] = str(blacklisted).lower()
        if msgtracking is not None:
            kwargs["msgtracking"] = msgtracking

        return await Base.handle_execute(
            self, where={"userid": str(self.user_id)}, **kwargs
        )


class Command(Base):
    table = Table.COMMANDS
    columns: tuple[str, ...] = ("guild",)

    def __init__(self, database: Database, /, *, name: str) -> None:
        self.name: str = name
        self.columns = self.columns + (name,)

        self.database: Database = database

        self.states: dict[int, Optional[str]] = {}
        self.data = {self.name: self.states, "placeholder": self.name}

    @staticmethod
    def _handle_state_bool(value: Optional[str]) -> Optional[bool]:
        return None if value is None else value == "true"

    async def fill_guild_ids(self) -> None:
        query = f"SELECT guild, commands.{self.name} FROM {self.table}"
        data = await self.database.fetch(query)
        for entry in data:
            guild_id = entry["guild"]
            self.states[int(guild_id)] = entry.get(self.name)

    def state_in(self, guild_id: int) -> Optional[bool]:
        guild_command = self.states.get(guild_id)
        return self._handle_state_bool(guild_command)

    async def modify(
        self,
        guild_id: int,
        state: Optional[bool] = None,
    ) -> Self:
        query = f"UPDATE {self.table} SET {self.name} = $1 WHERE guild = $2 RETURNING *"

        values = [str(state).lower()
                  if state is not None else None, str(guild_id)]
        data = await self.database.fetchrow(query, *values)
        self.states[guild_id] = data[self.name]  # type: ignore
        inst = self.__class__(self.database, name=self.name)  # type: ignore
        await inst.fill_guild_ids()
        self.database._commands[self.name] = inst
        return inst


class Guild(Base):
    table = Table.GUILDS
    columns: tuple[str, ...] = ("hentaichannel", "prefix", "chatbotchannel")

    def __init__(self, database: Database, /, data: GuildData) -> None:
        self.data: GuildData = data
        self.database: Database = database

        self.id: int = _handle_varchar(data["guildid"])
        self.hentai_channel_id: Optional[int] = _handle_varchar(
            data["hentaichannel"])
        self.prefix: Optional[str] = data["prefix"]
        self.chatbot_channel_id: Optional[int] = _handle_varchar(
            data["chatbotchannel"])

    async def modify(
        self,
        *,
        hentai_channel_id: Optional[int] = MISSING,
        prefix: Optional[Any] = MISSING,
        chatbot_channel_id: Optional[int] = MISSING,
    ) -> Guild:
        kwargs = {}
        if hentai_channel_id is not MISSING:
            kwargs["hentaichannel"] = (
                str(hentai_channel_id) if hentai_channel_id is not None else None
            )
        if prefix is not MISSING:
            kwargs["prefix"] = str(prefix) if prefix is not None else None

        if chatbot_channel_id is not MISSING:
            kwargs["chatbotchannel"] = (
                str(chatbot_channel_id) if chatbot_channel_id is not None else None
            )
        return await Base.handle_execute(
            self, where={"guildid": str(self.id)}, **kwargs
        )


class AutoMod(Base):
    table = Table.AUTOMOD
    columns: tuple[str, ...] = ("server", "log")

    def __init__(self, database: Database, /, data: AutoModData) -> None:
        self.data: AutoModData = data
        self.database: Database = database

        self.guild_id: int = _handle_varchar(data["server"])
        self.log_channel_id: Optional[int] = _handle_varchar(data["log"])

    async def modify(
        self,
        *,
        log: Optional[int] = MISSING,
    ) -> AutoMod:
        kwargs = {}
        if log is not MISSING:
            kwargs["log"] = str(log) if log is not None else None

        return await Base.handle_execute(
            self, where={"server": self.guild_id}, **kwargs
        )


class AutoPosting(Base):
    table = Table.AUTOPOSTING
    columns: tuple[str, ...] = (
        "guild_id",
        "hentai_id",
    )

    def __init__(self, database: Database, /, data: AutoPostingData) -> None:
        self.data: AutoPostingData = data
        self.database: Database = database

        self.guild_id: int = int(data["guild_id"])
        self.hentai_id: Optional[int] = _handle_varchar(data["hentai_id"])

    async def modify(
        self,
        *,
        hentai_id: Optional[int] = MISSING,
    ) -> AutoPosting:
        kwargs = {}
        if hentai_id is not MISSING:
            kwargs["hentai_id"] = str(
                hentai_id) if hentai_id is not None else None

        return await Base.handle_execute(
            self, where={"guild_id": str(self.guild_id)}, **kwargs
        )


class AutoRole(Base):
    table = Table.AUTOROLES
    columns: tuple[str, ...] = ("role", "enabled")

    def __init__(self, database: Database, /, data: AutoRolesData) -> None:
        self.data: AutoRolesData = data
        self.database: Database = database

        self.role_id: int = _handle_varchar(data["role"])
        self.enabled: bool = _handle_varchar(data["enabled"])

    async def modify(
        self,
        *,
        enabled: bool,
    ) -> AutoRole:
        return await Base.handle_execute(
            self, where={"role": self.role_id}, enabled=enabled
        )


class Badge(Base):
    table = Table.BADGES
    columns: tuple[str, ...] = ()

    def __init__(self, database: Database, /, *, name: str) -> None:
        self.database: Database = database

        self.name: str = name
        self.users: dict[int, bool] = {}

    async def fill_users_ids(self) -> None:
        query = f"SELECT userid, {self.name} FROM {self.table}"
        data = await self.database.fetch(query)
        for entry in data:
            user_id = entry["userid"]
            self.users[int(user_id)] = _handle_varchar(entry[self.name])

    def has_badge(self, user_id: int) -> bool:
        return self.users.get(user_id, False)

    async def modify(
        self,
        user_id: int,
        state: Optional[bool] = None,
    ) -> Self:
        query = (
            f"UPDATE {self.table} SET {self.name} = $1 WHERE userid = $2 RETURNING *"
        )

        values = [str(state).lower() if state else None, str(user_id)]
        data = await self.database.fetchrow(query, *values)
        self.users[user_id] = data[self.name]  # type: ignore
        return self


class Blacklist(Base):
    table = Table.BLACKLIST
    columns: tuple[str, ...] = (
        "userid", "blacklisted", "blacklistedtill", "reason")

    def __init__(self, database: Database, /, data: BlacklistData) -> None:
        self.data: BlacklistData = data
        self.database: Database = database

        self.user_id: int = _handle_varchar(data["userid"])
        self.is_blacklisted: bool = _handle_varchar(data["blacklisted"])
        self.blacklistedtill: Optional[str] = _handle_varchar(
            data["blacklistedtill"])
        self.reason: Optional[str] = _handle_varchar(data["reason"])

    async def modify(
        self,
        *,
        blacklisted: Optional[bool] = MISSING,
        blacklistedtill: Optional[int] = MISSING,
        reason: Optional[str] = MISSING,
    ) -> Blacklist:
        kwargs = {}
        if blacklisted is not MISSING:
            kwargs["blacklisted"] = (
                str(blacklisted).lower() if blacklisted is not None else None
            )
        if blacklistedtill is not MISSING:
            if blacklistedtill is not None:
                from Cogs.Utils import create_blacklist_date

                blacklistdate = create_blacklist_date(blacklistedtill)
            else:
                blacklistdate = None
            kwargs["blacklistedtill"] = blacklistdate
        if reason is not MISSING:
            kwargs["reason"] = str(reason) if reason is not None else None
        return await Base.handle_execute(
            self, where={"userid": str(self.user_id)}, **kwargs
        )


class GuildBlacklist(Base):
    table = Table.GUILDBLACKLIST
    columns: tuple[str, ...] = ("id", "name", "blacklisted")

    def __init__(self, database: Database, /, data: GuildBlacklistData) -> None:
        self.data: GuildBlacklistData = data
        self.database: Database = database

        self.id: int = _handle_varchar(data["id"])
        self.name: str = _handle_varchar(data["name"])
        self.is_blacklisted: bool = _handle_varchar(data["blacklisted"])

    async def modify(
        self,
        *,
        where: dict[str, Any] = None,
        name: Optional[str] = MISSING,
        blacklisted: Optional[bool] = MISSING,
    ) -> GuildBlacklist:
        if where is None:
            where = {}
        where = where or {"id": str(self.guild_id)}
        kwargs = {}
        if name is not MISSING:
            kwargs["name"] = str(name) if name is not None else None
        if blacklisted is not MISSING:
            kwargs["blacklisted"] = (
                str(blacklisted).lower() if blacklisted is not None else None
            )

        return await Base.handle_execute(self, where=where, **kwargs)


#         self.user_id: int = _handle_varchar(data["user"])
#         self.length: str = _handle_varchar(data["length"])
#         self.reminder: Optional[str] = _handle_varchar(data["reminder"])


class Status(Base):
    table = Table.STATUS
    columns: tuple[str, ...] = ("id", "status")

    def __init__(self, database: Database, /, data: StatusData) -> None:
        self.data: StatusData = data
        self.database: Database = database

        self.id: int = _handle_varchar(data["id"])
        self.status: str = _handle_varchar(data["status"])

    async def modify(self, status: str, *, where: dict[str, Any] = None) -> Status:
        if where is None:
            where = {}
        where = where or {"id": self.id}
        return await Base.handle_execute(self, where=where, status=status)


class GlobalVar(Base):
    table = Table.GLOBALVARS
    columns: tuple[str, ...] = (
        "variableName", "variableData", "variableData2")

    def __init__(self, database: Database, /, data: GlobalVarsData) -> None:
        self.data: GlobalVarsData = data
        self.database: Database = database

        self.variableName: str = _handle_varchar(data["variableName"])
        self.variableData: float = _handle_varchar(data["variableData"])
        self.variableData2: Any = _handle_varchar(data["variableData2"])

    async def modify(
        self,
        *,
        variableData: Optional[float] = None,
        variableData2: Optional[Any] = MISSING,
    ) -> GlobalVar:
        kwargs = {}
        if variableData is not None:
            kwargs["variableData"] = float(variableData)
        if variableData2 is not MISSING:
            kwargs["variableData2"] = (
                str(variableData2) if variableData2 is not None else None
            )
        return await Base.handle_execute(
            self, where={"variableName": self.variableName}, **kwargs
        )


table_to_cls: dict[Table, Any] = {
    Table.AUTOMOD: AutoMod,
    Table.AUTOPOSTING: AutoPosting,
    Table.AUTOROLES: AutoRole,
    Table.BADGES: Badge,
    Table.BLACKLIST: Blacklist,
    Table.COMMANDS: Command,
    Table.GUILDS: Guild,
    Table.GUILDBLACKLIST: GuildBlacklist,
    Table.GLOBALVARS: GlobalVar,
    # Table.REMINDERS: Reminder,
    Table.STATUS: Status,
    Table.USERS: User,
    Table.USER_ECONOMY: UserEconomy,
}
