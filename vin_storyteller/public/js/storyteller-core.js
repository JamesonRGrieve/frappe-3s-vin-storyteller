// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller: pure helpers (no DOM). Loaded as a plain script before storyteller.js, and by the
// Node unit tests; exposes globalThis.VinStorytellerCore.
(() => {
	"use strict";

	const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/;
	const SAFE_URL = /^https?:\/\/[^\s<>"']+$/i;

	const HISTORY_KINDS = {
		auction: "Auction",
		photo: "Photos",
		sale: "Sale",
		registration: "Registration",
		service: "Service",
		article: "Article",
		other: "Record",
	};
	const PROVENANCE_NAMES = {
		"CAPS 1999": "Mitsubishi's factory production record (the 1999 CAPS export)",
		"CAPS 2004": "Mitsubishi's factory production record (the 2004 CAPS build, which holds cars the 1999 export lost)",
		"ASA Japan 2008": "Mitsubishi's factory record of every Japanese-market GTO (the 2008 ASA Japan parts catalogue)",
	};
	// Model.Model as a count: "1 GTO", "2 Stealths".
	const MODEL_PLURALS = { "3000GT": "3000GTs", Stealth: "Stealths", GTO: "GTOs" };
	const LOCALE = "en-CA";
	const VIN_LENGTH = 17;
	const LOOK_ALIKES = /[IOQ]/;
	const NOT_VIN_CHARACTER = /[^A-Z0-9]/;
	// Japanese-market GTO chassis number (Z15A-/Z16A- and seven digits): not a VIN, and not in the record yet.
	const CHASSIS = /^Z1[56]A-?[0-9]{7}$/;
	const CHASSIS_SO_FAR = /^Z(1([56](A(-?[0-9]{0,7})?)?)?)?$/;
	// Export-market 3000GT frame number (1992-94 cars, e.g. DMNZ16APY00001): 14 characters, dashes ignored.
	const FRAME = /^(?=[A-Z0-9]{14}$)[A-Z]{2,3}Z16A[A-Z0-9]+$/;
	const isFrameNumber = (raw) => FRAME.test(normalizeVin(raw).replace(/-/g, ""));

	const normalizeVin = (raw) => String(raw ?? "").replace(/\s+/g, "").toUpperCase();
	const NAME_MAX = 100; // StoriesTold.Name
	// The visitor's name as logged with their story: whitespace collapsed; "" when blank or too long.
	const normalizeName = (raw) => {
		const name = String(raw ?? "").trim().replace(/\s+/g, " ");
		return name.length <= NAME_MAX ? name : "";
	};
	const isValidVin = (vin) => VIN_PATTERN.test(vin);
	const isChassisNumber = (raw) => CHASSIS.test(normalizeVin(raw));
	// A VIN, chassis or frame number handed in the address (?vin=…, e.g. from the stats page's search), or "".
	const vinFromAddress = (search) => {
		const vin = normalizeVin(new URLSearchParams(search || "").get("vin"));
		return isValidVin(vin) || isChassisNumber(vin) || isFrameNumber(vin) ? vin : "";
	};
	const isSafeUrl = (url) => typeof url === "string" && SAFE_URL.test(url);
	const formatNumber = (n) => Number(n).toLocaleString(LOCALE);
	const positionText = (p) => `#${formatNumber(p.position)} of ${formatNumber(p.total)}`;
	const UNDECODED = "MISSING"; // the record's placeholder for a code nobody has deciphered yet
	const codedText = (c) => {
		if (!c.code) return "Not known"; // a car on record from another source than the factory export
		return c.description === UNDECODED ? `Not yet decoded · ${c.code}` : `${c.description} · ${c.code}`;
	};
	// The "Built in …" line, or for a car that isn't in the factory export, where its record came from.
	const builtText = (story) =>
		story.partial
			? `Not in Mitsubishi's factory export: this car is on record from ${story.provenance}, so its build date, ` +
				"colours and equipment aren't known yet."
			: `Built in ${story.built}.`;
	const provenanceText = (p) => `Production record source: ${PROVENANCE_NAMES[p] || p}.`;
	// A model count's noun alone: "3000GT", "Stealths".
	const modelNoun = (c) => (c.count === 1 ? c.model : MODEL_PLURALS[c.model] || `${c.model}s`);
	const modelCountText = (c) =>
		`${formatNumber(c.count)} ${c.count === 1 ? c.model : MODEL_PLURALS[c.model] || `${c.model}s`}`;
	// "and"-joined list: "a", "a and b", "a, b and c".
	const listText = (items) =>
		items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
	// One cross-model line: the total sharing it and, when more than one model does, of which models.
	function breakdownParts(b) {
		let models = "";
		if (b.by_model.length > 1) models = `of which ${listText(b.by_model.map(modelCountText))}`;
		else if (b.by_model.length === 1 && b.total > 1) {
			models = `all ${MODEL_PLURALS[b.by_model[0].model] || b.by_model[0].model}`;
		}
		return { total: formatNumber(b.total), label: `${b.total === 1 ? "car" : "cars"} ${b.description}`, models };
	}
	// What the record key is called: a VIN, a JDM chassis number or an export frame number.
	const keyLabel = (key) => (key.length === 17 ? "VIN" : /^Z1[56]A-/.test(key) ? "Chassis number" : "Frame number");
	// What the equipment code fits, item by item, for the spec table.
	const equipmentItemsText = (items) => items.map(codedText);
	// Factory-fitted equipment the parts catalogue gives the car's grade and build date (e.g. headlamp washers).
	const featuresText = (features) => (features || []).map((f) => `${f} · fitted at the factory (parts catalogue)`);

	// Live feedback while typing: the count so far and, once something is wrong, why. `ready` means the VIN
	// can be looked up; nothing here blocks submitting (the submit handler validates again).
	function vinCheck(raw) {
		const vin = normalizeVin(raw);
		if (CHASSIS.test(vin)) return { count: "JDM chassis", state: "ready", ready: true, message: "" };
		if (isFrameNumber(vin)) return { count: "frame no.", state: "ready", ready: true, message: "" };
		if (vin.length > 1 && CHASSIS_SO_FAR.test(vin)) {
			return { count: "chassis?", state: "typing", ready: false, message: "" };
		}
		const count = `${vin.length} / ${VIN_LENGTH}`;
		if (NOT_VIN_CHARACTER.test(vin)) return { count, state: "bad", ready: false, message: "Use letters and numbers only." };
		if (LOOK_ALIKES.test(vin)) {
			return { count, state: "bad", ready: false, message: "VINs never contain I, O or Q. Did you mean 1 or 0?" };
		}
		if (vin.length > VIN_LENGTH) return { count, state: "bad", ready: false, message: `That's more than ${VIN_LENGTH} characters.` };
		if (vin.length === VIN_LENGTH) return { count, state: "ready", ready: true, message: "" };
		return { count, state: vin.length ? "typing" : "empty", ready: false, message: "" };
	}

	function badgeParts(rarity) {
		return {
			tier: rarity.tier_name || rarity.tier, // the tier's name comes with the story (story.RARITY_TIERS)
			count: `1 of ${formatNumber(rarity.total)}`,
			scope: rarity.description,
		};
	}

	function historyParts(record) {
		return {
			meta: [record.date, HISTORY_KINDS[record.kind] || HISTORY_KINDS.other].filter(Boolean).join(" · "),
			title: record.title,
			url: isSafeUrl(record.url) ? record.url : null,
			source: [record.source && `Source: ${record.source}`, record.provenance && `Added by: ${record.provenance}`]
				.filter(Boolean)
				.join(" · "),
		};
	}

	function timelineText(story) {
		return (
			`Production for the ${story.model_year} model year started in ${story.year_started}, and the first ` +
			`${story.vehicle_name} came off the line in ${story.model_started}. A production period is about one ` +
			"third of a month, or approximately 10 days."
		);
	}

	// Per-code pages (card 330): /storyteller/paint, /storyteller/interior and /storyteller/option, each an index
	// and, given a code, that code's page. A code is addressed by query (?code=T87, and &model=Z16A for an option),
	// which the public site router serves today, or by path (/storyteller/paint/T87, /storyteller/option/Z16A/302)
	// once it serves dynamic routes; both are read, and links are written in the page's data-code-routes style.
	const CODES_PATH = "/storyteller";
	const CODE_KINDS = Object.freeze(["paint", "interior", "option"]);
	const KIND_NAMES = Object.freeze({ paint: "Paint", interior: "Interior", option: "Option" });
	const KIND_PLURALS = Object.freeze({ paint: "Paint codes", interior: "Interior codes", option: "Option codes" });
	// What CAPS writes when it holds no code for a car; never a code page.
	const PLACEHOLDERS = { paint: "EXT", interior: "INT", option: "EQU" };
	const CODE = /^[A-Z0-9]{2,4}$/;
	const MODEL_CODE = /^[A-Z][0-9]{2}[A-Z]$/;
	const ROUTE = /^\/storyteller\/(paint|interior|option)(?:\/([^?#]*))?$/;
	const canonical = (raw) => String(raw ?? "").trim().toUpperCase();
	const decoded = (segment) => {
		try {
			return decodeURIComponent(segment);
		} catch {
			return ""; // a malformed escape is no code
		}
	};
	const isCode = (kind, code) => CODE_KINDS.includes(kind) && CODE.test(code) && code !== PLACEHOLDERS[kind];

	// The address of a kind's index.
	const indexHref = (kind) => `${CODES_PATH}/${kind}`;

	// The address of a code's page, or null when it has none (no code, a not-recorded placeholder, an option with no
	// model code).
	// Links from a story to the stats page's search (card 391): the cars built exactly like it (its identical-car
	// count: same model year, model line, paint code, interior and option), and the cars built in the same production
	// period or month. null when the story lacks what the search needs (a partial record).
	const STATS_PATH = "/storyteller/stats";
	const STORY_CODE = /^[A-Z0-9-]{1,8}$/;
	const BUILT = /^[0-9]{4}[0-3]$/;

	function exploreHref(story, kind) {
		const params = new URLSearchParams();
		if (!story || story.partial || !STORY_CODE.test(story.line_code || "")) return null;
		if (kind === "twins") {
			const codes = [story.exterior?.code, story.interior?.code, story.equipment?.code];
			if (!codes.every((c) => STORY_CODE.test(c || "")) || !/^[0-9]{4}$/.test(story.model_year || "")) return null;
			params.set("from", story.model_year);
			params.set("to", story.model_year);
			params.set("find_line", story.line_code);
			params.set("find_paint", codes[0]);
			params.set("find_interior", codes[1]);
			params.set("find_option", codes[2]);
			params.set("find_exact", "1");
			params.set("find_sort", "vin");
		} else if (kind === "period" || kind === "month") {
			if (!BUILT.test(story.built_code || "")) return null;
			const built = kind === "period" ? story.built_code : story.built_code.slice(0, 4);
			params.set("find_built_from", built);
			params.set("find_built_to", built);
			if (/^[a-z]{2,6}$/.test(story.series || "")) params.set("find_series", story.series);
			params.set("find_sort", "built");
		} else return null;
		return `${STATS_PATH}?${params.toString()}#find`;
	}

	function codeHref(kind, rawCode, rawModel, style = "query") {
		const code = canonical(rawCode);
		const model = canonical(rawModel);
		if (!isCode(kind, code)) return null;
		if (kind === "option" && !MODEL_CODE.test(model)) return null;
		if (style === "path") {
			return kind === "option" ? `${indexHref(kind)}/${model}/${code}` : `${indexHref(kind)}/${code}`;
		}
		const query = kind === "option" ? `model=${model}&code=${code}` : `code=${code}`;
		return `${indexHref(kind)}?${query}`;
	}

	// What a code page's address asks for: { kind, code, model } (code "" for the kind's index, and `invalid` when the
	// address names something that can't be a code), or null when it isn't a code page's address.
	function parseCodeRoute(pathname, search) {
		const match = ROUTE.exec(String(pathname ?? "").replace(/\/+$/, ""));
		if (!match) return null;
		const kind = match[1];
		const segments = (match[2] || "").split("/").filter(Boolean).map((s) => canonical(decoded(s)));
		const params = new URLSearchParams(search || "");
		let code = canonical(params.get("code"));
		let model = canonical(params.get("model"));
		if (segments.length) [code, model] = kind === "option" ? [segments[1] || "", segments[0]] : [segments[0], ""];
		if (kind !== "option") model = "";
		if (!segments.length && !code && !model) return { kind, code: "", model: "" };
		const valid = isCode(kind, code) && (kind !== "option" || MODEL_CODE.test(model));
		return valid ? { kind, code, model } : { kind, code: "", model: "", invalid: true };
	}

	// A code page's heading: "Paint T87 · Fiji Blue", "Option 302 · Z16A".
	function codeTitle(page) {
		const label = `${KIND_NAMES[page.kind] || page.kind} ${page.code}`;
		if (page.kind === "option") return `${label} · ${page.model_code}`;
		return page.description && page.description !== UNDECODED ? `${label} · ${page.description}` : label;
	}

	// What the code is called: a paint by each manufacturer, else its description, else not decoded yet.
	function codeNamesText(page) {
		const also = page.same_paint && page.same_paint.length ? ` · Also recorded as ${page.same_paint.join(", ")}` : "";
		if (page.names && page.names.length) return page.names.map((n) => `${n.manufacturer}: ${n.name}`).join(" · ") + also;
		if (page.description && page.description !== UNDECODED) return page.description + also;
		return "Not yet decoded. If you know what this code means, please email storyteller@3shub.com." + also;
	}

	function spanText(page) {
		if (!page.first_built) return "";
		if (page.first_built === page.last_built) return `Every one was built in ${page.first_built}.`;
		return `The first was built in ${page.first_built}, and the last in ${page.last_built}.`;
	}

	// A share of the code's total: "48%", or "0.4%" under ten percent.
	function shareText(count, total) {
		if (!total) return "";
		const share = (count * 100) / total;
		return `${share.toFixed(share < 10 ? 1 : 0)}%`;
	}

	// A paint's interior or an interior's paint on a code page.
	const pairingText = (p) => {
		if (!p.code) return "Not on record";
		return p.description === UNDECODED ? p.code : `${p.description} · ${p.code}`;
	};

	// What an option code fits for one grade and model year.
	function fitParts(fit) {
		return {
			grade: `${fit.model_year} · ${codedText(fit.classification)}`,
			items: fit.items.map(codedText),
			cars: `${formatNumber(fit.cars)} ${fit.cars === 1 ? "car" : "cars"} built so`,
		};
	}

	// One row of a kind's index.
	function indexEntryParts(entry) {
		return {
			code: entry.model_code ? `${entry.code} · ${entry.model_code}` : entry.code,
			description: entry.description === UNDECODED ? "Not yet decoded" : entry.description,
			total: formatNumber(entry.total),
			models: listText(entry.by_model.map(modelCountText)),
		};
	}
	// --- the printable build sheet (card 391) -------------------------------------------------------------------

	// What a build sheet's reference is computed from: the car's key and every factory-record field it prints. The
	// page shows the same reference, so a printed sheet can be checked against the record (a changed record gives a
	// different reference).
	function referenceSource(story) {
		return [
			"3shub-build-sheet-v1",
			story.vin,
			story.model_year,
			story.line_code,
			story.classification?.code,
			story.exterior?.code,
			story.interior?.code,
			story.equipment?.code,
			story.built_code,
			story.provenance,
		]
			.map((v) => String(v || ""))
			.join("|");
	}

	// '3SH-' and the first 8 hex digits of the source's SHA-256, in two groups: '3SH-1A2B-3C4D'.
	function formatReference(hex) {
		const h = String(hex || "").toUpperCase();
		return /^[0-9A-F]{8}/.test(h) ? `3SH-${h.slice(0, 4)}-${h.slice(4, 8)}` : "";
	}

	// The address a sheet's QR code and link open: the story page with the VIN filled in.
	function storyAddress(origin, vin) {
		return `${String(origin || "").replace(/\/$/, "")}/storyteller?vin=${encodeURIComponent(vin)}`;
	}

	// A story's share link (card 391): its link-preview page, which sends people on to the story.
	function shareHref(origin, vin) {
		return `${String(origin || "").replace(/\/$/, "")}/api/method/vin_storyteller.api.share?vin=${encodeURIComponent(vin)}`;
	}

	// The sheet's rows: [label, value], from the factory record only.
	function sheetRows(story) {
		const rows = [
			[keyLabel(story.vin), story.vin],
			["Model year", story.model_year || "Not known"],
			["Model", [story.manufacturer, story.model, story.trim].filter((p) => p && p !== UNDECODED).join(" ")],
		];
		if (story.classification?.code) rows.push(["Grade", codedText(story.classification)]);
		rows.push(["Exterior colour", codedText(story.exterior)], ["Interior", codedText(story.interior)], ["Option code", codedText(story.equipment)]);
		const items = equipmentItemsText(story.equipment_items || []);
		if (items.length) rows.push(["Option contents", items.join("; ")]);
		if (story.built) rows.push(["Built", story.built]);
		if (!story.partial) {
			rows.push(
				["In the model year", positionText(story.in_year)],
				["Of its model", positionText(story.in_model)],
				["In its colour", positionText(story.in_colour)],
				["Among identical cars", positionText(story.among_identical)],
			);
		}
		rows.push(["Record", PROVENANCE_NAMES[story.provenance] || story.provenance]);
		return rows;
	}

	// --- the colour chart (card 391): every paint or interior as a swatch card, from the kind's index and swatches.json

	// Model years as calendar ranges: ['00', '91', '92', '95', '96'] -> '1991–1992, 1995–1996, 2000'.
	function yearsText(years) {
		const full = [...new Set((years || []).filter((y) => /^[0-9]{2}$/.test(y)))]
			.map((y) => Number(y) + (Number(y) < 50 ? 2000 : 1900))
			.sort((a, b) => a - b);
		const runs = [];
		for (const year of full) {
			const last = runs.at(-1);
			if (last && year === last[1] + 1) last[1] = year;
			else runs.push([year, year]);
		}
		return runs.map(([a, b]) => (a === b ? String(a) : `${a}\u2013${b}`)).join(", ");
	}

	// A colour's hue (0-360) and lightness from '#rrggbb', for ordering the chart like a paint chip book: greys
	// (low saturation) first, light to dark, then by hue.
	function hueKey(hex) {
		const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
		if (!m) return [2, 0, 0];
		const [r, g, b] = m.slice(1).map((h) => parseInt(h, 16) / 255);
		const max = Math.max(r, g, b);
		const min = Math.min(r, g, b);
		const light = (max + min) / 2;
		const delta = max - min;
		const sat = delta === 0 ? 0 : delta / (1 - Math.abs(2 * light - 1));
		if (sat < 0.12) return [0, 1 - light, 0];
		let hue = max === r ? ((g - b) / delta) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
		hue = (hue * 60 + 360) % 360;
		return [1, Math.round(hue / 15), 1 - light];
	}

	const CHART_SORTS = Object.freeze({ cars: "Most built", colour: "Colour", code: "Code" });

	// The chart's cards: one per paint (a code's "A" form, e.g. WA5, folds into its plain code W75 with its cars
	// added) or per interior, with its names, years and cars by model, in the chosen order.
	function chartEntries(kind, codes, data, sort = "cars") {
		const table = (data && data[kind]) || {};
		const cards = new Map();
		for (const entry of codes || []) {
			const info = table[entry.code] || {};
			const home = kind === "paint" && info.same_paint_as && table[info.same_paint_as] ? info.same_paint_as : entry.code;
			const homeInfo = table[home] || info;
			if (!cards.has(home)) {
				cards.set(home, {
					code: home,
					also: [],
					name: homeInfo.mitsubishi_name || homeInfo.name || homeInfo.description || (entry.description !== UNDECODED ? entry.description : ""),
					dodge_name: homeInfo.dodge_name && homeInfo.dodge_name !== homeInfo.mitsubishi_name ? homeInfo.dodge_name : "",
					detail: kind === "interior" ? [homeInfo.colour, homeInfo.material !== "unknown" ? homeInfo.material : ""].filter(Boolean).join(" ") : homeInfo.finish || "",
					years: yearsText(homeInfo.model_years),
					hex: homeInfo.hex || homeInfo.sampled_hex || "",
					total: 0,
					by_model: new Map(),
				});
			}
			const card = cards.get(home);
			if (home !== entry.code) card.also.push(entry.code);
			card.total += entry.total;
			for (const m of entry.by_model || []) card.by_model.set(m.model, (card.by_model.get(m.model) || 0) + m.count);
		}
		const list = [...cards.values()].map((c) => ({ ...c, also: c.also.sort(), by_model: [...c.by_model].map(([model, count]) => ({ model, count })) }));
		const byCode = (a, b) => a.code.localeCompare(b.code);
		const keyed = (a, b) => {
			const [x, y] = [hueKey(a.hex), hueKey(b.hex)];
			for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] - y[i];
			return byCode(a, b);
		};
		return list.sort(sort === "code" ? byCode : sort === "colour" ? keyed : (a, b) => b.total - a.total || byCode(a, b));
	}

	// A chart card's lines of text.
	function chartCardParts(card) {
		const codes = [card.code, ...card.also].join(" / ");
		const detail = card.detail ? card.detail.charAt(0).toUpperCase() + card.detail.slice(1) : "";
		// An interior nobody has named yet is titled by its colour and material where those are known.
		const named = card.name && card.name !== UNDECODED;
		return {
			codes,
			name: named ? card.name : detail || "Not yet decoded",
			dodge: card.dodge_name ? `Dodge: ${card.dodge_name}` : "",
			detail: named ? detail : "",
			years: card.years,
			cars: `${formatNumber(card.total)} ${card.total === 1 ? "car" : "cars"}`,
			models: listText(card.by_model.map(modelCountText)),
		};
	}

	// The paint and interior swatches show when the record has either code; a car known only from another
	// source has neither, and gets no swatches rather than two empty panels.
	const swatchesShown = (story) => Boolean(story.exterior?.code || story.interior?.code);
	// What each swatch draws: its kind, the car's code and the record's description for it.
	const swatchRequests = (story) => [
		{ kind: "paint", code: story.exterior?.code || "", description: story.exterior?.description || "", make: story.manufacturer || "" },
		{ kind: "interior", code: story.interior?.code || "", description: story.interior?.description || "" },
	];

	globalThis.VinStorytellerCore = Object.freeze({
		CODE_KINDS,
		KIND_NAMES,
		KIND_PLURALS,
		referenceSource,
		formatReference,
		storyAddress,
		shareHref,
		sheetRows,
		CHART_SORTS,
		yearsText,
		hueKey,
		chartEntries,
		chartCardParts,
		indexHref,
		codeHref,
		exploreHref,
		parseCodeRoute,
		codeTitle,
		codeNamesText,
		spanText,
		shareText,
		pairingText,
		fitParts,
		indexEntryParts,
		normalizeVin,
		normalizeName,
		isValidVin,
		isChassisNumber,
		isFrameNumber,
		vinFromAddress,
		keyLabel,
		vinCheck,
		isSafeUrl,
		formatNumber,
		positionText,
		codedText,
		builtText,
		provenanceText,
		modelCountText,
		modelNoun,
		listText,
		breakdownParts,
		equipmentItemsText,
		featuresText,
		badgeParts,
		historyParts,
		timelineText,
		swatchesShown,
		swatchRequests,
	});
})();
