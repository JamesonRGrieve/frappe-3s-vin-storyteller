# SPDX-License-Identifier: AGPL-3.0-or-later
"""The production statistics page: region naming (pure) and the facets built from the real migrated SQLite
database (conftest.py)."""

import sqlite3
from contextlib import contextmanager

import pytest

from vin_storyteller.answer import RecordsUnavailable, stats_answer
from vin_storyteller.records import add_record
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.stats import (
	NOT_RECORDED,
	Region,
	destination_code,
	destination_digits,
	generation,
	grade_market,
	region_note,
	region_of,
	spec_market,
	transmission,
)
from vin_storyteller.story import ASA_GENERAL, ASA_JAPAN, MISSING

# --- pure ---------------------------------------------------------------------------------------------------------


def test_an_export_option_item_names_the_market():
	assert spec_market(["CD AUTO CHANGER", "ENGLAND SPEC"]) == "England"
	assert spec_market(["BRITISH ARMY SPEC IN WEST GERMANY"]) == "British Army in West Germany"
	assert spec_market(["germany spec"]) == "Germany"
	assert spec_market(["LEATHER SEAT & ROOM TRIM"]) is None
	assert spec_market([]) is None
	assert spec_market(["NON-EC SPEC"]) == "Non-EC"


def test_an_export_grade_text_names_the_gulf_market():
	assert grade_market("DOHC(TURBO/4WD/4WS),5FM/T GCC") == "Gulf states (GCC)"
	assert grade_market("DOHC(TURBO/4WD/4WS),6FM/T") is None
	assert grade_market(None) is None


def test_the_transmission_comes_from_the_grade_text():
	assert transmission("ULTIMATE LINE,6FM/T") == "6-speed manual"
	assert transmission("GTO,4FA/T") == "4-speed automatic"
	assert transmission("ULTIMATE LINE") == NOT_RECORDED
	assert transmission(None) == NOT_RECORDED


def test_destination_codes_and_digits_come_from_the_grade_table():
	assert destination_code("CAL53H") == "CAL"
	assert destination_code(None) == ""
	digits = destination_digits(
		{
			("Z16A", "MJGFL2M"): "FED",
			("Z16A", "MJGFL7M"): "CAL",
			("Z11A", "MNHEL2M"): "FED",
			("Z11A", "X"): "FED",
		}
	)
	assert digits == {"2": "FED", "7": "CAL"}
	assert (
		destination_digits({("A", "MNHEL2M"): "FED", ("B", "MNHEL2M"): "CAL"}) == {}
	)  # disagreeing: no rule


def test_regions_follow_the_record():
	assert region_of("G6", "Z", "") == Region("Japan", "Japan", "Japan")
	assert region_of("ER", "C", "", ["ENGLAND SPEC"]) == Region("England", "Export", "United Kingdom")
	assert region_of("EL", "J", "", ["BRITISH ARMY SPEC IN WEST GERMANY"]).country == "Germany"
	assert region_of("EL", "J", "", (), "…,5FM/T GCC") == Region("Gulf states (GCC)", "Export", "")
	assert region_of("ER", "J", "").name == "Export, market not recorded (right-hand drive)"
	assert region_of("M1", "6", "FED") == Region("Australia", "Australia", "Australia")
	assert region_of("M1", "J", "CAL") == Region("California", "North America", "United States of America")
	assert region_of("M1", "J", "FED").name == "Federal (49-state)"
	assert region_of("M1", "J", "XYZ") == Region("North America (XYZ)", "North America", "")
	assert region_of("M1", "J", "").name == "North America, destination not recorded"
	assert region_of("D1", "J", "digit 3").name == "North America, destination digit 3"
	assert region_of("D1", "J", "CAN") == Region("Canada", "North America", "Canada")


def test_generations_split_at_the_1994_facelift():
	assert generation("1993") == "1st generation (to 1993)"
	assert generation("1994") == "2nd generation (1994 on)"
	assert generation("2000") == "2nd generation (1994 on)"
	assert generation("") == NOT_RECORDED


def test_every_region_explains_itself():
	assert "emissions" in region_note(region_of("M1", "J", "FED"))
	assert "ENGLAND SPEC" in region_note(region_of("ER", "C", "", ["ENGLAND SPEC"]))
	assert "drive side" in region_note(region_of("ER", "C", ""))
	assert region_note(region_of("M1", "J", ""))


# --- against the database -----------------------------------------------------------------------------------------


@pytest.fixture
def records(connection):
	return ProductionRecords(connection, "qmark")


