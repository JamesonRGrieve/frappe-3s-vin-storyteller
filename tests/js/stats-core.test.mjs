// SPDX-License-Identifier: AGPL-3.0-or-later
// Unit tests for the stats page's pure helpers. Run: node --test 'tests/js/*.test.mjs'
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../vin_storyteller/public/js/stats-core.js", import.meta.url), "utf8");
const sandbox = { URLSearchParams };
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const core = sandbox.VinStatsCore;
const plain = (value) => JSON.parse(JSON.stringify(value));

// The API's shape (stats.build_stats): rows are [year, model, region, value, cars].
const STATS = {
	total: 100,
	years: ["1991", "1992", "1993"],
	models: ["GTO", "3000GT", "Stealth"],
	regions: [
		{ name: "Japan", market: "Japan", country: "Japan" },
		{ name: "California", market: "North America", country: "United States of America" },
		{ name: "Federal (49-state)", market: "North America", country: "United States of America" },
		{ name: "Gulf states (GCC)", market: "Export", country: "" },
	],
	facets: {
		line: {
			values: [{ name: "Mitsubishi GTO" }, { name: "Mitsubishi 3000GT VR-4" }, { name: "Dodge Stealth" }],
			rows: [
				[0, 0, 0, 0, 30],
				[1, 0, 0, 0, 10],
				[1, 1, 1, 1, 20],
				[2, 1, 2, 1, 25],
				[2, 2, 2, 2, 10],
				[2, 1, 3, 1, 5],
			],
		},
		paint: {
			values: [
				{ code: "T87", name: "Fiji Blue" },
				{ code: "R25", name: "Morocco Red" },
				{ code: "", name: "Not recorded" },
			],
			rows: [
				[0, 0, 0, 0, 30],
				[1, 0, 0, 1, 10],
				[1, 1, 1, 0, 20],
				[2, 1, 2, 1, 25],
				[2, 2, 2, 2, 10],
				[2, 1, 3, 0, 5],
			],
		},
		month: {
			values: [{ code: "1990-11", name: "1990-11" }, { code: "1992-03", name: "1992-03" }, { code: "", name: "Not recorded" }],
			rows: [
				[0, 0, 0, 0, 30],
				[1, 0, 0, 1, 10],
				[1, 1, 1, 1, 20],
				[2, 1, 2, 1, 25],
				[2, 2, 2, 2, 10],
				[2, 1, 3, 1, 5],
			],
		},
		colours: {
			values: [
				{ paint: "T87", interior: "12A" },
				{ paint: "R25", interior: "12A" },
				{ paint: "", interior: "12A" },
			],
			rows: [
				[0, 0, 0, 0, 30],
				[1, 0, 0, 1, 10],
				[1, 1, 1, 0, 20],
				[2, 1, 2, 1, 25],
				[2, 2, 2, 2, 10],
				[2, 1, 3, 0, 5],
			],
		},
		interior: { values: [{ code: "12A", name: "Grey" }], rows: [[0, 0, 0, 0, 100]] },
		generation: {
			values: [{ name: "2nd generation (1994 on)" }, { name: "1st generation (to 1993)" }],
			rows: [
				[0, 0, 0, 1, 40],
				[1, 1, 1, 1, 20],
				[2, 1, 2, 0, 40],
			],
		},
		option_records: {
			values: [
				{ code: "on_record", name: "Option contents on record" },
				{ code: "not_on_record", name: "Option contents not on record" },
			],
			rows: [
				[0, 0, 0, 0, 30],
				[1, 0, 0, 0, 10],
				[1, 1, 1, 1, 20],
				[2, 1, 2, 1, 35],
				[2, 1, 3, 0, 5],
			],
		},
		options: {
			values: [
				{ code: "K03", name: "LEATHER SEAT & ROOM TRIM" },
				{ code: "S11", name: "SEAT HEATER" },
			],
			rows: [
				[0, 0, 0, 0, 20],
				[1, 0, 0, 1, 4],
				[2, 1, 3, 1, 5],
			],
		},
		rarity: {
			values: [
				{ code: "common", name: "100 or more", order: 5 },
				{ code: "one_of_one", name: "One of one", order: 0 },
			],
			rows: [
				[0, 0, 0, 0, 90],
				[2, 1, 3, 1, 10],
			],
		},
	},
};

