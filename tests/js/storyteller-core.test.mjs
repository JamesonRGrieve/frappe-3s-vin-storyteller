// SPDX-License-Identifier: AGPL-3.0-or-later
// Unit tests for the front end's pure helpers. Run: node --test tests/js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../vin_storyteller/public/js/storyteller-core.js", import.meta.url), "utf8");
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const core = sandbox.VinStorytellerCore;

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
