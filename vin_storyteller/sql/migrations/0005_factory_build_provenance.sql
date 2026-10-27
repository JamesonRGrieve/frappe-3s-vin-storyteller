-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Name each factory record by the Mitsubishi catalogue build it came from (operator 2026-10-27), so the builds
-- can be told apart: the original export is Michael Reid's NA9199, taken from CAPS PASEN/SHARYO dated
-- 1999-09-16 (all 236,589 rows identical). Cars from the 2004 CAPS build are 'CAPS 2004'; JDM GTOs from the ASA
-- Japan EPC are 'ASA Japan 2008'. Every write names its Provenance; the column default is not relied on.
UPDATE Production SET Provenance = 'CAPS 1999' WHERE Provenance = 'CAPS'
