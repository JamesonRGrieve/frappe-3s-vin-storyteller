<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# frappe-3s-vin-storyteller

Tell the story of a Mitsubishi 3000GT or Dodge Stealth from its VIN, using the factory production record.
Built as a Frappe v16 app for [3S Hub](https://3shub.ca/), where it runs at https://3shub.ca/storyteller.

Enter a VIN and it tells you:

- the car's model year, make, model and trim, and its exterior colour, interior and equipment codes with
  what they mean;
- which production period it was built in (a period is about a third of a month);
- its number off the line for the model year, for its exact model, for its colour, and among identical cars;
- when production started for that model year and that model;
- how rare it is: a **one of one**, or one of **fewer than 10, 25, 50 or 100**, for its exact specification,
  its colour and its model run, shown with badges and a visual effect;
- where its production record came from (its *provenance*) and its later history on file: auctions,
  photos, sales, registrations, service records and articles, linked out.

Visitors give their name, and every story told is logged to `StoriesTold` (VIN, name, hour and time), as on the
original storyteller, so uses can be audited for errors. Each visitor gets 3 lookups an hour.

## Architecture

| Part | Role |
|---|---|
| `vin_storyteller/story.py` | Pure logic: VIN rules, production-date wording, colour naming, rarity tiers, link safety, the `Story` model. No Frappe or database. |
| `vin_storyteller/repository.py` | `ProductionRecords`: every SQL query, parameterized and read-only, written to run on MariaDB and SQLite. |
| `vin_storyteller/answer.py` | Builds the API answer for a VIN from a records session. No Frappe. |
| `vin_storyteller/api.py` | The Frappe endpoint: opens a read-only PyMySQL session and calls `answer`. Guest access, rate-limited. |
| `vin_storyteller/migrations.py`, `sql/migrations/` | Versioned schema migrations for the production-record database. |
| `vin_storyteller/commands.py` | `bench --site <site> vin-storyteller-migrate`. |
| `templates/includes/storyteller.html`, `public/js`, `public/css` | The page. `storyteller-core.js` holds the pure helpers; `storyteller.js` renders with text nodes only. |
| `public/js/swatch.js`, `swatch-core.js`, `public/css/swatch.css`, `public/data/swatches.json` | Animated paint and interior swatches, used by the story result and by any page on the ERP (see below). |
| `vin_storyteller/swatches.py` | Builds `swatches.json` from the extracted code lists and the researched paint colours. No Frappe. |

The production record lives in its own MariaDB database (for 3S Hub, `3s_production` on the same server as
ERPNext), not in the Frappe site's database.

## Swatches

The story result leads with the car's paint and interior, drawn as animated swatches: paint from a bump map
(orange peel) and a spectral flake map (metallic or pearl flake, interference colour, clearcoat highlight);
interiors as perforated leather or cloth weave. The light follows the cursor on desktop and the scroll on touch
screens, and holds still under `prefers-reduced-motion`. One shared WebGL context draws every swatch on a page;
without WebGL a swatch is a still CSS gradient. No dependencies.

Any page served by the ERP can use them:

```html
<link rel="stylesheet" href="/assets/vin_storyteller/css/swatch.css">
<div data-swatch="paint" data-code="W75" data-caption></div>
<div data-swatch="interior" data-code="18W" data-description="Charcoal Leather, Power Seats" data-caption></div>
<script>import("/assets/vin_storyteller/js/swatch-core.js").then(() => import("/assets/vin_storyteller/js/swatch.js"));</script>
```

`data-description` is optional (the record's name for the code; it wins over the table's). `data-caption` overlays
the name, code and finish or material. Elements present when the script loads are drawn; for markup added later
call `VinSwatch.mountAll(root)`, or draw one element with
`VinSwatch.render(element, {kind, code, description, caption})`, which resolves to the swatch model (`status`
`sourced`/`derived`/`missing` for paint, `named`/`missing` for interiors, `name`, `finish` or `material`, `confidence`,
`basis`). `VinSwatchCore.captionParts(model, code)` gives the caption text for your own markup.

The code tables (`public/data/swatches.json`) are rebuilt with
`python -m vin_storyteller.swatches paint_codes.tsv paint_hex.tsv interior_codes.tsv vin_storyteller/public/data/swatches.json paint_aliases.tsv interior_colours.tsv`
(the inputs live in `~/3shub-docs/storyteller_codes`, with their PROVENANCE):

- **Paint:** a colour is a published value with its source URL, or it is missing and drawn as a neutral panel
  marked "colour not on file". Where Mitsubishi and Dodge publish different values for one code, both ship and a
  Dodge car is drawn in Dodge's (`render(..., { make })`, `data-make`); a code page draws a Stealth-only code in
  Dodge's, any other in Mitsubishi's. A code with no published value or name may be `derived` from evidence that
  names its colour (BA4/HA8 = B34/H28 on the 1993 Stealth R/T grades; W9X = the white/black patrol-car GTOs); it
  is captioned "approximate colour" and records its derivation (operator, 2026-10-27).
- **Interior material:** the description if it says leather or cloth; else, for GTOs, Mitsubishi's leather option
  K03 on every car with the code (or on none); else the code's last letter, when at least 90% of the decided cars
  sharing it agree (marked *likely*). Each entry records its basis.
- **Interior colour:** no trim colour values exist, so a swatch takes a generic shade for a colour word (labelled
  "representative shade"): the description's, else the table's (`interior_colours.tsv`): *document* (a window sticker, equipment list or build record of a car with the code), *named* (a recorded
  description), *listings* (the sellers' words on Bring a Trailer / Cars & Bids for cars whose VIN gives the code),
  *catalogue* (the colour ASA's parts catalogue gives the trim parts specific to the code), or
  *letter* (the US trim letter: H/W charcoal, T tan, U red, D ivory; shown as *likely*). Otherwise the
  neutral panel. Where `interior_sampled.tsv` has a colour measured from listing photos of cars with the code, that
  colour is drawn instead, captioned with the number of cars (operator 2026-10-27: sampled everywhere).

## API

`GET /api/method/vin_storyteller.api.tell?vin=<VIN>&name=<visitor's name>`. Guests may call it 3 times an hour
per client (Cloudflare's `CF-Connecting-IP`, else Frappe's request IP); a malformed VIN doesn't count, and a
well-formed VIN without a name is refused (`invalid`) before it counts. Frappe wraps the body in `{"message": …}`:

| `status` | Meaning | Other fields |
|---|---|---|
| `found` | The VIN is on record | `story` (below) |
| `not_found` | Valid VIN, not on record | `message` |
| `invalid` | Not a VIN (17 characters, never I, O or Q) | `message` |
| `error` | The production record could not be read (logged in Frappe's Error Log) | `message` |

`story` fields: `vin`, `vehicle_name`, `model_year`, `manufacturer`, `model`, `trim`, `exterior` /
`interior` / `equipment` (`{code, description}`, description `MISSING` while a code is undeciphered),
`built`, `built_in_period`, `built_in_month`, `year_started`, `model_started`, `in_year` / `in_model` /
`in_colour` / `among_identical` (`{position, total}`), `provenance`, `history` (list of `{kind, title, url,
date, source, provenance}`; `url` is null unless it is a plain http(s) link), `rarities` (list of `{scope,
total, tier, description}`, rarest first) and `rarest` (the top tier or null).

## Code pages

Every exterior paint, interior and option code in the factory records has its own page, with its production stats
from the factory records only (CAPS 1999, CAPS 2004, ASA Japan 2008): the total; by model (3000GT / Stealth / GTO),
model year and model line; the first and last build; for a paint, its interiors (and for an interior, its paints);
and for an option code, what Mitsubishi's catalogue says it fits per grade and model year (ASA, so GTOs only).
An option code means something per chassis model code (Z11A, Z15A, Z16A), so its page is per model code. Each
kind has an index page too, and a story's exterior, interior and equipment rows link to their code pages.

| Address | Page |
|---|---|
| `/storyteller/paint`, `/storyteller/interior`, `/storyteller/option` | the kind's index |
| `/storyteller/paint?code=T87`, `/storyteller/interior?code=12A` | a paint's or interior's page |
| `/storyteller/option?model=Z16A&code=302` | an option code's page |

The pages are rendered in the browser from two guest GET endpoints, rate-limited together to 120 an hour per
client (apart from the 3 VIN lookups), cached for an hour, and never logged to `StoriesTold`:

- `GET /api/method/vin_storyteller.api.code?kind=paint|interior|option&code=<code>[&model=<model code>]`:
  `status` `found` (with `page`: `kind`, `code`, `model_code`, `description`, `names`, `total`, `by_model`,
  `by_year`, `by_line`, `first_built`, `last_built`, `pairings`, `fits`), `not_found`, `invalid` or `error`.
- `GET /api/method/vin_storyteller.api.codes?kind=...`: `status` `found` with `codes` (`code`, `model_code`,
  `description`, `total`, `by_model`), `invalid` or `error`.

The page script also reads path addresses (`/storyteller/paint/T87`, `/storyteller/option/Z16A/302`) and writes
links in that form when the page's `data-code-routes` is `path`; that needs a router that serves dynamic-route Web
Pages (frappe-public-site-router doesn't yet), so the shipped default is `query`.

Paint and interior pages, pairings and index rows carry an empty, hidden `.vst-swatch` with `data-swatch-kind`
and `data-swatch-code` for a colour swatch to fill.

## Data model

The CAPS dump provides `Production` (one row per car) and the lookup tables `Model`, `Exterior`,
`Interior` and `Equipment`. The migrations add:

- **`Production.Provenance`** (`VARCHAR(30)`): where the record came from. The dump's records are `CAPS 1999`
  (migration 0005); every later write names its own source (the column's old `'CAPS'` default is never relied on).
- **`VehicleHistory`**: what is known about a car after the factory, one row per record:
  `VIN`, `RecordType` (`auction`, `photo`, `sale`, `registration`, `service`, `article` or `other`; enforced),
  `Title`, `URL`, `RecordDate`, `Source`, `Notes`, `Provenance` (who added it) and `CreatedAt`.
- **`ClassificationLabel`**, **`OptionContent`**, **`OptionItem`** (migration 0006): what Mitsubishi's own catalogues
  say the codes mean, per source build and language: a model code's grade (classification) text, which option
  items an option (equipment) code fits per model, grade and model year, and each option item's text. Loaded by
  one-off host jobs from CAPS 2004 and ASA Japan 2008 (formats: 3S Hub SOP → *Mitsubishi CAPS and ASA Data
  Formats*).
- **Indexes** on the columns every lookup uses.

Adding a history record is a plain insert, for example:

```sql
INSERT INTO VehicleHistory (VIN, RecordType, Title, URL, RecordDate, Source, Provenance)
VALUES ('JA3AM84J3NY012345', 'auction', 'Sold on Bring a Trailer', 'https://bringatrailer.com/…',
        '2021-05-01', 'Bring a Trailer', '3S Hub');
```

Migrations are numbered files in [`vin_storyteller/sql/migrations/`](vin_storyteller/sql/migrations/). Each
runs once, in order, and is recorded in `SchemaMigration`. Never edit one that has run; add the next number.

### Factory records

Three provenances are factory records, named by the Mitsubishi catalogue build they came from; they tell full
stories and count in positions and totals:

- `CAPS 1999`: the original export, the 3000GT/Stealth part of Michael Reid's NA9199 (taken from CAPS
  `PASEN/SHARYO` dated 1999-09-16; every row identical). NA9199 is all of Nagoya's 1991–99 output; its 85,135
  Mitsubishi Diamante sedans (Model `XX`) were deleted on 2026-10-27, leaving 151,454 cars (Reid's 3S9199 count).
  The database holds 3000GTs, Stealths and GTOs only.
- `CAPS 2004`: cars only the 2004 CAPS build (WINCAPS, `PASEN/SHARYO`) holds: the 1997 Nov 1996 – Jan 1997 block
  and the last two 1999 SLs.
- `ASA Japan 2008`: every Japanese-market GTO (Z15A/Z16A, 23,369 cars, 1990–2000) from Mitsubishi's ASA Japan
  EPC. Model year is the record's own where it stores one, else the catalogue's production window for the
  build date (both agree on all 3,404 that store it). A 2000 model year is `00`.
- `ASA General 2008`: export-market 3000GTs (756 Z16A twin-turbo cars, 345 of them UK-spec) from Mitsubishi's ASA
  General EPC, Model `EL` / `ER` by drive side (migration 0007). They are keyed by a 17-character VIN (JMA/JMY,
  no ISO check digit) or, for 1992–94 cars, a 14-character frame number such as `DMNZ16APY00001`; the model year
  is the year letter in either.

Positions and totals count within the car's own market (North American VINs, JDM chassis numbers, or export
cars), so they never mix numbering schemes. The story's **breakdowns** span every model and market: how many
factory-record cars share its model year, exterior colour (every year, and its year), interior, colour pair,
production period and month, and of which models (3000GT, Stealth, GTO). Every other provenance is a partial
story outside all counts.

### Cars the factory records are missing


A real VIN proven by another source (a factory price label, a dealer or auction record) is added with
`bench --site <site> vin-storyteller-add-record <VIN> "<source>"` (admin credentials from the environment, as for
migrate). Only what the VIN establishes is stored: its model line comes from the CAPS cars sharing its first eight
characters (its own model year, else the nearest), its build date and colour, interior and equipment codes stay
empty, and `Provenance` names the source. The command refuses a VIN already on record, a wrong check digit, a
non-1991–99 model year, or a VIN no CAPS car resembles. Such a car is told as a **partial story** (model, year,
VIN, "not in Mitsubishi's factory export … on record from <source>"), and every position, total and rarity counts
CAPS cars only.

A Japanese-market GTO is added the same way by its chassis number (`Z15A-`/`Z16A-` and seven digits, stored in
canonical `Z16A-0011452` form in the VIN column): its family gives the Model (`G5` / `G6`, migration 0004,
Mitsubishi GTO with no trim), the seven digits are its serial, and model year, build date and codes stay empty.
What a source says beyond that (a factory build date, a trim) goes into `VehicleHistory` with that source. Since
ASA Japan holds every GTO, this is only for a chassis number ASA lacks.

### Not-found answers

A VIN without a record gets the most specific reason the VIN and the record give: not a JA3/JB3 VIN; not a
1991–99 model year; a wrong check digit (all 151,454 CAPS 1999 VINs have a correct one, so this means a typo); a serial
inside a stretch missing from the export (naming the cars either side and their build periods); before the
year's first or after its last car on record; otherwise the original message. A Japanese-market GTO chassis
number (`Z15A-`/`Z16A-` and seven digits) is looked up the same way and, when it isn't on record, answered as
not in Mitsubishi's ASA Japan record of GTOs.

## Rarity

A car is rated on three runs within its model year: its **exact specification** (model, trim, colour,
interior and equipment), its **colour** within its model, and its **model**. Each run's size maps to a tier:

| Cars in the run | Tier | Effect |
|---|---|---|
| 1 | One of one | Gold badge, animated iridescent border, shimmering name |
| 2–9 | Fewer than 10 | Morocco Red badge and pulsing glow |
| 10–24 | Fewer than 25 | Fiji Blue |
| 25–49 | Fewer than 50 | Danube Blue |
| 50–99 | Fewer than 100 | Silver |

Every rare run gets a badge; the rarest decides the page effect. Animation is off for visitors who prefer
reduced motion. Mitsubishi sometimes used several codes for the same colour or equipment, so a spec run can
read smaller than it really was. The page says so.

## Deploying

1. **Install the app** on the site (`bench get-app https://github.com/JamesonRGrieve/frappe-3s-vin-storyteller`,
   then `bench --site <site> install-app vin_storyteller`), or through your deployment pipeline's app list.
2. **Load the production record** into its own database on a MariaDB server the site can reach, and create a
   database user for the site with `SELECT` and `INSERT` (the app inserts only into `StoriesTold`).
3. **Migrate the schema**: `bench --site <site> vin-storyteller-migrate`. The command needs a user allowed to
   `ALTER` and `CREATE`, given only through the environment (`VIN_STORYTELLER_DB_ADMIN_USER`,
   `VIN_STORYTELLER_DB_ADMIN_PASSWORD`), never in site config or on the command line.
4. **Site config** (`site_config.json`):

   | Key | Default |
   |---|---|
   | `vin_storyteller_db_host` | `localhost` |
   | `vin_storyteller_db_port` | `3306` |
   | `vin_storyteller_db_name` | `3s_production` |
   | `vin_storyteller_db_user` | (required, the `SELECT`-only user) |
   | `vin_storyteller_db_password` | (required) |

5. **The page.** Create a published Web Page that includes the template. On a host served by
   [frappe-public-site-router](https://github.com/JamesonRGrieve/frappe-public-site-router), route it under
   the site's prefix so it answers at the host's root, e.g. `<prefix>/storyteller` → `3shub.ca/storyteller`:

   ```json
   {
     "doctype": "Web Page",
     "title": "VIN Storyteller",
     "route": "<prefix>/storyteller",
     "published": 1,
     "content_type": "HTML",
     "dynamic_template": 1,
     "main_section_html": "{% include \"vin_storyteller/templates/includes/storyteller.html\" %}"
   }
   ```

6. **The code pages.** Published Web Pages with `{% include "vin_storyteller/templates/includes/codes.html" %}` as
   their `main_section_html` (dynamic template, like the page above): the three indexes
   `<prefix>/storyteller/paint`, `<prefix>/storyteller/interior` and `<prefix>/storyteller/option`, and three
   dynamic-route pages (`dynamic_route` set) `<prefix>/storyteller/paint/<code>`,
   `<prefix>/storyteller/interior/<code>` and `<prefix>/storyteller/option/<model>/<code>`. frappe-public-site-router
   serves dynamic-route Web Pages and, through this app's `public_site_sitemap_routes` hook, lists every code page in
   the site's sitemap. The templates write path links (`data-code-routes="path"`); `?code=` addresses still work.

## Development

No bench is needed for the tests.

```sh
uv run --no-project --with pytest python -I -m pytest   # Python: logic, queries, migrations, answers
node --test 'tests/js/*.test.mjs'                       # front-end helpers
uvx ruff format --check . && uvx ruff check .
```

The Python tests run the real queries and migrations against an in-memory SQLite database shaped like the
CAPS dump (`tests/conftest.py`). Only `api.py` and `commands.py`, the thin Frappe wiring, run outside them.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE). The production data is not part of this repository.
