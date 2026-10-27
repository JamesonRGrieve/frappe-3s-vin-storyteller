# SPDX-License-Identifier: AGPL-3.0-or-later
"""Export-market 3000GTs from ASA General (card 331): 17-character JMA/JMY VINs and 14-character frame numbers, told
as full stories and counted within their own market."""

import sqlite3

import pytest

from vin_storyteller.answer import answer
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import ASA_GENERAL, is_frame_number, market_of, normalize_frame, not_found_message

EXPORT_VIN = "JMAMJZ16AVY000101"
FRAME = "DMNZ16APY00001"


def add_export(connection, key, serial, model="ER", built="96123", year="97", interior="51H"):
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES (?, ?, ?, 'Z16A', 'MJGFR6', 'T01', 'T87', ?, ?, ?, ?)",
		(serial, key, model, interior, built, year, ASA_GENERAL),
	)


@pytest.fixture
def records(connection):
	return ProductionRecords(connection, "qmark")


def test_an_export_car_tells_a_full_story(connection, records):
	add_export(connection, EXPORT_VIN, "VY000101")
	story = records.story(EXPORT_VIN)
	assert not story.partial and story.provenance == ASA_GENERAL
	assert story.vehicle_name == "1997 Mitsubishi 3000GT Twin Turbo (RHD)"


def test_export_cars_count_within_their_own_market(connection, records):
	before = records.story("JA3AM84J3NY000004")
	add_export(connection, EXPORT_VIN, "VY000101", built="92032", year="92")
	add_export(connection, FRAME, "PY00001", model="EL", built="92032", year="92")
	after = records.story("JA3AM84J3NY000004")
	assert (after.in_year, after.built_in_period) == (before.in_year, before.built_in_period)
	export = records.story(FRAME)
	assert (export.in_year.total, export.built_in_period) == (2, 2)
	period = {b.scope: b for b in after.breakdowns}["period"]
	assert period.total == before.built_in_period + 2  # the cross-model breakdown spans every market


def test_a_car_with_no_interior_on_record_has_no_interior_breakdowns(connection, records):
	add_export(connection, FRAME, "PY00001", model="EL", interior="")
	story = records.story(FRAME)
	assert story.interior.code == ""
	assert {b.scope for b in story.breakdowns}.isdisjoint({"interior", "colours"})


@pytest.mark.parametrize("raw", ["DMNZ16APY00001", "dmnz16a-py00001", "MNZ16AVY000101", " CMNZ16A PY00101 "])
def test_frame_numbers_are_recognised(raw):
	assert is_frame_number(raw)


@pytest.mark.parametrize("raw", ["DMNZ16APY0000", "Z16A-0011452", "JA3AM84J3NY000004", ""])
def test_other_keys_are_not_frame_numbers(raw):
	assert not is_frame_number(raw)


def test_markets():
	assert (market_of("ER"), market_of("EL"), market_of("G6"), market_of("VR")) == (
		"export",
		"export",
		"jdm",
		"us",
	)


def opener(connection):
	from contextlib import contextmanager

	@contextmanager
	def open_records():
		yield ProductionRecords(connection, "qmark")

	return open_records


def test_answer_finds_a_frame_number(connection):
	add_export(connection, FRAME, "PY00001", model="EL")
	body = answer(" dmnz16a-py00001 ", opener(connection), (sqlite3.Error,))
	assert body["status"] == "found" and body["story"]["vin"] == normalize_frame(FRAME)


def test_answer_explains_an_export_key_not_on_record(connection):
	body = answer("DMNZ16APY09999", opener(connection), (sqlite3.Error,))
	assert (
		body["status"] == "not_found"
		and "export-market" in body["message"]
		and "frame number" in body["message"]
	)
	assert "export-market" in not_found_message("JMAMJZ16AVY009999", None)


def feature(
	connection, start="1996061", end="1997053", item="", name="Headlamp washers", classification="MJGFR6"
):
	connection.execute(
		"INSERT INTO FactoryFeature (Source, ModelCode, Classification, StartDate, EndDate, OptionItem, Feature) "
		"VALUES ('ASA General 2008', 'Z16A', ?, ?, ?, ?, ?)",
		(classification, start, end, item, name),
	)


def test_a_factory_feature_applies_by_grade_and_build_date(connection, records):
	feature(connection)
	add_export(connection, EXPORT_VIN, "VY000101", built="96123")  # inside the window
	add_export(connection, "JMAMJZ16AWY000101", "WY000101", built="97061", year="98")  # after it
	assert records.story(EXPORT_VIN).features == ("Headlamp washers",)
	assert records.story("JMAMJZ16AWY000101").features == ()


def test_a_feature_tied_to_an_option_item_needs_that_item(connection, records):
	feature(connection, item="K03", name="Leather trim")
	connection.execute(
		"INSERT INTO OptionContent (Source, ModelCode, OptionCode, Classification, ModelYear, StartDate, EndDate, Items) "
		"VALUES ('ASA General 2008', 'Z16A', 'T01', 'MJGFR6', '97', '1996061', '1997053', 'K03,XA3')"
	)
	add_export(connection, EXPORT_VIN, "VY000101")
	assert records.story(EXPORT_VIN).features == ("Leather trim",)
	connection.execute("UPDATE OptionContent SET Items = 'XA3'")
	assert records.story(EXPORT_VIN).features == ()
