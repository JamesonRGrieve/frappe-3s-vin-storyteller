# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import re
from pathlib import Path

from vin_storyteller import swatches

SHIPPED = Path(__file__).resolve().parents[1] / "vin_storyteller" / "public" / "data" / "swatches.json"

PAINT_COLUMNS = "code\tmitsubishi_name\tdodge_name\tfinish_from_name\ttotal\t3000GT\tStealth\tGTO\tother_nagoya\tmodel_years"
HEX_COLUMNS = "code\tmitsubishi_name\tdodge_name\tfinish\tbase_hex\tflake_hex\tsource_url\tsource_model_years\tstatus\tnotes"
INTERIOR_COLUMNS = (
	"code\tdescription\ttotal\t3000GT\tStealth\tGTO\tother_nagoya\tgto_with_leather_option_K03\tgto_without_K03"
	"\tmodel_years"
)


def write(tmp_path, name, header, rows):
	path = tmp_path / name
	path.write_text("\n".join([header, *("\t".join(row) for row in rows)]) + "\n", encoding="utf-8")
	return path


def paint_row(code, mitsubishi, dodge, gt=0, stealth=0, gto=0, other=0, years="92"):
	return [
		code,
		mitsubishi,
		dodge,
		"",
		str(gt + stealth + gto + other),
		str(gt),
		str(stealth),
		str(gto),
		str(other),
		years,
	]


def interior_row(code, description, gt=0, stealth=0, gto=0, other=0, k03=0, no_k03=0, years="92"):
	total = gt + stealth + gto + other
	return [
		code,
		description,
		str(total),
		str(gt),
		str(stealth),
		str(gto),
		str(other),
		str(k03),
		str(no_k03),
		years,
	]


def test_in_scope_drops_diamante_only_codes_and_placeholders():
	assert swatches.in_scope({"code": "W75", "3000GT": "1", "other_nagoya": "5"})
	assert not swatches.in_scope(
		{"code": "S04", "3000GT": "0", "Stealth": "0", "GTO": "0", "other_nagoya": "5700"}
	)
	assert not swatches.in_scope({"code": "EXT", "3000GT": "836"})
	assert not swatches.in_scope({"code": "", "GTO": "3"})


def test_finish_and_hex_normalization():
	assert swatches.finish_from_name("Danube Blue Mica") == "pearl"
	assert swatches.finish_from_name("Ascot Silver Metallic") == "metallic"
	assert swatches.finish_from_name("Caracas Red") == "solid"
	assert swatches.finish_from_name("") == ""
	assert swatches.normalize_hex("2c4f8c") == "#2C4F8C"
	assert swatches.normalize_hex("#2C4F8C") == "#2C4F8C"
	for bad in ("", None, "#FFF", "MISSING", "#GG0000"):
		assert swatches.normalize_hex(bad) == ""


def test_paint_table_keeps_only_sourced_values(tmp_path):
	codes = write(
		tmp_path,
		"paint_codes.tsv",
		PAINT_COLUMNS,
		[
			paint_row("B34", "Danube Blue Mica", "Dark Blue Pearl", gt=10, stealth=5, other=3, years="93,94"),
			paint_row("R71", "Caracas Red", "Fire Storm", gt=4),
			paint_row("W20", "MISSING", "MISSING", stealth=2),
			paint_row("A71", "", "", gto=4),
			paint_row("S04", "MISSING", "MISSING", other=9),
		],
	)
	researched = write(
		tmp_path,
		"paint_hex.tsv",
		HEX_COLUMNS,
		[
			["B34", "", "", "pearl", "2c4f8c", "", "https://example.com/b34", "1993", "sourced", "from RGB"],
			["R71", "", "", "solid", "#C00000", "", "", "", "sourced", "no URL, so not sourced"],
			[
				"A71",
				"Some Silver",
				"",
				"metallic",
				"#B0B0B0",
				"#E0E0E0",
				"javascript:alert(1)",
				"",
				"sourced",
				"",
			],
		],
	)
	table = swatches.paint_table(swatches.read_tsv(codes), swatches.read_tsv(researched))
	assert set(table) == {"B34", "R71", "W20", "A71"}
	assert table["B34"] == {
		"name": "Danube Blue Mica",
		"mitsubishi_name": "Danube Blue Mica",
		"dodge_name": "Dark Blue Pearl",
		"finish": "pearl",
		"hex": "#2C4F8C",
		"flake_hex": "",
		"source": "https://example.com/b34",
		"status": "sourced",
		"notes": "from RGB",
		"models": ["3000GT", "Stealth"],
		"model_years": ["93", "94"],
	}
	assert table["R71"]["status"] == "missing" and table["R71"]["hex"] == ""
	assert table["A71"]["status"] == "missing" and table["A71"]["source"] == ""
	assert table["A71"]["name"] == "Some Silver"  # a researched name fills a gap
	assert table["A71"]["finish"] == "solid"  # read from that name
	assert table["W20"] == {**table["W20"], "name": "", "finish": "", "status": "missing"}


