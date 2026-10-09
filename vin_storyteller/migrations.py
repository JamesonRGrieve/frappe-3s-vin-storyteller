# SPDX-License-Identifier: AGPL-3.0-or-later
"""Versioned schema migrations for the production-record database.

Each `sql/migrations/NNNN_name.sql` file runs once, in order, and is recorded in `SchemaMigration`. The
files are plain SQL; `{autoincrement}` is the one dialect token (MariaDB needs AUTO_INCREMENT, SQLite's
INTEGER PRIMARY KEY already is).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "sql" / "migrations"
ADMIN_USER_ENV = "VIN_STORYTELLER_DB_ADMIN_USER"
ADMIN_PASSWORD_ENV = "VIN_STORYTELLER_DB_ADMIN_PASSWORD"
DIALECT_TOKENS = {"mariadb": {"autoincrement": "AUTO_INCREMENT"}, "sqlite": {"autoincrement": ""}}
PARAMS = {"mariadb": "%s", "sqlite": "?"}
TRACKING_TABLE = (
	"CREATE TABLE IF NOT EXISTS SchemaMigration ("
	"Version VARCHAR(100) PRIMARY KEY, AppliedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
)


class MissingCredentials(Exception):
	"""The migration user's credentials are not in the environment."""


def admin_credentials(environ: Mapping[str, str]) -> tuple[str, str]:
	"""The (user, password) allowed to change the schema, read from the environment only (never argv)."""
	user, password = environ.get(ADMIN_USER_ENV), environ.get(ADMIN_PASSWORD_ENV)
	if not user or not password:
		raise MissingCredentials(f"Set {ADMIN_USER_ENV} and {ADMIN_PASSWORD_ENV} in the environment.")
	return user, password


def available(directory: Path = MIGRATIONS_DIR) -> list[Path]:
	return sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def statements(sql: str, dialect: str) -> list[str]:
	"""The file's statements, dialect tokens filled, comments and blank statements dropped."""
	body = "\n".join(
		line for line in sql.format(**DIALECT_TOKENS[dialect]).splitlines() if not line.startswith("--")
	)
	return [s.strip() for s in body.split(";") if s.strip()]


def _execute(connection, sql: str, params: tuple = ()) -> list[tuple]:
	cursor = connection.cursor()
	try:
		cursor.execute(sql, params)
		return list(cursor.fetchall())
	finally:
		cursor.close()


def applied(connection) -> set[str]:
	_execute(connection, TRACKING_TABLE)
	return {row[0] for row in _execute(connection, "SELECT Version FROM SchemaMigration")}


def migrate(connection, dialect: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
	"""Apply every pending migration in order; returns the versions applied this run."""
	done = applied(connection)
	ran = []
	for path in available(directory):
		if path.stem in done:
			continue
		for statement in statements(path.read_text(), dialect):
			_execute(connection, statement)
		_execute(
			connection, f"INSERT INTO SchemaMigration (Version) VALUES ({PARAMS[dialect]})", (path.stem,)
		)
		connection.commit()
		ran.append(path.stem)
	return ran
