# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adding a car the CAPS export is missing: a real VIN proven by another source (operator, 2026-10-26).

Only what the VIN itself establishes is recorded. Its model line (Model, ModelCode, Classification) is taken
from the CAPS cars that share its first eight characters (manufacturer, line, body, engine, restraint),
preferring its own model year and then the nearest one; the build date and the colour, interior and equipment
codes stay empty, so the storyteller tells it as a partial story and it never enters a CAPS count. CAPS rows
are never touched. No Frappe import.
"""

from __future__ import annotations

from dataclasses import dataclass

from vin_storyteller.repository import PARAMSTYLES
from vin_storyteller.story import CAPS, has_valid_check_digit, normalize_vin, year_code

PROVENANCE_MAX = 30  # Production.Provenance


class RecordRefused(ValueError):
	"""The VIN can't be added: the message says why."""


@dataclass(frozen=True)
class AddedRecord:
	vin: str
	model: str
	model_code: str
	classification: str
	model_year: str
	provenance: str
	pattern_year: str  # the model year whose CAPS cars supplied the model line


def add_record(connection, raw_vin: str, provenance: str, paramstyle: str = "format") -> AddedRecord:
	"""Insert a non-CAPS production record for `raw_vin`, with `provenance` naming its source."""
	vin = normalize_vin(raw_vin)
	provenance = " ".join((provenance or "").split())
	if not provenance or provenance.upper() == CAPS or len(provenance) > PROVENANCE_MAX:
		raise RecordRefused(
			f"provenance must name the source in 1-{PROVENANCE_MAX} characters, and not be {CAPS}"
		)
	year = year_code(vin)
	if year is None:
		raise RecordRefused(f"{vin}: position 10 isn't a 1991-1999 model year")
	mark = PARAMSTYLES[paramstyle]
	cursor = connection.cursor()
	try:
		cursor.execute(f"SELECT 1 FROM Production WHERE VIN = {mark}", (vin,))
		if cursor.fetchone():
			raise RecordRefused(f"{vin} is already on record")
		if not has_valid_check_digit(vin):
			raise RecordRefused(f"{vin}: the check digit doesn't match; not a real VIN as written")
		cursor.execute(
			f"SELECT ModelYear, Model, ModelCode, Classification, COUNT(*) FROM Production "
			f"WHERE SUBSTR(VIN, 1, 8) = {mark} AND Provenance = {mark} "
			"GROUP BY ModelYear, Model, ModelCode, Classification",
			(vin[:8], CAPS),
		)
		patterns = cursor.fetchall()
		if not patterns:
			raise RecordRefused(
				f"{vin}: no CAPS car shares its first eight characters, so its model is unknown"
			)
		# Its own model year if CAPS has it, else the nearest; within a year, the commonest line.
		best = min(patterns, key=lambda p: (abs(int(p[0]) - int(year)), -p[4]))
		pattern_year, model, model_code, classification, _ = best
		cursor.execute(
			"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, "
			"Interior, DateOfManufacture, ModelYear, Provenance) "
			f"VALUES ({mark}, {mark}, {mark}, {mark}, {mark}, '', '', '', '', {mark}, {mark})",
			(vin[9:], vin, model, model_code, classification, year, provenance),
		)
	finally:
		cursor.close()
	connection.commit()
	return AddedRecord(vin, model, model_code, classification, year, provenance, pattern_year)
