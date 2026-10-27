-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Export-market 3000GTs from Mitsubishi's ASA General EPC (card 331): Z16A twin-turbo cars, keyed by their
-- 17-character VIN (JMA/JMY) or 14-character frame number, split by drive side as the catalogue grades them
-- (grade letter 5: L = left-hand drive, R = right-hand drive). Provenance 'ASA General 2008'.
INSERT INTO Model (ModelCode, Manufacturer, Model, Trim) VALUES ('EL', 'Mitsubishi', '3000GT', 'Twin Turbo (LHD)');
INSERT INTO Model (ModelCode, Manufacturer, Model, Trim) VALUES ('ER', 'Mitsubishi', '3000GT', 'Twin Turbo (RHD)')
