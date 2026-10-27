# SPDX-License-Identifier: AGPL-3.0-or-later
"""The swatches' code tables: paint code -> published colour and finish, interior code -> leather or cloth.

Pure logic, no Frappe. Builds `public/data/swatches.json` (served as
/assets/vin_storyteller/data/swatches.json and read by `public/js/swatch.js`) from the extracted code lists
(`paint_codes.tsv`, `interior_codes.tsv`) and the researched colour values (`paint_hex.tsv`):

    python -m vin_storyteller.swatches PAINT_CODES PAINT_HEX INTERIOR_CODES OUT_JSON [PAINT_ALIASES [INTERIOR_COLOURS]]

Rules (operator, 2026-10-27):
- Only 3000GTs, Stealths and GTOs: a code used only by the record's other Nagoya-built cars (the deleted
  Diamantes) is left out, and the `other_nagoya` column is otherwise ignored. EXT / INT are the record's
  "not recorded" placeholders, not codes.
- A paint colour is a published value with its source URL, or it is missing; never a guess. Where Mitsubishi
  and Dodge publish different values for one code, both ship (`hex`, `dodge_hex`) and a Dodge Stealth is drawn
  in Dodge's (operator: by the car's brand).
- A code with no published value or name may be `derived` from evidence that names its colour (operator: derive
  from the colour name): the same paint on another grade (BA4 = B34 on the R/T), or a colour word in the
  catalogue (W9X, the white/black patrol-car GTOs), or, where no official value exists, sampled from listing photos
  of cars whose VIN gives the code (`sampled: true`; operator 2026-10-27). It carries `approximate: true` and the
  derivation.
- Interior colour (`interior_colours.tsv`): a colour word per code, named (a recorded description), from listings
  (the sellers' words for cars whose VIN gives the code), from the catalogue (the colour of the trim parts specific
  to the code), or from the US trim letter; drawn as a representative shade for the word, never a factory value.
- Interior material: an explicit description wins; then, for GTOs, Mitsubishi's leather option K03 on the
  car; then, as evidence rather than a rule, the code's suffix letter when the decided codes sharing it
  agree. Each decision records how it was made.
- Paint aliases (`paint_aliases.tsv`): CAPS writes some early paints in an "A" form (RA8, WA5, TA7 ...) where
  Mitsubishi's ASA USA gives the same cars the plain paint code (R38, W75, T87 ...). An alias with no published
  value of its own takes its paint code's published value, and says so.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

MODELS = ("3000GT", "Stealth", "GTO")
PLACEHOLDERS = frozenset({"EXT", "INT"})
UNKNOWN_NAMES = frozenset({"", "MISSING"})
HEX = re.compile(r"^#[0-9A-F]{6}$")
SAFE_URL = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)
FINISHES = frozenset({"solid", "metallic", "pearl"})
# A suffix letter is evidence for a material only when this share of the decided cars carrying it agree.
LETTER_AGREEMENT = 0.9


def read_tsv(path: str | Path) -> list[dict[str, str]]:
	with open(path, newline="", encoding="utf-8") as handle:
		return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def _count(row: Mapping[str, str], column: str) -> int:
	value = (row.get(column) or "").strip()
	return int(value) if value else 0


def model_counts(row: Mapping[str, str]) -> dict[str, int]:
	return {model: _count(row, model) for model in MODELS}


def in_scope(row: Mapping[str, str]) -> bool:
	"""A real code used by at least one 3000GT, Stealth or GTO."""
	code = (row.get("code") or "").strip().upper()
	return bool(code) and code not in PLACEHOLDERS and sum(model_counts(row).values()) > 0


def known(name: str | None) -> str:
	name = (name or "").strip()
	return "" if name in UNKNOWN_NAMES else name


def finish_from_name(name: str) -> str:
	"""pearl (Mitsubishi's "Mica", anyone's "Pearl"), metallic, solid; "" when there is no name."""
	if not name:
		return ""
	if re.search(r"\b(pearl|mica)\b", name, re.IGNORECASE):
		return "pearl"
	if re.search(r"\bmetallic\b", name, re.IGNORECASE):
		return "metallic"
	return "solid"


def normalize_hex(value: str | None) -> str:
	"""'#rrggbb' / 'rrggbb' -> '#RRGGBB'; anything else -> ''."""
	text = (value or "").strip().upper()
	if text and not text.startswith("#"):
		text = f"#{text}"
	return text if HEX.match(text) else ""


def _usage(row: Mapping[str, str]) -> dict:
	counts = model_counts(row)
	return {
		"models": [model for model in MODELS if counts[model]],
		"model_years": [y for y in (row.get("model_years") or "").split(",") if y],
	}


def paint_table(
	code_rows: Iterable[Mapping[str, str]], hex_rows: Iterable[Mapping[str, str]]
) -> dict[str, dict]:
	"""code -> name, Dodge name, finish, hex (published or ""), flake_hex, source, status, notes, usage."""
	researched = {(row.get("code") or "").strip().upper(): row for row in hex_rows}
	table: dict[str, dict] = {}
	for row in code_rows:
		if not in_scope(row):
			continue
		code = row["code"].strip().upper()
		found = researched.get(code, {})
		mitsubishi = known(row.get("mitsubishi_name")) or known(found.get("mitsubishi_name"))
		dodge = known(row.get("dodge_name")) or known(found.get("dodge_name"))
		name = mitsubishi or dodge
		finish = finish_from_name(name) or (found.get("finish") or "").strip().lower()
		base = normalize_hex(found.get("base_hex"))
		flake = normalize_hex(found.get("flake_hex"))
		source = (found.get("source_url") or "").strip()
		sourced = bool(base) and bool(SAFE_URL.match(source))
		derivation = (found.get("derivation") or "").strip()
		dodge_hex = normalize_hex(found.get("dodge_hex"))
		dodge_source = (found.get("dodge_source_url") or "").strip()
		has_dodge = sourced and bool(dodge_hex) and bool(SAFE_URL.match(dodge_source))
		table[code] = {
			"name": name,
			"mitsubishi_name": mitsubishi,
			"dodge_name": dodge,
			"finish": finish if finish in FINISHES else "",
			"hex": base if sourced else "",
			"flake_hex": flake if sourced else "",
			"source": source if sourced else "",
			"status": ("derived" if derivation else "sourced") if sourced else "missing",
			"notes": (found.get("notes") or "").strip(),
			**_usage(row),
		}
		if has_dodge:
			table[code].update(dodge_hex=dodge_hex, dodge_source=dodge_source)
		if sourced and derivation:
			table[code].update(approximate=True, derivation=derivation)
			if (found.get("status") or "").strip() == "sampled":
				table[code]["sampled"] = True  # measured from listing photos of cars with this code
	return table


def _material_from_description(description: str) -> str:
	if re.search(r"\bleather\b", description, re.IGNORECASE):
		return "leather"
	if re.search(r"\b(cloth|fabric|velour|tricot)\b", description, re.IGNORECASE):
		return "cloth"
	return ""


def decide_material(row: Mapping[str, str]) -> dict | None:
	"""The material from the code's own evidence (description, then GTO K03), or None."""
	description = known(row.get("description"))
	material = _material_from_description(description)
	if material:
		return {"material": material, "confidence": "decided", "basis": f'description "{description}"'}
	# US Mitsubishi 3000GTs: ASA USA's option items say when a car has leather seats (K03, K67 ...). Only "every car
	# with this code has one" is evidence: leather standard on a grade needs no option item, so its absence is not
	# evidence of cloth.
	us_leather = _count(row, "us_with_leather_seat_item")
	if us_leather and not _count(row, "us_without_leather_seat_item"):
		return {
			"material": "leather",
			"confidence": "decided",
			"basis": f"ASA USA leather-seat option item (K03 / K67) on all {us_leather:,} US 3000GTs with this code",
		}
	with_k03 = _count(row, "gto_with_leather_option_K03")
	without_k03 = _count(row, "gto_without_K03")
	if with_k03 and not without_k03:
		return {
			"material": "leather",
			"confidence": "decided",
			"basis": f"ASA option K03 (leather seat & room trim) on all {with_k03:,} GTOs with this code",
		}
	if without_k03 and not with_k03:
		return {
			"material": "cloth",
			"confidence": "decided",
			"basis": f"ASA option K03 (leather seat & room trim) on none of the {without_k03:,} GTOs with this code",
		}
	return None


