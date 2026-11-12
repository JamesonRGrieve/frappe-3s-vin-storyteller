# SPDX-License-Identifier: AGPL-3.0-or-later
"""Car search on the stats page (operator, 2026-11-12: search alongside the charts, full VINs). Pure: the request's
parameters as a SearchQuery, and a result row's shape. The repository runs the query; region and market are named
by stats.region_of, the same way the charts name them, so a search and a chart always agree.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from vin_storyteller.story import CODE_PATTERN, full_year, model_name

PAGE_SIZE = 50
MAX_SCAN = 20000  # rows a search reads before region filtering; past it the answer says it was cut short
TEXT_PATTERN = re.compile(r"^[A-Z0-9-]{2,17}$")  # a VIN or chassis-number fragment, or a code
YEAR_PATTERN = re.compile(r"^(19|20)[0-9]{2}$")
FIRST_YEAR, LAST_YEAR = 1990, 2000
MODEL_NAMES = ("3000GT", "Stealth", "GTO")
LIST_MAX = 20  # values of one repeated filter


class InvalidSearch(ValueError):
	"""The request isn't a search: the message says why."""


@dataclass(frozen=True)
class SearchQuery:
	text: str = ""
	models: tuple[str, ...] = ()
	markets: tuple[str, ...] = ()
	regions: tuple[str, ...] = ()
	year_from: str = ""
	year_to: str = ""
	paint: str = ""
	interior: str = ""
	option: str = ""
	page: int = 1

	@property
	def narrowed(self) -> bool:
		return bool(
			self.text
			or self.paint
			or self.interior
			or self.option
			or self.models
			or self.regions
			or self.markets
			or self.year_from
			or self.year_to
		)

	def model_years(self) -> tuple[str, ...]:
		"""The 'YY' model-year codes the year range covers (all when it is open)."""
		low = int(self.year_from or FIRST_YEAR)
		high = int(self.year_to or LAST_YEAR)
		return tuple(str(y)[2:] for y in range(max(low, FIRST_YEAR), min(high, LAST_YEAR) + 1))

	def key(self) -> str:
		"""The cache key of this search."""
		return "|".join(str(v) if not isinstance(v, tuple) else ",".join(v) for v in asdict(self).values())


def _list(params: dict, name: str) -> tuple[str, ...]:
	raw = params.get(name) or ""
	values = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
	out = tuple(dict.fromkeys(v.strip() for v in values if v and v.strip()))
	if len(out) > LIST_MAX:
		raise InvalidSearch(f"too many values for {name}")
	return out


def _code(params: dict, name: str) -> str:
	code = str(params.get(name) or "").strip().upper()
	if code and not CODE_PATTERN.match(code):
		raise InvalidSearch(f"{name} must be a 2-4 character code")
	return code


def parse_query(params: dict) -> SearchQuery:
	"""A search from request parameters (q, model, market, region, from, to, paint, interior, option, page)."""
	text = re.sub(r"\s+", "", str(params.get("q") or "")).upper()
	if text and not TEXT_PATTERN.match(text):
		raise InvalidSearch(
			"search text is a VIN or chassis-number fragment or a code: 2-17 letters and digits"
		)
	years = {}
	for name in ("from", "to"):
		year = str(params.get(name) or "").strip()
		if year and not YEAR_PATTERN.match(year):
			raise InvalidSearch(f"{name} must be a year")
		years[name] = year
	models = _list(params, "model")
	if any(m not in MODEL_NAMES for m in models):
		raise InvalidSearch("model must be 3000GT, Stealth or GTO")
	try:
		page = max(1, int(params.get("page") or 1))
	except ValueError as error:
		raise InvalidSearch("page must be a number") from error
	return SearchQuery(
		text=text,
		models=models,
		markets=_list(params, "market"),
		regions=_list(params, "region"),
		year_from=years["from"],
		year_to=years["to"],
		paint=_code(params, "paint"),
		interior=_code(params, "interior"),
		option=_code(params, "option"),
		page=page,
	)


@dataclass(frozen=True)
class FoundCar:
	"""One car in a search's results: its record as stored, with its region named."""

	vin: str
	model_year: str  # '1992', '' when not recorded
	model: str  # 3000GT / Stealth / GTO
	line: str  # 'Mitsubishi 3000GT VR-4'
	model_code: str
	classification: str
	option: str
	paint: str
	interior: str
	built: str  # 'YYMMP' as stored ('' when not recorded)
	region: str
	market: str
	provenance: str


def found_car(row: tuple, region) -> FoundCar:
	"""A FoundCar from a repository row and its stats.Region."""
	(
		vin,
		year,
		_key,
		manufacturer,
		model,
		trim,
		model_code,
		grade,
		option,
		paint,
		interior,
		built,
		provenance,
	) = row
	line = " ".join(p for p in (manufacturer, model, trim) if p and p != "MISSING") or model_name(model)
	return FoundCar(
		vin=vin,
		model_year=full_year(year) if year else "",
		model=model_name(model),
		line=line,
		model_code=(model_code or "").strip(),
		classification=(grade or "").strip(),
		option=(option or "").strip(),
		paint=(paint or "").strip(),
		interior=(interior or "").strip(),
		built=(built or "").strip(),
		region=region.name,
		market=region.market,
		provenance=provenance or "",
	)
