# SPDX-License-Identifier: AGPL-3.0-or-later
"""The storyteller's public endpoints: GET /api/method/vin_storyteller.api.tell?vin=… (a VIN's story), and the
per-code pages' code?kind=…&code=…[&model=…] and codes?kind=… (card 330), and the stats page's stats.

Guests may call it, LOOKUPS_PER_WINDOW times an hour per client (client.client_address: Cloudflare's
CF-Connecting-IP, since Frappe's request_ip is forgeable and, behind the reverse proxy, shared by every
visitor). The visitor gives their name, and every counted lookup is logged to StoriesTold (VIN, name, hour, time)
as the original storyteller did, so uses can be audited. Only a well-formed VIN with a name counts: a typo never
reaches the database or uses up a lookup. The answer itself is built by answer.answer (Frappe-free and
unit-tested); this module only wires in Frappe, the cache and PyMySQL.

The code pages are production statistics, the same for every visitor and changed only when the record is reloaded:
they are never logged to StoriesTold, their answers are cached for CODE_CACHE_S, and a client may ask for
CODE_PAGES_PER_WINDOW of them an hour (counted apart from VIN lookups).
"""

import urllib.parse
from contextlib import closing, contextmanager

import frappe
import pymysql
from werkzeug.wrappers import Response

from vin_storyteller.answer import (
	UNAVAILABLE,
	RecordsUnavailable,
	answer,
	code_answer,
	index_answer,
	page_key,
	search_answer,
	search_csv,
	share_story,
	stats_answer,
)
from vin_storyteller.client import client_address
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.search import InvalidSearch, parse_query
from vin_storyteller.share import interior_look, preview_html, render_card, swatch_hints
from vin_storyteller.story import (
	CODE_KINDS,
	CODE_PAGE_ROUTES,
	InvalidName,
	InvalidVin,
	code_page_endpoints,
	is_chassis_number,
	is_frame_number,
	normalize_chassis,
	normalize_frame,
	normalize_name,
	normalize_vin,
)

LOOKUPS_PER_WINDOW = 3
CODE_PAGES_PER_WINDOW = 120
WINDOW_S = 60 * 60
CODE_CACHE_S = 60 * 60
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 15
DEFAULT_DB = "3s_production"
DEFAULT_PORT = 3306


def _connect(**extra):
	conf = frappe.conf
	return pymysql.connect(
		host=conf.get("vin_storyteller_db_host", "localhost"),
		port=int(conf.get("vin_storyteller_db_port", DEFAULT_PORT)),
		user=conf.get("vin_storyteller_db_user"),
		password=conf.get("vin_storyteller_db_password"),
		database=conf.get("vin_storyteller_db_name", DEFAULT_DB),
		charset="utf8mb4",
		connect_timeout=CONNECT_TIMEOUT_S,
		read_timeout=READ_TIMEOUT_S,
		**extra,
	)


@contextmanager
def _records():
	"""A read-only session on the production record, configured in site_config.json."""
	with closing(_connect(init_command="SET SESSION TRANSACTION READ ONLY")) as connection:
		yield ProductionRecords(connection)


def _record_story(vin: str, name: str) -> None:
	"""Log the story told; a failure is logged and never costs the visitor their story."""
	try:
		with closing(_connect()) as connection:
			ProductionRecords(connection).record_story(vin, name, frappe.utils.now_datetime())
	except pymysql.MySQLError:
		frappe.log_error(title="VIN Storyteller: could not log a story told")


LIMITED = f"You've used your {LOOKUPS_PER_WINDOW} lookups for this hour. Please try again later."


CODE_PAGES_LIMITED = f"You've opened {CODE_PAGES_PER_WINDOW} code pages this hour. Please try again later."


def _count_lookup(counter: str = "lookups", limit: int = LOOKUPS_PER_WINDOW, message: str = LIMITED) -> None:
	"""Count one request against the client; past the limit, answer 429 (RateLimitExceededError)."""
	client = client_address(frappe.get_request_header("CF-Connecting-IP"), frappe.local.request_ip)
	key = frappe.cache.make_key(f"vin_storyteller:{counter}:{client}")
	if not frappe.cache.get(key):
		frappe.cache.setex(key, WINDOW_S, 0)
	if frappe.cache.incrby(key, 1) > limit:
		frappe.throw(message, frappe.RateLimitExceededError)


