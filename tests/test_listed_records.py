# SPDX-License-Identifier: AGPL-3.0-or-later
"""Australian-delivered cars from an owners' listing (3SI's Aus-delivered list), against the real migrated SQLite
database (conftest.py): parsed from the pasted table, added as partial stories with their market and a history row
citing the listing page."""

import pytest

from vin_storyteller.answer import answer
from vin_storyteller.records import Listed, RecordRefused, add_listed_record, parse_listing
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import AUSTRALIAN_NOT_ON_RECORD, market_of

PAGE = "https://www.3si.org/threads/aus-delivered-3000gt-database.775802/page-2"
POST = """I'm trying to compile a database on all 117 of the Aussie delivered 3000GTs.
VIN\t                      Colour\tLocation
JMFJF5S24NJ000001\tRed\tWA*
JMFJF5S24NJ000003\twhite\tQLD
JMFJF5S24NJ000020\t?\tQld
JMFMNZ16ATY000102\tWhite\tQld
JMFJF5S24PJ000072 White NSW
JMFJ5S24RJ5000099\tRed\tVic
JMFJF5S24NJ000001\tRed\tWA*
"""


def test_the_listing_table_parses_once_per_vin_and_skips_malformed_vins():
	rows = parse_listing(POST, PAGE)
	assert [r.vin for r in rows] == [
		"JMFJF5S24NJ000001",
		"JMFJF5S24NJ000003",
		"JMFJF5S24NJ000020",
		"JMFMNZ16ATY000102",
		"JMFJF5S24PJ000072",
	]
	assert rows[0] == Listed("JMFJF5S24NJ000001", "Red", "WA*", PAGE)
	assert rows[2].colour == ""  # '?' is no colour


@pytest.fixture
def records(connection):
	return ProductionRecords(connection, "qmark")


def test_a_listed_car_is_a_partial_story_citing_its_listing(connection, records):
	rows = parse_listing(POST, PAGE)
	added = add_listed_record(connection, rows[0], "3SI Aus-delivered list", "3SI forum", "qmark")
	assert (added.model, added.model_year, added.model_code) == ("AU", "92", "")
	z16a = add_listed_record(connection, rows[3], "3SI Aus-delivered list", "3SI forum", "qmark")
	assert (z16a.model_code, z16a.model_year) == ("Z16A", "96")
	story = records.story("JMFJF5S24NJ000001")
	assert story.partial and story.provenance == "3SI Aus-delivered list"
	assert story.vehicle_name == "1992 Mitsubishi 3000GT"
	assert market_of("AU") == "au"
	(history,) = story.history
	assert history.url == PAGE and history.source == "3SI forum"
	assert history.title == "Listed among the Australian-delivered 3000GTs (colour Red; location WA*)"


def test_a_listed_car_is_added_once_and_only_with_a_source(connection):
	row = Listed("JMFJF5S24NJ000003", "white", "QLD", PAGE)
	add_listed_record(connection, row, "3SI Aus-delivered list", "3SI forum", "qmark")
	with pytest.raises(RecordRefused, match="already on record"):
		add_listed_record(connection, row, "3SI Aus-delivered list", "3SI forum", "qmark")
	with pytest.raises(RecordRefused, match="provenance"):
		add_listed_record(connection, Listed("JMFJF5S24NJ000005", "", "", PAGE), "CAPS 1999", "x", "qmark")
	with pytest.raises(RecordRefused, match="Australian"):
		add_listed_record(connection, Listed("JA3AM84J3NY000001", "", "", PAGE), "3SI list", "x", "qmark")


def test_listed_cars_never_count_in_the_factory_stats(connection, records):
	before = records.stats_rows()
	add_listed_record(
		connection, Listed("JMFJF5S24NJ000007", "Red", "Vic", PAGE), "3SI Aus-delivered list", "3SI", "qmark"
	)
	assert records.stats_rows() == before


def test_an_unlisted_australian_vin_gets_the_australian_answer(connection, records):
	from contextlib import contextmanager

	@contextmanager
	def session():
		yield records

	body = answer("JMFJF5S24NJ000009", session, ())
	assert body == {"status": "not_found", "message": AUSTRALIAN_NOT_ON_RECORD}
