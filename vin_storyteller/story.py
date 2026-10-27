# SPDX-License-Identifier: AGPL-3.0-or-later
"""The story of a 3000GT / Stealth, told from its VIN and its factory production record.

Pure logic: no Frappe and no database here, so every rule is unit-testable.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")  # 17 characters, never I, O or Q
MISSING = "MISSING"  # the record's own placeholder for an undeciphered code
PERIOD_NAMES = {"1": "1st", "2": "2nd", "3": "3rd"}


class InvalidVin(ValueError):
	"""Raised when the input cannot be a VIN."""


def normalize_vin(raw: str) -> str:
	"""The VIN in canonical form (upper case, no whitespace), or InvalidVin."""
	vin = "".join((raw or "").split()).upper()
	if not VIN_PATTERN.match(vin):
		raise InvalidVin(vin)
	return vin


NAME_MAX = 100  # StoriesTold.Name


class InvalidName(ValueError):
	"""No usable name: blank, or longer than StoriesTold.Name holds."""


def normalize_name(raw: str | None) -> str:
	"""The visitor's name as logged with their story (whitespace collapsed), or InvalidName."""
	name = " ".join((raw or "").split())
	if not name or len(name) > NAME_MAX:
		raise InvalidName(name)
	return name


def full_year(two_digit_year: str) -> str:
	"""'91' -> '1991'; '00' -> '2000' (the last GTOs are 2000 model years)."""
	return f"{'20' if two_digit_year < '50' else '19'}{two_digit_year}"


def describe_production_date(code: str) -> str:
	"""A 'YYMMP' production date (year, month, period 1-3) as 'the 2nd production period of March, 1992'."""
	year, month, period = code[0:2], code[2:4], code[4:5]
	month_name = (
		calendar.month_name[int(month)] if month.isdigit() and 1 <= int(month) <= 12 else "an unknown month"
	)
	return f"the {PERIOD_NAMES.get(period, 'Unknown')} production period of {month_name}, {full_year(year)}"


# Factory production records, named by the Mitsubishi catalogue build they came from (operator 2026-10-27). Only
# these tell full stories and count in positions and totals.
CAPS = "CAPS 1999"  # the original export: Reid's NA9199, from CAPS PASEN/SHARYO dated 1999-09-16
CAPS_2004 = (
	"CAPS 2004"  # cars only the 2004 WINCAPS build holds (the 1997 Nov 1996 - Jan 1997 block, two 1999s)
)
ASA_JAPAN = "ASA Japan 2008"  # every Japanese-market GTO, from Mitsubishi's ASA Japan EPC (2008-02-22)
ASA_GENERAL = "ASA General 2008"  # export-market 3000GTs (UK and others), from Mitsubishi's ASA General EPC
FACTORY_PROVENANCES = (CAPS, CAPS_2004, ASA_JAPAN, ASA_GENERAL)

# ISO 3779 check digit (the VIN's 9th character): every one of the 151,454 CAPS 1999 VINs has a correct one, so a VIN
# whose check digit fails was almost certainly mistyped.
_VIN_VALUES = {
	**{str(d): d for d in range(10)},
	**dict(zip("ABCDEFGH", range(1, 9), strict=True)),
	**dict(zip("JKLMN", range(1, 6), strict=True)),
	"P": 7,
	"R": 9,
	**dict(zip("STUVWXYZ", range(2, 10), strict=True)),
}
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def check_digit(vin: str) -> str:
	"""The check digit a 17-character VIN should carry in position 9."""
	remainder = sum(_VIN_VALUES[c] * w for c, w in zip(vin, _VIN_WEIGHTS, strict=True)) % 11
	return "X" if remainder == 10 else str(remainder)


def has_valid_check_digit(vin: str) -> bool:
	return check_digit(vin) == vin[8]


