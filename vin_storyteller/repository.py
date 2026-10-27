# SPDX-License-Identifier: AGPL-3.0-or-later
"""Queries against the factory production record (the `3s_production` database): read-only lookups, plus the
log of stories told (`record_story`).

Every value is a bound parameter. The SQL sticks to what both MariaDB and SQLite run (SUBSTR, MIN,
COUNT), so the same queries are tested against a real SQLite database and served from MariaDB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from vin_storyteller.story import (
	FACTORY_PROVENANCES,
	MARKET_MODELS,
	MISSING,
	Breakdown,
	Coded,
	Gap,
	HistoryRecord,
	ModelCount,
	Neighbour,
	Position,
	Story,
	describe_production_date,
	exterior_description,
	full_year,
	market_of,
	safe_url,
	year_code,
)

SECOND_SERIES = (
	"800000"  # 1995-96 also have an 8xxxxx VIN series (its own SerialNumber run); gaps stay within a series
)

PARAMSTYLES = {"format": "%s", "qmark": "?"}  # PyMySQL uses %s, sqlite3 uses ?
FACTORY = "Provenance IN (" + ", ".join(["%s"] * len(FACTORY_PROVENANCES)) + ")"
# Positions and totals stay within a car's own market and numbering (17-character VINs or JDM chassis numbers),
# so the original storyteller's counts are unchanged; the cross-model breakdowns span both.
_NON_US = "(" + ", ".join(f"'{m}'" for models in MARKET_MODELS.values() for m in models) + ")"
MARKETS = {
	"us": f"Model NOT IN {_NON_US}",
	**{
		market: "Model IN (" + ", ".join(f"'{m}'" for m in models) + ")"
		for market, models in MARKET_MODELS.items()
	},
}
LANGUAGE = "en"


@dataclass(frozen=True)
class Car:
	"""A car's row in Production."""

	serial: str
	model: str  # key into the Model table
	model_code: str
	equipment: str
	exterior: str
	interior: str
	built: str  # 'YYMMP'
	model_year: str  # 'YY'
	provenance: str
	classification: str = ""


# CAPS writes these instead of a code when it holds no colour or interior for a car (e.g. 285 1991 VR-4s).
NOT_RECORDED_CODES = {"EXT", "INT"}


def _unrecorded(code: str) -> Coded | None:
	"""A placeholder code as 'not recorded' (no code), else None."""
	return Coded("", MISSING) if code.strip() in NOT_RECORDED_CODES else None


def _full_date(built: str) -> str:
	"""'YYMMP' -> 'YYYYMMP', the ASA catalogue's date form."""
	return full_year(built[0:2]) + built[2:] if len(built) == 5 else ""


