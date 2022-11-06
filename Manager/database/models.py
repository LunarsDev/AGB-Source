from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Type, TypeVar, Union, get_type_hints

from asyncpg import Record

from ._kwarg_types import AutoMod as AutoModDataKwargs
from ._kwarg_types import AutoRoles as AutoRolesDataKwargs
from ._kwarg_types import Badges as BadgesDataKwargs
from ._kwarg_types import Blacklist as BlacklistDataKwargs
from ._kwarg_types import GuildBlacklist as GuildBlacklistDataKwargs
from ._kwarg_types import Guilds as GuildsDataKwargs
from ._kwarg_types import Reminders as RemindersDataKwargs
from ._kwarg_types import Status as StatusDataKwargs
from ._kwarg_types import UserEco as UserEcoDataKwargs
from ._kwarg_types import Users as UsersDataKwargs
from .types import AutoMod as AutoModData
from .types import AutoRoles as AutoRolesData
from .types import Badges as BadgesData
from .types import Blacklist as BlacklistData
from .types import Commands as CommandsData
from .types import GuildBlacklist as GuildBlacklistData
from .types import Guilds as GuildsData
from .types import Reminders as RemindersData
from .types import Status as StatusData
from .types import UserEco as UserEcoData
from .types import Users as UsersData

if TYPE_CHECKING:
    from datetime import datetime

    from typing_extensions import Self, Unpack

    from .database import Connection, Database


ValidType = Union[
    UserEcoData,
    UsersData,
    GuildsData,
    AutoModData,
    AutoRolesData,
    BadgesData,
    RemindersData,
    StatusData,
    BlacklistData,
    CommandsData,
    GuildBlacklistData,
]


__all__: tuple[str, ...] = (
    "Table",
    "UserEconomy",
    "User",
    "Guild",
    "AutoMod",
    "AutoRole",
    "Badge",
    "Reminder",
    "Status",
    "Blacklist",
    "Command",
    "GuildBlacklist",
)
ReturnC = TypeVar("ReturnC", bound="AGBRecord")


class Table(Enum):
    USERECO = "usereco"
    USERS = "users"
    GUILDS = "guilds"
    AUTOMOD = "automod"
    AUTOROLES = "autoroles"
    BADGES = "badges"
    REMINDERS = "reminders"
    STATUS = "status"
    BLACKLIST = "blacklist"
    COMMANDS = "commands"
    GUILDBLACKLISTS = "guildblacklists"

    def __str__(self) -> str:
        return self.value


class AGBRecordClass(Record):
    def __getattr__(self, name: str) -> Any:
        if self[name] is NotImplemented:
            raise AttributeError(f"{self.__class__.__name__} has no attribute {name}")
        return self[name]


class AGBRecord(Generic[ReturnC]):
    data_dict: Type[ValidType]
    table: Table
    database: Database
    connection: Connection
    original_record: Record
    attrs_aliases: dict[str, str] = {}

    def __init__(
        self,
        connection_database: Union[Connection, Database],
        record: AGBRecordClass,
    ) -> None:
        self.connection: Connection = (
            connection_database.connection  # type: ignore
            if hasattr(connection_database, "connection")
            else connection_database
        )
        self.database: Database = connection_database  # type: ignore
        self.original_record: Record = record

    def __getitem__(self, key: str) -> Any:
        original_record = object.__getattribute__(self, "original_record")
        attrs_aliases = object.__getattribute__(self, "attrs_aliases")
        if key in attrs_aliases:
            key = attrs_aliases[key]

        return original_record.get(key, NotImplemented)

    def __getattr__(self, name: str) -> Any:
        if self[name] is NotImplemented:
            raise AttributeError(f"{self.__class__.__name__} has no attribute {name}")
        return self[name]

    def __repr__(self) -> str:
        return self.original_record.__repr__()

    def __int__(self) -> int:  # yes, this is kinda weird and hacky
        possible_int_keys = ("id", "user_id", "guild_id")
        return next(
            (int(self.original_record[key]) for key in possible_int_keys if key in self.original_record),
            0,
        )

    @staticmethod
    def __handle_column_type(data: ValidType, **inputs: Any) -> None:
        def _handle_type(possible_types: tuple[Any, ...], column: str, value: Any, is_list: bool = False) -> None:
            possible_none: bool = type(None) in possible_types
            can_none = " or None" if possible_none else ""
            if not isinstance(value, possible_types):
                friendly_types = " or ".join(t.__name__ for t in possible_types if t is not type(None))
                if is_list:
                    raise TypeError(
                        f'Expected value of "{column}" to be a list with all items of type {friendly_types}'
                    )

                raise TypeError(
                    f'Expected value of "{column}" to be of type {friendly_types}{can_none}, got {type(value).__name__}'
                )

        typed_dict = get_type_hints(data)
        for column, value in inputs.items():
            _type = typed_dict.get(column)
            if not _type:
                raise TypeError(f"Invalid column {column} for table {data.__class__.__name__}")
            origin = getattr(_type, "__origin__", None)
            if origin is Union:
                _handle_type(_type.__args__, column, value)
            elif origin is list:
                if not isinstance(input, list):
                    raise TypeError(f"{input} must be of type list")
                for item in value:
                    _handle_type((_type.__args__[0],), item, True)  # type: ignore
            else:
                _handle_type((_type,), column, value)

    def __handle_query_inputs(
        self, *, where: dict[str, Any], **kwargs
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        self.__handle_column_type(self.data_dict, **kwargs)  # type: ignore

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

    async def handle_execute(self, *, where: dict[str, Any], **kwargs) -> Record:
        _where, _inputs, _values = self.__handle_query_inputs(where=where, **kwargs)
        where = where or _where
        query = f"UPDATE {self.table} SET {', '.join(f'{key} = {value}' for key, value in _inputs.items())}"
        if _where:
            query += " WHERE " + " AND ".join(f"{key} = {value}" for key, value in _where.items())
        query += " RETURNING *"
        data = await self.database.fetchrow(query, *_values)
        return self.__class__(self.database, data)

    async def modify(self, *args, **kwargs) -> Any:
        return await self.edit(*args, **kwargs)

    async def edit(self, where: Optional[Dict[str, Any]] = None, **kwargs: Optional[Any]) -> ReturnC:
        return await self.handle_execute(where=where or {}, **kwargs)


class UserEconomy(AGBRecord):
    data_dict = UserEcoData
    table = Table.USERECO
    attrs_aliases: dict[str, Any] = {}

    if TYPE_CHECKING:
        userid: int
        balance: int
        bank: int
        lastdaily: Optional[datetime]
        isbot: bool

    async def edit(
        self,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Unpack[UserEcoDataKwargs],
    ) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"userid": self.userid}, **kwargs)


