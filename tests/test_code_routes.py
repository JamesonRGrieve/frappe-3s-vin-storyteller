# SPDX-License-Identifier: AGPL-3.0-or-later
"""The code pages' sitemap routes (card 330): every code under the site prefix, behind the dynamic Web Pages."""

from vin_storyteller.story import CODE_PAGE_ROUTES, CodeIndexEntry, code_page_endpoint, code_page_endpoints


def entry(code, model_code=""):
	return CodeIndexEntry(code=code, model_code=model_code, description="", total=1, by_model=())


def test_code_page_endpoints():
	index = {
		"paint": (entry("T87"),),
		"interior": (entry("12A"),),
		"option": (entry("302", "Z16A"), entry("000")),
	}
	assert code_page_endpoints("3shub-ca", index) == [
		"3shub-ca/storyteller/paint/T87",
		"3shub-ca/storyteller/interior/12A",
		"3shub-ca/storyteller/option/Z16A/302",
	]


def test_endpoints_match_the_dynamic_routes():
	assert code_page_endpoint("p", "option", "302", "Z16A") == "p/" + CODE_PAGE_ROUTES["option"].replace(
		"<model>", "Z16A"
	).replace("<code>", "302")
	assert code_page_endpoint("p", "paint", "T87") == "p/" + CODE_PAGE_ROUTES["paint"].replace(
		"<code>", "T87"
	)
