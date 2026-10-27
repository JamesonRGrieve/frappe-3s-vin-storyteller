-- SPDX-License-Identifier: AGPL-3.0-or-later
-- An option code's page (card 330) finds its cars by option code within a chassis model code; without this index
-- every option page scans Production (about 30 ms on the 175k-car record in SQLite, against under 1 ms with it). Data is untouched.
CREATE INDEX idx_production_equipment ON Production (Equipment, ModelCode)
