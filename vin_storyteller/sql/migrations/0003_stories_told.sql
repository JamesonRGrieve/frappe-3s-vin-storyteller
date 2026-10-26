-- SPDX-License-Identifier: AGPL-3.0-or-later
-- The log of stories told, as the original storyteller kept it: the VIN, the name the visitor gave, the hour
-- and the time. The CAPS-era database already has this table with its history; a new database gets it here.
CREATE TABLE IF NOT EXISTS StoriesTold (
	ID INTEGER PRIMARY KEY {autoincrement},
	VIN VARCHAR(17) NOT NULL,
	Name VARCHAR(100) NOT NULL,
	DateHour DATETIME NOT NULL,
	Time DATETIME NOT NULL
)
