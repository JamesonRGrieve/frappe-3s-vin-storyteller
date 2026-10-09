# SPDX-License-Identifier: AGPL-3.0-or-later
"""The story of a 3000GT / Stealth, told from its VIN and its factory production record.

Pure logic: no Frappe and no database here, so every rule is unit-testable.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")  # 17 characters, never I, O or Q
CENTURY = "19"  # every car in the production record is a 1990s model year
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


def full_year(two_digit_year: str) -> str:
	return f"{CENTURY}{two_digit_year}"


def describe_production_date(code: str) -> str:
	"""A 'YYMMP' production date (year, month, period 1-3) as 'the 2nd production period of March, 1992'."""
	year, month, period = code[0:2], code[2:4], code[4:5]
	month_name = (
		calendar.month_name[int(month)] if month.isdigit() and 1 <= int(month) <= 12 else "an unknown month"
	)
	return f"the {PERIOD_NAMES.get(period, 'Unknown')} production period of {month_name}, {full_year(year)}"


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
	provenance: str  # where this VIN's production record came from, e.g. CAPS
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

	@property
	def vehicle_name(self) -> str:
		return " ".join(part for part in (self.model_year, self.manufacturer, self.model, self.trim) if part)

	@property
	def rarities(self) -> list[Rarity]:
		"""Every scope in which this car is rare, rarest first."""
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
			"vehicle_name": self.vehicle_name,
			"rarities": [{**asdict(r), "description": r.description} for r in rarities],
			"rarest": rarities[0].tier if rarities else None,
		}
