# SPDX-License-Identifier: AGPL-3.0-or-later
from . import __version__ as _version

app_name = "vin_storyteller"
app_title = "VIN Storyteller"
app_publisher = "Zephyrex Technologies Limited"
app_description = (
	"The story of a Mitsubishi 3000GT or Dodge Stealth, told from its VIN and the factory production record"
)
app_email = "jameson@zephyrex.ca"
app_license = "AGPL-3.0-or-later"
app_version = _version

required_apps = ["frappe"]
