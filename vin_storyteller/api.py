# SPDX-License-Identifier: AGPL-3.0-or-later
"""The storyteller's one public endpoint: GET /api/method/vin_storyteller.api.tell?vin=…

Guests may call it, LOOKUPS_PER_WINDOW times an hour per client (client.client_address: Cloudflare's
CF-Connecting-IP, since Frappe's request_ip is forgeable and, behind the reverse proxy, shared by every
visitor). Only well-formed VINs count: a typo never reaches the database and never uses up a lookup. No VIN or
visitor is stored beyond the counter's expiring cache key. The answer itself is built by answer.answer
(Frappe-free and unit-tested); this module only wires in Frappe, the cache and PyMySQL.
"""

from contextlib import closing, contextmanager

import frappe
import pymysql

from vin_storyteller.answer import UNAVAILABLE, RecordsUnavailable, answer
from vin_storyteller.client import client_address
from vin_storyteller.repository import ProductionRecords
from vin_storyteller.story import InvalidVin, normalize_vin

LOOKUPS_PER_WINDOW = 3
WINDOW_S = 60 * 60
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 15
DEFAULT_DB = "3s_production"
DEFAULT_PORT = 3306


@contextmanager
def _records():
	"""A read-only session on the production record, configured in site_config.json."""
	conf = frappe.conf
	connection = pymysql.connect(
		host=conf.get("vin_storyteller_db_host", "localhost"),
		port=int(conf.get("vin_storyteller_db_port", DEFAULT_PORT)),
		user=conf.get("vin_storyteller_db_user"),
		password=conf.get("vin_storyteller_db_password"),
		database=conf.get("vin_storyteller_db_name", DEFAULT_DB),
		charset="utf8mb4",
		connect_timeout=CONNECT_TIMEOUT_S,
		read_timeout=READ_TIMEOUT_S,
		init_command="SET SESSION TRANSACTION READ ONLY",
	)
	with closing(connection):
		yield ProductionRecords(connection)


LIMITED = f"You've used your {LOOKUPS_PER_WINDOW} lookups for this hour. Please try again later."


def _count_lookup() -> None:
	"""Count one lookup against the client; past the limit, answer 429 (RateLimitExceededError)."""
	client = client_address(frappe.get_request_header("CF-Connecting-IP"), frappe.local.request_ip)
	key = frappe.cache.make_key(f"vin_storyteller:lookups:{client}")
	if not frappe.cache.get(key):
		frappe.cache.setex(key, WINDOW_S, 0)
	if frappe.cache.incrby(key, 1) > LOOKUPS_PER_WINDOW:
		frappe.throw(LIMITED, frappe.RateLimitExceededError)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def tell(vin: str = "") -> dict:
	try:
		normalize_vin(vin)
	except InvalidVin:
		pass  # answered as invalid below, without touching the database or the client's lookups
	else:
		_count_lookup()
	try:
		return answer(vin, _records, (pymysql.MySQLError,))
	except RecordsUnavailable:
		frappe.log_error(title="VIN Storyteller: production record unavailable")
		return {"status": "error", "message": UNAVAILABLE}
