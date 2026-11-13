// SPDX-License-Identifier: AGPL-3.0-or-later
// Unit tests for the front end's pure helpers. Run: node --test tests/js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../vin_storyteller/public/js/storyteller-core.js", import.meta.url), "utf8");
const sandbox = { URLSearchParams };
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const core = sandbox.VinStorytellerCore;
const plain = (value) => JSON.parse(JSON.stringify(value));

test("exposes a frozen helper set", () => {
	assert.ok(Object.isFrozen(core));
	assert.equal(typeof core.badgeParts, "function");
});

test("normalizeVin strips whitespace and upper-cases", () => {
	assert.equal(core.normalizeVin(" ja3am84j3 ny012345\n"), "JA3AM84J3NY012345");
	assert.equal(core.normalizeVin(null), "");
	assert.equal(core.normalizeVin(undefined), "");
});

test("isValidVin accepts 17 VIN characters and rejects I, O, Q and wrong lengths", () => {
	assert.ok(core.isValidVin("JA3AM84J3NY012345"));
	for (const bad of ["", "JA3AM84J3NY01234", "JA3AM84J3NY0123456", "JA3AM84J3NY01234I", "JA3AM84J3NY01234O", "JA3AM84J3NY01234Q", "ja3am84j3ny012345"]) {
		assert.equal(core.isValidVin(bad), false, bad);
	}
});

test("isSafeUrl allows only plain http(s) links", () => {
	assert.ok(core.isSafeUrl("https://bringatrailer.com/listing/x"));
	assert.ok(core.isSafeUrl("http://example.com/a?b=c"));
	for (const bad of [null, undefined, 42, "", "javascript:alert(1)", "data:text/html,x", "ftp://x", "https://a b", 'https://x"y']) {
		assert.equal(core.isSafeUrl(bad), false, String(bad));
	}
});

test("numbers and positions use Canadian English grouping", () => {
	assert.equal(core.formatNumber(22104), "22,104");
	assert.equal(core.positionText({ position: 9876, total: 22104 }), "No. 9,876 of 22,104");
});

test("codedText and provenanceText", () => {
	assert.equal(core.codedText({ code: "T87", description: "Fiji Blue" }), "Fiji Blue · T87");
	assert.equal(core.codedText({ code: "47E", description: "MISSING" }), "Not yet decoded · 47E");
	assert.equal(
		core.provenanceText("CAPS 1999"),
		"Production record source: Mitsubishi's factory production record (the 1999 CAPS export).",
	);
	assert.match(core.provenanceText("ASA Japan 2008"), /every Japanese-market GTO/);
	assert.equal(core.provenanceText("owner"), "Production record source: owner.");
});

test("badgeParts names the tier and the run", () => {
	assert.deepEqual(
		{ ...core.badgeParts({ tier: "one_of_one", total: 1, description: "in this exact specification" }) },
		{ tier: "One of one", count: "1 of 1", scope: "in this exact specification" },
	);
	assert.equal(core.badgeParts({ tier: "sub25", total: 1234, description: "" }).count, "1 of 1,234");
	assert.equal(core.badgeParts({ tier: "sub100", total: 60, description: "" }).tier, "Fewer than 100");
	assert.equal(core.badgeParts({ tier: "mystery", total: 3, description: "" }).tier, "mystery");
});

test("historyParts builds meta, keeps safe links and drops unsafe ones", () => {
	const parts = core.historyParts({
		kind: "auction",
		title: "Sold at auction",
		url: "https://example.com/lot/1",
		date: "2021-05-01",
		source: "BaT",
		provenance: "3S Hub",
	});
	assert.deepEqual({ ...parts }, {
		meta: "2021-05-01 · Auction",
		title: "Sold at auction",
		url: "https://example.com/lot/1",
		source: "Source: BaT · Added by: 3S Hub",
	});
	const unsafe = core.historyParts({ kind: "weird", title: "x", url: "javascript:alert(1)", date: null, source: null, provenance: "op" });
	assert.equal(unsafe.url, null);
	assert.equal(unsafe.meta, "Record");
	assert.equal(unsafe.source, "Added by: op");
});

test("timelineText tells when the year and the model began", () => {
	const text = core.timelineText({
		model_year: "1992",
		vehicle_name: "1992 Mitsubishi 3000GT VR-4",
		year_started: "the 2nd production period of September, 1991",
		model_started: "the 3rd production period of September, 1991",
	});
	assert.match(text, /^Production for the 1992 model year started in the 2nd production period of September, 1991/);
	assert.match(text, /first 1992 Mitsubishi 3000GT VR-4 came off the line in the 3rd production period/);
});