def add_car(connection, vin, model, grade, option, exterior, interior, built, year, provenance):
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES (?, ?, ?, 'Z16A', ?, ?, ?, ?, ?, ?, ?)",
		(vin[-7:], vin, model, grade, option, exterior, interior, built, year, provenance),
	)


def catalogue(connection):
	connection.executemany(
		"INSERT INTO ClassificationLabel (Source, ModelCode, Classification, Language, Description, Destination) "
		"VALUES (?, ?, ?, 'en', ?, ?)",
		[
			("CAPS 2004", "Z16A", "MJGFL2M", "ULTIMATE LINE,6FM/T", "FED53H"),
			("CAPS 2004", "Z16A", "MJGFL7M", "ULTIMATE LINE,6FM/T", "CAL53H"),
			("ASA General 2008", "Z16A", "MNGFR", "DOHC(TURBO/4WD/4WS),5FM/T", ""),
			("ASA General 2008", "Z16A", "MJGFL6", "DOHC(TURBO/4WD/4WS),5FM/T GCC", ""),
			("ASA Japan 2008", "Z16A", "MNGF", "GTO TWIN-TURBO,5FM/T", ""),
		],
	)
	connection.execute(
		"INSERT INTO OptionContent (Source, ModelCode, OptionCode, Classification, ModelYear, StartDate, EndDate, "
		"Items) VALUES (?, 'Z16A', 'D01', 'MNGFR', '93', '1992081', '1993123', 'XA3,J50')",
		(ASA_GENERAL,),
	)
	connection.executemany(
		"INSERT INTO OptionItem (Source, ItemCode, Language, Description) VALUES (?, ?, 'en', ?)",
		[(ASA_GENERAL, "XA3", "ENGLAND SPEC"), (ASA_GENERAL, "J50", "CD AUTO CHANGER")],
	)
	connection.execute(
		"INSERT INTO PaintAlias (Code, PaintCode, Source) VALUES ('TA7', 'T87', 'ASA USA 2007')"
	)
	add_car(connection, "CMNZ16APY00101", "ER", "MNGFR", "D01", "R71", "12A", "92081", "93", ASA_GENERAL)
	add_car(connection, "JMAMJZ16AVY000777", "EL", "MJGFL6", "ZR3", "TA7", "12A", "97031", "97", ASA_GENERAL)
	add_car(connection, "Z16A-0014160", "G6", "MNGF", "302", "T87", "12A", "92032", "92", ASA_JAPAN)
	add_car(connection, "JA3AM84J3NY900001", "M1", "MJGFL7M", "XA1", "T87", "12A", "92032", "92", "CAPS 1999")
	add_car(connection, "6MMAM84J3NY900002", "M1", "MJGFL9M", "XA1", "T87", "12A", "92032", "92", "CAPS 2004")


def facet(stats, name):
	"""A facet's totals by value, keyed by the value's description."""
	values = stats["facets"][name]["values"]
	totals: dict = {}
	for *_, value, n in stats["facets"][name]["rows"]:
		key = (
			tuple(values[value].values())
			if name in ("colours", "rarity")
			else values[value].get("code", values[value]["name"])
		)
		totals[key] = totals.get(key, 0) + n
	return totals


def by(stats, dimension):
	"""Car totals by year, model or region (summed over the line facet, which counts every car once)."""
	position = {"years": 0, "models": 1, "regions": 2}[dimension]
	labels = stats[dimension]
	totals: dict = {}
	for row in stats["facets"]["line"]["rows"]:
		label = labels[row[position]]
		label = label["name"] if isinstance(label, dict) else label
		totals[label] = totals.get(label, 0) + row[-1]
	return totals


def test_every_factory_car_counts_once_in_every_facet(connection, records):
	catalogue(connection)
	add_record(connection, "Z16A-0011452", "Mitsubishi recall 1153", "qmark")  # another source: never counted
	stats = stats_answer(lambda: _session(records), (sqlite3.Error,))["stats"]
	factory = connection.execute(
		"SELECT COUNT(*) FROM Production WHERE Provenance IN "
		"('CAPS 1999', 'CAPS 2004', 'ASA Japan 2008', 'ASA General 2008', 'ASA USA 2007')"
	).fetchone()[0]
	assert stats["total"] == factory == 14
	for name, data in stats["facets"].items():
		if name != "options":  # a car counts under each of its option items
			assert sum(row[-1] for row in data["rows"]) == factory, name


