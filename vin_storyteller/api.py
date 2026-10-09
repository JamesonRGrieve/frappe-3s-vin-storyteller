# SPDX-License-Identifier: AGPL-3.0-or-later
"""The storyteller's one public endpoint: GET /api/method/vin_storyteller.api.tell?vin=…

Guests may call it; it is rate-limited per client IP. No VIN or visitor is ever stored. The answer itself
is built by answer.answer (Frappe-free and unit-tested); this module only wires in Frappe and PyMySQL.
"""

from contextlib import closing, contextmanager

import frappe
import pymysql
from frappe.rate_limiter import rate_limit

from vin_storyteller.answer import UNAVAILABLE, RecordsUnavailable, answer
from vin_storyteller.repository import ProductionRecords

LOOKUPS_PER_WINDOW = 30
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


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=LOOKUPS_PER_WINDOW, seconds=WINDOW_S)
def tell(vin: str = "") -> dict:
	try:
		return answer(vin, _records, (pymysql.MySQLError,))
	except RecordsUnavailable:
		frappe.log_error(title="VIN Storyteller: production record unavailable")
		return {"status": "error", "message": UNAVAILABLE}
