// SPDX-License-Identifier: AGPL-3.0-or-later
// Unit tests for the per-code pages' pure helpers (card 330). Run: node --test 'tests/js/*.test.mjs'
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

test("codeHref writes query addresses by default and path addresses on request", () => {
	assert.equal(core.codeHref("paint", "t87"), "/storyteller/paint?code=T87");
	assert.equal(core.codeHref("interior", " 12a ", "Z16A"), "/storyteller/interior?code=12A");
	assert.equal(core.codeHref("option", "302", "z16a"), "/storyteller/option?model=Z16A&code=302");
	assert.equal(core.codeHref("paint", "T87", "", "path"), "/storyteller/paint/T87");
	assert.equal(core.codeHref("option", "302", "Z16A", "path"), "/storyteller/option/Z16A/302");
	assert.equal(core.indexHref("option"), "/storyteller/option");
});

test("codeHref has no address for what is no code page", () => {
	for (const [kind, code, model] of [
		["paint", "", ""],
		["paint", "EXT", ""],
		["interior", "INT", ""],
		["option", "EQU", "Z16A"],
		["option", "302", ""],
		["option", "302", "Z16"],
		["paint", "T8&7", ""],
		["paint", "<b>", ""],
		["wheels", "T87", ""],
		["paint", null, null],
	]) {
		assert.equal(core.codeHref(kind, code, model), null, `${kind} ${code} ${model}`);
	}
});

test("parseCodeRoute reads both address styles", () => {
	assert.deepEqual(plain(core.parseCodeRoute("/storyteller/paint", "?code=t87")), { kind: "paint", code: "T87", model: "" });
	assert.deepEqual(plain(core.parseCodeRoute("/storyteller/paint/T87", "")), { kind: "paint", code: "T87", model: "" });
	assert.deepEqual(plain(core.parseCodeRoute("/storyteller/option/", "?model=Z16A&code=302")), {
		kind: "option",
		code: "302",
		model: "Z16A",
	});
	assert.deepEqual(plain(core.parseCodeRoute("/storyteller/option/z16a/302", "")), {
		kind: "option",
		code: "302",
		model: "Z16A",
	});
	assert.deepEqual(plain(core.parseCodeRoute("/storyteller/interior/12A/", "?code=99Z")), {
		kind: "interior",
		code: "12A",
		model: "",
	});
});

test("parseCodeRoute: an index, an invalid code, and not a code page", () => {
	assert.deepEqual(plain(core.parseCodeRoute("/storyteller/interior", "")), { kind: "interior", code: "", model: "" });
	for (const [path, search] of [
		["/storyteller/paint", "?code=EXT"],
		["/storyteller/paint/%E0%A4%A", ""],
		["/storyteller/option", "?code=302"],
		["/storyteller/option/Z16A", ""],
		["/storyteller/paint", "?code=<script>"],
	]) {
		assert.deepEqual(plain(core.parseCodeRoute(path, search)), { kind: path.split("/")[2], code: "", model: "", invalid: true }, path + search);
	}
	assert.equal(core.parseCodeRoute("/storyteller", ""), null);
	assert.equal(core.parseCodeRoute("/storyteller/wheels/T87", ""), null);
	assert.equal(core.parseCodeRoute("/about", "?code=T87"), null);
});

test("codeTitle and codeNamesText", () => {
	const paint = { kind: "paint", code: "T87", model_code: "", description: "Fiji Blue", names: [{ manufacturer: "Mitsubishi", name: "Fiji Blue" }, { manufacturer: "Dodge", name: "Bright Blue" }] };
	assert.equal(core.codeTitle(paint), "Paint T87 · Fiji Blue");
	assert.equal(core.codeNamesText(paint), "Mitsubishi: Fiji Blue · Dodge: Bright Blue");
	const interior = { kind: "interior", code: "04H", model_code: "", description: "MISSING", names: [] };
	assert.equal(core.codeTitle(interior), "Interior 04H");
	assert.match(core.codeNamesText(interior), /^Not yet decoded/);
	assert.equal(core.codeNamesText({ ...interior, description: "Grey cloth" }), "Grey cloth");
	assert.equal(core.codeTitle({ kind: "option", code: "302", model_code: "Z16A", description: "MISSING", names: [] }), "Option 302 · Z16A");
});

test("spanText and shareText", () => {
	const page = { first_built: "the 1st production period of May, 1992", last_built: "the 3rd production period of July, 2000" };
	assert.equal(core.spanText(page), "The first was built in the 1st production period of May, 1992, and the last in the 3rd production period of July, 2000.");
	assert.equal(core.spanText({ first_built: "x", last_built: "x" }), "Every one was built in x.");
	assert.equal(core.spanText({ first_built: "", last_built: "" }), "");
	assert.equal(core.shareText(16889, 25626), "66%");
	assert.equal(core.shareText(43, 25626), "0.2%");
	assert.equal(core.shareText(1, 0), "");
});

test("pairingText, fitParts and indexEntryParts", () => {
	assert.equal(core.pairingText({ code: "12A", description: "Grey", count: 5 }), "Grey · 12A");
	assert.equal(core.pairingText({ code: "39H", description: "MISSING", count: 5 }), "39H");
	assert.equal(core.pairingText({ code: "", description: "MISSING", count: 1 }), "Not on record");
	assert.deepEqual(
		plain(
			core.fitParts({
				classification: { code: "MNGF", description: "GTO TWIN-TURBO,5FM/T" },
				model_year: "1992",
				items: [{ code: "K03", description: "LEATHER SEAT & ROOM TRIM" }, { code: "ZZ1", description: "MISSING" }],
				cars: 1204,
				source: "ASA Japan 2008",
			}),
		),
		{ grade: "1992 · GTO TWIN-TURBO,5FM/T · MNGF", items: ["LEATHER SEAT & ROOM TRIM · K03", "Not yet decoded · ZZ1"], cars: "1,204 cars built so" },
	);
	assert.deepEqual(
		plain(core.indexEntryParts({ code: "302", model_code: "Z16A", description: "MISSING", total: 2699, by_model: [{ model: "GTO", count: 2699 }] })),
		{ code: "302 · Z16A", description: "Not yet decoded", total: "2,699", models: "2,699 GTOs" },
	);
});
