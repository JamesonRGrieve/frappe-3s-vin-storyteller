-- SPDX-License-Identifier: AGPL-3.0-or-later
-- The Japanese-market Mitsubishi GTO's two chassis families (Mitsubishi service campaign SC059), so a GTO can be
-- on record in Production by its chassis number (Z15A-/Z16A- and seven digits, in the VIN column) with its own
-- Provenance. Trim stays empty: the chassis family alone doesn't establish it.
INSERT INTO Model (ModelCode, Manufacturer, Model, Trim) VALUES ('G5', 'Mitsubishi', 'GTO', '');
INSERT INTO Model (ModelCode, Manufacturer, Model, Trim) VALUES ('G6', 'Mitsubishi', 'GTO', '')