class User(AGBRecord):
    data_dict = UsersData
    table = Table.USERS
    attrs_aliases = {
        "user_id": "userid",
        "is_bot": "isbot",
        "used_commands": "usedcmds",
        "message_tracking": "msgtracking",
    }

    if TYPE_CHECKING:
        userid: int
        isbot: bool
        usedcmds: int
        bio: str
        msgtracking: bool
        todos: List[str]
        # aliases
        user_id: int
        is_bot: bool
        used_commands: int
        message_tracking: bool

    async def edit(
        self,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Unpack[UsersDataKwargs],
    ) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"userid": self.userid}, **kwargs)


class Guild(AGBRecord):
    data_dict = GuildsData
    table = Table.GUILDS
    attrs_aliases = {
        "guild_id": "guildid",
        "hentai_channel_id": "hentaichannel",
        "welcome_channel_id": "welcomer",
    }

    def __init__(self, database: Database, record: Record) -> None:
        super().__init__(database, record)

    if TYPE_CHECKING:
        guildid: int
        hentaichannel: Optional[int]
        prefix: str
        welcomer: Optional[int]
        # aliases
        guild_id: int
        hentai_channel_id: Optional[int]
        welcome_channel_id: Optional[int]

    async def edit(self, where: Optional[Dict[str, Any]] = None, **kwargs: Unpack[GuildsDataKwargs]) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"guildid": self.guildid}, **kwargs)


class AutoMod(AGBRecord):
    data_dict = AutoModData
    table = Table.AUTOMOD
    attrs_aliases = {"guild_id": "guildid", "log_channel_id": "logchannelid"}

    if TYPE_CHECKING:
        guildid: int
        logchannelid: Optional[int]
        # aliases
        guild_id: int
        log_channel_id: Optional[int]

    async def edit(
        self,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Unpack[AutoModDataKwargs],
    ) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"guildid": self.guildid}, **kwargs)


class AutoRole(AGBRecord):
    data_dict = AutoRolesData
    table = Table.AUTOROLES
    attrs_aliases = {"guild_id": "guildid", "roles": "roleids"}

    if TYPE_CHECKING:
        guildid: int
        roleids: Optional[List[int]]
        # aliases
        guild_id: int
        roles: Optional[List[int]]

    async def add(self, role_id: int) -> None:
        if self.roleids and role_id in self.roleids:
            return

        if not self.roleids:
            self.roleids = [role_id]
        else:
            self.roleids.append(role_id)
        await self.database.execute(
            f"UPDATE {self.table} SET roleids = array_append(roleids, $1) WHERE guildid = $2",
            role_id,
            self.guild_id,
        )

    async def remove(self, role_id: int) -> None:
        if not self.roleids or role_id not in self.roleids:
            return

        self.roleids.remove(role_id)
        await self.database.execute(
            f"UPDATE {self.table} SET roleids = array_remove(roleids, $1) WHERE guildid = $2",
            role_id,
            self.guild_id,
        )

    async def edit(
        self,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Unpack[AutoRolesDataKwargs],
    ) -> Self:
        raise NotImplementedError("Use .add/remove instead")


