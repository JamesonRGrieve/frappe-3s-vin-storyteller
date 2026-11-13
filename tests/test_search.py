# SPDX-License-Identifier: AGPL-3.0-or-later
"""Car search on the stats page, against the real migrated SQLite database (conftest.py): full VINs, every
provenance, regions named as the charts name them."""

import sqlite3
from contextlib import contextmanager

import pytest

from vin_storyteller.answer import SEARCH_TOO_BROAD, RecordsUnavailable, search_answer
from vin_storyteller.records import add_record
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.search import InvalidSearch, SearchQuery, parse_query


@pytest.fixture
def records(connection):
	return ProductionRecords(connection, "qmark")


def run(records, **params):
	@contextmanager
	def session():
		yield records

	return search_answer(params, session, (sqlite3.Error,))


def test_queries_parse_and_refuse_what_isnt_a_search():
	q = parse_query(
		{"q": " ja3am84j3ny ", "model": "3000GT,GTO", "from": "1992", "paint": "t87", "page": "2"}
	)
	assert q == SearchQuery(
		text="JA3AM84J3NY", models=("3000GT", "GTO"), year_from="1992", paint="T87", page=2
	)
	assert q.model_years() == ("92", "93", "94", "95", "96", "97", "98", "99", "00")
	for bad in ({"q": "<b>"}, {"from": "19x2"}, {"model": "Diamante"}, {"paint": "TOOLONG"}, {"page": "x"}):
		with pytest.raises(InvalidSearch):
			parse_query(bad)
	assert not parse_query({}).narrowed


def test_a_vin_fragment_finds_full_vins_with_their_region(records):
	body = run(records, q="NY00000")
	assert body["status"] == "found" and body["total"] == 6  # JA3…NY000001-5 and 000009 (1992)
	car = body["cars"][0]
	assert car["vin"] == "JA3AM84J3NY000001"  # never censored
	assert (car["model_year"], car["model"], car["paint"], car["interior"]) == (
		"1992",
		"3000GT",
		"T87",
		"12A",
	)
	assert car["region"] and car["market"] == "North America"
	assert car["provenance"] == "CAPS 1999"


def test_filters_combine_and_codes_match(records):
	assert run(records, paint="R25")["total"] == 3
	assert run(records, paint="R25", model="Stealth")["total"] == 2
	assert run(records, q="R25", model="Stealth", to="1992")["total"] == 2
	assert run(records, interior="99Z")["total"] == 1
	assert run(records, model="3000GT", **{"from": "1991", "to": "1991"})["total"] == 1
	assert run(records, market="Japan")["total"] == 0


def test_every_provenance_is_found_and_labelled(connection, records):
	add_record(connection, "Z16A-0011452", "Mitsubishi recall 1153", "qmark")
	(car,) = run(records, q="Z16A-0011452")["cars"]
	assert car["provenance"] == "Mitsubishi recall 1153" and car["region"] == "Japan"


def test_paging(records, monkeypatch):
	import vin_storyteller.repository as repository

	monkeypatch.setattr(repository, "PAGE_SIZE", 4)
	first = records.search_cars(SearchQuery(text="JA3", page=1))
	second = records.search_cars(SearchQuery(text="JA3", page=2))
	assert len(first[0]) == 4 and len(second[0]) == 3 and first[1] == second[1] == 7
	assert not {c.vin for c in first[0]} & {c.vin for c in second[0]}


def test_an_open_or_invalid_search_is_refused_and_errors_surface(records):
	assert run(records) == {"status": "invalid", "message": SEARCH_TOO_BROAD}
	assert run(records, q="!")["status"] == "invalid"

	@contextmanager
	def broken():
		raise sqlite3.OperationalError("down")
		yield

	with pytest.raises(RecordsUnavailable):
		search_answer({"q": "JA3"}, broken, (sqlite3.Error,))


def test_results_run_in_calendar_order(connection, records):
	connection.execute(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, Interior, "
		"DateOfManufacture, ModelYear, Provenance) VALUES ('0600161', 'Z15A-0600161', 'G5', 'Z15A', 'MNPM', '004', "
		"'T87', '12A', '00013', '00', 'ASA Japan 2008')"
	)
	years = [c["model_year"] for c in run(records, paint="T87")["cars"]]
	assert years == sorted(years) and years[-1] == "2000"


# Known missing VIN ranges (migration 0011): shown red so owners can send their VIN tag.


def test_a_full_vin_inside_a_known_gap_comes_back_missing(records):
	body = run(
		records, q="JB3AN74K9SY008484"
	)  # a 1995 gap serial (found at a Copart auction, not yet loaded)
	assert body["cars"] == [] and body["missing_total"] == 1
	(gap,) = body["missing"]
	assert gap["vin"] == "JB3AN74K9SY008484" and gap["model_year"] == "1995" and gap["market"] == "us"
	assert "Stealth R/T Turbo" in gap["note"]
	assert run(records, q="JB3AN74K9MY008484")["missing_total"] == 0  # 1991 has that serial on record


def test_a_serial_alone_finds_its_gaps_and_filters_narrow_them(records):
	body = run(records, q="000600")
	assert {(g["model_year"], g["vin"]) for g in body["missing"]} >= {("1991", "J*3******MY000518-000704")}
	assert run(records, q="000600", model="GTO")["missing_total"] == 0
	assert run(records, q="000600", market="Japan")["missing_total"] == 0


