# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the storyteller answers for a VIN, independent of Frappe so it can be tested on any database.

`answer` takes a factory that opens a ProductionRecords session (as a context manager) and the exception
types that mean the database could not be read; the Frappe endpoint in api.py supplies PyMySQL for both.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import (
	CHASSIS_NOT_ON_RECORD,
	InvalidVin,
	is_chassis_number,
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
	if is_chassis_number(raw_vin):
		return {"status": "not_found", "message": CHASSIS_NOT_ON_RECORD}
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
