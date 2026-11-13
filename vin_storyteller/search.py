# SPDX-License-Identifier: AGPL-3.0-or-later
"""Car search on the stats page (operator, 2026-11-12: search alongside the charts, full VINs). Pure: the request's
parameters as a SearchQuery, and a result row's shape. The repository runs the query; region and market are named
by stats.region_of, the same way the charts name them, so a search and a chart always agree.
"""

from __future__ import annotations

import csv
import io
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
LINE_PATTERN = re.compile(r"^[A-Z0-9]{2}$")  # a Model key: 'VR', 'TT', 'G6', 'AU'
# A build month 'YYMM' or production period 'YYMMP'.
BUILT_PATTERN = re.compile(r"^[0-9]{2}(0[1-9]|1[0-2])[1-3]?$")
SERIES = ("us", "jdm", "export", "au")  # story.MARKET_MODELS's numbering series, plus North America ('us')
SORTS = ("", "vin", "built", "paint", "interior", "option", "grade")  # '' = model year, then VIN
BREAKDOWN_TOP = 12  # values a breakdown names; the rest are summed as 'other'


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
	missing_only: bool = False  # list the known missing VIN ranges the filters cover
	lines: tuple[str, ...] = ()  # Model keys (model line: 3000GT VR-4 'VR', Stealth R/T Turbo 'TT' ...)
	built_from: str = ""  # 'YYMM' or 'YYMMP', inclusive
	built_to: str = ""
	sort: str = ""
	descending: bool = False
	exact_paint: bool = False  # the paint code itself, not its whole family (the story's identical-car count)
	series: str = ""  # a numbering series ('us', 'jdm', 'export', 'au'): the scope a story's counts run in

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
			or self.missing_only
			or self.lines
			or self.built_from
			or self.built_to
			or self.series
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


def _built(params: dict, name: str) -> str:
	built = str(params.get(name) or "").strip()
	if built and not BUILT_PATTERN.match(built):
		raise InvalidSearch(f"{name} must be a build month YYMM or production period YYMMP")
	return built


def parse_query(params: dict) -> SearchQuery:
	"""A search from request parameters (q, model, market, region, from, to, paint, interior, option, page; line,
	built or built_from/built_to, sort, desc, exact, series)."""
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
	lines = tuple(line.upper() for line in _list(params, "line"))
	if any(not LINE_PATTERN.match(line) for line in lines):
		raise InvalidSearch("line must be a 2-character model line code")
	built_from, built_to = _built(params, "built_from"), _built(params, "built_to")
	if params.get("built"):
		built_from = built_to = _built(params, "built")
	series = str(params.get("series") or "").strip().lower()
	if series and series not in SERIES:
		raise InvalidSearch("series must be one of " + ", ".join(SERIES))
	sort = str(params.get("sort") or "").strip().lower()
	if sort not in SORTS:
		raise InvalidSearch("sort must be one of " + ", ".join(s for s in SORTS if s))
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
		missing_only=str(params.get("missing") or "").strip().lower() in ("1", "true", "yes"),
		lines=lines,
		built_from=built_from,
		built_to=built_to,
		sort=sort,
		descending=str(params.get("desc") or "").strip().lower() in ("1", "true", "yes"),
		exact_paint=str(params.get("exact") or "").strip().lower() in ("1", "true", "yes"),
		series=series,
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
	line_code: str  # the Model key ('VR')
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
		line_code=(_key or "").strip(),
		region=region.name,
		market=region.market,
		provenance=provenance or "",
	)


MISSING_MAX = 500  # missing ranges one answer lists
NORTH_AMERICAN_REGIONS = {"Federal (49-state)", "California", "Canada"}
AUSTRALIAN_YEARS = {"92", "93", "94", "95"}  # the 117 Australian cars' year letters N, P, R, S
FULL_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


@dataclass(frozen=True)
class MissingEntry:
	"""A known missing VIN range (or the one VIN searched for inside one): shown red, for owners to send their tag."""

	market: str  # 'us' / 'au'
	model_year: str  # '1991', '' when not known (Australia)
	vin: str  # the VIN searched for, or the range as a pattern: 'J*3******MY000518-000704'
	first: str
	last: str
	count: int
	note: str


def missing_markets(query: SearchQuery) -> tuple[str, ...]:
	"""Which missing-range markets ('us', 'au') the query's model, market and region filters can cover."""
	markets = {"us", "au"}
	if query.models:
		if "Stealth" not in query.models and "3000GT" not in query.models:
			return ()
		if "3000GT" not in query.models:
			markets.discard("au")  # the Australian cars are 3000GTs
	chosen = set(query.markets) | {
		"North America" if r in NORTH_AMERICAN_REGIONS or r.startswith("North America") else r
		for r in query.regions
	}
	if chosen:
		markets &= {m for m, name in (("us", "North America"), ("au", "Australia")) if name in chosen}
	return tuple(sorted(markets))