# Japanese-market GTOs carry a chassis number, not a 17-character VIN: Z15A- or Z16A- and seven digits (Mitsubishi
# service campaign SC059; card 327). Mitsubishi's ASA Japan catalogue holds every one of them.
CHASSIS_PATTERN = re.compile(r"^Z1[56]A-?[0-9]{7}$")
CHASSIS_NOT_ON_RECORD = (
	"That's a Japanese-market Mitsubishi GTO chassis number, but it isn't in Mitsubishi's own record of the GTOs it "
	"built (the ASA Japan parts catalogue, 23,369 cars). Please check it against the plate in the engine bay or "
	"your car's papers; if it's right, please email storyteller@3shub.com."
)


CHASSIS_MODELS = {"Z15A": "G5", "Z16A": "G6"}  # chassis family -> Model key (migration 0004)


EXPORT_MODELS = {"EL": "LHD", "ER": "RHD"}  # export-market 3000GT Model keys by drive side (migration 0007)
MARKET_MODELS = {"jdm": tuple(CHASSIS_MODELS.values()), "export": tuple(EXPORT_MODELS)}


def market_of(model: str) -> str:
	"""Which numbering a car's positions and totals count within: 'us', 'jdm' (GTO) or 'export'."""
	return next((market for market, models in MARKET_MODELS.items() if model in models), "us")


# Export-market 3000GTs (ASA General): 17-character VINs from JMA/JMY without an ISO check digit, or, for 1992-94
# cars, a 14-character frame number such as DMNZ16APY00001 (card 331).
EXPORT_VIN_PREFIXES = ("JMA", "JMY")
FRAME_PATTERN = re.compile(r"^(?=[A-Z0-9]{14}$)[A-Z]{2,3}Z16A[A-Z0-9]+$")
EXPORT_NOT_ON_RECORD = (
	"That's an export-market Mitsubishi 3000GT {kind}, but it isn't in Mitsubishi's record of the export cars (the "
	"ASA General parts catalogue, 756 cars). Please check it against your car's plate or papers; if it's right, "
	"please email storyteller@3shub.com."
)


def is_frame_number(raw: str | None) -> bool:
	"""An export 3000GT's 14-character frame number (e.g. DMNZ16APY00001), spaces and dashes ignored."""
	return bool(FRAME_PATTERN.match(normalize_frame(raw)))


def normalize_frame(raw: str | None) -> str:
	return "".join(c for c in (raw or "").upper() if c.isalnum())


def is_chassis_number(raw: str | None) -> bool:
	"""A JDM GTO chassis number (Z15A-/Z16A- and seven digits, the dash optional)."""
	return bool(CHASSIS_PATTERN.match("".join((raw or "").split()).upper()))


def normalize_chassis(raw: str | None) -> str:
	"""A GTO chassis number in canonical form ('Z16A-0011452'), or InvalidVin."""
	compact = "".join((raw or "").split()).upper()
	if not CHASSIS_PATTERN.match(compact):
		raise InvalidVin(compact)
	family, digits = compact[:4], compact[-7:]
	return f"{family}-{digits}"


# What a VIN that isn't on record can still tell us (positions 1-3, 10 and 12-17).
MANUFACTURER_CODES = {
	"JA3": "Mitsubishi",
	"JB3": "Dodge",
}  # every car in the CAPS export starts with one of these
YEAR_CODES = {
	"M": "91",
	"N": "92",
	"P": "93",
	"R": "94",
	"S": "95",
	"T": "96",
	"V": "97",
	"W": "98",
	"X": "99",
}
SPECIAL_SERIALS = 100  # 000001-000100: usually crash-test or promotional cars
REPORT = "please email storyteller@3shub.com with your VIN so we can add it"


@dataclass(frozen=True)
class Neighbour:
	"""The nearest car on record on one side of a missing serial, in the same model year."""

	serial: str
	built: str  # 'YYMMP'


