# SPDX-License-Identifier: AGPL-3.0-or-later
"""The production statistics page (/storyteller/stats): every factory-record car counted by model year, model,
region, paint, interior, model line, transmission, build month, colour pair and exact-spec rarity. Pure: no Frappe,
no database. The repository supplies grouped rows and Mitsubishi's own labels; this module names each car's region
and folds the rows into compact facets the page filters and charts in the browser.

A car's region comes from the factory record itself, never a guess:
- a Japanese-market GTO (ASA Japan) is Japan;
- an export 3000GT (ASA General) takes the market its option code names ("ENGLAND SPEC", "GERMANY SPEC",
  "BRITISH ARMY SPEC IN WEST GERMANY"), else the market its grade text names ("... GCC"), else its drive side;
- a CAPS car with an Australian VIN (world manufacturer region 6) is Australia;
- any other CAPS car takes its grade's emissions destination from CAPS's grade table (HLP_RUI: FED, CAL or CANADA). A
  grade missing from the table takes the destination its destination digit carries in the table's other grades (2 =
  FED, 7 = CAL in every 1999 and 2004 build), else the documented digit 3 = Canada (DOCUMENTED_DIGITS).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from vin_storyteller.story import (
	MISSING,
	full_year,
	market_of,
	model_name,
	rarity_tier,
)

NOT_RECORDED = "Not recorded"
JAPAN = "Japan"
NORTH_AMERICA = "North America"
EXPORT = "Export"
AUSTRALIA = "Australia"
MARKET_GROUPS = {"jdm": JAPAN, "export": EXPORT, "us": NORTH_AMERICA}

DESTINATIONS = {"FED": "Federal (49-state)", "CAL": "California", "CAN": "Canada"}
# Destination digits the 3S grade labels don't carry. 3 = Canada: CAPS 2004's HLP_RUI labels digit-3 grades CANADA on
# Mitsubishi's other North American models (Lancer CS6A SNHEL3M, Outlander CU4W, Montero Sport K96W/K99W, Montero
# V77W), and Michael Reid's "Canada Emissions Stealth Production" (stealth316.com, from the same CAPS VIN table) is
# exactly the 3,280 digit-3 Stealths of the 1999 export, year by year and trim by trim. Only Dodges carry it: the
# 3000GT was not sold in Canada (operator-approved research, card 388, 2026-11-12).
DOCUMENTED_DIGITS = {"3": "CAN"}
UNNAMED_DIGIT = "digit "  # a destination digit the grade table names no destination for, e.g. "digit 3"
DESTINATION_DIGIT = 5  # MNHEL2M: the 6th character of a North American grade is its destination digit
AUSTRALIAN_VIN_REGION = "6"  # ISO 3780: a VIN starting 6 was built for Australia (Mitsubishi Australia: 6MM)
WORLD_USA = "United States of America"  # the world map's name for the USA (world-atlas, Natural Earth)

# "ENGLAND SPEC", "BRITISH ARMY SPEC IN WEST GERMANY": an export option item that names the car's market.
SPEC_ITEM = re.compile(r"^(?P<place>[A-Z][A-Z .'&-]*?) SPEC(?: IN (?P<within>[A-Z][A-Z .'&-]*))?$")
# "...,5FM/T GCC": an export grade text that names its market after the transmission.
GRADE_MARKET = re.compile(r"[0-9]F[MA]/T\s+(?P<market>[A-Z]{2,})\s*$")
TRANSMISSION = re.compile(r"(?P<speeds>[0-9])F(?P<kind>[MA])/T")
TRANSMISSION_KINDS = {"M": "manual", "A": "automatic"}
SMALL_WORDS = {"in", "of", "and", "the"}
ACRONYMS = {"EC", "EU", "UK", "GCC", "USA", "US"}

GRADE_MARKETS = {"GCC": "Gulf states (GCC)"}
# What ASA General's grade texts put after the transmission besides a market: the drive side ("…,6FM/T RHD").
NOT_MARKETS = {"LHD", "RHD"}
# A market's country on the world map (world-atlas names); a market that is itself a map name needs no entry.
MAP_COUNTRIES = {
	"England": "United Kingdom",
	"Scotland": "United Kingdom",
	"Wales": "United Kingdom",
	"Great Britain": "United Kingdom",
	"British Army in West Germany": "Germany",
	"West Germany": "Germany",
	"Holland": "Netherlands",
	"Swiss": "Switzerland",
	"Federal (49-state)": WORLD_USA,
	"California": WORLD_USA,
	"Canada": "Canada",
	JAPAN: JAPAN,
	AUSTRALIA: AUSTRALIA,
}
DRIVE_SIDES = {"EL": "left-hand drive", "ER": "right-hand drive"}

RARITY_ORDER = ("one_of_one", "sub10", "sub25", "sub50", "sub100", "common")
RARITY_NAMES = {
	"one_of_one": "One of one",
	"sub10": "Fewer than 10",
	"sub25": "Fewer than 25",
	"sub50": "Fewer than 50",
	"sub100": "Fewer than 100",
	"common": "100 or more",
}
# The 1994 model year facelift (fixed headlamps, new bumpers) splits the cars into two generations.
SECOND_GENERATION_FROM = 1994
GENERATIONS = ("1st generation (to 1993)", "2nd generation (1994 on)")
OPTIONS_ON_RECORD = ("on_record", "not_on_record")
OPTIONS_ON_RECORD_NAMES = {
	"on_record": "Option contents on record",
	"not_on_record": "Option contents not on record",
}
# "options" counts a car once under each option item its option code fits, so it does not partition the cars;
# "option_records" does, and is the denominator for an item's share.
FACETS = (
	"paint",
	"interior",
	"line",
	"transmission",
	"month",
	"colours",
	"rarity",
	"generation",
	"options",
	"option_records",
)
REGION_NOTES = {
	"Federal (49-state)": "Mitsubishi's FED grade destination: built to US federal emissions rules. The factory "
	"records give a North American car's emissions destination, not the country it was sold in.",
	"California": "Mitsubishi's CAL grade destination: built to California's emissions rules.",
	"Canada": "Grades with destination digit 3, which Mitsubishi's grade table marks CANADA on its other North American "
	"models; every one is a Dodge Stealth (the 3000GT wasn't sold in Canada), and they match Michael Reid's count of "
	"Stealths built to Canadian standards car for car.",
	"Gulf states (GCC)": "Export grades whose catalogue text names the Gulf Cooperation Council market.",
	"Japan": "Japanese-market GTOs, from Mitsubishi's ASA Japan catalogue.",
	"Australia": "Cars with an Australian VIN (world manufacturer region 6) in Mitsubishi's North American catalogue. "
	"The Australian-delivered 3000GTs (VIN JMF) are known only from owners' listings, not factory records, so the "
	"factory counts here leave them out.",
}


@dataclass(frozen=True)
class Region:
	"""Where a car was built for: its region's name, its market group and its country on the world map ("" when it
	has none, e.g. the Gulf states)."""

	name: str
	market: str
	country: str = ""


def _word(word: str, first: bool) -> str:
	if word.upper() in ACRONYMS:
		return word.upper()
	if not first and word in SMALL_WORDS:
		return word
	return "-".join(
		_word(part, True) if part.upper() in ACRONYMS else part.capitalize() for part in word.split("-")
	)


def _title(text: str) -> str:
	"""Catalogue capitals as a name: 'BRITISH ARMY SPEC IN WEST GERMANY' words -> 'British Army in West Germany',
	'NON-EC' -> 'Non-EC'."""
	return " ".join(_word(w, i == 0) for i, w in enumerate(text.strip().lower().split()))


def generation(model_year: str) -> str:
	"""A full model year's generation: up to 1993, or from the 1994 facelift on."""
	return GENERATIONS[int(model_year) >= SECOND_GENERATION_FROM] if model_year.isdigit() else NOT_RECORDED