def searched_serial(text: str) -> tuple[str, str, str] | None:
	"""(market or '', year letter or '', serial) a search text names: a full US/Australian VIN, or a 6-digit serial."""
	if FULL_VIN.match(text):
		if text.startswith(("JA3", "JB3")):
			return "us", text[9], text[11:]
		if text.startswith("JMF"):
			return "au", text[9], text[11:]
		return None
	if re.fullmatch(r"[0-9]{6}", text):
		return "", "", text
	return None


def missing_entry(row: tuple, vin: str = "") -> MissingEntry:
	market, year, pattern, first, last, note = row
	span = first if first == last else f"{first}-{last}"
	return MissingEntry(
		market=market,
		model_year=full_year(year) if year else "",
		vin=vin or f"{pattern}{span}",
		first=first,
		last=last,
		count=int(last) - int(first) + 1,
		note=note,
	)


def calendar_built(built: str) -> str:
	"""A 'YYMMP' build date as a sortable key: 2000's '00…' after the 1990s."""
	return ("1" if built[:2] < "50" else "0") + built if built else ""


def in_built_range(built: str, low: str, high: str) -> bool:
	"""Whether a car's 'YYMMP' falls in [low, high] (each 'YYMM' or 'YYMMP'); open ends are unbounded."""
	if not built:
		return not (low or high)
	key = calendar_built(built)
	if low and key[: len(low) + 1] < calendar_built(low):
		return False
	return not (high and key[: len(high) + 1] > calendar_built(high))


SORT_KEYS = {
	"": lambda c: (c.model_year, c.vin),
	"vin": lambda c: (c.vin,),
	"built": lambda c: (calendar_built(c.built), c.vin),
	"paint": lambda c: (c.paint, c.model_year, c.vin),
	"interior": lambda c: (c.interior, c.model_year, c.vin),
	"option": lambda c: (c.model_code, c.option, c.model_year, c.vin),
	"grade": lambda c: (c.model_code, c.classification, c.model_year, c.vin),
}


def sorted_cars(cars: list[FoundCar], query: SearchQuery) -> list[FoundCar]:
	"""The search's cars in the order asked for (model year, then VIN, by default)."""
	return sorted(cars, key=SORT_KEYS[query.sort], reverse=query.descending)


@dataclass(frozen=True)
class Share:
	"""One value's share of a search's cars."""

	code: str
	name: str
	count: int
	percent: float


BREAKDOWNS = ("paint", "interior", "option", "grade", "line", "model_year", "region")


def breakdown(cars: list[FoundCar], names: dict[str, dict[str, str]]) -> dict[str, list[dict]]:
	"""How a search's cars split by paint, interior, option, grade, model line, model year and region: the
	BREAKDOWN_TOP largest values with counts and percentages, the rest summed as 'other'. `names` gives display
	names per facet and code (paint and interior names, grade texts)."""
	total = len(cars)
	facets = {
		"paint": lambda c: c.paint,
		"interior": lambda c: c.interior,
		"option": lambda c: f"{c.model_code} {c.option}".strip(),
		"grade": lambda c: f"{c.model_code} {c.classification}".strip(),
		"line": lambda c: c.line,
		"model_year": lambda c: c.model_year,
		"region": lambda c: c.region,
	}
	out: dict[str, list[dict]] = {}
	for facet, value in facets.items():
		counts: dict[str, int] = {}
		for car in cars:
			counts[value(car) or ""] = counts.get(value(car) or "", 0) + 1
		ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
		if facet == "model_year":
			ranked = sorted(counts.items())
		shares = [
			Share(code, names.get(facet, {}).get(code, ""), n, round(100 * n / total, 1))
			for code, n in ranked
		]
		if facet != "model_year" and len(shares) > BREAKDOWN_TOP:
			rest = sum(s.count for s in shares[BREAKDOWN_TOP:])
			shares = [*shares[:BREAKDOWN_TOP], Share("other", "Other", rest, round(100 * rest / total, 1))]
		out[facet] = [asdict(s) for s in shares]
	return out


CSV_COLUMNS = (
	"vin",
	"model_year",
	"model",
	"line",
	"model_code",
	"classification",
	"option",
	"paint",
	"interior",
	"built",
	"region",
	"market",
	"provenance",
)


def csv_text(cars: list[FoundCar]) -> str:
	"""A search's cars as CSV (every matching car, in the search's order)."""
	buffer = io.StringIO()
	writer = csv.writer(buffer, lineterminator="\n")
	writer.writerow(CSV_COLUMNS)
	for car in cars:
		writer.writerow([getattr(car, column) for column in CSV_COLUMNS])
	return buffer.getvalue()
