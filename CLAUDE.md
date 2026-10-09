# frappe-3s-vin-storyteller — Agent Operating Guide

The repo is `frappe-3s-vin-storyteller`; the Frappe app / Python package is `vin_storyteller` (app names
must be Python identifiers, and asset and API paths use it).

AGPL-3.0-or-later Frappe v16 app. Tells a 3000GT / Stealth's story from its VIN using the factory
production record, which lives in its own MariaDB database (not the Frappe site database).

## Layout

- `vin_storyteller/story.py`: pure logic, no Frappe import. VIN rules (17 chars, never I/O/Q), the
  'YYMMP' production-date wording, colour naming by manufacturer, the `Story` dataclass.
- `vin_storyteller/repository.py`: `ProductionRecords(connection, paramstyle)`. All SQL lives here, always
  parameterized, limited to what both MariaDB and SQLite run.
- `vin_storyteller/answer.py`: `answer(vin, open_records, database_errors)`, the whole API answer, no
  Frappe. Database failures surface as `RecordsUnavailable`.
- `vin_storyteller/api.py`: the only endpoint, `tell(vin)`, kept thin: guest, GET, rate-limited per IP;
  opens a read-only PyMySQL session from site-config keys `vin_storyteller_db_*` and calls `answer`; logs
  database failures, returns a generic message.
- `vin_storyteller/templates/includes/storyteller.html`, `public/js/storyteller-core.js` (pure helpers on
  `globalThis.VinStorytellerCore`, loaded first), `public/js/storyteller.js` (DOM only, text nodes, never
  innerHTML), `public/css/storyteller.css`: the page. The footer links the AGPL source on GitHub.
- `vin_storyteller/migrations.py` + `sql/migrations/NNNN_*.sql`: versioned schema migrations, applied in
  order and recorded in `SchemaMigration`; `{autoincrement}` is the only dialect token. Run by
  `commands.py` (`bench --site <site> vin-storyteller-migrate`) with write credentials from the environment
  only. Never edit an applied migration; add the next number.
- Schema: `Production` (one row per car; `Provenance` says where the record came from, `CAPS` for the
  factory export) and `VehicleHistory` (post-factory records per VIN: type, title, URL, date, source,
  provenance). History URLs are shown only when they are plain http(s) links (`story.safe_url`, re-checked
  in the JS).
- Rarity: `story.rarity_tier` maps a run's total to `one_of_one` (1) or `sub10`/`sub25`/`sub50`/`sub100`; a
  story is rated on its exact spec, its colour in its model line and year, and its model line. The rarest
  tier drives the page effect (`data-rarity` on the result); motion is off under prefers-reduced-motion.

## Rules

- Never store VINs or visitor data, and never write to the production record (read-only by design).
- The story must match the original storyteller's counts: positions use `SerialNumber <` within the same
  model year / model line / identical spec, plus one.
- The disclaimer text is the original's, verbatim.
- Serving: the page is a Web Page created by the deployment (see README). On public_site_router hosts it
  is routed `<prefix>/storyteller`; `www/` pages are not served on those hosts.

## Testing

No bench needed. Every change adds or extends tests; logic belongs in the tested modules, never in
`api.py` / `commands.py`.

- `uv run --no-project --with pytest python -I -m pytest`: `story` (pure), `repository` and `answer`
  against a real in-memory SQLite database shaped like the CAPS dump (`tests/conftest.py`), and the real
  migrations (`caps_connection` = dump as loaded; `connection` = migrated + history rows). No mocks.
- `node --test 'tests/js/*.test.mjs'`: the front-end helpers, loaded into a `vm` context.
- `uvx ruff format --check . && uvx ruff check .`
