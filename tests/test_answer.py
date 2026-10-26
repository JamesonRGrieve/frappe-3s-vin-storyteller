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
	assert answer(valid("JA3AM84J3NY999999"), open_records, DB_ERRORS) == {
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


def valid(vin):
	"""`vin` with its correct check digit (the fixture's VINs are made up)."""
	from vin_storyteller.story import check_digit

	return vin[:8] + check_digit(vin) + vin[9:]


def message(open_records, vin):
	reply = answer(valid(vin), open_records, DB_ERRORS)
	assert reply["status"] == "not_found"
	return reply["message"]


def test_not_found_inside_a_gap_names_the_cars_either_side(open_records):
	text = message(open_records, "JA3AM84J3NY000008")
	assert "Serial 000008 isn't in the factory record for the 1992 model year" in text
	assert "serial 000007 was built in the 2nd production period of March, 1992" in text
	assert "serial 000009 in the 3rd production period of March, 1992" in text
	assert "almost certainly genuine" in text and "storyteller@3shub.com" in text


def test_not_found_after_the_last_car_of_the_year(open_records):
	text = message(open_records, "JA3AM84J3NY000010")
	assert "comes after the last 1992 car in the factory record (serial 000009" in text


def test_not_found_before_the_first_car_mentions_crash_test_serials(open_records):
	text = message(open_records, "JA3AM84J3MY000005")
	assert "comes before the first 1991 car in the factory record (serial 000008" in text
	assert "crash-test or promotional" in text


@pytest.mark.parametrize(
	("vin", "expected"),
	[
		("1HGCM82633A004352", "starts with 1HG"),
		("JA3AM84J3AY000001", "isn't a 1991–1999 model year code"),
	],
)
def test_not_found_explains_a_vin_that_cannot_be_a_3s(open_records, vin, expected):
	assert expected in message(open_records, vin)


def test_not_found_falls_back_to_the_original_message(open_records):
	assert message(open_records, "JA3AM84J3NY999999") == NOT_FOUND


def test_a_wrong_check_digit_is_called_a_typo(open_records):
	vin = valid("JA3AM84J3NY000008")
	typo = vin[:8] + ("0" if vin[8] != "0" else "1") + vin[9:]
	text = answer(typo, open_records, DB_ERRORS)["message"]
	assert "almost certainly mistyped" in text


@pytest.mark.parametrize("chassis", ["Z16A-0011452", "z15a0200248", " Z16A-0006229 "])
def test_jdm_chassis_number_is_recognised_without_touching_the_database(chassis):
	from vin_storyteller.story import CHASSIS_NOT_ON_RECORD

	def opener():
		raise AssertionError("a chassis number never opens the production record")

	assert answer(chassis, opener, DB_ERRORS) == {"status": "not_found", "message": CHASSIS_NOT_ON_RECORD}


@pytest.mark.parametrize("not_chassis", ["Z17A-0011452", "Z16A-001145", "Z16A-00114521"])
def test_near_miss_chassis_numbers_stay_invalid(not_chassis):
	def opener():
		raise AssertionError("an invalid identifier never opens the production record")

	assert answer(not_chassis, opener, DB_ERRORS) == {"status": "invalid", "message": INVALID}
