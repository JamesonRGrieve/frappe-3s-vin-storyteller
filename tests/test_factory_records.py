# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every factory build as a full story (CAPS 1999, CAPS 2004, ASA Japan 2008), the cross-model breakdowns and
Mitsubishi's own code labels, against the real migrated SQLite database (conftest.py)."""

import pytest

from vin_storyteller.records import RecordRefused, add_record
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import ASA_JAPAN, ASA_USA, MISSING, Coded, ModelCount, full_year

# A JDM GTO from the ASA Japan catalogue, sharing the 1992 fixture cars' colour (T87) and interior (12A).
GTO = "Z16A-0014160"


def add_gto(
	connection, chassis=GTO, serial="0014160", built="92032", year="92", exterior="T87", option="302"
):
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES (?, ?, 'G6', 'Z16A', 'MNGF', ?, ?, '12A', ?, ?, ?)",
		(serial, chassis, option, exterior, built, year, ASA_JAPAN),
	)


@pytest.fixture
def records(connection):
	return ProductionRecords(connection, "qmark")


def test_an_asa_gto_tells_a_full_story(connection, records):
	add_gto(connection)
	story = records.story(GTO)
	assert not story.partial and story.provenance == ASA_JAPAN
	assert story.vehicle_name == "1992 Mitsubishi GTO"
	assert story.built == "the 2nd production period of March, 1992"


def test_positions_stay_within_their_market(connection, records):
	"""A GTO never shifts a North American car's count, and its own positions count GTOs only."""
	before = records.story("JA3AM84J3NY000004")
	add_gto(connection)
	add_gto(connection, "Z16A-0014161", "0014161")
	after = records.story("JA3AM84J3NY000004")
	assert (after.in_year, after.built_in_period, after.in_colour) == (
		before.in_year,
		before.built_in_period,
		before.in_colour,
	)
	gto = records.story("Z16A-0014161")
	assert (gto.in_year.position, gto.in_year.total, gto.built_in_period) == (2, 2, 2)


def test_breakdowns_span_every_model(connection, records):
	add_gto(connection)
	story = records.story("JA3AM84J3NY000004")
	by_scope = {b.scope: b for b in story.breakdowns}
	# 1992 fixture cars: 3000GTs 000001-000005 (four in T87), Stealths 000006/000007 (R25); the GTO in T87.
	assert by_scope["colour_year"].by_model == (ModelCount("3000GT", 4), ModelCount("GTO", 1))
	assert by_scope["colour_year"].total == 5
	assert by_scope["period"].by_model == (
		ModelCount("3000GT", 2),
		ModelCount("GTO", 1),
		ModelCount("Stealth", 1),
	)
	# Every 12A car of a named model: six 3000GTs (1992's five and 1991's), one Stealth and the GTO. The fixture's
	# unknown model code (ZZ) names no model, so it isn't counted.
	assert by_scope["interior"].by_model == (
		ModelCount("3000GT", 6),
		ModelCount("GTO", 1),
		ModelCount("Stealth", 1),
	)


def test_a_model_without_a_name_is_left_out_of_breakdowns(connection, records):
	"""Only 3000GT, Stealth and GTO are counted; a model the Model table names MISSING never appears."""
	connection.execute("INSERT INTO Model VALUES ('XX', 'MISSING', 'MISSING', 'MISSING')")
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES ('NY900001', 'JA3AP47H0NY900001', 'XX', 'F16A', 'TRHEL2M', "
		"'A00', 'T87', '12A', '92032', '92', 'CAPS 1999')"
	)
	by_scope = {b.scope: b for b in records.story("JA3AM84J3NY000004").breakdowns}
	assert all(c.model not in ("MISSING", "Other") for b in by_scope.values() for c in b.by_model)
	assert sum(c.count for c in by_scope["period"].by_model) == by_scope["period"].total


def test_breakdowns_skip_colours_not_on_record(connection, records):
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES ('MY003000', 'JA3XE74C9MY003000', 'M1', 'Z16A', 'MNGFL7M', "
		"'A07', 'EXT', 'INT', '90081', '91', 'CAPS 1999')"
	)
	scopes = {b.scope for b in records.story("JA3XE74C9MY003000").breakdowns}
	assert scopes == {"year", "period", "month"}


def test_other_sources_never_count_in_a_breakdown(connection, records):
	add_record(connection, "Z16A-0011452", "Mitsubishi recall 1153", "qmark")
	by_scope = {b.scope: b for b in records.story("JA3AM84J3NY000004").breakdowns}
	assert all(c.model != "GTO" for c in by_scope["year"].by_model)


def test_as_dict_carries_breakdowns_with_descriptions(connection, records):
	add_gto(connection)
	data = records.story(GTO).as_dict()
	colour = next(b for b in data["breakdowns"] if b["scope"] == "colour")
	assert colour["description"] == "in the same exterior colour, every year"
	assert {"model": "GTO", "count": 1} in colour["by_model"]


