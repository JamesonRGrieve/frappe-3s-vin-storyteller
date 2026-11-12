-- SPDX-License-Identifier: AGPL-3.0-or-later
-- The Australian-delivered 3000GTs (VINs JMF..., Mitsubishi Australia): their own Model key and market, so they never
-- shift a North American, Japanese or export count. None is in a Mitsubishi factory record we hold or in the online
-- catalogues (card 388); the cars come from owner listings, each with its own Provenance.
INSERT INTO Model (ModelCode, Manufacturer, Model, Trim) VALUES ('AU', 'Mitsubishi', '3000GT', '')