test("vinCheck counts characters and is ready only at 17 valid characters", () => {
	assert.deepEqual({ ...core.vinCheck("") }, { count: "0 / 17", state: "empty", ready: false, message: "" });
	assert.deepEqual({ ...core.vinCheck("ja3am") }, { count: "5 / 17", state: "typing", ready: false, message: "" });
	assert.deepEqual({ ...core.vinCheck(" ja3am84j3 ny012345") }, { count: "17 / 17", state: "ready", ready: true, message: "" });
});

test("vinCheck explains look-alike letters, other characters and overlong input", () => {
	assert.match(core.vinCheck("JA3AMO").message, /never contain I, O or Q/);
	assert.equal(core.vinCheck("JA3AMO").state, "bad");
	assert.match(core.vinCheck("JA3-AM").message, /letters and numbers only/);
	assert.match(core.vinCheck("JA3AM84J3NY0123456").message, /more than 17/);
	assert.equal(core.vinCheck("JA3AM84J3NY0123456").ready, false);
});

test("normalizeName collapses whitespace and refuses blank or overlong names", () => {
	assert.equal(core.normalizeName("  Trevor   Macken "), "Trevor Macken");
	assert.equal(core.normalizeName("   "), "");
	assert.equal(core.normalizeName(null), "");
	assert.equal(core.normalizeName("x".repeat(101)), "");
});

test("JDM GTO chassis numbers are recognised, partial ones are left alone", () => {
	assert.ok(core.isChassisNumber("Z16A-0011452"));
	assert.ok(core.isChassisNumber(" z15a0200248 "));
	assert.equal(core.isChassisNumber("Z17A-0011452"), false);
	assert.deepEqual({ ...core.vinCheck("Z16A-0011452") }, { count: "JDM chassis", state: "ready", ready: true, message: "" });
	assert.equal(core.vinCheck("Z16A-00").state, "typing");
	assert.equal(core.vinCheck("Z16A-00").message, "");
});

test("a partial story (not in the factory export) says so and shows unknown codes", () => {
	assert.equal(core.codedText({ code: "", description: "MISSING" }), "Not known");
	assert.match(core.builtText({ partial: true, provenance: "Price label" }), /on record from Price label/);
	assert.equal(core.builtText({ partial: false, built: "the 1st production period of May, 1996" }), "Built in the 1st production period of May, 1996.");
});

test("provenanceText names both factory exports", () => {
	assert.match(core.provenanceText("CAPS 1999"), /CAPS export/);
	assert.match(core.provenanceText("CAPS 2004"), /2004 CAPS build/);
	assert.equal(core.provenanceText("Canadian price label"), "Production record source: Canadian price label.");
});

test("breakdownParts says how many cars share something, and of which models", () => {
	const parts = core.breakdownParts({
		scope: "colour",
		total: 1236,
		description: "in the same exterior colour, every year",
		by_model: [
			{ model: "3000GT", count: 800 },
			{ model: "Stealth", count: 400 },
			{ model: "GTO", count: 36 },
		],
	});
	assert.deepEqual(
		{ ...parts },
		{
			total: "1,236",
			label: "cars in the same exterior colour, every year",
			models: "of which 800 3000GTs, 400 Stealths and 36 GTOs",
		},
	);
	const two = core.breakdownParts({ total: 2, description: "x", by_model: [{ model: "GTO", count: 1 }, { model: "Stealth", count: 1 }] });
	assert.equal(two.models, "of which 1 GTO and 1 Stealth");
	assert.equal(core.breakdownParts({ total: 5, description: "x", by_model: [{ model: "GTO", count: 5 }] }).models, "all GTOs");
	const one = core.breakdownParts({ total: 1, description: "built in the same production period", by_model: [{ model: "GTO", count: 1 }] });
	assert.deepEqual({ ...one }, { total: "1", label: "car built in the same production period", models: "" });
});

test("equipmentItemsText lists what an option code fits", () => {
	assert.deepEqual(
		[...core.equipmentItemsText([{ code: "J50", description: "CD AUTO CHANGER" }, { code: "ZZ1", description: "MISSING" }])],
		["CD AUTO CHANGER · J50", "Not yet decoded · ZZ1"],
	);
});

test("export frame numbers are accepted and named", () => {
	assert.ok(core.isFrameNumber("DMNZ16APY00001"));
	assert.ok(core.isFrameNumber("dmnz16a-py00001"));
	assert.ok(core.isFrameNumber("MNZ16AVY000101"));
	assert.equal(core.isFrameNumber("DMNZ16APY0000"), false);
	assert.equal(core.isFrameNumber("JA3AM84J3NY012345"), false);
	assert.equal(core.vinCheck("DMNZ16APY00001").ready, true);
	assert.equal(core.keyLabel("JMAMJZ16AVY000101"), "VIN");
	assert.equal(core.keyLabel("Z16A-0300250"), "Chassis number");
	assert.equal(core.keyLabel("DMNZ16APY00001"), "Frame number");
});