def region_note(region: Region) -> str:
	"""What a region means, for the page's (?) explanations."""
	if region.name in REGION_NOTES:
		return REGION_NOTES[region.name]
	if region.market == EXPORT and region.name.startswith("Export, market not recorded"):
		return "Export cars whose option code and grade name no market; only their drive side is recorded."
	if region.market == EXPORT:
		return f"Export cars whose option code carries Mitsubishi's {region.name.upper()} SPEC item (ASA General)."
	if region.market == NORTH_AMERICA and "destination digit" in region.name:
		return (
			"North American cars whose grade's destination digit (its 6th character) is one Mitsubishi's grade table "
			"names no destination for, so the records don't say where they were sold."
		)
	if region.market == NORTH_AMERICA:
		return "North American cars whose grade has no emissions destination in Mitsubishi's grade table."
	return ""


def spec_market(descriptions: Iterable[str]) -> str | None:
	"""The market an export car's option items name ("ENGLAND SPEC" -> England), or None when none does."""
	markets = set()
	for description in descriptions:
		match = SPEC_ITEM.match((description or "").strip().upper())
		if match:
			place = _title(match["place"])
			markets.add(f"{place} in {_title(match['within'])}" if match["within"] else place)
	return sorted(markets)[0] if markets else None


def grade_market(label: str | None) -> str | None:
	"""The market an export grade's text names after its transmission ("...,5FM/T GCC" -> Gulf states (GCC),
	"...,6FM/T BRAZIL" -> Brazil); a drive side there ("RHD") is no market."""
	match = GRADE_MARKET.search((label or "").strip().upper())
	if not match or match["market"] in NOT_MARKETS:
		return None
	return GRADE_MARKETS.get(match["market"]) or _title(match["market"])


