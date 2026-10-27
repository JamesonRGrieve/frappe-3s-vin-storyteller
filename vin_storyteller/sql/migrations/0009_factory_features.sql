-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Equipment a car had from the factory that its option code doesn't name, read from Mitsubishi's parts catalogues:
-- a feature's parts apply to a model code's grade (classification) built within a date window, sometimes only with
-- an option item (card 331; e.g. the export 3000GT's headlamp washers, catalogue B808K409A). Loaded by host jobs.
CREATE TABLE FactoryFeature (
	Source VARCHAR(30) NOT NULL,
	ModelCode VARCHAR(7) NOT NULL,
	Classification VARCHAR(9) NOT NULL,
	StartDate CHAR(7) NOT NULL,
	EndDate CHAR(7) NOT NULL,
	OptionItem VARCHAR(4) NOT NULL DEFAULT '',
	Feature VARCHAR(100) NOT NULL,
	PRIMARY KEY (Source, ModelCode, Classification, StartDate, OptionItem, Feature)
)