test("swatches show when the record has either code, each with its code and description", () => {
	const story = { manufacturer: "Dodge", exterior: { code: "R25", description: "Morocco Red Mica" }, interior: { code: "", description: "" } };
	assert.equal(core.swatchesShown(story), true);
	assert.equal(core.swatchesShown({ exterior: { code: "", description: "" }, interior: { code: "", description: "" } }), false);
	assert.equal(core.swatchesShown({}), false);
	assert.deepEqual(JSON.parse(JSON.stringify(core.swatchRequests(story))), [
		{ kind: "paint", code: "R25", description: "Morocco Red Mica", make: "Dodge" },
		{ kind: "interior", code: "", description: "" },
	]);
	assert.deepEqual(JSON.parse(JSON.stringify(core.swatchRequests({}))), [
		{ kind: "paint", code: "", description: "", make: "" },
		{ kind: "interior", code: "", description: "" },
	]);
});

test("featuresText says a feature came from the factory", () => {
	assert.deepEqual([...core.featuresText(["Headlamp washers"])], ["Headlamp washers · fitted at the factory (parts catalogue)"]);
	assert.deepEqual([...core.featuresText(undefined)], []);
});

test("a paint page names its other codes", () => {
	const text = core.codeNamesText({ names: [{ manufacturer: "Mitsubishi", name: "Fiji Blue Metallic" }], same_paint: ["TA7"] });
	assert.equal(text, "Mitsubishi: Fiji Blue Metallic · Also recorded as TA7");
});

test("a VIN handed in the address is taken only when it is a VIN, chassis or frame number", () => {
	assert.equal(core.vinFromAddress("?vin=ja3am84j3ny000001"), "JA3AM84J3NY000001");
	assert.equal(core.vinFromAddress("?vin=Z16A-0014160"), "Z16A-0014160");
	assert.equal(core.vinFromAddress("?vin=<script>"), "");
	assert.equal(core.vinFromAddress("?vin=JA3AM84J3NY00000I"), "");
	assert.equal(core.vinFromAddress(""), "");
});

// Card 391: a story's counts open the stats page's search for exactly those cars.
test("a story links to its spec twins and to the cars built in its period and month", () => {
	const story = {
		model_year: "1992",
		line_code: "VR",
		series: "us",
		built_code: "92031",
		exterior: { code: "T87" },
		interior: { code: "12A" },
		equipment: { code: "A07" },
	};
	assert.equal(
		core.exploreHref(story, "twins"),
		"/storyteller/stats?from=1992&to=1992&find_line=VR&find_paint=T87&find_interior=12A&find_option=A07&find_exact=1&find_sort=vin#find",
	);
	assert.equal(
		core.exploreHref(story, "period"),
		"/storyteller/stats?find_built_from=92031&find_built_to=92031&find_series=us&find_sort=built#find",
	);
	assert.equal(
		core.exploreHref(story, "month"),
		"/storyteller/stats?find_built_from=9203&find_built_to=9203&find_series=us&find_sort=built#find",
	);
	assert.equal(core.exploreHref({ ...story, partial: true }, "twins"), null);
	assert.equal(core.exploreHref({ ...story, built_code: "" }, "period"), null);
	assert.equal(core.exploreHref({ ...story, interior: { code: "<x>" } }, "twins"), null);
});

// Card 391: the colour chart.
test("model years read as calendar ranges", () => {
	assert.equal(core.yearsText(["00", "91", "92", "95", "96", "97"]), "1991–1992, 1995–1997, 2000");
	assert.equal(core.yearsText(["94"]), "1994");
	assert.equal(core.yearsText([]), "");
});

