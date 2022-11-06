from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Literal, NoReturn, Optional, Union, get_type_hints, overload

from asyncpg import Pool, create_pool
from utils.errors import DatabaseError

from ..logger import formatColor
from .models import (
    AGBRecord,
    AGBRecordClass,
    AutoMod,
    AutoRole,
    Badge,
    Blacklist,
    Command,
    Guild,
    GuildBlacklist,
    Status,
    Table,
    User,
    UserEconomy,
    table_to_cls,
)
from .types import ValidBadge

if TYPE_CHECKING:
    from asyncpg import Connection as AsyncConnection
    from index import AGB

    from .types import DBConfig

DATABASE_LOGGING_PREFIX = formatColor("[Database]", "green")


class Connection:

    __slots__: tuple[str, ...] = ("bot", "_config", "_pool", "__open_connections")

    def __init__(
        self,
        bot: AGB,
        /,
        config: DBConfig,
    ) -> None:
        self.bot: AGB = bot
        self._config = config
        self._pool: Optional[Pool] = None

        self.__open_connections: list[AsyncConnection] = []

    @property
    def pool(self) -> Pool:
        return self._pool  # type: ignore

    async def create_connection(self) -> None:
        self.__open_connections = []
        if self._pool is not None and not self._pool._closed:
            return

        pool: Pool = await create_pool(
            user=self._config.user,
            password=self._config.password,
            host=self._config.host,
            database=self._config.database,
            port=self._config.port,
            record_class=AGBRecordClass,
        )  # type: ignore
        self._pool = pool

        # circular imports
        from utils.default import log

        log(f"{DATABASE_LOGGING_PREFIX} Successfully created a connection to the database.")

    async def __get_active_connection(self) -> AsyncConnection:
        if len(self.__open_connections) == 0:
            return await self.pool.acquire()
        return self.__open_connections[0]

    async def __close_connections(self, c: Optional[AsyncConnection] = None) -> None:
        with contextlib.suppress(Exception):
            if c and not c.is_closed():
                await self.pool.release(c)
                with contextlib.suppress(ValueError):
                    self.__open_connections.remove(c)
            for connection in self.__open_connections:
                if connection.is_closed():
                    self.__open_connections.remove(connection)

    async def execute(self, query, *args) -> Any:
        con = await self.__get_active_connection()
        try:
            return await con.execute(query, *args)
        except Exception as e:
            raise DatabaseError(e) from e
        finally:
            await self.__close_connections(con)

    async def executemany(self, query, *args) -> Any:
        con = await self.__get_active_connection()
        try:
            return await con.executemany(query, args)
        except Exception as e:
            raise DatabaseError(e) from e
        finally:
            await self.__close_connections(con)

    async def fetch(self, query, *args) -> list[AGBRecordClass]:  # type: ignore
        con = await self.__get_active_connection()
        try:
            return await con.fetch(query, *args)
        except Exception as e:
            raise DatabaseError(e) from e
        finally:
            await self.__close_connections(con)

    async def fetchrow(self, query, *args) -> Optional[AGBRecordClass]:
        con = await self.__get_active_connection()
        try:
            return await con.fetchrow(query, *args)
        except Exception as e:
            raise DatabaseError(e) from e
        finally:
            await self.__close_connections(con)

    async def fetchval(self, query, *args) -> Optional[Any]:
        con = await self.pool.acquire()
        try:
            return await con.fetchval(query, *args)
        except Exception as e:
            raise DatabaseError(e) from e
        finally:
            await self.__close_connections(con)

    async def close(self) -> None:
        if self._pool is None:
            return

        await self._pool.close()
        self._pool = None
        self.__open_connections = []