def labels(connection):
	connection.executemany(
		"INSERT INTO ClassificationLabel (Source, ModelCode, Classification, Language, Description, Destination) "
		"VALUES (?, ?, ?, 'en', ?, ?)",
		[
			("ASA Japan 2008", "Z16A", "MNGF", "GTO TWIN-TURBO,5FM/T", ""),
			("CAPS 2004", "Z16A", "MJGFL7M", "ULTIMATE LINE,6FM/T", "CAL53H"),
		],
	)
	connection.execute(
		"INSERT INTO OptionContent (Source, ModelCode, OptionCode, Classification, ModelYear, StartDate, EndDate, "
		"Items) VALUES ('ASA Japan 2008', 'Z16A', '302', 'MNGF', '92', '1992011', '1992093', 'K03,J50,ZZ1')"
	)
	connection.executemany(
		"INSERT INTO OptionItem (Source, ItemCode, Language, Description) VALUES ('ASA Japan 2008', ?, 'en', ?)",
		[("K03", "LEATHER SEAT & ROOM TRIM"), ("J50", "CD AUTO CHANGER")],
	)


def test_classification_and_equipment_items_come_from_the_catalogue(connection, records):
	labels(connection)
	add_gto(connection)
	story = records.story(GTO)
	assert story.classification == Coded("MNGF", "GTO TWIN-TURBO,5FM/T")
	assert story.equipment_items == (
		Coded("K03", "LEATHER SEAT & ROOM TRIM"),
		Coded("J50", "CD AUTO CHANGER"),
		Coded("ZZ1", MISSING),
	)


def test_a_destination_variant_falls_back_to_its_grade(connection, records):
	"""CAPS splits a grade by destination (MJGFL2M federal, MJGFL7M California): the first four characters name it."""
	labels(connection)
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES ('NY004600', 'JA3AN74K3NY004600', 'M1', 'Z16A', "
		"'MJGFL2M', 'XA1', 'T87', '12A', '92033', '92', 'CAPS 1999')"
	)
	story = records.story("JA3AN74K3NY004600")
	assert story.classification == Coded("MJGFL2M", "ULTIMATE LINE,6FM/T")
	assert story.equipment_items == ()


def test_an_unlabelled_grade_reads_as_not_decoded(records):
	assert records.story("JA3AM84J3NY000004").classification == Coded("CLASS01", MISSING)


def test_the_last_gtos_are_2000_model_years():
	assert full_year("00") == "2000" and full_year("99") == "1999"


@pytest.mark.parametrize(
	"provenance", ["ASA Japan 2008", "asa japan 2008", "CAPS 2004", "CAPS 1999", "CAPS", "ASA USA 2007"]
)
def test_factory_build_names_are_reserved(connection, provenance):
	with pytest.raises(RecordRefused, match="factory"):
		add_record(connection, "Z16A-0011452", provenance, "qmark")


def test_a_gto_on_record_is_not_a_gap_neighbour(connection, records):
	add_gto(connection, "Z16A-0000010", "0000010", built="92011")
	gap = records.gap("JA3AM84J3NY000010")
	assert gap.before.serial == "000009"


def test_production_start_is_calendar_order_across_the_century(connection, records):
	"""A 2000 model year started in 1999: '99071' is earlier than '00011', though it sorts later as text."""
	add_gto(connection, "Z15A-0600101", "0600101", built="99071", year="00")
	add_gto(connection, "Z15A-0600102", "0600102", built="00011", year="00")
	story = records.story("Z15A-0600102")
	assert story.year_started == "the 1st production period of July, 1999"
	assert story.model_started == "the 1st production period of July, 1999"


def test_a_paints_a_form_counts_with_it_in_breakdowns_and_pages(connection, records):
	"""CAPS writes some early paints as an "A" form (TA7) that ASA records as the paint code (T87): one paint."""
	connection.execute(
		"INSERT INTO PaintAlias (Code, PaintCode, Source) VALUES ('TA7', 'T87', 'ASA USA 2007')"
	)
	add_gto(connection, exterior="TA7")
	story = records.story("JA3AM84J3NY000004")  # a T87 car
	colour = {b.scope: b for b in story.breakdowns}["colour"]
	assert ModelCount("GTO", 1) in colour.by_model  # the TA7 GTO is the same paint
	page = records.code_page("paint", "T87")
	assert page.same_paint == ("TA7",) and any(c.model == "GTO" for c in page.by_model)
	assert records.code_page("paint", "TA7").total == page.total
	index = {e.code: e for e in records.code_index("paint")}
	assert "TA7" not in index and index["T87"].total == page.total
	assert story.in_colour == records.story("JA3AM84J3NY000004").in_colour  # positions stay exact


def test_an_asa_usa_car_is_a_factory_record_counted_with_the_us_cars(connection, records):
	"""JA3AN74K2SY018786 is in ASA USA 2007 but neither CAPS build: a full story, counted in its US year."""
	before = records.story("JA3AM84J3NY000004").in_year.total
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES ('NY004601', 'JA3AN74K9NY004601', 'M1', 'Z16A', "
		"'MJGFL2M', 'XA1', 'T87', '12A', '92033', '92', ?)",
		(ASA_USA,),
	)
	story = records.story("JA3AN74K9NY004601")
	assert not story.partial and story.provenance == ASA_USA
	assert records.story("JA3AM84J3NY000004").in_year.total == before + 1