def transmission(label: str | None) -> str:
	"""A grade text's transmission ("ULTIMATE LINE,6FM/T" -> 6-speed manual), or NOT_RECORDED."""
	match = TRANSMISSION.search((label or "").upper())
	if not match:
		return NOT_RECORDED
	return f"{match['speeds']}-speed {TRANSMISSION_KINDS[match['kind']]}"


def destination_digits(destinations: dict[tuple[str, str], str]) -> dict[str, str]:
	"""Each destination digit's destination, where every labelled grade with that digit agrees."""
	seen: dict[str, set[str]] = {}
	for (_, grade), destination in destinations.items():
		if len(grade) > DESTINATION_DIGIT and destination:
			seen.setdefault(grade[DESTINATION_DIGIT], set()).add(destination)
	return {digit: next(iter(found)) for digit, found in seen.items() if len(found) == 1}


def destination_code(raw: str | None) -> str:
	"""HLP_RUI's destination field as its code: 'CAL53H' -> 'CAL'."""
	return (raw or "").strip()[:3].upper()


def region_of(
	model_key: str,
	vin_region: str,
	destination: str,
	market_items: Iterable[str] = (),
	grade_label: str | None = None,
) -> Region:
	"""A factory-record car's region, from its Model key (market), the first character of its VIN, its grade's
	destination code (FED/CAL; North America only), its option items (export only) and its grade text."""
	market = market_of(model_key)
	if market == "au":
		return Region(AUSTRALIA, AUSTRALIA, AUSTRALIA)
	if market == "jdm":
		return Region(JAPAN, JAPAN, JAPAN)
	if market == "export":
		named = spec_market(market_items) or grade_market(grade_label)
		if named:
			on_map = named not in GRADE_MARKETS.values()  # the Gulf states are several countries
			return Region(named, EXPORT, MAP_COUNTRIES.get(named, named) if on_map else "")
		side = DRIVE_SIDES.get(model_key, "")
		return Region(f"Export, market not recorded{f' ({side})' if side else ''}", EXPORT)
	if vin_region == AUSTRALIAN_VIN_REGION:
		return Region(AUSTRALIA, AUSTRALIA, AUSTRALIA)
	if destination in DESTINATIONS:
		name = DESTINATIONS[destination]
		return Region(name, NORTH_AMERICA, MAP_COUNTRIES[name])
	if destination.startswith(UNNAMED_DIGIT):
		return Region(f"North America, destination digit {destination[len(UNNAMED_DIGIT) :]}", NORTH_AMERICA)
	if destination:
		return Region(f"North America ({destination})", NORTH_AMERICA)
	return Region("North America, destination not recorded", NORTH_AMERICA)