class Database(Connection):
    def __init__(
        self,
        bot: AGB,
        /,
        config: DBConfig,
    ) -> None:
        super().__init__(bot, config=config)

        # cache

        self._commands: dict[int, Command] = {}
        self._users: dict[int, User] = {}
        self._economy_users: dict[int, UserEconomy] = {}
        self._guilds: dict[int, Guild] = {}
        self._automods: dict[int, AutoMod] = {}
        self._autoroles: dict[int, AutoRole] = {}
        self._badges: dict[str, Badge] = {}
        self._blacklists: dict[int, Blacklist] = {}
        self._guild_blacklists: dict[int, GuildBlacklist] = {}
        self._statuses: dict[int, Status] = {}
        self._reminders: dict[int, AGBRecord] = {}

        self._table_to_cache: dict[Table, tuple[str, dict[Any, Any]]] = {
            Table.USERECO: ("userid", self._economy_users),
            Table.USERS: ("userid", self._users),
            Table.GUILDS: ("guildid", self._guilds),
            Table.AUTOMOD: ("guildid", self._automods),
            Table.AUTOROLES: ("guildid", self._autoroles),
            Table.BADGES: ("name", self._badges),
            Table.REMINDERS: ("id", self._reminders),
            Table.STATUS: ("id", self._statuses),
            Table.BLACKLIST: ("userid", self._blacklists),
            Table.COMMANDS: ("guild", self._commands),
            Table.GUILDBLACKLISTS: ("id", self._blacklists),
        }

    def __repr__(self) -> str:
        cache_totals = " ".join(
            f"{t.name.title()}: {len(cache.values())}" for t, (_, cache) in self._table_to_cache.items()
        )
        return f"{self.__class__.__name__}({cache_totals})"

    def _add_to_cache(self, table: Table, class_instance: Any) -> None:
        cache_key, cache_dict = self._table_to_cache[table]
        typed_dict = table_to_cls[table].data_dict
        cast_to = get_type_hints(typed_dict)[cache_key]

        cache_key_value = getattr(class_instance, cache_key)
        cache_dict[cast_to(cache_key_value)] = class_instance

    async def initate_database(self, *, chunk: bool = True) -> None:
        # circular imports
        from utils.default import log

        log(f"{DATABASE_LOGGING_PREFIX} Initializing database...")
        await self.create_connection()
        if chunk:
            log(f"{DATABASE_LOGGING_PREFIX} Chunking database...")
            await self.chunk(commands=True)
            log(f"{DATABASE_LOGGING_PREFIX} Chunking database... Done!")

        log(f"{DATABASE_LOGGING_PREFIX} Database initialized.")

    async def chunk(
        self,
        *,
        auto_mod: bool = False,
        auto_roles: bool = False,
        badges: bool = False,
        blacklists: bool = False,
        commands: bool = False,
        guilds: bool = False,
        statuses: bool = False,
        users: bool = False,
        user_economy: bool = False,
    ) -> None:
        # circular imports
        from utils.default import log

        to_chunk = (
            ("Auto Mod", auto_mod, self.fetch_automods),
            ("Auto Roles", auto_roles, self.fetch_autoroles),
            ("Badges", badges, self.fetch_badges),
            ("Blacklists", blacklists, self.fetch_blacklists_table),
            ("Commands", commands, self.fetch_commands),
            ("Guilds", guilds, self.fetch_guilds),
            ("Statuses", statuses, self.fetch_statuses),
            ("Users", users, self.fetch_users),
            ("Users Economy", user_economy, self.fetch_economy_users),
        )
        for (pretty_name, to_chunk, to_call) in to_chunk:
            should_chunk = to_chunk
            if should_chunk is True:
                prefix: str = f"{DATABASE_LOGGING_PREFIX} Chunking {pretty_name}..."
                log(prefix)
                objs = await to_call(cache=True)
                log(f"{prefix} Done! Fetched and cached {len(objs)} entries.")

    @overload
    async def getch(self, table: Literal[Table.USERECO, "usereco", "USERECO"], key: int) -> Optional[UserEconomy]:
        ...

    @overload
    async def getch(self, table: Literal[Table.USERS, "users", "USERS"], key: int) -> Optional[User]:
        ...

    @overload
    async def getch(self, table: Literal[Table.GUILDS, "guilds", "GUILDS"], key: int) -> Optional[Guild]:
        ...

    @overload
    async def getch(self, table: Literal[Table.AUTOMOD, "automod", "AUTOMOD"], key: int) -> Optional[AutoMod]:
        ...

    @overload
    async def getch(self, table: Literal[Table.USERECO, "autoroles", "USERECO"], key: int) -> Optional[AutoRole]:
        ...

    @overload
    async def getch(self, table: Literal[Table.USERECO, "badges", "USERECO"], key: str) -> Optional[Badge]:
        ...

    @overload
    async def getch(self, table: Literal[Table.REMINDERS, "reminders", "REMINDERS"], key: Any) -> NoReturn:
        ...

    @overload
    async def getch(self, table: Literal[Table.STATUS, "status", "STATUS"], key: int) -> Optional[Status]:
        ...

    @overload
    async def getch(self, table: Literal[Table.BLACKLIST, "blacklist", "BLACKLIST"], key: int) -> Optional[Blacklist]:
        ...

    @overload
    async def getch(self, table: Literal[Table.COMMANDS, "commands", "COMMANDS"], key: int) -> Optional[Command]:
        ...

    @overload
    async def getch(
        self,
        table: Literal[Table.GUILDBLACKLISTS, "guildblacklists", "guildblacklists"],
        key: int,
    ) -> Optional[GuildBlacklist]:
        ...

    async def getch(self, table: Union[str, Table], key: Any) -> Optional[AGBRecord[Any]]:
        """Get or fetch a record from the database without any error being raised.

        Parameters
        ----------
        table : Table
            The table to fetch from.
        key : Any
            The key to fetch from.

        Returns
        -------
        Optional[:class:`AGBRecord`]
            The related record wrapped in the related class.
        """

        def get_enum() -> Optional[Table]:
            if table is Table:
                return table  # type: ignore
            elif isinstance(table, str):
                try:
                    return Table[table]
                except KeyError:
                    try:
                        return Table(table)
                    except ValueError:
                        return None
            else:
                raise TypeError(f"Expected Table or str, got {type(table)}")

        actual_table = get_enum()
        if actual_table is None:
            raise ValueError(f"Invalid table: {str(table)}")

        primary_key, cache_dict = self._table_to_cache[actual_table]
        table_to_method = {
            Table.USERECO: self.fetch_economy_user,
            Table.USERS: self.fetch_user,
            Table.GUILDS: self.fetch_guild,
            Table.AUTOMOD: self.fetch_automod,
            Table.AUTOROLES: self.fetch_autorole,
            Table.BADGES: self.fetch_badge,
            Table.STATUS: self.fetch_status,
            Table.BLACKLIST: self.fetch_blacklist,
            Table.COMMANDS: self.fetch_command,
            Table.GUILDBLACKLISTS: self.fetch_guild_blacklist,
        }
        cls = table_to_cls[actual_table]
        data_types = get_type_hints(cls.data_dict)
        if not isinstance(key, data_types[primary_key]):
            raise TypeError(f"Key must be of type {data_types[primary_key]} for table {actual_table.name}")

        if not (record := cache_dict.get(key)):
            try:
                record = await table_to_method[actual_table](key)
            except DatabaseError:
                return None

        return record

    @overload
    async def __fetch(self, table: Table, cache: Any, where: Literal[None] = ..., fetch_one: Any = ...) -> list[Any]:
        ...

    @overload
    async def __fetch(self, table: Table, cache: Any, where: Any, fetch_one: Literal[True] = ...) -> Optional[Any]:
        ...

    @overload
    async def __fetch(self, table: Table, cache: Any, where: Any, fetch_one: Literal[False] = ...) -> list[Any]:
        ...

    async def __fetch(
        self,
        table: Table,
        cache: bool = False,
        where: Optional[dict[str, Any]] = None,
        fetch_one: Optional[bool] = None,
    ) -> Union[list[Any], Optional[Any]]:
        """
        Fetch objects from the database.

        Parameters
        ----------
        table: Table
            The table to fetch from.
        cache: Optional[bool]
            Whether to cache the results.
        where: Optional[dict[str, Any]]
            The where clause to use.
        fetch_one: bool
            Whether to fetch one or many. This is ``True`` if `where` is not ``None``
            unless it's explicitly set to ``False``.
        """
        query = f"SELECT * FROM {table.value}"
        cls = table_to_cls[table]
        values = tuple(where.values()) if where else ()

        if fetch_one is None:
            fetch_one = where is not None

        if where is not None:
            query += " WHERE " + " AND ".join(f"{k} = ${i}" for i, (k, v) in enumerate(where.items(), start=1))

        if fetch_one is True:
            data = await self.fetchrow(query, *values)
            if data is None:
                return None

            inst = cls(self, data)
            if cache:
                self._add_to_cache(table, inst)

            return inst

        to_ret = []
        data = await self.fetch(query, *values)
        for entry in data:
            if not entry:
                continue
            inst = cls(self, entry)
            if cache:
                self._add_to_cache(table, inst)
            to_ret.append(inst)

        return to_ret

    # economy ---

    @property
    def economy_users(self) -> list[UserEconomy]:
        """List[:class:`UserEconomy`]: The cached economy users."""
        return list(self._economy_users.values())

    async def add_economy_user(
        self, user_id: int, *, balance: int = 500, bank: int = 500, cache: bool = False
    ) -> UserEconomy:
        """Add a user to the economy table.

        Parameters
        ----------
        user_id: int
            ID of the user to add.
        balance: int
            The balance to set. Defaults to 500.
        bank: int
            The bank amount to set. Defaults to 500.
        cache: bool
            Whether to cache the user. Defaults to ``False``.

        Returns
        -------
        :class:`UserEconomy`
            Object representing the added economy user.
        """
        query = f"INSERT INTO {Table.USERECO} (userid, balance, bank) VALUES ($1, $2, $3) RETURNING *"
        data = await self.fetchrow(query, user_id, balance, bank)
        inst = UserEconomy(self, data)
        if cache:
            self._economy_users[user_id] = inst
        return inst

    async def remove_economy_user(self, user_id: int) -> Optional[UserEconomy]:
        """Remove a user from the economy table.

        Parameters
        ----------
        user_id: int
            ID of the user to remove.

        Returns
        -------
        Optional[:class:`UserEconomy`]
            Object representing the removed economy user. If found in cache else ``None``.
        """
        query = f"DELETE FROM {Table.USERECO} WHERE userid = $1"
        await self.execute(query, user_id)
        return self._economy_users.pop(user_id, None)

    def get_economy_user(self, user_id: int) -> Optional[UserEconomy]:
        """Get an economy user from the cache.

        Parameters
        ----------
        user_id: int
            ID of the user to get.

        Returns
        -------
        Optional[:class:`UserEconomy`]
            Object representing the economy user. If found in cache else ``None``.
        """
        return self._economy_users.get(user_id)

    async def fetch_economy_users(self, cache: bool = False) -> list[UserEconomy]:
        """Fetch all economy users from the database.

        Parameters
        ----------
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        list[:class:`UserEconomy`]
            List of objects representing the economy users.
        """
        return await self.__fetch(Table.USERECO, cache=cache)

    async def fetch_economy_user(self, user_id: int, cache: bool = False) -> Optional[UserEconomy]:
        """Fetch an economy user from the database.

        Parameters
        ----------
        user_id: int
            ID of the user to fetch.
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        Optional[:class:`UserEconomy`]
            Object representing the economy user.
        """
        return await self.__fetch(Table.USERECO, cache=cache, where={"userid": user_id})

    # users ---

    @property
    def users(self) -> list[User]:
        """List[:class:`User`]: The cached users."""
        return list(self._users.values())

    async def add_user(self, user_id: int, cache: bool = False) -> User:
        """Add a user to the users table.

        Parameters
        ----------
        user_id: int
            ID of the user to add.
        cache: bool
            Whether to cache the user. Defaults to ``False``.

        Returns
        -------
         :class:`User`
            Object representing the added user.
        """
        query = f"INSERT INTO {Table.USERS} (userid) VALUES ($1) RETURNING *"
        data = await self.fetchrow(query, user_id)
        inst = User(self, data)
        if cache:
            self._users[user_id] = inst

        return inst

    async def remove_user(self, user_id: int) -> Optional[User]:
        """Remove a user from the users table.

        Parameters
        ----------
        user_id: int
            ID of the user to remove.

        Returns
        -------
        Optional[:class:`User`]
            Object representing the removed user. If found in cache else ``None``.
        """
        query = f"DELETE FROM {Table.USERS} WHERE userid = $1"
        await self.execute(query, user_id)
        return self._users.pop(user_id, None)

    def get_user(self, user_id: int) -> Optional[User]:
        """Get a user from the cache.

        Parameters
        ----------
        user_id: int
            ID of the user to get.

        Returns
        -------
        Optional[:class:`User`]
            Object representing the user. If found in cache else ``None``.
        """
        return self._users.get(user_id)

    async def fetch_users(self, cache: bool = False) -> list[User]:
        """Fetch all users from the database.

        Parameters
        ----------
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        list[:class:`User`]
            List of objects representing the users.
        """
        return await self.__fetch(Table.USERS, cache=cache)

    async def fetch_user(self, user_id: int, cache: bool = False) -> User:
        """Fetch a user from the database.

        Parameters
        ----------
        user_id: int
            ID of the user to fetch.
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        :class:`User`
            Object representing the user.
        """
        return await self.__fetch(Table.USERS, cache=cache, where={"userid": user_id})  # type: ignore

    # guilds ---

    @property
    def guilds(self) -> list[Guild]:
        """List[:class:`Guild`]: The cached guilds."""
        return list(self._guilds.values())

    async def add_guild(self, guild_id: int, cache: bool = False) -> Guild:
        """Add a guild to the guilds table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to add.
        cache: bool
            Whether to cache the guild. Defaults to ``False``.

        Returns
        -------
        :class:`Guild`
            Object representing the added guild.
        """
        query = f"INSERT INTO {Table.GUILDS} (guildid) VALUES ($1) RETURNING *"
        data = await self.fetchrow(query, guild_id)
        inst = Guild(self, data)
        if cache:
            self._guilds[guild_id] = inst
        return inst

    async def remove_guild(self, guild_id: int) -> Optional[Guild]:
        """Remove a guild from the guilds table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to remove.

        Returns
        -------
        Optional[:class:`Guild`]
            Object representing the removed guild. If found in cache else ``None``.
        """
        query = f"DELETE FROM {Table.GUILDS} WHERE guildid = $1"
        await self.execute(query, guild_id)
        return self._guilds.pop(guild_id, None)

    def get_guild(self, guild_id: int) -> Optional[Guild]:
        """Get a guild from the cache.

        Parameters
        ----------
        guild_id: int
            ID of the guild to get.

        Returns
        -------
        Optional[:class:`Guild`]
            Object representing the guild. If found in cache else ``None``.
        """
        return self._guilds.get(guild_id)

    async def fetch_guilds(self, cache: bool = False) -> list[Guild]:
        """Fetch all guilds from the database.

        Parameters
        ----------
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        list[:class:`Guild`]
            List of objects representing the guilds.
        """
        return await self.__fetch(Table.GUILDS, cache=cache)

    async def fetch_guild(self, guild_id: int, cache: bool = False) -> Optional[Guild]:
        """Fetch a guild from the database.

        Parameters
        ----------
        guild_id: int
            ID of the guild to fetch.
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        Optional[:class:`Guild`]
            Object representing the guild.
        """
        return await self.__fetch(Table.GUILDS, cache=cache, where={"guildid": guild_id})

    # automod ---

    async def add_automod(self, guild_id: int, log_channel_id: Optional[int] = None, cache: bool = False) -> AutoMod:
        """Add an auto moderation entry to the automod table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to add.
        log_channel_id: Optional[int]
            ID of the log channel to add. Defaults to ``None``.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.

        Returns
        -------
        :class:`AutoMod`
            Object representing the added entry.
        """
        query = f"INSERT INTO {Table.AUTOMOD} (guildid) VALUES ($1) RETURNING *"
        args = (guild_id,)
        if log_channel_id is not None:
            query = "INSERT INTO automod (guildid, logchannelid) VALUES ($1, $2)"
            args += (log_channel_id,)

        query = f"{query} RETURNING *"
        data = await self.fetchrow(query, *args)

        inst = AutoMod(self, data)
        if cache:
            self._automods[guild_id] = inst
        return inst

    async def remove_automod(self, guild_id: int) -> Optional[AutoMod]:
        """Remove an auto moderation entry from the automod table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to remove.

        Returns
        -------
        Optional[:class:`AutoMod`]
            Object representing the removed entry. If found in cache else ``None``.
        """
        query = f"DELETE FROM {Table.AUTOMOD} WHERE guildid = $1"
        await self.execute(query, guild_id)
        return self._automods.pop(guild_id, None)

    def get_automod(self, guild_id: int) -> Optional[AutoMod]:
        """Optional[:class:`AutoMod`]: Get an auto moderation entry from the cache."""
        return self._automods.get(guild_id)

    async def fetch_automods(self, cache: bool = False) -> list[AutoMod]:
        return await self.__fetch(Table.AUTOMOD, cache=cache)

    async def fetch_automod(self, guild_id: int, cache: bool = False) -> Optional[AutoMod]:
        return await self.__fetch(Table.AUTOMOD, cache=cache, where={"guildid": str(guild_id)})

    # autoroles ---

    async def add_autorole(self, guild_id: int, role_ids: list[int], cache: bool = False) -> AutoRole:
        """Add an auto role entry to the autoroles table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to add.
        role_ids: list[int]
            List of role IDs to add.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.

        Returns
        -------
        :class:`AutoRole`
            Object representing the added entry.
        """
        query = f"INSERT INTO {Table.AUTOROLES} (guildid, roleids) VALUES ($1, $2) RETURNING *"
        data = await self.fetchrow(query, guild_id, role_ids)
        inst = AutoRole(self, data)
        if cache:
            self._autoroles[guild_id] = inst
        return inst

    async def remove_autorole(self, guild_id: int) -> Optional[AutoRole]:
        """Remove an auto role entry from the autoroles table.

        Parameters
        ----------
        role_id: int
            ID of the role to remove.

        Returns
        -------
        Optional[:class:`AutoRole`]
            Object representing the removed entry. If found in cache else ``None``.
        """
        query = f"DELETE FROM {Table.AUTOROLES} WHERE guild_id = $1"
        await self.execute(query, guild_id)
        return self._autoroles.pop(guild_id, None)

    def get_autorole(self, role_id: int) -> Optional[AutoRole]:
        return self._autoroles.get(role_id)

    async def fetch_autoroles(self, cache: bool = False) -> list[AutoRole]:
        """Fetch all auto roles from the database.

        Parameters
        ----------
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        list[:class:`AutoRole`]
            List of objects representing the auto roles.
        """
        return await self.__fetch(Table.AUTOROLES, cache=cache)

    async def fetch_autorole(self, guild_id: int, cache: bool = False) -> Optional[AutoRole]:
        """Fetch an auto role entry from the database.

        Parameters
        ----------
        guild_id: int
            ID of the guild to fetch.
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        Optional[:class:`AutoRole`]
            Object representing the auto role.
        """
        return await self.__fetch(Table.AUTOROLES, cache=cache, where={"guildid": guild_id})

    # badges ---

    @property
    def badges(self) -> list[Badge]:
        """List[:class:`Badge`]: The cached badges."""
        return list(self._badges.values())

    async def add_badge(self, badge: str, user_ids: Optional[list[int]] = None, cache: bool = False) -> Badge:
        """Add a badge to the badges table.
        Make sure to add the badge to the ValidBadge list.

        Parameters
        ----------
        badge: str
            Name of the badge to add.
        user_id: int
            ID of the user to add.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.

        Returns
        -------
        :class:`Badge`
            Object representing the added badge.
        """
        query = f"INSERT INTO {Table.BADGES} (badge) VALUES ($1) RETURNING *"
        data = await self.fetchrow(query, badge)
        inst = Badge(badge, self, data)
        if user_ids:
            for user_id in user_ids:
                await inst.add(user_id)

        if cache:
            self._badges[inst.id] = inst
        return inst

    async def remove_badge(self, badge: ValidBadge) -> Optional[Badge]:
        """Remove a badge from the badges table.
        Make sure to remove the badge from the ValidBadge list.

        Parameters
        ----------
        badge: Union[:class:`Badge`, int, str]
            Badge to remove.

        Returns
        -------
        :class:`Badge`
            Object representing the removed badge. If found in cache else ``None``.
        """
        query = f"ALTER TABLE {Table.BADGES} DROP COLUMN {badge}"
        await self.execute(query)
        return self._badges.pop(badge, None)

    def get_badge(self, badge: ValidBadge) -> Optional[Badge]:
        """Get a badge from the cache.

        Parameters
        ----------
        badge: Literal["owner", "admin", "mod", "partner", "support", "friend"]
            The badge to get. Must be one of `owner`, `admin`,`"mod`, `partner`, `support`, `friend`

        Returns
        -------
        Optional[:class:`Badge`]
            Object representing the badge. If found in cache else ``None``.
        """
        return self._badges.get(badge)

    async def fetch_badges(self, cache: bool = False) -> list[Badge]:
        """Fetch all badges from the database.

        Parameters
        ----------
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        list[:class:`Badge`]
            List of objects representing the badges.
        """
        query = f"SELECT * FROM {Table.BADGES}"
        data = await self.fetchrow(query)
        if not data:
            return []

        to_return: dict[str, Badge] = {}
        for name, value in data.items():
            # don't need it.
            if name == "userid":
                continue

            inst = Badge(name, self, data)
            to_return[name] = inst

        if cache:
            self._badges = to_return

        return list(to_return.values())

    async def fetch_badge(self, badge: ValidBadge, cache: bool = False) -> Optional[Badge]:
        """Fetch a badge from the database.

        Parameters
        ----------
        badge: Literal["owner", "admin", "mod", "partner", "support", "friend"]
            The badge to fetch. Must be one of `owner`, `admin`,`"mod`, `partner`, `support`, `friend`
        cache: bool
            Whether to cache the results. Defaults to ``False``.

        Returns
        -------
        Optional[:class:`Badge`]
            Object representing the badge.
        """
        query = f"SELECT {badge} FROM {Table.BADGES}"
        data = await self.fetchrow(query, badge)
        if not data:
            return None

        inst = Badge(badge, self, data)
        if cache:
            self._badges[badge] = inst

        return inst

    # reminders --- TODO: ....
    # ....

    # status

    @property
    def statuses(self) -> list[Status]:
        """List[:class:`Status`]: The cached statuses."""
        return list(self._statuses.values())

    async def add_status(self, status: str, cache: bool = False) -> Status:
        query = f"INSERT INTO {Table.STATUS} (status) VALUES ($1) RETURNING *"
        data = await self.fetchrow(query, status)
        inst = Status(self, data)
        if cache:
            self._statuses[data["id"]] = inst  # type: ignore
        return inst

    async def remove_status(self, status_id: int) -> Optional[Status]:
        query = f"DELETE FROM {Table.STATUS} WHERE id = $1"
        await self.execute(query, status_id)
        return self._statuses.pop(status_id, None)

    def get_status(self, status_id: int) -> Optional[Status]:
        return self._statuses.get(status_id)

    async def fetch_statuses(self, cache: bool = False) -> list[Status]:
        return await self.__fetch(Table.STATUS, cache=cache)

    async def fetch_status(self, status_id: int, cache: bool = False) -> Optional[Status]:
        return await self.__fetch(Table.STATUS, cache=cache, where={"id": status_id})

    # blacklist ---

    @property
    def blacklisted_users(self) -> list[Blacklist]:
        """List[:class:`Blacklist`]: The cached blacklisted users."""
        return list(self._blacklisted_users.values())

    async def add_blacklist(
        self,
        user_id: int,
        blacklisted: bool = False,
        blacklistedtill: Optional[int] = None,
        reason: Optional[str] = None,
        cache: bool = False,
    ) -> Blacklist:
        """Add a user to the blacklist table.

        Parameters
        ----------
        user_id: int
            ID of the user to add.
        blacklisted: bool
            Whether the user is blacklisted. Defaults to ``False``.
        blacklistedtill: Optional[int]
            When the user will be unblacklisted. Defaults to ``None``.
        reason: Optional[str]
            Reason for blacklisting the user. Defaults to ``None``.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.

        Returns
        -------
        :class:`Blacklist`
            Object representing the added user.
        """
        if blacklistedtill:
            return await self.add_temp_blacklist(user_id, blacklistedtill, reason, cache=cache)
        query = f"INSERT INTO {Table.BLACKLIST} (userid, blacklisted) VALUES ($1, $2) RETURNING *"

        args = (user_id, blacklisted)
        if reason is not None:
            query = f"INSERT INTO {Table.BLACKLIST} (userid, blacklisted, reason) VALUES ($1, $2, $3) RETURNING *"
            args += (reason,)

        data = await self.fetchrow(query, *args)
        inst = Blacklist(self, data)
        if cache:
            self._blacklists[user_id] = inst
        return inst

    async def add_temp_blacklist(
        self,
        user_id: int,
        days: Optional[int] = None,
        reason: Optional[str] = None,
        cache: bool = False,
    ) -> Blacklist:
        from Cogs.Utils import create_blacklist_date

        blacklistdate = create_blacklist_date(days)
        args = (user_id, blacklistdate, True)
        query = f"INSERT INTO {Table.BLACKLIST} (userid, blacklisted, blacklistedtill) VALUES ($1, $2, $3) RETURNING *"
        if reason is not None:
            query = f"INSERT INTO {Table.BLACKLIST} (userid, blacklisted, blacklistedtill, reason) VALUES ($1, $2, $3, $4) RETURNING *"
            args += (reason,)

        data = await self.fetchrow(query, *args)
        inst = Blacklist(self, data)
        if cache:
            self._blacklists[user_id] = inst
        return inst

    async def update_temp_blacklist(
        self,
        user_id: int,
        days: Optional[int] = None,
        reason: Optional[str] = None,
        cache: bool = False,
    ) -> Optional[Blacklist]:
        from Cogs.Utils import create_blacklist_date

        blacklistdate = create_blacklist_date(days)
        args = (user_id, blacklistdate, True)
        query = f"UPDATE {Table.BLACKLIST} SET blacklisted = $3, blacklistedtill = $2"
        if reason is not None:
            query = f"UPDATE {Table.BLACKLIST} SET blacklisted = $3, blacklistedtill = $2, reason = $4"
            args += (reason,)

        query += " WHERE userid = $1 RETURNING *"
        data = await self.fetchrow(query, Table.BLACKLIST, *args)
        inst = Blacklist(self, data)
        if cache:
            self._blacklists[user_id] = inst
        return inst

    async def remove_blacklist(self, user_id: int) -> Optional[Blacklist]:
        """Remove a user from the blacklist table.

        Parameters
        ----------
        user_id: int
            ID of the user to remove.

        Returns
        -------
        Optional[:class:`Blacklist`]
            Object representing the removed user. If found in cache else ``None``.
        """
        query = f"DELETE FROM {Table.BLACKLIST} WHERE userid = $1"
        await self.execute(query, user_id)
        return self._blacklists.pop(user_id, None)

    def get_blacklist(self, user_id: int) -> Optional[Blacklist]:
        """Get a user from the blacklist table.

        Parameters
        ----------
        user_id: int
            ID of the user to get.

        Returns
        -------
        Optional[:class:`Blacklist`]
            Object representing the user. If found in cache else ``None``.
        """
        return self._blacklists.get(user_id)

    async def fetch_blacklists_table(self, cache: bool = False) -> list[Blacklist]:
        """Fetch all blacklisted users from the blacklist table.

        Parameters
        ----------
        cache: bool
            Whether to cache the entries. Defaults to ``False``.

        Returns
        -------
        list[:class:`Blacklist`]
            List of objects representing the blacklisted users.
        """
        return await self.__fetch(Table.BLACKLIST, cache=cache)

    async def fetch_blacklists(self, blacklisted: Optional[bool] = True, cache: bool = False) -> list[Blacklist]:
        """Fetch all blacklisted users from the blacklist table.

        Parameters
        ----------
        blacklisted: bool
            Whether to only fetch blacklisted users or not. Defaults to ``True``.
            Set to ``None`` for everyone.
        cache: bool
            Whether to cache the entries. Defaults to ``False``.

        Returns
        -------
        list[:class:`Blacklist`]
            List of objects representing the blacklisted users.
        """
        where = {}
        if blacklisted is not None:
            where["blacklisted"] = blacklisted
        return await self.__fetch(
            Table.BLACKLIST,
            cache=cache,
            where=where,
            fetch_one=False,
        )

    async def fetch_blacklist(
        self, user_id: int, blacklisted: Optional[bool] = None, cache: bool = False
    ) -> Optional[Blacklist]:
        """Fetch a blacklisted user from the blacklist table.

        Parameters
        ----------
        user_id: int
            ID of the user to fetch.
        blacklisted: bool
            Whether to only return if user is blacklisted or not. Defaults to ``True``.
            Set to ``None`` for it to return regardless.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.
        """
        where = {"userid": user_id}
        if blacklisted is not None:
            where["blacklisted"] = blacklisted
        return await self.__fetch(
            Table.BLACKLIST,
            cache=cache,
            where=where,
        )

    # commands

    @property
    def commands(self) -> list[Command]:
        return list(self._commands.values())

    async def disable_command(self, guild_id: int, command_name: str, cache: bool = True) -> Command:
        if guild_id in self._commands:
            entry = self._commands[guild_id]
            await entry.add(command_name)
        else:
            query = "INSERT INTO commands (guild, disabled) VALUES ($1, $2) ON CONFLICT (guild) DO UPDATE SET disabled = $2 RETURNING *"
            data = await self.fetchrow(query, guild_id, [command_name])
            entry = Command(self, data)
            if cache:
                self._commands[guild_id] = entry
            return entry

        return entry

    async def enable_command(self, guild_id: int, command_name: str, cache: bool = True):
        if guild_id in self._commands:
            entry = self._commands[guild_id]
            await entry.remove(command_name)
        else:
            query = "INSERT INTO commands (guild, disabled) VALUES ($1, $2) ON CONFLICT (guild) DO UPDATE SET disabled = $2 RETURNING *"
            data = await self.fetchrow(query, guild_id, [])
            entry = Command(self, data)
            if cache:
                self._commands[guild_id] = entry

        return entry

    def get_command(self, guild_id: int) -> Optional[Command]:
        return self._commands.get(guild_id)

    async def fetch_commands(self, cache: bool = True) -> list[Command]:
        to_return: dict[int, Command] = {}
        data = await self.fetch(f"SELECT * FROM {Table.COMMANDS}")
        if not data:
            return []

        for command in data:
            to_return[command["guild"]] = Command(self, command)

        if cache:
            self._commands = to_return

        return list(to_return.values())

    async def fetch_command(self, guild_id: int, command_name: str, cache: bool = True) -> Optional[Command]:
        query = f"SELECT * FROM {Table.COMMANDS} where guildid = $1"
        try:
            data = await self.fetchrow(query, guild_id)
        except DatabaseError:
            return None

        if not data:
            return None

        if command_name not in data["disabled_commands"]:
            return None

        inst = Command(self, data)
        if cache:
            self._commands[guild_id] = inst

        return inst

    async def add_command_guild(self, guild_id: int, cache: bool = True) -> Command:
        """Add a guild to the commands table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to add.
        cache: bool
            Whether to cache the entry. Defaults to ``True``.

        Returns
        -------
        :class:`Command`
            Object representing the added command guild.
        """
        query = "INSERT INTO commands (guild, disabled) VALUES ($1, $2) ON CONFLICT (guild) DO UPDATE SET disabled = $2 RETURNING *"
        data = await self.fetchrow(query, guild_id, [])
        entry = Command(self, data)
        if cache:
            self._commands[guild_id] = entry
        return entry

    async def fetch_command_guild(self, guild_id: int, cache: bool = True) -> Optional[Command]:
        """Fetch a guild from the commands table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to fetch.
        cache: bool
            Whether to cache the entry. Defaults to ``True``.

        Returns
        -------
        Optional[:class:`Command`]
            Object representing the command guild. ``None`` if not found.
        """
        query = f"SELECT * FROM {Table.COMMANDS} where guild = $1"
        try:
            data = await self.fetchrow(query, guild_id)
        except DatabaseError:
            return None

        if not data:
            return None

        inst = Command(self, data)
        if cache:
            self._commands[guild_id] = inst

        return inst

    # guild blacklists ---

    @property
    def blacklisted_guilds(self) -> list[GuildBlacklist]:
        return list(self._guild_blacklists.values())

    async def add_guild_blacklist(
        self,
        guild_id: int,
        name: Optional[str] = None,
        blacklisted: bool = True,
        cache: bool = False,
    ) -> GuildBlacklist:
        """Add a guild to the guild blacklist table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to add.
        name: Optional[str]
            Name of the guild. Defaults to ``None``.
        blacklisted: bool
            Whether the guild is blacklisted or not. Defaults to ``True``.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.

        Returns
        -------
        :class:`GuildBlacklist`
            Object representing the added guild.
        """
        args = (guild_id, blacklisted)
        query = f"INSERT INTO {Table.GUILDBLACKLISTS} (id, blacklisted) VALUES ($1, $2)"
        if name:
            query = f"INSERT INTO {Table.GUILDBLACKLISTS} (id, name, blacklisted) VALUES ($1, $3, $2)"
            args = (guild_id, blacklisted, name)

        query += " RETURNING *"
        data = await self.execute(query, *args)
        inst = GuildBlacklist(self, data)
        if cache:
            self._guild_blacklists[guild_id] = inst
        return inst

    async def remove_guild_blacklist(
        self,
        guild_id: int,
    ) -> Optional[GuildBlacklist]:
        """Remove a guild from the guild blacklist table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to remove.

        Returns
        -------
        Optional[:class:`GuildBlacklist`]
            Object representing the removed guild. If found in cache else ``None``.
        """
        query = f"DELETE FROM {Table.GUILDBLACKLISTS} WHERE id = $1"
        await self.execute(query, guild_id)
        return self._guild_blacklists.pop(guild_id, None)

    async def fetch_guild_blacklists(
        self, blacklisted: Optional[bool] = True, cache: bool = False
    ) -> list[GuildBlacklist]:
        """Fetch all guilds from the guild blacklist table.

        Parameters
        ----------
        blacklisted: bool
            Whether to only fetch blacklisted guilds or not. Defaults to ``True``.
            Set to ``None`` for everyone.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.

        """
        where = {}
        if blacklisted is not None:
            where["blacklisted"] = blacklisted
        return await self.__fetch(Table.GUILDBLACKLISTS, cache=cache, where=where)  # type: ignore

    async def fetch_guild_blacklist(
        self, guild_id: int, blacklisted: Optional[bool] = True, cache: bool = False
    ) -> Optional[GuildBlacklist]:
        """Fetch a guild from the guild blacklist table.

        Parameters
        ----------
        guild_id: int
            ID of the guild to fetch.
        blacklisted: bool
            Whether to only return if user is blacklisted or not. Defaults to ``True``.
            Set to ``None`` for it to return regardless.
        cache: bool
            Whether to cache the entry. Defaults to ``False``.

        Returns
        -------
        Optional[:class:`GuildBlacklist`]
            Object representing the fetched guild. If found in cache else ``None``.
        """
        where = {"id": guild_id}
        if blacklisted is not None:
            where["blacklisted"] = blacklisted
        return await self.__fetch(Table.GUILDBLACKLISTS, cache=cache, where=where)

    def get_guild_blacklist(self, guild_id: int) -> Optional[GuildBlacklist]:
        """Get a guild from the guild blacklists cache.

        Parameters
        ----------
        guild_id: int
            ID of the guild to get.

        Returns
        -------
        Optional[:class:`GuildBlacklist`]
            Object representing the entry. If found else ``None``.
        """
        return self._guild_blacklists.get(guild_id)