test("the chart folds a paint's A form into its plain code and orders cards", () => {
	const data = {
		paint: {
			W75: { mitsubishi_name: "Glacier White Pearl", dodge_name: "Galaxy White Pearl", finish: "pearl", model_years: ["91", "92", "95"], hex: "#E5EDE3", also_codes: ["WA5"] },
			WA5: { mitsubishi_name: "Glacier White Pearl", same_paint_as: "W75", hex: "#E5EDE3" },
			R71: { mitsubishi_name: "Caracas Red", dodge_name: "Caracas Red", finish: "solid", model_years: ["91"], hex: "#B01020" },
		},
	};
	const codes = [
		{ code: "WA5", description: "Glacier White Pearl", total: 10, by_model: [{ model: "3000GT", count: 10 }] },
		{ code: "W75", description: "Glacier White Pearl", total: 5, by_model: [{ model: "3000GT", count: 3 }, { model: "Stealth", count: 2 }] },
		{ code: "R71", description: "Caracas Red", total: 12, by_model: [{ model: "Stealth", count: 12 }] },
		{ code: "X99", description: "MISSING", total: 1, by_model: [{ model: "GTO", count: 1 }] },
	];
	const cards = plain(core.chartEntries("paint", codes, data));
	assert.deepEqual(cards.map((c) => c.code), ["W75", "R71", "X99"]);
	assert.deepEqual(cards[0].also, ["WA5"]);
	assert.equal(cards[0].total, 15);
	assert.deepEqual(cards[0].by_model, [{ model: "3000GT", count: 13 }, { model: "Stealth", count: 2 }]);
	assert.equal(cards[1].dodge_name, ""); // the same name under both brands isn't repeated
	assert.deepEqual(plain(core.chartEntries("paint", codes, data, "code")).map((c) => c.code), ["R71", "W75", "X99"]);
	assert.deepEqual(plain(core.chartEntries("paint", codes, data, "colour")).map((c) => c.code), ["W75", "R71", "X99"]);
	const parts = plain(core.chartCardParts(cards[0]));
	assert.deepEqual(parts, {
		codes: "W75 / WA5",
		name: "Glacier White Pearl",
		dodge: "Dodge: Galaxy White Pearl",
		detail: "Pearl",
		years: "1991–1992, 1995",
		cars: "15 cars",
		models: "13 3000GTs and 2 Stealths",
	});
	assert.equal(core.chartCardParts(cards[2]).name, "Not yet decoded");
});

test("an unnamed interior is titled by its colour and material", () => {
	const data = { interior: { "14T": { description: "", colour: "Ivory", material: "leather", model_years: ["91"] } } };
	const [card] = plain(core.chartEntries("interior", [{ code: "14T", description: "MISSING", total: 3, by_model: [{ model: "3000GT", count: 3 }] }], data));
	const parts = core.chartCardParts(card);
	assert.equal(parts.name, "Ivory leather");
	assert.equal(parts.detail, "");
});

// Card 391: the printable build sheet.
test("a build sheet's reference comes from the record it prints, and changes with it", () => {
	const story = {
		vin: "JA3XE74C2MY001329", model_year: "1991", line_code: "VR", classification: { code: "MNGFL7M" },
		exterior: { code: "WA5" }, interior: { code: "14U" }, equipment: { code: "A07" }, built_code: "90071", provenance: "CAPS 1999",
	};
	assert.equal(core.referenceSource(story), "3shub-build-sheet-v1|JA3XE74C2MY001329|1991|VR|MNGFL7M|WA5|14U|A07|90071|CAPS 1999");
	assert.notEqual(core.referenceSource(story), core.referenceSource({ ...story, interior: { code: "14W" } }));
	assert.equal(core.formatReference("1a2b3c4d5e6f"), "3SH-1A2B-3C4D");
	assert.equal(core.formatReference("xyz"), "");
	assert.equal(core.storyAddress("https://3shub.ca/", "JA3XE74C2MY001329"), "https://3shub.ca/storyteller?vin=JA3XE74C2MY001329");
});

test("a build sheet prints the factory record's rows", () => {
	const story = {
		vin: "JA3XE74C2MY001329", model_year: "1991", manufacturer: "Mitsubishi", model: "3000GT", trim: "VR-4",
		classification: { code: "MNGFL7M", description: "ULTIMATE LINE,5FM/TR" },
		exterior: { code: "WA5", description: "Glacier White Pearl" }, interior: { code: "14U", description: "MISSING" },
		equipment: { code: "A07", description: "MISSING" }, equipment_items: [{ code: "K03", description: "LEATHER SEAT & ROOM TRIM" }],
		built: "the 1st production period of July, 1990", provenance: "CAPS 1999",
		in_year: { position: 345, total: 27207 }, in_model: { position: 155, total: 3693 },
		in_colour: { position: 1, total: 760 }, among_identical: { position: 1, total: 20 },
	};
	const rows = plain(core.sheetRows(story));
	assert.deepEqual(rows.slice(0, 4), [
		["VIN", "JA3XE74C2MY001329"],
		["Model year", "1991"],
		["Model", "Mitsubishi 3000GT VR-4"],
		["Grade", "ULTIMATE LINE,5FM/TR · MNGFL7M"],
	]);
	assert.deepEqual(rows.find((r) => r[0] === "Option contents"), ["Option contents", "LEATHER SEAT & ROOM TRIM · K03"]);
	assert.deepEqual(rows.find((r) => r[0] === "Among identical cars"), ["Among identical cars", "No. 1 of 20"]);
	assert.ok(!plain(core.sheetRows({ ...story, partial: true })).some((r) => r[0] === "In the model year"));
});
