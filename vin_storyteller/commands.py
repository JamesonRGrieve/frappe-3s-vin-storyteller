# SPDX-License-Identifier: AGPL-3.0-or-later
"""`bench --site <site> vin-storyteller-migrate`: apply pending schema migrations to the production record.

Host, port and database come from the site config (as the API uses them). The schema changes need a user
that may ALTER and CREATE, which the read-only API user must not be, so those credentials come only from
the environment: VIN_STORYTELLER_DB_ADMIN_USER and VIN_STORYTELLER_DB_ADMIN_PASSWORD.
"""

import os
from contextlib import closing

import click
from frappe.commands import get_site, pass_context

CONNECT_TIMEOUT_S = 10


@click.command("vin-storyteller-migrate")
@pass_context
def migrate_production_record(context):
	"""Apply pending VIN Storyteller schema migrations."""
	import frappe
	import pymysql

	from vin_storyteller.migrations import MissingCredentials, admin_credentials, migrate

	try:
		user, password = admin_credentials(os.environ)
	except MissingCredentials as error:
		raise click.UsageError(str(error)) from error
	frappe.init(site=get_site(context))
	try:
		conf = frappe.conf
		connection = pymysql.connect(
			host=conf.get("vin_storyteller_db_host", "localhost"),
			port=int(conf.get("vin_storyteller_db_port", 3306)),
			user=user,
			password=password,
			database=conf.get("vin_storyteller_db_name", "3s_production"),
			charset="utf8mb4",
			connect_timeout=CONNECT_TIMEOUT_S,
		)
		with closing(connection):
			ran = migrate(connection, "mariadb")
	finally:
		frappe.destroy()
	click.echo(f"applied: {', '.join(ran)}" if ran else "up to date")


commands = [migrate_production_record]
