# SPDX-License-Identifier: AGPL-3.0-or-later
"""A story's share card and link preview (card 391), from the real migrated SQLite database (conftest.py)."""

import io
import sqlite3
from contextlib import contextmanager

import pytest
from PIL import Image

from vin_storyteller.answer import RecordsUnavailable, share_story
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.share import HEIGHT, WIDTH, card_text, preview_html, render_card, swatch_hints


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
	assert any(line.startswith("Paint: ") and story.exterior.code in line for line in text.lines)
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
