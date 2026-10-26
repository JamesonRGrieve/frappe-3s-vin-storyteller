# SPDX-License-Identifier: AGPL-3.0-or-later
from dataclasses import replace

import pytest

from vin_storyteller.story import (
	MISSING,
	Coded,
	HistoryRecord,
	InvalidVin,
	Position,
	Story,
	describe_production_date,
	exterior_description,
	full_year,
	normalize_vin,
	rarity_tier,
	safe_url,
)


class TestNormalizeVin:
	def test_upper_cases_and_strips_whitespace(self):
		assert normalize_vin("  ja3am84j3ny012345 \n") == "JA3AM84J3NY012345"

	def test_removes_inner_spaces(self):
		assert normalize_vin("JA3AM84J3 NY012345") == "JA3AM84J3NY012345"

	@pytest.mark.parametrize("bad", ["", "JA3AM84J3NY01234", "JA3AM84J3NY0123456", "JA3AM84J3NY01234-"])
	def test_rejects_wrong_length_or_characters(self, bad):
		with pytest.raises(InvalidVin):
			normalize_vin(bad)

	@pytest.mark.parametrize("letter", ["I", "O", "Q"])
	def test_rejects_letters_vins_never_use(self, letter):
		with pytest.raises(InvalidVin):
			normalize_vin(f"JA3AM84J3NY01234{letter}")

	def test_none_is_invalid(self):
		with pytest.raises(InvalidVin):
			normalize_vin(None)


class TestProductionDate:
	@pytest.mark.parametrize(
		("code", "text"),
		[
			("92031", "the 1st production period of March, 1992"),
			("92032", "the 2nd production period of March, 1992"),
			("91123", "the 3rd production period of December, 1991"),
		],
	)
	def test_periods(self, code, text):
		assert describe_production_date(code) == text

	def test_unknown_period(self):
		assert describe_production_date("95064") == "the Unknown production period of June, 1995"

	def test_unknown_month(self):
		assert describe_production_date("95131") == "the 1st production period of an unknown month, 1995"

	def test_full_year(self):
		assert full_year("97") == "1997"


class TestExteriorDescription:
	def test_mitsubishi_name_for_mitsubishi(self):
		assert exterior_description("Mitsubishi", "Fiji Blue", "Bright Blue") == "Fiji Blue"

	def test_dodge_name_for_dodge(self):
		assert exterior_description("Dodge", "Fiji Blue", "Bright Blue") == "Bright Blue"

	def test_missing_when_own_name_unknown(self):
		assert exterior_description("Dodge", "Fiji Blue", MISSING) == MISSING
		assert exterior_description("Mitsubishi", MISSING, "Bright Blue") == MISSING

	def test_missing_for_unknown_manufacturer(self):
		assert exterior_description(MISSING, "Fiji Blue", "Bright Blue") == MISSING


class TestSafeUrl:
	@pytest.mark.parametrize("url", ["https://bringatrailer.com/listing/x", "http://example.com/a?b=c"])
	def test_keeps_http_links(self, url):
		assert safe_url(url) == url

	@pytest.mark.parametrize(
		"url",
		[
			None,
			"",
			"javascript:alert(1)",
			"data:text/html,x",
			"ftp://x",
			"https://a b",
			'https://x"onclick=y',
		],
	)
	def test_drops_everything_else(self, url):
		assert safe_url(url) is None


class TestRarityTier:
	@pytest.mark.parametrize(
		("total", "tier"),
		[
			(1, "one_of_one"),
			(2, "sub10"),
			(9, "sub10"),
			(10, "sub25"),
			(24, "sub25"),
			(25, "sub50"),
			(49, "sub50"),
			(50, "sub100"),
			(99, "sub100"),
			(100, None),
			(0, None),
		],
	)
	def test_tiers(self, total, tier):
		assert rarity_tier(total) == tier


def make_story(**overrides) -> Story:
	base = Story(
		vin="JA3AM84J3NY012345",
		provenance="CAPS",
		history=(
			HistoryRecord(
				"auction", "Sold on BaT", "https://bringatrailer.com/x", "2021-05-01", "BaT", "operator"
			),
		),
		model_year="1992",
		manufacturer="Mitsubishi",
		model="3000GT",
		trim="VR-4",
		exterior=Coded("T87", "Fiji Blue"),
		interior=Coded("12A", "Grey"),
		equipment=Coded("XA1", "Leather"),
		built="the 2nd production period of March, 1992",
		built_in_period=10,
		built_in_month=30,
		year_started="the 1st production period of September, 1991",
		model_started="the 2nd production period of September, 1991",
		in_year=Position(5, 1000),
		in_model=Position(2, 400),
		in_colour=Position(3, 150),
		among_identical=Position(1, 120),
	)
	return replace(base, **overrides)


def test_vehicle_name_and_dict():
	data = make_story().as_dict()
	assert data["vehicle_name"] == "1992 Mitsubishi 3000GT VR-4"
	assert data["in_year"] == {"position": 5, "total": 1000}
	assert data["exterior"] == {"code": "T87", "description": "Fiji Blue"}
	assert data["provenance"] == "CAPS"
	assert data["history"][0]["kind"] == "auction"
	assert data["rarities"] == [] and data["rarest"] is None


def test_vehicle_name_skips_empty_trim():
	assert make_story(manufacturer="Dodge", model="Stealth", trim="").vehicle_name == "1992 Dodge Stealth"


def test_one_of_one_is_rarest():
	story = make_story(among_identical=Position(1, 1), in_colour=Position(1, 30))
	assert [(r.scope, r.tier) for r in story.rarities] == [("spec", "one_of_one"), ("colour", "sub50")]
	data = story.as_dict()
	assert data["rarest"] == "one_of_one"
	assert data["rarities"][0]["description"].startswith("in this exact specification")


def test_rarities_sorted_by_tier_then_total():
	story = make_story(among_identical=Position(1, 40), in_colour=Position(1, 12), in_model=Position(1, 8))
	assert [r.scope for r in story.rarities] == ["model", "colour", "spec"]


class TestNormalizeName:
	def test_collapses_whitespace(self):
		from vin_storyteller.story import normalize_name

		assert normalize_name("  Trevor   Macken \n") == "Trevor Macken"

	@pytest.mark.parametrize("bad", ["", "   ", None, "x" * 101])
	def test_rejects_blank_or_too_long(self, bad):
		from vin_storyteller.story import InvalidName, normalize_name

		with pytest.raises(InvalidName):
			normalize_name(bad)
