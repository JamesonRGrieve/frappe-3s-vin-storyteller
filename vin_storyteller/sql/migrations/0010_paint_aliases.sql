-- SPDX-License-Identifier: AGPL-3.0-or-later
-- Paint codes that name the same paint: CAPS writes some early paints in an "A" form (RA8, WA5, TA7 ...) where
-- Mitsubishi's ASA USA gives the very same cars the plain paint code (R38, W75, T87 ...; 100% agreement over every
-- shared car). Colour breakdowns and paint pages count a paint under all its codes; positions stay exact.
CREATE TABLE PaintAlias (
	Code CHAR(3) PRIMARY KEY,
	PaintCode CHAR(3) NOT NULL,
	Source VARCHAR(30) NOT NULL
)