def test_missing_only_lists_the_gaps_the_filters_cover(records):
	body = run(records, missing="1", **{"from": "1995", "to": "1995"})
	assert body["cars"] == [] and body["missing_total"] > 1000
	assert {g["model_year"] for g in body["missing"]} <= {"1995", ""}
	assert len(body["missing"]) <= 500
	australia = run(records, missing="1", market="Australia")
	assert australia["missing"] and {g["market"] for g in australia["missing"]} == {"au"}
	assert all(g["vin"].startswith("JMFJF5S24*J") for g in australia["missing"])
	assert run(records, missing="1", **{"from": "1997", "to": "1997"})["missing_total"] == 0


def test_an_australian_vin_in_a_gap_and_a_car_on_record_is_never_missing(records):
	assert run(records, q="JMFJF5S24NJ000002")["missing"][0]["market"] == "au"
	assert run(records, q="JA3AM84J3NY000001")["missing_total"] == 0


# Sort, model line and build-period filters, breakdowns and CSV (card 391).


def test_sorting_and_order(records):
	cars = run(records, q="JA3", sort="vin", desc="1")["cars"]
	vins = [c["vin"] for c in cars]
	assert vins == sorted(vins, reverse=True)
	built = [c["built"] for c in run(records, q="JA3", sort="built")["cars"]]
	assert built == sorted(built, key=lambda b: ("1" if b[:2] < "50" else "0") + b)
	with pytest.raises(InvalidSearch):
		parse_query({"q": "JA3", "sort": "price"})


def test_a_model_line_and_a_build_period_narrow_a_search(records):
	every = run(records, q="JA3")["cars"]
	line = every[0]["line_code"]
	assert line and all(c["line_code"] == line for c in run(records, line=line)["cars"])
	period = every[0]["built"]
	same = run(records, built=period)["cars"]
	assert same and all(c["built"] == period for c in same)
	month = run(records, built_from=period[:4], built_to=period[:4])["cars"]
	assert {c["vin"] for c in same} <= {c["vin"] for c in month}
	assert all(c["built"][:4] == period[:4] for c in month)
	for bad in ({"line": "VR4"}, {"built": "9213"}, {"built_from": "x"}):
		with pytest.raises(InvalidSearch):
			parse_query(bad)
	assert parse_query({"line": "vr"}).narrowed and parse_query({"built": "92031"}).narrowed


def test_a_build_range_runs_across_the_year_2000():
	from vin_storyteller.search import in_built_range

	assert in_built_range("00013", "9901", "0012")
	assert in_built_range("99121", "9901", "0012")
	assert not in_built_range("98121", "9901", "0012")
	assert in_built_range("92031", "", "")
	assert not in_built_range("", "9201", "")


def test_a_search_breaks_down_by_spec_with_shares(records):
	body = run(records, paint="R25")
	shares = body["breakdown"]
	assert set(shares) == {"paint", "interior", "option", "grade", "line", "model_year", "region"}
	for facet in shares.values():
		assert sum(s["count"] for s in facet) == body["total"]
		assert abs(sum(s["percent"] for s in facet) - 100) < 1
	(paint,) = shares["paint"]
	assert paint["code"] == "R25" and paint["count"] == 3


def test_a_search_downloads_as_csv(records):
	from vin_storyteller.answer import search_csv
	from vin_storyteller.search import CSV_COLUMNS

	@contextmanager
	def session():
		yield records

	filename, text = search_csv({"paint": "R25"}, session, (sqlite3.Error,))
	lines = text.strip().split("\n")
	assert filename.endswith(".csv") and lines[0].split(",") == list(CSV_COLUMNS) and len(lines) == 4
	assert search_csv({}, session, (sqlite3.Error,))["status"] == "invalid"


def test_a_storys_spec_twins_and_build_period_are_searches_that_agree_with_its_counts(records):
	"""The story links to these searches (card 391): their totals must be the story's own counts."""
	for vin in ("JA3AM84J3NY000001", "JA3AM84J3NY000004"):
		story = records.story(vin)
		year = story.model_year
		twins = run(
			records,
			line=story.line_code,
			paint=story.exterior.code,
			exact="1",
			interior=story.interior.code,
			option=story.equipment.code,
			**{"from": year, "to": year},
		)
		assert twins["total"] == story.among_identical.total
		assert vin in {c["vin"] for c in twins["cars"]}
		period = run(records, built=story.built_code, series=story.series)
		assert period["total"] == story.built_in_period
		assert all(c["built"] == story.built_code for c in period["cars"]) and vin in {
			c["vin"] for c in period["cars"]
		}
		month = run(records, built=story.built_code[:4], series=story.series)
		assert month["total"] == story.built_in_month


def test_an_exact_paint_search_leaves_out_the_paints_other_codes(records):
	assert parse_query({"paint": "W75", "exact": "1"}).exact_paint
	assert parse_query({"series": "JDM"}).series == "jdm"
	with pytest.raises(InvalidSearch):
		parse_query({"series": "mars"})
	assert run(records, paint="R25", exact="1")["total"] <= run(records, paint="R25")["total"]