test("a summary counts the filtered cars", () => {
	const all = core.summary(STATS, core.emptyFilter());
	assert.equal(all.total, 100);
	assert.equal(all.models, 3);
	assert.equal(all.regions, 4);
	assert.equal(all.paints, 2); // "Not recorded" is no paint
	assert.deepEqual([all.firstYear, all.lastYear], ["1991", "1993"]);
	const gtos = core.summary(STATS, { ...core.emptyFilter(), model: ["GTO"] });
	assert.equal(gtos.total, 40);
	const range = core.summary(STATS, { ...core.emptyFilter(), from: "1992", to: "1992" });
	assert.equal(range.total, 30);
});

test("filters combine models, markets, regions and years", () => {
	const f = { ...core.emptyFilter(), market: ["North America"], model: ["3000GT"] };
	assert.equal(core.summary(STATS, f).total, 45);
	const g = { ...f, region: ["California"] };
	assert.equal(core.summary(STATS, g).total, 20);
});

test("regions are ranked, and grouped by map country", () => {
	const regions = core.regionTotals(STATS, core.emptyFilter());
	assert.deepEqual(
		plain(regions.map((r) => [r.name, r.count])),
		[
			["Japan", 40],
			["Federal (49-state)", 35],
			["California", 20],
			["Gulf states (GCC)", 5],
		],
	);
	const { countries, unmapped } = core.countryTotals(regions);
	assert.equal(countries.get("United States of America"), 55);
	assert.equal(countries.get("Japan"), 40);
	assert.deepEqual(plain(unmapped.map((r) => r.name)), ["Gulf states (GCC)"]);
});

test("models by year keep the fixed model order and fill missing years with zero", () => {
	const { years, series } = core.modelsByYear(STATS, core.emptyFilter());
	assert.deepEqual(plain(years), ["1991", "1992", "1993"]);
	assert.deepEqual(plain(series), [
		{ key: "3000GT", data: [0, 20, 30] },
		{ key: "Stealth", data: [0, 0, 10] },
		{ key: "GTO", data: [30, 10, 0] },
	]);
});

test("regions by year fold the tail into Other", () => {
	const { series, slots } = core.regionsByYear(STATS, core.emptyFilter(), 2);
	assert.deepEqual(plain([...slots]), [
		["Japan", 0],
		["Federal (49-state)", 1],
	]);
	assert.deepEqual(
		plain(series.map((s) => [s.key, s.data])),
		[
			["Japan", [30, 10, 0]],
			["Federal (49-state)", [0, 0, 35]],
			["Other", [0, 20, 5]],
		],
	);
});

test("a region keeps its colour slot whatever the filter", () => {
	const filtered = core.regionsByYear(STATS, { ...core.emptyFilter(), region: ["Federal (49-state)"] }, 2);
	assert.deepEqual(plain(filtered.series.map((s) => s.key)), ["Federal (49-state)"]);
	assert.equal(filtered.slots.get("Federal (49-state)"), 1);
	const tail = core.regionsByYear(STATS, { ...core.emptyFilter(), region: ["California"] }, 2);
	assert.deepEqual(plain(tail.series.map((s) => s.key)), ["Other"]);
});

test("facet totals and shares by year", () => {
	const paints = core.facetTotals(STATS, "paint", core.emptyFilter());
	assert.deepEqual(plain(paints.map((p) => [p.value.code, p.count])), [
		["T87", 55],
		["R25", 35],
		["", 10],
	]);
	const share = core.facetShareByYear(STATS, "paint", core.emptyFilter(), 1);
	assert.deepEqual(plain(share.series.map((s) => s.value.name)), ["Fiji Blue", "Other"]);
	assert.deepEqual(plain(share.series[0].share.map(Math.round)), [100, 67, 13]);
	const top = core.topWithOther(paints, 1);
	assert.equal(top.length, 2);
	assert.equal(top[1].count, 45);
	assert.ok(top[1].other);
});

