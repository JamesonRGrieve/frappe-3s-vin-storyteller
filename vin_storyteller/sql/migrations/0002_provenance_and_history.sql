-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Where each production record came from (every record loaded so far is from the CAPS export), and a
-- history of what is known about each car after it left the factory: auctions, photos, sales and so on.
ALTER TABLE Production ADD COLUMN Provenance VARCHAR(30) NOT NULL DEFAULT 'CAPS';

CREATE TABLE VehicleHistory (
	ID INTEGER PRIMARY KEY {autoincrement},
	VIN CHAR(17) NOT NULL,
	RecordType VARCHAR(20) NOT NULL,
	Title VARCHAR(200) NOT NULL,
	URL VARCHAR(2048),
	RecordDate DATE,
	Source VARCHAR(100),
	Notes TEXT,
	Provenance VARCHAR(100) NOT NULL,
	CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	CHECK (RecordType IN ('auction', 'photo', 'sale', 'registration', 'service', 'article', 'other'))
);

CREATE INDEX idx_history_vin ON VehicleHistory (VIN, RecordDate);