@dataclass(frozen=True)
class Gap:
	"""Where a missing VIN's serial falls among the model year's cars on record."""

	before: Neighbour | None
	after: Neighbour | None


def year_code(vin: str) -> str | None:
	"""The two-digit model year a VIN's 10th character encodes, if it is a 1991-1999 code."""
	return YEAR_CODES.get(vin[9])


def not_found_message(vin: str, gap: Gap | None) -> str | None:
	"""Why a well-formed VIN has no production record, when the VIN or the record around it says; None otherwise."""
	if vin[:3] in EXPORT_VIN_PREFIXES:
		return EXPORT_NOT_ON_RECORD.format(kind="VIN")
	maker = MANUFACTURER_CODES.get(vin[:3])
	if maker is None:
		return (
			f"That VIN starts with {vin[:3]}, so it wasn't issued for a North American Mitsubishi 3000GT or Dodge "
			"Stealth: theirs start with JA3 (Mitsubishi) or JB3 (Dodge). A Japanese-market GTO carries a chassis "
			"number instead of a VIN, and those aren't in the production record yet."
		)
	year = year_code(vin)
	if year is None:
		return (
			f"The 10th character of that VIN, {vin[9]}, isn't a 1991–1999 model year code, so it isn't a 3000GT "
			"or Stealth VIN. Please check it against the plate at the base of your windshield."
		)
	if not has_valid_check_digit(vin):
		return (
			"That VIN doesn't add up: its 9th character is a check digit calculated from the other 16, and it "
			"doesn't match them, so one of the characters is almost certainly mistyped. Please check it against "
			"the plate at the base of your windshield."
		)
	if gap is None:
		return None
	serial = vin[11:]
	model_year = full_year(year)
	if gap.before and gap.after:
		return (
			f"Serial {serial} isn't in the factory record for the {model_year} model year, but the cars either side "
			f"of it are: serial {gap.before.serial} was built in {describe_production_date(gap.before.built)} and "
			f"serial {gap.after.serial} in {describe_production_date(gap.after.built)}. That stretch is missing from "
			f"the export Mitsubishi made, so your car is almost certainly genuine; {REPORT}."
		)
	if gap.after:
		special = (
			" Serial numbers 000001 to 000100 were usually crash-test or promotional cars."
			if int(serial) <= SPECIAL_SERIALS
			else ""
		)
		return (
			f"Serial {serial} comes before the first {model_year} car in the factory record (serial "
			f"{gap.after.serial}, built in {describe_production_date(gap.after.built)}), and the export is missing "
			f"cars from the start of some model years.{special} If your VIN is right, {REPORT}."
		)
	if gap.before:
		return (
			f"Serial {serial} comes after the last {model_year} car in the factory record (serial "
			f"{gap.before.serial}, built in {describe_production_date(gap.before.built)}). Please check the VIN; if "
			f"it's right, {REPORT}."
		)
	return None


def exterior_description(manufacturer: str, mitsubishi: str, dodge: str) -> str:
	"""The colour name the car's own manufacturer used, or MISSING when it is not deciphered yet."""
	if manufacturer == "Mitsubishi" and mitsubishi != MISSING:
		return mitsubishi
	if manufacturer == "Dodge" and dodge != MISSING:
		return dodge
	return MISSING


@dataclass(frozen=True)
class Coded:
	"""A factory code and what it means."""

	code: str
	description: str


@dataclass(frozen=True)
class ModelCount:
	model: str  # Model.Model: 3000GT, Stealth, GTO
	count: int


# What each cross-model breakdown counts: every factory record of every model and market, matching on...
BREAKDOWN_SCOPES = {
	"year": "built for the same model year",
	"colour": "in the same exterior colour, every year",
	"colour_year": "in the same exterior colour for the same model year",
	"interior": "with the same interior, every year",
	"colours": "with the same exterior and interior colours, every year",
	"period": "built in the same production period",
	"month": "built in the same production month",
}