test("build months run in calendar order per model", () => {
	const { months, series } = core.monthsByModel(STATS, core.emptyFilter());
	assert.deepEqual(plain(months), ["1990-11", "1992-03"]);
	assert.deepEqual(plain(series.find((s) => s.key === "GTO").data), [30, 10]);
	assert.deepEqual(plain(series.find((s) => s.key === "Stealth").data), [0, 0]); // its month isn't recorded
});

test("the colour matrix pairs the top paints and interiors, skipping unrecorded colours", () => {
	const m = core.colourMatrix(STATS, core.emptyFilter(), 5, 5);
	assert.deepEqual(plain(m.paints), ["T87", "R25"]);
	assert.deepEqual(plain(m.interiors), ["12A"]);
	assert.deepEqual(plain(m.cells), [
		[0, 0, 55],
		[1, 0, 35],
	]);
	assert.equal(m.max, 55);
});

test("the market tree nests regions and models", () => {
	const tree = plain(core.marketTree(STATS, core.emptyFilter()));
	assert.deepEqual(
		tree.map((m) => [m.name, m.value]),
		[
			["North America", 55],
			["Japan", 40],
			["Export", 5],
		],
	);
	assert.deepEqual(tree[0].children[0].children.map((c) => c.name), ["3000GT", "Stealth"]);
});

test("rarity tiers run rarest first", () => {
	assert.deepEqual(plain(core.rarityTotals(STATS, core.emptyFilter()).map((r) => r.value.code)), ["one_of_one", "common"]);
});

test("the address round-trips a filter and ignores what isn't one", () => {
	const state = { model: ["3000GT", "GTO"], market: [], region: ["California"], from: "1992", to: "" };
	const query = core.stateQuery(state);
	assert.equal(query, "?model=3000GT&model=GTO&region=California&from=1992");
	assert.deepEqual(plain(core.parseState(query)), state);
	assert.deepEqual(plain(core.parseState("?from=19x2&to=<b>&model=,,")), plain(core.emptyFilter()));
	assert.equal(core.stateQuery(core.emptyFilter()), "");
});

test("CSV cells are quoted and never run as formulas", () => {
	assert.equal(core.csvCell('a "b", c'), '"a ""b"", c"');
	assert.equal(core.csvCell("=HYPERLINK(1)"), "'=HYPERLINK(1)");
	assert.equal(core.csvCell("-1"), "'-1");
	assert.equal(core.csvCell(42), "42");
	assert.equal(core.csvCell(null), "");
	assert.equal(core.toCsv(["a", "b"], [[1, 2]]), "a,b\r\n1,2");
});

test("tables list a facet's values with shares, or every filtered car group", () => {
	const table = core.facetTable(STATS, "paint", core.emptyFilter());
	assert.deepEqual(plain(table.header), ["Code", "Name", "Cars", "Share"]);
	assert.deepEqual(plain(table.rows[0]), ["T87", "Fiji Blue", 55, "55%"]);
	const raw = core.rawTable(STATS, "paint", { ...core.emptyFilter(), model: ["Stealth"] });
	assert.deepEqual(plain(raw.rows), [["1993", "Stealth", "Federal (49-state)", "North America", "", "Not recorded", 10]]);
});

test("labels and percentages", () => {
	assert.equal(core.label({ code: "T87", name: "Fiji Blue" }), "T87 Fiji Blue");
	assert.equal(core.label({ name: "6-speed manual" }), "6-speed manual");
	assert.equal(core.label({ paint: "T87", interior: "" }), "T87 / —");
	assert.equal(core.percent(1, 300), "0.3%");
	assert.equal(core.percent(0, 0), "0%");
	assert.equal(core.modelSlot("Stealth"), 1);
	assert.equal(core.modelSlot("Diamante"), 3);
});

