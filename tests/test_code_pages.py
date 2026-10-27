# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-code pages (card 330): a paint, interior or option code's production stats and the kind's index, against
the real migrated SQLite database (conftest.py)."""

import pytest

from tests.test_factory_records import GTO, add_gto, labels
from vin_storyteller.records import add_record
from vin_storyteller.story import (
	MISSING,
	Coded,
	LineCount,
	MakerName,
	ModelCount,
	OptionFit,
	Pairing,
	YearCount,
)

# conftest's cars: 3000GTs (M1, Z16A, XA1) 000001/2/4/5 in T87 and 000003 in R25 for 1992, 000008 in T87 for 1991;
# Stealths (D1, Z16D) 000006/7 in R25; 000009 a car whose model and codes are unknown. All interior 12A but 000007.


def test_a_paint_page_counts_its_cars_by_model_year_and_line(records):
	page = records.code_page("paint", "T87")
	assert (page.kind, page.code, page.model_code, page.total) == ("paint", "T87", "", 5)
	assert page.description == "Fiji Blue"
	assert page.names == (MakerName("Mitsubishi", "Fiji Blue"), MakerName("Dodge", "Bright Blue"))
	assert page.by_model == (ModelCount("3000GT", 5),)
	assert page.by_year == (YearCount("1991", 1), YearCount("1992", 4))
	assert page.by_line == (LineCount("Mitsubishi", "3000GT", "VR-4", "Z16A", 5),)
	assert page.by_line[0].name == "Mitsubishi 3000GT VR-4"
	assert page.first_built == "the 1st production period of October, 1990"
	assert page.last_built == "the 2nd production period of March, 1992"
	assert page.pairings == (Pairing("12A", "Grey", 5),)
	assert page.fits == ()


def test_a_paint_only_dodge_named_reads_as_mitsubishis_name(records):
	page = records.code_page("paint", "R25")
	assert page.description == "Morocco Red" and page.names == (MakerName("Mitsubishi", "Morocco Red"),)
	assert page.by_model == (ModelCount("Stealth", 2), ModelCount("3000GT", 1))


def test_an_interior_page_pairs_it_with_its_paints(records):
	page = records.code_page("interior", "12A")
	assert page.total == 8 and page.description == "Grey"
	assert page.by_model == (ModelCount("3000GT", 6), ModelCount("Other", 1), ModelCount("Stealth", 1))
	assert page.pairings == (
		Pairing("T87", "Fiji Blue", 5),
		Pairing("R25", "Morocco Red", 2),
		Pairing("XXX", MISSING, 1),
	)


def test_a_colour_not_on_record_pairs_as_no_code(connection, records):
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES ('MY003000', 'JA3XE74C9MY003000', 'M1', 'Z16A', 'MNGFL7M', "
		"'XA1', 'EXT', '12A', '90081', '91', 'CAPS 1999')"
	)
	assert Pairing("", MISSING, 1) in records.code_page("interior", "12A").pairings


def test_an_option_page_is_per_chassis_model_code(records):
	page = records.code_page("option", "XA1", "Z16A")
	assert (page.code, page.model_code, page.description, page.total) == ("XA1", "Z16A", "Leather", 6)
	assert records.code_page("option", "XA1", "Z16D").total == 2  # the Stealths 000006 and 000007
	assert page.pairings == () and page.fits == ()


def test_an_option_page_says_what_the_code_fits_per_grade_and_year(connection, records):
	labels(connection)
	add_gto(connection)
	page = records.code_page("option", "302", "Z16A")
	assert page.total == 1 and page.by_model == (ModelCount("GTO", 1),)
	assert page.description == MISSING
	assert page.fits == (
		OptionFit(
			classification=Coded("MNGF", "GTO TWIN-TURBO,5FM/T"),
			model_year="1992",
			items=(
				Coded("K03", "LEATHER SEAT & ROOM TRIM"),
				Coded("J50", "CD AUTO CHANGER"),
				Coded("ZZ1", MISSING),
			),
			cars=1,
			source="ASA Japan 2008",
		),
	)


def test_a_fit_with_no_cars_built_so_still_shows(connection, records):
	labels(connection)
	add_gto(connection)
	connection.execute(
		"INSERT INTO OptionContent (Source, ModelCode, OptionCode, Classification, ModelYear, StartDate, EndDate, "
		"Items) VALUES ('ASA Japan 2008', 'Z16A', '302', 'MNGF', '93', '1992101', '1993093', 'J50')"
	)
	fits = records.code_page("option", "302", "Z16A").fits
	assert [(f.model_year, f.cars, len(f.items)) for f in fits] == [("1992", 1, 3), ("1993", 0, 1)]


def test_the_last_build_of_a_2000_gto_comes_after_1999(connection, records):
	add_gto(connection, built="00011", year="00")
	page = records.code_page("paint", "T87")
	assert page.first_built == "the 1st production period of October, 1990"
	assert page.last_built == "the 1st production period of January, 2000"
	assert page.by_year[-1] == YearCount("2000", 1)
	assert ModelCount("GTO", 1) in page.by_model


def test_only_factory_records_count(connection, records):
	add_record(connection, "Z16A-0011452", "Mitsubishi recall 1153", "qmark")
	connection.execute("UPDATE Production SET Exterior = 'T87', Interior = '12A' WHERE VIN = 'Z16A-0011452'")
	assert records.code_page("paint", "T87").total == 5
	assert all(e.model_code != "Z16A" or e.code for e in records.code_index("option"))


def test_a_code_no_factory_car_carries_has_no_page(records):
	assert records.code_page("paint", "Q99") is None
	assert records.code_page("option", "XA1", "Z15A") is None


def test_an_unknown_kind_is_refused(records):
	with pytest.raises(ValueError):
		records.code_page("wheels", "T87")
	with pytest.raises(ValueError):
		records.code_index("wheels")


def test_the_paint_index_lists_every_code_with_its_models(connection, records):
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES ('MY003000', 'JA3XE74C9MY003000', 'M1', 'Z16A', 'MNGFL7M', "
		"'EQU', 'EXT', 'INT', '90081', '91', 'CAPS 1999')"
	)
	index = records.code_index("paint")
	assert [(e.code, e.description, e.total) for e in index] == [
		("R25", "Morocco Red", 3),
		("T87", "Fiji Blue", 5),
		("XXX", MISSING, 1),
	]
	assert index[0].by_model == (ModelCount("Stealth", 2), ModelCount("3000GT", 1))
	assert "INT" not in {e.code for e in records.code_index("interior")}
	assert "EQU" not in {e.code for e in records.code_index("option")}


def test_the_option_index_is_per_model_code(records):
	assert [(e.model_code, e.code, e.total) for e in records.code_index("option")] == [
		("Z16A", "XA1", 6),
		("Z16D", "XA1", 2),
		("Z16X", "QQQ", 1),
	]


def test_the_interior_index(records):
	assert [(e.code, e.description, e.total) for e in records.code_index("interior")] == [
		("12A", "Grey", 8),
		("99Z", MISSING, 1),
	]


def test_a_page_as_dict_names_its_lines(records):
	data = records.code_page("paint", "T87").as_dict()
	assert data["by_line"] == [
		{
			"manufacturer": "Mitsubishi",
			"model": "3000GT",
			"trim": "VR-4",
			"model_code": "Z16A",
			"count": 5,
			"name": "Mitsubishi 3000GT VR-4",
		}
	]
	assert data["names"][0] == {"manufacturer": "Mitsubishi", "name": "Fiji Blue"}


def test_a_story_carries_its_model_code_for_option_links(connection, records):
	add_gto(connection)
	assert records.story(GTO).model_code == "Z16A"
	assert records.story("JA3AM84J3NY000004").as_dict()["model_code"] == "Z16A"