@dataclass(frozen=True)
class StatsRow:
	"""Factory-record cars sharing every dimension the stats page counts by."""

	model_year: str  # 'YY'
	model_key: str  # Production.Model
	manufacturer: str | None
	model: str | None
	trim: str | None
	model_code: str
	classification: str
	equipment: str
	exterior: str
	interior: str
	built_month: str  # 'YYMM'
	vin_region: str  # the VIN's first character
	count: int


@dataclass(frozen=True)
class Catalogue:
	"""What the stats need from Mitsubishi's labels: grade texts, grade destinations, export market items, a paint's
	plain code for its "A" forms, and paint and interior names."""

	grades: dict[tuple[str, str], str]  # (model code, grade) -> grade text
	destinations: dict[tuple[str, str], str]  # (model code, grade) -> FED / CAL
	market_items: dict[
		tuple[str, str, str], tuple[str, ...]
	]  # export (model code, option, grade) -> item texts
	paint_aliases: dict[str, str]
	paint_names: dict[str, str]
	interior_names: dict[str, str]
	option_items: dict[tuple[str, str, str, str], tuple[str, ...]] | None = (
		None  # (model code, option, grade, year)
	)
	item_names: dict[str, str] | None = None

	def items(
		self, model_code: str, option: str, classification: str, model_year: str, fallback: dict
	) -> tuple:
		"""The option items a car's option code fits for its grade and model year (else any year's), or None
		when the catalogue holds none."""
		key = (model_code, option.strip(), classification.strip())
		exact = (self.option_items or {}).get((*key, model_year))
		return exact if exact is not None else fallback.get(key)

	def grade(self, model_code: str, classification: str) -> str | None:
		"""A grade's text: exact, else by its first four characters (as the story labels it)."""
		grade = classification.strip()
		exact = self.grades.get((model_code, grade))
		if exact:
			return exact
		return next(
			(
				text
				for (code, g), text in sorted(self.grades.items())
				if code == model_code and g[:4] == grade[:4]
			),
			None,
		)

	def destination(self, model_code: str, classification: str, digits: dict[str, str]) -> str:
		grade = classification.strip()
		exact = self.destinations.get((model_code, grade))
		if exact:
			return exact
		if len(grade) <= DESTINATION_DIGIT:
			return ""
		digit = grade[DESTINATION_DIGIT]
		return (
			digits.get(digit)
			or DOCUMENTED_DIGITS.get(digit)
			or (f"{UNNAMED_DIGIT}{digit}" if digit.isdigit() else "")
		)


def _line_name(row: StatsRow) -> str:
	parts = (row.manufacturer, row.model, row.trim)
	return " ".join(p for p in parts if p and p != MISSING) or model_name(row.model)


def _month(built_month: str) -> str:
	"""'YYMM' -> 'YYYY-MM' (calendar), or '' when it isn't a month."""
	if len(built_month) != 4 or not built_month.isdigit() or not 1 <= int(built_month[2:]) <= 12:
		return ""
	return f"{full_year(built_month[:2])}-{built_month[2:]}"


def _code(raw: str, placeholder: str) -> str:
	code = (raw or "").strip()
	return "" if code in ("", placeholder) else code


class _Index:
	"""Values in first-seen order, each with its index."""

	def __init__(self):
		self.values: dict = {}

	def __call__(self, value) -> int:
		return self.values.setdefault(value, len(self.values))