test("highlights name the commonest and scarcest paint, the regions at either end, and the generations", () => {
	const h = core.highlights(STATS, core.emptyFilter());
	assert.equal(h.commonestPaint.value.code, "T87");
	assert.deepEqual(plain(h.scarcestPaints.map((e) => e.value.code)), ["R25"]);
	assert.equal(h.mostRegion.name, "Japan");
	assert.equal(h.fewestRegion.name, "Gulf states (GCC)");
	assert.deepEqual(plain(h.generations.map((g) => [g.value.name, g.count])), [
		["1st generation (to 1993)", 60],
		["2nd generation (1994 on)", 40],
	]);
	const one = core.highlights(STATS, { ...core.emptyFilter(), region: ["Japan"] });
	assert.equal(one.fewestRegion, null); // one region has no "fewest"
});

test("option items are shared out against each region's cars with option contents on record", () => {
	const m = core.optionsByRegion(STATS, core.emptyFilter(), 10);
	assert.deepEqual(plain(m.regions.map((r) => [r.name, r.of])), [
		["Japan", 40],
		["Gulf states (GCC)", 5],
	]);
	assert.deepEqual(plain(m.items.map((e) => e.value.code)), ["K03", "S11"]);
	assert.deepEqual(plain(m.cells.sort()), [
		[0, 0, 50, 20],
		[1, 0, 10, 4],
		[1, 1, 100, 5],
	]);
	assert.deepEqual(plain(core.itemByRegion(STATS, core.emptyFilter(), 1)), [
		{ name: "Gulf states (GCC)", of: 5, count: 5 },
		{ name: "Japan", of: 40, count: 4 },
	]);
});

test("search keeps rows matching every word; sorting is numeric for numbers", () => {
	const rows = [
		["T87", "Fiji Blue", 55],
		["R25", "Morocco Red", 35],
		["W75", "Pure White", 120],
	];
	assert.deepEqual(plain(core.searchRows(rows, "blue fiji")), [rows[0]]);
	assert.deepEqual(plain(core.searchRows(rows, "  ")), plain(rows));
	assert.deepEqual(plain(core.sortRows(rows, 2, true).map((r) => r[0])), ["W75", "T87", "R25"]);
	assert.deepEqual(plain(core.sortRows(rows, 1, false).map((r) => r[0])), ["T87", "R25", "W75"]);
});

test("a search request carries the page filters and the form's text and codes", () => {
	const filter = { model: ["GTO"], market: [], region: ["Japan"], from: "1992", to: "" };
	assert.equal(
		core.searchParams(filter, { q: " Z16A-001 ", paint: "T87", interior: "", option: "" }, 1),
		"q=Z16A-001&paint=T87&model=GTO&region=Japan&from=1992",
	);
	assert.equal(core.searchParams(core.emptyFilter(), { q: "JA3" }, 3), "q=JA3&page=3");
});

test("build dates read as month and period, or month only", () => {
	assert.equal(core.builtLabel("92032"), "1992-03, 2nd period");
	assert.equal(core.builtLabel("94070"), "1994-07");
	assert.equal(core.builtLabel("00011"), "2000-01, 1st period");
	assert.equal(core.builtLabel(""), "");
	assert.equal(core.builtLabel("EXT"), "");
});

test("a found car's cells follow the columns, VIN uncensored", () => {
	const car = { vin: "JA3AM84J3NY000001", model_year: "1992", line: "Mitsubishi 3000GT VR-4", region: "California", paint: "T87", interior: "12A", option: "XA1", built: "91092", provenance: "CAPS 1999" };
	const cells = plain(core.carCells(car));
	assert.equal(cells.length, core.SEARCH_COLUMNS.length);
	assert.deepEqual(cells, ["JA3AM84J3NY000001", "1992", "Mitsubishi 3000GT VR-4", "California", "T87", "12A", "XA1", "1991-09, 2nd period", "CAPS 1999"]);
});
