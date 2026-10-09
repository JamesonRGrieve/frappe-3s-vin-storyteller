-- SPDX-License-Identifier: AGPL-3.0-or-later
-- The CAPS dump has only primary keys; every storyteller lookup filters Production by VIN, model year,
-- model line or build date. Data is untouched.
CREATE INDEX idx_production_vin ON Production (VIN);
CREATE INDEX idx_production_year_serial ON Production (ModelYear, SerialNumber);
CREATE INDEX idx_production_line ON Production (ModelYear, Model, ModelCode, SerialNumber);
CREATE INDEX idx_production_spec ON Production (ModelYear, Model, ModelCode, Interior, Exterior, Equipment, SerialNumber);
CREATE INDEX idx_production_built ON Production (DateOfManufacture);
