"""Hold writer guards while snapshotting through separate read connections."""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path

from gleansight.workspaces.models import DatabaseState, TableState
from papers.domain.errors import ConflictError, ValidationError


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def reader(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0)


def tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    )


@contextmanager
def guarded_databases(paths: tuple[Path, ...]) -> Iterator[tuple[sqlite3.Connection, ...]]:
    with ExitStack() as stack:
        guards: list[sqlite3.Connection] = []
        try:
            for path in sorted(set(paths)):
                connection = stack.enter_context(
                    closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0))
                )
                connection.execute("BEGIN IMMEDIATE")
                stack.callback(connection.rollback)
                existing = tables(connection)
                for table in ("jobs", "nsqd_jobs"):
                    if (
                        table in existing
                        and connection.execute(
                            f"SELECT 1 FROM {table} WHERE status = 'running' LIMIT 1"
                        ).fetchone()
                    ):
                        raise ConflictError(
                            "Workspace has running work; wait for it to finish first."
                        )
                if (
                    "supervised_workers" in existing
                    and connection.execute(
                        "SELECT 1 FROM supervised_workers WHERE phase IN "
                        "('starting', 'running', 'paused', 'stopping') LIMIT 1"
                    ).fetchone()
                ):
                    raise ConflictError("Workspace has an active managed worker; stop it first.")
                guards.append(connection)
            yield tuple(guards)
        except sqlite3.OperationalError as exc:
            raise ConflictError(f"Workspace database is busy or unavailable: {exc}") from exc


def snapshot_database(source: Path, destination: Path) -> None:
    with closing(reader(source)) as connection, closing(sqlite3.connect(destination)) as output:
        connection.backup(output)


def database_state(path: Path, target: str) -> DatabaseState:
    try:
        with closing(reader(path)) as connection:
            check = connection.execute("PRAGMA quick_check").fetchall()
            if check != [("ok",)]:
                raise ValidationError(f"Database integrity check failed: {target}")
            names = tables(connection)
            migrations = (
                tuple(
                    row[0]
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )
                )
                if "schema_migrations" in names
                else ()
            )
            schema = "\n".join(
                str(row)
                for row in connection.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
                )
            )
            return DatabaseState(
                target=target,
                user_version=connection.execute("PRAGMA user_version").fetchone()[0],
                migrations=migrations,
                schema_sha256=hashlib.sha256(schema.encode()).hexdigest(),
                tables=tuple(
                    TableState(
                        name=name,
                        rows=connection.execute(
                            f"SELECT count(*) FROM {quote_identifier(name)}"
                        ).fetchone()[0],
                    )
                    for name in names
                ),
            )
    except sqlite3.DatabaseError as exc:
        raise ValidationError(f"Database integrity check failed: {target}") from exc
