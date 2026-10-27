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
FACTORY_PROVENANCES = (CAPS, CAPS_2004, ASA_JAPAN)

# ISO 3779 check digit (the VIN's 9th character): every one of the 236,589 CAPS VINs has a correct one, so a VIN
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


def is_chassis_record(vin: str) -> bool:
	"""A Production key that is a JDM chassis number rather than a 17-character VIN."""
	return len(vin) != 17


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
	equipment_items: tuple[Coded, ...] = ()  # what the equipment (option) code fits, item by item
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
