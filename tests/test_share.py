# SPDX-License-Identifier: AGPL-3.0-or-later
"""A story's share card and link preview (card 391), from the real migrated SQLite database (conftest.py)."""

import io
import sqlite3
from contextlib import contextmanager

import pytest
from PIL import Image

from vin_storyteller.answer import RecordsUnavailable, share_story
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.share import (
	HEIGHT,
	WIDTH,
	card_text,
	interior_look,
	preview_html,
	render_card,
	swatch_hints,
)
from vin_storyteller.swatches import INTERIOR_TONES


@pytest.fixture
def records(connection):
	return ProductionRecords(connection, "qmark")


def session_of(records):
	@contextmanager
	def session():
		yield records

	return session


def test_a_share_finds_any_key_the_storyteller_takes_and_nothing_else(records):
	story = share_story(" ja3am84j3ny000001 ", session_of(records), (sqlite3.Error,))
	assert story.vin == "JA3AM84J3NY000001"
	assert share_story("not a vin", session_of(records), (sqlite3.Error,)) is None
	assert share_story("JA3AM84J3NY999999", session_of(records), (sqlite3.Error,)) is None

	@contextmanager
	def broken():
		raise sqlite3.OperationalError("down")
		yield

	with pytest.raises(RecordsUnavailable):
		share_story("JA3AM84J3NY000001", broken, (sqlite3.Error,))


def test_the_card_says_what_the_storys_headline_says(records):
	story = records.story("JA3AM84J3NY000001")
	text = card_text(story)
	assert text.title == story.vehicle_name
	assert text.paint.endswith(f"\u00b7 {story.exterior.code}") and text.interior.endswith(
		story.interior.code
	)
	assert "Paint: " in text.description and text.built.startswith("Built ")
	assert (
		text.position
		== f"No. {story.in_year.position:,} of {story.in_year.total:,} built for {story.model_year}"
	)
	assert text.description and text.title not in text.description


def test_swatch_hints_give_the_paint_colour_and_an_unnamed_interiors_colour_and_material(records):
	story = records.story("JA3AM84J3NY000001")
	swatches = {
		"paint": {story.exterior.code: {"same_paint_as": "P1"}, "P1": {"hex": "#112233"}},
		"interior": {story.interior.code: {"colour": "Red", "material": "leather"}},
	}
	assert swatch_hints(swatches, story) == ("#112233", "Red leather")
	assert swatch_hints({}, story) == (None, "")


def test_the_card_is_a_1200_by_630_png(records):
	png = render_card(records.story("JA3AM84J3NY000001"), "#4F8EBF", "red leather")
	image = Image.open(io.BytesIO(png))
	assert image.format == "PNG" and image.size == (WIDTH, HEIGHT)
	assert render_card(records.story("JA3AM84J3NY000001"), None)  # no colour on file: a neutral panel


def test_the_preview_page_escapes_everything_and_sends_people_to_the_story(records):
	story = records.story("JA3AM84J3NY000001")
	html = preview_html(
		story, 'https://3shub.ca/storyteller?vin=X"><script>', "https://3shub.ca/i.png?a=1&b=2", "<b>"
	)
	assert "<script>" not in html and "<b>" not in html
	assert 'og:image" content="https://3shub.ca/i.png?a=1&amp;b=2"' in html
	assert 'twitter:card" content="summary_large_image"' in html
	assert 'http-equiv="refresh"' in html and "&quot;&gt;&lt;script&gt;" in html


def test_the_interior_tile_is_resolved_as_the_animated_swatch_resolves_it(records):
	story = records.story("JA3AM84J3NY000001")
	code = story.interior.code
	tones = [list(t) for t in INTERIOR_TONES]
	sampled = {
		"interior_tones": tones,
		"interior": {code: {"sampled_hex": "#123456", "colour": "Red", "material": "cloth"}},
	}
	assert interior_look(sampled, story) == ("#123456", "cloth")  # a colour sampled from photos comes first
	named = {"interior_tones": tones, "interior": {code: {"colour": "Red", "material": "leather"}}}
	# A colour word in the record's own description outranks the table's colour (here the description names grey).
	assert story.interior.description == "Grey"
	assert interior_look(named, story)[0] == dict(INTERIOR_TONES)["grey"]
	unnamed = story.__class__(**{**story.__dict__, "interior": story.interior.__class__(code, "MISSING")})
	assert interior_look(named, unnamed) == (dict(INTERIOR_TONES)["red"], "leather")
	assert interior_look({"interior_tones": tones, "interior": {}}, unnamed) == (
		None,
		"unknown",
	)  # nothing on file
	png = render_card(story, "#4F8EBF", "Red leather", interior_look(named, story))
	assert Image.open(io.BytesIO(png)).size == (WIDTH, HEIGHT)


def test_swatches_json_carries_the_interior_tones():
	import json
	from pathlib import Path

	shipped = json.loads(
		(Path(__file__).parent.parent / "vin_storyteller/public/data/swatches.json").read_text()
	)
	assert shipped["interior_tones"] == [list(t) for t in INTERIOR_TONES]


def test_the_card_lists_the_factory_options_and_keeps_the_rarity_to_one_line(records):
	from dataclasses import replace

	from vin_storyteller.story import Coded

	story = records.story("JA3AM84J3NY000001")
	items = tuple(
		Coded(f"K{i:02}", name) for i, name in enumerate(["LEATHER SEAT & ROOM TRIM", "SUNROOF (B)", "ECS"])
	)
	full = replace(story, equipment_items=items, features=("Headlamp washers",))
	text = card_text(full)
	assert text.options == ("LEATHER SEAT & ROOM TRIM", "SUNROOF (B)", "ECS", "Headlamp washers")
	assert text.option == story.equipment.code and "Options: LEATHER SEAT" in text.description
	assert "(" not in text.rarity.split(": ", 1)[-1] if text.rarity else True  # the short scope on the card
	many = replace(
		story, equipment_items=tuple(Coded(f"X{i:02}", f"OPTION ITEM NUMBER {i}") for i in range(30))
	)
	png = render_card(many, "#4F8EBF", "Red leather", ("#7E1F24", "leather"))  # overflow: '+N more', no error
	assert Image.open(io.BytesIO(png)).size == (WIDTH, HEIGHT)


def test_the_card_gives_the_cars_place_in_its_paint_interior_both_and_exact_spec(records):
	story = records.story("JA3AM84J3NY000001")
	text = card_text(story)
	assert text.positions[-3:] == (
		f"{story.in_colour.position:,} of {story.in_colour.total:,} in this paint",
		f"{story.in_interior.position:,} of {story.in_interior.total:,} in this interior",
		f"{story.in_colours.position:,} of {story.in_colours.total:,} in this paint + interior",
	)
	spec = (
		f"{story.among_identical.position:,} of {story.among_identical.total:,} in this exact specification"
	)
	assert text.rarity.endswith(spec)
	# The runs nest: exact spec within paint + interior within each of paint and interior.
	assert (
		story.among_identical.total
		<= story.in_colours.total
		<= min(story.in_colour.total, story.in_interior.total)
	)
