-- SPDX-License-Identifier: AGPL-3.0-or-later
-- What Mitsubishi's own catalogues say the factory codes mean, kept per source build (CAPS 2004, ASA Japan 2008)
-- and language, as the catalogues hold them; loaded by one-off host jobs.
--   ClassificationLabel: a model code's grade (classification) code, e.g. Z16A MJGF = GTO TWIN-TURBO,6FM/T.
--   OptionContent: what a car's option (equipment) code fits, per model, classification and model year: a
--     comma-separated list of option item codes.
--   OptionItem: an option item's text, e.g. J50 = CD AUTO CHANGER.
CREATE TABLE ClassificationLabel (
	Source VARCHAR(30) NOT NULL,
	ModelCode VARCHAR(7) NOT NULL,
	Classification VARCHAR(9) NOT NULL,
	Language CHAR(2) NOT NULL,
	Description VARCHAR(200) NOT NULL,
	Destination VARCHAR(12) NOT NULL DEFAULT '',
	PRIMARY KEY (Source, ModelCode, Classification, Language)
);

CREATE TABLE OptionContent (
	Source VARCHAR(30) NOT NULL,
	ModelCode VARCHAR(7) NOT NULL,
	OptionCode VARCHAR(4) NOT NULL,
	Classification VARCHAR(9) NOT NULL,
	ModelYear CHAR(2) NOT NULL,
	StartDate CHAR(7) NOT NULL,
	EndDate CHAR(7) NOT NULL,
	Items VARCHAR(255) NOT NULL,
	PRIMARY KEY (Source, ModelCode, OptionCode, Classification, ModelYear, StartDate)
);

CREATE TABLE OptionItem (
	Source VARCHAR(30) NOT NULL,
	ItemCode VARCHAR(4) NOT NULL,
	Language CHAR(2) NOT NULL,
	Description VARCHAR(200) NOT NULL,
	PRIMARY KEY (Source, ItemCode, Language)
);

CREATE INDEX idx_production_colours ON Production (Exterior, Interior, ModelYear);
CREATE INDEX idx_production_interior ON Production (Interior)
