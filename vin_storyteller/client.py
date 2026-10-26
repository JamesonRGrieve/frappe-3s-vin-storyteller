# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who is asking: the client address the lookup limit is counted against. No Frappe import.

Frappe's own `request_ip` is the left-most X-Forwarded-For entry, which a visitor can set to anything (a
proxy appends to it rather than replacing it), and behind a reverse proxy that rewrites X-Forwarded-For it is
the proxy's address for every visitor. Cloudflare's `CF-Connecting-IP` is set by Cloudflare itself to the
address that connected to it, replacing any value the visitor sent, so it is preferred when present.
"""

from __future__ import annotations

import ipaddress

UNKNOWN = "unknown"


def _address(value: str | None) -> str | None:
	"""`value` as a canonical IP address, or None when it isn't exactly one address."""
	try:
		return str(ipaddress.ip_address((value or "").strip()))
	except ValueError:
		return None


def client_address(cf_connecting_ip: str | None, request_ip: str | None) -> str:
	"""The address to count a lookup against: Cloudflare's view of the client, else Frappe's request IP."""
	return _address(cf_connecting_ip) or _address(request_ip) or UNKNOWN
