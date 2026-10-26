# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production-record maintenance from bench, with admin credentials from the environment only:

- `bench --site <site> vin-storyteller-migrate`: apply pending schema migrations;
- `bench --site <site> vin-storyteller-add-record <VIN> <PROVENANCE>`: add a car the CAPS export is missing, from
  another source (records.add_record), e.g. `vin-storyteller-add-record JB3AN74K1SY008527 "Price label"`.

Host, port and database come from the site config (as the API uses them). The schema changes need a user
that may ALTER and CREATE, which the read-only API user must not be, so those credentials come only from
the environment: VIN_STORYTELLER_DB_ADMIN_USER and VIN_STORYTELLER_DB_ADMIN_PASSWORD.
"""

import os
from contextlib import closing

import click
from frappe.commands import get_site, pass_context

CONNECT_TIMEOUT_S = 10


def _with_admin_connection(context, work):
	"""Run `work(connection)` on the production record as the admin user named in the environment."""
	import frappe
	import pymysql

	from vin_storyteller.migrations import MissingCredentials, admin_credentials

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
			return work(connection)
	finally:
		frappe.destroy()


@click.command("vin-storyteller-migrate")
@pass_context
def migrate_production_record(context):
	"""Apply pending VIN Storyteller schema migrations."""
	from vin_storyteller.migrations import migrate

	ran = _with_admin_connection(context, lambda connection: migrate(connection, "mariadb"))
	click.echo(f"applied: {', '.join(ran)}" if ran else "up to date")


@click.command("vin-storyteller-add-record")
@click.argument("vin")
@click.argument("provenance")
@pass_context
def add_production_record(context, vin, provenance):
	"""Add a car the CAPS export is missing, proven by another source named in PROVENANCE."""
	from vin_storyteller.records import RecordRefused, add_record
	from vin_storyteller.story import InvalidVin

	try:
		added = _with_admin_connection(context, lambda connection: add_record(connection, vin, provenance))
	except (RecordRefused, InvalidVin) as error:
		raise click.ClickException(f"refused: {error}") from error
	click.echo(
		f"added {added.vin} ({added.model_year}, line {added.model}/{added.model_code} from "
		f"{added.pattern_year} CAPS cars), provenance {added.provenance!r}"
	)


commands = [migrate_production_record, add_production_record]
