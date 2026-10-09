# SPDX-License-Identifier: AGPL-3.0-or-later
"""A real SQLite database shaped like the CAPS dump of 3s_production, seeded with a small production run.

`caps_connection` is the dump as loaded (no migrations yet); `connection` is that plus every migration and a
few history records, as the live database is once deployed.
"""

import sqlite3

import pytest

from vin_storyteller.migrations import migrate
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import MISSING

SCHEMA = """
CREATE TABLE Production (
	ID INTEGER PRIMARY KEY, SerialNumber CHAR(8) NOT NULL, VIN CHAR(17) NOT NULL, Model CHAR(2) NOT NULL,
	ModelCode CHAR(4) NOT NULL, Classification CHAR(7) NOT NULL, Equipment CHAR(3) NOT NULL,
	Exterior CHAR(3) NOT NULL, Interior CHAR(3) NOT NULL, DateOfManufacture CHAR(5) NOT NULL,
	ModelYear CHAR(2) NOT NULL
);
CREATE TABLE Model (ModelCode CHAR(2) PRIMARY KEY, Manufacturer VARCHAR(10), Model VARCHAR(7), Trim VARCHAR(20));
CREATE TABLE Exterior (ExteriorCode CHAR(3) PRIMARY KEY, MitsubishiDescription VARCHAR(30) NOT NULL,
	DodgeDescription VARCHAR(30) NOT NULL);
CREATE TABLE Interior (InteriorCode CHAR(3) PRIMARY KEY, Description VARCHAR(30) NOT NULL);
CREATE TABLE Equipment (EquipmentCode CHAR(3) PRIMARY KEY, Description VARCHAR(100) NOT NULL);
"""

MODELS = [("M1", "Mitsubishi", "3000GT", "VR-4"), ("D1", "Dodge", "Stealth", "R/T Turbo")]
EXTERIORS = [("T87", "Fiji Blue", "Bright Blue"), ("R25", "Morocco Red", MISSING)]
INTERIORS = [("12A", "Grey")]
EQUIPMENT = [("XA1", "Leather")]

# (serial, vin, model, model code, equipment, exterior, interior, built YYMMP, model year)
CARS = [
	("00004500", "JA3AM84J3NY000001", "M1", "Z16A", "XA1", "T87", "12A", "91092", "92"),  # first of MY92
	("00004510", "JA3AM84J3NY000002", "M1", "Z16A", "XA1", "T87", "12A", "91093", "92"),
	("00004520", "JA3AM84J3NY000003", "M1", "Z16A", "XA1", "R25", "12A", "92031", "92"),  # one of one
	(
		"00004530",
		"JA3AM84J3NY000004",
		"M1",
		"Z16A",
		"XA1",
		"T87",
		"12A",
		"92032",
		"92",
	),  # main car under test
	("00004540", "JA3AM84J3NY000005", "M1", "Z16A", "XA1", "T87", "12A", "92032", "92"),
	("00004505", "1B3XC64B7NS000006", "D1", "Z16D", "XA1", "R25", "12A", "91101", "92"),
	("00004535", "1B3XC64B7NS000007", "D1", "Z16D", "XA1", "R25", "99Z", "92032", "92"),  # unknown interior
	("00001000", "JA3AM84J3MY000008", "M1", "Z16A", "XA1", "T87", "12A", "90101", "91"),  # other model year
	("00004550", "JA3AM84J3NY000009", "ZZ", "Z16X", "QQQ", "XXX", "12A", "92033", "92"),  # unknown codes
]

# (vin, type, title, url, date, source, provenance)
HISTORY = [
	("JA3AM84J3NY000004", "photo", "Owner photos", "https://example.com/photos", None, "owner", "owner"),
	(
		"JA3AM84J3NY000004",
		"auction",
		"Sold at auction",
		"https://example.com/lot/1",
		"2021-05-01",
		"BaT",
		"op",
	),
	("JA3AM84J3NY000004", "sale", "Private sale", "javascript:alert(1)", "2015-02-03", None, "op"),
]


@pytest.fixture
def caps_connection():
	connection = sqlite3.connect(":memory:")
	connection.executescript(SCHEMA)
	connection.executemany("INSERT INTO Model VALUES (?, ?, ?, ?)", MODELS)
	connection.executemany("INSERT INTO Exterior VALUES (?, ?, ?)", EXTERIORS)
	connection.executemany("INSERT INTO Interior VALUES (?, ?)", INTERIORS)
	connection.executemany("INSERT INTO Equipment VALUES (?, ?)", EQUIPMENT)
	connection.executemany(
		"INSERT INTO Production (SerialNumber, VIN, Model, ModelCode, Classification, Equipment, Exterior, "
		"Interior, DateOfManufacture, ModelYear) VALUES (?, ?, ?, ?, 'CLASS01', ?, ?, ?, ?, ?)",
		CARS,
	)
	yield connection
	connection.close()


@pytest.fixture
def connection(caps_connection):
	migrate(caps_connection, "sqlite")  # after the CAPS rows, exactly as on the live database
	caps_connection.executemany(
		"INSERT INTO VehicleHistory (VIN, RecordType, Title, URL, RecordDate, Source, Provenance) "
		"VALUES (?, ?, ?, ?, ?, ?, ?)",
		HISTORY,
	)
	return caps_connection


@pytest.fixture
def records(connection):
	return ProductionRecords(connection, paramstyle="qmark")
