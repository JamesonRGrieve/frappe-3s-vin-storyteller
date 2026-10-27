// SPDX-License-Identifier: AGPL-3.0-or-later
// Unit tests for the swatches' pure logic. Run: node --test 'tests/js/*.test.mjs'
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../../vin_storyteller/public/js/swatch-core.js", import.meta.url), "utf8");
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const core = sandbox.VinSwatchCore;
const plain = (value) => JSON.parse(JSON.stringify(value));
const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} ≉ ${b}`);

test("exposes a frozen helper set", () => {
	assert.ok(Object.isFrozen(core));
	assert.ok(Object.isFrozen(core.FINISHES.pearl));
});

test("parseHex and toHex round-trip and reject anything but 6-digit hex", () => {
	assert.deepEqual(plain(core.parseHex("#FF8000")), { r: 1, g: 128 / 255, b: 0 });
	assert.deepEqual(plain(core.parseHex("ff8000")), plain(core.parseHex("#FF8000")));
	assert.equal(core.toHex(core.parseHex("#1a2b3c")), "#1A2B3C");
	for (const bad of [null, undefined, "", "#FFF", "#GGGGGG", "MISSING", "#1234567"]) {
		assert.equal(core.parseHex(bad), null, String(bad));
	}
	assert.equal(core.toHex({ r: 2, g: -1, b: 0.5 }), "#FF0080");
});

test("sRGB transfer functions invert each other and hit known points", () => {
	near(core.srgbToLinear(0), 0);
	near(core.srgbToLinear(1), 1);
	near(core.srgbToLinear(0.5), 0.214041, 1e-5);
	for (const v of [0, 0.02, 0.2, 0.5, 0.9, 1]) near(core.linearToSrgb(core.srgbToLinear(v)), v);
});

test("mix works in linear light; luminance follows WCAG", () => {
	const black = { r: 0, g: 0, b: 0 };
	const white = { r: 1, g: 1, b: 1 };
	assert.equal(core.toHex(core.mix(black, white, 0)), "#000000");
	assert.equal(core.toHex(core.mix(black, white, 1)), "#FFFFFF");
	// Half-way in linear light is brighter than sRGB 0.5.
	assert.equal(core.toHex(core.mix(black, white, 0.5)), "#BCBCBC");
	near(core.luminance(white), 1);
	near(core.luminance(black), 0);
	near(core.luminance(core.parseHex("#FF0000")), 0.2126);
});

test("HSL round-trips and rotates hue", () => {
	for (const hex of ["#4F8EBF", "#AF1F41", "#808080", "#00FF00"]) {
		assert.equal(core.toHex(core.hslToRgb(core.rgbToHsl(core.parseHex(hex)))), hex);
	}
	assert.equal(core.toHex(core.rotateHue(core.parseHex("#FF0000"), 120)), "#00FF00");
	assert.equal(core.toHex(core.rotateHue(core.parseHex("#FF0000"), -120)), "#0000FF");
});

test("finishFromName reads Mitsubishi's Mica and Dodge's Pearl/Metallic", () => {
	assert.equal(core.finishFromName("Danube Blue Mica"), "pearl");
	assert.equal(core.finishFromName("Galaxy White Pearl"), "pearl");
	assert.equal(core.finishFromName("Fiji Blue Metallic"), "metallic");
	assert.equal(core.finishFromName("Caracas Red"), "solid");
	assert.equal(core.finishFromName("MISSING"), "");
	assert.equal(core.finishFromName(""), "");
	assert.equal(core.finishFromName(null), "");
});

test("paintSwatch uses only a published hex; anything else is the neutral 'not on file' panel", () => {
	const sourced = core.paintSwatch({ hex: "#2C4F8C", finish: "pearl", name: "Danube Blue Mica", source: "https://x" }, "");
	assert.equal(sourced.status, "sourced");
	assert.equal(sourced.label, "Danube Blue Mica");
	assert.equal(core.toHex(sourced.base), "#2C4F8C");
	assert.equal(sourced.params, core.FINISHES.pearl);
	assert.ok(sourced.flake, "a pearl gets a derived interference colour");

	const published = core.paintSwatch({ hex: "#101010", flake_hex: "#C0A060", finish: "pearl" }, "Solano Black Pearl");
	assert.equal(core.toHex(published.flake), "#C0A060");

	for (const entry of [undefined, null, { name: "Fire Storm", finish: "solid" }, { hex: "MISSING" }]) {
		const missing = core.paintSwatch(entry, "Fire Storm");
		assert.equal(missing.status, "missing");
		assert.equal(missing.label, core.NOT_ON_FILE);
		assert.equal(core.toHex(missing.base), core.NEUTRAL);
		assert.equal(missing.flake, null);
		assert.equal(core.shaderMode(missing), core.MODES.plain);
	}
});

test("paintSwatch: the story's description names it and sets the finish when it says so", () => {
	const s = core.paintSwatch({ hex: "#3060A0", finish: "solid", name: "Old" }, "Fiji Blue Metallic");
	assert.equal(s.name, "Fiji Blue Metallic");
	assert.equal(s.finish, "metallic");
	const undecoded = core.paintSwatch({ hex: "#3060A0", finish: "pearl", name: "Table name" }, "MISSING");
	assert.equal(undecoded.name, "Table name");
	assert.equal(undecoded.finish, "pearl");
	assert.equal(core.paintSwatch({ hex: "#3060A0" }, "").finish, "solid");
});

test("derivedFlake: metallic lifts toward white; a white pearl gets a warm tint", () => {
	const base = core.parseHex("#204080");
	assert.ok(core.luminance(core.derivedFlake(base, "metallic")) > core.luminance(base));
	const whitePearl = core.derivedFlake(core.parseHex("#F2F2F0"), "pearl");
	assert.ok(whitePearl.r > whitePearl.b, "warm");
	const blackPearl = core.derivedFlake(core.parseHex("#101010"), "pearl");
	assert.ok(core.luminance(blackPearl) < core.luminance(whitePearl), "a black pearl's tint stays darker than a white pearl's");
});

test("interiorMaterial: the description wins, then the table's decision, else unknown", () => {
	assert.deepEqual(plain(core.interiorMaterial({ material: "cloth", basis: "x" }, "Tan Leather, Power Seats")), {
		material: "leather",
		confidence: "decided",
		basis: "description",
	});
	assert.deepEqual(plain(core.interiorMaterial(null, "Charcoal Cloth, Power Seats")), {
		material: "cloth",
		confidence: "decided",
		basis: "description",
	});
	assert.deepEqual(
		plain(core.interiorMaterial({ material: "leather", confidence: "decided", basis: "K03 on all 1437 GTOs" }, "MISSING")),
		{ material: "leather", confidence: "decided", basis: "K03 on all 1437 GTOs" },
	);
	assert.equal(core.interiorMaterial({ material: "cloth" }, "").confidence, "inferred", "a table entry without one is not decided");
	const none = { material: "unknown", confidence: "", basis: "" };
	assert.deepEqual(plain(core.interiorMaterial({ material: "unknown" }, "")), none);
	assert.deepEqual(plain(core.interiorMaterial(undefined, undefined)), none);
});

test("interiorTone finds the colour word; interiorSwatch says when nothing is on file", () => {
	assert.equal(core.interiorTone("Charcoal Cloth, Power Seats").word, "charcoal");
	assert.equal(core.interiorTone("Red Leather").word, "red");
	assert.equal(core.interiorTone("Redwood"), null);
	assert.equal(core.interiorTone("MISSING"), null);

	const named = core.interiorSwatch({ material: "cloth" }, "Red Cloth, Power Seats");
	assert.equal(named.status, "named");
	assert.equal(named.material, "cloth");
	assert.equal(core.shaderMode(named), core.MODES.cloth);

	const unnamed = core.interiorSwatch({ material: "leather", basis: "K03" }, "MISSING");
	assert.equal(unnamed.status, "missing");
	assert.equal(unnamed.material, "leather");
	assert.equal(unnamed.label, core.NOT_ON_FILE);
	assert.equal(core.toHex(unnamed.base), core.NEUTRAL);
	assert.equal(core.shaderMode(unnamed), core.MODES.leather, "the texture still shows the material");
	assert.equal(core.shaderMode(core.interiorSwatch(null, "")), core.MODES.plain);
});

test("uniformsFor gives linear colours and numeric finish parameters", () => {
	const u = core.uniformsFor(core.paintSwatch({ hex: "#FFFFFF", finish: "metallic" }, ""), 5);
	assert.equal(u.mode, core.MODES.paint);
	assert.deepEqual(plain(u.base), [1, 1, 1]);
	assert.equal(u.finish.length, 4);
	assert.equal(u.surface.length, 2);
	assert.ok(u.finish.every((v) => typeof v === "number" && Number.isFinite(v)));
	assert.equal(u.seed, 5);
	assert.equal(core.uniformsFor(core.paintSwatch(null, ""), -3).seed, 994);
});

test("seedFor is stable and bounded", () => {
	assert.equal(core.seedFor("W75"), core.seedFor("W75"));
	assert.notEqual(core.seedFor("W75"), core.seedFor("WA5"));
	for (const code of ["", "R71", "X94", null]) {
		const s = core.seedFor(code);
		assert.ok(Number.isInteger(s) && s >= 0 && s < 997);
	}
});

test("staticBackground is a CSS gradient in the swatch colour", () => {
	const css = core.staticBackground(core.paintSwatch({ hex: "#AF1F41" }, ""));
	assert.match(css, /^linear-gradient\(135deg, #[0-9A-F]{6} 0%, #AF1F41 45%, #[0-9A-F]{6} 100%\)$/);
});

test("motionMode: still under reduced motion, pointer on desktop, scroll on touch", () => {
	assert.equal(core.motionMode({ reducedMotion: true, finePointer: true }), "still");
	assert.equal(core.motionMode({ reducedMotion: false, finePointer: true }), "pointer");
	assert.equal(core.motionMode({ reducedMotion: false, finePointer: false }), "scroll");
});

test("lightFromPointer maps the viewport to -1..1 and clamps", () => {
	assert.deepEqual(plain(core.lightFromPointer(0, 0, 200, 100)), { x: -1, y: -1 });
	assert.deepEqual(plain(core.lightFromPointer(100, 50, 200, 100)), { x: 0, y: 0 });
	assert.deepEqual(plain(core.lightFromPointer(400, -50, 200, 100)), { x: 1, y: -1 });
	assert.deepEqual(plain(core.lightFromPointer(1, 1, 0, 0)), plain(core.REST_LIGHT));
});

test("lightFromScroll sweeps top to bottom as the swatch crosses the viewport", () => {
	const top = core.lightFromScroll(0, 800);
	const mid = core.lightFromScroll(400, 800);
	const bottom = core.lightFromScroll(2000, 800);
	near(top.y, -1);
	near(mid.y, 0);
	near(bottom.y, 1);
	near(mid.x, 0);
	assert.deepEqual(plain(core.lightFromScroll(10, 0)), plain(core.REST_LIGHT));
});

test("approach eases toward the target, frame-rate independently", () => {
	const from = { x: 0, y: 0 };
	const to = { x: 1, y: -1 };
	assert.deepEqual(plain(core.approach(from, to, 0)), { x: 0, y: 0 });
	const one = core.approach(from, to, 0.032);
	const two = core.approach(core.approach(from, to, 0.016), to, 0.016);
	near(one.x, two.x);
	assert.ok(core.settled(core.approach(from, to, 5), to));
	assert.equal(core.settled(from, to), false);
});

test("canvasSize uses device pixels up to 2x and caps the longest side", () => {
	assert.deepEqual(plain(core.canvasSize(160, 100, 1)), { width: 160, height: 100 });
	assert.deepEqual(plain(core.canvasSize(160, 100, 3)), { width: 320, height: 200 });
	assert.deepEqual(plain(core.canvasSize(600, 300, 2)), { width: 640, height: 320 });
	assert.deepEqual(plain(core.canvasSize(0, 0, undefined)), { width: 1, height: 1 });
});

test("captionParts names the swatch and never implies a colour that isn't on file", () => {
	const paint = core.paintSwatch({ hex: "#AF1F41", finish: "pearl" }, "Morocco Red Mica");
	assert.deepEqual(plain(core.captionParts(paint, "R25")), { title: "Morocco Red Mica · R25", detail: "Pearl" });
	assert.deepEqual(plain(core.captionParts(core.paintSwatch(null, "Fire Storm"), "R38")), {
		title: "Fire Storm · R38",
		detail: "Colour not on file",
	});
	assert.deepEqual(plain(core.captionParts(core.paintSwatch(null, ""), "")), { title: "Paint", detail: "No colour on record" });
	assert.deepEqual(plain(core.captionParts(core.interiorSwatch(null, "Tan Leather, Power Seats"), "18T")), {
		title: "Tan Leather, Power Seats · 18T",
		detail: "Leather · representative shade",
	});
	assert.deepEqual(plain(core.captionParts(core.interiorSwatch({ material: "cloth", confidence: "decided" }, "MISSING"), "04H")), {
		title: "Interior · 04H",
		detail: "Cloth · Colour not on file",
	});
	assert.deepEqual(plain(core.captionParts(core.interiorSwatch({ material: "leather", confidence: "inferred" }, "MISSING"), "14T")), {
		title: "Interior · 14T",
		detail: "Leather (likely) · Colour not on file",
	});
	assert.deepEqual(plain(core.captionParts(core.interiorSwatch(null, ""), "")), { title: "Interior", detail: "No interior on record" });
});

test("pearl paints use their own texture coordinates; metallic, solid and interiors don't", () => {
	assert.equal(core.uniformsFor(core.paintSwatch({ hex: "#F2F2EE", finish: "pearl" }, "")).uvMap, 1);
	assert.equal(core.uniformsFor(core.paintSwatch({ hex: "#4F8EBF", finish: "metallic" }, "")).uvMap, 0);
	assert.equal(core.uniformsFor(core.paintSwatch({ hex: "#AA0000", finish: "solid" }, "")).uvMap, 0);
});