@dataclass(frozen=True)
class Breakdown:
	"""How many factory-record cars of every model share something with this one, and of which models."""

	scope: str  # a BREAKDOWN_SCOPES key
	total: int
	by_model: tuple[ModelCount, ...]  # largest first

	@property
	def description(self) -> str:
		return BREAKDOWN_SCOPES[self.scope]


@dataclass(frozen=True)
class Position:
	"""This car's place in a run: number `position` out of `total`."""

	position: int
	total: int


HISTORY_TYPES = ("auction", "photo", "sale", "registration", "service", "article", "other")

# (largest total in the tier, tier id), rarest first. A total of 1 is a one-of-one.
RARITY_TIERS = ((1, "one_of_one"), (9, "sub10"), (24, "sub25"), (49, "sub50"), (99, "sub100"))
RARITY_SCOPES = {
	"spec": "in this exact specification (year, model, colours and equipment)",
	"colour": "in this colour for this model and year",
	"model": "of this model built for the model year",
}


def rarity_tier(total: int) -> str | None:
	"""The rarity tier for a production run of `total` cars, or None when it is not rare."""
	return next((tier for ceiling, tier in RARITY_TIERS if 0 < total <= ceiling), None)


@dataclass(frozen=True)
class Rarity:
	scope: str  # a RARITY_SCOPES key
	total: int
	tier: str

	@property
	def description(self) -> str:
		return RARITY_SCOPES[self.scope]


SAFE_URL = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)


def safe_url(url: str | None) -> str | None:
	"""The URL if it is a plain http(s) link, else None (never a javascript:/data: or malformed link)."""
	return url if url and SAFE_URL.match(url) else None


@dataclass(frozen=True)
class HistoryRecord:
	"""Something known about this car after it left the factory: an auction, a photo set, a sale…"""

	kind: str
	title: str
	url: str | None
	date: str | None  # ISO date
	source: str | None
	provenance: str


@dataclass(frozen=True)
class Story:
	vin: str
	provenance: str  # where this VIN's production record came from, e.g. CAPS 1999
	history: tuple[HistoryRecord, ...]
	model_year: str
	manufacturer: str
	model: str
	trim: str
	exterior: Coded
	interior: Coded
	equipment: Coded
	built: str
	built_in_period: int
	built_in_month: int
	year_started: str
	model_started: str
	in_year: Position
	in_model: Position
	in_colour: Position
	among_identical: Position
	partial: bool = (
		False  # on record from another source than CAPS: no build date, codes, positions or rarity
	)
	classification: Coded = Coded("", "")  # the factory grade code and Mitsubishi's description of it
	model_code: str = (
		""  # the chassis model code (Z11A, Z15A, Z16A): an option code means something per model code
	)
	equipment_items: tuple[Coded, ...] = ()  # what the equipment (option) code fits, item by item
	features: tuple[
		str, ...
	] = ()  # factory-fitted equipment the parts catalogue gives its grade and build date
	breakdowns: tuple[Breakdown, ...] = ()  # across every model: same colour, same period, ...

	@property
	def vehicle_name(self) -> str:
		return " ".join(part for part in (self.model_year, self.manufacturer, self.model, self.trim) if part)

	@property
	def rarities(self) -> list[Rarity]:
		"""Every scope in which this car is rare, rarest first."""
		if self.partial:
			return []
		runs = {
			"spec": self.among_identical.total,
			"colour": self.in_colour.total,
			"model": self.in_model.total,
		}
		found = [Rarity(scope, total, tier) for scope, total in runs.items() if (tier := rarity_tier(total))]
		order = [tier for _, tier in RARITY_TIERS]
		return sorted(found, key=lambda r: (order.index(r.tier), r.total))

	def as_dict(self) -> dict:
		rarities = self.rarities
		return {
			**asdict(self),
			"breakdowns": [{**asdict(b), "description": b.description} for b in self.breakdowns],
			"vehicle_name": self.vehicle_name,
			"rarities": [{**asdict(r), "description": r.description} for r in rarities],
			"rarest": rarities[0].tier if rarities else None,
		}


