# SPDX-License-Identifier: AGPL-3.0-or-later
"""The production-record queries, run against a real SQLite database with the 3s_production schema
(fixtures in conftest.py)."""

import sqlite3

import pytest

from vin_storyteller.repository import PARAMSTYLES, ProductionRecords
from vin_storyteller.story import MISSING


def test_existing_records_are_caps(records):
	assert records.story("JA3AM84J3NY000004").provenance == "CAPS"


def test_car_row(records):
	car = records.car("JA3AM84J3NY000004")
	assert (
		car.serial,
		car.model,
		car.model_code,
		car.exterior,
		car.built,
		car.model_year,
		car.provenance,
	) == (
		"00004530",
		"M1",
		"Z16A",
		"T87",
		"92032",
		"92",
		"CAPS",
	)
	assert records.car("JA3AM84J3NY999999") is None


def test_history_oldest_first_undated_last_and_unsafe_links_dropped(records):
	history = records.history("JA3AM84J3NY000004")
	assert [h.kind for h in history] == ["sale", "auction", "photo"]
	assert history[0].url is None  # the javascript: link
	assert (history[1].url, history[1].date, history[1].source) == (
		"https://example.com/lot/1",
		"2021-05-01",
		"BaT",
	)
	assert records.story("JA3AM84J3NY000004").history == history


def test_no_history_is_empty(records):
	assert records.history("JA3AM84J3NY000001") == ()


def test_history_rejects_unknown_record_types(connection):
	with pytest.raises(sqlite3.IntegrityError):
		connection.execute(
			"INSERT INTO VehicleHistory (VIN, RecordType, Title, Provenance) VALUES ('X', 'rumour', 't', 'p')"
		)


def test_colour_run_and_rarity(records):
	story = records.story("JA3AM84J3NY000004")
	# MY92 3000GT VR-4 in Fiji Blue (T87): serials 4500, 4510 before it, 4540 after -> number 3 of 4
	assert (story.in_colour.position, story.in_colour.total) == (3, 4)
	# same tier: fewest first; on a tie the narrower claim (spec) leads
	assert [(r.scope, r.total, r.tier) for r in story.rarities] == [
		("spec", 4, "sub10"),
		("colour", 4, "sub10"),
		("model", 5, "sub10"),
	]


def test_one_of_one_red_car(records):
	story = records.story("JA3AM84J3NY000003")  # the only MY92 Morocco Red 3000GT VR-4
	assert story.among_identical == story.in_colour
	assert story.as_dict()["rarest"] == "one_of_one"


def test_unknown_vin_has_no_story(records):
	assert records.story("JA3AM84J3NY999999") is None


def test_story_of_a_mitsubishi(records):
	story = records.story("JA3AM84J3NY000004")
	assert story.vehicle_name == "1992 Mitsubishi 3000GT VR-4"
	assert story.exterior.description == "Fiji Blue"
	assert (story.interior.code, story.interior.description) == ("12A", "Grey")
	assert story.equipment.description == "Leather"
	assert story.built == "the 2nd production period of March, 1992"


def test_counts_for_build_period_and_month(records):
	story = records.story("JA3AM84J3NY000004")
	assert story.built_in_period == 3  # 92032: cars 4, 5 and the Stealth 7
	assert story.built_in_month == 5  # 9203x: cars 3, 4, 5, 7, 9


def test_production_starts(records):
	story = records.story("JA3AM84J3NY000004")
	assert story.year_started == "the 2nd production period of September, 1991"  # earliest MY92 build, 91092
	assert story.model_started == "the 2nd production period of September, 1991"  # first MY92 3000GT VR-4


def test_positions(records):
	story = records.story("JA3AM84J3NY000004")
	# MY92 serials below 00004530: 4500, 4505, 4510, 4520 -> number 5 of 8 MY92 cars
	assert (story.in_year.position, story.in_year.total) == (5, 8)
	# MY92 3000GT VR-4 (M1/Z16A): 4500, 4510, 4520 before it -> number 4 of 5
	assert (story.in_model.position, story.in_model.total) == (4, 5)
	# identical spec (Fiji Blue, Grey, Leather): 4500, 4510 before -> number 3 of 4
	assert (story.among_identical.position, story.among_identical.total) == (3, 4)


def test_dodge_uses_its_own_colour_name_or_missing(records):
	assert records.story("1B3XC64B7NS000006").exterior.description == MISSING  # R25 has no Dodge name
	assert records.story("1B3XC64B7NS000006").vehicle_name == "1992 Dodge Stealth R/T Turbo"


def test_unknown_interior_is_missing(records):
	story = records.story("1B3XC64B7NS000007")
	assert (story.interior.code, story.interior.description) == ("99Z", MISSING)


def test_unknown_model_exterior_and_equipment(records):
	story = records.story("JA3AM84J3NY000009")
	assert (story.manufacturer, story.model, story.trim) == (MISSING, MISSING, "")
	assert story.exterior.description == MISSING
	assert story.equipment.description == MISSING
	assert story.vehicle_name == "1992 MISSING MISSING"


def test_first_car_is_number_one(records):
	story = records.story("JA3AM84J3NY000001")
	assert story.in_year.position == 1
	assert story.among_identical.position == 1


def test_queries_are_parameterized(records):
	"""An injection attempt is just a VIN that isn't on record."""
	assert records.story("' OR '1'='1") is None


def test_paramstyles():
	assert PARAMSTYLES == {"format": "%s", "qmark": "?"}
	with pytest.raises(KeyError):
		ProductionRecords(None, paramstyle="named")