class Badge(AGBRecord):
    data_dict = BadgesData
    table = Table.BADGES

    def __init__(self, name: str, database: Database, record: Record) -> None:
        super().__init__(database, record)
        self.name: str = name
        self.user_ids: list[int] = list(self.original_record[self.name] or [])

    def has(self, user_id: int) -> bool:
        return user_id in self.user_ids

    async def add(self, user_id: int) -> None:
        if user_id in self.user_ids:
            return
        self.user_ids.append(user_id)
        await self.database.execute(
            f"UPDATE {self.table} SET {self.name} = array_append({self.name}, $1)",
            user_id,
        )

    async def remove(self, user_id: int) -> None:
        if user_id not in self.user_ids:
            return
        self.user_ids.remove(user_id)
        await self.database.execute(
            f"UPDATE {self.table} SET {self.name} = array_remove({self.name}, $1)",
            user_id,
        )

    async def edit(self, where: Optional[Dict[str, Any]] = None, **kwargs: Unpack[BadgesDataKwargs]) -> Self:
        raise NotImplementedError("Use .add/remove instead")


class Reminder(AGBRecord):
    data_dict = RemindersData
    table = Table.REMINDERS
    attrs_aliases = {"user_id": "userid"}

    if TYPE_CHECKING:
        id: int
        userid: int
        message: Optional[str]
        time: Optional[datetime]
        # aliases
        user_id: int

    async def edit(
        self,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Unpack[RemindersDataKwargs],
    ) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"id": self.id}, **kwargs)


class Status(AGBRecord):
    data_dict = StatusData
    table = Table.STATUS

    if TYPE_CHECKING:
        id: int
        status: str

    async def edit(self, where: Optional[Dict[str, Any]] = None, **kwargs: Unpack[StatusDataKwargs]) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"id": self.id}, **kwargs)


class Blacklist(AGBRecord):
    data_dict = BlacklistData
    table = Table.BLACKLIST
    attrs_aliases = {
        "user_id": "userid",
        "blacklisted_until": "blacklistedtill",
        "is_blacklisted": "blacklisted",
    }

    if TYPE_CHECKING:
        userid: int
        blacklisted: bool
        blacklistedtill: Optional[str]
        reason: str
        # aliases
        user_id: int
        blacklisted_until: Optional[str]
        is_blacklisted: bool

    async def edit(
        self,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Unpack[BlacklistDataKwargs],
    ) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"userid": self.userid}, **kwargs)


class Command(AGBRecord):
    data_dict = CommandsData
    table = Table.COMMANDS
    attrs_aliases = {"guild_id": "guild"}

    if TYPE_CHECKING:
        guild: int
        # aliases
        guild_id: int

    def __init__(self, database: Database, record: Record) -> None:
        super().__init__(database, record)
        disabled = self.original_record["disabled"]
        if disabled is None:
            self.disabled: list[str] = []
        else:
            self.disabled: list[str] = list(self.original_record["disabled"])

    def is_disabled(self, command_name: str) -> bool:
        return command_name in self.disabled

    async def add(self, command_name: str) -> None:
        if command_name in self.disabled:
            return
        self.disabled.append(command_name)
        await self.database.execute(
            f"UPDATE {self.table} SET disabled = array_append(disabled, $1) WHERE guild = $2",
            command_name,
            self.guild_id,
        )

    async def remove(self, command_name: str) -> None:
        if command_name not in self.disabled:
            return
        self.disabled.remove(command_name)
        await self.database.execute(
            f"UPDATE {self.table} SET disabled = array_remove(disabled, $1) WHERE guild = $2",
            command_name,
            self.guild_id,
        )

    async def edit(
        self,
        command_name: str,
        state: bool,
    ) -> Self:
        if state:
            await self.add(command_name)
        else:
            await self.remove(command_name)
        return self


class GuildBlacklist(AGBRecord):
    data_dict = GuildBlacklistData
    table = Table.GUILDBLACKLISTS
    attrs_aliases = {"guild_id": "id", "is_blacklisted": "blacklisted"}

    if TYPE_CHECKING:
        id: int
        name: str
        blacklisted: bool
        # aliases
        guild_id: int
        is_blacklisted: bool

    async def edit(
        self,
        where: Optional[Dict[str, Any]] = None,
        **kwargs: Unpack[GuildBlacklistDataKwargs],
    ) -> Self:
        return await AGBRecord.handle_execute(self, where=where or {"id": self.id}, **kwargs)


table_to_cls = {
    Table.USERECO: UserEconomy,
    Table.USERS: User,
    Table.GUILDS: Guild,
    Table.AUTOMOD: AutoMod,
    Table.AUTOROLES: AutoRole,
    Table.BADGES: Badge,
    Table.REMINDERS: Reminder,
    Table.STATUS: Status,
    Table.BLACKLIST: Blacklist,
    Table.COMMANDS: Command,
    Table.GUILDBLACKLISTS: GuildBlacklist,
}