# Per-code pages (card 330): a page for each exterior paint, interior and (per model code) option code, with its
# production stats from the factory records.
CODE_KINDS = ("paint", "interior", "option")
# What CAPS writes instead of a code when it holds none for a car; never a code page of its own.
PLACEHOLDER_CODES = {"paint": "EXT", "interior": "INT", "option": "EQU"}
CODE_PATTERN = re.compile(r"^[A-Z0-9]{2,4}$")
MODEL_CODE_PATTERN = re.compile(r"^[A-Z][0-9]{2}[A-Z]$")  # Z11A, Z15A, Z16A
UNKNOWN_MODEL = "Other"  # a Model key with no Model name (none on the live record since 2026-10-27)


class InvalidCode(ValueError):
	"""Not a code page: an unknown kind, or a code or model code that cannot be one."""


def normalize_code(kind: str, raw: str | None) -> str:
	"""A paint / interior / option code in canonical form (upper case, no whitespace), or InvalidCode."""
	code = "".join((raw or "").split()).upper()
	if kind not in CODE_KINDS or not CODE_PATTERN.match(code) or code == PLACEHOLDER_CODES[kind]:
		raise InvalidCode(code)
	return code


def normalize_model_code(raw: str | None) -> str:
	"""A chassis model code (an option code's scope) in canonical form, or InvalidCode."""
	code = "".join((raw or "").split()).upper()
	if not MODEL_CODE_PATTERN.match(code):
		raise InvalidCode(code)
	return code


def build_order(built: str) -> str:
	"""A 'YYMMP' date as a sortable 'YYYYMMP' (2000's GTOs, built '00', sort after 1999)."""
	return full_year(built[0:2]) + built[2:]


BUILT_PATTERN = re.compile(r"^[0-9]{4}[1-3]$")


def build_span(dates) -> tuple[str, str] | None:
	"""The first and last of some 'YYMMP' build dates, in calendar order; None when none is a date."""
	valid = sorted((d for d in dates if d and BUILT_PATTERN.match(d)), key=build_order)
	return (valid[0], valid[-1]) if valid else None


def model_name(model: str | None) -> str:
	"""Model.Model as a breakdown name (3000GT, Stealth, GTO)."""
	return model if model and model != MISSING else UNKNOWN_MODEL


@dataclass(frozen=True)
class YearCount:
	model_year: str  # '1992'
	count: int


@dataclass(frozen=True)
class LineCount:
	"""A model line (Model key and chassis model code) and its cars."""

	manufacturer: str
	model: str
	trim: str
	model_code: str
	count: int

	@property
	def name(self) -> str:
		return (
			" ".join(p for p in (self.manufacturer, self.model, self.trim) if p and p != MISSING)
			or UNKNOWN_MODEL
		)


@dataclass(frozen=True)
class LineRow:
	"""One row of a code's production: cars of one model line built for one model year."""

	model_year: str  # 'YY'
	manufacturer: str | None
	model: str | None
	trim: str | None
	model_code: str
	count: int


@dataclass(frozen=True)
class Tally:
	total: int
	by_model: tuple[ModelCount, ...]  # largest first
	by_year: tuple[YearCount, ...]  # in model-year order
	by_line: tuple[LineCount, ...]  # largest first


