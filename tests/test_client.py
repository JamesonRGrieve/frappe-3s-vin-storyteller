# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from vin_storyteller.client import UNKNOWN, client_address


class TestClientAddress:
	def test_prefers_cloudflares_connecting_ip(self):
		assert client_address("203.0.113.7", "192.168.6.1") == "203.0.113.7"

	def test_strips_whitespace(self):
		assert client_address(" 203.0.113.7 ", None) == "203.0.113.7"

	def test_canonicalizes_ipv6(self):
		assert client_address("2001:DB8:0:0::1", None) == "2001:db8::1"

	def test_falls_back_to_request_ip_without_cloudflare(self):
		assert client_address(None, "192.168.6.10") == "192.168.6.10"

	@pytest.mark.parametrize("forged", ["", "evil", "203.0.113.7, 198.51.100.2", "203.0.113.7:443", "1.2.3"])
	def test_ignores_a_header_that_is_not_exactly_one_address(self, forged):
		assert client_address(forged, "192.168.6.10") == "192.168.6.10"

	def test_unknown_when_neither_is_an_address(self):
		assert client_address(None, None) == UNKNOWN
