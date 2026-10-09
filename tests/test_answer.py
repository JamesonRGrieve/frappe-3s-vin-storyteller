# SPDX-License-Identifier: AGPL-3.0-or-later
"""The API answer for a VIN, end to end against the real SQLite production record."""

import sqlite3
from contextlib import contextmanager

import pytest

from vin_storyteller.answer import INVALID, NOT_FOUND, RecordsUnavailable, answer
from vin_storyteller.repository import ProductionRecords

DB_ERRORS = (sqlite3.Error,)


@pytest.fixture
def open_records(connection):
	@contextmanager
	def opener():
		yield ProductionRecords(connection, paramstyle="qmark")

	return opener


def test_found(open_records):
	body = answer(" ja3am84j3ny000004 ", open_records, DB_ERRORS)
	assert body["status"] == "found"
	story = body["story"]
	assert story["vin"] == "JA3AM84J3NY000004"
	assert story["vehicle_name"] == "1992 Mitsubishi 3000GT VR-4"
	assert story["provenance"] == "CAPS"
	assert [h["kind"] for h in story["history"]] == ["sale", "auction", "photo"]
	assert story["rarest"] == "sub10"


@pytest.mark.parametrize("vin", [None, "", "SHORT", "JA3AM84J3NY00000O"])
def test_invalid_vin_never_touches_the_database(vin):
	def opener():
		raise AssertionError("the database must not be opened for an invalid VIN")

	assert answer(vin, opener, DB_ERRORS) == {"status": "invalid", "message": INVALID}


def test_not_found(open_records):
	assert answer("JA3AM84J3NY999999", open_records, DB_ERRORS) == {
		"status": "not_found",
		"message": NOT_FOUND,
	}


def test_database_failure_is_raised_as_unavailable(tmp_path):
	empty = sqlite3.connect(tmp_path / "empty.db")  # no tables: every query fails

	@contextmanager
	def opener():
		yield ProductionRecords(empty, paramstyle="qmark")

	with pytest.raises(RecordsUnavailable) as raised:
		answer("JA3AM84J3NY000004", opener, DB_ERRORS)
	assert isinstance(raised.value.__cause__, sqlite3.OperationalError)
	empty.close()


def test_other_errors_are_not_swallowed(open_records):
	@contextmanager
	def opener():
		raise RuntimeError("bug")
		yield

	with pytest.raises(RuntimeError):
		answer("JA3AM84J3NY000004", opener, DB_ERRORS)


def test_not_found_message_keeps_the_original_wording():
	assert "storyteller@3shub.com" in NOT_FOUND and "lost VIN" in NOT_FOUND