def evidence_cars(row: Mapping[str, str], decision: Mapping[str, str]) -> int:
	"""How many cars a decision was observed on: every car for a description, the GTOs for K03."""
	if decision["basis"].startswith("description"):
		return sum(model_counts(row).values())
	if decision["basis"].startswith("ASA USA"):
		return _count(row, "us_with_leather_seat_item")
	return _count(row, "gto_with_leather_option_K03") + _count(row, "gto_without_K03")


def _suffix(code: str) -> str:
	return code[-1:] if code[-1:].isalpha() else ""


def letter_evidence(decided: Mapping[str, tuple[dict, int]]) -> dict[str, dict]:
	"""Per suffix letter: evidence cars by material among the decided codes, and the codes behind them."""
	evidence: dict[str, dict] = defaultdict(
		lambda: {"leather": 0, "cloth": 0, "codes": {"leather": [], "cloth": []}}
	)
	for code, (decision, cars) in sorted(decided.items()):
		letter = _suffix(code)
		if letter:
			evidence[letter][decision["material"]] += cars
			evidence[letter]["codes"][decision["material"]].append(code)
	return dict(evidence)


def infer_from_letter(code: str, evidence: Mapping[str, dict]) -> dict:
	letter = _suffix(code)
	seen = evidence.get(letter)
	if not seen:
		return {
			"material": "unknown",
			"confidence": "",
			"basis": f"no decided code ends in {letter or 'this'}",
		}
	total = seen["leather"] + seen["cloth"]
	for material, other in (("leather", "cloth"), ("cloth", "leather")):
		if total and seen[material] / total >= LETTER_AGREEMENT:
			against = f"; against: {', '.join(seen['codes'][other])}" if seen["codes"][other] else ""
			return {
				"material": material,
				"confidence": "inferred",
				"basis": (
					f"suffix letter {letter}: {seen[material]:,} of {total:,} decided cars ending {letter} are "
					f"{material} ({', '.join(seen['codes'][material])}){against}"
				),
			}
	return {
		"material": "unknown",
		"confidence": "",
		"basis": (
			f"suffix letter {letter} is mixed: leather {seen['leather']:,} cars "
			f"({', '.join(seen['codes']['leather'])}), cloth {seen['cloth']:,} ({', '.join(seen['codes']['cloth'])})"
		),
	}