NAME_REQUIRED = "Please enter your name. Every story told is logged with the name given."


@frappe.whitelist(allow_guest=True, methods=["GET"])
def tell(vin: str = "", name: str = "") -> dict:
	try:
		normalized = (
			normalize_chassis(vin)
			if is_chassis_number(vin)
			else normalize_frame(vin)
			if is_frame_number(vin)
			else normalize_vin(vin)
		)
	except InvalidVin:
		normalized = None  # answered as invalid below, without touching the database or the client's lookups
	if normalized:
		try:
			visitor = normalize_name(name)
		except InvalidName:
			return {"status": "invalid", "message": NAME_REQUIRED}
		_count_lookup()
		_record_story(normalized, visitor)
	try:
		return answer(vin, _records, (pymysql.MySQLError,))
	except RecordsUnavailable:
		frappe.log_error(title="VIN Storyteller: production record unavailable")
		return {"status": "error", "message": UNAVAILABLE}


def _cached(key: str | None, build) -> dict:
	"""A code page or index answer, from the cache when it holds one; errors and invalid requests are never cached."""
	cache_key = f"vin_storyteller:page:{key}" if key else None  # get_value/set_value add the site prefix
	if cache_key and (hit := frappe.cache.get_value(cache_key)):
		return hit
	try:
		body = build()
	except RecordsUnavailable:
		frappe.log_error(title="VIN Storyteller: production record unavailable")
		return {"status": "error", "message": UNAVAILABLE}
	if cache_key and body["status"] in ("found", "not_found"):
		frappe.cache.set_value(cache_key, body, expires_in_sec=CODE_CACHE_S)
	return body