def tally(rows) -> Tally:
	"""A code's production by model, by model year and by model line, from its LineRows."""
	models: dict[str, int] = {}
	years: dict[str, int] = {}
	lines: dict[tuple, int] = {}
	for row in rows:
		models[model_name(row.model)] = models.get(model_name(row.model), 0) + row.count
		year = full_year(row.model_year) if row.model_year else ""
		years[year] = years.get(year, 0) + row.count
		line = (row.manufacturer or "", row.model or "", row.trim or "", row.model_code)
		lines[line] = lines.get(line, 0) + row.count
	return Tally(
		total=sum(models.values()),
		by_model=tuple(
			sorted((ModelCount(m, n) for m, n in models.items()), key=lambda c: (-c.count, c.model))
		),
		by_year=tuple(YearCount(y, n) for y, n in sorted(years.items())),
		by_line=tuple(
			sorted(
				(LineCount(*line, n) for line, n in lines.items()),
				key=lambda c: (-c.count, c.name, c.model_code),
			)
		),
	)


@dataclass(frozen=True)
class Pairing:
	"""The other colour code a paint or interior was built with, and how many cars."""

	code: str  # "" when the record holds none (EXT / INT)
	description: str
	count: int


@dataclass(frozen=True)
class OptionFit:
	"""What an option code fits for one grade and model year, per Mitsubishi's catalogue (ASA: GTOs only)."""

	classification: Coded
	model_year: str  # '1992'
	items: tuple[Coded, ...]
	cars: int  # factory-record cars of this grade and model year with the code
	source: str


@dataclass(frozen=True)
class MakerName:
	manufacturer: str
	name: str


def paint_names(mitsubishi: str | None, dodge: str | None) -> tuple[str, tuple[MakerName, ...]]:
	"""A paint's description (Mitsubishi's name, else Dodge's, else MISSING) and its names per manufacturer."""
	names = tuple(
		MakerName(maker, name)
		for maker, name in (("Mitsubishi", mitsubishi), ("Dodge", dodge))
		if name and name != MISSING
	)
	return (names[0].name if names else MISSING), names


@dataclass(frozen=True)
class CodePage:
	"""A paint, interior or option code and its production in the factory records."""

	kind: str  # a CODE_KINDS value
	code: str
	model_code: str  # an option code's chassis model code; "" for paint and interior
	description: str  # MISSING while undeciphered
	names: tuple[MakerName, ...]  # a paint's name per manufacturer, where known
	total: int
	by_model: tuple[ModelCount, ...]
	by_year: tuple[YearCount, ...]
	by_line: tuple[LineCount, ...]
	first_built: str  # 'the 1st production period of ...'
	last_built: str
	pairings: tuple[Pairing, ...] = ()  # paint: its interiors; interior: its paints
	fits: tuple[OptionFit, ...] = ()  # option: what it fits, per grade and model year
	same_paint: tuple[str, ...] = ()  # paint: its other codes (an "A" form like TA7 for T87), counted with it

	def as_dict(self) -> dict:
		return {
			**asdict(self),
			"by_line": [{**asdict(line), "name": line.name} for line in self.by_line],
		}


@dataclass(frozen=True)
class CodeIndexEntry:
	"""A code on a kind's index page: its total and models."""

	code: str
	model_code: str
	description: str
	total: int
	by_model: tuple[ModelCount, ...]


# The code pages' dynamic Web Page routes under a site's prefix (card 330), and the page each code has there.
CODE_PAGE_ROUTES = {
	"paint": "storyteller/paint/<code>",
	"interior": "storyteller/interior/<code>",
	"option": "storyteller/option/<model>/<code>",
}


def code_page_endpoint(prefix: str, kind: str, code: str, model_code: str = "") -> str:
	"""A code page's endpoint under the site prefix: ``3shub-ca/storyteller/option/Z16A/302``."""
	tail = f"{model_code}/{code}" if kind == "option" else code
	return f"{prefix}/storyteller/{kind}/{tail}"


def code_page_endpoints(prefix: str, index: dict[str, tuple]) -> list[str]:
	"""Every code page under ``prefix`` for the sitemap, from each kind's code index entries."""
	return [
		code_page_endpoint(prefix, kind, entry.code, entry.model_code)
		for kind in CODE_KINDS
		for entry in index.get(kind, ())
		if kind != "option" or entry.model_code
	]
