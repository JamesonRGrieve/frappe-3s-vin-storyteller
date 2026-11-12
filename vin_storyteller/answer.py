# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the storyteller answers for a VIN, independent of Frappe so it can be tested on any database.

`answer` takes a factory that opens a ProductionRecords session (as a context manager) and the exception
types that mean the database could not be read; the Frappe endpoint in api.py supplies PyMySQL for both.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict

from vin_storyteller.repository import ProductionRecords
from vin_storyteller.search import PAGE_SIZE, InvalidSearch, parse_query
from vin_storyteller.stats import build_stats
from vin_storyteller.story import (
	CHASSIS_NOT_ON_RECORD,
	CODE_KINDS,
	EXPORT_NOT_ON_RECORD,
	InvalidCode,
	InvalidVin,
	is_chassis_number,
	is_frame_number,
	normalize_chassis,
	normalize_code,
	normalize_frame,
	normalize_model_code,
	normalize_vin,
	not_found_message,
)

INVALID = "Please enter a valid 17 character VIN. VINs never contain the letters I, O or Q."
NOT_FOUND = (
	"According to our records, that VIN does not belong to a Mitsubishi 3000GT or Dodge Stealth. "
	"Please check your input (remember, VINs never have O's, Q's or I's because they look like 0's and 1's). "
	"If you're sure it is correct, your vehicle may be a 'lost VIN', please email storyteller@3shub.com with your VIN."
)
UNAVAILABLE = "The storyteller is unavailable right now. Please try again later."


class RecordsUnavailable(Exception):
	"""The production record could not be read; the caller logs the cause."""


def answer(
	raw_vin: str | None,
	open_records: Callable[[], AbstractContextManager[ProductionRecords]],
	database_errors: tuple[type[BaseException], ...],
) -> dict:
	"""The API response body for `raw_vin`: status invalid | not_found | found (with the story)."""
	if is_chassis_number(raw_vin) or is_frame_number(raw_vin):
		chassis_number = is_chassis_number(raw_vin)
		key = normalize_chassis(raw_vin) if chassis_number else normalize_frame(raw_vin)
		try:
			with open_records() as records:
				story = records.story(key)
		except database_errors as error:
			raise RecordsUnavailable from error
		if story is None:
			message = (
				CHASSIS_NOT_ON_RECORD if chassis_number else EXPORT_NOT_ON_RECORD.format(kind="frame number")
			)
			return {"status": "not_found", "message": message}
		return {"status": "found", "story": story.as_dict()}
	try:
		vin = normalize_vin(raw_vin)
	except InvalidVin:
		return {"status": "invalid", "message": INVALID}
	try:
		with open_records() as records:
			story = records.story(vin)
			gap = records.gap(vin) if story is None else None
	except database_errors as error:
		raise RecordsUnavailable from error
	if story is None:
		return {"status": "not_found", "message": not_found_message(vin, gap) or NOT_FOUND}
	return {"status": "found", "story": story.as_dict()}


# Per-code pages (card 330).
CODE_INVALID = (
	"That isn't a paint, interior or option code: codes are two to four letters and digits, and an option code "
	"goes with its chassis model code (e.g. Z16A)."
)
CODE_NOT_FOUND = "No car in Mitsubishi's factory records carries that code."
KINDS_INVALID = "There are code pages for paint, interior and option codes only."


def code_request(
	kind: str | None, raw_code: str | None, raw_model: str | None = None
) -> tuple[str, str, str]:
	"""(kind, code, model code) in canonical form, or InvalidCode. Only an option code takes a model code."""
	if kind not in CODE_KINDS:
		raise InvalidCode(kind)
	code = normalize_code(kind, raw_code)
	return kind, code, normalize_model_code(raw_model) if kind == "option" else ""


def page_key(kind: str | None, raw_code: str | None, raw_model: str | None = None) -> str | None:
	"""The cache key of a code page's answer, or None for a request that is no code page."""
	try:
		return ":".join(code_request(kind, raw_code, raw_model))
	except InvalidCode:
		return None


def code_answer(
	kind: str | None,
	raw_code: str | None,
	raw_model: str | None,
	open_records: Callable[[], AbstractContextManager[ProductionRecords]],
	database_errors: tuple[type[BaseException], ...],
) -> dict:
	"""The API response body for a code page: status invalid | not_found | found (with the page)."""
	try:
		kind, code, model_code = code_request(kind, raw_code, raw_model)
	except InvalidCode:
		return {"status": "invalid", "message": CODE_INVALID}
	try:
		with open_records() as records:
			page = records.code_page(kind, code, model_code)
	except database_errors as error:
		raise RecordsUnavailable from error
	if page is None:
		return {"status": "not_found", "message": CODE_NOT_FOUND}
	return {"status": "found", "page": page.as_dict()}


def index_answer(
	kind: str | None,
	open_records: Callable[[], AbstractContextManager[ProductionRecords]],
	database_errors: tuple[type[BaseException], ...],
) -> dict:
	"""The API response body for a kind's index: every code with its total and models."""
	if kind not in CODE_KINDS:
		return {"status": "invalid", "message": KINDS_INVALID}
	try:
		with open_records() as records:
			entries = records.code_index(kind)
	except database_errors as error:
		raise RecordsUnavailable from error
	return {"status": "found", "kind": kind, "codes": [asdict(e) for e in entries]}


# The production statistics page.
STATS_EMPTY = "There are no factory records to count yet."


def stats_answer(
	open_records: Callable[[], AbstractContextManager[ProductionRecords]],
	database_errors: tuple[type[BaseException], ...],
) -> dict:
	"""The API response body for the stats page: status found (with the stats) | not_found."""
	try:
		with open_records() as records:
			rows = records.stats_rows()
			catalogue = records.stats_catalogue()
	except database_errors as error:
		raise RecordsUnavailable from error
	if not rows:
		return {"status": "not_found", "message": STATS_EMPTY}
	return {"status": "found", "stats": build_stats(rows, catalogue)}


# Car search on the stats page.
SEARCH_TOO_BROAD = "Narrow the search: give part of a VIN, a code, a model, a year or a region."


def search_answer(
	params: dict,
	open_records: Callable[[], AbstractContextManager[ProductionRecords]],
	database_errors: tuple[type[BaseException], ...],
) -> dict:
	"""The API response body for a car search: status found (cars, total, page, pages, truncated) | invalid."""
	try:
		query = parse_query(params)
	except InvalidSearch as error:
		return {"status": "invalid", "message": str(error)}
	if not query.narrowed:
		return {"status": "invalid", "message": SEARCH_TOO_BROAD}
	try:
		with open_records() as records:
			if query.missing_only:
				cars, total, truncated = (), 0, False
			else:
				cars, total, truncated = records.search_cars(query)
			missing, missing_total = records.missing_ranges(query)
	except database_errors as error:
		raise RecordsUnavailable from error
	return {
		"status": "found",
		"total": total,
		"page": query.page,
		"pages": max(1, -(-total // PAGE_SIZE)),
		"truncated": truncated,
		"cars": [asdict(car) for car in cars],
		"missing": [asdict(entry) for entry in missing],
		"missing_total": missing_total,
	}