@frappe.whitelist(allow_guest=True, methods=["GET"])
def code(kind: str = "", code: str = "", model: str = "") -> dict:
	"""A paint, interior or option code's page: its production stats from the factory records."""
	_count_lookup("code_pages", CODE_PAGES_PER_WINDOW, CODE_PAGES_LIMITED)
	return _cached(
		page_key(kind, code, model), lambda: code_answer(kind, code, model, _records, (pymysql.MySQLError,))
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def codes(kind: str = "") -> dict:
	"""Every paint, interior or option code in the factory records, with its total and models."""
	_count_lookup("code_pages", CODE_PAGES_PER_WINDOW, CODE_PAGES_LIMITED)
	key = f"index:{kind}" if kind in CODE_KINDS else None
	return _cached(key, lambda: index_answer(kind, _records, (pymysql.MySQLError,)))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def stats() -> dict:
	"""The production statistics page's data: every factory-record car, counted by model year, model, region,
	paint, interior, model line, transmission, build month, colour pair and exact-spec rarity."""
	_count_lookup("code_pages", CODE_PAGES_PER_WINDOW, CODE_PAGES_LIMITED)
	return _cached("stats", lambda: stats_answer(_records, (pymysql.MySQLError,)))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def search(**params) -> dict:
	"""Car search for the stats page: q (VIN fragment or code), model, market, region, from, to, paint, interior,
	option, page. Full VINs (operator, 2026-11-12). Counted with the code pages; answers cached for CODE_CACHE_S."""
	_count_lookup("code_pages", CODE_PAGES_PER_WINDOW, CODE_PAGES_LIMITED)
	params = {k: v for k, v in params.items() if k != "cmd"}
	try:
		key = f"search:{parse_query(params).key()}"
	except InvalidSearch:
		key = None
	return _cached(key, lambda: search_answer(params, _records, (pymysql.MySQLError,)))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def search_export(**params):
	"""The same search as `search`, every matching car (up to the scan limit) as a CSV download. Counted with the
	code pages; not cached (a download is a one-off)."""
	_count_lookup("code_pages", CODE_PAGES_PER_WINDOW, CODE_PAGES_LIMITED)
	params = {k: v for k, v in params.items() if k != "cmd"}
	try:
		result = search_csv(params, _records, (pymysql.MySQLError,))
	except RecordsUnavailable:
		frappe.log_error(title="VIN Storyteller: production record unavailable")
		return {"status": "error", "message": UNAVAILABLE}
	if isinstance(result, dict):
		return result
	filename, text = result
	frappe.response["type"] = "download"
	frappe.response["filename"] = filename
	frappe.response["filecontent"] = text.encode("utf-8")
	frappe.response["content_type"] = "text/csv; charset=utf-8"


SHARES_PER_WINDOW = 600  # link-preview crawlers fetch from few addresses; the card is cached per key
SHARE_CACHE_S = 60 * 60


def _share_inputs(vin: str):
	"""The story a share link shows, its swatch hints and its interior's look, or None (not a key on record)."""
	import json

	story = share_story(vin, _records, (pymysql.MySQLError,))
	if story is None:
		return None
	path = frappe.get_app_path("vin_storyteller", "public", "data", "swatches.json")
	with open(path, encoding="utf-8") as handle:
		swatches = json.load(handle)
	return story, swatch_hints(swatches, story), interior_look(swatches, story)


def _share_urls(key: str) -> tuple[str, str]:
	base = frappe.utils.get_url()
	quoted = urllib.parse.quote(key)
	return (
		f"{base}/storyteller?vin={quoted}",
		f"{base}/api/method/vin_storyteller.api.share_image?vin={quoted}",
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def share(vin: str = ""):
	"""A story's share link (card 391): link-preview tags for Facebook, Messenger and forums, then on to the story.
	Never logged and never a lookup: it shows only the story's headline."""
	_count_lookup("shares", SHARES_PER_WINDOW, CODE_PAGES_LIMITED)
	try:
		found = _share_inputs(vin)
	except RecordsUnavailable:
		frappe.log_error(title="VIN Storyteller: production record unavailable")
		return Response(UNAVAILABLE, status=503, mimetype="text/plain")
	if found is None:
		return Response("That isn't a VIN on record.", status=404, mimetype="text/plain")
	story, (_paint, hint), _interior = found
	page, image = _share_urls(story.vin)
	return Response(preview_html(story, page, image, hint), mimetype="text/html")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def share_image(vin: str = ""):
	"""A story's share card, 1200x630 PNG, cached per key for SHARE_CACHE_S."""
	_count_lookup("shares", SHARES_PER_WINDOW, CODE_PAGES_LIMITED)
	key = f"vin_storyteller:share:{''.join((vin or '').split()).upper()[:20]}"
	png = frappe.cache.get_value(key)
	if not png:
		try:
			found = _share_inputs(vin)
		except RecordsUnavailable:
			frappe.log_error(title="VIN Storyteller: production record unavailable")
			return Response(UNAVAILABLE, status=503, mimetype="text/plain")
		if found is None:
			return Response("That isn't a VIN on record.", status=404, mimetype="text/plain")
		story, (paint, hint), interior = found
		png = render_card(story, paint, hint, interior)
		frappe.cache.set_value(key, png, expires_in_sec=SHARE_CACHE_S)
	response = Response(png, mimetype="image/png")
	response.headers["Cache-Control"] = f"public, max-age={SHARE_CACHE_S}"
	return response


def sitemap_routes(site) -> list[tuple[str, None]]:
	"""public_site_sitemap_routes hook (frappe-public-site-router): every code page on a site that publishes the
	dynamic code-page Web Pages. A database failure leaves the code pages out of the sitemap rather than breaking it."""
	routes = {kind: f"{site.route_prefix}/{route}" for kind, route in CODE_PAGE_ROUTES.items()}
	if not frappe.db.exists("Web Page", {"route": routes["paint"], "published": 1, "dynamic_route": 1}):
		return []
	try:
		with _records() as records:
			index = {kind: records.code_index(kind) for kind in CODE_KINDS}
	except pymysql.MySQLError:
		frappe.log_error(title="VIN Storyteller: code pages left out of the sitemap")
		return []
	return [(endpoint, None) for endpoint in code_page_endpoints(site.route_prefix, index)]
