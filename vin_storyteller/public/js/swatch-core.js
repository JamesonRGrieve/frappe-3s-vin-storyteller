// SPDX-License-Identifier: AGPL-3.0-or-later
// Paint and interior swatches: pure logic (no DOM). Colour maths, finish and material choice, the shader's
// parameters and the motion input. Loaded as a plain script before swatch.js, and by the Node unit tests;
// exposes globalThis.VinSwatchCore.
(() => {
	"use strict";

	const HEX = /^#?([0-9a-f]{6})$/i;
	const clamp = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));

	// "#RRGGBB" -> { r, g, b } in 0..1 (sRGB), or null when it isn't a 6-digit hex colour.
	function parseHex(hex) {
		const match = HEX.exec(String(hex ?? "").trim());
		if (!match) return null;
		const n = Number.parseInt(match[1], 16);
		return { r: ((n >> 16) & 255) / 255, g: ((n >> 8) & 255) / 255, b: (n & 255) / 255 };
	}
	const toHex = (c) =>
		`#${[c.r, c.g, c.b]
			.map((v) => Math.round(clamp(v) * 255).toString(16).padStart(2, "0"))
			.join("")
			.toUpperCase()}`;

	// sRGB transfer function, per channel.
	const srgbToLinear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
	const linearToSrgb = (v) => (v <= 0.0031308 ? v * 12.92 : 1.055 * v ** (1 / 2.4) - 0.055);
	const toLinear = (c) => ({ r: srgbToLinear(c.r), g: srgbToLinear(c.g), b: srgbToLinear(c.b) });
	const fromLinear = (c) => ({ r: linearToSrgb(c.r), g: linearToSrgb(c.g), b: linearToSrgb(c.b) });
	// Mix in linear light (what paint mixing and lighting do), returning sRGB.
	function mix(a, b, t) {
		const la = toLinear(a);
		const lb = toLinear(b);
		return fromLinear({ r: la.r + (lb.r - la.r) * t, g: la.g + (lb.g - la.g) * t, b: la.b + (lb.b - la.b) * t });
	}
	// Relative luminance (WCAG), 0..1.
	function luminance(c) {
		const l = toLinear(c);
		return 0.2126 * l.r + 0.7152 * l.g + 0.0722 * l.b;
	}
	function rgbToHsl({ r, g, b }) {
		const max = Math.max(r, g, b);
		const min = Math.min(r, g, b);
		const l = (max + min) / 2;
		if (max === min) return { h: 0, s: 0, l };
		const d = max - min;
		const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
		let h;
		if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
		else if (max === g) h = (b - r) / d + 2;
		else h = (r - g) / d + 4;
		return { h: h * 60, s, l };
	}
	function hslToRgb({ h, s, l }) {
		const hue = (((h % 360) + 360) % 360) / 360;
		if (s === 0) return { r: l, g: l, b: l };
		const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
		const p = 2 * l - q;
		const channel = (t) => {
			const u = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
			if (u < 1 / 6) return p + (q - p) * 6 * u;
			if (u < 1 / 2) return q;
			if (u < 2 / 3) return p + (q - p) * (2 / 3 - u) * 6;
			return p;
		};
		return { r: channel(hue + 1 / 3), g: channel(hue), b: channel(hue - 1 / 3) };
	}
	const rotateHue = (c, degrees) => {
		const hsl = rgbToHsl(c);
		return hslToRgb({ ...hsl, h: hsl.h + degrees });
	};

	// Finish from a paint name: Mitsubishi calls its pearls "Mica" or "Pearl"; Dodge says "Pearl" or "Metallic".
	function finishFromName(name) {
		const text = String(name ?? "");
		if (!text || text === "MISSING") return "";
		if (/\b(pearl|mica)\b/i.test(text)) return "pearl";
		if (/\bmetallic\b/i.test(text)) return "metallic";
		return "solid";
	}

	// How each finish is drawn. flake: metallic/pearl flake coverage and sparkle; pearl: how strongly the
	// interference colour shifts with angle; gloss: clearcoat sharpness; peel: orange-peel bump height.
	const FINISHES = Object.freeze({
		solid: Object.freeze({ flakeDensity: 0, flakeSize: 1, flakeStrength: 0, pearl: 0, gloss: 0.9, peel: 0.35 }),
		metallic: Object.freeze({ flakeDensity: 0.75, flakeSize: 1.4, flakeStrength: 0.9, pearl: 0.08, gloss: 0.85, peel: 0.3 }),
		pearl: Object.freeze({ flakeDensity: 0.5, flakeSize: 1.8, flakeStrength: 0.55, pearl: 0.6, gloss: 0.88, peel: 0.3 }),
	});
	const NOT_ON_FILE = "Colour not on file";
	const NEUTRAL = "#7A7C80"; // the "not on file" panel: a mid grey that claims no colour

	// The flake / highlight colour when no published one exists: a metallic's flake is its own colour lifted
	// toward white; a pearl's interference colour sits a little round the hue wheel (warm on a white pearl).
	function derivedFlake(base, finish) {
		if (finish === "pearl") {
			const hsl = rgbToHsl(base);
			const shifted = hsl.s < 0.08 ? hslToRgb({ h: 40, s: 0.35, l: clamp(hsl.l + 0.3, 0.3, 0.85) }) : rotateHue(base, 28);
			return mix(shifted, { r: 1, g: 1, b: 1 }, 0.35);
		}
		return mix(base, { r: 1, g: 1, b: 1 }, 0.45);
	}

	// Which published value to draw: where Mitsubishi and Dodge publish different values for one code, a Dodge
	// car is drawn in Dodge's (operator 2026-10-27: by the car's brand). With no car (a code page), a code only
	// Stealths wore is Dodge's; any other is Mitsubishi's.
	function paintValue(entry, make) {
		const dodge = parseHex(entry?.dodge_hex);
		const stealthOnly = Array.isArray(entry?.models) && entry.models.length === 1 && entry.models[0] === "Stealth";
		if (dodge && (make === "Dodge" || (!make && stealthOnly))) return { base: dodge, source: entry.dodge_source || "" };
		return { base: parseHex(entry?.hex), source: entry?.source || "" };
	}

	// One paint swatch from the shipped table entry for its code, the story's description (which may be newer
	// than the table) and the car's make. `status` is "sourced" with a published hex, "derived" with an
	// approximate value derived from named evidence (it says so); otherwise the swatch is the neutral
	// "colour not on file" panel and never a guess.
	function paintSwatch(entry, description, make = "") {
		const named = description && description !== "MISSING" ? description : "";
		const name = named || entry?.name || "";
		const finish = finishFromName(named) || entry?.finish || finishFromName(name) || "solid";
		const { base, source } = paintValue(entry, make);
		if (!base) {
			return { kind: "paint", status: "missing", name, finish, label: NOT_ON_FILE, base: parseHex(NEUTRAL), flake: null, params: null };
		}
		const flake = parseHex(entry.flake_hex) || derivedFlake(base, finish);
		const status = entry.approximate ? "derived" : "sourced";
		return { kind: "paint", status, approximate: Boolean(entry.approximate), name, finish, label: name, base, flake, params: FINISHES[finish] || FINISHES.solid, source };
	}

	// Interior material. An explicit "Leather" / "Cloth" in the description wins; then the shipped table's
	// decision (which says how it was made); otherwise unknown.
	function interiorMaterial(entry, description) {
		const text = String(description ?? "");
		if (/\bleather\b/i.test(text)) return { material: "leather", confidence: "decided", basis: "description" };
		if (/\b(cloth|fabric|velour|tricot)\b/i.test(text)) return { material: "cloth", confidence: "decided", basis: "description" };
		if (entry && (entry.material === "leather" || entry.material === "cloth")) {
			return { material: entry.material, confidence: entry.confidence || "inferred", basis: entry.basis || "table" };
		}
		return { material: "unknown", confidence: "", basis: "" };
	}

	// Representative tones for the colour word in an interior description. These are generic shades for the
	// word, not factory trim values (no published trim colours exist in the record); the label says so.
	const INTERIOR_TONES = Object.freeze([
		["charcoal", "#3A3B3E"],
		["black", "#1E1F21"],
		["gray", "#6E7074"],
		["grey", "#6E7074"],
		["tan", "#B08A62"],
		["beige", "#C8B596"],
		["ivory", "#E2D9C3"],
		["white", "#DAD7CF"],
		["red", "#7E1F24"],
		["blue", "#2E3F63"],
		["brown", "#5B4130"],
	]);
	function interiorTone(description) {
		const text = String(description ?? "").toLowerCase();
		for (const [word, hex] of INTERIOR_TONES) {
			if (new RegExp(`\\b${word}\\b`).test(text)) return { word, hex };
		}
		return null;
	}
	const MATERIAL_PARAMS = Object.freeze({
		leather: Object.freeze({ gloss: 0.35, peel: 0.6 }),
		cloth: Object.freeze({ gloss: 0.05, peel: 0.8 }),
		unknown: Object.freeze({ gloss: 0.2, peel: 0.3 }),
	});
	// The colour word comes from the description when it names one, else from the shipped table (named, from
	// the catalogue's trim parts, or from the US trim letter); a letter-inferred colour is said to be likely.
	function interiorSwatch(entry, description) {
		const named = description && description !== "MISSING" ? description : entry?.description || "";
		const { material, confidence, basis } = interiorMaterial(entry, named);
		const ownTone = interiorTone(named);
		const tone = ownTone || interiorTone(entry?.colour);
		const colourConfidence = ownTone ? "named" : tone ? entry.colour_confidence || "" : "";
		return {
			kind: "interior",
			status: tone ? "named" : "missing",
			material,
			confidence,
			basis,
			colour: ownTone ? "" : tone ? entry.colour : "",
			colourConfidence,
			name: named,
			label: tone ? named || entry.colour : NOT_ON_FILE,
			base: parseHex(tone ? tone.hex : NEUTRAL),
			params: MATERIAL_PARAMS[material],
		};
	}

	// Shader mode per swatch: 0 paint, 1 perforated leather, 2 cloth weave, 3 plain (nothing on file).
	const MODES = Object.freeze({ paint: 0, leather: 1, cloth: 2, plain: 3 });
	function shaderMode(swatch) {
		if (swatch.kind === "paint") return swatch.status === "missing" ? MODES.plain : MODES.paint;
		return MODES[swatch.material] ?? MODES.plain;
	}
	// Uniform values for one swatch: colours in linear light, finish parameters as numbers.
	// The ?v= of an asset URL ("" when it has none), and a URL with that version added.
	function versionOf(url) {
		const match = /[?&]v=([^&#]*)/.exec(String(url ?? ""));
		return match ? decodeURIComponent(match[1]) : "";
	}
	const versionedUrl = (path, version) => (version ? `${path}?v=${encodeURIComponent(version)}` : path);

	function uniformsFor(swatch, seed = 0) {
		const base = toLinear(swatch.base);
		const flake = toLinear(swatch.flake || swatch.base);
		const p = swatch.params || {};
		return {
			mode: shaderMode(swatch),
			base: [base.r, base.g, base.b],
			flake: [flake.r, flake.g, flake.b],
			finish: [p.flakeDensity ?? 0, p.flakeSize ?? 1, p.flakeStrength ?? 0, p.pearl ?? 0],
			surface: [p.gloss ?? 0.2, p.peel ?? 0.3],
			// Which texture coordinates the paint's flake and interference layers use: 1 for a pearl, whose mica
			// platelets lie in long swirled streaks, else 0 (the panel's own coordinates) (operator 2026-10-27).
			uvMap: swatch.kind === "paint" && swatch.finish === "pearl" ? 1 : 0,
			seed: ((seed % 997) + 997) % 997,
		};
	}
	// A stable seed per code, so each swatch's flake pattern differs but never changes between visits.
	function seedFor(text) {
		let h = 2166136261;
		for (const ch of String(text ?? "")) h = Math.imul(h ^ ch.codePointAt(0), 16777619);
		return (h >>> 0) % 997;
	}

	// Without WebGL: a still CSS background in the swatch's colour, lit from the top left.
	function staticBackground(swatch) {
		const hi = toHex(mix(swatch.base, { r: 1, g: 1, b: 1 }, swatch.kind === "paint" ? 0.35 : 0.15));
		const lo = toHex(mix(swatch.base, { r: 0, g: 0, b: 0 }, 0.35));
		return `linear-gradient(135deg, ${hi} 0%, ${toHex(swatch.base)} 45%, ${lo} 100%)`;
	}

	// Motion. The light is a point over the swatch in -1..1 on each axis (x right, y down).
	const REST_LIGHT = Object.freeze({ x: -0.45, y: -0.55 });
	// "still" under prefers-reduced-motion; "pointer" with a hovering fine pointer (desktop); "scroll" otherwise.
	function motionMode({ reducedMotion, finePointer }) {
		if (reducedMotion) return "still";
		return finePointer ? "pointer" : "scroll";
	}
	// Desktop: the cursor's place in the viewport moves the light across every swatch together.
	function lightFromPointer(x, y, width, height) {
		if (!(width > 0 && height > 0)) return { ...REST_LIGHT };
		return { x: clamp((x / width) * 2 - 1, -1, 1), y: clamp((y / height) * 2 - 1, -1, 1) };
	}
	// Mobile: a swatch's place in the viewport as it scrolls by sweeps the light from top to bottom, with a
	// gentle sideways drift so the flake keeps catching it.
	function lightFromScroll(centerY, viewportHeight) {
		if (!(viewportHeight > 0)) return { ...REST_LIGHT };
		const t = clamp(centerY / viewportHeight, 0, 1);
		return { x: Math.sin(t * Math.PI * 2) * 0.6, y: t * 2 - 1 };
	}
	// Ease the light toward its target: frame-rate independent exponential smoothing.
	function approach(current, target, dtSeconds, rate = 8) {
		const k = 1 - Math.exp(-rate * Math.max(0, dtSeconds));
		return { x: current.x + (target.x - current.x) * k, y: current.y + (target.y - current.y) * k };
	}
	const settled = (a, b, epsilon = 0.002) => Math.abs(a.x - b.x) < epsilon && Math.abs(a.y - b.y) < epsilon;
	// Backing-store size for a swatch canvas: device pixels, capped so a big swatch stays cheap.
	function canvasSize(cssWidth, cssHeight, dpr, maxSide = 640) {
		const scale = Math.min(Math.max(dpr || 1, 1), 2);
		let w = Math.max(1, Math.round(cssWidth * scale));
		let h = Math.max(1, Math.round(cssHeight * scale));
		const over = Math.max(w, h) / maxSide;
		if (over > 1) {
			w = Math.max(1, Math.round(w / over));
			h = Math.max(1, Math.round(h / over));
		}
		return { width: w, height: h };
	}

	// Caption lines for a swatch: what it is, and what's behind it.
	const FINISH_NAMES = { solid: "Solid", metallic: "Metallic", pearl: "Pearl" };
	const MATERIAL_NAMES = { leather: "Leather", cloth: "Cloth", unknown: "Trim material not on file" };
	function captionParts(swatch, code) {
		const coded = (text) => (code ? `${text} · ${code}` : text);
		if (swatch.kind === "paint") {
			if (swatch.status === "missing") {
				return { title: coded(swatch.name || "Paint"), detail: code ? NOT_ON_FILE : "No colour on record" };
			}
			const finish = FINISH_NAMES[swatch.finish] || "";
			return { title: coded(swatch.name || "Paint"), detail: swatch.approximate ? [finish, "approximate colour"].filter(Boolean).join(" · ") : finish };
		}
		// An inferred material (from the code's suffix letter) is said to be likely, not stated as fact.
		const material = MATERIAL_NAMES[swatch.material] + (swatch.confidence === "inferred" ? " (likely)" : "");
		if (swatch.status !== "named") {
			return { title: coded(swatch.name && swatch.name !== "MISSING" ? swatch.name : "Interior"), detail: code ? `${material} · ${NOT_ON_FILE}` : "No interior on record" };
		}
		if (swatch.colour) {
			const colour = swatch.colour + (swatch.colourConfidence === "letter" ? " (likely)" : "");
			const what = swatch.material === "unknown" ? `${colour} · ${material}` : `${colour} ${material.toLowerCase()}`;
			return { title: coded(swatch.name && swatch.name !== swatch.colour ? swatch.name : "Interior"), detail: `${what} · representative shade` };
		}
		return { title: coded(swatch.name), detail: `${material} · representative shade` };
	}

	globalThis.VinSwatchCore = Object.freeze({
		parseHex,
		toHex,
		srgbToLinear,
		linearToSrgb,
		mix,
		luminance,
		rgbToHsl,
		hslToRgb,
		rotateHue,
		finishFromName,
		FINISHES,
		NOT_ON_FILE,
		NEUTRAL,
		derivedFlake,
		paintSwatch,
		interiorMaterial,
		INTERIOR_TONES,
		interiorTone,
		interiorSwatch,
		paintValue,
		MODES,
		shaderMode,
		versionOf,
		versionedUrl,
		uniformsFor,
		seedFor,
		staticBackground,
		REST_LIGHT,
		motionMode,
		lightFromPointer,
		lightFromScroll,
		approach,
		settled,
		canvasSize,
		captionParts,
	});
})();