class ProductionRecords:
	def __init__(self, connection, paramstyle: str = "format"):
		self.connection = connection
		self.placeholder = PARAMSTYLES[paramstyle]

	def _rows(self, sql: str, params: tuple) -> list[tuple]:
		cursor = self.connection.cursor()
		try:
			cursor.execute(sql.replace("%s", self.placeholder), params)
			return list(cursor.fetchall())
		finally:
			cursor.close()

	def _one(self, sql: str, params: tuple) -> tuple | None:
		rows = self._rows(sql, params)
		return rows[0] if rows else None

	def _count(self, where: str, params: tuple, market: str = "us") -> int:
		"""Factory-record cars in the same market matching `where`: records from other sources never shift a count."""
		return int(
			self._one(
				f"SELECT COUNT(*) FROM Production WHERE ({where}) AND {FACTORY} AND {MARKETS[market]}",
				(*params, *FACTORY_PROVENANCES),
			)[0]
		)

	def _breakdown(self, scope: str, where: str, params: tuple) -> Breakdown:
		"""Factory-record cars of every model and market matching `where`, by model (3000GT, Stealth, GTO)."""
		rows = self._rows(
			"SELECT m.Model, COUNT(*) FROM Production p JOIN Model m ON m.ModelCode = p.Model "
			f"WHERE ({where}) AND p.{FACTORY} AND m.Model <> %s GROUP BY m.Model",
			(*params, *FACTORY_PROVENANCES, MISSING),
		)
		counts = tuple(
			sorted((ModelCount(model, int(n)) for model, n in rows), key=lambda c: (-c.count, c.model))
		)
		return Breakdown(scope, sum(c.count for c in counts), counts)

	def breakdowns(self, car: Car) -> tuple[Breakdown, ...]:
		"""What this car shares with the rest of the factory record, across every model."""
		scopes = [("year", "p.ModelYear = %s", (car.model_year,))]
		exterior_known = car.exterior.strip() not in NOT_RECORDED_CODES | {""}
		interior_known = car.interior.strip() not in NOT_RECORDED_CODES | {""}
		if exterior_known:
			scopes += [
				("colour", "p.Exterior = %s", (car.exterior,)),
				("colour_year", "p.Exterior = %s AND p.ModelYear = %s", (car.exterior, car.model_year)),
			]
		if interior_known:
			scopes.append(("interior", "p.Interior = %s", (car.interior,)))
		if exterior_known and interior_known:
			scopes.append(("colours", "p.Exterior = %s AND p.Interior = %s", (car.exterior, car.interior)))
		scopes += [
			("period", "p.DateOfManufacture = %s", (car.built,)),
			("month", "SUBSTR(p.DateOfManufacture, 1, 4) = %s", (car.built[0:4],)),
		]
		return tuple(self._breakdown(scope, where, params) for scope, where, params in scopes)

	def classification(self, car: Car) -> Coded:
		"""The grade code and Mitsubishi's description of it: the exact code, else the same first four characters
		(CAPS splits a grade by destination, e.g. MJGFL2M federal / MJGFL7M California)."""
		if not car.classification:
			return Coded("", "")
		row = self._one(
			"SELECT Description FROM ClassificationLabel WHERE ModelCode = %s AND Classification = %s "
			"AND Language = %s ORDER BY Source DESC LIMIT 1",
			(car.model_code, car.classification.strip(), LANGUAGE),
		) or self._one(
			"SELECT Description FROM ClassificationLabel WHERE ModelCode = %s AND SUBSTR(Classification, 1, 4) = %s "
			"AND Language = %s ORDER BY Source DESC, Classification LIMIT 1",
			(car.model_code, car.classification.strip()[0:4], LANGUAGE),
		)
		return Coded(car.classification.strip(), row[0] if row else MISSING)

	def equipment_items(self, car: Car) -> tuple[Coded, ...]:
		"""What the car's option code fits, from the catalogue entry for its model, grade and model year."""
		row = self._one(
			"SELECT Items FROM OptionContent WHERE ModelCode = %s AND OptionCode = %s AND Classification = %s "
			"AND ModelYear = %s AND StartDate <= %s AND EndDate >= %s ORDER BY Source DESC LIMIT 1",
			(
				car.model_code,
				car.equipment,
				car.classification.strip(),
				car.model_year,
				*(_full_date(car.built),) * 2,
			),
		) or self._one(
			"SELECT Items FROM OptionContent WHERE ModelCode = %s AND OptionCode = %s AND Classification = %s "
			"AND ModelYear = %s ORDER BY Source DESC LIMIT 1",
			(car.model_code, car.equipment, car.classification.strip(), car.model_year),
		)
		if not row or not row[0]:
			return ()
		items = []
		for code in row[0].split(","):
			label = self._one(
				"SELECT Description FROM OptionItem WHERE ItemCode = %s AND Language = %s ORDER BY Source DESC LIMIT 1",
				(code, LANGUAGE),
			)
			items.append(Coded(code, label[0] if label else MISSING))
		return tuple(items)

	def car(self, vin: str) -> Car | None:
		row = self._one(
			"SELECT SerialNumber, Model, ModelCode, Equipment, Exterior, Interior, DateOfManufacture, ModelYear, "
			f"Provenance, Classification FROM Production WHERE VIN = %s ORDER BY {FACTORY} DESC LIMIT 1",
			(vin, *FACTORY_PROVENANCES),
		)
		return Car(*row) if row else None

	def history(self, vin: str) -> tuple[HistoryRecord, ...]:
		"""What is known about the car after the factory, oldest first (undated last)."""
		rows = self._rows(
			"SELECT RecordType, Title, URL, RecordDate, Source, Provenance FROM VehicleHistory "
			"WHERE VIN = %s ORDER BY RecordDate IS NULL, RecordDate, ID",
			(vin,),
		)
		return tuple(
			HistoryRecord(kind, title, safe_url(url), str(date) if date else None, source, provenance)
			for kind, title, url, date, source, provenance in rows
		)

	def _description(self, table: str, key: str, code: str) -> str:
		row = self._one(f"SELECT Description FROM {table} WHERE {key} = %s", (code,))
		return row[0] if row else MISSING

	def story(self, vin: str) -> Story | None:
		car = self.car(vin)
		if car is None:
			return None
		model = self._one("SELECT Manufacturer, Model, Trim FROM Model WHERE ModelCode = %s", (car.model,))
		manufacturer, model_name, trim = model if model else (MISSING, MISSING, "")
		paint = self._one(
			"SELECT MitsubishiDescription, DodgeDescription FROM Exterior WHERE ExteriorCode = %s",
			(car.exterior,),
		)

		same_line = "ModelYear = %s AND Model = %s AND ModelCode = %s"
		line = (car.model_year, car.model, car.model_code)
		identical = f"{same_line} AND Interior = %s AND Exterior = %s AND Equipment = %s"
		spec = (*line, car.interior, car.exterior, car.equipment)
		same_colour = f"{same_line} AND Exterior = %s"
		colour = (*line, car.exterior)
		earlier = " AND SerialNumber < %s"

		chassis = market_of(car.model)  # the car's market: positions and totals count within it
		market = MARKETS[chassis]
		year_start = self._one(
			f"SELECT MIN(DateOfManufacture) FROM Production WHERE ModelYear = %s AND {FACTORY} AND {market}",
			(car.model_year, *FACTORY_PROVENANCES),
		)
		model_start = self._one(
			f"SELECT MIN(DateOfManufacture) FROM Production WHERE {same_line} AND {FACTORY}",
			(*line, *FACTORY_PROVENANCES),
		)
		if car.provenance not in FACTORY_PROVENANCES:
			return Story(
				vin=vin,
				provenance=car.provenance,
				history=self.history(vin),
				model_year=full_year(car.model_year) if car.model_year else "",
				manufacturer=manufacturer or MISSING,
				model=model_name or MISSING,
				trim=trim or "",
				exterior=Coded(car.exterior, MISSING),
				interior=Coded(car.interior, MISSING),
				equipment=Coded(car.equipment, MISSING),
				built="",
				built_in_period=0,
				built_in_month=0,
				year_started=describe_production_date(year_start[0]) if year_start and year_start[0] else "",
				model_started=describe_production_date(model_start[0])
				if model_start and model_start[0]
				else "",
				in_year=Position(0, 0),
				in_model=Position(0, 0),
				in_colour=Position(0, 0),
				among_identical=Position(0, 0),
				partial=True,
				classification=self.classification(car),
			)

		return Story(
			vin=vin,
			provenance=car.provenance,
			history=self.history(vin),
			model_year=full_year(car.model_year),
			manufacturer=manufacturer or MISSING,
			model=model_name or MISSING,
			trim=trim or "",
			exterior=_unrecorded(car.exterior)
			or Coded(car.exterior, exterior_description(manufacturer, *paint) if paint else MISSING),
			interior=_unrecorded(car.interior)
			or Coded(car.interior, self._description("Interior", "InteriorCode", car.interior)),
			equipment=Coded(car.equipment, self._description("Equipment", "EquipmentCode", car.equipment)),
			built=describe_production_date(car.built),
			built_in_period=self._count("DateOfManufacture = %s", (car.built,), chassis),
			built_in_month=self._count("SUBSTR(DateOfManufacture, 1, 4) = %s", (car.built[0:4],), chassis),
			year_started=describe_production_date(year_start[0]),
			model_started=describe_production_date(model_start[0]),
			in_year=Position(
				self._count("ModelYear = %s" + earlier, (car.model_year, car.serial), chassis) + 1,
				self._count("ModelYear = %s", (car.model_year,), chassis),
			),
			in_model=Position(
				self._count(same_line + earlier, (*line, car.serial), chassis) + 1,
				self._count(same_line, line, chassis),
			),
			in_colour=Position(
				self._count(same_colour + earlier, (*colour, car.serial), chassis) + 1,
				self._count(same_colour, colour, chassis),
			),
			among_identical=Position(
				self._count(identical + earlier, (*spec, car.serial), chassis) + 1,
				self._count(identical, spec, chassis),
			),
			classification=self.classification(car),
			equipment_items=self.equipment_items(car),
			breakdowns=self.breakdowns(car),
		)

	def gap(self, vin: str) -> Gap | None:
		"""The nearest cars on record either side of an unrecorded VIN's serial, in its model year and series."""
		year = year_code(vin)
		if year is None:
			return None
		serial = vin[11:]
		# Neighbours come from the factory export only: a car added from another source has no build date.
		if serial >= SECOND_SERIES:
			occupied = (
				"SELECT SUBSTR(VIN, 12, 6) AS s, DateOfManufacture AS d FROM Production "
				f"WHERE ModelYear = %s AND {FACTORY} AND {MARKETS['us']} AND SUBSTR(VIN, 12, 6) >= %s"
			)
			params = (year, *FACTORY_PROVENANCES, SECOND_SERIES)
		else:
			# 1995-96's 8xxxxx-VIN cars take their place in the main run by their SerialNumber's digits.
			occupied = (
				"SELECT SUBSTR(VIN, 12, 6) AS s, DateOfManufacture AS d FROM Production "
				f"WHERE ModelYear = %s AND {FACTORY} AND {MARKETS['us']} AND SUBSTR(VIN, 12, 6) < %s "
				"UNION ALL SELECT SUBSTR(SerialNumber, 3, 6) AS s, DateOfManufacture AS d FROM Production "
				f"WHERE ModelYear = %s AND {FACTORY} AND {MARKETS['us']} AND SUBSTR(VIN, 12, 6) >= %s"
			)
			params = (year, *FACTORY_PROVENANCES, SECOND_SERIES, year, *FACTORY_PROVENANCES, SECOND_SERIES)
		before = self._one(
			f"SELECT s, d FROM ({occupied}) AS run WHERE s < %s ORDER BY s DESC LIMIT 1", (*params, serial)
		)
		after = self._one(
			f"SELECT s, d FROM ({occupied}) AS run WHERE s > %s ORDER BY s LIMIT 1", (*params, serial)
		)
		if before is None and after is None:
			return None
		return Gap(before=Neighbour(*before) if before else None, after=Neighbour(*after) if after else None)

	def record_story(self, vin: str, name: str, at: datetime) -> None:
		"""Log a story told, as the original storyteller did: the VIN, the visitor's name, the hour and the time."""
		cursor = self.connection.cursor()
		try:
			cursor.execute(
				"INSERT INTO StoriesTold (VIN, Name, DateHour, Time) VALUES (%s, %s, %s, %s)".replace(
					"%s", self.placeholder
				),
				(vin, name, at.replace(minute=0, second=0, microsecond=0), at.replace(microsecond=0)),
			)
		finally:
			cursor.close()
		self.connection.commit()
