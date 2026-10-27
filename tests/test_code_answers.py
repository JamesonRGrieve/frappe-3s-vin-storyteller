# SPDX-License-Identifier: AGPL-3.0-or-later
"""The API answers for code pages and indexes, end to end against the real SQLite production record, and the pure
code rules they rest on."""

import sqlite3
from contextlib import contextmanager

import pytest

from vin_storyteller.answer import (
	CODE_INVALID,
	CODE_NOT_FOUND,
	KINDS_INVALID,
	RecordsUnavailable,
	code_answer,
	code_request,
	index_answer,
	page_key,
)
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import (
	MISSING,
	InvalidCode,
	LineRow,
	MakerName,
	ModelCount,
	YearCount,
	build_span,
	normalize_code,
	normalize_model_code,
	paint_names,
	tally,
)

DB_ERRORS = (sqlite3.Error,)


@pytest.fixture
def open_records(connection):
	@contextmanager
	def opener():
		yield ProductionRecords(connection, paramstyle="qmark")

	return opener


def never_opened():
	raise AssertionError("the database must not be opened for an invalid request")


def test_a_paint_page(open_records):
	body = code_answer("paint", " t87 ", None, open_records, DB_ERRORS)
	assert body["status"] == "found"
	page = body["page"]
	assert (page["kind"], page["code"], page["total"], page["description"]) == (
		"paint",
		"T87",
		5,
		"Fiji Blue",
	)
	assert page["by_year"] == ({"model_year": "1991", "count": 1}, {"model_year": "1992", "count": 4})
	assert page["pairings"] == ({"code": "12A", "description": "Grey", "count": 5},)


def test_an_option_page_needs_its_model_code(open_records):
	assert code_answer("option", "XA1", "z16a", open_records, DB_ERRORS)["page"]["model_code"] == "Z16A"
	assert code_answer("option", "XA1", None, never_opened, DB_ERRORS) == {
		"status": "invalid",
		"message": CODE_INVALID,
	}


def test_a_paint_page_ignores_a_model_code(open_records):
	assert code_answer("paint", "T87", "Z16A", open_records, DB_ERRORS)["page"]["model_code"] == ""


@pytest.mark.parametrize(
	("kind", "code"),
	[
		("paint", ""),
		("paint", None),
		("paint", "T8&7"),
		("paint", "TOOLONG"),
		("wheels", "T87"),
		(None, "T87"),
	],
)
def test_an_invalid_request_never_touches_the_database(kind, code):
	assert code_answer(kind, code, None, never_opened, DB_ERRORS) == {
		"status": "invalid",
		"message": CODE_INVALID,
	}


@pytest.mark.parametrize(("kind", "placeholder"), [("paint", "EXT"), ("interior", "INT"), ("option", "EQU")])
def test_a_not_recorded_placeholder_is_no_code(kind, placeholder):
	assert code_answer(kind, placeholder, "Z16A", never_opened, DB_ERRORS)["status"] == "invalid"


def test_a_code_nobody_carries(open_records):
	assert code_answer("interior", "77Q", None, open_records, DB_ERRORS) == {
		"status": "not_found",
		"message": CODE_NOT_FOUND,
	}


def test_an_index(open_records):
	body = index_answer("paint", open_records, DB_ERRORS)
	assert body["status"] == "found" and body["kind"] == "paint"
	assert body["codes"][0] == {
		"code": "R25",
		"model_code": "",
		"description": "Morocco Red",
		"total": 3,
		"by_model": ({"model": "Stealth", "count": 2}, {"model": "3000GT", "count": 1}),
	}
	assert index_answer("wheels", never_opened, DB_ERRORS) == {"status": "invalid", "message": KINDS_INVALID}


def test_database_failures_surface_as_unavailable():
	@contextmanager
	def broken():
		raise sqlite3.OperationalError("down")
		yield

	with pytest.raises(RecordsUnavailable):
		code_answer("paint", "T87", None, broken, DB_ERRORS)
	with pytest.raises(RecordsUnavailable):
		index_answer("paint", broken, DB_ERRORS)


def test_page_keys_are_canonical():
	assert page_key("paint", " t87", "Z16A") == "paint:T87:"
	assert page_key("option", "302", "z16a") == "option:302:Z16A"
	assert page_key("option", "302", "") is None
	assert page_key("paint", "<script>", None) is None
	assert code_request("interior", "12a") == ("interior", "12A", "")


def test_normalize_code():
	assert normalize_code("paint", " w75 ") == "W75"
	assert normalize_code("option", "01Z") == "01Z"
	for kind, bad in [
		("paint", "W"),
		("paint", "W75AB"),
		("paint", "W-5"),
		("paint", "EXT"),
		("seat", "W75"),
	]:
		with pytest.raises(InvalidCode):
			normalize_code(kind, bad)


def test_normalize_model_code():
	assert normalize_model_code(" z11a") == "Z11A"
	for bad in [None, "", "Z11", "Z11AA", "1Z1A", "Z-1A"]:
		with pytest.raises(InvalidCode):
			normalize_model_code(bad)


def test_build_span_runs_in_calendar_order():
	assert build_span(["92032", "00011", "99121", "90101"]) == ("90101", "00011")
	assert build_span(["", "BAD", "92034"]) is None
	assert build_span([]) is None


def test_tally():
	counts = tally(
		[
			LineRow("92", "Mitsubishi", "3000GT", "VR4", "Z16A", 3),
			LineRow("93", "Mitsubishi", "3000GT", "VR4", "Z16A", 2),
			LineRow("92", "Dodge", "Stealth", "R/T Twin Turbo", "Z16A", 4),
			LineRow("00", "Mitsubishi", "GTO", "", "Z16A", 1),
			LineRow("92", None, None, None, "Z16X", 1),
		]
	)
	assert counts.total == 11
	assert counts.by_model == (
		ModelCount("3000GT", 5),
		ModelCount("Stealth", 4),
		ModelCount("GTO", 1),
		ModelCount("Other", 1),
	)
	assert counts.by_year == (YearCount("1992", 8), YearCount("1993", 2), YearCount("2000", 1))
	assert [(line.name, line.count) for line in counts.by_line] == [
		("Mitsubishi 3000GT VR4", 5),
		("Dodge Stealth R/T Twin Turbo", 4),
		("Mitsubishi GTO", 1),
		("Other", 1),
	]


def test_paint_names():
	assert paint_names("Fiji Blue", "Bright Blue") == (
		"Fiji Blue",
		(MakerName("Mitsubishi", "Fiji Blue"), MakerName("Dodge", "Bright Blue")),
	)
	assert paint_names(MISSING, "Fire Storm") == ("Fire Storm", (MakerName("Dodge", "Fire Storm"),))
	assert paint_names(MISSING, MISSING) == (MISSING, ())
	assert paint_names(None, None) == (MISSING, ())
