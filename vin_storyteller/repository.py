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
	CAPS,
	MISSING,
	Coded,
	Gap,
	HistoryRecord,
	Neighbour,
	Position,
	Story,
	describe_production_date,
	exterior_description,
	full_year,
	safe_url,
	year_code,
)

SECOND_SERIES = (
	"800000"  # 1995-96 also have an 8xxxxx VIN series (its own SerialNumber run); gaps stay within a series
)

PARAMSTYLES = {"format": "%s", "qmark": "?"}  # PyMySQL uses %s, sqlite3 uses ?


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

	def _count(self, where: str, params: tuple) -> int:
		"""Cars in the factory export matching `where`: records from other sources never shift a CAPS count."""
		return int(
			self._one(
				f"SELECT COUNT(*) FROM Production WHERE ({where}) AND Provenance = %s", (*params, CAPS)
			)[0]
		)

	def car(self, vin: str) -> Car | None:
		row = self._one(
			"SELECT SerialNumber, Model, ModelCode, Equipment, Exterior, Interior, DateOfManufacture, ModelYear, "
			"Provenance FROM Production WHERE VIN = %s LIMIT 1",
			(vin,),
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

		year_start = self._one(
			"SELECT MIN(DateOfManufacture) FROM Production WHERE ModelYear = %s AND Provenance = %s",
			(car.model_year, CAPS),
		)
		model_start = self._one(
			f"SELECT MIN(DateOfManufacture) FROM Production WHERE {same_line} AND Provenance = %s",
			(*line, CAPS),
		)
		if car.provenance != CAPS:
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
			)

		return Story(
			vin=vin,
			provenance=car.provenance,
			history=self.history(vin),
			model_year=full_year(car.model_year),
			manufacturer=manufacturer or MISSING,
			model=model_name or MISSING,
			trim=trim or "",
			exterior=Coded(car.exterior, exterior_description(manufacturer, *paint) if paint else MISSING),
			interior=Coded(car.interior, self._description("Interior", "InteriorCode", car.interior)),
			equipment=Coded(car.equipment, self._description("Equipment", "EquipmentCode", car.equipment)),
			built=describe_production_date(car.built),
			built_in_period=self._count("DateOfManufacture = %s", (car.built,)),
			built_in_month=self._count("SUBSTR(DateOfManufacture, 1, 4) = %s", (car.built[0:4],)),
			year_started=describe_production_date(year_start[0]),
			model_started=describe_production_date(model_start[0]),
			in_year=Position(
				self._count("ModelYear = %s" + earlier, (car.model_year, car.serial)) + 1,
				self._count("ModelYear = %s", (car.model_year,)),
			),
			in_model=Position(
				self._count(same_line + earlier, (*line, car.serial)) + 1,
				self._count(same_line, line),
			),
			in_colour=Position(
				self._count(same_colour + earlier, (*colour, car.serial)) + 1,
				self._count(same_colour, colour),
			),
			among_identical=Position(
				self._count(identical + earlier, (*spec, car.serial)) + 1,
				self._count(identical, spec),
			),
		)

	def gap(self, vin: str) -> Gap | None:
		"""The nearest cars on record either side of an unrecorded VIN's serial, in its model year and series."""
		year = year_code(vin)
		if year is None:
			return None
		serial = vin[11:]
		series = ">= %s" if serial >= SECOND_SERIES else "< %s"
		where = f"ModelYear = %s AND SUBSTR(VIN, 12, 6) {series}"
		before = self._one(
			f"SELECT SUBSTR(VIN, 12, 6), DateOfManufacture FROM Production WHERE {where} AND SUBSTR(VIN, 12, 6) < %s "
			"ORDER BY SUBSTR(VIN, 12, 6) DESC LIMIT 1",
			(year, SECOND_SERIES, serial),
		)
		after = self._one(
			f"SELECT SUBSTR(VIN, 12, 6), DateOfManufacture FROM Production WHERE {where} AND SUBSTR(VIN, 12, 6) > %s "
			"ORDER BY SUBSTR(VIN, 12, 6) LIMIT 1",
			(year, SECOND_SERIES, serial),
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
