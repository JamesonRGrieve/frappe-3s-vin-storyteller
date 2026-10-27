# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schema migrations: parsing, ordering, recording, idempotence and the credential rule."""

import sqlite3

import pytest

from vin_storyteller.migrations import (
	ADMIN_PASSWORD_ENV,
	ADMIN_USER_ENV,
	MIGRATIONS_DIR,
	MissingCredentials,
	admin_credentials,
	applied,
	available,
	migrate,
	statements,
)

SHIPPED = [
	"0001_indexes",
	"0002_provenance_and_history",
	"0003_stories_told",
	"0004_gto_models",
	"0005_factory_build_provenance",
	"0006_code_labels",
	"0007_export_models",
	"0008_option_code_index",
]


def test_shipped_migrations_in_order():
	assert [p.stem for p in available()] == SHIPPED


def test_statements_fill_dialect_and_drop_comments():
	sql = "-- a comment\nCREATE TABLE T (ID INTEGER PRIMARY KEY {autoincrement});\n\n-- another\nSELECT 1;\n"
	assert statements(sql, "mariadb") == [
		"CREATE TABLE T (ID INTEGER PRIMARY KEY AUTO_INCREMENT)",
		"SELECT 1",
	]
	assert statements(sql, "sqlite") == ["CREATE TABLE T (ID INTEGER PRIMARY KEY )", "SELECT 1"]


def test_unknown_dialect_is_rejected():
	with pytest.raises(KeyError):
		statements("SELECT 1;", "postgres")


@pytest.mark.parametrize("path", available(), ids=lambda p: p.stem)
def test_every_shipped_migration_parses_for_mariadb(path):
	parsed = statements(path.read_text(), "mariadb")
	assert parsed and all("{" not in s for s in parsed)


def test_fresh_dump_migrates_and_records(caps_connection):
	assert applied(caps_connection) == set()
	assert migrate(caps_connection, "sqlite") == SHIPPED
	assert applied(caps_connection) == set(SHIPPED)
	assert migrate(caps_connection, "sqlite") == []  # idempotent


def test_existing_rows_are_named_for_the_1999_caps_build(caps_connection):
	"""The original export is NA9199, from CAPS PASEN/SHARYO dated 1999-09-16 (0002 then 0005)."""
	migrate(caps_connection, "sqlite")
	values = {row[0] for row in caps_connection.execute("SELECT Provenance FROM Production")}
	assert values == {"CAPS 1999"}


def test_new_rows_can_carry_other_provenance(caps_connection):
	migrate(caps_connection, "sqlite")
	caps_connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, "
		"Interior, DateOfManufacture, ModelYear, Provenance) "
		"VALUES ('00009999', 'JA3AM84J3NY099999', 'M1', 'Z16A', 'C', 'XA1', 'T87', '12A', '93011', '93', 'owner')"
	)
	row = caps_connection.execute(
		"SELECT Provenance FROM Production WHERE VIN = 'JA3AM84J3NY099999'"
	).fetchone()
	assert row == ("owner",)


def test_indexes_exist(caps_connection):
	migrate(caps_connection, "sqlite")
	names = {row[0] for row in caps_connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
	assert {
		"idx_production_vin",
		"idx_production_spec",
		"idx_history_vin",
		"idx_production_colours",
		"idx_production_interior",
		"idx_production_equipment",
	} <= names


def test_pending_only(tmp_path, caps_connection):
	(tmp_path / "0001_a.sql").write_text("CREATE TABLE A (X INTEGER);")
	assert migrate(caps_connection, "sqlite", tmp_path) == ["0001_a"]
	(tmp_path / "0002_b.sql").write_text("CREATE TABLE B (X INTEGER);")
	(tmp_path / "notes.sql").write_text("this is not a migration")
	assert migrate(caps_connection, "sqlite", tmp_path) == ["0002_b"]


def test_failing_migration_is_not_recorded(tmp_path):
	connection = sqlite3.connect(":memory:")
	(tmp_path / "0001_ok.sql").write_text("CREATE TABLE A (X INTEGER);")
	(tmp_path / "0002_bad.sql").write_text("CREATE TABLE NOPE (;")
	with pytest.raises(sqlite3.OperationalError):
		migrate(connection, "sqlite", tmp_path)
	assert applied(connection) == {"0001_ok"}
	connection.close()


def test_migrations_dir_is_packaged():
	assert MIGRATIONS_DIR.is_dir()


class TestAdminCredentials:
	def test_reads_both(self):
		assert admin_credentials({ADMIN_USER_ENV: "u", ADMIN_PASSWORD_ENV: "p"}) == ("u", "p")

	@pytest.mark.parametrize(
		"environ",
		[{}, {ADMIN_USER_ENV: "u"}, {ADMIN_PASSWORD_ENV: "p"}, {ADMIN_USER_ENV: "", ADMIN_PASSWORD_ENV: "p"}],
	)
	def test_missing_is_an_error_naming_the_variables(self, environ):
		with pytest.raises(MissingCredentials, match=ADMIN_USER_ENV):
			admin_credentials(environ)


def test_existing_stories_told_is_kept(caps_connection):
	"""The CAPS-era database already has StoriesTold with years of history: 0003 leaves it untouched."""
	caps_connection.execute(
		"CREATE TABLE StoriesTold (ID INTEGER PRIMARY KEY, VIN VARCHAR(17) NOT NULL, Name VARCHAR(100) NOT NULL, "
		"DateHour DATETIME NOT NULL, Time DATETIME NOT NULL)"
	)
	caps_connection.execute(
		"INSERT INTO StoriesTold (VIN, Name, DateHour, Time) "
		"VALUES ('JA3AN74K8RY020181', 'Jay Kim', '2026-04-01 23:00:00', '2026-04-01 23:13:46')"
	)
	migrate(caps_connection, "sqlite")
	assert caps_connection.execute("SELECT Name FROM StoriesTold").fetchall() == [("Jay Kim",)]