def test_interior_material_decisions(tmp_path):
	rows = [
		interior_row("18W", "Charcoal Leather, Power Seats", stealth=100),
		interior_row("08H", "Charcoal Cloth, Power Seats", stealth=50),
		interior_row("08A", "Red Cloth, Power Seats", stealth=40),
		interior_row("14W", "MISSING", gt=900, gto=100, k03=100),
		interior_row("33W", "", gto=5, no_k03=5),
		interior_row("04H", "MISSING", gt=10, gto=90, no_k03=90),
		interior_row("21A", "MISSING", gt=10, gto=60, k03=60),
		interior_row("07J", "", gto=7, k03=3, no_k03=4),
		interior_row("17W", "MISSING", stealth=30),
		interior_row("05H", "MISSING", stealth=30),
		interior_row("10A", "MISSING", gt=30),
		interior_row("47E", "MISSING", gt=30),
		interior_row("31X", "MISSING", other=99),
		interior_row("INT", "MISSING", gt=9),
	]
	path = write(tmp_path, "interior_codes.tsv", INTERIOR_COLUMNS, rows)
	table = swatches.interior_table(swatches.read_tsv(path))
	assert "31X" not in table and "INT" not in table
	assert table["18W"]["material"] == "leather" and table["18W"]["confidence"] == "decided"
	assert table["08H"]["material"] == "cloth" and "description" in table["08H"]["basis"]
	assert table["14W"]["material"] == "leather" and "K03" in table["14W"]["basis"]
	assert table["33W"]["material"] == "cloth" and "none of the 5 GTOs" in table["33W"]["basis"]
	assert table["04H"]["material"] == "cloth"
	# Mixed K03 is not decided by the code; J's other evidence is only itself, so unknown.
	assert table["07J"]["material"] == "unknown"
	# W: 200 leather cars (18W, 14W's GTOs) against 5 cloth -> inferred leather, naming the counter-evidence.
	assert table["17W"]["material"] == "leather" and table["17W"]["confidence"] == "inferred"
	assert "against: 33W" in table["17W"]["basis"]
	assert table["17W"]["basis"].startswith("suffix letter W: 200 of 205 decided cars")
	assert table["05H"]["material"] == "cloth" and table["05H"]["confidence"] == "inferred"
	# A: 60 GTOs with K03 (21A; its 3000GTs are not evidence) against 40 cloth cars (08A) -> mixed, unknown.
	assert table["10A"]["material"] == "unknown" and "mixed" in table["10A"]["basis"]
	assert table["47E"]["material"] == "unknown" and "no decided code" in table["47E"]["basis"]


def test_main_writes_json(tmp_path):
	codes = write(tmp_path, "p.tsv", PAINT_COLUMNS, [paint_row("T87", "Fiji Blue Metallic", "", gt=1)])
	researched = write(tmp_path, "h.tsv", HEX_COLUMNS, [])
	interior = write(tmp_path, "i.tsv", INTERIOR_COLUMNS, [interior_row("18T", "Tan Leather", stealth=1)])
	out = tmp_path / "swatches.json"
	assert swatches.main([str(codes), str(researched), str(interior), str(out)]) == 0
	data = json.loads(out.read_text(encoding="utf-8"))
	assert data["paint"]["T87"]["status"] == "missing"
	assert data["interior"]["18T"]["material"] == "leather"
	assert swatches.main([]) == 2


def test_shipped_table_is_well_formed():
	data = json.loads(SHIPPED.read_text(encoding="utf-8"))
	assert data["paint"] and data["interior"]
	for code, entry in data["paint"].items():
		assert re.fullmatch(r"[A-Z0-9]{3}", code)
		assert entry["status"] in {"sourced", "missing"}
		if entry["status"] == "sourced":
			assert re.fullmatch(r"#[0-9A-F]{6}", entry["hex"]), code
			assert re.match(r"https?://", entry["source"]), code
		else:
			assert entry["hex"] == "" and entry["flake_hex"] == "", code
		assert entry["finish"] in {"", "solid", "metallic", "pearl"}
		assert entry["models"], code
	for code, entry in data["interior"].items():
		assert entry["material"] in {"leather", "cloth", "unknown"}, code
		assert entry["basis"], code


def test_an_alias_takes_its_paint_codes_published_value():
	from vin_storyteller.swatches import apply_aliases

	paint = {
		"R38": {
			"status": "sourced",
			"hex": "#DA2318",
			"flake_hex": "",
			"source": "https://x/r38",
			"finish": "solid",
			"notes": "",
		},
		"RA8": {
			"status": "missing",
			"hex": "",
			"flake_hex": "",
			"source": "",
			"finish": "",
			"notes": "none found",
		},
		"TA7": {
			"status": "sourced",
			"hex": "#123456",
			"flake_hex": "",
			"source": "https://x/ta7",
			"finish": "",
			"notes": "",
		},
		"T87": {
			"status": "sourced",
			"hex": "#4F8EBF",
			"flake_hex": "",
			"source": "https://x/t87",
			"finish": "",
			"notes": "",
		},
	}
	apply_aliases(
		paint, [{"caps_code": "RA8", "paint_code": "R38"}, {"caps_code": "TA7", "paint_code": "T87"}]
	)
	assert (
		paint["RA8"]["hex"] == "#DA2318"
		and paint["RA8"]["status"] == "sourced"
		and paint["RA8"]["finish"] == "solid"
	)
	assert paint["RA8"]["same_paint_as"] == "R38" and "Same paint as R38" in paint["RA8"]["notes"]
	assert paint["TA7"]["hex"] == "#123456"  # its own published value is kept
