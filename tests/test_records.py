# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from vin_storyteller.records import RecordRefused, add_record
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import CAPS, check_digit


def valid(vin):
	return vin[:8] + check_digit(vin) + vin[9:]


GAP_VIN = valid("JA3AM84J3NY000008")  # 1992, between fixture serials 000007 and 000009


def test_adds_a_partial_record_with_the_model_line_of_its_caps_twins(connection):
	added = add_record(connection, GAP_VIN, "Price label", "qmark")
	assert (added.model, added.model_code, added.model_year, added.pattern_year) == ("M1", "Z16A", "92", "92")
	row = connection.execute(
		"SELECT SerialNumber, Equipment, Exterior, Interior, DateOfManufacture, Provenance FROM Production WHERE VIN = ?",
		(GAP_VIN,),
	).fetchone()
	assert row == ("NY000008", "", "", "", "", "Price label")


def test_the_storyteller_tells_it_as_a_partial_story(connection):
	add_record(connection, GAP_VIN, "Price label", "qmark")
	story = ProductionRecords(connection, "qmark").story(GAP_VIN)
	assert story.partial and story.provenance == "Price label"
	assert story.vehicle_name == "1992 Mitsubishi 3000GT VR-4"
	assert story.built == "" and story.rarities == []


def test_caps_counts_never_include_it(connection):
	records = ProductionRecords(connection, "qmark")
	before = records.story("JA3AM84J3NY000009").in_year
	add_record(connection, GAP_VIN, "Price label", "qmark")
	assert records.story("JA3AM84J3NY000009").in_year == before


def test_a_year_with_no_caps_twin_borrows_the_nearest_year(connection):
	added = add_record(
		connection, valid("JA3AM84J3PY000001"), "Auction record", "qmark"
	)  # 1993: none in fixture
	assert (added.model, added.pattern_year) == ("M1", "92")


@pytest.mark.parametrize(
	("vin", "provenance", "reason"),
	[
		("JA3AM84J3NY000004", "Price label", "already on record"),
		(valid("JA3AM84J3NY000008")[:8] + "0" + valid("JA3AM84J3NY000008")[9:], "Price label", "check digit"),
		(valid("JA3ZZ99Z3NY000008"), "Price label", "no CAPS car shares"),
		(valid("JA3AM84J3AY000008"), "Price label", "model year"),
		(GAP_VIN, "", "provenance"),
		(GAP_VIN, CAPS, "provenance"),
	],
)
def test_refuses_what_it_cannot_ground(connection, vin, provenance, reason):
	if "check digit" in reason and check_digit(vin) == vin[8]:
		pytest.skip("the substituted digit happened to be valid")
	with pytest.raises(RecordRefused, match=reason):
		add_record(connection, vin, provenance, "qmark")
	assert connection.execute("SELECT COUNT(*) FROM Production WHERE Provenance <> 'CAPS'").fetchone()[0] == 0


def test_a_jdm_gto_is_recorded_by_its_chassis_number(connection):
	added = add_record(connection, "z16a 0011452", "Mitsubishi recall 1153", "qmark")
	assert (added.vin, added.model, added.model_code) == ("Z16A-0011452", "G6", "Z16A")
	row = connection.execute(
		"SELECT SerialNumber, ModelYear, DateOfManufacture, Provenance FROM Production WHERE VIN = 'Z16A-0011452'"
	).fetchone()
	assert row == ("0011452", "", "", "Mitsubishi recall 1153")
	with pytest.raises(RecordRefused, match="already on record"):
		add_record(connection, "Z16A-0011452", "Another source", "qmark")


def test_gap_neighbours_come_from_caps_only(connection):
	"""A car added from another source (no build date) is never named as a missing VIN's neighbour."""
	from vin_storyteller.story import Neighbour

	add_record(
		connection, GAP_VIN, "Auction record", "qmark"
	)  # serial 000008, between CAPS 000007 and 000009
	gap = ProductionRecords(connection, "qmark").gap(valid("JA3AM84J3NY000010"))
	assert gap.before == Neighbour("000009", "92033")
	gap = ProductionRecords(connection, "qmark").gap(
		valid("JA3AM84J3NY000006")
	)  # 000006 is a CAPS Dodge (1B3)
	assert gap is not None