COLOUR_CONFIDENCES = frozenset({"named", "listings", "catalogue", "letter"})


def interior_colours(rows: Iterable[Mapping[str, str]]) -> dict[str, dict]:
	"""code -> colour word, how it was found (named | catalogue | letter) and the evidence."""
	colours: dict[str, dict] = {}
	for row in rows:
		code = (row.get("code") or "").strip().upper()
		word = (row.get("colour") or "").strip()
		confidence = (row.get("confidence") or "").strip().lower()
		if code and word and confidence in COLOUR_CONFIDENCES:
			colours[code] = {
				"colour": word,
				"colour_confidence": confidence,
				"colour_basis": (row.get("basis") or "").strip(),
			}
	return colours


def interior_table(
	rows: Iterable[Mapping[str, str]], colour_rows: Iterable[Mapping[str, str]] = ()
) -> dict[str, dict]:
	"""code -> description, material (leather | cloth | unknown), confidence, basis, colour word, usage."""
	rows = [row for row in rows if in_scope(row)]
	colours = interior_colours(colour_rows)
	decided: dict[str, tuple[dict, int]] = {}
	for row in rows:
		decision = decide_material(row)
		if decision:
			decided[row["code"].strip().upper()] = (decision, evidence_cars(row, decision))
	# The suffix-letter rule learns only from descriptions and the GTO K03 evidence: US leather-seat items decide their
	# own codes, but leather is option-driven there, so letting them vote would flip unrelated codes (a Stealth
	# base/ES "D" interior, which ASA USA doesn't cover, would turn leather).
	evidence = letter_evidence({c: d for c, d in decided.items() if not d[0]["basis"].startswith("ASA USA")})
	table: dict[str, dict] = {}
	for row in rows:
		code = row["code"].strip().upper()
		decision = decided[code][0] if code in decided else infer_from_letter(code, evidence)
		table[code] = {
			"description": known(row.get("description")),
			**decision,
			**colours.get(code, {}),
			**_usage(row),
		}
	return table


def apply_aliases(paint: dict[str, dict], alias_rows: Iterable[Mapping[str, str]]) -> dict[str, dict]:
	"""Give each aliased code without a published value its paint code's (same paint, another code)."""
	for row in alias_rows:
		code = (row.get("caps_code") or "").strip().upper()
		target = (row.get("paint_code") or "").strip().upper()
		entry, source = paint.get(code), paint.get(target)
		if not entry or not source:
			continue
		entry["same_paint_as"] = target
		if entry["status"] == "missing" and source["status"] == "sourced":
			entry.update(
				hex=source["hex"], flake_hex=source["flake_hex"], source=source["source"], status="sourced"
			)
			if "dodge_hex" in source:
				entry.update(dodge_hex=source["dodge_hex"], dodge_source=source["dodge_source"])
			entry["finish"] = entry["finish"] or source["finish"]
			entry["notes"] = (
				f"Same paint as {target}: Mitsubishi's ASA USA gives the same cars both codes; colour from {target}'s "
				f"published value. {entry['notes']}"
			).strip()
	return paint


def build(
	paint_codes: str | Path,
	paint_hex: str | Path,
	interior_codes: str | Path,
	paint_aliases: str | Path | None = None,
	interior_colour_rows: str | Path | None = None,
) -> dict:
	paint = paint_table(read_tsv(paint_codes), read_tsv(paint_hex))
	if paint_aliases:
		apply_aliases(paint, read_tsv(paint_aliases))
	return {
		"version": 1,
		"about": (
			"Paint: published colour values with their source URL (Mitsubishi's, and Dodge's where it differs), "
			"approximate values derived from named evidence, or missing (shown as 'colour not on file'). "
			"Interior: leather or cloth, and a colour word, each with its basis. 3000GT, Stealth and GTO codes only."
		),
		"paint": paint,
		"interior": interior_table(
			read_tsv(interior_codes), read_tsv(interior_colour_rows) if interior_colour_rows else ()
		),
	}


def main(argv: list[str]) -> int:
	if len(argv) not in (4, 5, 6):
		print(__doc__, file=sys.stderr)
		return 2
	data = build(*argv[:3], *argv[4:6])
	Path(argv[3]).write_text(
		json.dumps(data, indent="\t", sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