def test_regions_split_the_cars(connection, records):
	catalogue(connection)
	stats = stats_answer(lambda: _session(records), (sqlite3.Error,))["stats"]
	regions = by(stats, "regions")
	assert regions["England"] == 1
	assert regions["Gulf states (GCC)"] == 1
	assert regions["Japan"] == 1
	assert regions["California"] == 1
	assert regions["Australia"] == 1
	# The fixture's CAPS grade CLASS01 has no label and a destination digit (0) no labelled grade uses.
	assert regions["North America, destination digit 0"] == 9
	assert {r["name"]: r["country"] for r in stats["regions"]}["England"] == "United Kingdom"


def test_a_grade_missing_from_the_table_takes_its_destination_digit(connection, records):
	catalogue(connection)
	add_car(connection, "JA3AM84J3NY900003", "M1", "MNGFL2X", "XA1", "T87", "12A", "92032", "92", "CAPS 1999")
	regions = by(stats_answer(lambda: _session(records), (sqlite3.Error,))["stats"], "regions")
	assert regions["Federal (49-state)"] == 1


def test_facets_name_their_values(connection, records):
	catalogue(connection)
	stats = stats_answer(lambda: _session(records), (sqlite3.Error,))["stats"]
	paints = facet(stats, "paint")
	assert paints["T87"] == 9  # the "A" form TA7 counts under T87
	assert "TA7" not in paints
	paint_names = {v["code"]: v["name"] for v in stats["facets"]["paint"]["values"]}
	assert paint_names["T87"] == "Fiji Blue"
	assert paint_names["R71"] == MISSING
	transmissions = facet(stats, "transmission")
	assert transmissions["5-speed manual"] == 3  # the English export car, the Gulf car and the GTO
	assert transmissions["6-speed manual"] == 2  # MJGFL7M, and MJGFL9M by its first four characters
	assert transmissions[NOT_RECORDED] == 9
	months = facet(stats, "month")
	assert months["1992-03"] == 8 and months["1997-03"] == 1
	assert by(stats, "years")["1993"] == 1
	assert set(by(stats, "models")) == {"3000GT", "Stealth", "GTO", "Other"}


def test_rarity_counts_cars_by_their_exact_specs_run(connection, records):
	stats = stats_answer(lambda: _session(records), (sqlite3.Error,))["stats"]
	rarity = {key[1]: n for key, n in facet(stats, "rarity").items()}
	# MY92 3000GT T87/12A/XA1 is four cars (sub10); the R25 3000GT, both Stealths, the 1991 car and the unknown
	# codes are each one of one.
	assert rarity == {"Fewer than 10": 4, "One of one": 5}


def test_the_stats_answer_reports_an_unreadable_record(records):
	@contextmanager
	def broken():
		raise sqlite3.OperationalError("down")
		yield

	with pytest.raises(RecordsUnavailable):
		stats_answer(broken, (sqlite3.Error,))


def test_no_factory_cars_is_not_found(connection, records):
	connection.execute("DELETE FROM Production")
	assert stats_answer(lambda: _session(records), (sqlite3.Error,))["status"] == "not_found"


@contextmanager
def _session(records):
	yield records


def test_option_items_count_per_region_against_the_cars_with_records(connection, records):
	catalogue(connection)
	stats = stats_answer(lambda: _session(records), (sqlite3.Error,))["stats"]
	options = facet(stats, "options")
	# The English export car's D01 fits XA3 ENGLAND SPEC (its region, so left out) and J50.
	assert options == {"J50": 1}
	names = {v["code"]: v["name"] for v in stats["facets"]["options"]["values"]}
	assert names["J50"] == "CD AUTO CHANGER"
	assert facet(stats, "option_records") == {"on_record": 1, "not_on_record": 13}
	assert facet(stats, "generation") == {"1st generation (to 1993)": 13, "2nd generation (1994 on)": 1}
	assert {r["name"]: r["note"] for r in stats["regions"]}["Japan"].startswith("Japanese-market")


def test_destination_digit_3_is_canada(connection, records):
	"""Digit 3 has no 3S grade label, but is Canada (DOCUMENTED_DIGITS); an unknown digit stays a digit."""
	catalogue(connection)
	add_car(connection, "JB3XE74C5MY000002", "M1", "MNGFL3D", "XA1", "T87", "12A", "90041", "91", "CAPS 1999")
	add_car(connection, "JB3XE74C5MY000003", "M1", "MNGFL4D", "XA1", "T87", "12A", "90041", "91", "CAPS 1999")
	stats = stats_answer(lambda: _session(records), (sqlite3.Error,))["stats"]
	regions = by(stats, "regions")
	assert regions["Canada"] == 1
	assert regions["North America, destination digit 4"] == 1
	assert {r["name"]: r["country"] for r in stats["regions"]}["Canada"] == "Canada"
	assert "CANADA" in {r["name"]: r["note"] for r in stats["regions"]}["Canada"]
