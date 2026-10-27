// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller: pure helpers (no DOM). Loaded as a plain script before storyteller.js, and by the
// Node unit tests; exposes globalThis.VinStorytellerCore.
(() => {
	"use strict";

	const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/;
	const SAFE_URL = /^https?:\/\/[^\s<>"']+$/i;
	const TIER_NAMES = {
		one_of_one: "One of one",
		sub10: "Fewer than 10",
		sub25: "Fewer than 25",
		sub50: "Fewer than 50",
		sub100: "Fewer than 100",
	};
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

	const normalizeVin = (raw) => String(raw ?? "").replace(/\s+/g, "").toUpperCase();
	const NAME_MAX = 100; // StoriesTold.Name
	// The visitor's name as logged with their story: whitespace collapsed; "" when blank or too long.
	const normalizeName = (raw) => {
		const name = String(raw ?? "").trim().replace(/\s+/g, " ");
		return name.length <= NAME_MAX ? name : "";
	};
	const isValidVin = (vin) => VIN_PATTERN.test(vin);
	const isChassisNumber = (raw) => CHASSIS.test(normalizeVin(raw));
	const isSafeUrl = (url) => typeof url === "string" && SAFE_URL.test(url);
	const formatNumber = (n) => Number(n).toLocaleString(LOCALE);
	const positionText = (p) => `No. ${formatNumber(p.position)} of ${formatNumber(p.total)}`;
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
	const OTHER_MODELS = "Other"; // the record's other Nagoya-built cars (no Model name)
	const modelCountText = (c) => {
		if (c.model === OTHER_MODELS) return `${formatNumber(c.count)} other Nagoya-built ${c.count === 1 ? "car" : "cars"}`;
		return `${formatNumber(c.count)} ${c.count === 1 ? c.model : MODEL_PLURALS[c.model] || `${c.model}s`}`;
	};
	// "and"-joined list: "a", "a and b", "a, b and c".
	const listText = (items) =>
		items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
	// One cross-model line: the total sharing it and, when more than one model does, of which models.
	function breakdownParts(b) {
		let models = "";
		if (b.by_model.length > 1) models = `of which ${listText(b.by_model.map(modelCountText))}`;
		else if (b.by_model.length === 1 && b.total > 1 && b.by_model[0].model !== OTHER_MODELS) {
			models = `all ${MODEL_PLURALS[b.by_model[0].model] || b.by_model[0].model}`;
		}
		return { total: formatNumber(b.total), label: `${b.total === 1 ? "car" : "cars"} ${b.description}`, models };
	}
	// What the equipment code fits, item by item, for the spec table.
	const equipmentItemsText = (items) => items.map(codedText);

	// Live feedback while typing: the count so far and, once something is wrong, why. `ready` means the VIN
	// can be looked up; nothing here blocks submitting (the submit handler validates again).
	function vinCheck(raw) {
		const vin = normalizeVin(raw);
		if (CHASSIS.test(vin)) return { count: "JDM chassis", state: "ready", ready: true, message: "" };
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
			tier: TIER_NAMES[rarity.tier] || rarity.tier,
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

	globalThis.VinStorytellerCore = Object.freeze({
		normalizeVin,
		normalizeName,
		isValidVin,
		isChassisNumber,
		vinCheck,
		isSafeUrl,
		formatNumber,
		positionText,
		codedText,
		builtText,
		provenanceText,
		modelCountText,
		listText,
		breakdownParts,
		equipmentItemsText,
		badgeParts,
		historyParts,
		timelineText,
	});
})();
