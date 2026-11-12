# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adding a car the CAPS export is missing: a real VIN proven by another source (operator, 2026-10-26).

Only what the VIN itself establishes is recorded. Its model line (Model, ModelCode, Classification) is taken
from the CAPS cars that share its first eight characters (manufacturer, line, body, engine, restraint),
preferring its own model year and then the nearest one; the build date and the colour, interior and equipment
codes stay empty, so the storyteller tells it as a partial story and it never enters a CAPS count. CAPS rows
are never touched. No Frappe import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vin_storyteller.repository import PARAMSTYLES
from vin_storyteller.story import (
	AUSTRALIAN_MODEL,
	AUSTRALIAN_VIN_PREFIX,
	CHASSIS_MODELS,
	FACTORY_PROVENANCES,
	has_valid_check_digit,
	is_chassis_number,
	normalize_chassis,
	normalize_vin,
	year_code,
)

PROVENANCE_MAX = 30  # Production.Provenance
FACTORY_NAMES = {p.upper() for p in FACTORY_PROVENANCES} | {"CAPS", "ASA"}  # reserved for the factory records


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
	"""Insert a non-CAPS production record for `raw_vin` (a 17-character VIN, or a JDM GTO chassis number), with
	`provenance` naming its source."""
	provenance = " ".join((provenance or "").split())
	if not provenance or provenance.upper() in FACTORY_NAMES or len(provenance) > PROVENANCE_MAX:
		raise RecordRefused(
			f"provenance must name the source in 1-{PROVENANCE_MAX} characters, and not be a factory export"
		)
	if is_chassis_number(raw_vin):
		return _add_chassis(connection, normalize_chassis(raw_vin), provenance, PARAMSTYLES[paramstyle])
	vin = normalize_vin(raw_vin)
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
			f"WHERE SUBSTR(VIN, 1, 8) = {mark} AND Provenance IN ({', '.join([mark] * len(FACTORY_PROVENANCES))}) "
			"GROUP BY ModelYear, Model, ModelCode, Classification",
			(vin[:8], *FACTORY_PROVENANCES),
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


def _add_chassis(connection, chassis: str, provenance: str, mark: str) -> AddedRecord:
	"""A JDM GTO by chassis number: its family gives the Model; serial is the seven digits; nothing else is known."""
	family = chassis[:4]
	model = CHASSIS_MODELS[family]
	cursor = connection.cursor()
	try:
		cursor.execute(f"SELECT 1 FROM Production WHERE VIN = {mark}", (chassis,))
		if cursor.fetchone():
			raise RecordRefused(f"{chassis} is already on record")
		cursor.execute(
			"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, "
			"Interior, DateOfManufacture, ModelYear, Provenance) "
			f"VALUES ({mark}, {mark}, {mark}, {mark}, '', '', '', '', '', '', {mark})",
			(chassis[-7:], chassis, model, family, provenance),
		)
	finally:
		cursor.close()
	connection.commit()
	return AddedRecord(chassis, model, family, "", "", provenance, "")


# A listed Australian car (card 388): only what the listing and its VIN establish.
LISTED_VIN = re.compile(r"^JMF[A-HJ-NPR-Z0-9]{14}$")
# "JMFJF5S24NJ000001<tab>Red<tab>WA*": VIN, a one-word colour (or ?), then the location (tabs or spaces).
LISTING_ROW = re.compile(r"^\s*(JMF[A-Z0-9]{14})\s+(\S+)(?:\s+(\S.*?))?\s*$")
HISTORY_TITLE_MAX = 200  # VehicleHistory.Title


@dataclass(frozen=True)
class Listed:
	"""One car in an owners' listing: its VIN and what the listing says about it."""

	vin: str
	colour: str  # as written ('Red', 'white'); '' for '?' or blank
	location: str  # as written ('Vic', 'WA*')
	url: str  # the listing page that names it


def parse_listing(text: str, url: str) -> list[Listed]:
	"""Rows of a VIN / colour / location table pasted into a forum post (3SI's Aus-delivered list), first mention
	of each VIN kept. A malformed VIN (wrong length, I/O/Q, no model-year letter in position 10) is skipped."""
	found: dict[str, Listed] = {}
	for line in text.splitlines():
		match = LISTING_ROW.match(line)
		if not match:
			continue
		vin, colour, location = match.group(1).upper(), match.group(2).strip(), (match.group(3) or "").strip()
		if LISTED_VIN.match(vin) and year_code(vin) and vin not in found:
			found[vin] = Listed(vin, "" if colour in ("?", "") else colour, location, url)
	return list(found.values())


def add_listed_record(
	connection, listed: Listed, provenance: str, source: str, paramstyle: str = "format"
) -> AddedRecord:
	"""Insert an Australian-delivered 3000GT from an owners' listing: Model AU, its model year from the VIN's year
	letter, chassis Z16A where the VIN spells it, every code empty (a partial story outside every count); and a
	VehicleHistory row citing the listing page with the colour and location it gives."""
	provenance = " ".join((provenance or "").split())
	if not provenance or provenance.upper() in FACTORY_NAMES or len(provenance) > PROVENANCE_MAX:
		raise RecordRefused(
			f"provenance must name the source in 1-{PROVENANCE_MAX} characters, and not be a factory export"
		)
	vin = listed.vin
	if not vin.startswith(AUSTRALIAN_VIN_PREFIX) or not LISTED_VIN.match(vin):
		raise RecordRefused(f"{vin}: not an Australian (JMF) VIN")
	year = year_code(vin)
	if year is None:
		raise RecordRefused(f"{vin}: position 10 isn't a 1991-1999 model year")
	model_code = "Z16A" if "Z16A" in vin[3:9] else ""
	mark = PARAMSTYLES[paramstyle]
	details = "; ".join(
		part
		for part in (
			f"colour {listed.colour}" if listed.colour else "",
			f"location {listed.location}" if listed.location else "",
		)
		if part
	)
	title = f"Listed among the Australian-delivered 3000GTs{f' ({details})' if details else ''}"[
		:HISTORY_TITLE_MAX
	]
	cursor = connection.cursor()
	try:
		cursor.execute(f"SELECT 1 FROM Production WHERE VIN = {mark}", (vin,))
		if cursor.fetchone():
			raise RecordRefused(f"{vin} is already on record")
		cursor.execute(
			"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, "
			"Interior, DateOfManufacture, ModelYear, Provenance) "
			f"VALUES ({mark}, {mark}, {mark}, {mark}, '', '', '', '', '', {mark}, {mark})",
			(vin[9:], vin, AUSTRALIAN_MODEL, model_code, year, provenance),
		)
		cursor.execute(
			"INSERT INTO VehicleHistory (VIN, RecordType, Title, URL, Source, Provenance) "
			f"VALUES ({mark}, 'other', {mark}, {mark}, {mark}, {mark})",
			(vin, title, listed.url, source, provenance),
		)
	finally:
		cursor.close()
	connection.commit()
	return AddedRecord(vin, AUSTRALIAN_MODEL, model_code, "", year, provenance, "")