def build_stats(rows: Iterable[StatsRow], catalogue: Catalogue) -> dict:
	"""The stats page's data: dimensions (years, models, regions), and per facet its values and rows of
	[year, model, region, value, cars] (indexes into the dimension and value lists)."""
	rows = list(rows)
	digits = destination_digits(catalogue.destinations)
	years, models, regions = _Index(), _Index(), _Index()
	values = {facet: _Index() for facet in FACETS}
	counts: dict[str, dict[tuple, int]] = {facet: {} for facet in FACETS}

	spec_totals: dict[tuple, int] = {}
	for row in rows:  # the original storyteller's "identical cars": same year, line, colours and option code
		spec = _spec(row)
		spec_totals[spec] = spec_totals.get(spec, 0) + row.count

	grades: dict[tuple[str, str], str | None] = {}
	# An item that names the market ("ENGLAND SPEC") is the car's region, not equipment: the options facet leaves it out.
	market_codes = {code for code, name in (catalogue.item_names or {}).items() if spec_market([name])}
	any_year: dict[tuple[str, str, str], tuple[str, ...]] = {}
	for (model_code, option, grade, _), found in sorted((catalogue.option_items or {}).items()):
		any_year.setdefault((model_code, option, grade), found)
	for row in sorted(rows, key=lambda r: (full_year(r.model_year), model_name(r.model))):
		grade_key = (row.model_code, row.classification)
		if grade_key not in grades:
			grades[grade_key] = catalogue.grade(*grade_key)
		grade = grades[grade_key]
		region = region_of(
			row.model_key,
			row.vin_region,
			catalogue.destination(row.model_code, row.classification, digits),
			catalogue.market_items.get(
				(row.model_code, row.equipment.strip(), row.classification.strip()), ()
			),
			grade,
		)
		key = (
			years(full_year(row.model_year) if row.model_year else NOT_RECORDED),
			models(model_name(row.model)),
			regions(region),
		)
		paint = _code(row.exterior, "EXT")
		paint = catalogue.paint_aliases.get(paint, paint)
		interior = _code(row.interior, "INT")
		tier = rarity_tier(spec_totals[_spec(row)]) or "common"
		items = catalogue.items(row.model_code, row.equipment, row.classification, row.model_year, any_year)
		year = full_year(row.model_year) if row.model_year else ""
		facet_values = {
			"paint": paint,
			"interior": interior,
			"line": _line_name(row),
			"transmission": transmission(grade),
			"month": _month(row.built_month),
			"colours": (paint, interior),
			"rarity": tier,
			"generation": generation(year),
			"option_records": OPTIONS_ON_RECORD[items is None],
		}
		for facet, value in facet_values.items():
			cell = (*key, values[facet](value))
			counts[facet][cell] = counts[facet].get(cell, 0) + row.count
		for item in dict.fromkeys(i for i in items or () if i not in market_codes):
			cell = (*key, values["options"](item))
			counts["options"][cell] = counts["options"].get(cell, 0) + row.count

	return {
		"total": sum(r.count for r in rows),
		"years": list(years.values),
		"models": list(models.values),
		"regions": [
			{"name": r.name, "market": r.market, "country": r.country, "note": region_note(r)}
			for r in regions.values
		],
		"facets": {
			facet: {
				"values": [_describe(facet, value, catalogue) for value in values[facet].values],
				"rows": [[*cell, n] for cell, n in sorted(counts[facet].items())],
			}
			for facet in FACETS
		},
	}


def _spec(row: StatsRow) -> tuple:
	return (
		row.model_year,
		row.model_key,
		row.model_code,
		row.interior.strip(),
		row.exterior.strip(),
		row.equipment.strip(),
	)


def _describe(facet: str, value, catalogue: Catalogue) -> dict:
	"""A facet value as the page shows it."""
	if facet == "paint":
		return {"code": value, "name": catalogue.paint_names.get(value, MISSING) if value else NOT_RECORDED}
	if facet == "interior":
		return {
			"code": value,
			"name": catalogue.interior_names.get(value, MISSING) if value else NOT_RECORDED,
		}
	if facet == "colours":
		return {"paint": value[0], "interior": value[1]}
	if facet == "rarity":
		return {"code": value, "name": RARITY_NAMES[value], "order": RARITY_ORDER.index(value)}
	if facet == "options":
		return {"code": value, "name": (catalogue.item_names or {}).get(value, MISSING)}
	if facet == "option_records":
		return {"code": value, "name": OPTIONS_ON_RECORD_NAMES[value]}
	if facet == "month":
		return {"code": value, "name": value or NOT_RECORDED}
	return {"name": value}
